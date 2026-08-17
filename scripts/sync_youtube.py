"""Snapshot the Peasy Anglais YouTube channel's public stats into local SQLite.

The YouTube Data API v3 only returns the channel's CURRENT totals (subscriber
count, view count, video count) - it has no historical endpoint for these.
Growth over time is built the same way as everything else in this project:
one row per day, accumulated by the daily automation.

Requires YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID in .env - a plain API key is
enough (no OAuth) since only public channel-level statistics are read.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402


class YoutubeSyncError(RuntimeError):
    pass


def fetch_channel_stats(env: dict[str, str]) -> tuple[int, int, int]:
    try:
        import requests
    except ImportError as error:
        raise YoutubeSyncError("requests is not installed.") from error

    api_key = env.get("YOUTUBE_API_KEY")
    channel_id = env.get("YOUTUBE_CHANNEL_ID")
    if not api_key or not channel_id:
        raise YoutubeSyncError("Missing YOUTUBE_API_KEY or YOUTUBE_CHANNEL_ID in .env")

    response = requests.get(
        "https://www.googleapis.com/youtube/v3/channels",
        params={"part": "statistics", "id": channel_id, "key": api_key},
        timeout=20,
    )
    payload = response.json()
    if not response.ok:
        raise YoutubeSyncError(f"YouTube API error ({response.status_code}): {payload}")

    items = payload.get("items") or []
    if not items:
        raise YoutubeSyncError(f"No channel found for id {channel_id}")

    stats = items[0]["statistics"]
    return (
        int(stats.get("subscriberCount") or 0),
        int(stats.get("viewCount") or 0),
        int(stats.get("videoCount") or 0),
    )


def store_snapshot(report_date: str, subscribers: int, views: int, videos: int) -> None:
    with dashboard_app.db() as con:
        con.execute(
            """
            INSERT INTO youtube_channel_daily (report_date, subscriber_count, view_count, video_count, synced_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                subscriber_count = excluded.subscriber_count,
                view_count = excluded.view_count,
                video_count = excluded.video_count,
                synced_at = CURRENT_TIMESTAMP
            """,
            (report_date, subscribers, views, videos),
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    subscribers, views, videos = fetch_channel_stats(env)
    today = date.today().isoformat()
    store_snapshot(today, subscribers, views, videos)

    print(f"YouTube snapshot complete: {subscribers} subscribers, {views} views, {videos} videos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
