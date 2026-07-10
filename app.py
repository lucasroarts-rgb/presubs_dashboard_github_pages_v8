from __future__ import annotations

import base64
import hmac
import io
import math
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import pandas as pd
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("DB_PATH", str(BASE_DIR / "data" / "presubs.db")))
STATIC_DIR = BASE_DIR / "static"
CREDENTIALS_PATH = BASE_DIR / "data" / "admin_credentials.txt"


def read_local_credentials() -> dict[str, str]:
    values: dict[str, str] = {}
    if not CREDENTIALS_PATH.exists():
        return values
    for line in CREDENTIALS_PATH.read_text(encoding="utf-8").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


_local_credentials = read_local_credentials()
ADMIN_USER = os.getenv("ADMIN_USER") or _local_credentials.get("ADMIN_USER") or "lucas"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or _local_credentials.get("ADMIN_PASSWORD") or ""


def has_valid_admin_credentials(request: Request) -> bool:
    if not ADMIN_PASSWORD:
        return False

    authorization = request.headers.get("Authorization", "")
    if not authorization.lower().startswith("basic "):
        return False

    try:
        encoded = authorization.split(" ", 1)[1].strip()
        decoded = base64.b64decode(encoded).decode("utf-8")
        username, password = decoded.split(":", 1)
    except Exception:
        return False

    return hmac.compare_digest(username, ADMIN_USER) and hmac.compare_digest(
        password, ADMIN_PASSWORD
    )


app = FastAPI(title="PreSubs Weekly Dashboard")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def protect_admin_and_writes(request: Request, call_next):
    path = request.url.path
    protects_admin_page = path == "/admin"
    protects_write_api = path.startswith("/api/") and request.method.upper() not in {
        "GET",
        "HEAD",
        "OPTIONS",
    }

    if protects_admin_page or protects_write_api:
        if not ADMIN_PASSWORD:
            return JSONResponse(
                {
                    "detail": (
                        "The admin password is not configured. "
                        "Start the project with START_PUBLIC_DASHBOARD.bat."
                    )
                },
                status_code=503,
            )

        if not has_valid_admin_credentials(request):
            return Response(
                status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="PreSubs Admin"'},
            )

    return await call_next(request)


@app.middleware("http")
async def disable_browser_cache(request, call_next):
    """Avoid stale HTML/JS while the dashboard is being iterated."""
    response = await call_next(request)
    if (
        request.url.path in {"/", "/admin"}
        or request.url.path.startswith("/static/")
        or request.url.path.startswith("/api/")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@contextmanager
def db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def init_db() -> None:
    schema = """
    CREATE TABLE IF NOT EXISTS weeks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_start TEXT NOT NULL,
        week_end TEXT NOT NULL,
        label TEXT NOT NULL,
        imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(week_start, week_end)
    );

    CREATE TABLE IF NOT EXISTS campaign_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_id INTEGER NOT NULL REFERENCES weeks(id) ON DELETE CASCADE,
        entity_key TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        status TEXT,
        created_date TEXT,
        spend REAL NOT NULL DEFAULT 0,
        results REAL NOT NULL DEFAULT 0,
        reach REAL NOT NULL DEFAULT 0,
        frequency REAL NOT NULL DEFAULT 0,
        impressions REAL NOT NULL DEFAULT 0,
        link_clicks REAL NOT NULL DEFAULT 0,
        cpc REAL,
        ctr REAL,
        landing_page_views REAL NOT NULL DEFAULT 0,
        cost_per_lpv REAL,
        cost_per_result REAL,
        UNIQUE(week_id, entity_key)
    );

    CREATE TABLE IF NOT EXISTS adset_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_id INTEGER NOT NULL REFERENCES weeks(id) ON DELETE CASCADE,
        entity_key TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        campaign_key TEXT,
        campaign_name TEXT,
        status TEXT,
        created_date TEXT,
        start_date TEXT,
        daily_budget REAL,
        spend REAL NOT NULL DEFAULT 0,
        results REAL NOT NULL DEFAULT 0,
        reach REAL NOT NULL DEFAULT 0,
        frequency REAL NOT NULL DEFAULT 0,
        impressions REAL NOT NULL DEFAULT 0,
        link_clicks REAL NOT NULL DEFAULT 0,
        cpc REAL,
        ctr REAL,
        landing_page_views REAL NOT NULL DEFAULT 0,
        cost_per_lpv REAL,
        cost_per_result REAL,
        UNIQUE(week_id, entity_key)
    );

    CREATE TABLE IF NOT EXISTS ad_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_id INTEGER NOT NULL REFERENCES weeks(id) ON DELETE CASCADE,
        entity_key TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        campaign_key TEXT,
        campaign_name TEXT,
        adset_key TEXT,
        adset_name TEXT,
        status TEXT,
        created_date TEXT,
        spend REAL NOT NULL DEFAULT 0,
        results REAL NOT NULL DEFAULT 0,
        reach REAL NOT NULL DEFAULT 0,
        frequency REAL NOT NULL DEFAULT 0,
        impressions REAL NOT NULL DEFAULT 0,
        link_clicks REAL NOT NULL DEFAULT 0,
        cpc REAL,
        ctr REAL,
        landing_page_views REAL NOT NULL DEFAULT 0,
        cost_per_lpv REAL,
        cost_per_result REAL,
        quality_ranking TEXT,
        engagement_ranking TEXT,
        conversion_ranking TEXT,
        preview_url TEXT,
        UNIQUE(week_id, entity_key)
    );

    CREATE TABLE IF NOT EXISTS daily_ad_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_id INTEGER NOT NULL REFERENCES weeks(id) ON DELETE CASCADE,
        report_date TEXT NOT NULL,
        entity_key TEXT NOT NULL,
        entity_name TEXT NOT NULL,
        campaign_key TEXT,
        campaign_name TEXT,
        adset_key TEXT,
        adset_name TEXT,
        status TEXT,
        spend REAL NOT NULL DEFAULT 0,
        results REAL NOT NULL DEFAULT 0,
        reach REAL NOT NULL DEFAULT 0,
        frequency REAL NOT NULL DEFAULT 0,
        impressions REAL NOT NULL DEFAULT 0,
        link_clicks REAL NOT NULL DEFAULT 0,
        cpc REAL,
        ctr REAL,
        landing_page_views REAL NOT NULL DEFAULT 0,
        cost_per_lpv REAL,
        cost_per_result REAL,
        UNIQUE(week_id, report_date, entity_key)
    );

    CREATE INDEX IF NOT EXISTS idx_daily_ad_metrics_week_date
    ON daily_ad_metrics (week_id, report_date);

    CREATE TABLE IF NOT EXISTS landing_pages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        page_name TEXT NOT NULL,
        variant_name TEXT NOT NULL DEFAULT 'Default',
        page_url TEXT,
        start_date TEXT,
        status TEXT NOT NULL DEFAULT 'active',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(page_name, variant_name)
    );

    CREATE TABLE IF NOT EXISTS landing_page_metrics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_id INTEGER NOT NULL REFERENCES weeks(id) ON DELETE CASCADE,
        landing_page_id INTEGER NOT NULL REFERENCES landing_pages(id) ON DELETE CASCADE,
        sessions REAL NOT NULL DEFAULT 0,
        page_views REAL NOT NULL DEFAULT 0,
        leads REAL NOT NULL DEFAULT 0,
        spend REAL NOT NULL DEFAULT 0,
        UNIQUE(week_id, landing_page_id)
    );
    """
    with db() as con:
        con.executescript(schema)
        columns = {
            row["name"] for row in con.execute("PRAGMA table_info(landing_pages)").fetchall()
        }
        if "start_date" not in columns:
            con.execute("ALTER TABLE landing_pages ADD COLUMN start_date TEXT")
        if "page_code" not in columns:
            con.execute("ALTER TABLE landing_pages ADD COLUMN page_code TEXT")



def normalize_relation_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


def campaign_kind(value: Any) -> str | None:
    text = normalize_relation_text(value)
    if re.search(r"\b(hot|rmkt|remarket|remarketing)\b", text):
        return "hot"
    if re.search(r"\b(cold|lal|lookalike|advantage)\b", text):
        return "cold"
    return None


def infer_campaign_for_adset(
    adset: dict[str, Any],
    campaigns: list[dict[str, Any]],
    historical_relation: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Resolve the campaign even when Meta omits Campaign name in the ad-set export."""
    if not campaigns:
        return None

    explicit_key = normalize_relation_text(adset.get("campaign_key"))
    explicit_name = normalize_relation_text(adset.get("campaign_name"))
    if explicit_key or explicit_name:
        for campaign in campaigns:
            if (
                explicit_key
                and normalize_relation_text(campaign.get("entity_key")) == explicit_key
            ) or (
                explicit_name
                and normalize_relation_text(campaign.get("entity_name")) == explicit_name
            ):
                return campaign

    if historical_relation:
        historical_key = normalize_relation_text(historical_relation.get("campaign_key"))
        historical_name = normalize_relation_text(historical_relation.get("campaign_name"))
        for campaign in campaigns:
            if (
                historical_key
                and normalize_relation_text(campaign.get("entity_key")) == historical_key
            ) or (
                historical_name
                and normalize_relation_text(campaign.get("entity_name")) == historical_name
            ):
                return campaign

    adset_kind = campaign_kind(adset.get("entity_name"))
    same_kind = [
        campaign
        for campaign in campaigns
        if campaign_kind(campaign.get("entity_name")) == adset_kind
    ]
    if adset_kind and len(same_kind) == 1:
        return same_kind[0]

    # A remarketing ad set commonly carries the whole remarketing campaign spend.
    spend = float(adset.get("spend") or 0)
    close_spend = [
        campaign
        for campaign in campaigns
        if abs(float(campaign.get("spend") or 0) - spend) <= 0.05
    ]
    if len(close_spend) == 1:
        return close_spend[0]

    if len(campaigns) == 1:
        return campaigns[0]

    # In the current PreSubs structure all non-HOT/LAL sets belong to the only
    # remaining campaign kind. This remains deterministic for two-campaign weeks.
    kind_map: dict[str, list[dict[str, Any]]] = {}
    for campaign in campaigns:
        kind = campaign_kind(campaign.get("entity_name"))
        if kind:
            kind_map.setdefault(kind, []).append(campaign)
    if adset_kind in kind_map and len(kind_map[adset_kind]) == 1:
        return kind_map[adset_kind][0]

    return None


def backfill_relations(
    con: sqlite3.Connection,
    week_id: int | None = None,
) -> None:
    """Persist Campaign → Ad set → Ad relations so the UI never shows export warnings."""
    if week_id is None:
        week_rows = con.execute("SELECT id FROM weeks").fetchall()
        week_ids = [int(row["id"]) for row in week_rows]
    else:
        week_ids = [int(week_id)]

    for current_week_id in week_ids:
        campaigns = [
            dict(row)
            for row in con.execute(
                "SELECT * FROM campaign_metrics WHERE week_id=? ORDER BY spend DESC",
                (current_week_id,),
            ).fetchall()
        ]
        adsets = [
            dict(row)
            for row in con.execute(
                "SELECT * FROM adset_metrics WHERE week_id=? ORDER BY spend DESC",
                (current_week_id,),
            ).fetchall()
        ]

        for adset in adsets:
            historical = con.execute(
                """
                SELECT campaign_key, campaign_name
                FROM adset_metrics
                WHERE entity_key=?
                  AND (campaign_key IS NOT NULL OR campaign_name IS NOT NULL)
                  AND id<>?
                ORDER BY week_id DESC, id DESC
                LIMIT 1
                """,
                (adset["entity_key"], adset["id"]),
            ).fetchone()
            chosen = infer_campaign_for_adset(
                adset,
                campaigns,
                dict(historical) if historical else None,
            )
            if not chosen:
                continue
            con.execute(
                """
                UPDATE adset_metrics
                SET campaign_key=?, campaign_name=?
                WHERE id=?
                """,
                (chosen["entity_key"], chosen["entity_name"], adset["id"]),
            )

        refreshed_adsets = [
            dict(row)
            for row in con.execute(
                "SELECT * FROM adset_metrics WHERE week_id=?",
                (current_week_id,),
            ).fetchall()
        ]
        adsets_by_name = {
            normalize_relation_text(row["entity_name"]): row
            for row in refreshed_adsets
        }
        adsets_by_key = {
            normalize_relation_text(row["entity_key"]): row
            for row in refreshed_adsets
        }

        ads = con.execute(
            "SELECT * FROM ad_metrics WHERE week_id=?",
            (current_week_id,),
        ).fetchall()
        for ad_row in ads:
            ad = dict(ad_row)
            related = None
            if ad.get("adset_key"):
                related = adsets_by_key.get(normalize_relation_text(ad["adset_key"]))
            if related is None and ad.get("adset_name"):
                related = adsets_by_name.get(normalize_relation_text(ad["adset_name"]))
            if related is None:
                continue
            con.execute(
                """
                UPDATE ad_metrics
                SET adset_key=?,
                    adset_name=?,
                    campaign_key=?,
                    campaign_name=?
                WHERE id=?
                """,
                (
                    related["entity_key"],
                    related["entity_name"],
                    related.get("campaign_key"),
                    related.get("campaign_name"),
                    ad["id"],
                ),
            )

        daily_ads = con.execute(
            "SELECT * FROM daily_ad_metrics WHERE week_id=?",
            (current_week_id,),
        ).fetchall()
        for daily_row in daily_ads:
            daily_ad = dict(daily_row)
            related = None
            if daily_ad.get("adset_key"):
                related = adsets_by_key.get(
                    normalize_relation_text(daily_ad["adset_key"])
                )
            if related is None and daily_ad.get("adset_name"):
                related = adsets_by_name.get(
                    normalize_relation_text(daily_ad["adset_name"])
                )
            if related is None:
                continue
            con.execute(
                """
                UPDATE daily_ad_metrics
                SET adset_key=?,
                    adset_name=?,
                    campaign_key=?,
                    campaign_name=?
                WHERE id=?
                """,
                (
                    related["entity_key"],
                    related["entity_name"],
                    related.get("campaign_key"),
                    related.get("campaign_name"),
                    daily_ad["id"],
                ),
            )


@app.on_event("startup")
def startup() -> None:
    init_db()
    with db() as con:
        backfill_relations(con)


@app.get("/api/health")
def health():
    with db() as con:
        con.execute("SELECT 1").fetchone()
    return {
        "status": "ok",
        "database": "sqlite",
        "admin_protected": bool(ADMIN_PASSWORD),
    }


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/admin")
def admin():
    return FileResponse(STATIC_DIR / "admin.html")


def clean_number(value: Any) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0.0
    if isinstance(value, str):
        value = value.strip().replace("\u00a0", "")
        if not value or value in {"—", "-", "nan"}:
            return 0.0
        value = value.replace(".", "").replace(",", ".") if "," in value else value
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def clean_text(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    text = str(value).strip()
    return text if text and text not in {"—", "nan"} else None


def clean_date(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return clean_text(value)


def col(row: pd.Series, *names: str) -> Any:
    for name in names:
        if name in row.index:
            return row[name]
    return None


def read_excel(upload: UploadFile) -> pd.DataFrame:
    content = upload.file.read()
    if not content:
        raise HTTPException(400, f"{upload.filename}: empty file")
    try:
        frame = pd.read_excel(io.BytesIO(content))
    except Exception as exc:
        raise HTTPException(400, f"Could not read {upload.filename}: {exc}") from exc
    frame = frame.dropna(how="all")
    return frame


def entity_key(row: pd.Series, id_names: tuple[str, ...], name: str) -> str:
    raw_id = col(row, *id_names)
    if clean_text(raw_id):
        return str(raw_id).strip()
    return name.lower().strip()


METRIC_FIELDS = {
    "status": ("Veiculação da campanha", "Veiculação do conjunto de anúncios", "Veiculação de anúncio", "Delivery"),
    "created_date": ("Data de criação", "Created"),
    "spend": ("Valor usado (EUR)", "Amount spent (EUR)", "Amount spent"),
    "results": ("Resultados", "Results"),
    "reach": ("Alcance", "Reach"),
    "frequency": ("Frequência", "Frequency"),
    "impressions": ("Impressões", "Impressions"),
    "link_clicks": ("Cliques no link", "Link clicks"),
    "cpc": ("CPC (custo por clique no link) (EUR)", "CPC (cost per link click)", "CPC"),
    "ctr": ("CTR (taxa de cliques no link)", "CTR (link click-through rate)", "CTR"),
    "landing_page_views": ("Visualizações da página de destino", "Landing page views"),
    "cost_per_lpv": ("Custo por visualização da página de destino (EUR)", "Cost per landing page view"),
    "cost_per_result": ("Custo por resultados", "Cost per results"),
}


def common_metrics(row: pd.Series) -> dict[str, Any]:
    spend = clean_number(col(row, *METRIC_FIELDS["spend"]))
    results = clean_number(col(row, *METRIC_FIELDS["results"]))
    reach = clean_number(col(row, *METRIC_FIELDS["reach"]))
    impressions = clean_number(col(row, *METRIC_FIELDS["impressions"]))
    cpc = clean_number(col(row, *METRIC_FIELDS["cpc"])) or None
    link_clicks = clean_number(col(row, *METRIC_FIELDS["link_clicks"]))
    frequency = clean_number(col(row, *METRIC_FIELDS["frequency"]))

    # Some Meta export presets omit link clicks and frequency while keeping
    # CPC, impressions and reach. Reconstruct those metrics when possible.
    if not link_clicks and spend > 0 and cpc:
        link_clicks = round(spend / cpc)
    if not frequency and impressions > 0 and reach > 0:
        frequency = impressions / reach

    lpv_provided = any(name in row.index for name in METRIC_FIELDS["landing_page_views"])
    cost_lpv_provided = any(name in row.index for name in METRIC_FIELDS["cost_per_lpv"])

    return {
        "status": clean_text(col(row, *METRIC_FIELDS["status"])),
        "created_date": clean_date(col(row, *METRIC_FIELDS["created_date"])),
        "spend": spend,
        "results": results,
        "reach": reach,
        "frequency": frequency,
        "impressions": impressions,
        "link_clicks": link_clicks,
        "cpc": cpc or (spend / link_clicks if spend > 0 and link_clicks > 0 else None),
        "ctr": clean_number(col(row, *METRIC_FIELDS["ctr"])) or (
            link_clicks * 100.0 / impressions if impressions > 0 and link_clicks > 0 else None
        ),
        "landing_page_views": (
            clean_number(col(row, *METRIC_FIELDS["landing_page_views"]))
            if lpv_provided
            else 0.0
        ),
        "cost_per_lpv": (
            clean_number(col(row, *METRIC_FIELDS["cost_per_lpv"])) or None
            if cost_lpv_provided
            else None
        ),
        "lpv_provided": 1 if lpv_provided else 0,
        "cost_lpv_provided": 1 if cost_lpv_provided else 0,
        "cost_per_result": clean_number(col(row, *METRIC_FIELDS["cost_per_result"])) or (
            spend / results if spend > 0 and results > 0 else None
        ),
    }


def infer_report_date(frame: pd.DataFrame, *column_names: str) -> str | None:
    for column_name in column_names:
        if column_name not in frame.columns:
            continue
        values = frame[column_name].dropna()
        if values.empty:
            continue
        value = clean_date(values.iloc[0])
        if value:
            return value
    return None


def reporting_date_pairs(frame: pd.DataFrame) -> list[tuple[str, str]]:
    start_column = next(
        (
            name
            for name in ("Início dos relatórios", "Reporting starts", "Dia", "Day")
            if name in frame.columns
        ),
        None,
    )
    end_column = next(
        (
            name
            for name in ("Encerramento dos relatórios", "Reporting ends")
            if name in frame.columns
        ),
        None,
    )
    if not start_column:
        return []

    pairs: list[tuple[str, str]] = []
    for _, row in frame.iterrows():
        start = clean_date(row.get(start_column))
        end = clean_date(row.get(end_column)) if end_column else start
        if start:
            pairs.append((start, end or start))
    return pairs


def is_day_breakdown(frame: pd.DataFrame) -> bool:
    pairs = reporting_date_pairs(frame)
    distinct_days = {start for start, _ in pairs}
    return len(distinct_days) > 1 and all(start == end for start, end in pairs)


def validate_weekly_export(frame: pd.DataFrame, label: str) -> None:
    if is_day_breakdown(frame):
        raise HTTPException(
            400,
            (
                f"{label} is using the Day breakdown. "
                "Remove the breakdown from the three weekly exports. "
                "Only the optional fourth Ad-by-day export should use Day."
            ),
        )


def validate_daily_ad_export(frame: pd.DataFrame) -> None:
    if not is_day_breakdown(frame):
        raise HTTPException(
            400,
            (
                "The Ad-by-day export does not appear to use the Day breakdown. "
                "In Meta Ads, add Breakdown > Time > Day before exporting it."
            ),
        )


def get_or_create_week(con: sqlite3.Connection, week_start: str, week_end: str) -> int:
    try:
        start = date.fromisoformat(week_start)
        end = date.fromisoformat(week_end)
    except ValueError as exc:
        raise HTTPException(400, "Dates must use YYYY-MM-DD.") from exc
    if end < start:
        raise HTTPException(400, "The end date cannot be before the start date.")
    label = f"{start.strftime('%d %b %Y')} – {end.strftime('%d %b %Y')}"
    con.execute(
        """
        INSERT INTO weeks (week_start, week_end, label)
        VALUES (?, ?, ?)
        ON CONFLICT(week_start, week_end) DO UPDATE SET label=excluded.label
        """,
        (week_start, week_end, label),
    )
    row = con.execute(
        "SELECT id FROM weeks WHERE week_start=? AND week_end=?",
        (week_start, week_end),
    ).fetchone()
    return int(row["id"])


def import_campaigns(con: sqlite3.Connection, week_id: int, frame: pd.DataFrame) -> int:
    count = 0
    for _, row in frame.iterrows():
        name = clean_text(col(row, "Nome da campanha", "Campaign name"))
        if not name:
            continue
        key = entity_key(row, ("ID da campanha", "Campaign ID"), name)
        metrics = common_metrics(row)
        con.execute(
            """
            INSERT INTO campaign_metrics (
                week_id, entity_key, entity_name, status, created_date, spend,
                results, reach, frequency, impressions, link_clicks, cpc, ctr,
                landing_page_views, cost_per_lpv, cost_per_result
            ) VALUES (
                :week_id, :entity_key, :entity_name, :status, :created_date, :spend,
                :results, :reach, :frequency, :impressions, :link_clicks, :cpc, :ctr,
                :landing_page_views, :cost_per_lpv, :cost_per_result
            )
            ON CONFLICT(week_id, entity_key) DO UPDATE SET
                entity_name=excluded.entity_name, status=excluded.status,
                created_date=COALESCE(excluded.created_date, campaign_metrics.created_date),
                spend=excluded.spend,
                results=excluded.results, reach=excluded.reach,
                frequency=excluded.frequency, impressions=excluded.impressions,
                link_clicks=excluded.link_clicks, cpc=excluded.cpc, ctr=excluded.ctr,
                landing_page_views=CASE
                    WHEN :lpv_provided=1 THEN excluded.landing_page_views
                    ELSE campaign_metrics.landing_page_views
                END,
                cost_per_lpv=CASE
                    WHEN :cost_lpv_provided=1 THEN excluded.cost_per_lpv
                    ELSE campaign_metrics.cost_per_lpv
                END,
                cost_per_result=excluded.cost_per_result
            """,
            {"week_id": week_id, "entity_key": key, "entity_name": name, **metrics},
        )
        count += 1
    return count


def import_adsets(con: sqlite3.Connection, week_id: int, frame: pd.DataFrame) -> int:
    count = 0
    for _, row in frame.iterrows():
        name = clean_text(col(row, "Nome do conjunto de anúncios", "Ad set name"))
        if not name:
            continue
        key = entity_key(row, ("ID do conjunto de anúncios", "Ad set ID"), name)
        metrics = common_metrics(row)
        campaign_name = clean_text(col(row, "Nome da campanha", "Campaign name"))
        campaign_key = clean_text(col(row, "ID da campanha", "Campaign ID"))
        con.execute(
            """
            INSERT INTO adset_metrics (
                week_id, entity_key, entity_name, campaign_key, campaign_name,
                status, created_date, start_date, daily_budget, spend, results,
                reach, frequency, impressions, link_clicks, cpc, ctr,
                landing_page_views, cost_per_lpv, cost_per_result
            ) VALUES (
                :week_id, :entity_key, :entity_name, :campaign_key, :campaign_name,
                :status, :created_date, :start_date, :daily_budget, :spend, :results,
                :reach, :frequency, :impressions, :link_clicks, :cpc, :ctr,
                :landing_page_views, :cost_per_lpv, :cost_per_result
            )
            ON CONFLICT(week_id, entity_key) DO UPDATE SET
                entity_name=excluded.entity_name,
                campaign_name=COALESCE(excluded.campaign_name, adset_metrics.campaign_name),
                campaign_key=COALESCE(excluded.campaign_key, adset_metrics.campaign_key),
                status=excluded.status,
                created_date=COALESCE(excluded.created_date, adset_metrics.created_date),
                start_date=COALESCE(excluded.start_date, adset_metrics.start_date),
                daily_budget=excluded.daily_budget, spend=excluded.spend,
                results=excluded.results, reach=excluded.reach,
                frequency=excluded.frequency, impressions=excluded.impressions,
                link_clicks=excluded.link_clicks, cpc=excluded.cpc, ctr=excluded.ctr,
                landing_page_views=CASE
                    WHEN :lpv_provided=1 THEN excluded.landing_page_views
                    ELSE adset_metrics.landing_page_views
                END,
                cost_per_lpv=CASE
                    WHEN :cost_lpv_provided=1 THEN excluded.cost_per_lpv
                    ELSE adset_metrics.cost_per_lpv
                END,
                cost_per_result=excluded.cost_per_result
            """,
            {
                "week_id": week_id,
                "entity_key": key,
                "entity_name": name,
                "campaign_key": campaign_key,
                "campaign_name": campaign_name,
                "start_date": clean_date(col(row, "Início", "Start")),
                "daily_budget": clean_number(col(
                    row,
                    "Orçamento do conjunto de anúncios",
                    "Ad set budget",
                )) or None,
                **metrics,
            },
        )
        count += 1
    return count


def import_ads(con: sqlite3.Connection, week_id: int, frame: pd.DataFrame) -> int:
    count = 0
    for _, row in frame.iterrows():
        name = clean_text(col(row, "Nome do anúncio", "Ad name"))
        if not name:
            continue
        adset_name = clean_text(col(row, "Nome do conjunto de anúncios", "Ad set name"))
        raw_ad_id = clean_text(col(row, "ID do anúncio", "Ad ID"))
        key = raw_ad_id or f"{adset_name or 'unknown-adset'}::{name}".lower().strip()
        metrics = common_metrics(row)
        old_link = con.execute(
            "SELECT preview_url FROM ad_metrics WHERE entity_key=? AND preview_url IS NOT NULL ORDER BY id DESC LIMIT 1",
            (key,),
        ).fetchone()
        preview_url = old_link["preview_url"] if old_link else None
        con.execute(
            """
            INSERT INTO ad_metrics (
                week_id, entity_key, entity_name, campaign_key, campaign_name,
                adset_key, adset_name, status, created_date, spend, results, reach,
                frequency, impressions, link_clicks, cpc, ctr, landing_page_views,
                cost_per_lpv, cost_per_result, quality_ranking, engagement_ranking,
                conversion_ranking, preview_url
            ) VALUES (
                :week_id, :entity_key, :entity_name, :campaign_key, :campaign_name,
                :adset_key, :adset_name, :status, :created_date, :spend, :results, :reach,
                :frequency, :impressions, :link_clicks, :cpc, :ctr, :landing_page_views,
                :cost_per_lpv, :cost_per_result, :quality_ranking, :engagement_ranking,
                :conversion_ranking, :preview_url
            )
            ON CONFLICT(week_id, entity_key) DO UPDATE SET
                entity_name=excluded.entity_name,
                campaign_name=COALESCE(excluded.campaign_name, ad_metrics.campaign_name),
                campaign_key=COALESCE(excluded.campaign_key, ad_metrics.campaign_key),
                adset_key=COALESCE(excluded.adset_key, ad_metrics.adset_key),
                adset_name=COALESCE(excluded.adset_name, ad_metrics.adset_name),
                status=excluded.status,
                created_date=COALESCE(excluded.created_date, ad_metrics.created_date),
                spend=excluded.spend,
                results=excluded.results, reach=excluded.reach,
                frequency=excluded.frequency, impressions=excluded.impressions,
                link_clicks=excluded.link_clicks, cpc=excluded.cpc, ctr=excluded.ctr,
                landing_page_views=CASE
                    WHEN :lpv_provided=1 THEN excluded.landing_page_views
                    ELSE ad_metrics.landing_page_views
                END,
                cost_per_lpv=CASE
                    WHEN :cost_lpv_provided=1 THEN excluded.cost_per_lpv
                    ELSE ad_metrics.cost_per_lpv
                END,
                cost_per_result=excluded.cost_per_result,
                quality_ranking=excluded.quality_ranking,
                engagement_ranking=excluded.engagement_ranking,
                conversion_ranking=excluded.conversion_ranking,
                preview_url=COALESCE(ad_metrics.preview_url, excluded.preview_url)
            """,
            {
                "week_id": week_id,
                "entity_key": key,
                "entity_name": name,
                "campaign_key": clean_text(col(row, "ID da campanha", "Campaign ID")),
                "campaign_name": clean_text(col(row, "Nome da campanha", "Campaign name")),
                "adset_key": clean_text(col(row, "ID do conjunto de anúncios", "Ad set ID")),
                "adset_name": adset_name,
                "quality_ranking": clean_text(col(row, "Classificação de qualidade", "Quality ranking")),
                "engagement_ranking": clean_text(col(row, "Classificação da taxa de engajamento", "Engagement rate ranking")),
                "conversion_ranking": clean_text(col(row, "Classificação da taxa de conversão", "Conversion rate ranking")),
                "preview_url": preview_url,
                **metrics,
            },
        )
        count += 1
    return count


def import_daily_ads(
    con: sqlite3.Connection,
    week_id: int,
    frame: pd.DataFrame,
) -> int:
    count = 0
    for _, row in frame.iterrows():
        report_date = clean_date(
            col(
                row,
                "Dia",
                "Day",
                "Início dos relatórios",
                "Reporting starts",
            )
        )
        name = clean_text(col(row, "Nome do anúncio", "Ad name"))
        if not report_date or not name:
            continue

        adset_name = clean_text(
            col(row, "Nome do conjunto de anúncios", "Ad set name")
        )
        raw_ad_id = clean_text(col(row, "ID do anúncio", "Ad ID"))
        key = raw_ad_id or f"{adset_name or 'unknown-adset'}::{name}".lower().strip()
        metrics = common_metrics(row)

        con.execute(
            """
            INSERT INTO daily_ad_metrics (
                week_id, report_date, entity_key, entity_name,
                campaign_key, campaign_name, adset_key, adset_name,
                status, spend, results, reach, frequency, impressions,
                link_clicks, cpc, ctr, landing_page_views, cost_per_lpv,
                cost_per_result
            ) VALUES (
                :week_id, :report_date, :entity_key, :entity_name,
                :campaign_key, :campaign_name, :adset_key, :adset_name,
                :status, :spend, :results, :reach, :frequency, :impressions,
                :link_clicks, :cpc, :ctr, :landing_page_views, :cost_per_lpv,
                :cost_per_result
            )
            ON CONFLICT(week_id, report_date, entity_key) DO UPDATE SET
                entity_name=excluded.entity_name,
                campaign_key=COALESCE(excluded.campaign_key, daily_ad_metrics.campaign_key),
                campaign_name=COALESCE(excluded.campaign_name, daily_ad_metrics.campaign_name),
                adset_key=COALESCE(excluded.adset_key, daily_ad_metrics.adset_key),
                adset_name=COALESCE(excluded.adset_name, daily_ad_metrics.adset_name),
                status=excluded.status,
                spend=excluded.spend,
                results=excluded.results,
                reach=excluded.reach,
                frequency=excluded.frequency,
                impressions=excluded.impressions,
                link_clicks=excluded.link_clicks,
                cpc=excluded.cpc,
                ctr=excluded.ctr,
                landing_page_views=excluded.landing_page_views,
                cost_per_lpv=excluded.cost_per_lpv,
                cost_per_result=excluded.cost_per_result
            """,
            {
                "week_id": week_id,
                "report_date": report_date,
                "entity_key": key,
                "entity_name": name,
                "campaign_key": clean_text(
                    col(row, "ID da campanha", "Campaign ID")
                ),
                "campaign_name": clean_text(
                    col(row, "Nome da campanha", "Campaign name")
                ),
                "adset_key": clean_text(
                    col(row, "ID do conjunto de anúncios", "Ad set ID")
                ),
                "adset_name": adset_name,
                **metrics,
            },
        )
        count += 1
    return count


@app.post("/api/import/meta")
def import_meta(
    week_start: str = Form(""),
    week_end: str = Form(""),
    campaigns_file: UploadFile = File(...),
    adsets_file: UploadFile = File(...),
    ads_file: UploadFile = File(...),
    ads_daily_file: UploadFile | None = File(None),
):
    campaign_frame = read_excel(campaigns_file)
    adset_frame = read_excel(adsets_file)
    ad_frame = read_excel(ads_file)

    validate_weekly_export(campaign_frame, "The campaign export")
    validate_weekly_export(adset_frame, "The ad-set export")
    validate_weekly_export(ad_frame, "The weekly ad export")

    daily_frame: pd.DataFrame | None = None
    if ads_daily_file is not None and ads_daily_file.filename:
        daily_frame = read_excel(ads_daily_file)
        validate_daily_ad_export(daily_frame)

    resolved_start = week_start.strip() or infer_report_date(
        campaign_frame, "Início dos relatórios", "Reporting starts"
    )
    resolved_end = week_end.strip() or infer_report_date(
        campaign_frame, "Encerramento dos relatórios", "Reporting ends"
    )
    if not resolved_start or not resolved_end:
        raise HTTPException(
            400,
            "Could not detect the reporting dates. Enter the start and end dates manually.",
        )

    with db() as con:
        week_id = get_or_create_week(con, resolved_start, resolved_end)
        counts = {
            "campaigns": import_campaigns(con, week_id, campaign_frame),
            "adsets": import_adsets(con, week_id, adset_frame),
            "ads": import_ads(con, week_id, ad_frame),
            "daily_ads": 0,
        }

        if daily_frame is not None:
            con.execute(
                "DELETE FROM daily_ad_metrics WHERE week_id=?",
                (week_id,),
            )
            counts["daily_ads"] = import_daily_ads(con, week_id, daily_frame)

        backfill_relations(con, week_id)

    return {
        "ok": True,
        "week_id": week_id,
        "week_start": resolved_start,
        "week_end": resolved_end,
        "counts": counts,
        "daily_detail_included": daily_frame is not None,
    }


@app.get("/api/weeks")
def list_weeks():
    with db() as con:
        rows = con.execute(
            "SELECT * FROM weeks ORDER BY week_start DESC"
        ).fetchall()
    return [dict(row) for row in rows]


def rows(con: sqlite3.Connection, query: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    return [dict(row) for row in con.execute(query, params).fetchall()]


def totals(data: list[dict[str, Any]]) -> dict[str, float]:
    spend = sum(float(x.get("spend") or 0) for x in data)
    results = sum(float(x.get("results") or 0) for x in data)
    impressions = sum(float(x.get("impressions") or 0) for x in data)
    clicks = sum(float(x.get("link_clicks") or 0) for x in data)
    lpv = sum(float(x.get("landing_page_views") or 0) for x in data)
    return {
        "spend": spend,
        "results": results,
        "cpl": spend / results if results else None,
        "impressions": impressions,
        "link_clicks": clicks,
        "cpc": spend / clicks if clicks else None,
        "ctr": clicks / impressions * 100 if impressions else None,
        "landing_page_views": lpv,
        "cost_per_lpv": spend / lpv if lpv else None,
    }


def funnel_metrics(data: list[dict[str, Any]]) -> dict[str, Any]:
    summary = totals(data)
    lpv = float(summary.get("landing_page_views") or 0)
    clicks = float(summary.get("link_clicks") or 0)
    results = float(summary.get("results") or 0)
    denominator = lpv if lpv > 0 else clicks
    basis = "landing_page_views" if lpv > 0 else "link_clicks_proxy"
    conversion_rate = results * 100.0 / denominator if denominator else None
    drop_off_rate = (denominator - results) * 100.0 / denominator if denominator else None
    return {
        **summary,
        "conversion_denominator": denominator,
        "conversion_basis": basis,
        "conversion_rate": conversion_rate,
        "drop_off_rate": drop_off_rate,
    }


def add_conversion_fields(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        row = dict(item)
        lpv = float(row.get("landing_page_views") or 0)
        clicks = float(row.get("link_clicks") or 0)
        results = float(row.get("results") or 0)
        denominator = lpv if lpv > 0 else clicks
        row["conversion_denominator"] = denominator
        row["conversion_basis"] = (
            "landing_page_views" if lpv > 0 else "link_clicks_proxy"
        )
        row["conversion_rate"] = (
            results * 100.0 / denominator if denominator else None
        )
        row["drop_off_rate"] = (
            (denominator - results) * 100.0 / denominator if denominator else None
        )
        row["calculated_cpl"] = (
            float(row.get("spend") or 0) / results if results else None
        )
        if row.get("entity_name"):
            row.update(page_identity_from_ad_name(row.get("entity_name")))
        enriched.append(row)
    return enriched



PAGE_TAG_PATTERN = re.compile(r"\[\s*LP\s*[-_: ]\s*([^\]]+?)\s*\]", re.IGNORECASE)
MAIN_PAGE_CODES = {"MAIN", "PRINCIPAL", "DEFAULT", "PADRAO", "PADRÃO"}


def normalize_page_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"[^A-Z0-9_-]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-_")


def page_identity_from_ad_name(ad_name: str | None) -> dict[str, Any]:
    """Read [LP-A], [LP-B], [LP-QUIZ], etc. Ads without a tag use Main page."""
    text = str(ad_name or "")
    match = PAGE_TAG_PATTERN.search(text)
    if not match:
        return {
            "page_key": "main",
            "page_code": "MAIN",
            "page_name": "Main page",
            "is_default": True,
        }
    code = normalize_page_code(match.group(1)) or "MAIN"
    if code in MAIN_PAGE_CODES:
        return {
            "page_key": "main",
            "page_code": "MAIN",
            "page_name": "Main page",
            "is_default": True,
        }
    readable = code.replace("_", " ").replace("-", " ").title()
    if len(code) <= 3:
        readable = code.upper()
    return {
        "page_key": f"lp-{code.lower()}",
        "page_code": code,
        "page_name": f"Page {readable}",
        "is_default": False,
    }


def registered_page_map(con: sqlite3.Connection) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows(
        con,
        """
        SELECT *, COALESCE(start_date, substr(created_at, 1, 10)) AS effective_start_date
        FROM landing_pages
        ORDER BY id
        """,
    ):
        code = normalize_page_code(row.get("page_code") or row.get("variant_name"))
        if not code:
            continue
        key = "main" if code in MAIN_PAGE_CODES else f"lp-{code.lower()}"
        output[key] = row
    return output


def page_history_start_dates(con: sqlite3.Connection) -> dict[str, str]:
    output: dict[str, str] = {}
    history = rows(
        con,
        """
        SELECT adm.entity_name, adm.created_date, w.week_start
        FROM ad_metrics adm
        JOIN weeks w ON w.id=adm.week_id
        """,
    )
    for row in history:
        identity = page_identity_from_ad_name(row.get("entity_name"))
        candidate = row.get("created_date") or row.get("week_start")
        if not candidate:
            continue
        current = output.get(identity["page_key"])
        if current is None or candidate < current:
            output[identity["page_key"]] = candidate
    return output


def aggregate_ads_by_page(
    ads: list[dict[str, Any]],
    start_dates: dict[str, str],
    registered: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for ad in ads:
        identity = page_identity_from_ad_name(ad.get("entity_name"))
        key = identity["page_key"]
        registration = registered.get(key) or {}
        group = groups.setdefault(
            key,
            {
                **identity,
                "page_name": registration.get("page_name") or identity["page_name"],
                "variant_name": registration.get("variant_name") or identity["page_name"],
                "page_url": registration.get("page_url"),
                "status": registration.get("status") or "active",
                "effective_start_date": start_dates.get(key) or registration.get("effective_start_date"),
                "start_date_source": "first_tagged_ad" if start_dates.get(key) else "registered_start_date",
                "spend": 0.0,
                "results": 0.0,
                "impressions": 0.0,
                "link_clicks": 0.0,
                "landing_page_views": 0.0,
                "ad_keys": set(),
                "ad_names": [],
            },
        )
        group["spend"] += float(ad.get("spend") or 0)
        group["results"] += float(ad.get("results") or 0)
        group["impressions"] += float(ad.get("impressions") or 0)
        group["link_clicks"] += float(ad.get("link_clicks") or 0)
        group["landing_page_views"] += float(ad.get("landing_page_views") or 0)
        group["ad_keys"].add(str(ad.get("entity_key") or ad.get("id")))
        ad_name = str(ad.get("entity_name") or "")
        if ad_name and ad_name not in group["ad_names"]:
            group["ad_names"].append(ad_name)

    result: list[dict[str, Any]] = []
    for group in groups.values():
        spend = float(group["spend"])
        registrations = float(group["results"])
        impressions = float(group["impressions"])
        clicks = float(group["link_clicks"])
        lpv = float(group["landing_page_views"])
        denominator = lpv if lpv > 0 else clicks
        group["ad_count"] = len(group.pop("ad_keys"))
        group["ad_names"] = sorted(group["ad_names"], key=str.lower)
        group["cpl"] = spend / registrations if registrations else None
        group["cpc"] = spend / clicks if clicks else None
        group["ctr"] = clicks * 100.0 / impressions if impressions else None
        group["conversion_denominator"] = denominator
        group["conversion_basis"] = "landing_page_views" if lpv > 0 else "link_clicks_proxy"
        group["conversion_rate"] = registrations * 100.0 / denominator if denominator else None
        group["drop_off_rate"] = (denominator - registrations) * 100.0 / denominator if denominator else None
        result.append(group)
    return sorted(result, key=lambda item: (-float(item["spend"]), item["page_name"].lower()))


def compare_page_groups(
    current_groups: list[dict[str, Any]],
    previous_groups: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    current_map = {row["page_key"]: row for row in current_groups}
    previous_map = {row["page_key"]: row for row in previous_groups}
    output: list[dict[str, Any]] = []
    for key in set(current_map) | set(previous_map):
        current = current_map.get(key) or {}
        previous = previous_map.get(key) or {}
        if current and previous:
            delivery_status = "continued"
        elif current:
            delivery_status = "new"
        else:
            delivery_status = "not_in_current_week"
        current_metrics = {
            "spend": float(current.get("spend") or 0),
            "results": float(current.get("results") or 0),
            "cpl": current.get("cpl"),
            "conversion_rate": current.get("conversion_rate"),
            "link_clicks": float(current.get("link_clicks") or 0),
            "landing_page_views": float(current.get("landing_page_views") or 0),
            "ad_count": int(current.get("ad_count") or 0),
        }
        previous_metrics = {
            "spend": float(previous.get("spend") or 0),
            "results": float(previous.get("results") or 0),
            "cpl": previous.get("cpl"),
            "conversion_rate": previous.get("conversion_rate"),
            "link_clicks": float(previous.get("link_clicks") or 0),
            "landing_page_views": float(previous.get("landing_page_views") or 0),
            "ad_count": int(previous.get("ad_count") or 0),
        }
        output.append(
            {
                "page_key": key,
                "page_name": current.get("page_name") or previous.get("page_name") or key,
                "page_code": current.get("page_code") or previous.get("page_code"),
                "delivery_status": delivery_status,
                "effective_start_date": current.get("effective_start_date") or previous.get("effective_start_date"),
                "current": current_metrics,
                "previous": previous_metrics,
                "change": {
                    "spend": percent_change(current_metrics["spend"], previous_metrics["spend"]),
                    "results": percent_change(current_metrics["results"], previous_metrics["results"]),
                    "cpl": percent_change(current_metrics["cpl"], previous_metrics["cpl"]),
                    "conversion_rate": percent_change(
                        current_metrics["conversion_rate"], previous_metrics["conversion_rate"]
                    ),
                },
            }
        )
    return sorted(
        output,
        key=lambda item: (
            -float(item["current"]["spend"] or 0),
            -float(item["previous"]["spend"] or 0),
            item["page_name"].lower(),
        ),
    )


def entity_rows_with_dates(
    con: sqlite3.Connection,
    table: str,
    alias: str,
    week_id: int,
    date_expression: str,
) -> list[dict[str, Any]]:
    query = f"""
        SELECT
            {alias}.*,
            COALESCE(
                {date_expression},
                (
                    SELECT MIN(w2.week_start)
                    FROM {table} history
                    JOIN weeks w2 ON w2.id=history.week_id
                    WHERE history.entity_key={alias}.entity_key
                )
            ) AS effective_start_date,
            CASE
                WHEN {date_expression} IS NOT NULL THEN 'meta_start_date'
                ELSE 'first_imported_delivery'
            END AS start_date_source
        FROM {table} {alias}
        WHERE {alias}.week_id=?
        ORDER BY {alias}.spend DESC, {alias}.entity_name
    """
    return rows(con, query, (week_id,))


def aggregate_daily_performance(
    daily_ads: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}

    for ad in daily_ads:
        report_date = str(ad.get("report_date") or "")
        if not report_date:
            continue

        group = grouped.setdefault(
            report_date,
            {
                "report_date": report_date,
                "spend": 0.0,
                "results": 0.0,
                "impressions": 0.0,
                "link_clicks": 0.0,
                "landing_page_views": 0.0,
                "ad_keys": set(),
                "page_keys": set(),
            },
        )
        group["spend"] += float(ad.get("spend") or 0)
        group["results"] += float(ad.get("results") or 0)
        group["impressions"] += float(ad.get("impressions") or 0)
        group["link_clicks"] += float(ad.get("link_clicks") or 0)
        group["landing_page_views"] += float(ad.get("landing_page_views") or 0)
        delivered = any(
            float(ad.get(field) or 0) > 0
            for field in ("spend", "results", "impressions", "link_clicks")
        )
        if delivered:
            group["ad_keys"].add(str(ad.get("entity_key") or ad.get("id")))
            group["page_keys"].add(str(ad.get("page_key") or "main"))

    output: list[dict[str, Any]] = []
    for report_date in sorted(grouped):
        group = grouped[report_date]
        spend = float(group["spend"])
        results = float(group["results"])
        impressions = float(group["impressions"])
        clicks = float(group["link_clicks"])
        lpv = float(group["landing_page_views"])
        denominator = lpv if lpv > 0 else clicks

        output.append(
            {
                "report_date": report_date,
                "spend": spend,
                "results": results,
                "cpl": spend / results if results else None,
                "impressions": impressions,
                "link_clicks": clicks,
                "cpc": spend / clicks if clicks else None,
                "ctr": clicks * 100.0 / impressions if impressions else None,
                "landing_page_views": lpv,
                "cost_per_lpv": spend / lpv if lpv else None,
                "conversion_denominator": denominator,
                "conversion_basis": (
                    "landing_page_views" if lpv > 0 else "link_clicks_proxy"
                ),
                "conversion_rate": (
                    results * 100.0 / denominator if denominator else None
                ),
                "ad_count": len(group["ad_keys"]),
                "page_count": len(group["page_keys"]),
            }
        )

    return output


@app.get("/api/dashboard")
def dashboard(week_id: int | None = None):
    with db() as con:
        if week_id is None:
            current = con.execute(
                "SELECT * FROM weeks ORDER BY week_start DESC LIMIT 1"
            ).fetchone()
        else:
            current = con.execute(
                "SELECT * FROM weeks WHERE id=?", (week_id,)
            ).fetchone()

        if not current:
            return {
                "current_week": None,
                "previous_week": None,
                "totals": {},
                "previous_totals": {},
                "conversion_summary": {},
                "previous_conversion_summary": {},
                "campaigns": [],
                "adsets": [],
                "ads": [],
                "pages": [],
                "page_groups": [],
                "previous_page_groups": [],
                "page_comparison": [],
                "daily_ads": [],
                "daily_summary": [],
                "daily_available": False,
            }

        previous = con.execute(
            "SELECT * FROM weeks WHERE week_start < ? ORDER BY week_start DESC LIMIT 1",
            (current["week_start"],),
        ).fetchone()

        campaigns = entity_rows_with_dates(
            con,
            "campaign_metrics",
            "cm",
            int(current["id"]),
            "cm.created_date",
        )
        adsets = entity_rows_with_dates(
            con,
            "adset_metrics",
            "asm",
            int(current["id"]),
            "COALESCE(asm.start_date, asm.created_date)",
        )
        ads = entity_rows_with_dates(
            con,
            "ad_metrics",
            "adm",
            int(current["id"]),
            "adm.created_date",
        )
        daily_ads = add_conversion_fields(
            rows(
                con,
                """
                SELECT *
                FROM daily_ad_metrics
                WHERE week_id=?
                ORDER BY report_date, spend DESC, entity_name
                """,
                (current["id"],),
            )
        )

        pages = rows(
            con,
            """
            SELECT
                lpm.*, lp.page_name, lp.variant_name, lp.page_url, lp.status,
                COALESCE(lp.start_date, substr(lp.created_at, 1, 10)) AS effective_start_date,
                CASE
                    WHEN lp.start_date IS NOT NULL THEN 'registered_start_date'
                    ELSE 'dashboard_registration_date'
                END AS start_date_source,
                CASE
                    WHEN lpm.page_views > 0
                    THEN lpm.leads * 100.0 / lpm.page_views
                END AS conversion_rate,
                CASE
                    WHEN lpm.page_views > 0
                    THEN (lpm.page_views - lpm.leads) * 100.0 / lpm.page_views
                END AS drop_off_rate,
                CASE WHEN lpm.leads > 0 THEN lpm.spend / lpm.leads END AS cpl
            FROM landing_page_metrics lpm
            JOIN landing_pages lp ON lp.id=lpm.landing_page_id
            WHERE lpm.week_id=?
            ORDER BY lpm.leads DESC, lpm.page_views DESC
            """,
            (current["id"],),
        )

        all_pages = rows(
            con,
            """
            SELECT
                lp.*,
                COALESCE(lp.start_date, substr(lp.created_at, 1, 10)) AS effective_start_date,
                CASE
                    WHEN lp.start_date IS NOT NULL THEN 'registered_start_date'
                    ELSE 'dashboard_registration_date'
                END AS start_date_source
            FROM landing_pages lp
            ORDER BY lp.page_name, lp.variant_name
            """,
        )
        page_ids_with_metrics = {int(page["landing_page_id"]) for page in pages}
        for page in all_pages:
            if int(page["id"]) in page_ids_with_metrics:
                continue
            pages.append(
                {
                    "landing_page_id": page["id"],
                    "page_name": page["page_name"],
                    "variant_name": page["variant_name"],
                    "page_url": page["page_url"],
                    "status": page["status"],
                    "effective_start_date": page["effective_start_date"],
                    "start_date_source": page["start_date_source"],
                    "sessions": 0,
                    "page_views": 0,
                    "leads": 0,
                    "spend": 0,
                    "conversion_rate": None,
                    "drop_off_rate": None,
                    "cpl": None,
                }
            )

        previous_campaigns: list[dict[str, Any]] = []
        previous_ads: list[dict[str, Any]] = []
        if previous:
            previous_campaigns = rows(
                con,
                "SELECT * FROM campaign_metrics WHERE week_id=?",
                (previous["id"],),
            )
            previous_ads = entity_rows_with_dates(
                con,
                "ad_metrics",
                "padm",
                int(previous["id"]),
                "padm.created_date",
            )

        page_starts = page_history_start_dates(con)
        registered_pages = registered_page_map(con)
        page_groups = aggregate_ads_by_page(ads, page_starts, registered_pages)
        previous_page_groups = aggregate_ads_by_page(
            previous_ads, page_starts, registered_pages
        )

    current_totals = totals(campaigns)
    previous_totals = totals(previous_campaigns)
    return {
        "current_week": dict(current),
        "previous_week": dict(previous) if previous else None,
        "totals": current_totals,
        "previous_totals": previous_totals,
        "conversion_summary": funnel_metrics(campaigns),
        "previous_conversion_summary": funnel_metrics(previous_campaigns),
        "campaigns": add_conversion_fields(campaigns),
        "adsets": add_conversion_fields(adsets),
        "ads": add_conversion_fields(ads),
        "pages": pages,
        "page_groups": page_groups,
        "previous_page_groups": previous_page_groups,
        "page_comparison": compare_page_groups(page_groups, previous_page_groups),
        "daily_ads": daily_ads,
        "daily_summary": aggregate_daily_performance(daily_ads),
        "daily_available": bool(daily_ads),
    }


def percent_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous in (None, 0):
        return None
    return (float(current) - float(previous)) * 100.0 / float(previous)


def derived_metrics(row: dict[str, Any] | None) -> dict[str, Any]:
    if not row:
        return {
            "spend": 0.0,
            "results": 0.0,
            "cpl": None,
            "impressions": 0.0,
            "link_clicks": 0.0,
            "cpc": None,
            "ctr": None,
            "reach": 0.0,
            "frequency": 0.0,
        }
    spend = float(row.get("spend") or 0)
    results = float(row.get("results") or 0)
    impressions = float(row.get("impressions") or 0)
    clicks = float(row.get("link_clicks") or 0)
    return {
        "spend": spend,
        "results": results,
        "cpl": spend / results if results else None,
        "impressions": impressions,
        "link_clicks": clicks,
        "cpc": spend / clicks if clicks else None,
        "ctr": clicks * 100.0 / impressions if impressions else None,
        "reach": float(row.get("reach") or 0),
        "frequency": float(row.get("frequency") or 0),
    }


def compare_entity_sets(
    current_rows: list[dict[str, Any]],
    previous_rows: list[dict[str, Any]],
    relation_field: str | None = None,
) -> list[dict[str, Any]]:
    current_map = {str(row["entity_key"]): row for row in current_rows}
    previous_map = {str(row["entity_key"]): row for row in previous_rows}
    output: list[dict[str, Any]] = []

    for key in set(current_map) | set(previous_map):
        current_row = current_map.get(key)
        previous_row = previous_map.get(key)
        current = derived_metrics(current_row)
        previous = derived_metrics(previous_row)
        entity_name = (
            (current_row or {}).get("entity_name")
            or (previous_row or {}).get("entity_name")
            or key
        )
        relation_name = None
        if relation_field:
            relation_name = (
                (current_row or {}).get(relation_field)
                or (previous_row or {}).get(relation_field)
            )
        if current_row and previous_row:
            delivery_status = "continued"
        elif current_row:
            delivery_status = "new"
        else:
            delivery_status = "not_in_current_week"

        output.append(
            {
                "entity_key": key,
                "entity_name": entity_name,
                "relation_name": relation_name,
                "delivery_status": delivery_status,
                "current_status": (current_row or {}).get("status"),
                "previous_status": (previous_row or {}).get("status"),
                "current": current,
                "previous": previous,
                "change": {
                    "spend": percent_change(current["spend"], previous["spend"]),
                    "results": percent_change(current["results"], previous["results"]),
                    "cpl": percent_change(current["cpl"], previous["cpl"]),
                    "link_clicks": percent_change(
                        current["link_clicks"], previous["link_clicks"]
                    ),
                    "cpc": percent_change(current["cpc"], previous["cpc"]),
                    "ctr": percent_change(current["ctr"], previous["ctr"]),
                },
            }
        )

    return sorted(
        output,
        key=lambda item: (
            -float(item["current"]["spend"] or 0),
            -float(item["previous"]["spend"] or 0),
            item["entity_name"].lower(),
        ),
    )


@app.get("/api/comparison")
def comparison(current_week_id: int, previous_week_id: int):
    if current_week_id == previous_week_id:
        raise HTTPException(400, "Choose two different reporting weeks.")

    with db() as con:
        current_week = con.execute(
            "SELECT * FROM weeks WHERE id=?", (current_week_id,)
        ).fetchone()
        previous_week = con.execute(
            "SELECT * FROM weeks WHERE id=?", (previous_week_id,)
        ).fetchone()
        if not current_week or not previous_week:
            raise HTTPException(404, "Reporting week not found.")

        current_campaigns = rows(
            con,
            "SELECT * FROM campaign_metrics WHERE week_id=?",
            (current_week_id,),
        )
        previous_campaigns = rows(
            con,
            "SELECT * FROM campaign_metrics WHERE week_id=?",
            (previous_week_id,),
        )
        current_adsets = rows(
            con,
            "SELECT * FROM adset_metrics WHERE week_id=?",
            (current_week_id,),
        )
        previous_adsets = rows(
            con,
            "SELECT * FROM adset_metrics WHERE week_id=?",
            (previous_week_id,),
        )
        current_ads = entity_rows_with_dates(
            con, "ad_metrics", "cadm", current_week_id, "cadm.created_date"
        )
        previous_ads = entity_rows_with_dates(
            con, "ad_metrics", "padm", previous_week_id, "padm.created_date"
        )
        page_starts = page_history_start_dates(con)
        registered_pages = registered_page_map(con)
        current_page_groups = aggregate_ads_by_page(
            current_ads, page_starts, registered_pages
        )
        previous_page_groups = aggregate_ads_by_page(
            previous_ads, page_starts, registered_pages
        )

    return {
        "current_week": dict(current_week),
        "previous_week": dict(previous_week),
        "current_totals": totals(current_campaigns),
        "previous_totals": totals(previous_campaigns),
        "campaigns": compare_entity_sets(current_campaigns, previous_campaigns),
        "adsets": compare_entity_sets(
            current_adsets, previous_adsets, relation_field="campaign_name"
        ),
        "ads": compare_entity_sets(
            current_ads, previous_ads, relation_field="adset_name"
        ),
        "pages": compare_page_groups(current_page_groups, previous_page_groups),
    }


@app.post("/api/ads/{ad_id}/preview")
def update_ad_preview(ad_id: int, payload: dict[str, Any]):
    url = str(payload.get("preview_url") or "").strip()
    if url and not url.startswith(("http://", "https://")):
        raise HTTPException(400, "The link must start with http:// or https://")
    with db() as con:
        row = con.execute(
            "SELECT entity_key FROM ad_metrics WHERE id=?", (ad_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, "Ad not found")
        con.execute(
            "UPDATE ad_metrics SET preview_url=? WHERE entity_key=?",
            (url or None, row["entity_key"]),
        )
    return {"ok": True}


@app.post("/api/pages")
def create_page(payload: dict[str, Any]):
    page_name = str(payload.get("page_name") or "").strip()
    variant_name = str(payload.get("variant_name") or "Default").strip()
    start_date = clean_date(payload.get("start_date"))
    page_code = normalize_page_code(payload.get("page_code") or variant_name)
    if not page_name:
        raise HTTPException(400, "Page name is required.")
    with db() as con:
        con.execute(
            """
            INSERT INTO landing_pages (
                page_name, variant_name, page_code, page_url, start_date, status
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(page_name, variant_name) DO UPDATE SET
                page_code=excluded.page_code,
                page_url=excluded.page_url,
                start_date=COALESCE(excluded.start_date, landing_pages.start_date),
                status=excluded.status
            """,
            (
                page_name,
                variant_name,
                page_code,
                str(payload.get("page_url") or "").strip() or None,
                start_date,
                str(payload.get("status") or "active").strip(),
            ),
        )
        row = con.execute(
            """
            SELECT
                *,
                COALESCE(start_date, substr(created_at, 1, 10)) AS effective_start_date
            FROM landing_pages
            WHERE page_name=? AND variant_name=?
            """,
            (page_name, variant_name),
        ).fetchone()
    return dict(row)


@app.get("/api/pages")
def list_pages():
    with db() as con:
        return rows(
            con,
            """
            SELECT
                *,
                COALESCE(start_date, substr(created_at, 1, 10)) AS effective_start_date
            FROM landing_pages
            ORDER BY page_name, variant_name
            """,
        )


@app.post("/api/page-metrics")
def save_page_metrics(payload: dict[str, Any]):
    required = ("week_id", "landing_page_id")
    if any(payload.get(key) in (None, "") for key in required):
        raise HTTPException(400, "Week and landing page are required.")
    with db() as con:
        con.execute(
            """
            INSERT INTO landing_page_metrics (
                week_id, landing_page_id, sessions, page_views, leads, spend
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_id, landing_page_id) DO UPDATE SET
                sessions=excluded.sessions, page_views=excluded.page_views,
                leads=excluded.leads, spend=excluded.spend
            """,
            (
                int(payload["week_id"]),
                int(payload["landing_page_id"]),
                clean_number(payload.get("sessions")),
                clean_number(payload.get("page_views")),
                clean_number(payload.get("leads")),
                clean_number(payload.get("spend")),
            ),
        )
    return {"ok": True}
