"""Pull Google Ads campaign performance into local SQLite.

Only aggregated day-level campaign counts are stored - no PII involved,
Google Ads campaign performance is account-level aggregate by nature.

Requires GOOGLE_ADS_DEVELOPER_TOKEN, GOOGLE_ADS_LOGIN_CUSTOMER_ID,
GOOGLE_ADS_CUSTOMER_ID, GOOGLE_ADS_CLIENT_ID, GOOGLE_ADS_CLIENT_SECRET and
GOOGLE_ADS_REFRESH_TOKEN in .env - see scripts/_oauth_setup_tmp.py history
(deleted after use) for how the refresh token was generated.
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


class GoogleAdsSyncError(RuntimeError):
    pass


REQUIRED_KEYS = [
    "GOOGLE_ADS_DEVELOPER_TOKEN",
    "GOOGLE_ADS_CUSTOMER_ID",
    "GOOGLE_ADS_CLIENT_ID",
    "GOOGLE_ADS_CLIENT_SECRET",
    "GOOGLE_ADS_REFRESH_TOKEN",
]


def _client(env: dict[str, str]):
    try:
        from google.ads.googleads.client import GoogleAdsClient
    except ImportError as error:
        raise GoogleAdsSyncError(
            "google-ads is not installed. Run: pip install google-ads"
        ) from error

    missing = [key for key in REQUIRED_KEYS if not env.get(key)]
    if missing:
        raise GoogleAdsSyncError("Missing in .env: " + ", ".join(missing))

    # No login_customer_id: the OAuth identity has direct access to
    # GOOGLE_ADS_CUSTOMER_ID (confirmed via CustomerService.list_accessible_customers),
    # so routing through the GOOGLE_ADS_LOGIN_CUSTOMER_ID manager account is not
    # needed and fails with USER_PERMISSION_DENIED unless that MCC link is
    # fully accepted.
    client = GoogleAdsClient.load_from_dict(
        {
            "developer_token": env["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "client_id": env["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": env["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": env["GOOGLE_ADS_REFRESH_TOKEN"],
            "use_proto_plus": True,
        }
    )
    return client, env["GOOGLE_ADS_CUSTOMER_ID"]


def fetch_campaign_daily(client, customer_id: str) -> list[tuple[str, str, str, str, float, int, int, float]]:
    service = client.get_service("GoogleAdsService")
    end = date.today()
    start = end - timedelta(days=LOOKBACK_DAYS)
    query = f"""
        SELECT
            segments.date,
            campaign.id,
            campaign.name,
            campaign.status,
            metrics.cost_micros,
            metrics.clicks,
            metrics.impressions,
            metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start.isoformat()}' AND '{end.isoformat()}'
    """
    rows: list[tuple[str, str, str, str, float, int, int, float]] = []
    response = service.search_stream(customer_id=customer_id, query=query)
    for batch in response:
        for row in batch.results:
            rows.append(
                (
                    row.segments.date,
                    str(row.campaign.id),
                    row.campaign.name,
                    row.campaign.status.name,
                    row.metrics.cost_micros / 1_000_000,
                    int(row.metrics.clicks),
                    int(row.metrics.impressions),
                    float(row.metrics.conversions),
                )
            )
    return rows


def store_campaign_daily(rows: list[tuple[str, str, str, str, float, int, int, float]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO google_ads_campaign_daily
                (report_date, campaign_id, campaign_name, status, spend, clicks, impressions, conversions, synced_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date, campaign_id) DO UPDATE SET
                campaign_name = excluded.campaign_name,
                status = excluded.status,
                spend = excluded.spend,
                clicks = excluded.clicks,
                impressions = excluded.impressions,
                conversions = excluded.conversions,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    client, customer_id = _client(env)
    rows = fetch_campaign_daily(client, customer_id)
    store_campaign_daily(rows)

    print(f"Google Ads sync complete: {len(rows)} campaign-day rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
