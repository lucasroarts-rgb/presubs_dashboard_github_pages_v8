"""Ad-hoc (not part of daily sync): which capture ads (utm_content) generated
the most Confirmed sales, per past launch (L21 onward).

Attribution: for each Confirmed sale, find the matching lead by email whose
utm_campaign matches a launch code (l21/l22/l23/l24 or cplNN), and take that
email's earliest non-blank utm_content as the attributed ad. Same join
pattern as fetch_sale_counts() in sync_crm.py. Email is only ever a JOIN key
here, never selected - no PII leaves the CRM.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.automate_meta import load_env_file  # noqa: E402
import pymysql  # noqa: E402


def connect(env):
    return pymysql.connect(
        host=env["CRM_MYSQL_HOST"],
        user=env["CRM_MYSQL_USER"],
        password=env["CRM_MYSQL_PASSWORD"],
        database=env["CRM_MYSQL_DATABASE"],
        connect_timeout=15,
        charset="utf8mb4",
    )


LAUNCH_CODE_REGEXP = r"(^|[^a-z0-9])(l1[8-9]|l2[0-4]|cpl1[8-9]|cpl2[0-4])([^0-9]|$)"


QUERY = """
SELECT
    launch_lead.launch_code AS launch,
    COALESCE(NULLIF(TRIM(first_content.utm_content), ''), '(sem utm_content)') AS ad_name,
    COUNT(*) AS sale_count,
    COALESCE(SUM(s.price_full), 0) AS revenue_full,
    COALESCE(SUM(s.total_paid), 0) AS revenue_net
FROM sales s
JOIN (
    -- earliest lead row per email that has a launch-coded utm_campaign, to tag the launch
    SELECT l1.email,
           REPLACE(LOWER(REGEXP_SUBSTR(l1.utm_campaign, 'l1[8-9]|l2[0-4]|cpl1[8-9]|cpl2[0-4]')), 'cpl', 'l') AS launch_code
    FROM leads l1
    JOIN (
        SELECT email, MIN(data) AS first_date
        FROM leads
        WHERE utm_campaign REGEXP %s
        GROUP BY email
    ) fl ON fl.email = l1.email AND fl.first_date = l1.data
    WHERE l1.utm_campaign REGEXP %s
    GROUP BY l1.email, launch_code
) launch_lead ON launch_lead.email = s.email
LEFT JOIN (
    -- earliest lead row per email that has a non-blank utm_content, to tag the ad
    SELECT l2.email, l2.utm_content
    FROM leads l2
    JOIN (
        SELECT email, MIN(data) AS first_date
        FROM leads
        WHERE utm_content IS NOT NULL AND utm_content <> ''
        GROUP BY email
    ) fc ON fc.email = l2.email AND fc.first_date = l2.data
    GROUP BY l2.email
) first_content ON first_content.email = s.email
WHERE s.sale_status = 'Confirmed'
GROUP BY launch, ad_name
HAVING ad_name NOT REGEXP '^[0-9]+$'
   AND LOWER(ad_name) NOT REGEXP '^(unic|sales|homepage|bio|live|audrey|ccm|ad\\.name|invitation|arrastao)'
   AND LOWER(ad_name) NOT REGEXP '^[0-9]+[a-z]*(top)$'
ORDER BY launch, sale_count DESC
"""
# Excludes clearly-non-ad utm_content noise: bare numbers, generic UTM tags
# ("unic", "sales", "homepage", "bio", "live", "ccm", "Audrey"), the literal
# unsubstituted macro "ad.name", and date-slot tags (e.g. "9junetop",
# "10morningtop"). Kept: anything matching real ad-naming conventions
# (AD####, RLS####, adNNN, bare numeric-code names from older launches
# excluded above only when *purely* numeric with no other text).


_COPY_SUFFIX_RE = re.compile(r"[\s\-_]*(copy|c[o0]pia|c.pia)(\s*\d*)$", re.IGNORECASE)
_PCTENC_RE = re.compile(r"%[0-9A-Fa-f]{2}")


def normalize_ad_name(name: str) -> str:
    """Collapse URL-encoding / duplicate-object variants of the same creative
    ('AD429+-++RLS...' vs 'AD429 - RLS... — Cópia') into one grouping key."""
    n = name.replace("+", " ")
    n = _PCTENC_RE.sub(" ", n)
    n = n.replace("�", " ")
    n = _COPY_SUFFIX_RE.sub("", n)
    n = re.sub(r"\s+", " ", n).strip().lower()
    return n


def main() -> int:
    env = load_env_file()
    conn = connect(env)
    try:
        cur = conn.cursor()
        cur.execute(QUERY, [LAUNCH_CODE_REGEXP, LAUNCH_CODE_REGEXP])
        rows = cur.fetchall()
    finally:
        conn.close()

    if not rows:
        print("Nenhuma linha retornada - regex ou schema pode precisar ajuste.")
        return 0

    # merge URL-encoded / "- Copy" / "- Copia" duplicate-object variants of
    # the same creative so ranking reflects the real ad, not the object id
    grouped = defaultdict(lambda: {"display": None, "count": 0, "full": 0.0, "net": 0.0})
    for launch, ad_name, sale_count, revenue_full, revenue_net in rows:
        key = (launch, normalize_ad_name(ad_name))
        g = grouped[key]
        if g["display"] is None or len(ad_name) > len(g["display"]):
            g["display"] = ad_name
        g["count"] += sale_count
        g["full"] += float(revenue_full)
        g["net"] += float(revenue_net)

    merged_rows = sorted(
        ((launch, g["display"], g["count"], g["full"], g["net"]) for (launch, _), g in grouped.items()),
        key=lambda r: (r[0] or "", -r[2]),
    )

    current_launch = None
    for launch, ad_name, sale_count, revenue_full, revenue_net in merged_rows:
        if launch != current_launch:
            print(f"\n=== {launch.upper() if launch else '(sem launch)'} ===")
            current_launch = launch
        print(f"  {ad_name:45s}  vendas={sale_count:3d}  full=EUR{revenue_full:9.2f}  net=EUR{revenue_net:9.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
