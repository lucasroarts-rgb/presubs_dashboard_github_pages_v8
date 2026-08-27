"""Sync Microsoft Clarity session-quality metrics (rage/dead clicks,
scroll depth, engagement time) plus browser/device/OS/country/page/
referrer breakdowns.

Clarity's Data Export API (https://www.clarity.ms/export-data/api/v1/
project-live-insights) only accepts numOfDays=1, 2 or 3 - it always
returns a ROLLING window ending "now", with no way to pick an arbitrary
past date range, and no per-day breakdown within that window (the
numbers are one aggregate total for the whole window). There is also a
hard rate limit of 10 requests per project per day.

Because of that, this is built the same way as YouTube/Instagram: pull
numOfDays=1 once a day and store it as a single daily snapshot,
accumulating real history in our own database over time - not a true
historical backfill (Clarity itself doesn't expose one).
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

API_URL = "https://www.clarity.ms/export-data/api/v1/project-live-insights"
BREAKDOWN_DIMENSIONS = {
    "Browser": "browser",
    "Device": "device",
    "OS": "os",
    "Country": "country",
    "PageTitle": "page_title",
    "ReferrerUrl": "referrer",
}


class ClaritySyncError(RuntimeError):
    pass


def fetch_metrics(token: str) -> list[dict]:
    import requests

    response = requests.get(
        API_URL,
        params={"numOfDays": 1},
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )
    if not response.ok:
        raise ClaritySyncError(f"Clarity API error ({response.status_code}): {response.text}")
    return response.json()


def _find(metrics: list[dict], name: str) -> dict:
    for item in metrics:
        if item.get("metricName") == name:
            return (item.get("information") or [{}])[0]
    return {}


def _float_or_none(value) -> float | None:
    return None if value is None else float(value)


def parse_daily(metrics: list[dict]) -> dict:
    traffic = _find(metrics, "Traffic")
    engagement = _find(metrics, "EngagementTime")
    scroll = _find(metrics, "ScrollDepth")
    dead_click = _find(metrics, "DeadClickCount")
    rage_click = _find(metrics, "RageClickCount")
    quickback = _find(metrics, "QuickbackClick")
    excessive_scroll = _find(metrics, "ExcessiveScroll")
    script_error = _find(metrics, "ScriptErrorCount")
    error_click = _find(metrics, "ErrorClickCount")

    return {
        "sessions_count": int(traffic.get("totalSessionCount") or 0),
        "bot_sessions_count": int(traffic.get("totalBotSessionCount") or 0),
        "distinct_users_count": int(traffic.get("distinctUserCount") or 0),
        "pages_per_session": _float_or_none(traffic.get("pagesPerSessionPercentage")),
        "engagement_time_total": int(engagement.get("totalTime") or 0),
        "engagement_time_active": int(engagement.get("activeTime") or 0),
        "scroll_depth_avg": _float_or_none(scroll.get("averageScrollDepth")),
        "dead_click_sessions": int(dead_click.get("subTotal") or 0),
        "dead_click_pct": _float_or_none(dead_click.get("sessionsWithMetricPercentage")),
        "rage_click_sessions": int(rage_click.get("subTotal") or 0),
        "rage_click_pct": _float_or_none(rage_click.get("sessionsWithMetricPercentage")),
        "quickback_click_sessions": int(quickback.get("subTotal") or 0),
        "excessive_scroll_sessions": int(excessive_scroll.get("subTotal") or 0),
        "script_error_sessions": int(script_error.get("subTotal") or 0),
        "error_click_sessions": int(error_click.get("subTotal") or 0),
    }


def parse_breakdown(metrics: list[dict]) -> list[tuple[str, str, int]]:
    rows: list[tuple[str, str, int]] = []
    for source_name, dimension in BREAKDOWN_DIMENSIONS.items():
        for item in metrics:
            if item.get("metricName") != source_name:
                continue
            for entry in item.get("information") or []:
                key = entry.get("name")
                if key is None:
                    continue
                rows.append((dimension, str(key), int(entry.get("sessionsCount") or 0)))

    for item in metrics:
        if item.get("metricName") != "PopularPages":
            continue
        for entry in item.get("information") or []:
            url = entry.get("url")
            if url is None:
                continue
            rows.append(("popular_page", url, int(entry.get("visitsCount") or 0)))
    return rows


def store_daily(report_date: str, data: dict) -> None:
    with dashboard_app.db() as con:
        con.execute(
            """
            INSERT INTO clarity_daily
                (report_date, sessions_count, bot_sessions_count, distinct_users_count,
                 pages_per_session, engagement_time_total, engagement_time_active, scroll_depth_avg,
                 dead_click_sessions, dead_click_pct, rage_click_sessions, rage_click_pct,
                 quickback_click_sessions, excessive_scroll_sessions, script_error_sessions,
                 error_click_sessions, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                sessions_count = excluded.sessions_count,
                bot_sessions_count = excluded.bot_sessions_count,
                distinct_users_count = excluded.distinct_users_count,
                pages_per_session = excluded.pages_per_session,
                engagement_time_total = excluded.engagement_time_total,
                engagement_time_active = excluded.engagement_time_active,
                scroll_depth_avg = excluded.scroll_depth_avg,
                dead_click_sessions = excluded.dead_click_sessions,
                dead_click_pct = excluded.dead_click_pct,
                rage_click_sessions = excluded.rage_click_sessions,
                rage_click_pct = excluded.rage_click_pct,
                quickback_click_sessions = excluded.quickback_click_sessions,
                excessive_scroll_sessions = excluded.excessive_scroll_sessions,
                script_error_sessions = excluded.script_error_sessions,
                error_click_sessions = excluded.error_click_sessions,
                synced_at = CURRENT_TIMESTAMP
            """,
            (
                report_date, data["sessions_count"], data["bot_sessions_count"], data["distinct_users_count"],
                data["pages_per_session"], data["engagement_time_total"], data["engagement_time_active"],
                data["scroll_depth_avg"], data["dead_click_sessions"], data["dead_click_pct"],
                data["rage_click_sessions"], data["rage_click_pct"], data["quickback_click_sessions"],
                data["excessive_scroll_sessions"], data["script_error_sessions"], data["error_click_sessions"],
            ),
        )


def store_breakdown(rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.execute("DELETE FROM clarity_breakdown")
        con.executemany(
            "INSERT INTO clarity_breakdown (dimension, key, value, synced_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    token = env.get("CLARITY_API_TOKEN")
    if not token:
        raise ClaritySyncError("Missing CLARITY_API_TOKEN in .env")

    metrics = fetch_metrics(token)
    daily = parse_daily(metrics)
    report_date = (date.today() - timedelta(days=1)).isoformat()
    store_daily(report_date, daily)

    breakdown = parse_breakdown(metrics)
    store_breakdown(breakdown)

    print(
        f"Clarity sync complete: {daily['sessions_count']} sessions, "
        f"{daily['rage_click_sessions']} rage-click sessions, {len(breakdown)} breakdown rows."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
