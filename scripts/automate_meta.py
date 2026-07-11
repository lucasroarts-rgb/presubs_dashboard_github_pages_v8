from __future__ import annotations

import argparse
import csv
import getpass
import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
EXPORTS_DIR = ROOT / "exports"
LOGS_DIR = ROOT / "logs"

sys.path.insert(0, str(ROOT))
import app as dashboard_app  # noqa: E402
from scripts.generate_public_site import main as generate_public_site  # noqa: E402


class AutomationError(RuntimeError):
    pass


EXPECTED_RESULT_ACTION_TYPE = "offsite_conversion.fb_pixel_complete_registration"
DEFAULT_EXCLUDE_NAME_TERMS = (
    "QUIZ",
    "QUIZ REGISTRATION",
    "QUIZ REGISTRATIONS",
)


def parse_exclusion_terms(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_EXCLUDE_NAME_TERMS
    terms: list[str] = []
    for raw in re.split(r"[,;|\n]+", value):
        term = raw.strip()
        if term and term.casefold() not in {item.casefold() for item in terms}:
            terms.append(term)
    return tuple(terms) or DEFAULT_EXCLUDE_NAME_TERMS


def contains_excluded_term(value: Any, terms: tuple[str, ...]) -> bool:
    text = str(value or "").casefold()
    return any(term.casefold() in text for term in terms if term)


def row_is_excluded(row: dict[str, Any], terms: tuple[str, ...]) -> bool:
    return any(
        contains_excluded_term(row.get(field), terms)
        for field in (
            "campaign_name",
            "adset_name",
            "ad_name",
            "name",
        )
    )


def validate_result_action_type(value: str) -> str:
    normalized = value.strip()
    if normalized != EXPECTED_RESULT_ACTION_TYPE:
        raise AutomationError(
            "The dashboard must use only the exact Meta CompleteRegistration event. "
            f"Expected {EXPECTED_RESULT_ACTION_TYPE}, but found {normalized or '(empty)'}. "
            "Run CONFIGURAR_META.bat again and select the exact pixel complete registration action."
        )
    return normalized


def load_env_file(path: Path = ENV_PATH) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def save_env_file(values: dict[str, str], path: Path = ENV_PATH) -> None:
    ordered_keys = [
        "META_ACCESS_TOKEN",
        "META_AD_ACCOUNT_ID",
        "META_API_VERSION",
        "META_CAMPAIGN_FILTER",
        "META_EXCLUDE_NAME_TERMS",
        "META_RESULT_ACTION_TYPE",
        "META_CURRENCY_DECIMALS",
        "GITHUB_PAGES_URL",
        "AUTO_PUBLISH",
        "WAIT_FOR_GITHUB_PAGES",
    ]
    lines = [
        "# Local credentials and automation settings.",
        "# This file is ignored by Git and must never be published.",
    ]
    for key in ordered_keys:
        if key in values:
            safe_value = values[key].replace("\n", "").replace("\r", "")
            lines.append(f"{key}={safe_value}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def env_bool(values: dict[str, str], key: str, default: bool = False) -> bool:
    value = values.get(key)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "sim", "s"}


def normalize_account_id(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise AutomationError("META_AD_ACCOUNT_ID is empty.")
    return cleaned if cleaned.startswith("act_") else f"act_{cleaned}"


def parse_number(value: Any) -> float:
    if value is None or value == "":
        return 0.0
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) else 0.0


def iso_date(value: Any) -> str | None:
    if not value:
        return None
    text = str(value)
    match = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    return match.group(1) if match else None


def action_value(row: dict[str, Any], action_type: str) -> float:
    for action in row.get("actions") or []:
        if action.get("action_type") == action_type:
            return parse_number(action.get("value"))
    return 0.0


def landing_page_views(row: dict[str, Any]) -> float:
    return action_value(row, "landing_page_view")


def status_value(value: Any) -> str:
    return "active" if str(value or "").upper() == "ACTIVE" else "inactive"


def last_completed_friday_thursday(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    thursday = 3
    delta = (current.weekday() - thursday) % 7
    if delta == 0:
        delta = 7
    end = current - timedelta(days=delta)
    start = end - timedelta(days=6)
    return start, end


@dataclass
class MetaConfig:
    token: str
    account_id: str
    api_version: str
    campaign_filter: str
    exclude_name_terms: tuple[str, ...]
    result_action_type: str
    currency_decimals: int
    github_pages_url: str
    auto_publish: bool
    wait_for_pages: bool

    @classmethod
    def from_env(cls, values: dict[str, str]) -> "MetaConfig":
        token = values.get("META_ACCESS_TOKEN", "").strip()
        account = values.get("META_AD_ACCOUNT_ID", "").strip()
        result_action = values.get("META_RESULT_ACTION_TYPE", "").strip()

        missing = []
        if not token:
            missing.append("META_ACCESS_TOKEN")
        if not account:
            missing.append("META_AD_ACCOUNT_ID")
        if not result_action:
            missing.append("META_RESULT_ACTION_TYPE")
        if missing:
            raise AutomationError(
                "Missing configuration: "
                + ", ".join(missing)
                + ". Run CONFIGURAR_META.bat first."
            )

        try:
            decimals = int(values.get("META_CURRENCY_DECIMALS", "2"))
        except ValueError as exc:
            raise AutomationError("META_CURRENCY_DECIMALS must be an integer.") from exc

        result_action = validate_result_action_type(result_action)

        return cls(
            token=token,
            account_id=normalize_account_id(account),
            api_version=values.get("META_API_VERSION", "v25.0").strip() or "v25.0",
            campaign_filter=values.get("META_CAMPAIGN_FILTER", "PRESUBS").strip(),
            exclude_name_terms=parse_exclusion_terms(
                values.get("META_EXCLUDE_NAME_TERMS", ",".join(DEFAULT_EXCLUDE_NAME_TERMS))
            ),
            result_action_type=result_action,
            currency_decimals=decimals,
            github_pages_url=values.get("GITHUB_PAGES_URL", "").strip().rstrip("/"),
            auto_publish=env_bool(values, "AUTO_PUBLISH", True),
            wait_for_pages=env_bool(values, "WAIT_FOR_GITHUB_PAGES", False),
        )


class MetaClient:
    def __init__(self, config: MetaConfig):
        self.config = config
        self.base_url = f"https://graph.facebook.com/{config.api_version}"
        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "PreSubsDashboardAutomation/1.0"}
        )

    def _request(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        retries: int = 5,
    ) -> dict[str, Any]:
        request_params = dict(params or {})
        request_params.setdefault("access_token", self.config.token)

        for attempt in range(1, retries + 1):
            try:
                response = self.session.get(
                    url,
                    params=request_params,
                    timeout=90,
                )
            except requests.RequestException as exc:
                if attempt == retries:
                    raise AutomationError(
                        f"Could not connect to Meta after {retries} attempts: {exc}"
                    ) from exc
                time.sleep(min(30, 2 ** attempt))
                continue

            try:
                payload = response.json()
            except ValueError:
                payload = {"raw": response.text[:500]}

            if response.ok:
                return payload

            error = payload.get("error") if isinstance(payload, dict) else None
            code = error.get("code") if isinstance(error, dict) else None
            message = (
                error.get("message")
                if isinstance(error, dict)
                else f"HTTP {response.status_code}"
            )

            retryable = response.status_code in {429, 500, 502, 503, 504} or code in {
                1,
                2,
                4,
                17,
                32,
                613,
            }
            if retryable and attempt < retries:
                wait = min(60, 2 ** attempt)
                print(f"Meta temporarily unavailable. Retrying in {wait}s...")
                time.sleep(wait)
                continue

            raise AutomationError(
                f"Meta API error ({response.status_code}, code {code}): {message}"
            )

        raise AutomationError("Unexpected Meta API request failure.")

    def get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        return self._request(url, params=params)

    def get_all(
        self,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        payload = self.get(path, params)
        rows: list[dict[str, Any]] = list(payload.get("data") or [])
        next_url = (payload.get("paging") or {}).get("next")

        while next_url:
            payload = self._request(next_url, params={})
            rows.extend(payload.get("data") or [])
            next_url = (payload.get("paging") or {}).get("next")
        return rows

    def account_info(self) -> dict[str, Any]:
        return self.get(
            self.config.account_id,
            {"fields": "id,name,currency,timezone_name,account_status"},
        )

    def objects(self, object_type: str, fields: str) -> list[dict[str, Any]]:
        return self.get_all(
            f"{self.config.account_id}/{object_type}",
            {"fields": fields, "limit": 500},
        )

    def insights(
        self,
        *,
        level: str,
        start: str,
        end: str,
        daily: bool = False,
    ) -> list[dict[str, Any]]:
        fields = [
            "date_start",
            "date_stop",
            "campaign_id",
            "campaign_name",
            "spend",
            "reach",
            "frequency",
            "impressions",
            "inline_link_clicks",
            "cost_per_inline_link_click",
            "inline_link_click_ctr",
            "actions",
        ]
        if level in {"adset", "ad"}:
            fields.extend(["adset_id", "adset_name"])
        if level == "ad":
            fields.extend(
                [
                    "ad_id",
                    "ad_name",
                    "quality_ranking",
                    "engagement_rate_ranking",
                    "conversion_rate_ranking",
                ]
            )

        params: dict[str, Any] = {
            "level": level,
            "fields": ",".join(fields),
            "time_range": json.dumps({"since": start, "until": end}),
            "action_report_time": "conversion",
            "use_unified_attribution_setting": "true",
            "limit": 500,
        }
        if daily:
            params["time_increment"] = 1

        return self.get_all(f"{self.config.account_id}/insights", params)


def campaign_matches(
    name: str,
    campaign_filter: str,
    exclude_terms: tuple[str, ...] = (),
) -> bool:
    text = name or ""
    if campaign_filter and campaign_filter.casefold() not in text.casefold():
        return False
    return not contains_excluded_term(text, exclude_terms)


def metadata_maps(
    client: MetaClient,
    campaign_filter: str,
    exclude_terms: tuple[str, ...] = (),
) -> dict[str, Any]:
    campaign_rows = client.objects(
        "campaigns",
        "id,name,effective_status,created_time,start_time,stop_time",
    )
    campaigns = {
        str(row["id"]): row
        for row in campaign_rows
        if campaign_matches(
            str(row.get("name") or ""), campaign_filter, exclude_terms
        )
    }

    adset_rows = client.objects(
        "adsets",
        "id,name,campaign_id,effective_status,created_time,start_time,daily_budget,lifetime_budget",
    )
    adsets = {
        str(row["id"]): row
        for row in adset_rows
        if str(row.get("campaign_id") or "") in campaigns
        and not contains_excluded_term(row.get("name"), exclude_terms)
    }

    ad_rows = client.objects(
        "ads",
        "id,name,adset_id,campaign_id,effective_status,created_time",
    )
    ads = {
        str(row["id"]): row
        for row in ad_rows
        if str(row.get("campaign_id") or "") in campaigns
        and str(row.get("adset_id") or "") in adsets
        and not contains_excluded_term(row.get("name"), exclude_terms)
    }

    return {
        "campaigns": campaigns,
        "adsets": adsets,
        "ads": ads,
    }


def metric_values(row: dict[str, Any], result_action_type: str) -> dict[str, float | None]:
    spend = parse_number(row.get("spend"))
    results = action_value(row, result_action_type)
    reach = parse_number(row.get("reach"))
    frequency = parse_number(row.get("frequency"))
    impressions = parse_number(row.get("impressions"))
    clicks = parse_number(row.get("inline_link_clicks"))
    cpc = parse_number(row.get("cost_per_inline_link_click")) or (
        spend / clicks if clicks else None
    )
    ctr = parse_number(row.get("inline_link_click_ctr")) or (
        clicks * 100 / impressions if impressions else None
    )
    lpv = landing_page_views(row)

    return {
        "spend": spend,
        "results": results,
        "reach": reach,
        "frequency": frequency,
        "impressions": impressions,
        "clicks": clicks,
        "cpc": cpc,
        "ctr": ctr,
        "lpv": lpv,
        "cost_lpv": spend / lpv if lpv else None,
        "cost_result": spend / results if results else None,
    }


def weekly_base_columns(
    row: dict[str, Any],
    metrics: dict[str, Any],
    *,
    status: str,
    created: str | None,
    currency: str,
) -> dict[str, Any]:
    return {
        "Início dos relatórios": row.get("date_start"),
        "Encerramento dos relatórios": row.get("date_stop"),
        "Valor usado (EUR)": metrics["spend"],
        "Resultados": metrics["results"],
        "Alcance": metrics["reach"],
        "Frequência": metrics["frequency"],
        "Impressões": metrics["impressions"],
        "Cliques no link": metrics["clicks"],
        "CPC (custo por clique no link) (EUR)": metrics["cpc"],
        "CTR (taxa de cliques no link)": metrics["ctr"],
        "Visualizações da página de destino": metrics["lpv"],
        "Custo por visualização da página de destino (EUR)": metrics["cost_lpv"],
        "Custo por resultados": metrics["cost_result"],
        "Data de criação": created,
        "_account_currency": currency,
        "_status": status,
    }


def build_frames(
    *,
    weekly_campaigns: list[dict[str, Any]],
    weekly_adsets: list[dict[str, Any]],
    weekly_ads: list[dict[str, Any]],
    daily_ads: list[dict[str, Any]],
    metadata: dict[str, Any],
    config: MetaConfig,
    account_info: dict[str, Any],
) -> dict[str, pd.DataFrame]:
    campaign_meta = metadata["campaigns"]
    adset_meta = metadata["adsets"]
    ad_meta = metadata["ads"]
    currency = str(account_info.get("currency") or "EUR")
    divisor = 10 ** config.currency_decimals

    campaign_rows: list[dict[str, Any]] = []
    for row in weekly_campaigns:
        if (
            not campaign_matches(
                str(row.get("campaign_name") or ""),
                config.campaign_filter,
                config.exclude_name_terms,
            )
            or row_is_excluded(row, config.exclude_name_terms)
        ):
            continue
        campaign_id = str(row.get("campaign_id") or "")
        meta = campaign_meta.get(campaign_id, {})
        metrics = metric_values(row, config.result_action_type)
        base = weekly_base_columns(
            row,
            metrics,
            status=status_value(meta.get("effective_status")),
            created=iso_date(meta.get("created_time")),
            currency=currency,
        )
        base.update(
            {
                "ID da campanha": campaign_id,
                "Nome da campanha": row.get("campaign_name"),
                "Veiculação da campanha": base.pop("_status"),
            }
        )
        campaign_rows.append(base)

    adset_rows: list[dict[str, Any]] = []
    for row in weekly_adsets:
        if (
            not campaign_matches(
                str(row.get("campaign_name") or ""),
                config.campaign_filter,
                config.exclude_name_terms,
            )
            or row_is_excluded(row, config.exclude_name_terms)
        ):
            continue
        adset_id = str(row.get("adset_id") or "")
        meta = adset_meta.get(adset_id, {})
        metrics = metric_values(row, config.result_action_type)
        base = weekly_base_columns(
            row,
            metrics,
            status=status_value(meta.get("effective_status")),
            created=iso_date(meta.get("created_time")),
            currency=currency,
        )
        daily_budget = parse_number(meta.get("daily_budget"))
        base.update(
            {
                "ID da campanha": str(row.get("campaign_id") or ""),
                "Nome da campanha": row.get("campaign_name"),
                "ID do conjunto de anúncios": adset_id,
                "Nome do conjunto de anúncios": row.get("adset_name"),
                "Veiculação do conjunto de anúncios": base.pop("_status"),
                "Início": iso_date(meta.get("start_time")),
                "Orçamento do conjunto de anúncios": (
                    daily_budget / divisor if daily_budget else None
                ),
            }
        )
        adset_rows.append(base)

    ad_rows: list[dict[str, Any]] = []
    for row in weekly_ads:
        if (
            not campaign_matches(
                str(row.get("campaign_name") or ""),
                config.campaign_filter,
                config.exclude_name_terms,
            )
            or row_is_excluded(row, config.exclude_name_terms)
        ):
            continue
        ad_id = str(row.get("ad_id") or "")
        meta = ad_meta.get(ad_id, {})
        metrics = metric_values(row, config.result_action_type)
        base = weekly_base_columns(
            row,
            metrics,
            status=status_value(meta.get("effective_status")),
            created=iso_date(meta.get("created_time")),
            currency=currency,
        )
        base.update(
            {
                "ID da campanha": str(row.get("campaign_id") or ""),
                "Nome da campanha": row.get("campaign_name"),
                "ID do conjunto de anúncios": str(row.get("adset_id") or ""),
                "Nome do conjunto de anúncios": row.get("adset_name"),
                "ID do anúncio": ad_id,
                "Nome do anúncio": row.get("ad_name"),
                "Veiculação de anúncio": base.pop("_status"),
                "Classificação de qualidade": row.get("quality_ranking"),
                "Classificação da taxa de engajamento": row.get(
                    "engagement_rate_ranking"
                ),
                "Classificação da taxa de conversão": row.get(
                    "conversion_rate_ranking"
                ),
            }
        )
        ad_rows.append(base)

    daily_rows: list[dict[str, Any]] = []
    for row in daily_ads:
        if (
            not campaign_matches(
                str(row.get("campaign_name") or ""),
                config.campaign_filter,
                config.exclude_name_terms,
            )
            or row_is_excluded(row, config.exclude_name_terms)
        ):
            continue
        ad_id = str(row.get("ad_id") or "")
        meta = ad_meta.get(ad_id, {})
        metrics = metric_values(row, config.result_action_type)
        daily_rows.append(
            {
                "Dia": row.get("date_start"),
                "Início dos relatórios": row.get("date_start"),
                "Encerramento dos relatórios": row.get("date_start"),
                "ID da campanha": str(row.get("campaign_id") or ""),
                "Nome da campanha": row.get("campaign_name"),
                "ID do conjunto de anúncios": str(row.get("adset_id") or ""),
                "Nome do conjunto de anúncios": row.get("adset_name"),
                "ID do anúncio": ad_id,
                "Nome do anúncio": row.get("ad_name"),
                "Veiculação de anúncio": status_value(
                    meta.get("effective_status")
                ),
                "Valor usado (EUR)": metrics["spend"],
                "Resultados": metrics["results"],
                "Alcance": metrics["reach"],
                "Frequência": metrics["frequency"],
                "Impressões": metrics["impressions"],
                "Cliques no link": metrics["clicks"],
                "CPC (custo por clique no link) (EUR)": metrics["cpc"],
                "CTR (taxa de cliques no link)": metrics["ctr"],
                "Visualizações da página de destino": metrics["lpv"],
                "Custo por visualização da página de destino (EUR)": metrics[
                    "cost_lpv"
                ],
                "Custo por resultados": metrics["cost_result"],
                "_account_currency": currency,
            }
        )

    frames = {
        "campaigns": pd.DataFrame(campaign_rows),
        "adsets": pd.DataFrame(adset_rows),
        "ads": pd.DataFrame(ad_rows),
        "daily_ads": pd.DataFrame(daily_rows),
    }

    for frame in frames.values():
        if "_account_currency" in frame.columns:
            frame.drop(columns=["_account_currency"], inplace=True)

    return frames


def frame_totals(frame: pd.DataFrame) -> dict[str, float]:
    def total(column: str) -> float:
        if column not in frame.columns:
            return 0.0
        return float(pd.to_numeric(frame[column], errors="coerce").fillna(0).sum())

    return {
        "spend": total("Valor usado (EUR)"),
        "results": total("Resultados"),
        "impressions": total("Impressões"),
        "clicks": total("Cliques no link"),
        "lpv": total("Visualizações da página de destino"),
    }


def qa_report(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    totals = {name: frame_totals(frame) for name, frame in frames.items()}
    comparisons = []

    pairs = [
        ("campaigns", "adsets"),
        ("campaigns", "ads"),
        ("ads", "daily_ads"),
    ]
    tolerances = {
        "spend": 0.10,
        "results": 0.01,
        "impressions": 1.0,
        "clicks": 1.0,
        "lpv": 1.0,
    }

    for left, right in pairs:
        for metric, tolerance in tolerances.items():
            difference = abs(totals[left][metric] - totals[right][metric])
            comparisons.append(
                {
                    "left": left,
                    "right": right,
                    "metric": metric,
                    "left_value": totals[left][metric],
                    "right_value": totals[right][metric],
                    "difference": difference,
                    "ok": difference <= tolerance,
                }
            )

    return {
        "totals": totals,
        "comparisons": comparisons,
        "warnings": [item for item in comparisons if not item["ok"]],
    }


def save_exports(
    *,
    start: str,
    end: str,
    frames: dict[str, pd.DataFrame],
    raw_payload: dict[str, Any],
    qa: dict[str, Any],
) -> Path:
    folder = EXPORTS_DIR / f"{start}__{end}"
    folder.mkdir(parents=True, exist_ok=True)

    for name, frame in frames.items():
        frame.to_csv(
            folder / f"{name}.csv",
            index=False,
            encoding="utf-8-sig",
            quoting=csv.QUOTE_MINIMAL,
        )

    (folder / "raw_meta.json").write_text(
        json.dumps(raw_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (folder / "qa_report.json").write_text(
        json.dumps(qa, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return folder


def import_into_database(
    *,
    start: str,
    end: str,
    frames: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    dashboard_app.init_db()

    with dashboard_app.db() as con:
        preview_rows = con.execute(
            """
            SELECT entity_key, preview_url
            FROM ad_metrics
            WHERE preview_url IS NOT NULL AND preview_url <> ''
            ORDER BY week_id DESC, id DESC
            """
        ).fetchall()
        preview_map: dict[str, str] = {}
        for row in preview_rows:
            preview_map.setdefault(str(row["entity_key"]), str(row["preview_url"]))

        week_id = dashboard_app.get_or_create_week(con, start, end)

        for table in (
            "daily_ad_metrics",
            "campaign_metrics",
            "adset_metrics",
            "ad_metrics",
        ):
            con.execute(f"DELETE FROM {table} WHERE week_id=?", (week_id,))

        counts = {
            "campaigns": dashboard_app.import_campaigns(
                con, week_id, frames["campaigns"]
            ),
            "adsets": dashboard_app.import_adsets(
                con, week_id, frames["adsets"]
            ),
            "ads": dashboard_app.import_ads(con, week_id, frames["ads"]),
            "daily_ads": dashboard_app.import_daily_ads(
                con, week_id, frames["daily_ads"]
            ),
        }

        for entity_key, preview_url in preview_map.items():
            con.execute(
                """
                UPDATE ad_metrics
                SET preview_url=?
                WHERE week_id=? AND entity_key=?
                """,
                (preview_url, week_id, entity_key),
            )

        dashboard_app.backfill_relations(con, week_id)

    return {"week_id": week_id, "counts": counts}


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise AutomationError(f"Git command failed: git {' '.join(args)}\n{detail}")
    return result


def publish_to_github(start: str, end: str) -> dict[str, Any]:
    if not (ROOT / ".git").exists():
        raise AutomationError(
            "This folder is not connected to GitHub. "
            "Run MIGRAR_DO_V8.bat or add this folder in GitHub Desktop."
        )

    run_git(["add", "docs"])
    diff = run_git(["diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        return {"changed": False, "pushed": False, "message": "No public changes."}

    message = f"Automated Meta update {start} to {end}"
    run_git(["commit", "-m", message])
    push = run_git(["push"], check=False)
    if push.returncode != 0:
        detail = push.stderr.strip() or push.stdout.strip()
        raise AutomationError(
            "The site was generated and committed, but Git push failed. "
            f"Open GitHub Desktop and click Push origin.\n{detail}"
        )

    return {"changed": True, "pushed": True, "message": message}


def verify_github_pages(base_url: str, generated_at: str, timeout: int = 600) -> bool:
    if not base_url:
        return False

    deadline = time.time() + timeout
    url = f"{base_url}/export-summary.json"
    print("Waiting for GitHub Pages to publish the new version...")

    while time.time() < deadline:
        try:
            response = requests.get(
                url,
                params={"t": int(time.time())},
                timeout=20,
                headers={"Cache-Control": "no-cache"},
            )
            if response.ok:
                payload = response.json()
                if payload.get("generated_at") == generated_at:
                    print("GitHub Pages update verified.")
                    return True
        except (requests.RequestException, ValueError):
            pass
        time.sleep(15)

    print(
        "GitHub Pages did not confirm the new version within 10 minutes. "
        "The push succeeded; check the Actions tab."
    )
    return False


def configure() -> int:
    print("")
    print("PreSubs Meta API setup")
    print("----------------------")
    print("The token stays only in this computer and is ignored by Git.")
    print("")

    account = input("Meta Ad Account ID (with or without act_): ").strip()
    token = getpass.getpass("Meta access token with ads_read: ").strip()
    api_version = input("Graph API version [v25.0]: ").strip() or "v25.0"

    temporary = MetaConfig(
        token=token,
        account_id=normalize_account_id(account),
        api_version=api_version,
        campaign_filter="",
        exclude_name_terms=DEFAULT_EXCLUDE_NAME_TERMS,
        result_action_type=EXPECTED_RESULT_ACTION_TYPE,
        currency_decimals=2,
        github_pages_url="",
        auto_publish=True,
        wait_for_pages=False,
    )
    client = MetaClient(temporary)
    info = client.account_info()

    print("")
    print(
        f"Account found: {info.get('name')} | "
        f"Currency: {info.get('currency')} | "
        f"Timezone: {info.get('timezone_name')}"
    )

    campaign_filter = input("Campaign name filter [PRESUBS]: ").strip() or "PRESUBS"

    sample_end = date.today() - timedelta(days=1)
    sample_start = sample_end - timedelta(days=29)
    sample = client.insights(
        level="ad",
        start=sample_start.isoformat(),
        end=sample_end.isoformat(),
        daily=False,
    )

    action_totals: dict[str, float] = {}
    for row in sample:
        if not campaign_matches(
            str(row.get("campaign_name") or ""),
            campaign_filter,
            DEFAULT_EXCLUDE_NAME_TERMS,
        ):
            continue
        for action in row.get("actions") or []:
            action_type = str(action.get("action_type") or "")
            action_totals[action_type] = action_totals.get(action_type, 0.0) + parse_number(
                action.get("value")
            )

    candidates = [
        (name, value)
        for name, value in sorted(
            action_totals.items(),
            key=lambda item: item[1],
            reverse=True,
        )
        if "registration" in name.lower() or "lead" in name.lower()
    ]

    print("")
    exact_candidate = next(
        (item for item in candidates if item[0] == EXPECTED_RESULT_ACTION_TYPE),
        None,
    )
    if exact_candidate:
        result_action = EXPECTED_RESULT_ACTION_TYPE
        print(
            "Exact CompleteRegistration action detected and selected: "
            f"{result_action} = {exact_candidate[1]:g}"
        )
    else:
        print(
            "The exact CompleteRegistration pixel action was not detected in the "
            "last 30 days. Quiz registrations and Lead events cannot be used."
        )
        raise AutomationError(
            f"Required action not found: {EXPECTED_RESULT_ACTION_TYPE}"
        )

    pages_url = input(
        "GitHub Pages URL "
        "[https://lucasroarts-rgb.github.io/presubs_dashboard_github_pages_v8/]: "
    ).strip() or (
        "https://lucasroarts-rgb.github.io/"
        "presubs_dashboard_github_pages_v8/"
    )

    publish = input("Publish automatically after each sync? [Y/n]: ").strip().lower()
    wait = input(
        "Wait and verify GitHub Pages after push? [y/N]: "
    ).strip().lower()

    values = {
        "META_ACCESS_TOKEN": token,
        "META_AD_ACCOUNT_ID": normalize_account_id(account),
        "META_API_VERSION": api_version,
        "META_CAMPAIGN_FILTER": campaign_filter,
        "META_EXCLUDE_NAME_TERMS": ",".join(DEFAULT_EXCLUDE_NAME_TERMS),
        "META_RESULT_ACTION_TYPE": result_action,
        "META_CURRENCY_DECIMALS": "2",
        "GITHUB_PAGES_URL": pages_url,
        "AUTO_PUBLISH": "false" if publish in {"n", "no", "nao", "não"} else "true",
        "WAIT_FOR_GITHUB_PAGES": "true" if wait in {"y", "yes", "s", "sim"} else "false",
    }
    save_env_file(values)

    print("")
    print("Configuration saved successfully in .env.")
    print(f"Registration action: {result_action}")
    print("Run AUTOMATIZAR_SEMANA.bat.")
    return 0


def sync(
    *,
    start: str,
    end: str,
    publish: bool,
    wait_for_pages: bool,
) -> dict[str, Any]:
    values = load_env_file()
    config = MetaConfig.from_env(values)
    client = MetaClient(config)

    print("")
    print("PreSubs Meta automation")
    print("-----------------------")
    print(f"Period: {start} to {end}")
    print(f"Account: {config.account_id}")
    print(f"Campaign filter: contains {config.campaign_filter or '(all campaigns)'}")
    print(
        "Excluded name terms: "
        + ", ".join(config.exclude_name_terms)
    )
    print(f"Registration action: {config.result_action_type} (exact only)")
    print("")

    account_info = client.account_info()
    print(
        f"Connected to {account_info.get('name')} "
        f"({account_info.get('currency')}, {account_info.get('timezone_name')})"
    )

    print("Downloading campaign, ad-set and ad metadata...")
    metadata = metadata_maps(
        client, config.campaign_filter, config.exclude_name_terms
    )

    print("Downloading weekly campaign insights...")
    weekly_campaigns = client.insights(
        level="campaign", start=start, end=end
    )
    print("Downloading weekly ad-set insights...")
    weekly_adsets = client.insights(
        level="adset", start=start, end=end
    )
    print("Downloading weekly ad insights...")
    weekly_ads = client.insights(
        level="ad", start=start, end=end
    )
    print("Downloading daily ad insights...")
    daily_ads = client.insights(
        level="ad", start=start, end=end, daily=True
    )

    raw_payload = {
        "account": account_info,
        "scope": {
            "campaign_name_contains": config.campaign_filter,
            "excluded_name_terms": list(config.exclude_name_terms),
            "result_action_type": config.result_action_type,
        },
        "campaigns": weekly_campaigns,
        "adsets": weekly_adsets,
        "ads": weekly_ads,
        "daily_ads": daily_ads,
    }

    frames = build_frames(
        weekly_campaigns=weekly_campaigns,
        weekly_adsets=weekly_adsets,
        weekly_ads=weekly_ads,
        daily_ads=daily_ads,
        metadata=metadata,
        config=config,
        account_info=account_info,
    )

    if any(frame.empty for frame in frames.values()):
        empty_names = [name for name, frame in frames.items() if frame.empty]
        raise AutomationError(
            "Meta returned no matching data for: "
            + ", ".join(empty_names)
            + ". Check the period, campaign filter and token access."
        )

    qa = qa_report(frames)
    export_folder = save_exports(
        start=start,
        end=end,
        frames=frames,
        raw_payload=raw_payload,
        qa=qa,
    )

    print("")
    print("Downloaded rows:")
    for name, frame in frames.items():
        print(f"  {name}: {len(frame)}")

    if qa["warnings"]:
        print("")
        print("QA warnings:")
        for warning in qa["warnings"]:
            print(
                "  "
                f"{warning['left']} vs {warning['right']} | "
                f"{warning['metric']} | "
                f"difference {warning['difference']:.4f}"
            )
        print("The sync will continue, and the QA report was saved for review.")
    else:
        print("QA: campaign, ad-set, ad and daily totals are aligned.")

    imported = import_into_database(start=start, end=end, frames=frames)
    print("")
    print(f"Database updated. Week ID: {imported['week_id']}")
    print(f"Local audit exports: {export_folder}")

    print("Generating the public GitHub Pages files...")
    result = generate_public_site()
    if result != 0:
        raise AutomationError("The public site generator failed.")

    summary_path = ROOT / "docs" / "export-summary.json"
    generated_at = ""
    if summary_path.exists():
        generated_at = json.loads(
            summary_path.read_text(encoding="utf-8")
        ).get("generated_at", "")

    git_result = {"changed": False, "pushed": False}
    if publish:
        print("Publishing to GitHub...")
        git_result = publish_to_github(start, end)
        print(git_result["message"])
        if git_result.get("pushed") and wait_for_pages and generated_at:
            verify_github_pages(config.github_pages_url, generated_at)
    else:
        print("Automatic GitHub publication was skipped.")

    return {
        "period": {"start": start, "end": end},
        "imported": imported,
        "qa": qa,
        "export_folder": str(export_folder),
        "git": git_result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download Meta Ads data, update SQLite and publish GitHub Pages."
    )
    parser.add_argument("--configure", action="store_true")
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    publish_group = parser.add_mutually_exclusive_group()
    publish_group.add_argument("--publish", action="store_true")
    publish_group.add_argument("--no-publish", action="store_true")
    parser.add_argument("--wait-pages", action="store_true")
    args = parser.parse_args()

    try:
        if args.configure:
            return configure()

        values = load_env_file()
        config = MetaConfig.from_env(values)

        if args.start or args.end:
            if not args.start or not args.end:
                raise AutomationError("--start and --end must be used together.")
            start_date = date.fromisoformat(args.start)
            end_date = date.fromisoformat(args.end)
        else:
            start_date, end_date = last_completed_friday_thursday()

        if end_date < start_date:
            raise AutomationError("The end date cannot be before the start date.")

        publish = (
            True
            if args.publish
            else False
            if args.no_publish
            else config.auto_publish
        )
        wait_for_pages = args.wait_pages or config.wait_for_pages

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        started = datetime.now(timezone.utc)
        result = sync(
            start=start_date.isoformat(),
            end=end_date.isoformat(),
            publish=publish,
            wait_for_pages=wait_for_pages,
        )
        finished = datetime.now(timezone.utc)

        log_payload = {
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat(),
            "result": result,
        }
        log_name = (
            f"automation_{start_date.isoformat()}__{end_date.isoformat()}_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        )
        (LOGS_DIR / log_name).write_text(
            json.dumps(log_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        print("")
        print("Automation completed successfully.")
        print(f"Period: {start_date} to {end_date}")
        if publish:
            print("The GitHub push was completed or no public changes were needed.")
        return 0

    except (AutomationError, ValueError) as exc:
        print("")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
