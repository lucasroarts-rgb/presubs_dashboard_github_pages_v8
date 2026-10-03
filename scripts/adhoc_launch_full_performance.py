"""Ad-hoc (not part of daily sync): full per-launch performance - real lead
volume AND real confirmed sales, per ad, for L18-L24.

Data-source map (this is the part that's easy to get wrong):
  L18 -> launch17db.leads_l18
  L19 -> launch17db.leads_l19
  L20 -> launch17db.leads_l20
  L21, L22, L23, L24 -> launch17db.leads_l21  (one rolling table; the name is
  legacy and was never renamed past L21)
Each table also keeps collecting stragglers from older launches' pages long
after that launch ended, so the launch is identified by the landing-page slug
in url_first (e.g. "l23-sign-ups-a"), NOT by table alone and NOT by date.
presubs_db.leads is NOT a usable lead source for any launch - it holds only a
small unrepresentative slice (151 rows for L22 vs the real 20k).

Email is only ever a JOIN key, never selected/stored - no PII leaves the CRM.
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
        charset="utf8mb4",
    )


LAUNCH_TABLE = {
    "l18": "launch17db.leads_l18",
    "l19": "launch17db.leads_l19",
    "l20": "launch17db.leads_l20",
    "l21": "launch17db.leads_l21",
    "l22": "launch17db.leads_l21",
    "l23": "launch17db.leads_l21",
    "l24": "launch17db.leads_l21",
}

_JUNK_EXACT = {
    "unic", "sales", "homepage", "bio", "live", "audrey", "ccm", "ad.name",
    "invitation", "arrastao", "",
}
_COPY_SUFFIX_RE = re.compile(r"[\s\-_]*(copy|c[o0]pia|c.pia)(\s*\d*)$", re.IGNORECASE)
_PCTENC_RE = re.compile(r"%[0-9A-Fa-f]{2}")


def normalize_ad_name(name: str) -> str:
    n = (name or "").replace("+", " ")
    n = _PCTENC_RE.sub(" ", n)
    n = n.replace("�", " ")
    n = _COPY_SUFFIX_RE.sub("", n)
    return re.sub(r"\s+", " ", n).strip()


def is_junk(name: str) -> bool:
    low = name.lower()
    return (
        low in _JUNK_EXACT
        or low.isdigit()
        or bool(re.match(r"^\d+[a-z]*top$", low))
        or low.startswith("unic")
        or low.startswith("sales")
    )


def main() -> int:
    env = load_env_file()
    conn = connect(env)
    summary = []
    try:
        cur = conn.cursor()
        for code, table in LAUNCH_TABLE.items():
            pattern = f"%{code}-sign-ups%"

            cur.execute(
                f"SELECT utm_content, COUNT(*) FROM {table} WHERE url_first LIKE %s GROUP BY utm_content",
                [pattern],
            )
            lead_rows = cur.fetchall()
            total_leads = sum(c for _, c in lead_rows)

            lead_by_ad: dict[str, int] = defaultdict(int)
            for raw, cnt in lead_rows:
                norm = normalize_ad_name(raw)
                if not is_junk(norm):
                    lead_by_ad[norm] += cnt

            cur.execute(
                f"""
                SELECT lead.utm_content, COUNT(*), COALESCE(SUM(s.price_full),0)
                FROM presubs_db.sales s
                JOIN (
                    SELECT l1.email, l1.utm_content
                    FROM {table} l1
                    JOIN (
                        SELECT email, MIN(data) AS first_date FROM {table}
                        WHERE url_first LIKE %s GROUP BY email
                    ) fl ON fl.email = l1.email AND fl.first_date = l1.data
                    WHERE l1.url_first LIKE %s
                    GROUP BY l1.email, l1.utm_content
                ) lead ON lead.email = s.email
                WHERE s.sale_status = 'Confirmed'
                GROUP BY lead.utm_content
                """,
                [pattern, pattern],
            )
            sale_rows = cur.fetchall()
            sales_by_ad: dict[str, list] = defaultdict(lambda: [0, 0.0])
            total_sales = 0
            total_revenue = 0.0
            for raw, sc, rf in sale_rows:
                norm = normalize_ad_name(raw)
                if is_junk(norm):
                    norm = "(sem tag de anuncio)"
                sales_by_ad[norm][0] += sc
                sales_by_ad[norm][1] += float(rf)
                total_sales += sc
                total_revenue += float(rf)

            conv = (total_sales / total_leads * 100) if total_leads else 0
            rev_per_lead = (total_revenue / total_leads) if total_leads else 0
            summary.append((code, total_leads, total_sales, total_revenue, conv, rev_per_lead))

            print(f"\n{'='*78}")
            print(f"{code.upper()}  [{table}]  {total_leads} leads · {total_sales} vendas · EUR{total_revenue:,.0f} · conv {conv:.2f}% · EUR{rev_per_lead:.2f}/lead")
            print(f"{'='*78}")
            print("  anuncios com >=200 leads, ordenado por RECEITA POR LEAD (qualidade, nao volume):")
            ranked = []
            for name, leads_ct in lead_by_ad.items():
                if leads_ct < 200:
                    continue
                sc, rf = sales_by_ad.get(name, [0, 0.0])
                ranked.append((rf / leads_ct, name, leads_ct, sc, rf))
            for rpl, name, leads_ct, sc, rf in sorted(ranked, reverse=True)[:8]:
                cv = (sc / leads_ct * 100) if leads_ct else 0
                print(f"    EUR{rpl:6.2f}/lead  {name[:46]:46s} leads={leads_ct:6d} vendas={sc:3d} conv={cv:4.2f}%")
            if not ranked:
                print("    (nenhum anuncio com volume suficiente)")
    finally:
        conn.close()

    print(f"\n\n{'='*78}\nRESUMO\n{'='*78}")
    print(f"{'launch':8s} {'leads':>8s} {'vendas':>7s} {'receita':>12s} {'conv%':>7s} {'EUR/lead':>9s}")
    for code, leads, sales, rev, conv, rpl in summary:
        print(f"{code.upper():8s} {leads:8d} {sales:7d} {rev:12,.0f} {conv:6.2f}% {rpl:8.2f}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
