from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import hashlib
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
    html = html.replace('/static/styles.css?v=10.6.4.2', 'styles.css?v=10.6.4.2')
    html = html.replace('/static/dashboard.js?v=10.6.4.2', 'dashboard.js?v=10.6.4.2')
    html = html.replace('/static/student_profile_data.js?v=10.6.4.2', 'student_profile_data.js?v=10.6.4.2')
    html = html.replace('/static/assets/peasy-logo.png', 'assets/peasy-logo.png')
    html = html.replace('/static/weekly-review.html', 'weekly-review.html')
    html = html.replace('/weekly-reviews/index.html', 'weekly-reviews/index.html')
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

    password_hash = (
        hashlib.sha256(dashboard_app.DASHBOARD_PASSWORD.encode("utf-8")).hexdigest()
        if dashboard_app.DASHBOARD_PASSWORD
        else ""
    )
    if password_hash:
        html = html.replace('<body data-active-view="auditOverview">', GATE_OVERLAY_HTML, 1)
        html = html.replace(
            '<script src="dashboard.js?v=10.6.4.2"></script>',
            GATE_LOADER_SCRIPT.replace("__PASSWORD_HASH__", password_hash),
        )
    else:
        html = html.replace(
            '<script src="dashboard.js?v=10.6.4.2"></script>',
            '<script src="data.js?v=10.6.4.2"></script>\n  <script src="dashboard.js?v=10.6.4.2"></script>',
        )
    return html


GATE_OVERLAY_HTML = """<body data-active-view="auditOverview">
  <div id="dashLockOverlay" style="position:fixed;inset:0;z-index:99999;background:#0c0f1c;display:flex;align-items:center;justify-content:center;font-family:inherit">
    <form id="dashLockForm" style="background:#161c30;border:1px solid #2a3350;border-radius:14px;padding:32px 28px;width:min(340px,90vw);box-shadow:0 20px 60px rgba(0,0,0,.4)">
      <div style="font-size:15px;font-weight:800;color:#f5f6fb;margin-bottom:6px">PreSubs Dashboard</div>
      <div style="font-size:12px;color:#9aa3bd;margin-bottom:16px">Digite a senha para acessar.</div>
      <input id="dashLockInput" type="password" placeholder="Senha" autocomplete="current-password" autofocus style="width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid #2a3350;background:#0c0f1c;color:#f5f6fb;font-size:14px;margin-bottom:12px" />
      <button type="submit" style="width:100%;padding:10px 12px;border-radius:8px;border:none;background:#6a5cff;color:#fff;font-weight:700;font-size:14px;cursor:pointer">Entrar</button>
      <div id="dashLockError" style="display:none;margin-top:10px;font-size:12px;color:#ff6b6b">Senha incorreta.</div>
    </form>
  </div>"""

GATE_LOADER_SCRIPT = """<script>
(function(){
  var EXPECTED_HASH="__PASSWORD_HASH__";
  var STORAGE_KEY="presubs_dash_unlock_v1";
  function sha256Hex(text){
    var enc=new TextEncoder().encode(text);
    return crypto.subtle.digest("SHA-256",enc).then(function(buf){
      return Array.prototype.map.call(new Uint8Array(buf),function(b){return b.toString(16).padStart(2,"0")}).join("");
    });
  }
  function removeOverlay(){
    var overlay=document.getElementById("dashLockOverlay");
    if(overlay)overlay.remove();
  }
  function loadScripts(){
    removeOverlay();
    var s1=document.createElement("script");
    s1.src="data.js?v=10.6.4.2";
    s1.onload=function(){
      var s2=document.createElement("script");
      s2.src="dashboard.js?v=10.6.4.2";
      document.body.appendChild(s2);
    };
    document.body.appendChild(s1);
  }
  var stored=null;
  try{stored=localStorage.getItem(STORAGE_KEY);}catch(e){}
  if(stored===EXPECTED_HASH){
    loadScripts();
  }else{
    var form=document.getElementById("dashLockForm");
    var input=document.getElementById("dashLockInput");
    var err=document.getElementById("dashLockError");
    form.addEventListener("submit",function(ev){
      ev.preventDefault();
      sha256Hex(input.value).then(function(hash){
        if(hash===EXPECTED_HASH){
          try{localStorage.setItem(STORAGE_KEY,hash);}catch(e){}
          loadScripts();
        }else{
          err.style.display="block";
          input.value="";
          input.focus();
        }
      });
    });
  }
})();
</script>"""


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

    old_dashboard = """  document.body.dataset.periodMode="week";
  const url=weekId?`/api/dashboard?week_id=${weekId}`:"/api/dashboard";
  try{
    dashboard=await fetch(url).then(r=>r.json());
  }catch(error){
    console.error("Dashboard render error in loadDashboard:",error);
    dashboard={current_week:null};
  }
  renderLoadedDashboard();"""
    new_dashboard = """  document.body.dataset.periodMode="week";
  if(IS_STATIC){
    const selected=weekId || STATIC_DATA.weeks?.[0]?.id;
    dashboard=STATIC_DATA.dashboards?.[String(selected)] || {current_week:null};
  }else{
    const url=weekId?`/api/dashboard?week_id=${weekId}`:"/api/dashboard";
    try{
      dashboard=await fetch(url).then(r=>r.json());
    }catch(error){
      console.error("Dashboard render error in loadDashboard:",error);
      dashboard={current_week:null};
    }
  }
  renderLoadedDashboard();"""
    if old_dashboard not in js:
        raise RuntimeError("Could not patch loadDashboard.")
    js = js.replace(old_dashboard, new_dashboard, 1)

    old_custom_range = """  try{
    const extras=await fetch(`/api/period-extras?start=${start}&end=${end}`).then(r=>r.json());
    Object.assign(dashboard,extras);
  }catch(error){
    console.error("Dashboard render error in applyGlobalCustomRange:",error);
    dashboard.period_extras_unavailable=true;
  }
  renderLoadedDashboard();
}"""
    new_custom_range = """  if(IS_STATIC){
    dashboard.period_extras_unavailable=true;
  }else{
    try{
      const extras=await fetch(`/api/period-extras?start=${start}&end=${end}`).then(r=>r.json());
      Object.assign(dashboard,extras);
    }catch(error){
      console.error("Dashboard render error in applyGlobalCustomRange:",error);
      dashboard.period_extras_unavailable=true;
    }
  }
  renderLoadedDashboard();
}"""
    if old_custom_range not in js:
        raise RuntimeError("Could not patch applyGlobalCustomRange.")
    js = js.replace(old_custom_range, new_custom_range, 1)

    old_competitor_ads = """  if(!competitorAdsCache){
    try{
      const res=await fetch("/api/competitor-ads");
      competitorAdsCache=res.ok?await res.json():{available:false,ads:[]};
    }catch(error){
      console.error("Dashboard render error in renderCompetitors:",error);
      competitorAdsCache={available:false,ads:[]};
    }
  }"""
    new_competitor_ads = """  if(!competitorAdsCache){
    if(IS_STATIC){
      competitorAdsCache=STATIC_DATA.competitor_ads||{available:false,ads:[]};
    }else{
      try{
        const res=await fetch("/api/competitor-ads");
        competitorAdsCache=res.ok?await res.json():{available:false,ads:[]};
      }catch(error){
        console.error("Dashboard render error in renderCompetitors:",error);
        competitorAdsCache={available:false,ads:[]};
      }
    }
  }"""
    if old_competitor_ads not in js:
        raise RuntimeError("Could not patch renderCompetitors.")
    js = js.replace(old_competitor_ads, new_competitor_ads, 1)

    return js


def main() -> int:
    dashboard_app.init_db()
    with dashboard_app.db() as connection:
        dashboard_app.backfill_relations(connection)
        competitor_ads = dashboard_app.competitor_ads_summary(connection)

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
            "competitor_ads": competitor_ads,
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
    if (STATIC_DIR / "weekly-review.html").exists():
        (DOCS_DIR / "weekly-review.html").write_text(
            (STATIC_DIR / "weekly-review.html").read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    weekly_reviews_dir = ROOT / "weekly_reviews"
    if weekly_reviews_dir.exists():
        shutil.copytree(weekly_reviews_dir, DOCS_DIR / "weekly-reviews")
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
