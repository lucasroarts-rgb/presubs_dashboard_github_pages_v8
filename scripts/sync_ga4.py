"""Pull site-wide visitor counts from Google Analytics (GA4) into local SQLite.

Only aggregated day-level counts are stored - no user-level or PII data is
requested from the GA4 Data API at all (GA4 itself is aggregated by design).

Requires GA4_PROPERTY_ID and GA4_SERVICE_ACCOUNT_FILE in .env - the service
account must be added as a Viewer on the GA4 property (Admin > Property
Access Management).
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

LOOKBACK_DAYS = 90


class Ga4SyncError(RuntimeError):
    pass


def _client(env: dict[str, str]):
    try:
        from google.analytics.data_v1beta import BetaAnalyticsDataClient
        from google.oauth2 import service_account
    except ImportError as error:
        raise Ga4SyncError(
            "google-analytics-data is not installed. Run: pip install google-analytics-data"
        ) from error

    property_id = env.get("GA4_PROPERTY_ID")
    key_file = env.get("GA4_SERVICE_ACCOUNT_FILE")
    if not property_id or not key_file:
        raise Ga4SyncError(
            "Missing GA4_PROPERTY_ID or GA4_SERVICE_ACCOUNT_FILE in .env"
        )

    key_path = ROOT / key_file
    if not key_path.exists():
        raise Ga4SyncError(f"GA4 service account file not found: {key_path}")

    creds = service_account.Credentials.from_service_account_file(str(key_path))
    return BetaAnalyticsDataClient(credentials=creds), property_id


def _home_page_filter():
    """Landing page = "/" (the home page, query string stripped) - all PreSubs
    ad traffic lands there, regardless of the UTM parameters attached."""
    from google.analytics.data_v1beta.types import Filter, FilterExpression

    return FilterExpression(
        filter=Filter(
            field_name="landingPage",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.EXACT,
                value="/",
                case_sensitive=True,
            ),
        )
    )


def fetch_daily_traffic(client, property_id: str) -> list[tuple[str, int, int, int, int]]:
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date")],
        metrics=[
            Metric(name="activeUsers"),
            Metric(name="newUsers"),
            Metric(name="sessions"),
            Metric(name="engagedSessions"),
        ],
        date_ranges=[DateRange(start_date=f"{LOOKBACK_DAYS}daysAgo", end_date="today")],
        dimension_filter=_home_page_filter(),
    )
    response = client.run_report(request)
    rows: list[tuple[str, int, int, int, int]] = []
    for row in response.rows:
        raw_date = row.dimension_values[0].value  # YYYYMMDD
        report_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        active_users = int(row.metric_values[0].value or 0)
        new_users = int(row.metric_values[1].value or 0)
        sessions = int(row.metric_values[2].value or 0)
        engaged_sessions = int(row.metric_values[3].value or 0)
        rows.append((report_date, active_users, new_users, sessions, engaged_sessions))
    return rows


def fetch_daily_channel(client, property_id: str) -> list[tuple[str, str, int]]:
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest

    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="date"), Dimension(name="sessionDefaultChannelGroup")],
        metrics=[Metric(name="sessions")],
        date_ranges=[DateRange(start_date=f"{LOOKBACK_DAYS}daysAgo", end_date="today")],
        dimension_filter=_home_page_filter(),
    )
    response = client.run_report(request)
    rows: list[tuple[str, str, int]] = []
    for row in response.rows:
        raw_date = row.dimension_values[0].value
        report_date = f"{raw_date[0:4]}-{raw_date[4:6]}-{raw_date[6:8]}"
        channel_group = row.dimension_values[1].value or "(unassigned)"
        sessions = int(row.metric_values[0].value or 0)
        rows.append((report_date, channel_group, sessions))
    return rows


def store_daily_traffic(rows: list[tuple[str, int, int, int, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO site_traffic_daily
                (report_date, active_users, new_users, sessions, engaged_sessions, synced_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date) DO UPDATE SET
                active_users = excluded.active_users,
                new_users = excluded.new_users,
                sessions = excluded.sessions,
                engaged_sessions = excluded.engaged_sessions,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def store_daily_channel(rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO site_traffic_by_channel_daily (report_date, channel_group, sessions)
            VALUES (?, ?, ?)
            ON CONFLICT(report_date, channel_group) DO UPDATE SET
                sessions = excluded.sessions
            """,
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    client, property_id = _client(env)
    traffic = fetch_daily_traffic(client, property_id)
    channels = fetch_daily_channel(client, property_id)

    store_daily_traffic(traffic)
    store_daily_channel(channels)

    print(f"GA4 sync complete: {len(traffic)} traffic-days, {len(channels)} channel-day rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
