"""Pull YouTube Analytics breakdowns (country, device, age/gender) for the
Peasy Anglais channel into local SQLite.

Separate from sync_youtube.py (which only needs a public API key for the
channel's total subscriber/view counts): this one reads private analytics
data, so it needs OAuth as the channel owner - see
scripts/_oauth_setup_youtube_tmp.py history (deleted after use) for how the
refresh token was generated.

Only aggregated counts are stored (no viewer-level data exists in this API).
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
TOP_LIMIT = 15

REQUIRED_KEYS = [
    "YOUTUBE_CHANNEL_ID",
    "YOUTUBE_API_KEY",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "YOUTUBE_REFRESH_TOKEN",
]


class YoutubeAnalyticsSyncError(RuntimeError):
    pass


def _access_token(env: dict[str, str]) -> str:
    import requests

    response = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": env["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": env["YOUTUBE_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        },
        timeout=20,
    )
    payload = response.json()
    if not response.ok or not payload.get("access_token"):
        raise YoutubeAnalyticsSyncError(f"Token refresh failed ({response.status_code}): {payload}")
    return payload["access_token"]


def _query(access_token: str, channel_id: str, **params: str) -> list[list]:
    import requests

    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    response = requests.get(
        "https://youtubeanalytics.googleapis.com/v2/reports",
        params={
            "ids": f"channel=={channel_id}",
            "startDate": start.isoformat(),
            "endDate": end.isoformat(),
            **params,
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise YoutubeAnalyticsSyncError(f"YouTube Analytics error ({response.status_code}): {payload}")
    return payload.get("rows") or []


def fetch_by_country(access_token: str, channel_id: str) -> list[tuple[str, int, int]]:
    rows = _query(
        access_token, channel_id,
        metrics="views,estimatedMinutesWatched", dimensions="country",
        sort="-views", maxResults=str(TOP_LIMIT),
    )
    return [(row[0], int(row[1]), int(row[2])) for row in rows]


def fetch_by_device(access_token: str, channel_id: str) -> list[tuple[str, int, int]]:
    rows = _query(
        access_token, channel_id,
        metrics="views,estimatedMinutesWatched", dimensions="deviceType",
        sort="-views",
    )
    return [(row[0], int(row[1]), int(row[2])) for row in rows]


def fetch_subscribers_daily(access_token: str, channel_id: str) -> list[tuple[str, int, int, int]]:
    rows = _query(
        access_token, channel_id,
        metrics="subscribersGained,subscribersLost,views", dimensions="day",
        sort="day",
    )
    return [(row[0], int(row[1]), int(row[2]), int(row[3])) for row in rows]


def fetch_top_videos(access_token: str, channel_id: str, api_key: str) -> list[tuple[str, str, int, int, int, int]]:
    import requests

    rows = _query(
        access_token, channel_id,
        metrics="views,likes,comments,estimatedMinutesWatched", dimensions="video",
        sort="-views", maxResults=str(TOP_LIMIT),
    )
    if not rows:
        return []

    video_ids = [row[0] for row in rows]
    titles: dict[str, str] = {}
    response = requests.get(
        "https://www.googleapis.com/youtube/v3/videos",
        params={"part": "snippet", "id": ",".join(video_ids), "key": api_key},
        timeout=20,
    )
    payload = response.json()
    if response.ok:
        for item in payload.get("items") or []:
            titles[item["id"]] = item.get("snippet", {}).get("title") or item["id"]

    return [
        (video_id, titles.get(video_id, video_id), int(views), int(likes), int(comments), int(watch_minutes))
        for video_id, views, likes, comments, watch_minutes in rows
    ]


def fetch_by_demographics(access_token: str, channel_id: str) -> list[tuple[str, str, float]]:
    rows = _query(
        access_token, channel_id,
        metrics="viewerPercentage", dimensions="ageGroup,gender",
        sort="ageGroup,gender",
    )
    return [(row[0], row[1], float(row[2])) for row in rows]


def store_country(rows: list[tuple[str, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM youtube_views_by_country")
        con.executemany(
            "INSERT INTO youtube_views_by_country (country, views, watch_minutes, synced_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_device(rows: list[tuple[str, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM youtube_views_by_device")
        con.executemany(
            "INSERT INTO youtube_views_by_device (device_type, views, watch_minutes, synced_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_subscribers_daily(rows: list[tuple[str, int, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO youtube_subscribers_daily (report_date, subscribers_gained, subscribers_lost, views, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                subscribers_gained = excluded.subscribers_gained,
                subscribers_lost = excluded.subscribers_lost,
                views = excluded.views,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def store_top_videos(rows: list[tuple[str, str, int, int, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM youtube_top_videos")
        con.executemany(
            "INSERT INTO youtube_top_videos "
            "(video_id, title, views, likes, comments, watch_minutes, synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def store_demographics(rows: list[tuple[str, str, float]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM youtube_demographics")
        con.executemany(
            "INSERT INTO youtube_demographics (age_group, gender, viewer_percentage, synced_at) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    missing = [key for key in REQUIRED_KEYS if not env.get(key)]
    if missing:
        raise YoutubeAnalyticsSyncError("Missing in .env: " + ", ".join(missing))

    access_token = _access_token(env)
    channel_id = env["YOUTUBE_CHANNEL_ID"]

    countries = fetch_by_country(access_token, channel_id)
    devices = fetch_by_device(access_token, channel_id)
    demographics = fetch_by_demographics(access_token, channel_id)
    subscribers_daily = fetch_subscribers_daily(access_token, channel_id)
    top_videos = fetch_top_videos(access_token, channel_id, env["YOUTUBE_API_KEY"])

    store_country(countries)
    store_device(devices)
    store_demographics(demographics)
    store_subscribers_daily(subscribers_daily)
    store_top_videos(top_videos)

    print(
        f"YouTube Analytics sync complete: {len(countries)} countries, "
        f"{len(subscribers_daily)} subscriber-days, {len(top_videos)} top videos, "
        f"{len(devices)} device types, {len(demographics)} age/gender rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
