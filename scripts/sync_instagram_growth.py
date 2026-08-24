"""Sync Instagram Business account growth via the Instagram Graph API's
Insights endpoints (instagram_basic/instagram_manage_insights, granted on
the System User token 2026-08-24 - see project memory for the approval
history).

Separate from sync_meta_organic.py, which only stores a single daily
follower-count snapshot (that script predates these scopes being granted
and doesn't need them - the IG account is read through its link to the
Facebook Page). This script pulls the richer growth data the reference
Looker Studio "Growth Instagram" page showed: daily reach/views/profile
visits/new followers, follower demographics (gender/age/country/city),
and per-post performance for recent media.

Metric API notes (Graph API v25.0, confirmed empirically - the Instagram
Insights API has repeatedly deprecated/renamed metrics across versions,
so don't trust older documentation blindly):
  - reach, follower_count: metric_type=time_series works, returns one row
    per day for a date range in a single call.
  - views, profile_views: metric_type=time_series is REJECTED by the API
    ("incompatible with metric type") - only metric_type=total_value
    works, which aggregates the whole requested window into one number.
    To get a daily series we loop one 1-day window per day instead.
  - follower_demographics: metric_type=total_value with a `breakdown`
    param (gender/age/country/city) - lifetime snapshot, not date-ranged.
  - Per-media insights (reach/saved/total_interactions/likes/comments/
    shares) are lifetime-cumulative per post, fetched individually per
    media id.
"""

from __future__ import annotations

import calendar
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

API_VERSION = "v25.0"
TIME_SERIES_LOOKBACK_DAYS = 29  # API hard-caps since/until at exactly 30 days apart
TOTAL_VALUE_LOOKBACK_DAYS = 14
MEDIA_LOOKBACK_COUNT = 25
DEMOGRAPHIC_BREAKDOWNS = ["gender", "age", "country", "city"]


class InstagramSyncError(RuntimeError):
    pass


def _epoch(day: date) -> int:
    """Unix timestamp for midnight UTC on `day` - date.strftime("%s") is
    not portable (unsupported on Windows), so go through calendar.timegm
    instead."""
    return calendar.timegm(day.timetuple())


def _ig_account_id(token: str) -> str:
    import requests

    response = requests.get(
        f"https://graph.facebook.com/{API_VERSION}/me/accounts",
        params={"access_token": token, "fields": "instagram_business_account"},
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise InstagramSyncError(f"Meta Graph API error ({response.status_code}): {payload}")
    for page in payload.get("data") or []:
        ig_account = page.get("instagram_business_account")
        if ig_account:
            return ig_account["id"]
    raise InstagramSyncError("No Instagram Business account linked to any accessible Page.")


def fetch_time_series(ig_id: str, token: str, metric: str) -> dict[str, int]:
    import requests

    since = _epoch(date.today() - timedelta(days=TIME_SERIES_LOOKBACK_DAYS))
    response = requests.get(
        f"https://graph.facebook.com/{API_VERSION}/{ig_id}/insights",
        params={
            "access_token": token,
            "metric": metric,
            "period": "day",
            "metric_type": "time_series",
            "since": since,
        },
        timeout=30,
    )
    payload = response.json()
    if not response.ok:
        raise InstagramSyncError(f"Meta insights error for {metric} ({response.status_code}): {payload}")
    values = (payload.get("data") or [{}])[0].get("values") or []
    return {row["end_time"][:10]: int(row.get("value") or 0) for row in values}


def fetch_daily_total_value(ig_id: str, token: str) -> dict[str, dict[str, int]]:
    """views + profile_views don't support time_series, so loop a 1-day
    window per day for the lookback range instead."""
    import requests

    result: dict[str, dict[str, int]] = {}
    today = date.today()
    for offset in range(1, TOTAL_VALUE_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=offset)
        since = _epoch(day)
        until = _epoch(day + timedelta(days=1))
        response = requests.get(
            f"https://graph.facebook.com/{API_VERSION}/{ig_id}/insights",
            params={
                "access_token": token,
                "metric": "views,profile_views",
                "period": "day",
                "metric_type": "total_value",
                "since": since,
                "until": until,
            },
            timeout=30,
        )
        payload = response.json()
        if not response.ok:
            raise InstagramSyncError(f"Meta insights error for views/profile_views ({response.status_code}): {payload}")
        row = {"views": 0, "profile_views": 0}
        for item in payload.get("data") or []:
            row[item["name"]] = int((item.get("total_value") or {}).get("value") or 0)
        result[day.isoformat()] = row
    return result


def fetch_demographics(ig_id: str, token: str) -> list[tuple[str, str, int]]:
    import requests

    rows: list[tuple[str, str, int]] = []
    for breakdown in DEMOGRAPHIC_BREAKDOWNS:
        response = requests.get(
            f"https://graph.facebook.com/{API_VERSION}/{ig_id}/insights",
            params={
                "access_token": token,
                "metric": "follower_demographics",
                "period": "lifetime",
                "metric_type": "total_value",
                "breakdown": breakdown,
            },
            timeout=30,
        )
        payload = response.json()
        if not response.ok:
            raise InstagramSyncError(f"Meta demographics error for {breakdown} ({response.status_code}): {payload}")
        for entry in payload.get("data") or []:
            for group in (entry.get("total_value") or {}).get("breakdowns") or []:
                for result in group.get("results") or []:
                    key = result["dimension_values"][0]
                    rows.append((breakdown, key, int(result.get("value") or 0)))
    return rows


def fetch_recent_media(ig_id: str, token: str) -> list[dict]:
    import requests

    response = requests.get(
        f"https://graph.facebook.com/{API_VERSION}/{ig_id}/media",
        params={
            "access_token": token,
            "fields": "id,caption,media_type,permalink,thumbnail_url,timestamp",
            "limit": MEDIA_LOOKBACK_COUNT,
        },
        timeout=30,
    )
    payload = response.json()
    if not response.ok:
        raise InstagramSyncError(f"Meta media list error ({response.status_code}): {payload}")
    return payload.get("data") or []


def fetch_media_insights(media_id: str, media_type: str, token: str) -> dict[str, int]:
    import requests

    metrics = "reach,saved,total_interactions,likes,comments"
    if media_type != "CAROUSEL_ALBUM":
        metrics += ",shares"
    response = requests.get(
        f"https://graph.facebook.com/{API_VERSION}/{media_id}/insights",
        params={"access_token": token, "metric": metrics},
        timeout=30,
    )
    payload = response.json()
    if not response.ok:
        return {}
    result = {"reach": 0, "saved": 0, "total_interactions": 0, "likes": 0, "comments": 0, "shares": 0}
    for item in payload.get("data") or []:
        result[item["name"]] = int((item.get("values") or [{}])[0].get("value") or 0)
    return result


def store_daily(reach: dict[str, int], followers: dict[str, int], totals: dict[str, dict[str, int]]) -> None:
    dates = set(reach) | set(followers) | set(totals)
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO instagram_daily (report_date, reach, views, profile_views, new_followers, synced_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                reach = excluded.reach,
                views = COALESCE(excluded.views, instagram_daily.views),
                profile_views = COALESCE(excluded.profile_views, instagram_daily.profile_views),
                new_followers = excluded.new_followers,
                synced_at = CURRENT_TIMESTAMP
            """,
            [
                (
                    report_date,
                    reach.get(report_date, 0),
                    totals.get(report_date, {}).get("views"),
                    totals.get(report_date, {}).get("profile_views"),
                    followers.get(report_date, 0),
                )
                for report_date in sorted(dates)
            ],
        )


def store_demographics(rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM instagram_demographics")
        con.executemany(
            "INSERT INTO instagram_demographics (dimension, key, value, synced_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_media(rows: list[dict]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO instagram_media
                (media_id, report_date, media_type, caption, permalink, thumbnail_url,
                 reach, saved, total_interactions, likes, comments, shares, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(media_id) DO UPDATE SET
                reach = excluded.reach,
                saved = excluded.saved,
                total_interactions = excluded.total_interactions,
                likes = excluded.likes,
                comments = excluded.comments,
                shares = excluded.shares,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    token = env.get("META_ORGANIC_ACCESS_TOKEN")
    if not token:
        raise InstagramSyncError("Missing META_ORGANIC_ACCESS_TOKEN in .env")

    ig_id = _ig_account_id(token)

    reach = fetch_time_series(ig_id, token, "reach")
    followers = fetch_time_series(ig_id, token, "follower_count")
    totals = fetch_daily_total_value(ig_id, token)
    store_daily(reach, followers, totals)

    demographics = fetch_demographics(ig_id, token)
    store_demographics(demographics)

    media_list = fetch_recent_media(ig_id, token)
    media_rows = []
    for media in media_list:
        insights = fetch_media_insights(media["id"], media.get("media_type", ""), token)
        media_rows.append(
            (
                media["id"],
                media.get("timestamp", "")[:10],
                media.get("media_type"),
                media.get("caption"),
                media.get("permalink"),
                media.get("thumbnail_url"),
                insights.get("reach", 0),
                insights.get("saved", 0),
                insights.get("total_interactions", 0),
                insights.get("likes", 0),
                insights.get("comments", 0),
                insights.get("shares", 0),
            )
        )
    store_media(media_rows)

    print(
        f"Instagram growth sync complete: {len(reach)} days of reach, "
        f"{len(demographics)} demographic rows, {len(media_rows)} posts."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
