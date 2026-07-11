from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.automate_meta import (  # noqa: E402
    AutomationError,
    MetaClient,
    MetaConfig,
    build_frames,
    generate_public_site,
    import_into_database,
    load_env_file,
    metadata_maps,
    publish_to_github,
    qa_report,
    resilient_insights,
    save_exports,
    verify_github_pages,
)

STATE_DIR = ROOT / "logs"
BACKUP_DIR = ROOT / "backups"
DB_PATH = ROOT / "data" / "presubs.db"


def first_friday_on_or_after(value: date) -> date:
    days_until_friday = (4 - value.weekday()) % 7
    return value + timedelta(days=days_until_friday)


def last_completed_thursday(today: date | None = None) -> date:
    current = today or date.today()
    days_since_thursday = (current.weekday() - 3) % 7
    if days_since_thursday == 0:
        days_since_thursday = 7
    return current - timedelta(days=days_since_thursday)


def weekly_periods(start: date, end: date) -> list[tuple[date, date]]:
    normalized_start = first_friday_on_or_after(start)
    if normalized_start > end:
        return []

    periods: list[tuple[date, date]] = []
    current = normalized_start
    while current + timedelta(days=6) <= end:
        periods.append((current, current + timedelta(days=6)))
        current += timedelta(days=7)
    return periods


def load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"completed": {}, "skipped": {}, "failed": {}}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {"completed": {}, "skipped": {}, "failed": {}}
    payload.setdefault("completed", {})
    payload.setdefault("skipped", {})
    payload.setdefault("failed", {})
    return payload


def save_state(path: Path, state: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    path.write_text(
        json.dumps(state, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def backup_database() -> Path | None:
    if not DB_PATH.exists():
        return None
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    destination = BACKUP_DIR / (
        "presubs_before_history_"
        + datetime.now().strftime("%Y%m%d_%H%M%S")
        + ".db"
    )
    shutil.copy2(DB_PATH, destination)
    return destination


def period_key(start: date, end: date) -> str:
    return f"{start.isoformat()}__{end.isoformat()}"


def download_import_period(
    *,
    client: MetaClient,
    config: MetaConfig,
    account_info: dict[str, Any],
    metadata: dict[str, Any],
    start: date,
    end: date,
) -> dict[str, Any]:
    start_text = start.isoformat()
    end_text = end.isoformat()

    weekly_campaigns = resilient_insights(
        client, metadata, level="campaign", start=start_text, end=end_text
    )
    weekly_adsets = resilient_insights(
        client, metadata, level="adset", start=start_text, end=end_text
    )
    weekly_ads = resilient_insights(
        client, metadata, level="ad", start=start_text, end=end_text
    )
    daily_ads = resilient_insights(
        client, metadata, level="ad", start=start_text, end=end_text, daily=True
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

    if frames["campaigns"].empty:
        return {
            "status": "no_data",
            "reason": "No campaign containing PRESUBS had delivery in this period.",
        }

    required = ["adsets", "ads", "daily_ads"]
    missing = [name for name in required if frames[name].empty]
    if missing:
        raise AutomationError(
            "Meta returned campaign data but no matching rows for: "
            + ", ".join(missing)
        )

    qa = qa_report(frames)
    export_folder = save_exports(
        start=start_text,
        end=end_text,
        frames=frames,
        raw_payload=raw_payload,
        qa=qa,
    )
    imported = import_into_database(
        start=start_text,
        end=end_text,
        frames=frames,
    )

    return {
        "status": "completed",
        "period": {"start": start_text, "end": end_text},
        "rows": {name: len(frame) for name, frame in frames.items()},
        "qa_warnings": len(qa.get("warnings", [])),
        "week_id": imported["week_id"],
        "counts": imported["counts"],
        "export_folder": str(export_folder),
    }


def ask_confirmation(periods: list[tuple[date, date]], force: bool) -> bool:
    print("")
    print("Historical Meta import")
    print("----------------------")
    print(f"First period: {periods[0][0]} to {periods[0][1]}")
    print(f"Last period:  {periods[-1][0]} to {periods[-1][1]}")
    print(f"Weekly periods: {len(periods)}")
    print("Campaign rule: name contains PRESUBS")
    print("Excluded: campaign, ad-set or ad names containing QUIZ")
    print("Results: exact Meta Pixel CompleteRegistration only")
    print("GitHub publication: one single push after every week is processed")
    if force:
        print("Mode: force reimport of every period")
    else:
        print("Mode: resume, skipping periods already completed by this importer")
    print("")
    answer = input("Continue? [Y/n]: ").strip().lower()
    return answer not in {"n", "no", "nao", "não"}


def run_backfill(
    *,
    start: date,
    end: date,
    publish: bool,
    wait_pages: bool,
    force: bool,
    yes: bool,
) -> int:
    values = load_env_file()
    config = MetaConfig.from_env(values)

    completed_end = last_completed_thursday()
    effective_end = min(end, completed_end)
    periods = weekly_periods(start, effective_end)
    if not periods:
        raise AutomationError(
            "No complete Friday-to-Thursday period exists inside the selected dates."
        )

    if not yes and not ask_confirmation(periods, force):
        print("Cancelled.")
        return 0

    state_name = (
        f"history_{periods[0][0].isoformat()}__"
        f"{periods[-1][1].isoformat()}_state.json"
    )
    state_path = STATE_DIR / state_name
    state = load_state(state_path)

    backup = backup_database()
    if backup:
        print(f"Database backup: {backup}")

    client = MetaClient(config)
    account_info = client.account_info()
    print(
        f"Connected to {account_info.get('name')} | "
        f"{account_info.get('currency')} | "
        f"{account_info.get('timezone_name')}"
    )
    print("Loading campaign, ad-set and ad metadata once...")
    metadata = metadata_maps(
        client, config.campaign_filter, config.exclude_name_terms
    )

    completed_count = 0
    skipped_count = 0
    no_data_count = 0
    started_at = datetime.now(timezone.utc)

    for index, (period_start, period_end) in enumerate(periods, start=1):
        key = period_key(period_start, period_end)

        if not force and key in state["completed"]:
            skipped_count += 1
            print(
                f"[{index}/{len(periods)}] {period_start} to {period_end}: "
                "already completed, skipped"
            )
            continue

        print("")
        print(
            f"[{index}/{len(periods)}] Importing "
            f"{period_start} to {period_end}..."
        )

        try:
            result = download_import_period(
                client=client,
                config=config,
                account_info=account_info,
                metadata=metadata,
                start=period_start,
                end=period_end,
            )
        except Exception as exc:
            state["failed"][key] = {
                "error": str(exc),
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            save_state(state_path, state)
            raise AutomationError(
                f"History import stopped at {period_start} to {period_end}: {exc}\n"
                "Run the same file again after correcting the problem. "
                "Completed periods will be skipped automatically."
            ) from exc

        if result["status"] == "no_data":
            no_data_count += 1
            state["skipped"][key] = {
                **result,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            state["failed"].pop(key, None)
            print("No PRESUBS delivery in this period. Period skipped.")
        else:
            completed_count += 1
            state["completed"][key] = {
                **result,
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }
            state["failed"].pop(key, None)
            print(
                "Imported: "
                f"{result['rows']['campaigns']} campaigns, "
                f"{result['rows']['adsets']} ad sets, "
                f"{result['rows']['ads']} ads, "
                f"{result['rows']['daily_ads']} daily rows"
            )
            if result["qa_warnings"]:
                print(
                    f"QA warnings: {result['qa_warnings']} "
                    "(details saved in exports)"
                )

        save_state(state_path, state)
        time.sleep(1)

    print("")
    print("Generating the public dashboard once...")
    generator_result = generate_public_site()
    if generator_result != 0:
        raise AutomationError("The public site generator failed.")

    summary_path = ROOT / "docs" / "export-summary.json"
    generated_at = ""
    if summary_path.exists():
        try:
            generated_at = json.loads(
                summary_path.read_text(encoding="utf-8")
            ).get("generated_at", "")
        except ValueError:
            generated_at = ""

    git_result: dict[str, Any] = {
        "changed": False,
        "pushed": False,
        "message": "Publication disabled.",
    }
    if publish:
        print("Publishing all historical periods to GitHub...")
        git_result = publish_to_github(
            periods[0][0].isoformat(), periods[-1][1].isoformat()
        )
        print(git_result["message"])
        if git_result.get("pushed") and wait_pages and generated_at:
            verify_github_pages(config.github_pages_url, generated_at)

    finished_at = datetime.now(timezone.utc)
    final_log = {
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "requested_start": start.isoformat(),
        "effective_first_period": periods[0][0].isoformat(),
        "effective_last_period": periods[-1][1].isoformat(),
        "period_count": len(periods),
        "imported_now": completed_count,
        "already_completed": skipped_count,
        "no_data": no_data_count,
        "force": force,
        "publication": git_result,
        "state_file": str(state_path),
        "backup": str(backup) if backup else None,
    }
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log_path = STATE_DIR / (
        "history_run_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".json"
    )
    log_path.write_text(
        json.dumps(final_log, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("Historical import completed successfully.")
    print(f"Imported in this run: {completed_count}")
    print(f"Previously completed and skipped: {skipped_count}")
    print(f"Periods without PRESUBS delivery: {no_data_count}")
    print(f"State file: {state_path}")
    if publish:
        print("The GitHub Pages site was committed and pushed once at the end.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Import historical PRESUBS data week by week, update SQLite, "
            "generate the static site and publish once."
        )
    )
    parser.add_argument("--year", type=int)
    parser.add_argument("--start", help="YYYY-MM-DD")
    parser.add_argument("--end", help="YYYY-MM-DD")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--yes", action="store_true")
    publish_group = parser.add_mutually_exclusive_group()
    publish_group.add_argument("--publish", action="store_true")
    publish_group.add_argument("--no-publish", action="store_true")
    parser.add_argument("--wait-pages", action="store_true")
    args = parser.parse_args()

    try:
        values = load_env_file()
        config = MetaConfig.from_env(values)

        if args.year and (args.start or args.end):
            raise AutomationError("Use --year or --start/--end, not both.")

        if args.year:
            requested_start = date(args.year, 1, 1)
            requested_end = date(args.year, 12, 31)
        elif args.start or args.end:
            if not args.start:
                raise AutomationError("--start is required when --end is used.")
            requested_start = date.fromisoformat(args.start)
            requested_end = (
                date.fromisoformat(args.end)
                if args.end
                else last_completed_thursday()
            )
        else:
            requested_start = date(date.today().year, 1, 1)
            requested_end = last_completed_thursday()

        if requested_end < requested_start:
            raise AutomationError("The end date cannot be before the start date.")

        publish = (
            True
            if args.publish
            else False
            if args.no_publish
            else config.auto_publish
        )
        wait_pages = args.wait_pages or config.wait_for_pages

        return run_backfill(
            start=requested_start,
            end=requested_end,
            publish=publish,
            wait_pages=wait_pages,
            force=args.force,
            yes=args.yes,
        )
    except (AutomationError, ValueError) as exc:
        print("")
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
