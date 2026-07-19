from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"
DOCS_DIR = ROOT / "docs"

sys.path.insert(0, str(ROOT))
import app as dashboard_app  # noqa: E402


def clean_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): clean_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean_json(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def build_public_index() -> str:
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    html = html.replace('/static/styles.css?v=10.5.0', 'styles.css?v=10.5.0')
    html = html.replace('/static/dashboard.js?v=10.5.0', 'dashboard.js?v=10.5.0')
    html = html.replace('/static/student_profile_data.js?v=10.5.0', 'student_profile_data.js?v=10.5.0')
    html = html.replace('/static/assets/peasy-logo.png', 'assets/peasy-logo.png')
    html = html.replace('<a class="btn" href="/admin">Weekly import</a>', '')
    html = html.replace(
        'No reporting period has been imported. Open <a href="/admin">Weekly import</a>.',
        'No reporting period has been published yet.',
    )
    html = html.replace(
        '<span class="pill info">Links are saved in the database</span>',
        '<span class="pill info">Published from the local database</span>',
    )
    html = html.replace('<a class="btn" href="/admin">Page settings</a>', '')
    html = html.replace('<a class="btn" href="/admin">Edit goals</a>', '')
    html = html.replace('<a class="btn" href="/admin">Configure goals and events</a>', '')
    html = html.replace(
        '<script src="dashboard.js?v=10.5.0"></script>',
        '<script src="data.js?v=10.5.0"></script>\n  <script src="dashboard.js?v=10.5.0"></script>',
    )
    return html


def build_public_javascript() -> str:
    js = (STATIC_DIR / "dashboard.js").read_text(encoding="utf-8")
    js = (
        'const STATIC_DATA = window.PRESUBS_STATIC_DATA || null;\n'
        'const IS_STATIC = Boolean(STATIC_DATA);\n\n'
        + js
    )

    js = js.replace(
        'weeks=await fetch("/api/weeks").then(r=>r.json());',
        'weeks=IS_STATIC ? (STATIC_DATA.weeks||[]) : await fetch("/api/weeks").then(r=>r.json());',
        1,
    )

    old_edit = """async function editPreview(ad){
  const url=prompt(`Paste the Meta preview link for:\\n${ad.entity_name}`,ad.preview_url||"");
  if(url===null) return;
  const response=await fetch(`/api/ads/${ad.id}/preview`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({preview_url:url})});
  if(!response.ok){alert((await response.json()).detail||"Could not save the link.");return}
  await loadDashboard(document.getElementById("weekSelect").value);
}"""
    new_edit = """async function editPreview(ad){
  if(IS_STATIC){
    if(ad?.preview_url) window.open(ad.preview_url,"_blank","noopener");
    return;
  }
  const url=prompt(`Paste the Meta preview link for:\\n${ad.entity_name}`,ad.preview_url||"");
  if(url===null) return;
  const response=await fetch(`/api/ads/${ad.id}/preview`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({preview_url:url})});
  if(!response.ok){alert((await response.json()).detail||"Could not save the link.");return}
  await loadDashboard(document.getElementById("weekSelect").value);
}"""
    if old_edit not in js:
        raise RuntimeError("Could not patch editPreview.")
    js = js.replace(old_edit, new_edit, 1)

    old_preview_column = '{label:"Preview",render:r=>`<button class="link-button ad-link" data-ad="${r.id}">${r.preview_url?"View / edit":"＋ Add ad link"}</button>`}'
    new_preview_column = '{label:"Preview",render:r=>r.preview_url?`<button class="link-button ad-link" data-ad="${r.id}">View ad ↗</button>`:"—"}'
    if old_preview_column not in js:
        raise RuntimeError("Could not patch preview column.")
    js = js.replace(old_preview_column, new_preview_column, 1)

    old_hierarchy_button = '<div><button class="ad-link" data-hierarchy-ad="${ad.id}">${ad.preview_url?"View ad ↗":"＋ Add ad link"}</button></div>'
    new_hierarchy_button = '<div>${ad.preview_url?`<button class="ad-link" data-hierarchy-ad="${ad.id}">View ad ↗</button>`:"—"}</div>'
    if old_hierarchy_button not in js:
        raise RuntimeError("Could not patch hierarchy preview button.")
    js = js.replace(old_hierarchy_button, new_hierarchy_button, 1)

    old_comparison = """  const response=await fetch(`/api/comparison?current_week_id=${currentId}&previous_week_id=${previousId}`);
  const data=await response.json();
  if(!response.ok){alert(data.detail||"Could not load comparison.");return}
  comparisonData=data;"""
    new_comparison = """  let data;
  if(IS_STATIC){
    data=buildClientComparison(currentId,previousId);
    if(!data){alert("The selected reporting periods are not available in this export.");return}
  }else{
    const response=await fetch(`/api/comparison?current_week_id=${currentId}&previous_week_id=${previousId}`);
    data=await response.json();
    if(!response.ok){alert(data.detail||"Could not load comparison.");return}
  }
  comparisonData=data;"""
    if old_comparison not in js:
        raise RuntimeError("Could not patch loadComparison.")
    js = js.replace(old_comparison, new_comparison, 1)

    old_dashboard = """  const url=weekId?`/api/dashboard?week_id=${weekId}`:"/api/dashboard";
  dashboard=await fetch(url).then(r=>r.json());"""
    new_dashboard = """  if(IS_STATIC){
    const selected=weekId || STATIC_DATA.weeks?.[0]?.id;
    dashboard=STATIC_DATA.dashboards?.[String(selected)] || {current_week:null};
  }else{
    const url=weekId?`/api/dashboard?week_id=${weekId}`:"/api/dashboard";
    dashboard=await fetch(url).then(r=>r.json());
  }"""
    if old_dashboard not in js:
        raise RuntimeError("Could not patch loadDashboard.")
    js = js.replace(old_dashboard, new_dashboard, 1)

    return js


def main() -> int:
    dashboard_app.init_db()
    with dashboard_app.db() as connection:
        dashboard_app.backfill_relations(connection)

    weeks = dashboard_app.list_weeks()
    dashboards: dict[str, Any] = {}
    for week in weeks:
        week_id = int(week["id"])
        dashboards[str(week_id)] = dashboard_app.dashboard(week_id)


    payload = clean_json(
        {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "weeks": weeks,
            "dashboards": dashboards,
            "config": dashboard_app.read_dashboard_config(),
        }
    )

    if DOCS_DIR.exists():
        shutil.rmtree(DOCS_DIR)
    DOCS_DIR.mkdir(parents=True)

    (DOCS_DIR / "index.html").write_text(build_public_index(), encoding="utf-8")
    (DOCS_DIR / "styles.css").write_text(
        (STATIC_DIR / "styles.css").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (DOCS_DIR / "dashboard.js").write_text(
        build_public_javascript(),
        encoding="utf-8",
    )
    (DOCS_DIR / "student_profile_data.js").write_text(
        (STATIC_DIR / "student_profile_data.js").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    if (STATIC_DIR / "assets").exists():
        shutil.copytree(STATIC_DIR / "assets", DOCS_DIR / "assets")

    json_text = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    )
    (DOCS_DIR / "data.js").write_text(
        "window.PRESUBS_STATIC_DATA=" + json_text + ";\n",
        encoding="utf-8",
    )
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")

    latest = dashboards.get(str(weeks[0]["id"])) if weeks else None
    summary = {
        "generated_at": payload["generated_at"],
        "weeks": len(weeks),
        "campaigns_latest": len((latest or {}).get("campaigns", [])),
        "adsets_latest": len((latest or {}).get("adsets", [])),
        "ads_latest": len((latest or {}).get("ads", [])),
        "page_groups_latest": len((latest or {}).get("page_groups", [])),
        "daily_ad_rows_latest": len((latest or {}).get("daily_ads", [])),
        "daily_ad_rows_published": sum(
            len(item.get("daily_ads", [])) for item in dashboards.values()
        ),
        "daily_days_published": sum(
            len(item.get("daily_summary", [])) for item in dashboards.values()
        ),
        "config_updated_at": payload.get("config", {}).get("updated_at"),
        "annotations": len(payload.get("config", {}).get("annotations", [])),
        "student_profile_responses": 2115,
    }
    (DOCS_DIR / "export-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("")
    print("Public site generated successfully.")
    print(f"Folder: {DOCS_DIR}")
    print(f"Reporting periods: {len(weeks)}")
    print("The public dashboard data was exported; the SQLite database and source spreadsheets remain local.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
