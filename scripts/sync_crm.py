"""Pull aggregated PreSubs lead and sale counts from the CRM MySQL database.

Only day-level counts and monetary sums are stored locally (no email, phone
or name) - matching the project rule that no personal data leaves the CRM.

Lead scope mirrors the filter used in the existing Looker Studio report
("[MYSQL] - Facebook" data source): utm_source contains facebook-ads or the
known facebbok-ads typo, Source is not Trial, plus the same PRESUBS-name
scoping and QUIZ exclusion used on the Meta side of this dashboard.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402
from scripts.automate_meta import load_env_file  # noqa: E402

PRESUBS_CAMPAIGN_PATTERNS = ["%presubs%", "%pre-subs%", "%pre subs%"]
QUIZ_EXCLUDE_PATTERN = "%quiz%"


class CrmSyncError(RuntimeError):
    pass


def _connect(env: dict[str, str]):
    try:
        import pymysql
    except ImportError as error:
        raise CrmSyncError(
            "pymysql is not installed. Run: pip install pymysql"
        ) from error

    required = ["CRM_MYSQL_HOST", "CRM_MYSQL_DATABASE", "CRM_MYSQL_USER", "CRM_MYSQL_PASSWORD"]
    missing = [key for key in required if not env.get(key)]
    if missing:
        raise CrmSyncError(
            "Missing CRM MySQL settings in .env: " + ", ".join(missing)
        )

    return pymysql.connect(
        host=env["CRM_MYSQL_HOST"],
        user=env["CRM_MYSQL_USER"],
        password=env["CRM_MYSQL_PASSWORD"],
        database=env["CRM_MYSQL_DATABASE"],
        connect_timeout=15,
        charset="utf8mb4",
    )


def fetch_lead_counts(connection) -> list[tuple[str, int]]:
    campaign_clause = " OR ".join(["LOWER(utm_campaign) LIKE %s"] * len(PRESUBS_CAMPAIGN_PATTERNS))
    query = f"""
        SELECT data AS report_date, COUNT(DISTINCT LOWER(TRIM(email))) AS lead_count
        FROM leads
        WHERE data IS NOT NULL AND data <> '0000-00-00'
          AND (LOWER(utm_source) LIKE %s OR LOWER(utm_source) LIKE %s)
          AND (Source IS NULL OR LOWER(Source) NOT LIKE %s)
          AND ({campaign_clause})
          AND LOWER(utm_campaign) NOT LIKE %s
        GROUP BY data
        ORDER BY data
    """
    params = ["%facebook-ads%", "%facebbok-ads%", "%trial%", *PRESUBS_CAMPAIGN_PATTERNS, QUIZ_EXCLUDE_PATTERN]
    cursor = connection.cursor()
    cursor.execute(query, params)
    return [(str(row[0]), int(row[1])) for row in cursor.fetchall()]


def fetch_sale_counts(connection) -> list[tuple[str, int, float, float]]:
    query = """
        SELECT sale_date AS report_date,
               COUNT(*) AS sale_count,
               COALESCE(SUM(price_full), 0) AS revenue_full,
               COALESCE(SUM(total_paid), 0) AS revenue_net
        FROM sales
        WHERE sale_date IS NOT NULL
          AND LOWER(sale_campaign) LIKE '%presubs%'
          AND sale_status = 'Confirmed'
        GROUP BY sale_date
        ORDER BY sale_date
    """
    cursor = connection.cursor()
    cursor.execute(query)
    return [(str(row[0]), int(row[1]), float(row[2]), float(row[3])) for row in cursor.fetchall()]


def store_lead_counts(rows: list[tuple[str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_leads_daily (report_date, source_bucket, lead_count, synced_at)
            VALUES (?, 'facebook-ads', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date, source_bucket) DO UPDATE SET
                lead_count = excluded.lead_count,
                synced_at = CURRENT_TIMESTAMP
            """,
            rows,
        )


def store_sale_counts(rows: list[tuple[str, int, float, float]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_sales_daily (report_date, sale_campaign, sale_count, revenue_full, revenue_net)
            VALUES (?, 'presubs', ?, ?, ?)
            ON CONFLICT(report_date, sale_campaign) DO UPDATE SET
                sale_count = excluded.sale_count,
                revenue_full = excluded.revenue_full,
                revenue_net = excluded.revenue_net
            """,
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    connection = _connect(env)
    try:
        leads = fetch_lead_counts(connection)
        sales = fetch_sale_counts(connection)
    finally:
        connection.close()

    store_lead_counts(leads)
    store_sale_counts(sales)

    print(f"CRM sync complete: {len(leads)} lead-days, {len(sales)} sale-days.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
