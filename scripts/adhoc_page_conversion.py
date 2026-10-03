"""Ad-hoc: pageviews per landing-page variant (GA4) vs real leads (CRM
launch17db.leads_l21, via url_first) to find which page variant (A/B/C/D...)
converted best per launch."""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.automate_meta import load_env_file  # noqa: E402
from scripts.sync_ga4 import _client  # noqa: E402
import pymysql  # noqa: E402


def fetch_pageviews(client, property_id: str) -> dict[str, int]:
    from google.analytics.data_v1beta.types import DateRange, Dimension, Metric, RunReportRequest, Filter, FilterExpression

    dim_filter = FilterExpression(
        filter=Filter(
            field_name="pagePath",
            string_filter=Filter.StringFilter(
                match_type=Filter.StringFilter.MatchType.CONTAINS,
                value="sign-ups",
                case_sensitive=False,
            ),
        )
    )
    request = RunReportRequest(
        property=f"properties/{property_id}",
        dimensions=[Dimension(name="pagePath")],
        metrics=[Metric(name="screenPageViews")],
        date_ranges=[DateRange(start_date="2025-01-01", end_date="today")],
        dimension_filter=dim_filter,
        limit=500,
    )
    response = client.run_report(request)
    out: dict[str, int] = {}
    for row in response.rows:
        path = row.dimension_values[0].value
        views = int(row.metric_values[0].value or 0)
        out[path] = out.get(path, 0) + views
    return out


SLUG_RE = re.compile(r"(l\d{2}-sign-ups-[a-z0-9]+)", re.IGNORECASE)


def normalize_slug(path: str) -> str | None:
    m = SLUG_RE.search(path.lower())
    return m.group(1) if m else None


def main() -> int:
    env = load_env_file()
    try:
        client, property_id = _client(env)
    except Exception as e:
        print("GA4 error:", e)
        return 1
    pageviews_raw = fetch_pageviews(client, property_id)

    pageviews: dict[str, int] = defaultdict(int)
    for path, views in pageviews_raw.items():
        slug = normalize_slug(path)
        if slug:
            pageviews[slug] += views

    conn = pymysql.connect(
        host=env["CRM_MYSQL_HOST"], user=env["CRM_MYSQL_USER"],
        password=env["CRM_MYSQL_PASSWORD"], charset="utf8mb4",
    )
    cur = conn.cursor()
    cur.execute(
        "SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(url_first,'/',4),'/',-1) AS slug, COUNT(*) "
        "FROM launch17db.leads_l21 WHERE url_first LIKE '%sign-ups%' GROUP BY slug"
    )
    leads: dict[str, int] = {}
    for slug, cnt in cur.fetchall():
        leads[slug.lower()] = leads.get(slug.lower(), 0) + cnt
    conn.close()

    print(f"{'page':30s} {'pageviews':>10s} {'leads':>8s} {'conv%':>8s}")
    all_slugs = sorted(set(pageviews) | set(leads))
    for slug in all_slugs:
        pv = pageviews.get(slug, 0)
        ld = leads.get(slug, 0)
        conv = (ld / pv * 100) if pv else 0
        print(f"{slug:30s} {pv:10d} {ld:8d} {conv:7.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
