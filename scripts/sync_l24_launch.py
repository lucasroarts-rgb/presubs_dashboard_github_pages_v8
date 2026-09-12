"""Sync the L24 launch campaigns from Meta Ads.

Separate from the main PreSubs sync (scoped to campaigns named "PRESUBS")
and from the Video Funnel sync (scoped to "CP_P#" campaigns) - this one
is scoped to campaigns whose name starts with "L24 -", in the same ad
account. Kept in its own tables so it never mixes into the PreSubs
totals, same rationale as sync_video_funnel.py.

Campaign structure (all in the same ad account, confirmed 2026-09-11):
  L24 - CPL - CONVERSION - COLD PF - General   - cold prospecting, live
  L24 - CPL - CONVERSION - HOT - IG e FB       - remarketing, starts 2026-09-28
  L24 - SALES - CONVERSION - HOT               - sales retargeting, out of scope for now

Discovery is by name, not hardcoded campaign IDs, so a renamed or added
campaign is picked up automatically on the next sync.
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402
from scripts.sync_ghl import extract_campaign, fetch_opportunities_in_window  # noqa: E402

LOOKBACK_DAYS = 90
CAMPAIGN_NAME_PATTERN = "L24 -"

# The Meta side of this launch is tagged "L24", but the CRM capture-page
# tag for it is "[L21]" (confirmed with the user 2026-09-11 - L-numbers
# get reused across launches on the CRM side, so this is NOT the same
# thing as any earlier L21 launch). Leads before this date belong to
# whatever that earlier L21 was, not this launch, so they're excluded.
CRM_CAMPAIGN_TAG = "L21"
CRM_LAUNCH_START = "2026-09-11"


class L24SyncError(RuntimeError):
    pass


def _action_value(row: dict, *action_types: str) -> int:
    for item in row.get("actions") or []:
        if item.get("action_type") in action_types:
            return int(float(item.get("value") or 0))
    return 0


def discover_campaigns(env: dict[str, str]) -> list[dict[str, str]]:
    import requests

    token = env["META_ACCESS_TOKEN"]
    account = env["META_AD_ACCOUNT_ID"]
    version = env.get("META_API_VERSION", "v25.0")
    campaigns: list[dict[str, str]] = []
    url = f"https://graph.facebook.com/{version}/{account}/campaigns"
    params = {"access_token": token, "fields": "id,name,status", "limit": 500}
    while url:
        response = requests.get(url, params=params, timeout=30)
        payload = response.json()
        if not response.ok:
            raise L24SyncError(f"Meta campaigns error ({response.status_code}): {payload}")
        for row in payload.get("data") or []:
            if row["name"].startswith(CAMPAIGN_NAME_PATTERN):
                campaigns.append({"id": row["id"], "name": row["name"], "status": row.get("status", "")})
        next_page = (payload.get("paging") or {}).get("next")
        url, params = (next_page, None) if next_page else (None, None)
    return campaigns


def group_from_name(name: str) -> str:
    upper = name.upper()
    if "SALES" in upper:
        return "sales"
    if "HOT" in upper:
        return "hot"
    if "COLD" in upper:
        return "cold"
    return "other"


def _paginate_insights(env: dict[str, str], campaign_id: str) -> list[dict]:
    """Same pagination-safety fix as sync_video_funnel.py: time_increment=1
    responses cap at a page size regardless of the requested window.

    Uses an explicit time_range instead of date_preset=last_Nd: this ad
    account's timezone runs ahead of the sync machine's clock, so on the
    campaign's first live day date_preset=last_90d excluded that
    still-"in progress" day entirely and returned zero rows, while an
    explicit since/until through today included it correctly."""
    import requests

    token = env["META_ACCESS_TOKEN"]
    version = env.get("META_API_VERSION", "v25.0")
    url = f"https://graph.facebook.com/{version}/{campaign_id}/insights"
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (date.today() + timedelta(days=1)).isoformat()
    params = {
        "access_token": token,
        "fields": "impressions,spend,actions",
        "time_increment": 1,
        "time_range": json.dumps({"since": since, "until": until}),
        "limit": 100,
    }
    rows: list[dict] = []
    while url:
        response = requests.get(url, params=params, timeout=30)
        payload = response.json()
        if not response.ok:
            raise L24SyncError(f"Meta insights error ({response.status_code}): {payload}")
        rows.extend(payload.get("data") or [])
        next_page = (payload.get("paging") or {}).get("next")
        url, params = (next_page, None) if next_page else (None, None)
    return rows


def fetch_daily(env: dict[str, str], campaign_id: str) -> list[dict]:
    raw_rows = _paginate_insights(env, campaign_id)
    rows = []
    for row in raw_rows:
        rows.append(
            {
                "report_date": row["date_start"],
                "impressions": int(row.get("impressions") or 0),
                "spend": float(row.get("spend") or 0),
                "clicks": _action_value(row, "link_click"),
                "landing_page_views": _action_value(row, "landing_page_view"),
                "leads": _action_value(row, "lead", "offsite_conversion.fb_pixel_lead"),
            }
        )
    return rows


def store_daily(group: str, campaign_id: str, campaign_name: str, rows: list[dict]) -> None:
    with dashboard_app.db() as con:
        con.execute(
            "DELETE FROM l24_daily WHERE campaign_id = ?",
            (campaign_id,),
        )
        con.executemany(
            """
            INSERT INTO l24_daily
                (group_name, campaign_id, campaign_name, report_date, impressions, spend, clicks, landing_page_views, leads, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                (
                    group, campaign_id, campaign_name, row["report_date"], row["impressions"],
                    row["spend"], row["clicks"], row["landing_page_views"], row["leads"],
                )
                for row in rows
            ],
        )


def fetch_crm_leads(env: dict[str, str]) -> list[tuple[str, int]]:
    """Daily lead counts from GHL opportunities tagged [L21], created on
    or after CRM_LAUNCH_START - the real ground-truth CRM count for this
    launch, comparable against Meta's own pixel-reported leads the same
    way the rest of the dashboard compares CRM vs Meta."""
    opportunities = fetch_opportunities_in_window(env)
    start = date.fromisoformat(CRM_LAUNCH_START)
    counts: dict[str, int] = {}
    for opp in opportunities:
        if extract_campaign(opp.get("source")) != CRM_CAMPAIGN_TAG:
            continue
        created_at = opp.get("created_at")
        if not created_at or created_at.date() < start:
            continue
        report_date = created_at.date().isoformat()
        counts[report_date] = counts.get(report_date, 0) + 1
    return sorted(counts.items())


def store_crm_leads(rows: list[tuple[str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM l24_crm_daily")
        con.executemany(
            "INSERT INTO l24_crm_daily (report_date, leads, synced_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    missing = [
        key for key in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID", "GHL_API_KEY", "GHL_LOCATION_ID", "GHL_PIPELINE_ID")
        if not env.get(key)
    ]
    if missing:
        raise L24SyncError("Missing in .env: " + ", ".join(missing))

    campaigns = discover_campaigns(env)
    if not campaigns:
        print("L24 sync: no 'L24 -' campaigns found - nothing to do.")
        return 0

    total_rows = 0
    for campaign in campaigns:
        group = group_from_name(campaign["name"])
        daily = fetch_daily(env, campaign["id"])
        store_daily(group, campaign["id"], campaign["name"], daily)
        total_rows += len(daily)

    crm_leads = fetch_crm_leads(env)
    store_crm_leads(crm_leads)

    print(
        f"L24 sync complete: {len(campaigns)} campaigns "
        f"({', '.join(c['name'] for c in campaigns)}), {total_rows} Meta daily rows, "
        f"{sum(count for _, count in crm_leads)} CRM leads ([{CRM_CAMPAIGN_TAG}] since {CRM_LAUNCH_START})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
