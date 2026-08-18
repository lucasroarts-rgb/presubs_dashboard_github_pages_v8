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
from scripts.geo_codes import resolve_country  # noqa: E402

PRESUBS_CAMPAIGN_PATTERNS = ["%presubs%", "%pre-subs%", "%pre subs%"]
QUIZ_EXCLUDE_PATTERN = "%quiz%"

CHANNEL_LABELS = {
    "facebook-ads": "Facebook Ads",
    "facebbok-ads": "Facebook Ads",
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "youtube": "YouTube",
    "adwords": "Google Ads",
    "google-ads": "Google Ads",
    "google_ads": "Google Ads",
    "facebook": "Facebook (organic)",
    "email": "Email",
    "whatsapp": "WhatsApp",
    "redirect": "Direct/Redirect",
    "visit": "Direct/Other",
}


def normalize_channel(raw: str | None) -> str:
    if not raw or not raw.strip():
        return "Direct/Other"
    key = raw.strip().lower()
    return CHANNEL_LABELS.get(key, raw.strip().title())


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


def fetch_organic_lead_counts(connection) -> list[tuple[str, int]]:
    """Organic PreSubs leads - Location='Organic' in the CRM, not paid traffic."""
    campaign_clause = " OR ".join(["LOWER(utm_campaign) LIKE %s"] * len(PRESUBS_CAMPAIGN_PATTERNS))
    query = f"""
        SELECT data AS report_date, COUNT(DISTINCT LOWER(TRIM(email))) AS lead_count
        FROM leads
        WHERE data IS NOT NULL AND data <> '0000-00-00'
          AND Location = 'Organic'
          AND ({campaign_clause})
          AND LOWER(utm_campaign) NOT LIKE %s
        GROUP BY data
        ORDER BY data
    """
    params = [*PRESUBS_CAMPAIGN_PATTERNS, QUIZ_EXCLUDE_PATTERN]
    cursor = connection.cursor()
    cursor.execute(query, params)
    return [(str(row[0]), int(row[1])) for row in cursor.fetchall()]


def fetch_country_counts(connection) -> list[tuple[str, str, str, int]]:
    """(report_date, country, source_bucket['organic'|'paid'], lead_count).

    Country comes from the phone number's calling-code prefix only (5 chars
    max fetched) - the full phone number is never pulled or stored.
    """
    campaign_clause = " OR ".join(["LOWER(utm_campaign) LIKE %s"] * len(PRESUBS_CAMPAIGN_PATTERNS))
    query = f"""
        SELECT data AS report_date, SUBSTRING(phone,1,5) AS prefix, Location,
               COUNT(DISTINCT LOWER(TRIM(email))) AS lead_count
        FROM leads
        WHERE data IS NOT NULL AND data <> '0000-00-00'
          AND phone IS NOT NULL AND phone <> '' AND phone <> '+'
          AND ({campaign_clause})
          AND LOWER(utm_campaign) NOT LIKE %s
        GROUP BY data, prefix, Location
    """
    params = [*PRESUBS_CAMPAIGN_PATTERNS, QUIZ_EXCLUDE_PATTERN]
    cursor = connection.cursor()
    cursor.execute(query, params)

    aggregated: dict[tuple[str, str, str], int] = {}
    for report_date, prefix, location, count in cursor.fetchall():
        country = resolve_country(prefix)
        bucket = "organic" if location == "Organic" else "paid"
        key = (str(report_date), country, bucket)
        aggregated[key] = aggregated.get(key, 0) + int(count)
    return [(d, c, b, n) for (d, c, b), n in aggregated.items()]


CORE_MARKET_COUNTRIES = {"France", "Belgium", "Switzerland"}


def fetch_organic_foreign_by_channel(connection) -> list[tuple[str, str, int]]:
    """(report_date, channel, lead_count) for organic leads whose phone-prefix
    country is outside France/Belgium/Switzerland - which acquisition channel
    (Instagram bio, Facebook bio, TikTok, etc) brought them in."""
    campaign_clause = " OR ".join(["LOWER(utm_campaign) LIKE %s"] * len(PRESUBS_CAMPAIGN_PATTERNS))
    query = f"""
        SELECT data AS report_date, SUBSTRING(phone,1,5) AS prefix, COALESCE(Source,'') AS source,
               COUNT(DISTINCT LOWER(TRIM(email))) AS lead_count
        FROM leads
        WHERE data IS NOT NULL AND data <> '0000-00-00'
          AND Location = 'Organic'
          AND phone IS NOT NULL AND phone <> '' AND phone <> '+'
          AND ({campaign_clause})
          AND LOWER(utm_campaign) NOT LIKE %s
        GROUP BY data, prefix, source
    """
    params = [*PRESUBS_CAMPAIGN_PATTERNS, QUIZ_EXCLUDE_PATTERN]
    cursor = connection.cursor()
    cursor.execute(query, params)

    aggregated: dict[tuple[str, str], int] = {}
    for report_date, prefix, source, count in cursor.fetchall():
        country = resolve_country(prefix)
        if country in CORE_MARKET_COUNTRIES:
            continue
        channel = normalize_channel(source)
        key = (str(report_date), channel)
        aggregated[key] = aggregated.get(key, 0) + int(count)
    return [(d, c, n) for (d, c), n in aggregated.items()]


def fetch_channel_counts(connection) -> list[tuple[str, str, int]]:
    campaign_clause = " OR ".join(["LOWER(utm_campaign) LIKE %s"] * len(PRESUBS_CAMPAIGN_PATTERNS))
    query = f"""
        SELECT data AS report_date, COALESCE(Source,'') AS source,
               COUNT(DISTINCT LOWER(TRIM(email))) AS lead_count
        FROM leads
        WHERE data IS NOT NULL AND data <> '0000-00-00'
          AND ({campaign_clause})
          AND LOWER(utm_campaign) NOT LIKE %s
        GROUP BY data, source
    """
    params = [*PRESUBS_CAMPAIGN_PATTERNS, QUIZ_EXCLUDE_PATTERN]
    cursor = connection.cursor()
    cursor.execute(query, params)

    aggregated: dict[tuple[str, str], int] = {}
    for report_date, source, count in cursor.fetchall():
        channel = normalize_channel(source)
        key = (str(report_date), channel)
        aggregated[key] = aggregated.get(key, 0) + int(count)
    return [(d, c, n) for (d, c), n in aggregated.items()]


ORGANIC_BREAKDOWN_FIELDS = {
    "source": "utm_source",
    "content": "utm_content",
    "term": "utm_term",
    "temperature": "Temperature",
}


def fetch_organic_breakdown(connection) -> list[tuple[str, str, str, int]]:
    """(report_date, dimension_type, dimension_value, lead_count) for organic
    PreSubs leads, one pass per utm_source/utm_content/utm_term/Temperature."""
    campaign_clause = " OR ".join(["LOWER(utm_campaign) LIKE %s"] * len(PRESUBS_CAMPAIGN_PATTERNS))
    rows: list[tuple[str, str, str, int]] = []
    for dimension_type, column in ORGANIC_BREAKDOWN_FIELDS.items():
        query = f"""
            SELECT data AS report_date, COALESCE(NULLIF(TRIM({column}), ''), '(not set)') AS value,
                   COUNT(DISTINCT LOWER(TRIM(email))) AS lead_count
            FROM leads
            WHERE data IS NOT NULL AND data <> '0000-00-00'
              AND Location = 'Organic'
              AND ({campaign_clause})
              AND LOWER(utm_campaign) NOT LIKE %s
            GROUP BY data, value
        """
        params = [*PRESUBS_CAMPAIGN_PATTERNS, QUIZ_EXCLUDE_PATTERN]
        cursor = connection.cursor()
        cursor.execute(query, params)
        for report_date, value, count in cursor.fetchall():
            rows.append((str(report_date), dimension_type, str(value)[:120], int(count)))
    return rows


def store_organic_breakdown(rows: list[tuple[str, str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_organic_breakdown_daily (report_date, dimension_type, dimension_value, lead_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(report_date, dimension_type, dimension_value) DO UPDATE SET
                lead_count = excluded.lead_count
            """,
            rows,
        )


SALE_CAMPAIGN_CODE_REGEXP = r"(^|[^a-z0-9])(cpl|l)[0-9]{2}([^0-9]|$)"


def fetch_sale_counts(connection) -> list[tuple[str, int, float, float]]:
    """sales.sale_campaign holds the raw ad-campaign name, not a fixed
    product tag like leads.utm_campaign - a plain "%presubs%" match only
    caught the old literal-named campaigns. Every campaign since then
    uses the same L##/cpl## capture-page code used throughout this
    dashboard (see CAMPAIGN_SOURCE_PATTERN in sync_ghl.py), so that's
    matched too.

    sale_campaign is blank on ~63% of Confirmed rows (no attribution
    captured at the point of sale itself) - for those, fall back to the
    matching lead's own utm_campaign, joined by email and picking each
    email's earliest row that actually has a non-blank utm_campaign
    (leads.email is not unique - a contact can have multiple capture-page
    visits over time, so a naive join fans out and double-counts revenue;
    this recovers ~53 of 130 previously-blank Confirmed sales / ~90 days,
    the rest have no matching lead row with UTM data at all). The join
    key (email) is only ever used inside this query, never selected or
    stored - no PII leaves the CRM."""
    query = """
        SELECT s.sale_date AS report_date,
               COUNT(*) AS sale_count,
               COALESCE(SUM(s.price_full), 0) AS revenue_full,
               COALESCE(SUM(s.total_paid), 0) AS revenue_net
        FROM sales s
        LEFT JOIN (
            SELECT l1.email, l1.utm_campaign
            FROM leads l1
            JOIN (
                SELECT email, MIN(data) AS first_date
                FROM leads
                WHERE utm_campaign IS NOT NULL AND utm_campaign <> ''
                GROUP BY email
            ) fl ON fl.email = l1.email AND fl.first_date = l1.data
            GROUP BY l1.email
        ) first_lead ON first_lead.email = s.email
        WHERE s.sale_date IS NOT NULL
          AND s.sale_status = 'Confirmed'
          AND (
            LOWER(COALESCE(NULLIF(s.sale_campaign, ''), first_lead.utm_campaign, '')) LIKE %s
            OR LOWER(COALESCE(NULLIF(s.sale_campaign, ''), first_lead.utm_campaign, '')) LIKE %s
            OR LOWER(COALESCE(NULLIF(s.sale_campaign, ''), first_lead.utm_campaign, '')) LIKE %s
            OR LOWER(COALESCE(NULLIF(s.sale_campaign, ''), first_lead.utm_campaign, '')) REGEXP %s
          )
        GROUP BY s.sale_date
        ORDER BY s.sale_date
    """
    cursor = connection.cursor()
    cursor.execute(query, ["%presubs%", "%pre-subs%", "%pre subs%", SALE_CAMPAIGN_CODE_REGEXP])
    return [(str(row[0]), int(row[1]), float(row[2]), float(row[3])) for row in cursor.fetchall()]


def store_lead_counts(rows: list[tuple[str, int]], *, source_bucket: str = "facebook-ads") -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_leads_daily (report_date, source_bucket, lead_count, synced_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(report_date, source_bucket) DO UPDATE SET
                lead_count = excluded.lead_count,
                synced_at = CURRENT_TIMESTAMP
            """,
            [(report_date, source_bucket, lead_count) for report_date, lead_count in rows],
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


def store_country_counts(rows: list[tuple[str, str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_leads_by_country (report_date, country, source_bucket, lead_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(report_date, country, source_bucket) DO UPDATE SET
                lead_count = excluded.lead_count
            """,
            rows,
        )


def store_channel_counts(rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_leads_by_channel (report_date, channel, lead_count)
            VALUES (?, ?, ?)
            ON CONFLICT(report_date, channel) DO UPDATE SET
                lead_count = excluded.lead_count
            """,
            rows,
        )


def store_organic_foreign_by_channel(rows: list[tuple[str, str, int]]) -> None:
    with dashboard_app.db() as con:
        con.executemany(
            """
            INSERT INTO crm_organic_foreign_by_channel_daily (report_date, channel, lead_count)
            VALUES (?, ?, ?)
            ON CONFLICT(report_date, channel) DO UPDATE SET
                lead_count = excluded.lead_count
            """,
            rows,
        )


def main() -> int:
    env = load_env_file()
    dashboard_app.init_db()

    connection = _connect(env)
    try:
        leads = fetch_lead_counts(connection)
        organic_leads = fetch_organic_lead_counts(connection)
        countries = fetch_country_counts(connection)
        channels = fetch_channel_counts(connection)
        organic_breakdown = fetch_organic_breakdown(connection)
        organic_foreign_by_channel = fetch_organic_foreign_by_channel(connection)
        sales = fetch_sale_counts(connection)
    finally:
        connection.close()

    store_lead_counts(leads, source_bucket="facebook-ads")
    store_lead_counts(organic_leads, source_bucket="organic")
    store_country_counts(countries)
    store_channel_counts(channels)
    store_organic_breakdown(organic_breakdown)
    store_organic_foreign_by_channel(organic_foreign_by_channel)
    store_sale_counts(sales)

    print(
        f"CRM sync complete: {len(leads)} facebook-ads lead-days, "
        f"{len(organic_leads)} organic lead-days, {len(countries)} country-day rows, "
        f"{len(channels)} channel-day rows, {len(organic_breakdown)} organic-breakdown rows, "
        f"{len(organic_foreign_by_channel)} organic-foreign-channel rows, "
        f"{len(sales)} sale-days."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
