"""Read-only ad-hoc check: list GA4 event names + counts for the last N days.

Reuses the same auth pattern as sync_ga4.py. Does not write to the DB.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.automate_meta import load_env_file  # noqa: E402

DAYS = int(sys.argv[1]) if len(sys.argv) > 1 else 30


def main():
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    from google.analytics.data_v1beta.types import (
        DateRange, Dimension, Metric, RunReportRequest, OrderBy,
    )
    from google.oauth2 import service_account

    env = load_env_file(ROOT / ".env")
    property_id = env.get("GA4_PROPERTY_ID")
    key_file = env.get("GA4_SERVICE_ACCOUNT_FILE")
    key_path = ROOT / key_file
    creds = service_account.Credentials.from_service_account_file(str(key_path))
    client = BetaAnalyticsDataClient(credentials=creds)

    order = OrderBy(metric=OrderBy.MetricOrderBy(metric_name="eventCount"), desc=True)
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="eventName")],
        metrics=[Metric(name="eventCount"), Metric(name="conversions")],
        date_ranges=[DateRange(start_date=f"{DAYS}daysAgo", end_date="today")],
        order_bys=[order],
        limit=100,
    )
    response = client.run_report(request)

    print(f"GA4 events, last {DAYS} days, property {property_id}")
    print(f"{'event_name':<40}{'eventCount':>12}{'conversions':>14}")
    for row in response.rows:
        name = row.dimension_values[0].value
        count = row.metric_values[0].value
        conv = row.metric_values[1].value
        print(f"{name:<40}{count:>12}{conv:>14}")


if __name__ == "__main__":
    main()
