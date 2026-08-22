"""Sync the "Corredor Polones" video-view awareness funnel from Meta Ads.

This is a SEPARATE product/campaign from PreSubs (the rest of this
dashboard is scoped to campaigns whose name contains "PRESUBS" - these
are not that). Kept in its own tables/tab so it never mixes into the
PreSubs spend/registration totals.

Campaign naming convention (confirmed with the user against their own
Looker Studio filters):
  CP_P1_VV_FR  - Phase 1 (Unaware), video-view awareness campaign
  CP_P2_VV_FR  - Phase 2 (Problem-Aware), video-view awareness campaign
  CP_P3_VV_FR  - Phase 3 (Solution-Aware), video-view awareness campaign
  CP_P4_CPL_FR - Phase 4, lead-generation/conversion campaign

Phases 1-3 are read via video_p25/p50/p75_watched_actions (VV25/VV50/
VV75 - percentage-of-video-watched gates). Phase 4 is read via the
standard leads/spend/CPL actions, same shape as the main PreSubs sync.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

LOOKBACK_DAYS = 90
CAMPAIGN_NAME_PATTERN = "CP_P"


class VideoFunnelSyncError(RuntimeError):
    pass


def _video_action_value(row: dict, field: str) -> int:
    for item in row.get(field) or []:
        if item.get("action_type") == "video_view":
            return int(float(item.get("value") or 0))
    return 0


def _action_value(row: dict, action_type: str) -> int:
    for item in row.get("actions") or []:
        if item.get("action_type") == action_type:
            return int(float(item.get("value") or 0))
    return 0


def discover_campaigns(env: dict[str, str]) -> list[dict[str, str]]:
    """Find the CP_P# campaigns by name - not tied to hardcoded campaign
    IDs, so a new phase (CP_P5...) or a renamed variant is picked up
    automatically on the next sync."""
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
            raise VideoFunnelSyncError(f"Meta campaigns error ({response.status_code}): {payload}")
        for row in payload.get("data") or []:
            if CAMPAIGN_NAME_PATTERN in row["name"].upper():
                campaigns.append({"id": row["id"], "name": row["name"], "status": row.get("status", "")})
        next_page = (payload.get("paging") or {}).get("next")
        url, params = (next_page, None) if next_page else (None, None)
    return campaigns


def phase_from_name(name: str) -> str:
    upper = name.upper()
    for phase in ("P1", "P2", "P3", "P4"):
        if phase in upper:
            return phase
    return "OTHER"


def _paginate_insights(env: dict[str, str], campaign_id: str, fields: str) -> list[dict]:
    """Meta's insights API caps time_increment=1 responses to a page size
    (25 days) regardless of the requested window - LOOKBACK_DAYS=90 was
    silently truncated to the first ~25 days without this, dropping the
    most recent (and most relevant) daily rows entirely."""
    import requests

    token = env["META_ACCESS_TOKEN"]
    version = env.get("META_API_VERSION", "v25.0")
    url = f"https://graph.facebook.com/{version}/{campaign_id}/insights"
    params = {
        "access_token": token,
        "fields": fields,
        "time_increment": 1,
        "date_preset": f"last_{LOOKBACK_DAYS}d",
        "limit": 100,
    }
    rows: list[dict] = []
    while url:
        response = requests.get(url, params=params, timeout=30)
        payload = response.json()
        if not response.ok:
            raise VideoFunnelSyncError(f"Meta insights error ({response.status_code}): {payload}")
        rows.extend(payload.get("data") or [])
        next_page = (payload.get("paging") or {}).get("next")
        url, params = (next_page, None) if next_page else (None, None)
    return rows


def fetch_video_daily(env: dict[str, str], campaign_id: str) -> list[dict]:
    raw_rows = _paginate_insights(
        env, campaign_id,
        "impressions,spend,frequency,video_p25_watched_actions,"
        "video_p50_watched_actions,video_p75_watched_actions,video_p95_watched_actions",
    )

    rows = []
    for row in raw_rows:
        rows.append(
            {
                "report_date": row["date_start"],
                "impressions": int(row.get("impressions") or 0),
                "spend": float(row.get("spend") or 0),
                "frequency": float(row.get("frequency") or 0),
                "vv25": _video_action_value(row, "video_p25_watched_actions"),
                "vv50": _video_action_value(row, "video_p50_watched_actions"),
                "vv75": _video_action_value(row, "video_p75_watched_actions"),
                "vv95": _video_action_value(row, "video_p95_watched_actions"),
            }
        )
    return rows


def fetch_lead_daily(env: dict[str, str], campaign_id: str) -> list[dict]:
    raw_rows = _paginate_insights(env, campaign_id, "impressions,spend,actions")

    rows = []
    for row in raw_rows:
        rows.append(
            {
                "report_date": row["date_start"],
                "impressions": int(row.get("impressions") or 0),
                "spend": float(row.get("spend") or 0),
                "frequency": 0.0,
                "vv25": 0,
                "vv50": 0,
                "vv75": 0,
                "vv95": 0,
                "leads": _action_value(row, "lead") or _action_value(row, "offsite_conversion.fb_pixel_lead"),
            }
        )
    return rows


def fetch_vv50_demographics(env: dict[str, str], campaign_id: str) -> list[tuple[str, str, int]]:
    import requests

    token = env["META_ACCESS_TOKEN"]
    version = env.get("META_API_VERSION", "v25.0")
    response = requests.get(
        f"https://graph.facebook.com/{version}/{campaign_id}/insights",
        params={
            "access_token": token,
            "fields": "video_p50_watched_actions",
            "breakdowns": "age,gender",
            "date_preset": f"last_{LOOKBACK_DAYS}d",
        },
        timeout=30,
    )
    payload = response.json()
    if not response.ok:
        raise VideoFunnelSyncError(f"Meta demographics error ({response.status_code}): {payload}")

    rows = []
    for row in payload.get("data") or []:
        vv50 = _video_action_value(row, "video_p50_watched_actions")
        if vv50:
            rows.append((row.get("age") or "unknown", row.get("gender") or "unknown", vv50))
    return rows


def store_daily(phase: str, campaign_id: str, campaign_name: str, rows: list[dict]) -> None:
    with dashboard_app.db() as con:
        con.execute(
            "DELETE FROM video_funnel_daily WHERE phase = ? AND campaign_id = ?",
            (phase, campaign_id),
        )
        con.executemany(
            """
            INSERT INTO video_funnel_daily
                (phase, campaign_id, campaign_name, report_date, impressions, spend,
                 frequency, vv25, vv50, vv75, vv95, leads, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            [
                (
                    phase, campaign_id, campaign_name, row["report_date"], row["impressions"], row["spend"],
                    row["frequency"], row["vv25"], row["vv50"], row["vv75"], row["vv95"], row.get("leads", 0),
                )
                for row in rows
            ],
        )


def store_demographics(phase: str, rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM video_funnel_demographics WHERE phase = ?", (phase,))
        con.executemany(
            "INSERT INTO video_funnel_demographics (phase, age, gender, vv50, synced_at) "
            "VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)",
            [(phase, age, gender, vv50) for age, gender, vv50 in rows],
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    missing = [key for key in ("META_ACCESS_TOKEN", "META_AD_ACCOUNT_ID") if not env.get(key)]
    if missing:
        raise VideoFunnelSyncError("Missing in .env: " + ", ".join(missing))

    campaigns = discover_campaigns(env)
    if not campaigns:
        print("Video funnel sync: no CP_P# campaigns found - nothing to do.")
        return 0

    total_daily_rows = 0
    for campaign in campaigns:
        phase = phase_from_name(campaign["name"])
        if phase == "P4":
            daily = fetch_lead_daily(env, campaign["id"])
        else:
            daily = fetch_video_daily(env, campaign["id"])
            demographics = fetch_vv50_demographics(env, campaign["id"])
            store_demographics(phase, demographics)
        store_daily(phase, campaign["id"], campaign["name"], daily)
        total_daily_rows += len(daily)

    print(
        f"Video funnel sync complete: {len(campaigns)} campaigns "
        f"({', '.join(c['name'] for c in campaigns)}), {total_daily_rows} daily rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
