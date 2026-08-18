"""Pull PreSubs funnel data from GoHighLevel (internally called "Twilead")
into local SQLite: new leads per day and current opportunity counts per
pipeline stage.

Scope: the entire "Commercial Pipeline" pipeline in this GoHighLevel
location IS the PreSubs funnel (confirmed with the user 2026-08-17) - other
Peasy Anglais products use other pipelines/calendars in the same location,
so no additional campaign/tag filter is applied.

Only aggregated day-level and stage-level counts are stored - no contact
name, email or phone ever leaves the CRM into this database, matching the
project's privacy rule for every other CRM-adjacent integration.

Requires GHL_API_KEY, GHL_LOCATION_ID and GHL_PIPELINE_ID in .env. The API
key is a GoHighLevel "Private Integration" token (Settings > Private
Integrations in the location) with read access to Contacts and
Opportunities - no OAuth flow needed.
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

LOOKBACK_DAYS = 90
CALENDAR_LOOKBACK_DAYS = 60
API_BASE = "https://services.leadconnectorhq.com"
API_VERSION = "2021-07-28"

# Commercial Pipeline stages (id -> name), fetched once and reused - see
# GET /opportunities/pipelines. Stored here since pipeline stage lists
# change rarely and this avoids an extra API call on every sync.
REQUIRED_KEYS = ["GHL_API_KEY", "GHL_LOCATION_ID", "GHL_PIPELINE_ID"]


class GhlSyncError(RuntimeError):
    pass


def _headers(env: dict[str, str]) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {env['GHL_API_KEY']}",
        "Version": API_VERSION,
        "Accept": "application/json",
    }


def fetch_pipeline_stages(env: dict[str, str]) -> dict[str, str]:
    import requests

    response = requests.get(
        f"{API_BASE}/opportunities/pipelines",
        headers=_headers(env),
        params={"locationId": env["GHL_LOCATION_ID"]},
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise GhlSyncError(f"GHL pipelines error ({response.status_code}): {payload}")

    for pipeline in payload.get("pipelines") or []:
        if pipeline.get("id") == env["GHL_PIPELINE_ID"]:
            return {stage["id"]: stage["name"] for stage in pipeline.get("stages") or []}
    raise GhlSyncError(f"Pipeline {env['GHL_PIPELINE_ID']} not found")


def fetch_new_leads_by_day(env: dict[str, str]) -> list[tuple[str, int]]:
    """Paginate opportunities in the PreSubs pipeline, newest first, and
    stop once past the lookback window - much cheaper than scanning all
    35k+ historical opportunities on every sync."""
    import requests

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    counts: dict[str, int] = {}
    params = {
        "location_id": env["GHL_LOCATION_ID"],
        "pipeline_id": env["GHL_PIPELINE_ID"],
        "limit": 100,
    }
    headers = _headers(env)

    while True:
        response = requests.get(f"{API_BASE}/opportunities/search", headers=headers, params=params, timeout=20)
        payload = response.json()
        if not response.ok:
            raise GhlSyncError(f"GHL opportunities error ({response.status_code}): {payload}")

        opportunities = payload.get("opportunities") or []
        if not opportunities:
            break

        stop = False
        for opp in opportunities:
            created_at = opp.get("createdAt")
            if not created_at:
                continue
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if created < cutoff:
                stop = True
                break
            report_date = created.date().isoformat()
            counts[report_date] = counts.get(report_date, 0) + 1

        if stop:
            break

        meta = payload.get("meta") or {}
        start_after = meta.get("startAfter")
        start_after_id = meta.get("startAfterId")
        if not start_after or not start_after_id:
            break
        params["startAfter"] = start_after
        params["startAfterId"] = start_after_id

    return sorted(counts.items())


def fetch_stage_counts(env: dict[str, str], stages: dict[str, str]) -> list[tuple[str, int]]:
    """One lightweight request per stage (reads meta.total only) instead of
    listing every opportunity - cheap even with 30+ stages."""
    import requests

    headers = _headers(env)
    rows: list[tuple[str, int]] = []
    for stage_id, stage_name in stages.items():
        response = requests.get(
            f"{API_BASE}/opportunities/search",
            headers=headers,
            params={
                "location_id": env["GHL_LOCATION_ID"],
                "pipeline_id": env["GHL_PIPELINE_ID"],
                "pipeline_stage_id": stage_id,
                "limit": 1,
            },
            timeout=20,
        )
        payload = response.json()
        if not response.ok:
            raise GhlSyncError(f"GHL stage count error ({response.status_code}): {payload}")
        total = int((payload.get("meta") or {}).get("total") or 0)
        rows.append((stage_name, total))
    return rows


def fetch_all_calendars(env: dict[str, str]) -> list[tuple[str, str]]:
    import requests

    response = requests.get(
        f"{API_BASE}/calendars/",
        headers=_headers(env),
        params={"locationId": env["GHL_LOCATION_ID"]},
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise GhlSyncError(f"GHL calendars error ({response.status_code}): {payload}")
    return [(c["id"], c.get("name") or c["id"]) for c in payload.get("calendars") or []]


def fetch_calendar_events(env: dict[str, str], calendar_id: str, start_ms: int, end_ms: int) -> list[dict]:
    import requests

    response = requests.get(
        f"{API_BASE}/calendars/events",
        headers=_headers(env),
        params={
            "locationId": env["GHL_LOCATION_ID"],
            "calendarId": calendar_id,
            "startTime": start_ms,
            "endTime": end_ms,
        },
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise GhlSyncError(f"GHL calendar events error ({response.status_code}): {payload}")
    return payload.get("events") or []


def discover_calendars_and_events(
    env: dict[str, str], calendars: list[tuple[str, str]]
) -> tuple[list[tuple[str, str, int, int]], list[dict]]:
    """One events call per calendar over the last CALENDAR_LOOKBACK_DAYS days.
    Calendars with zero bookings in that window are marked inactive and
    excluded from the appointment-status aggregation - most of this
    location's 70+ calendars are personal/unused/other-product calendars,
    not PreSubs booking calendars."""
    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(days=CALENDAR_LOOKBACK_DAYS)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    calendar_rows: list[tuple[str, str, int, int]] = []
    active_events: list[dict] = []
    for calendar_id, calendar_name in calendars:
        events = fetch_calendar_events(env, calendar_id, start_ms, end_ms)
        is_active = 1 if events else 0
        calendar_rows.append((calendar_id, calendar_name, is_active, len(events)))
        if is_active:
            active_events.extend(events)
    return calendar_rows, active_events


def aggregate_appointments(events: list[dict]) -> list[tuple[str, str, int]]:
    """(report_date, appointment_status, count) - only the status and date
    of each booking are kept, never the contact name/title in the event."""
    counts: dict[tuple[str, str], int] = {}
    for event in events:
        start_time = event.get("startTime")
        if not start_time:
            continue
        report_date = start_time[:10]
        status = event.get("appointmentStatus") or "unknown"
        key = (report_date, status)
        counts[key] = counts.get(key, 0) + 1
    return [(report_date, status, count) for (report_date, status), count in counts.items()]


def store_calendars(rows: list[tuple[str, str, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM ghl_calendars")
        con.executemany(
            "INSERT INTO ghl_calendars (calendar_id, calendar_name, is_active, event_count, synced_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_appointments(rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM ghl_appointments_daily")
        con.executemany(
            "INSERT INTO ghl_appointments_daily (report_date, status, count, synced_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_leads_daily(rows: list[tuple[str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO ghl_leads_daily (report_date, lead_count, synced_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                lead_count = excluded.lead_count,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def store_stage_counts(rows: list[tuple[str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM ghl_pipeline_stage")
        con.executemany(
            "INSERT INTO ghl_pipeline_stage (stage_name, opportunity_count, synced_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    missing = [key for key in REQUIRED_KEYS if not env.get(key)]
    if missing:
        raise GhlSyncError("Missing in .env: " + ", ".join(missing))

    stages = fetch_pipeline_stages(env)
    leads_daily = fetch_new_leads_by_day(env)
    stage_counts = fetch_stage_counts(env, stages)

    store_leads_daily(leads_daily)
    store_stage_counts(stage_counts)

    all_calendars = fetch_all_calendars(env)
    calendar_rows, active_events = discover_calendars_and_events(env, all_calendars)
    appointment_rows = aggregate_appointments(active_events)

    store_calendars(calendar_rows)
    store_appointments(appointment_rows)

    active_count = sum(1 for row in calendar_rows if row[2])
    print(
        f"GoHighLevel sync complete: {len(leads_daily)} lead-days, "
        f"{len(stage_counts)} pipeline stages, "
        f"{active_count}/{len(calendar_rows)} active calendars, "
        f"{len(appointment_rows)} appointment status-day rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
