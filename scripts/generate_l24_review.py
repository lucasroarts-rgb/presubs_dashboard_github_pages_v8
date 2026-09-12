"""Generate the L24 launch review slide deck (static/l24-review.html).

Entirely separate from generate_weekly_review.py (the PreSubs weekly
deck) per the user's explicit instruction not to mix the two - own
output file, own archive directory (l24_reviews/, not weekly_reviews/),
own data source (dashboard_app.l24_launch_summary()), own cadence
(Monday/Wednesday/Friday, not Wednesday-only).

The visual style is borrowed read-only from static/weekly-review.html's
<style> block (same brand look), but this script never writes to that
file - the two decks stay fully independent outputs.

Run manually:
    python scripts/generate_l24_review.py --force
"""

from __future__ import annotations

import sys
from datetime import date, datetime, timezone
from html import escape
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app as dashboard_app  # noqa: E402

STATIC_DIR = ROOT / "static"
ARCHIVE_DIR = ROOT / "l24_reviews"  # outside docs/ - survives generate_public_site.py's docs/ wipe
CALL_WEEKDAYS = {0, 2, 4}  # Monday, Wednesday, Friday


def money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"€{value:,.2f}"


def number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}%"


def kpi_card(label: str, value: str, note_html: str = "") -> str:
    return (
        '<article class="kpi">'
        f'<div class="kpi-label">{escape(label)}</div>'
        f'<div class="kpi-value">{value}</div>'
        f'{note_html}'
        "</article>"
    )


def should_run_today(today: date | None = None) -> bool:
    return (today or date.today()).weekday() in CALL_WEEKDAYS


def adset_breakdown(creatives: list[dict[str, Any]]) -> list[dict[str, Any]]:
    totals: dict[str, dict[str, float]] = {}
    for ad in creatives:
        adset = ad.get("adset_name") or "—"
        bucket = totals.setdefault(adset, {"spend": 0.0, "leads": 0, "clicks": 0, "impressions": 0})
        bucket["spend"] += ad["spend"]
        bucket["leads"] += ad["leads"]
        bucket["clicks"] += ad["clicks"]
        bucket["impressions"] += ad["impressions"]
    rows = []
    for adset, totals_row in totals.items():
        cpl = round(totals_row["spend"] / totals_row["leads"], 2) if totals_row["leads"] else None
        ctr = round(totals_row["clicks"] / totals_row["impressions"] * 100, 2) if totals_row["impressions"] else None
        rows.append({"adset_name": adset, "spend": round(totals_row["spend"], 2), "leads": int(totals_row["leads"]), "cpl": cpl, "ctr": ctr})
    return sorted(rows, key=lambda r: r["spend"], reverse=True)


def build_suggestions(creatives: list[dict[str, Any]], adsets: list[dict[str, Any]], overall_cpl: float | None, lpv_to_lead_pct: float | None) -> list[str]:
    """Data-grounded observations only - every line traces to a real
    number computed from this sync's own data, nothing invented."""
    suggestions: list[str] = []
    ads_with_leads = [a for a in creatives if a["leads"] > 0]

    if overall_cpl:
        underperforming = [a for a in adsets if a["cpl"] and a["cpl"] > overall_cpl * 1.5]
        for adset in underperforming:
            suggestions.append(
                f"Ad set \"{adset['adset_name']}\" está com CPL {money(adset['cpl'])} "
                f"({round(adset['cpl']/overall_cpl,1)}x a média geral de {money(overall_cpl)}) - candidato a revisão ou pausa."
            )

    if ads_with_leads:
        avg_ctr = sum(a["ctr"] for a in ads_with_leads) / len(ads_with_leads)
        for ad in ads_with_leads:
            if overall_cpl and ad["ctr"] > avg_ctr * 1.3 and ad["cpl"] and ad["cpl"] > overall_cpl * 1.3:
                suggestions.append(
                    f"{ad['ad_name']} tem CTR acima da média ({pct(ad['ctr'])}) mas CPL alto ({money(ad['cpl'])}) - "
                    "o criativo atrai clique mas não converte; revisar alinhamento oferta/página."
                )

    if lpv_to_lead_pct is not None and lpv_to_lead_pct < 20:
        suggestions.append(
            f"Conversão da página (LPV → Lead) está em {pct(lpv_to_lead_pct)} - abaixo do que se espera de uma "
            "landing page de captura direta; vale revisar formulário/oferta na página."
        )

    if not suggestions:
        suggestions.append("Nenhum padrão de baixa performance destacado ainda - amostra ainda pequena para conclusões.")
    return suggestions


def build_deck(l24: dict[str, Any]) -> str:
    targets = l24.get("targets") or {}
    creatives = l24.get("creatives") or []
    adsets = adset_breakdown(creatives)

    kpis = "".join(
        [
            kpi_card("Meta spend", money(l24.get("cold_spend")), '<div class="note">COLD campaign</div>'),
            kpi_card("Meta leads", number(l24.get("cold_leads")), '<div class="note">Pixel-reported</div>'),
            kpi_card("Meta CPL", money(l24.get("cold_cpl")), '<div class="note">Spend / Meta leads</div>'),
            kpi_card("CRM leads", number(l24.get("crm_leads_total")), '<div class="note">[L21] tag, ground truth</div>'),
            kpi_card("CRM CPL", money(l24.get("crm_cpl")), '<div class="note">Spend / CRM leads</div>'),
            kpi_card("Click → LPV", pct(l24.get("click_to_lpv_pct")), '<div class="note">Page conversion (step 1)</div>'),
            kpi_card("LPV → Lead", pct(l24.get("lpv_to_lead_pct")), '<div class="note">Page conversion (step 2)</div>'),
        ]
    )

    adset_rows = "".join(
        f"<tr><td class='name'>{escape(a['adset_name'])}</td>"
        f"<td class='num'>{money(a['spend'])}</td>"
        f"<td class='num'>{number(a['leads'])}</td>"
        f"<td class='num'>{money(a['cpl']) if a['cpl'] is not None else '—'}</td>"
        f"<td class='num'>{pct(a['ctr']) if a['ctr'] is not None else '—'}</td></tr>"
        for a in adsets
    ) or "<tr><td colspan='5' class='name'>No adset data synced yet.</td></tr>"

    ads_with_leads = sorted([a for a in creatives if a["leads"] > 0], key=lambda a: a["cpl"])
    best = ads_with_leads[:5]
    worst = list(reversed(ads_with_leads[-5:])) if len(ads_with_leads) > 5 else list(reversed(ads_with_leads))

    def creative_rows(rows: list[dict[str, Any]]) -> str:
        return "".join(
            f"<tr><td class='name'>{escape(a['ad_name'] or '')}</td>"
            f"<td class='name'>{escape(a['adset_name'] or '')}</td>"
            f"<td class='num'>{money(a['cpl'])}</td>"
            f"<td class='num'>{pct(a['ctr'])}</td>"
            f"<td class='num'>{money(a['spend'])}</td>"
            f"<td class='num'>{number(a['leads'])}</td></tr>"
            for a in rows
        ) or "<tr><td colspan='6' class='name'>No creatives with leads yet.</td></tr>"

    suggestions = build_suggestions(creatives, adsets, l24.get("cold_cpl"), l24.get("lpv_to_lead_pct"))
    suggestions_html = "".join(f"<li>{escape(s)}</li>" for s in suggestions)

    css = (STATIC_DIR / "weekly-review.html").read_text(encoding="utf-8")
    style_block = css.split("<style>", 1)[1].split("</style>", 1)[0]

    today_label = date.today().strftime("%d %b %Y")
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<meta charset="utf-8">
<meta name="google" content="notranslate">
<title>L24 — Launch Review — {escape(today_label)}</title>
<style>{style_block}</style>

<div class="deck" id="deck" lang="en" translate="no">

  <section class="slide cover active" data-index="0">
    <div class="slide-body">
      <div class="mark">
        <svg viewBox="0 0 24 24" fill="none"><path d="M12 2 20 6v6c0 5.5-3.5 9.4-8 11-4.5-1.6-8-5.5-8-11V6l8-4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
        Peasy Anglais · L24
      </div>
      <h1>L24 launch review</h1>
      <p class="cover-sub">Page conversion, cost per lead, where leads come from, and creative performance - what's working, what isn't.</p>
    </div>
    <div class="cover-period">
      <div>Snapshot date<strong>{escape(today_label)}</strong></div>
      <div>CPL-capturing window<strong>{escape(targets.get("cpl_capturing_start",""))} – {escape(targets.get("cpl_capturing_end",""))}</strong></div>
      <div>Funnel<strong>L24 · Meta Ads (COLD)</strong></div>
    </div>
  </section>

  <section class="slide" data-index="1">
    <p class="eyebrow">Snapshot</p>
    <h2 class="slide-title">Spend, leads, page conversion</h2>
    <p class="slide-sub">Cumulative since launch start.</p>
    <div class="slide-body">
      <div class="kpi-grid">{kpis}</div>
    </div>
  </section>

  <section class="slide" data-index="2">
    <p class="eyebrow">Where leads come from</p>
    <h2 class="slide-title">Performance by ad set</h2>
    <p class="slide-sub">COLD campaign, all 6 ad sets.</p>
    <div class="slide-body">
      <table class="top-table"><thead><tr><th>Ad set</th><th class="num">Spend</th><th class="num">Leads</th><th class="num">CPL</th><th class="num">CTR</th></tr></thead><tbody>{adset_rows}</tbody></table>
    </div>
  </section>

  <section class="slide" data-index="3">
    <p class="eyebrow">Creative performance</p>
    <h2 class="slide-title">Best creatives (lowest CPL)</h2>
    <p class="slide-sub">Ads with at least one lead, sorted by CPL.</p>
    <div class="slide-body">
      <table class="top-table"><thead><tr><th>Ad</th><th>Ad set</th><th class="num">CPL</th><th class="num">CTR</th><th class="num">Spend</th><th class="num">Leads</th></tr></thead><tbody>{creative_rows(best)}</tbody></table>
    </div>
  </section>

  <section class="slide" data-index="4">
    <p class="eyebrow">Creative performance</p>
    <h2 class="slide-title">Worst creatives (highest CPL)</h2>
    <p class="slide-sub">Ads with at least one lead, sorted by CPL descending.</p>
    <div class="slide-body">
      <table class="top-table"><thead><tr><th>Ad</th><th>Ad set</th><th class="num">CPL</th><th class="num">CTR</th><th class="num">Spend</th><th class="num">Leads</th></tr></thead><tbody>{creative_rows(worst)}</tbody></table>
    </div>
  </section>

  <section class="slide" data-index="5">
    <p class="eyebrow">Recommendations</p>
    <h2 class="slide-title">Improvement suggestions</h2>
    <p class="slide-sub">Data-grounded, from this snapshot only - not proof, a starting point for review.</p>
    <div class="slide-body">
      <ul class="suggestion-list">{suggestions_html}</ul>
    </div>
  </section>

  <button class="click-zone left" aria-label="Previous slide" onclick="go(-1)"></button>
  <button class="click-zone right" aria-label="Next slide" onclick="go(1)"></button>

  <div class="chrome">
    <div class="nav-btns">
      <button class="nav-btn" id="prevBtn" aria-label="Previous slide" onclick="go(-1)">
        <svg viewBox="0 0 24 24" fill="none"><path d="M15 5 8 12l7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <button class="nav-btn" id="nextBtn" aria-label="Next slide" onclick="go(1)">
        <svg viewBox="0 0 24 24" fill="none"><path d="M9 5l7 7-7 7" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
      </button>
      <span class="slide-count" id="slideCount">1 / 6</span>
    </div>
    <div class="dots" id="dots"></div>
  </div>
</div>

<!-- generated {generated_at} -->
<style>.suggestion-list{{font-size:16px;line-height:1.7;padding-left:22px}}.suggestion-list li{{margin-bottom:14px}}</style>
<script>
(function(){{
  var slides = Array.prototype.slice.call(document.querySelectorAll('.slide'));
  var total = slides.length;
  var current = 0;
  var dotsEl = document.getElementById('dots');
  var countEl = document.getElementById('slideCount');
  var prevBtn = document.getElementById('prevBtn');
  var nextBtn = document.getElementById('nextBtn');

  slides.forEach(function(_, i){{
    var d = document.createElement('button');
    d.className = 'dot' + (i === 0 ? ' active' : '');
    d.setAttribute('aria-label', 'Go to slide ' + (i+1));
    d.onclick = function(){{ render(i); }};
    dotsEl.appendChild(d);
  }});

  function render(i){{
    current = Math.max(0, Math.min(total - 1, i));
    slides.forEach(function(s, idx){{ s.classList.toggle('active', idx === current); }});
    Array.prototype.forEach.call(dotsEl.children, function(d, idx){{ d.classList.toggle('active', idx === current); }});
    countEl.textContent = (current + 1) + ' / ' + total;
    prevBtn.disabled = current === 0;
    nextBtn.disabled = current === total - 1;
  }}
  window.go = function(delta){{ render(current + delta); }};
  document.addEventListener('keydown', function(e){{
    if(e.key === 'ArrowRight') go(1);
    if(e.key === 'ArrowLeft') go(-1);
  }});
  render(0);
}})();
</script>
"""


def main(*, force: bool = False) -> int:
    if not force and not should_run_today():
        print("Not an L24 review day (Mon/Wed/Fri) - skipping.")
        return 0

    dashboard_app.init_db()
    with dashboard_app.db() as con:
        l24 = dashboard_app.l24_launch_summary(con)

    if not l24.get("available"):
        print("No L24 data synced yet - skipping review generation.")
        return 0

    html = build_deck(l24)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_stem = date.today().isoformat()
    (ARCHIVE_DIR / f"{snapshot_stem}.html").write_text(html, encoding="utf-8")
    (STATIC_DIR / "l24-review.html").write_text(html, encoding="utf-8")

    archives = sorted((p.stem for p in ARCHIVE_DIR.glob("*.html") if p.stem != "index"), reverse=True)
    index_rows = "".join(
        f"<tr><td>{stem}</td><td class='num'><a href='{stem}.html'>View</a> · <a href='{stem}.html' download>Download</a></td></tr>"
        for stem in archives
    )
    index_html = f"""<meta charset="utf-8">
<title>L24 — Launch Review Archive</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f3ea;color:#102a43;padding:48px;}}
  h1{{font-family:Georgia,serif;}}
  table{{border-collapse:collapse;margin-top:20px;}}
  td{{padding:10px 20px 10px 0;border-bottom:1px solid #dcd2ba;}}
  a{{color:#2a6e99;text-decoration:none;}}
  a:hover{{text-decoration:underline;}}
</style>
<h1>L24 review archive</h1>
<p>One snapshot per Mon/Wed/Fri.</p>
<table>{index_rows}</table>
"""
    (ARCHIVE_DIR / "index.html").write_text(index_html, encoding="utf-8")

    print(f"L24 review generated: {snapshot_stem} ({len(archives)} archived total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(force="--force" in sys.argv))
