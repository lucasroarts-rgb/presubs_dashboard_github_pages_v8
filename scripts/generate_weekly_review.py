"""Generate the weekly review slide deck (docs/weekly-review.html) from live data.

Pulls everything from dashboard_app.dashboard() - the same function the app
and the public JSON export use - so the deck can never drift from what the
dashboard itself shows. No metric here is computed a second time by hand.

Run manually:
    python scripts/generate_weekly_review.py

In the daily automation, this only fires on the call day (Wednesday) so one
dated snapshot is archived per week - see should_run_today() / main().
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
ARCHIVE_DIR = ROOT / "weekly_reviews"  # outside docs/ - survives generate_public_site.py's docs/ wipe
CALL_WEEKDAY = 2  # Monday=0 ... Wednesday=2


def money(value: float | None) -> str:
    if value is None:
        return "—"
    return f"€{value:,.2f}"


def number(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:,.0f}"


def decimal1(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.1f}"


def pct(value: float | None) -> str:
    if value is None:
        return "—"
    return f"{value:.2f}%"


def signed_pct(value: float | None) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.0f}%"


def pct_change(current: float, previous: float) -> float | None:
    if not previous:
        return None
    return (current - previous) / previous * 100.0


def format_date_short(iso_date: str) -> str:
    d = date.fromisoformat(iso_date)
    return f"{d.strftime('%b')} {d.day}"


def format_date_range(start: str, end: str) -> str:
    s, e = date.fromisoformat(start), date.fromisoformat(end)
    return f"{s.strftime('%b')} {s.day} – {e.strftime('%b')} {e.day}, {e.year}"


def bar_chart_svg(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return '<p class="empty-note">No daily data available yet.</p>'
    values = [max(0.0, float(r["results"] or 0)) for r in rows]
    top = max(values) if values else 0
    ceiling = max(5.0, (int(top / 5) + 1) * 5)
    chart_w, chart_h = 940, 300
    left_pad, right_pad, top_pad, bottom_pad = 60, 40, 40, 50
    plot_w = chart_w - left_pad - right_pad
    plot_h = chart_h - top_pad - bottom_pad
    n = len(rows)
    slot_w = plot_w / n
    bar_w = min(72, slot_w * 0.62)
    best_idx = values.index(max(values)) if values else -1

    grid_lines = []
    axis_labels = []
    for i in range(5):
        frac = i / 4
        y = top_pad + plot_h * (1 - frac)
        grid_lines.append(f'<line class="grid-line" x1="{left_pad}" y1="{y:.1f}" x2="{chart_w - right_pad}" y2="{y:.1f}"/>')
        axis_labels.append(f'<text class="bar-axis-label" x="{left_pad - 8}" y="{y + 4:.1f}" text-anchor="end">{number(ceiling * frac)}</text>')

    bars = []
    for i, (row, value) in enumerate(zip(rows, values)):
        cx = left_pad + slot_w * i + slot_w / 2
        bar_h = (value / ceiling) * plot_h if ceiling else 0
        y = top_pad + plot_h - bar_h
        is_best = i == best_idx and value > 0
        fill = "var(--good)" if is_best else "var(--chart-meta)"
        label_style = ' style="fill:var(--good);font-size:15px;"' if is_best else ""
        axis_style = ' style="font-weight:700;"' if is_best else ""
        bars.append(
            f'<rect x="{cx - bar_w / 2:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{max(bar_h, 2):.1f}" rx="4" fill="{fill}"/>'
            f'<text class="bar-val" x="{cx:.1f}" y="{y - 10:.1f}" text-anchor="middle"{label_style}>{number(value)}</text>'
            f'<text class="bar-axis-label" x="{cx:.1f}" y="{chart_h - bottom_pad + 22:.1f}" text-anchor="middle"{axis_style}>{format_date_short(row["report_date"])}</text>'
        )

    svg = (
        f'<svg viewBox="0 0 {chart_w} {chart_h}" width="100%" height="{chart_h}" role="img" aria-label="Registrations per day">'
        + "".join(grid_lines) + "".join(axis_labels) + "".join(bars)
        + "</svg>"
    )
    return svg


def kpi_card(label: str, value: str, note_html: str) -> str:
    return (
        '<div class="kpi-card">'
        f'<div class="label">{escape(label)}</div>'
        f'<div class="value">{value}</div>'
        f"{note_html}"
        "</div>"
    )


def build_deck(data: dict[str, Any], previous_crm_gap: dict[str, Any], annotations: list[dict[str, Any]]) -> str:
    current = data["current_week"]
    previous = data.get("previous_week")
    totals = data["totals"]
    previous_totals = data.get("previous_totals") or {}
    conv = data["conversion_summary"]
    previous_conv = data.get("previous_conversion_summary") or {}
    crm_gap = data.get("crm_gap") or {}
    daily = data.get("daily_summary") or []
    ads = [a for a in data.get("ads", []) if float(a.get("results") or 0) > 0]
    ads = sorted(ads, key=lambda a: float(a.get("results") or 0), reverse=True)[:4]
    campaigns = sorted(data.get("campaigns", []), key=lambda c: float(c.get("spend") or 0), reverse=True)
    top_campaign = campaigns[0] if campaigns else None

    data_through = daily[-1]["report_date"] if daily else current["week_end"]

    reg_days = len(daily) or 1
    reg_per_day = float(totals.get("results") or 0) / reg_days
    prev_reg_days = 7
    prev_reg_per_day = float(previous_totals.get("results") or 0) / prev_reg_days if previous_totals else None

    cpl_change = pct_change(float(totals.get("cpl") or 0), float(previous_totals.get("cpl") or 0)) if previous_totals.get("cpl") else None
    reg_change = pct_change(float(totals.get("results") or 0), float(previous_totals.get("results") or 0)) if previous_totals.get("results") else None

    meta_reg = float(totals.get("results") or 0)
    crm_leads = float(crm_gap.get("crm_leads") or 0)
    gap_now = pct_change(meta_reg, crm_leads) if crm_leads else None

    prev_meta_reg = float(previous_totals.get("results") or 0)
    prev_crm_leads = float(previous_crm_gap.get("crm_leads") or 0)
    gap_prev = pct_change(prev_meta_reg, prev_crm_leads) if prev_crm_leads else None

    click_lpv_now = (float(conv.get("landing_page_views") or 0) / float(conv.get("link_clicks") or 1)) * 100 if conv.get("link_clicks") else None
    click_lpv_prev = (float(previous_conv.get("landing_page_views") or 0) / float(previous_conv.get("link_clicks") or 1)) * 100 if previous_conv.get("link_clicks") else None

    kpis = "".join(
        [
            kpi_card("Spend", money(totals.get("spend")), f'<div class="note">{escape(current["label"])}</div>'),
            kpi_card(
                "Registrations",
                number(totals.get("results")),
                f'<div class="delta {"good" if (reg_change or 0) >= 0 else "crit"}">{"▲" if (reg_change or 0) >= 0 else "▼"} {decimal1(reg_per_day)}/day{f" (was {decimal1(prev_reg_per_day)}/day)" if prev_reg_per_day is not None else ""}</div>',
            ),
            kpi_card(
                "Average CPL",
                money(totals.get("cpl")),
                f'<div class="delta {"good" if (cpl_change or 0) <= 0 else "crit"}">{"▼" if (cpl_change or 0) <= 0 else "▲"} {signed_pct(cpl_change) if cpl_change is not None else "no prior week"}</div>',
            ),
            kpi_card(
                "Click → LPV",
                pct(click_lpv_now) if click_lpv_now is not None else "—",
                f'<div class="note">{f"was {pct(click_lpv_prev)}" if click_lpv_prev is not None else "no prior week"}</div>',
            ),
            kpi_card(
                "LPV → registration",
                pct(conv.get("conversion_rate")),
                f'<div class="note">{"was " + pct(previous_conv.get("conversion_rate")) if previous_conv.get("conversion_rate") is not None else "no prior week"}</div>',
            ),
            kpi_card(
                "CRM vs Meta gap",
                signed_pct(gap_now) if gap_now is not None else "—",
                f'<div class="note">{f"was {signed_pct(gap_prev)}" if gap_prev is not None else "no CRM data for prior week"}</div>',
            ),
        ]
    )

    timeline_items = ""
    for a in annotations[:5]:
        d = date.fromisoformat(a["event_date"])
        timeline_items += (
            '<div class="tl-item">'
            f'<div class="tl-date">{d.strftime("%b")} {d.day}</div>'
            '<div class="tl-line"><span class="tl-dot"></span></div>'
            '<div class="tl-content">'
            f'<div class="tl-cat">{escape((a.get("category") or "change").title())}</div>'
            f'<div class="tl-title">{escape(a.get("title") or "")}</div>'
            f'<div class="tl-note">{escape(a.get("description") or "")}</div>'
            "</div></div>"
        )

    top_rows = ""
    for i, ad in enumerate(ads, start=1):
        top_rows += (
            "<tr>"
            f'<td class="name"><span class="rank-pill">{i}</span>{escape(ad.get("entity_name") or "")}</td>'
            f'<td class="num">{money(ad.get("spend"))}</td>'
            f'<td class="num">{number(ad.get("results"))}</td>'
            f'<td class="num">{money(ad.get("cost_per_result"))}</td>'
            "</tr>"
        )
    if not top_rows:
        top_rows = '<tr><td colspan="4" class="name">No ads with registrations this week yet.</td></tr>'

    campaign_strip = ""
    if top_campaign:
        campaign_strip = (
            '<div class="campaign-strip">'
            f'<div class="cs-name">Leading campaign: {escape(top_campaign.get("entity_name") or "")}</div>'
            '<div class="cs-figs">'
            f'<span>Registrations <b>{number(top_campaign.get("results"))}</b></span>'
            f'<span>CPL <b>{money(top_campaign.get("cost_per_result"))}</b></span>'
            "</div></div>"
        )

    css = (STATIC_DIR / "weekly-review.html").read_text(encoding="utf-8")
    style_block = css.split("<style>", 1)[1].split("</style>", 1)[0]

    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    return f"""<meta charset="utf-8">
<meta name="google" content="notranslate">
<title>PreSubs — Weekly Review — {escape(current["label"])}</title>
<style>{style_block}</style>

<div class="deck" id="deck" lang="en" translate="no">

  <section class="slide cover active" data-index="0">
    <div class="slide-body">
      <div class="mark">
        <svg viewBox="0 0 24 24" fill="none"><path d="M12 2 20 6v6c0 5.5-3.5 9.4-8 11-4.5-1.6-8-5.5-8-11V6l8-4Z" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/></svg>
        Peasy Anglais · PreSubs
      </div>
      <h1>Weekly acquisition review</h1>
      <p class="cover-sub">Meta Ads, CRM tracking and page conversion — what changed, what improved, and what to watch next.</p>
    </div>
    <div class="cover-period">
      <div>Period in focus<strong>{format_date_range(current["week_start"], current["week_end"])}</strong></div>
      <div>Complete data through<strong>{format_date_short(data_through)}, {date.fromisoformat(data_through).year}</strong></div>
      <div>Funnel<strong>PreSubs · Meta Ads</strong></div>
    </div>
  </section>

  <section class="slide" data-index="1">
    <p class="eyebrow">Week at a glance</p>
    <h2 class="slide-title">This week vs {escape(previous["label"]) if previous else "no prior week"}</h2>
    <p class="slide-sub">{escape(current["label"])}, data through {format_date_short(data_through)}.</p>
    <div class="slide-body">
      <div class="kpi-grid">{kpis}</div>
    </div>
  </section>

  <section class="slide" data-index="2">
    <p class="eyebrow">Daily trend</p>
    <h2 class="slide-title">Registrations per day</h2>
    <p class="slide-sub">{escape(current["label"])}.</p>
    <div class="slide-body">
      <div class="chart-wrap">
        {bar_chart_svg(daily)}
        <div class="chart-legend">
          <span><i style="background:var(--chart-meta)"></i>Registrations/day</span>
          <span><i style="background:var(--good)"></i>Best day</span>
        </div>
      </div>
    </div>
  </section>

  <section class="slide" data-index="3">
    <p class="eyebrow">Tracking health</p>
    <h2 class="slide-title">CRM leads vs Meta-reported registrations</h2>
    <p class="slide-sub">Same scope both sides: PreSubs, Facebook Ads.</p>
    <div class="slide-body">
      <div class="gap-compare">
        <div class="gap-block">
          <div class="gap-eyebrow">{escape(previous["label"]) if previous else "Prior week"}</div>
          <div class="gap-row"><span class="k">Meta registrations</span><span class="v">{number(prev_meta_reg)}</span></div>
          <div class="gap-row"><span class="k">CRM leads</span><span class="v">{number(prev_crm_leads) if prev_crm_leads else "—"}</span></div>
          <div class="gap-result"><span class="k" style="font-size:13px;">Tracking gap</span><span class="v" style="color:{"var(--good)" if (gap_prev or 0) >= -10 else "var(--critical)"}">{signed_pct(gap_prev) if gap_prev is not None else "—"}</span></div>
        </div>
        <div class="gap-arrow">
          <svg viewBox="0 0 24 24" fill="none"><path d="M4 12h16m0 0-6-6m6 6-6 6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span>this week</span>
        </div>
        <div class="gap-block">
          <div class="gap-eyebrow">{escape(current["label"])}</div>
          <div class="gap-row"><span class="k">Meta registrations</span><span class="v">{number(meta_reg)}</span></div>
          <div class="gap-row"><span class="k">CRM leads</span><span class="v">{number(crm_leads) if crm_leads else "—"}</span></div>
          <div class="gap-result"><span class="k" style="font-size:13px;">Tracking gap</span><span class="v" style="color:{"var(--good)" if (gap_now or 0) >= -10 else "var(--critical)"}">{signed_pct(gap_now) if gap_now is not None else "—"}</span></div>
        </div>
      </div>
    </div>
  </section>

  <section class="slide" data-index="4">
    <p class="eyebrow">Landing page</p>
    <h2 class="slide-title">Page conversion, this week vs last</h2>
    <p class="slide-sub">Correlation with the timeline on the next slide, not an isolated cause.</p>
    <div class="slide-body">
      <div class="stat-compare">
        <div class="sc-card">
          <div class="label">Registrations per day</div>
          <div class="sc-track"><span class="sc-old">{decimal1(prev_reg_per_day) if prev_reg_per_day is not None else "—"}</span><span class="sc-arrow-inline">→</span><span class="sc-new">{decimal1(reg_per_day)}</span></div>
          <div class="sc-delta">{signed_pct(pct_change(reg_per_day, prev_reg_per_day)) if prev_reg_per_day else "—"}</div>
        </div>
        <div class="sc-card">
          <div class="label">Click → LPV</div>
          <div class="sc-track"><span class="sc-old">{pct(click_lpv_prev) if click_lpv_prev is not None else "—"}</span><span class="sc-arrow-inline">→</span><span class="sc-new">{pct(click_lpv_now) if click_lpv_now is not None else "—"}</span></div>
          <div class="sc-delta">{f"{(click_lpv_now - click_lpv_prev):+.1f} pts" if click_lpv_now is not None and click_lpv_prev is not None else "—"}</div>
        </div>
        <div class="sc-card">
          <div class="label">LPV → registration</div>
          <div class="sc-track"><span class="sc-old">{pct(previous_conv.get("conversion_rate"))}</span><span class="sc-arrow-inline">→</span><span class="sc-new">{pct(conv.get("conversion_rate"))}</span></div>
          <div class="sc-delta">{signed_pct(pct_change(conv.get("conversion_rate") or 0, previous_conv.get("conversion_rate") or 0)) if previous_conv.get("conversion_rate") else "—"}</div>
        </div>
      </div>
    </div>
  </section>

  <section class="slide" data-index="5">
    <p class="eyebrow">Where spend performed best</p>
    <h2 class="slide-title">Top creatives this week</h2>
    <p class="slide-sub">{escape(current["label"])}, data through {format_date_short(data_through)}.</p>
    <div class="slide-body">
      <table class="top-table">
        <thead><tr><th>Ad</th><th style="text-align:right">Spend</th><th style="text-align:right">Registrations</th><th style="text-align:right">CPL</th></tr></thead>
        <tbody>{top_rows}</tbody>
      </table>
      {campaign_strip}
    </div>
  </section>

  <section class="slide" data-index="6">
    <p class="eyebrow">Timeline</p>
    <h2 class="slide-title">Recent account changes</h2>
    <p class="slide-sub">Most recent changes logged in the dashboard.</p>
    <div class="slide-body">
      <div class="timeline">{timeline_items or '<p class="empty-note">No recent annotations.</p>'}</div>
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
      <span class="slide-count" id="slideCount">1 / 7</span>
    </div>
    <div class="dots" id="dots"></div>
  </div>
</div>

<!-- generated {generated_at} -->
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
  var dots = Array.prototype.slice.call(dotsEl.children);

  function render(index){{
    index = Math.max(0, Math.min(total - 1, index));
    slides.forEach(function(s, i){{
      s.classList.remove('active','prev');
      if (i === index) s.classList.add('active');
      else if (i < index) s.classList.add('prev');
    }});
    dots.forEach(function(d, i){{ d.classList.toggle('active', i === index); }});
    countEl.textContent = (index + 1) + ' / ' + total;
    prevBtn.disabled = index === 0;
    nextBtn.disabled = index === total - 1;
    current = index;
  }}

  window.go = function(delta){{ render(current + delta); }};

  document.addEventListener('keydown', function(e){{
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'PageDown') {{ go(1); e.preventDefault(); }}
    if (e.key === 'ArrowLeft' || e.key === 'PageUp') {{ go(-1); e.preventDefault(); }}
    if (e.key === 'Home') render(0);
    if (e.key === 'End') render(total - 1);
  }});

  render(0);
}})();
</script>
"""


def render_pdf(html: str, pdf_path: Path) -> None:
    """Render the deck to PDF (one slide per landscape A4 page) via headless Chromium."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="load")
            page.emulate_media(media="print")
            page.pdf(path=str(pdf_path), format="A4", landscape=True, print_background=True)
        finally:
            browser.close()


def should_run_today(today: date | None = None) -> bool:
    return (today or date.today()).weekday() == CALL_WEEKDAY


def main(*, force: bool = False) -> int:
    if not force and not should_run_today():
        print("Not the weekly call day (Wednesday) - skipping weekly review generation.")
        return 0

    dashboard_app.init_db()
    data = dashboard_app.dashboard()
    if not data.get("current_week"):
        print("No reporting week available yet - skipping weekly review generation.")
        return 0

    with dashboard_app.db() as con:
        previous_crm_gap: dict[str, Any] = {}
        previous_week = data.get("previous_week")
        if previous_week:
            previous_crm_gap = dashboard_app.crm_gap_summary(
                con, previous_week["week_start"], previous_week["week_end"]
            )

    cfg = dashboard_app.read_dashboard_config()
    annotations = sorted(
        cfg.get("annotations") or [], key=lambda a: a.get("event_date") or "", reverse=True
    )

    html = build_deck(data, previous_crm_gap, annotations)

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_stem = date.today().isoformat()
    (ARCHIVE_DIR / f"{snapshot_stem}.html").write_text(html, encoding="utf-8")
    (STATIC_DIR / "weekly-review.html").write_text(html, encoding="utf-8")

    pdf_path = ARCHIVE_DIR / f"{snapshot_stem}.pdf"
    try:
        render_pdf(html, pdf_path)
    except Exception as pdf_error:
        print(f"WARNING: PDF export skipped ({pdf_error})", file=sys.stderr)

    archives = sorted(
        (p.stem for p in ARCHIVE_DIR.glob("*.html") if p.stem != "index"), reverse=True
    )
    index_rows = "".join(
        f"<tr><td>{stem}</td>"
        f'<td class="num"><a href="{stem}.html">View</a> · <a href="{stem}.html" download>Download HTML</a>'
        + (f' · <a href="{stem}.pdf" download>Download PDF</a>' if (ARCHIVE_DIR / f"{stem}.pdf").exists() else "")
        + "</td></tr>"
        for stem in archives
    )
    index_html = f"""<meta charset="utf-8">
<title>PreSubs — Weekly Review Archive</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#f7f3ea;color:#102a43;padding:48px;}}
  h1{{font-family:Georgia,serif;}}
  table{{border-collapse:collapse;margin-top:20px;}}
  td{{padding:10px 20px 10px 0;border-bottom:1px solid #dcd2ba;}}
  a{{color:#2a6e99;text-decoration:none;}}
  a:hover{{text-decoration:underline;}}
</style>
<h1>Weekly review archive</h1>
<p>One snapshot per week, generated on the call day.</p>
<table>{index_rows}</table>
"""
    (ARCHIVE_DIR / "index.html").write_text(index_html, encoding="utf-8")

    pdf_note = "with PDF" if pdf_path.exists() else "PDF skipped"
    print(f"Weekly review generated: {snapshot_stem} ({pdf_note}, {len(archives)} archived total).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(force="--force" in sys.argv))
