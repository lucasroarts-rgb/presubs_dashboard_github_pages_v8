from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import (  # noqa: E402
    AutomationError,
    MetaClient,
    MetaConfig,
    build_frames,
    load_env_file,
    metadata_maps,
    qa_report,
    resilient_insights,
    save_exports,
)
from scripts.generate_public_site import main as generate_public_site  # noqa: E402
from scripts.generate_weekly_review import main as generate_weekly_review  # noqa: E402
from scripts.sync_crm import main as sync_crm  # noqa: E402
from scripts.sync_ga4 import main as sync_ga4  # noqa: E402
from scripts.sync_gsc import main as sync_gsc  # noqa: E402
from scripts.sync_google_ads import main as sync_google_ads  # noqa: E402
from scripts.sync_youtube import main as sync_youtube  # noqa: E402
from scripts.sync_youtube_analytics import main as sync_youtube_analytics  # noqa: E402
from scripts.sync_ghl import main as sync_ghl  # noqa: E402
from scripts.sync_meta_organic import main as sync_meta_organic  # noqa: E402
from scripts.sync_video_funnel import main as sync_video_funnel  # noqa: E402

LOGS_DIR = ROOT / "logs"


def friday_thursday_bounds(day: date) -> tuple[date, date]:
    days_since_friday = (day.weekday() - 4) % 7
    start = day - timedelta(days=days_since_friday)
    return start, start + timedelta(days=6)


def run_git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), *args],
        text=True,
        capture_output=True,
    )
    if check and result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip()
        raise AutomationError(f"Git command failed: git {' '.join(args)}\\n{detail}")
    return result


def prepare_git() -> None:
    if not (ROOT / ".git").exists():
        raise AutomationError(
            "This folder is not connected to GitHub. "
            "Run MIGRAR_DA_VERSAO_ATUAL.bat first."
        )

    branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if branch == "HEAD":
        raise AutomationError(
            "Git is in detached HEAD mode. Open GitHub Desktop or finish/abort "
            "the previous rebase before running the daily automation."
        )

    rebase_dir = ROOT / ".git" / "rebase-merge"
    rebase_apply = ROOT / ".git" / "rebase-apply"
    if rebase_dir.exists() or rebase_apply.exists():
        raise AutomationError(
            "A Git rebase is still open. Finish or abort it before the scheduled sync."
        )

    run_git(["fetch", "origin"])
    pull = run_git(
        ["pull", "--rebase", "--autostash", "origin", branch],
        check=False,
    )
    if pull.returncode != 0:
        detail = pull.stderr.strip() or pull.stdout.strip()
        raise AutomationError(
            "Could not synchronize the local folder with GitHub before publishing.\\n"
            + detail
        )


def publish_docs(message: str) -> dict[str, object]:
    run_git(["add", "docs", "weekly_reviews", "static/weekly-review.html", ".gitignore", "README.md"])
    diff = run_git(["diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        return {"changed": False, "pushed": False}

    run_git(["commit", "-m", message])
    push = run_git(["push", "origin", "HEAD"], check=False)
    if push.returncode != 0:
        run_git(["fetch", "origin"])
        branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
        rebase = run_git(
            ["pull", "--rebase", "--autostash", "origin", branch],
            check=False,
        )
        if rebase.returncode != 0:
            detail = rebase.stderr.strip() or rebase.stdout.strip()
            raise AutomationError(
                "The daily data was committed, but GitHub changed at the same time.\\n"
                + detail
            )
        run_git(["push", "origin", "HEAD"])
    return {"changed": True, "pushed": True}


def import_fixed_week(
    *,
    week_start: str,
    week_end: str,
    frames,
) -> dict[str, object]:
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

        week_id = dashboard_app.get_or_create_week(con, week_start, week_end)
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


def main() -> int:
    try:
        values = load_env_file()
        config = MetaConfig.from_env(values)
        client = MetaClient(config)
        account = client.account_info()

        timezone_name = str(account.get("timezone_name") or "Europe/Paris")
        try:
            account_tz = ZoneInfo(timezone_name)
        except Exception:
            account_tz = ZoneInfo("Europe/Paris")

        account_now = datetime.now(account_tz)
        data_through = account_now.date() - timedelta(days=1)
        week_start, week_end = friday_thursday_bounds(data_through)

        print("")
        print("PreSubs daily Meta update")
        print("-------------------------")
        print(f"Account timezone: {timezone_name}")
        print(f"Data through: {data_through}")
        print(f"Dashboard week: {week_start} to {week_end}")
        print("Campaign rule: contains PRESUBS")
        print("Excluded: QUIZ in campaign, ad set or ad name")
        print("Result: exact Pixel CompleteRegistration only")
        print("")

        prepare_git()

        metadata = metadata_maps(
            client,
            config.campaign_filter,
            config.exclude_name_terms,
        )
        start_text = week_start.isoformat()
        data_text = data_through.isoformat()

        print("Downloading current Friday-to-yesterday data...")
        weekly_campaigns = resilient_insights(
            client,
            metadata,
            level="campaign",
            start=start_text,
            end=data_text,
        )
        weekly_adsets = resilient_insights(
            client,
            metadata,
            level="adset",
            start=start_text,
            end=data_text,
        )
        weekly_ads = resilient_insights(
            client,
            metadata,
            level="ad",
            start=start_text,
            end=data_text,
        )
        daily_ads = resilient_insights(
            client,
            metadata,
            level="ad",
            start=start_text,
            end=data_text,
            daily=True,
        )

        raw_payload = {
            "account": account,
            "mode": "daily_refresh",
            "data_through": data_text,
            "dashboard_week": {
                "start": week_start.isoformat(),
                "end": week_end.isoformat(),
            },
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
            account_info=account,
        )
        if frames["campaigns"].empty:
            raise AutomationError(
                "No PRESUBS delivery was returned for the current reporting week."
            )

        qa = qa_report(frames)
        export_folder = save_exports(
            start=start_text,
            end=data_text,
            frames=frames,
            raw_payload=raw_payload,
            qa=qa,
        )
        imported = import_fixed_week(
            week_start=week_start.isoformat(),
            week_end=week_end.isoformat(),
            frames=frames,
        )

        print(
            "Imported: "
            f"{len(frames['campaigns'])} campaigns, "
            f"{len(frames['adsets'])} ad sets, "
            f"{len(frames['ads'])} ads, "
            f"{len(frames['daily_ads'])} daily rows"
        )
        print(f"Audit folder: {export_folder}")
        print(f"Week ID: {imported['week_id']}")

        print("Syncing CRM leads and sales...")
        crm_sync_status = "ok"
        try:
            sync_crm()
        except Exception as crm_error:
            crm_sync_status = f"skipped: {crm_error}"
            print(f"WARNING: CRM sync skipped ({crm_error})", file=sys.stderr)

        print("Syncing GA4 site traffic...")
        ga4_sync_status = "ok"
        try:
            sync_ga4()
        except Exception as ga4_error:
            ga4_sync_status = f"skipped: {ga4_error}"
            print(f"WARNING: GA4 sync skipped ({ga4_error})", file=sys.stderr)

        print("Syncing Search Console data...")
        gsc_sync_status = "ok"
        try:
            sync_gsc()
        except Exception as gsc_error:
            gsc_sync_status = f"skipped: {gsc_error}"
            print(f"WARNING: Search Console sync skipped ({gsc_error})", file=sys.stderr)

        print("Syncing Google Ads data...")
        google_ads_sync_status = "ok"
        try:
            sync_google_ads()
        except Exception as google_ads_error:
            google_ads_sync_status = f"skipped: {google_ads_error}"
            print(f"WARNING: Google Ads sync skipped ({google_ads_error})", file=sys.stderr)

        print("Syncing YouTube channel stats...")
        youtube_sync_status = "ok"
        try:
            sync_youtube()
        except Exception as youtube_error:
            youtube_sync_status = f"skipped: {youtube_error}"
            print(f"WARNING: YouTube sync skipped ({youtube_error})", file=sys.stderr)

        print("Syncing YouTube Analytics breakdowns...")
        youtube_analytics_sync_status = "ok"
        try:
            sync_youtube_analytics()
        except Exception as youtube_analytics_error:
            youtube_analytics_sync_status = f"skipped: {youtube_analytics_error}"
            print(f"WARNING: YouTube Analytics sync skipped ({youtube_analytics_error})", file=sys.stderr)

        print("Syncing GoHighLevel data...")
        ghl_sync_status = "ok"
        try:
            sync_ghl()
        except Exception as ghl_error:
            ghl_sync_status = f"skipped: {ghl_error}"
            print(f"WARNING: GoHighLevel sync skipped ({ghl_error})", file=sys.stderr)

        print("Syncing Meta organic (Facebook/Instagram) growth...")
        meta_organic_sync_status = "ok"
        try:
            sync_meta_organic()
        except Exception as meta_organic_error:
            meta_organic_sync_status = f"skipped: {meta_organic_error}"
            print(f"WARNING: Meta organic sync skipped ({meta_organic_error})", file=sys.stderr)

        print("Syncing Video Funnel (Corredor Polones) campaigns...")
        video_funnel_sync_status = "ok"
        try:
            sync_video_funnel()
        except Exception as video_funnel_error:
            video_funnel_sync_status = f"skipped: {video_funnel_error}"
            print(f"WARNING: Video funnel sync skipped ({video_funnel_error})", file=sys.stderr)

        weekly_review_status = "not the call day"
        try:
            generate_weekly_review()
            weekly_review_status = "ok"
        except Exception as weekly_review_error:
            weekly_review_status = f"skipped: {weekly_review_error}"
            print(f"WARNING: Weekly review generation skipped ({weekly_review_error})", file=sys.stderr)

        print("Generating the GitHub Pages site...")
        if generate_public_site() != 0:
            raise AutomationError("The public site generator failed.")

        result = publish_docs(
            f"Daily dashboard update through {data_text}"
        )

        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_path = LOGS_DIR / (
            "daily_sync_"
            + datetime.now().strftime("%Y%m%d_%H%M%S")
            + ".json"
        )
        log_path.write_text(
            json.dumps(
                {
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                    "data_through": data_text,
                    "week_start": week_start.isoformat(),
                    "week_end": week_end.isoformat(),
                    "timezone": timezone_name,
                    "rows": {
                        name: len(frame) for name, frame in frames.items()
                    },
                    "qa_warnings": len(qa.get("warnings", [])),
                    "crm_sync": crm_sync_status,
                    "ga4_sync": ga4_sync_status,
                    "gsc_sync": gsc_sync_status,
                    "google_ads_sync": google_ads_sync_status,
                    "youtube_sync": youtube_sync_status,
                    "youtube_analytics_sync": youtube_analytics_sync_status,
                    "ghl_sync": ghl_sync_status,
                    "meta_organic_sync": meta_organic_sync_status,
                    "video_funnel_sync": video_funnel_sync_status,
                    "weekly_review": weekly_review_status,
                    "git": result,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print("")
        print("Daily automation completed successfully.")
        print(f"Published through {data_text}.")
        return 0
    except Exception as exc:
        print("")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
