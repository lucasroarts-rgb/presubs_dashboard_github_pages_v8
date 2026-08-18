"""Snapshot Facebook Page and Instagram Business account growth (organic,
not paid ads) into local SQLite.

Uses a Meta System User token (Presubsautomation) with pages_read_engagement
- the Instagram Business account is read through its link to the Page, so
no separate instagram_basic/instagram_manage_insights scope is required for
these follower/media totals (post-level engagement detail does need that
scope and isn't pulled yet).

Only aggregated day-level totals are stored - no post content, no
individual comment/like data.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

API_VERSION = "v25.0"


class MetaOrganicSyncError(RuntimeError):
    pass


def fetch_page_and_instagram(env: dict[str, str]) -> dict:
    import requests

    token = env.get("META_ORGANIC_ACCESS_TOKEN")
    if not token:
        raise MetaOrganicSyncError("Missing META_ORGANIC_ACCESS_TOKEN in .env")

    response = requests.get(
        f"https://graph.facebook.com/{API_VERSION}/me/accounts",
        params={"access_token": token, "fields": "id,name,fan_count,instagram_business_account"},
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise MetaOrganicSyncError(f"Meta Graph API error ({response.status_code}): {payload}")

    pages = payload.get("data") or []
    if not pages:
        raise MetaOrganicSyncError("Token has no accessible Facebook Pages.")
    page = pages[0]

    result = {
        "facebook_fan_count": int(page.get("fan_count") or 0),
        "instagram_followers": None,
        "instagram_media_count": None,
    }

    ig_account = page.get("instagram_business_account")
    if ig_account:
        ig_response = requests.get(
            f"https://graph.facebook.com/{API_VERSION}/{ig_account['id']}",
            params={"access_token": token, "fields": "followers_count,media_count"},
            timeout=20,
        )
        ig_payload = ig_response.json()
        if ig_response.ok:
            result["instagram_followers"] = int(ig_payload.get("followers_count") or 0)
            result["instagram_media_count"] = int(ig_payload.get("media_count") or 0)

    return result


def store_snapshot(report_date: str, data: dict) -> None:
    with dashboard_app.db() as con:
        con.execute(
            """
            INSERT INTO meta_organic_daily
                (report_date, facebook_fan_count, instagram_followers, instagram_media_count, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                facebook_fan_count = excluded.facebook_fan_count,
                instagram_followers = excluded.instagram_followers,
                instagram_media_count = excluded.instagram_media_count,
                synced_at = CURRENT_TIMESTAMP
            """,
            (
                report_date,
                data["facebook_fan_count"],
                data["instagram_followers"],
                data["instagram_media_count"],
            ),
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    data = fetch_page_and_instagram(env)
    today = date.today().isoformat()
    store_snapshot(today, data)

    print(
        f"Meta organic snapshot complete: {data['facebook_fan_count']} FB fans, "
        f"{data['instagram_followers']} IG followers, {data['instagram_media_count']} IG posts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
