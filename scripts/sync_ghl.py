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

import re
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


CAMPAIGN_SOURCE_PATTERN = re.compile(r"^\s*\[l\s*(\d+)\]\s*-?\s*(.*)$", re.IGNORECASE)


def extract_campaign(source: str | None) -> str | None:
    """PreSubs capture-page sources look like "[L22] - Capture Lead Semaine
    l'anglais - PAGE WHITE" - the same [LP-...] tagging convention already
    used on the Meta side. Sources that don't match (other Peasy Anglais
    products sharing this pipeline/location, e.g. "Peasy Academy - RRPREIND")
    return None and are excluded from the campaign breakdown rather than
    silently miscounted as PreSubs."""
    if not source:
        return None
    match = CAMPAIGN_SOURCE_PATTERN.match(source)
    if not match:
        return None
    return f"L{match.group(1)}"


SALE_STAGE_PATTERN = re.compile(r"sale", re.IGNORECASE)
SALE_STAGE_EXCLUDE_PATTERN = re.compile(r"park|process|meeting", re.IGNORECASE)


def is_sale_stage(name: str) -> bool:
    """A stage counts as a closed sale only if its name contains "sale"
    and isn't a mid-funnel holding stage ("...En Process", "Park...
    (Meeting + Sales)"). The old bare "sale|confirmed" regex also matched
    the generic "Confirmed" stage (appointment-confirmed, not a sale) and
    two "Park" stages - together over 10k opportunities, turning the
    per-contact attribution lookup into an hours-long sequential API
    crawl. Revenue/CAC/ROAS on the dashboard still come from the CRM
    MySQL sales table, not this heuristic - this only drives the
    supplementary "revenue by campaign" breakdown."""
    return bool(SALE_STAGE_PATTERN.search(name)) and not SALE_STAGE_EXCLUDE_PATTERN.search(name)


def fetch_sale_opportunities(env: dict[str, str], stages: dict[str, str]) -> list[dict]:
    """Every opportunity currently sitting in a "sale"-looking stage
    (contains "sale" or "confirmed"), with its monetaryValue - not
    windowed by LOOKBACK_DAYS, since a sale can close long after the lead
    was created and we want the full current snapshot for revenue
    attribution."""
    import requests

    headers = _headers(env)
    sale_stage_ids = [stage_id for stage_id, name in stages.items() if is_sale_stage(name)]
    results: list[dict] = []
    for stage_id in sale_stage_ids:
        params = {
            "location_id": env["GHL_LOCATION_ID"],
            "pipeline_id": env["GHL_PIPELINE_ID"],
            "pipeline_stage_id": stage_id,
            "limit": 100,
        }
        while True:
            response = requests.get(f"{API_BASE}/opportunities/search", headers=headers, params=params, timeout=20)
            payload = response.json()
            if not response.ok:
                raise GhlSyncError(f"GHL sale opportunities error ({response.status_code}): {payload}")
            batch = payload.get("opportunities") or []
            if not batch:
                break
            for opp in batch:
                results.append({"contact_id": opp.get("contactId"), "monetary_value": opp.get("monetaryValue") or 0})
            meta = payload.get("meta") or {}
            start_after, start_after_id = meta.get("startAfter"), meta.get("startAfterId")
            if not start_after or not start_after_id:
                break
            params["startAfter"] = start_after
            params["startAfterId"] = start_after_id
    return results


def fetch_contact_attribution(env: dict[str, str], contact_id: str) -> dict[str, str | None]:
    """The stable, first-touch UTM data for a contact - unlike
    opportunity/contact "source" (last-touch, overwritten every time the
    contact interacts with something new), attributionSource is set once
    and never changes. Only utm_source/utm_campaign/utm_content are kept -
    no name, email, phone or IP from the payload."""
    import requests

    response = requests.get(
        f"{API_BASE}/contacts/{contact_id}", headers=_headers(env), timeout=20
    )
    payload = response.json()
    if not response.ok:
        return {"utm_source": None, "utm_campaign": None, "utm_content": None}
    attribution = (payload.get("contact") or {}).get("attributionSource") or {}
    return {
        "utm_source": attribution.get("utmSource"),
        "utm_campaign": attribution.get("campaign"),
        "utm_content": attribution.get("utmContent"),
    }


def aggregate_sales_attribution(env: dict[str, str], sale_opportunities: list[dict]) -> list[tuple]:
    """(utm_campaign, utm_source, utm_content, sale_count, revenue) - one
    contacts/{id} call per opportunity currently in a sale-looking stage
    (a few dozen, not the full lead volume) to get the stable first-touch
    attribution."""
    totals: dict[tuple[str, str, str], dict[str, float]] = {}
    for opp in sale_opportunities:
        contact_id = opp.get("contact_id")
        if not contact_id:
            continue
        attribution = fetch_contact_attribution(env, contact_id)
        campaign = attribution["utm_campaign"] or "(unknown)"
        source = attribution["utm_source"] or "(unknown)"
        content = attribution["utm_content"] or "(unknown)"
        key = (campaign, source, content)
        bucket = totals.setdefault(key, {"count": 0, "revenue": 0.0})
        bucket["count"] += 1
        bucket["revenue"] += float(opp.get("monetary_value") or 0)

    return [
        (campaign, source, content, int(data["count"]), data["revenue"])
        for (campaign, source, content), data in sorted(
            totals.items(), key=lambda item: item[1]["revenue"], reverse=True
        )
    ]


def fetch_opportunities_in_window(env: dict[str, str]) -> list[dict]:
    """Paginate opportunities in the PreSubs pipeline, newest first, and
    stop once past the lookback window - much cheaper than scanning all
    35k+ historical opportunities on every sync. Returns id/source/
    contactId/stage/createdAt only - no contact name, email or phone."""
    import requests

    cutoff = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)
    results: list[dict] = []
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
            results.append(
                {
                    "created_at": created,
                    "source": opp.get("source"),
                    "contact_id": opp.get("contactId"),
                    "pipeline_stage_id": opp.get("pipelineStageId"),
                }
            )

        if stop:
            break

        meta = payload.get("meta") or {}
        start_after = meta.get("startAfter")
        start_after_id = meta.get("startAfterId")
        if not start_after or not start_after_id:
            break
        params["startAfter"] = start_after
        params["startAfterId"] = start_after_id

    return results


def leads_by_day(opportunities: list[dict]) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for opp in opportunities:
        report_date = opp["created_at"].date().isoformat()
        counts[report_date] = counts.get(report_date, 0) + 1
    return sorted(counts.items())


def contact_status_map(events: list[dict]) -> dict[str, str]:
    """contactId -> most recent appointmentStatus, from active-calendar
    events only. Never keeps the contact name/title from the event."""
    latest: dict[str, tuple[datetime, str]] = {}
    for event in events:
        contact_id = event.get("contactId")
        start_time = event.get("startTime")
        status = event.get("appointmentStatus")
        if not contact_id or not start_time or not status:
            continue
        try:
            when = datetime.fromisoformat(start_time)
        except ValueError:
            continue
        if contact_id not in latest or when > latest[contact_id][0]:
            latest[contact_id] = (when, status)
    return {contact_id: status for contact_id, (_, status) in latest.items()}


def aggregate_campaign_funnel(
    opportunities: list[dict], stages: dict[str, str], statuses_by_contact: dict[str, str]
) -> list[tuple[str, int, int, int, int, int]]:
    """(campaign, leads, booked, cancelled, showed, sales) per PreSubs
    capture-page campaign code. "Sale" is a heuristic: current stage name
    contains "sale" or "confirmed" (e.g. Regular Sale, CPF Sale, Confirmed,
    Sale Direct Link) - flagged as a heuristic, not a guaranteed-correct
    revenue source (the CRM MySQL sales table remains the trusted revenue
    figure elsewhere in the dashboard)."""
    totals: dict[str, dict[str, int]] = {}
    for opp in opportunities:
        campaign = extract_campaign(opp.get("source"))
        if not campaign:
            continue
        bucket = totals.setdefault(campaign, {"leads": 0, "booked": 0, "cancelled": 0, "showed": 0, "sales": 0})
        bucket["leads"] += 1

        status = statuses_by_contact.get(opp.get("contact_id") or "")
        if status:
            bucket["booked"] += 1
            if status == "cancelled":
                bucket["cancelled"] += 1
            elif status == "showed":
                bucket["showed"] += 1

        stage_name = stages.get(opp.get("pipeline_stage_id") or "", "")
        if is_sale_stage(stage_name):
            bucket["sales"] += 1

    return [
        (campaign, data["leads"], data["booked"], data["cancelled"], data["showed"], data["sales"])
        for campaign, data in sorted(totals.items(), key=lambda item: item[1]["leads"], reverse=True)
    ]


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
    """A handful of these 71 sequential calls intermittently come back as a
    transient "Command timed out" (GHL rate-limiting the burst) - retried a
    few times with a short backoff before giving up on that one calendar."""
    import time

    import requests

    last_error: Exception | None = None
    for attempt in range(4):
        if attempt:
            time.sleep(1.5 * attempt)
        try:
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
        except requests.RequestException as error:
            last_error = error
            continue
        payload = response.json()
        if response.ok:
            return payload.get("events") or []
        if "timed out" in str(payload.get("message", "")).lower():
            last_error = GhlSyncError(f"GHL calendar events error ({response.status_code}): {payload}")
            continue
        raise GhlSyncError(f"GHL calendar events error ({response.status_code}): {payload}")

    raise GhlSyncError(f"GHL calendar events error for {calendar_id} after retries: {last_error}")


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
    """(report_date, appointment_status, count) - grouped by the meeting's
    own startTime day, since attendance (showed/cancelled/noshow) is only
    knowable on the day of the meeting itself. Only the status and date
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


def aggregate_bookings_by_day(events: list[dict]) -> list[tuple[str, int]]:
    """(report_date, count) - grouped by dateAdded, the day the person
    actually booked the meeting, not the day of the meeting itself
    (startTime). This keeps "Bookings" on the same creation-day basis as
    "Leads", so Lead -> Booking is a same-day-cohort rate instead of
    mixing a lead-creation-day count against a meeting-occurrence-day
    count (falls back to startTime if dateAdded is missing)."""
    counts: dict[str, int] = {}
    for event in events:
        booked_at = event.get("dateAdded") or event.get("startTime")
        if not booked_at:
            continue
        report_date = booked_at[:10]
        counts[report_date] = counts.get(report_date, 0) + 1
    return sorted(counts.items())


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


def store_bookings_daily(rows: list[tuple[str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM ghl_bookings_daily")
        con.executemany(
            "INSERT INTO ghl_bookings_daily (report_date, count, synced_at) "
            "VALUES (?, ?, CURRENT_TIMESTAMP)",
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


def store_sales_attribution(rows: list[tuple]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM ghl_sales_attribution")
        con.executemany(
            "INSERT INTO ghl_sales_attribution "
            "(utm_campaign, utm_source, utm_content, sale_count, revenue, synced_at) "
            "VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_campaign_funnel(rows: list[tuple[str, int, int, int, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM ghl_campaign_funnel")
        con.executemany(
            "INSERT INTO ghl_campaign_funnel "
            "(campaign, leads, booked, cancelled, showed, sales, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
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
    opportunities = fetch_opportunities_in_window(env)
    leads_daily = leads_by_day(opportunities)
    stage_counts = fetch_stage_counts(env, stages)

    store_leads_daily(leads_daily)
    store_stage_counts(stage_counts)

    all_calendars = fetch_all_calendars(env)
    calendar_rows, active_events = discover_calendars_and_events(env, all_calendars)
    appointment_rows = aggregate_appointments(active_events)
    booking_rows = aggregate_bookings_by_day(active_events)

    store_calendars(calendar_rows)
    store_appointments(appointment_rows)
    store_bookings_daily(booking_rows)

    statuses_by_contact = contact_status_map(active_events)
    campaign_funnel = aggregate_campaign_funnel(opportunities, stages, statuses_by_contact)
    store_campaign_funnel(campaign_funnel)

    sale_opportunities = fetch_sale_opportunities(env, stages)
    sales_attribution = aggregate_sales_attribution(env, sale_opportunities)
    store_sales_attribution(sales_attribution)

    active_count = sum(1 for row in calendar_rows if row[2])
    print(
        f"GoHighLevel sync complete: {len(leads_daily)} lead-days, "
        f"{len(stage_counts)} pipeline stages, "
        f"{active_count}/{len(calendar_rows)} active calendars, "
        f"{len(appointment_rows)} appointment status-day rows, "
        f"{len(campaign_funnel)} campaigns tracked, "
        f"{len(sale_opportunities)} sales attributed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
