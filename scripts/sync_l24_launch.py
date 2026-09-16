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
from scripts.sync_crm import _connect as connect_crm_mysql  # noqa: E402

LOOKBACK_DAYS = 90
CAMPAIGN_NAME_PATTERN = "L24 -"

# CRM ground truth for this launch's leads is the launch17db.leads_l21
# MySQL table (legacy name, reused across L21/L22/L23/L24 - it's not
# per-launch, just the raw landing-page capture table), confirmed with
# the sibling "L24 criativos Meta Ads" session on 2026-09-16. No tag or
# campaign filter needed - the table itself only holds captures from
# this launch's pages, just a date floor at launch start.
#
# An earlier version of this filtered GHL "Commercial Pipeline"
# opportunities by a [L21]/[L24] source tag instead - that was reading
# a completely different, much-later funnel stage (booking/sales
# pipeline, not raw capture) and undercounted leads by ~2 orders of
# magnitude (2-5 vs the ~1,450 that actually landed on the page). Left
# as a cautionary note, not code: don't reintroduce a GHL-opportunities
# based lead count here.
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


def fetch_ad_creative_info(env: dict[str, str], ad_id: str) -> dict:
    """Thumbnail image (works for both image and video ads - video ads
    return a poster frame) and a shareable preview link (renders the real
    ad, video included, no login needed) - so the review deck and any
    dashboard row that cites an ad can link straight to it instead of
    just naming it."""
    import requests

    token = env["META_ACCESS_TOKEN"]
    version = env.get("META_API_VERSION", "v25.0")
    url = f"https://graph.facebook.com/{version}/{ad_id}"
    params = {
        "access_token": token,
        "fields": "creative{thumbnail_url},preview_shareable_link",
    }
    response = requests.get(url, params=params, timeout=30)
    payload = response.json()
    if not response.ok:
        return {"creative_image_url": None, "preview_url": None}
    return {
        "creative_image_url": (payload.get("creative") or {}).get("thumbnail_url"),
        "preview_url": payload.get("preview_shareable_link"),
    }


def fetch_ad_performance(env: dict[str, str], campaign_id: str) -> list[dict]:
    """Ad-level lifetime performance for one campaign - used for the
    best/worst creative breakdown in the L24 review slide. Ad-level
    insights don't hit the time_increment pagination issue since there's
    no per-day breakdown requested here (one row per ad, lifetime)."""
    import requests

    token = env["META_ACCESS_TOKEN"]
    version = env.get("META_API_VERSION", "v25.0")
    url = f"https://graph.facebook.com/{version}/{campaign_id}/insights"
    since = (date.today() - timedelta(days=LOOKBACK_DAYS)).isoformat()
    until = (date.today() + timedelta(days=1)).isoformat()
    params = {
        "access_token": token,
        "level": "ad",
        "fields": "ad_id,ad_name,adset_name,spend,clicks,impressions,ctr,actions",
        "time_range": json.dumps({"since": since, "until": until}),
        "limit": 100,
    }
    rows: list[dict] = []
    while url:
        response = requests.get(url, params=params, timeout=30)
        payload = response.json()
        if not response.ok:
            raise L24SyncError(f"Meta ad-level insights error ({response.status_code}): {payload}")
        for row in payload.get("data") or []:
            leads = _action_value(row, "lead", "offsite_conversion.fb_pixel_lead")
            spend = float(row.get("spend") or 0)
            creative_info = fetch_ad_creative_info(env, row.get("ad_id"))
            rows.append(
                {
                    "ad_id": row.get("ad_id"),
                    "ad_name": row.get("ad_name"),
                    "adset_name": row.get("adset_name"),
                    "spend": spend,
                    "impressions": int(row.get("impressions") or 0),
                    "clicks": int(row.get("clicks") or 0),
                    "ctr": float(row.get("ctr") or 0),
                    "leads": leads,
                    "cpl": round(spend / leads, 2) if leads else None,
                    "creative_image_url": creative_info["creative_image_url"],
                    "preview_url": creative_info["preview_url"],
                }
            )
        next_page = (payload.get("paging") or {}).get("next")
        url, params = (next_page, None) if next_page else (None, None)
    return rows


def store_ad_performance(rows: list[dict]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM l24_ad_performance")
        con.executemany(
            """
            INSERT INTO l24_ad_performance
                (ad_id, ad_name, adset_name, spend, impressions, clicks, ctr, leads, cpl,
                 creative_image_url, preview_url, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                (
                    r["ad_id"], r["ad_name"], r["adset_name"], r["spend"], r["impressions"],
                    r["clicks"], r["ctr"], r["leads"], r["cpl"],
                    r.get("creative_image_url"), r.get("preview_url"),
                )
                for r in rows
            ],
        )


def fetch_crm_leads(env: dict[str, str]) -> list[tuple[str, int]]:
    """Daily lead counts straight from launch17db.leads_l21 - see the
    module-level note on why this isn't a GHL opportunities query."""
    connection = connect_crm_mysql(env)
    try:
        cursor = connection.cursor()
        cursor.execute(
            "SELECT data AS report_date, COUNT(*) AS lead_count "
            "FROM launch17db.leads_l21 "
            "WHERE data IS NOT NULL AND data <> '0000-00-00' AND data >= %s "
            "GROUP BY data ORDER BY data",
            (CRM_LAUNCH_START,),
        )
        return [(str(row[0]), int(row[1])) for row in cursor.fetchall()]
    finally:
        connection.close()


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
        key for key in (
            "META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID",
            "CRM_MYSQL_HOST", "CRM_MYSQL_DATABASE", "CRM_MYSQL_USER", "CRM_MYSQL_PASSWORD",
        )
        if not env.get(key)
    ]
    if missing:
        raise L24SyncError("Missing in .env: " + ", ".join(missing))

    campaigns = discover_campaigns(env)
    if not campaigns:
        print("L24 sync: no 'L24 -' campaigns found - nothing to do.")
        return 0

    total_rows = 0
    all_cold_ad_rows: list[dict] = []
    for campaign in campaigns:
        group = group_from_name(campaign["name"])
        daily = fetch_daily(env, campaign["id"])
        store_daily(group, campaign["id"], campaign["name"], daily)
        total_rows += len(daily)

        if group == "cold":
            # Accumulate across ALL cold campaigns before writing - there
            # can be more than one (e.g. "COLD PF - General" and "COLD -
            # BEST SELLERS" running at once). store_ad_performance() does
            # a full DELETE+INSERT, so calling it per-campaign inside this
            # loop would wipe out the previous cold campaign's ads on
            # every iteration but the last.
            all_cold_ad_rows.extend(fetch_ad_performance(env, campaign["id"]))

    if all_cold_ad_rows:
        store_ad_performance(all_cold_ad_rows)
    ad_rows_count = len(all_cold_ad_rows)

    crm_leads = fetch_crm_leads(env)
    store_crm_leads(crm_leads)

    print(
        f"L24 sync complete: {len(campaigns)} campaigns "
        f"({', '.join(c['name'] for c in campaigns)}), {total_rows} Meta daily rows, "
        f"{ad_rows_count} ad-level rows, "
        f"{sum(count for _, count in crm_leads)} CRM leads (launch17db.leads_l21 since {CRM_LAUNCH_START})."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
