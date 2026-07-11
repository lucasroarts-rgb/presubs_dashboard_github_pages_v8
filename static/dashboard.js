const money = value => value == null ? "—" : new Intl.NumberFormat("en-IE",{style:"currency",currency:"EUR",minimumFractionDigits:2}).format(Number(value));
const number = value => new Intl.NumberFormat("en-IE",{maximumFractionDigits:0}).format(Number(value)||0);
const decimal = value => value == null ? "—" : new Intl.NumberFormat("en-IE",{maximumFractionDigits:2}).format(Number(value));
const percent = value => value == null ? "—" : `${decimal(value)}%`;
const formatDate = value => value ? new Intl.DateTimeFormat("en-GB",{day:"2-digit",month:"short",year:"numeric"}).format(new Date(`${value}T12:00:00`)) : "—";

let weeks=[];
let dashboard=null;
let comparisonData=null;

document.querySelectorAll(".tab").forEach(button=>{
  button.addEventListener("click",()=>{
    document.querySelectorAll(".tab").forEach(el=>el.classList.remove("active"));
    document.querySelectorAll(".view").forEach(el=>el.classList.remove("active"));
    button.classList.add("active");
    document.getElementById(button.dataset.view).classList.add("active");
  });
});

function change(current,previous,invert=false){
  if(current==null || previous==null || Number(previous)===0) return null;
  const value=(Number(current)-Number(previous))*100/Number(previous);
  return {value,good:invert?value<0:value>0};
}

function deltaHtml(delta){
  if(!delta) return `<span class="delta">No previous data</span>`;
  return `<span class="delta ${delta.good?"good":"bad"}">${delta.value>=0?"+":""}${decimal(delta.value)}%</span>`;
}

function comparisonDelta(value,invert,currentValue,previousValue){
  if(value==null){
    if((Number(previousValue)||0)===0 && (Number(currentValue)||0)>0) return `<span class="delta good">New delivery</span>`;
    return `<span class="delta">—</span>`;
  }
  const good=invert?value<0:value>0;
  return `<span class="delta ${good?"good":"bad"}">${value>=0?"+":""}${decimal(value)}%</span>`;
}

function statusPill(status){
  const value=(status||"unknown").toLowerCase();
  const cls=value==="active"?"active":"inactive";
  const label=value==="active"?"Active":value==="inactive"?"Inactive":status||"Unknown";
  return `<span class="pill ${cls}">${label}</span>`;
}

function startSourceLabel(source){
  const labels={
    meta_start_date:"Meta start date",
    first_imported_delivery:"First seen in imported history",
    registered_start_date:"Registered page start date",
    dashboard_registration_date:"Dashboard registration date",
    first_tagged_ad:"First ad assigned to this page"
  };
  return labels[source]||"Available start date";
}

function startCell(row){
  return `${formatDate(row.effective_start_date)}<span class="sub-cell">${startSourceLabel(row.start_date_source)}</span>`;
}

function pageBadge(row){
  const code=row.page_code||"MAIN";
  return `<span class="pill ${row.is_default?"inactive":"info"}">${row.is_default?"Main page":`LP-${code}`}</span>`;
}

function calculatedCpl(row){
  return row.cost_per_result || row.calculated_cpl || (Number(row.results)>0?Number(row.spend)/Number(row.results):null);
}

function performancePill(row){
  const cpl=calculatedCpl(row);
  const average=Number(dashboard?.totals?.cpl)||0;
  if(!Number(row.results)) return `<span class="pill bad">No registrations</span>`;
  if(!average) return `<span class="pill info">Delivered</span>`;
  if(cpl<=average*.85) return `<span class="pill good">Strong</span>`;
  if(cpl<=average*1.12) return `<span class="pill info">On benchmark</span>`;
  return `<span class="pill warn">High CPL</span>`;
}

function normalized(value){return String(value||"").trim().toLowerCase()}

function campaignForAdset(adset){
  if(!dashboard) return null;
  if(adset.campaign_name){
    const explicit=dashboard.campaigns.find(c=>normalized(c.entity_name)===normalized(adset.campaign_name) || normalized(c.entity_key)===normalized(adset.campaign_key));
    if(explicit) return {...explicit,relation_inferred:false};
  }
  const text=normalized(adset.entity_name);
  let match=null;
  if(/hot|rmkt|remarket/.test(text)) match=dashboard.campaigns.find(c=>/hot|remarket/.test(normalized(c.entity_name)));
  if(!match && /cold|lal|lookalike|advantage/.test(text)) match=dashboard.campaigns.find(c=>/cold/.test(normalized(c.entity_name)));
  if(!match && dashboard.campaigns.length===1) match=dashboard.campaigns[0];
  return match?{...match,relation_inferred:true}:null;
}

function adsetForAd(ad){
  if(!dashboard) return null;
  if(ad.adset_key){
    const byKey=dashboard.adsets.find(s=>normalized(s.entity_key)===normalized(ad.adset_key));
    if(byKey) return byKey;
  }
  return dashboard.adsets.find(s=>normalized(s.entity_name)===normalized(ad.adset_name))||null;
}

function campaignForAd(ad){
  const set=adsetForAd(ad);
  return set?campaignForAdset(set):null;
}

function relationLabelForAdset(adset){
  const campaign=campaignForAdset(adset);
  return campaign ? `<span class="sub-cell">${campaign.entity_name}</span>` : "";
}

function relationLabelForAd(ad){
  const set=adsetForAd(ad);
  const campaign=campaignForAd(ad);
  return `${set?`<span class="sub-cell">${set.entity_name}</span>`:""}${campaign?`<span class="sub-cell">${campaign.entity_name}</span>`:""}`;
}

async function loadWeeks(){
  weeks=await fetch("/api/weeks").then(r=>r.json());
  const main=document.getElementById("weekSelect");
  const current=document.getElementById("compareCurrent");
  const previous=document.getElementById("comparePrevious");
  const options=weeks.map(w=>`<option value="${w.id}">${w.label}</option>`).join("");
  main.innerHTML=options||`<option>No reporting periods</option>`;
  current.innerHTML=options;
  previous.innerHTML=options;
  main.disabled=!weeks.length;
  current.disabled=!weeks.length;
  previous.disabled=!weeks.length;
  if(weeks[0]) current.value=weeks[0].id;
  if(weeks[1]) previous.value=weeks[1].id;
  else if(weeks[0]) previous.value=weeks[0].id;
  main.addEventListener("change",()=>loadDashboard(main.value));
  document.getElementById("runComparison").addEventListener("click",loadComparison);
  document.getElementById("hideZeroDelivery").addEventListener("change",()=>{
    if(comparisonData) renderDetailedComparison(comparisonData);
  });
  await loadDashboard(weeks[0]?.id);
  if(weeks.length>1) await loadComparison();
}

function renderKpis(data){
  const t=data.totals||{};
  document.getElementById("accountCpl").textContent=money(t.cpl);
  const lpvAvailable=Number(t.landing_page_views)>0;
  const items=[
    ["Spend",money(t.spend),"Total across all campaigns"],
    ["Registrations",number(t.results),"Meta complete registrations only"],
    ["Cost / registration",money(t.cpl),"Blended CPL"],
    ["Link clicks",number(t.link_clicks),`Blended CPC ${money(t.cpc)}`],
    ["Landing-page views",lpvAvailable?number(t.landing_page_views):"—",lpvAvailable?`Cost / LPV ${money(t.cost_per_lpv)}`:"Not included in this export"],
    ["Link CTR",percent(t.ctr),`${number(t.impressions)} impressions`]
  ];
  document.getElementById("kpis").innerHTML=items.map(x=>`<article class="card kpi"><div class="kpi-label">${x[0]}</div><div><div class="kpi-value">${x[1]}</div><div class="kpi-note">${x[2]}</div></div></article>`).join("");
}

function renderCampaignCards(items){
  document.getElementById("campaignCount").textContent=`${items.length} campaign${items.length===1?"":"s"}`;
  document.getElementById("campaignCards").innerHTML=items.length?items.map(item=>`
    <div class="compare-card">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div class="compare-title">${item.entity_name}</div>${statusPill(item.status)}
      </div>
      <div class="compare-metrics">
        <div class="mini-metric"><span>Spend</span><strong>${money(item.spend)}</strong></div>
        <div class="mini-metric"><span>Results</span><strong>${number(item.results)}</strong></div>
        <div class="mini-metric"><span>CPL</span><strong>${money(calculatedCpl(item))}</strong></div>
      </div>
      <div class="entity-sub">Started ${formatDate(item.effective_start_date)} · ${startSourceLabel(item.start_date_source)}</div>
    </div>`).join(""):`<div class="empty">No campaigns in this period.</div>`;
}

function renderAdsetBars(items){
  const rows=[...items].filter(x=>Number(x.results)>0).sort((a,b)=>calculatedCpl(a)-calculatedCpl(b));
  if(!rows.length){document.getElementById("adsetBars").innerHTML=`<div class="empty">No ad sets with registrations.</div>`;return}
  const max=Math.max(...rows.map(calculatedCpl));
  document.getElementById("adsetBars").innerHTML=rows.map(x=>`
    <div class="bar-row">
      <div class="bar-label" title="${x.entity_name}">${x.entity_name}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2,calculatedCpl(x)/max*100)}%"></div></div>
      <div class="bar-value">${money(calculatedCpl(x))}</div>
    </div>`).join("");
}

function adScore(ad){
  if(!Number(ad.results)) return -1;
  const cpl=calculatedCpl(ad)||99999;
  return Number(ad.results)*1000-cpl;
}

function renderTopAds(items){
  const rows=[...items].filter(x=>Number(x.results)>0).sort((a,b)=>adScore(b)-adScore(a)).slice(0,3);
  document.getElementById("topAds").innerHTML=rows.length?rows.map((ad,index)=>`
    <div class="ad-highlight">
      <div style="display:flex;justify-content:space-between;gap:8px"><div class="rank">#${index+1}</div>${performancePill(ad)}</div>
      <h4>${ad.entity_name}</h4>
      <p>${ad.adset_name||"Ad-set relation not included"}</p>
      <div class="metric-line"><span>Registrations <strong>${number(ad.results)}</strong></span><span>CPL <strong>${money(calculatedCpl(ad))}</strong></span></div>
      <div class="entity-sub">Started ${formatDate(ad.effective_start_date)} · ${pageBadge(ad)} ${ad.page_name||"Main page"}</div>
    </div>`).join(""):`<div class="empty">No ads with registrations.</div>`;
}

function table(container,columns,rows,emptyMessage="No data for this period."){
  document.getElementById(container).innerHTML=`<div class="table-wrap"><table><thead><tr>${columns.map(c=>`<th>${c.label}</th>`).join("")}</tr></thead><tbody>${rows.length?rows.map(row=>`<tr>${columns.map(c=>`<td class="${c.numeric?"numeric":""} ${c.name?"name-cell":""}">${c.render?c.render(row):(row[c.key]??"—")}</td>`).join("")}</tr>`).join(""):`<tr><td colspan="${columns.length}" class="empty">${emptyMessage}</td></tr>`}</tbody></table></div>`;
}

async function editPreview(ad){
  const url=prompt(`Paste the Meta preview link for:\n${ad.entity_name}`,ad.preview_url||"");
  if(url===null) return;
  const response=await fetch(`/api/ads/${ad.id}/preview`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({preview_url:url})});
  if(!response.ok){alert((await response.json()).detail||"Could not save the link.");return}
  await loadDashboard(document.getElementById("weekSelect").value);
}

function campaignRows(){
  const search=normalized(document.getElementById("campaignSearch")?.value);
  const status=document.getElementById("campaignStatusFilter")?.value||"";
  return (dashboard?.campaigns||[]).filter(row=>
    (!search || normalized(row.entity_name).includes(search)) &&
    (!status || normalized(row.status)===status)
  );
}

function adsetRows(){
  const search=normalized(document.getElementById("adsetSearch")?.value);
  const campaignKey=document.getElementById("adsetCampaignFilter")?.value||"";
  const status=document.getElementById("adsetStatusFilter")?.value||"";
  return (dashboard?.adsets||[]).filter(row=>{
    const campaign=campaignForAdset(row);
    return (!search || normalized(row.entity_name).includes(search)) &&
      (!campaignKey || String(campaign?.entity_key||"")===campaignKey) &&
      (!status || normalized(row.status)===status);
  });
}

function adRows(){
  const search=normalized(document.getElementById("adSearch")?.value);
  const campaignKey=document.getElementById("adCampaignFilter")?.value||"";
  const adsetKey=document.getElementById("adAdsetFilter")?.value||"";
  const pageKey=document.getElementById("adPageFilter")?.value||"";
  const status=document.getElementById("adStatusFilter")?.value||"";
  const result=document.getElementById("adResultFilter")?.value||"";
  return (dashboard?.ads||[]).filter(row=>{
    const set=adsetForAd(row);
    const campaign=campaignForAd(row);
    return (!search || normalized(row.entity_name).includes(search)) &&
      (!campaignKey || String(campaign?.entity_key||"")===campaignKey) &&
      (!adsetKey || String(set?.entity_key||"")===adsetKey) &&
      (!pageKey || String(row.page_key||"main")===pageKey) &&
      (!status || normalized(row.status)===status) &&
      (!result || (result==="with"?Number(row.results)>0:Number(row.results)===0));
  });
}

function renderCampaignTable(){
  table("campaignTable",[
    {label:"Campaign",name:true,render:r=>`<span>${r.entity_name}</span>`},
    {label:"Status",render:r=>statusPill(r.status)},
    {label:"Start date",render:startCell},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"CPL",numeric:true,render:r=>money(calculatedCpl(r))},
    {label:"Reach",numeric:true,render:r=>number(r.reach)},
    {label:"Frequency",numeric:true,render:r=>decimal(r.frequency)},
    {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
    {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"CPC",numeric:true,render:r=>money(r.cpc)},
    {label:"LPV",numeric:true,render:r=>number(r.landing_page_views)},
    {label:"Cost / LPV",numeric:true,render:r=>money(r.cost_per_lpv)},
    {label:"Click/LPV → registration",numeric:true,render:r=>percent(r.conversion_rate)}
  ],campaignRows());
}

function renderAdsetTable(){
  table("adsetTable",[
    {label:"Ad set",name:true,render:r=>`<span>${r.entity_name}</span><span class="sub-cell">${r.attribution||""}</span>`},
    {label:"Campaign",render:r=>campaignForAdset(r)?.entity_name||"—"},
    {label:"Status",render:r=>statusPill(r.status)},
    {label:"Running since",render:startCell},
    {label:"Daily budget",numeric:true,render:r=>money(r.daily_budget)},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"CPL",numeric:true,render:r=>money(calculatedCpl(r))},
    {label:"Reach",numeric:true,render:r=>number(r.reach)},
    {label:"Frequency",numeric:true,render:r=>decimal(r.frequency)},
    {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
    {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
    {label:"CPC",numeric:true,render:r=>money(r.cpc)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"LPV",numeric:true,render:r=>Number(r.landing_page_views)>0?number(r.landing_page_views):"—"},
    {label:"Cost / LPV",numeric:true,render:r=>money(r.cost_per_lpv)},
    {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)}
  ],adsetRows());
}

function renderAdTable(){
  const rows=adRows();
  table("adTable",[
    {label:"Ad",name:true,render:r=>`<span>${r.entity_name}</span>${performancePill(r)}`},
    {label:"Ad set",render:r=>adsetForAd(r)?.entity_name||r.adset_name||"—"},
    {label:"Campaign",render:r=>campaignForAd(r)?.entity_name||r.campaign_name||"—"},
    {label:"Page",render:r=>`${pageBadge(r)}<span class="sub-cell">${r.page_name||"Main page"}</span>`},
    {label:"Status",render:r=>statusPill(r.status)},
    {label:"Created",render:startCell},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"CPL",numeric:true,render:r=>money(calculatedCpl(r))},
    {label:"Reach",numeric:true,render:r=>number(r.reach)},
    {label:"Frequency",numeric:true,render:r=>decimal(r.frequency)},
    {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
    {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
    {label:"CPC",numeric:true,render:r=>money(r.cpc)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"LPV",numeric:true,render:r=>Number(r.landing_page_views)>0?number(r.landing_page_views):"—"},
    {label:"Cost / LPV",numeric:true,render:r=>money(r.cost_per_lpv)},
    {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)},
    {label:"Quality",render:r=>r.quality_ranking||"—"},
    {label:"Engagement",render:r=>r.engagement_ranking||"—"},
    {label:"Conversion ranking",render:r=>r.conversion_ranking||"—"},
    {label:"Preview",render:r=>`<button class="link-button ad-link" data-ad="${r.id}">${r.preview_url?"View / edit":"＋ Add ad link"}</button>`}
  ],rows);
  document.querySelectorAll("[data-ad]").forEach(button=>button.addEventListener("click",()=>{
    const ad=dashboard.ads.find(x=>x.id===Number(button.dataset.ad));
    if(ad.preview_url && confirm("Open the existing link?\nChoose Cancel to edit it.")){window.open(ad.preview_url,"_blank");return}
    editPreview(ad);
  }));
}

function populateDynamicFilters(data){
  const campaignOptions=data.campaigns.map(c=>`<option value="${c.entity_key}">${c.entity_name}</option>`).join("");
  ["adsetCampaignFilter","adCampaignFilter","dailyCampaignFilter"].forEach(id=>{
    const select=document.getElementById(id);
    if(!select) return;
    const current=select.value;
    select.innerHTML=`<option value="">All campaigns</option>${campaignOptions}`;
    if([...select.options].some(o=>o.value===current)) select.value=current;
  });

  ["adAdsetFilter","dailyAdsetFilter"].forEach(id=>{
    const select=document.getElementById(id);
    if(!select) return;
    const current=select.value;
    select.innerHTML=`<option value="">All ad sets</option>${data.adsets.map(s=>`<option value="${s.entity_key}">${s.entity_name}</option>`).join("")}`;
    if([...select.options].some(o=>o.value===current)) select.value=current;
  });

  const sourceAds=[...(data.ads||[]),...(data.daily_ads||[])];
  const pages=[...new Map(sourceAds.map(a=>[a.page_key||"main",{key:a.page_key||"main",name:a.page_name||"Main page"}])).values()];
  ["adPageFilter","dailyPageFilter"].forEach(id=>{
    const select=document.getElementById(id);
    if(!select) return;
    const current=select.value;
    select.innerHTML=`<option value="">All pages</option>${pages.map(p=>`<option value="${p.key}">${p.name}</option>`).join("")}`;
    if([...select.options].some(o=>o.value===current)) select.value=current;
  });
}

function renderPerformanceTables(data){
  populateDynamicFilters(data);
  renderCampaignTable();
  renderAdsetTable();
  renderAdTable();
}

function renderHierarchy(data){
  const root=document.getElementById("hierarchyTree");
  const campaigns=data.campaigns||[];
  const adsets=data.adsets||[];
  const ads=data.ads||[];
  const assignedSetKeys=new Set();

  const cards=campaigns.map((campaign,index)=>{
    const sets=adsets.filter(set=>{
      const related=campaignForAdset(set);
      const match=related && String(related.entity_key)===String(campaign.entity_key);
      if(match) assignedSetKeys.add(set.entity_key);
      return match;
    });
    return `<article class="card tree-card ${index===0?"open":""}">
      <button class="tree-head" onclick="this.parentElement.classList.toggle('open')">
        <div>
          <div class="entity-name">${campaign.entity_name}</div>
          <div class="entity-sub">${statusPill(campaign.status)} &nbsp; Started ${formatDate(campaign.effective_start_date)} · ${startSourceLabel(campaign.start_date_source)}</div>
        </div>
        <div class="tree-metric"><span>Spend</span><strong>${money(campaign.spend)}</strong></div>
        <div class="tree-metric"><span>Results</span><strong>${number(campaign.results)}</strong></div>
        <div class="tree-metric"><span>CPL</span><strong>${money(calculatedCpl(campaign))}</strong></div>
        <div class="tree-metric hide-medium"><span>Ad sets</span><strong>${number(sets.length)}</strong></div>
        <div class="chev">⌄</div>
      </button>
      <div class="tree-body">
        ${sets.length?sets.map(set=>{
          const children=ads.filter(ad=>{
            const related=adsetForAd(ad);
            return related && String(related.entity_key)===String(set.entity_key);
          });
          const relation=campaignForAdset(set);
          return `<div class="adset-block">
            <div class="adset-title">
              <div>
                <div class="entity-name" style="font-size:14px">${set.entity_name}</div>
                <div class="entity-sub">${statusPill(set.status)} &nbsp; ${money(set.daily_budget)}/day · Started ${formatDate(set.effective_start_date)}</div>
                
              </div>
              <div class="tree-metric"><span>Spend</span><strong>${money(set.spend)}</strong></div>
              <div class="tree-metric"><span>Results</span><strong>${number(set.results)}</strong></div>
              <div class="tree-metric"><span>CPL</span><strong>${money(calculatedCpl(set))}</strong></div>
              <div class="tree-metric"><span>Ads</span><strong>${number(children.length)}</strong></div>
            </div>
            <div class="ads-list">
              ${children.length?children.map(ad=>`<div class="ad-row">
                <div>
                  <div class="ad-name">${ad.entity_name}</div>
                  <div class="ad-date">${statusPill(ad.status)} &nbsp; Started ${formatDate(ad.effective_start_date)} · ${pageBadge(ad)} ${ad.page_name||"Main page"}</div>
                </div>
                <div class="tree-metric"><span>Spend</span><strong>${money(ad.spend)}</strong></div>
                <div class="tree-metric"><span>Results</span><strong>${number(ad.results)}</strong></div>
                <div class="tree-metric"><span>CPL</span><strong>${money(calculatedCpl(ad))}</strong></div>
                <div class="tree-metric hide-medium"><span>CTR</span><strong>${percent(ad.ctr)}</strong></div>
                <div class="tree-metric hide-medium"><span>Conversion</span><strong>${percent(ad.conversion_rate)}</strong></div>
                <div><button class="ad-link" data-hierarchy-ad="${ad.id}">${ad.preview_url?"View ad ↗":"＋ Add ad link"}</button></div>
              </div>`).join(""):`<div class="empty">No ads linked to this ad set.</div>`}
            </div>
          </div>`;
        }).join(""):`<div class="empty">No ad sets linked to this campaign.</div>`}
      </div>
    </article>`;
  });

  const unassigned=adsets.filter(set=>!assignedSetKeys.has(set.entity_key));
  if(unassigned.length){
    cards.push(`<article class="card tree-card">
      <button class="tree-head" onclick="this.parentElement.classList.toggle('open')">
        <div><div class="entity-name">Unassigned ad sets</div><div class="entity-sub">These ad sets could not be matched automatically.</div></div>
        <div class="tree-metric"><span>Spend</span><strong>${money(unassigned.reduce((s,x)=>s+Number(x.spend||0),0))}</strong></div>
        <div class="tree-metric"><span>Results</span><strong>${number(unassigned.reduce((s,x)=>s+Number(x.results||0),0))}</strong></div>
        <div class="tree-metric"><span>CPL</span><strong>—</strong></div>
        <div class="tree-metric hide-medium"><span>Ad sets</span><strong>${unassigned.length}</strong></div>
        <div class="chev">⌄</div>
      </button><div class="tree-body"><div class="empty">${unassigned.map(x=>x.entity_name).join(" · ")}</div></div>
    </article>`);
  }

  root.innerHTML=cards.join("");
  document.querySelectorAll("[data-hierarchy-ad]").forEach(button=>button.addEventListener("click",()=>{
    const ad=data.ads.find(x=>x.id===Number(button.dataset.hierarchyAd));
    if(ad.preview_url){window.open(ad.preview_url,"_blank","noopener");return}
    editPreview(ad);
  }));
}


function filteredDailyAds(){
  const search=normalized(document.getElementById("dailyAdSearch")?.value);
  const campaignKey=document.getElementById("dailyCampaignFilter")?.value||"";
  const adsetKey=document.getElementById("dailyAdsetFilter")?.value||"";
  const pageKey=document.getElementById("dailyPageFilter")?.value||"";
  const hideZero=document.getElementById("dailyHideZero")?.checked!==false;

  return (dashboard?.daily_ads||[]).filter(row=>{
    const delivered=Number(row.spend||0)>0 || Number(row.results||0)>0 || Number(row.impressions||0)>0 || Number(row.link_clicks||0)>0;
    return (!hideZero || delivered) &&
      (!search || normalized(row.entity_name).includes(search)) &&
      (!campaignKey || normalized(row.campaign_key)===normalized(campaignKey) || normalized(row.campaign_name)===normalized(campaignKey)) &&
      (!adsetKey || normalized(row.adset_key)===normalized(adsetKey) || normalized(row.adset_name)===normalized(adsetKey)) &&
      (!pageKey || String(row.page_key||"main")===pageKey);
  });
}

function aggregateDailyRows(rows){
  const groups=new Map();
  rows.forEach(row=>{
    const day=row.report_date;
    if(!day) return;
    if(!groups.has(day)){
      groups.set(day,{
        report_date:day,spend:0,results:0,impressions:0,link_clicks:0,
        landing_page_views:0,ad_keys:new Set(),page_keys:new Set()
      });
    }
    const g=groups.get(day);
    g.spend+=Number(row.spend||0);
    g.results+=Number(row.results||0);
    g.impressions+=Number(row.impressions||0);
    g.link_clicks+=Number(row.link_clicks||0);
    g.landing_page_views+=Number(row.landing_page_views||0);
    const delivered=Number(row.spend||0)>0 || Number(row.results||0)>0 || Number(row.impressions||0)>0 || Number(row.link_clicks||0)>0;
    if(delivered){
      g.ad_keys.add(String(row.entity_key||row.id));
      g.page_keys.add(String(row.page_key||"main"));
    }
  });

  return [...groups.values()].sort((a,b)=>a.report_date.localeCompare(b.report_date)).map(g=>{
    const denominator=g.landing_page_views>0?g.landing_page_views:g.link_clicks;
    return {
      report_date:g.report_date,
      spend:g.spend,
      results:g.results,
      cpl:g.results>0?g.spend/g.results:null,
      impressions:g.impressions,
      link_clicks:g.link_clicks,
      cpc:g.link_clicks>0?g.spend/g.link_clicks:null,
      ctr:g.impressions>0?g.link_clicks*100/g.impressions:null,
      landing_page_views:g.landing_page_views,
      cost_per_lpv:g.landing_page_views>0?g.spend/g.landing_page_views:null,
      conversion_denominator:denominator,
      conversion_basis:g.landing_page_views>0?"landing_page_views":"link_clicks_proxy",
      conversion_rate:denominator>0?g.results*100/denominator:null,
      ad_count:g.ad_keys.size,
      page_count:g.page_keys.size
    };
  });
}

function renderDailySpendResults(summary){
  const container=document.getElementById("dailySpendResultsChart");
  if(!summary.length){
    container.innerHTML=`<div class="empty">No daily rows match the selected filters.</div>`;
    return;
  }
  const maxSpend=Math.max(1,...summary.map(x=>Number(x.spend)||0));
  const maxResults=Math.max(1,...summary.map(x=>Number(x.results)||0));
  container.innerHTML=summary.map(day=>`
    <div class="daily-trend-row">
      <div class="daily-date">${formatDate(day.report_date)}</div>
      <div class="daily-series">
        <span class="daily-series-label">Spend</span>
        <div class="daily-track"><div class="daily-fill spend" style="width:${Math.max(2,Number(day.spend)/maxSpend*100)}%"></div></div>
      </div>
      <div class="daily-chart-value">${money(day.spend)}</div>
      <div class="daily-series">
        <span class="daily-series-label">Registrations</span>
        <div class="daily-track"><div class="daily-fill results" style="width:${Number(day.results)>0?Math.max(4,Number(day.results)/maxResults*100):0}%"></div></div>
      </div>
      <div class="daily-chart-value">${number(day.results)}</div>
    </div>
  `).join("");
}

function renderDailyCpl(summary){
  const container=document.getElementById("dailyCplChart");
  if(!summary.length){
    container.innerHTML=`<div class="empty">No daily rows match the selected filters.</div>`;
    return;
  }
  const valid=summary.filter(x=>x.cpl!=null);
  const max=Math.max(1,...valid.map(x=>Number(x.cpl)||0));
  container.innerHTML=summary.map(day=>`
    <div class="bar-row">
      <div class="bar-label">${formatDate(day.report_date)}</div>
      <div class="bar-track">
        ${day.cpl==null
          ? `<div class="daily-no-result">No registrations</div>`
          : `<div class="bar-fill" style="width:${Math.max(2,Number(day.cpl)/max*100)}%"></div>`}
      </div>
      <div class="bar-value">${day.cpl==null?"—":money(day.cpl)}</div>
    </div>
  `).join("");
}

function renderDaily(){
  const allRows=dashboard?.daily_ads||[];
  const rows=filteredDailyAds();
  const summary=aggregateDailyRows(rows);
  const notice=document.getElementById("dailyNotice");
  const badge=document.getElementById("dailyCoverageBadge");

  if(!allRows.length){
    badge.textContent="Daily file not imported";
    notice.innerHTML=`<strong>Daily detail unavailable:</strong> import the optional fourth Meta Ads file with <strong>Breakdown → Time → Day</strong>. The weekly dashboard remains valid without it.`;
    document.getElementById("dailyKpis").innerHTML="";
    document.getElementById("dailySpendResultsChart").innerHTML=`<div class="empty">No ad-by-day export is available for this reporting period.</div>`;
    document.getElementById("dailyCplChart").innerHTML=`<div class="empty">No daily CPL data is available.</div>`;
    document.getElementById("dailySummaryTable").innerHTML="";
    document.getElementById("dailyAdTable").innerHTML="";
    return;
  }

  badge.textContent=`${number(allRows.length)} ad-day rows`;
  notice.innerHTML=`<strong>Source:</strong> ad-level Meta export with the Day breakdown. Weekly reach and frequency continue to come from the weekly exports because daily reach cannot be safely summed.`;

  const spend=summary.reduce((sum,x)=>sum+Number(x.spend||0),0);
  const results=summary.reduce((sum,x)=>sum+Number(x.results||0),0);
  const clicks=summary.reduce((sum,x)=>sum+Number(x.link_clicks||0),0);
  const impressions=summary.reduce((sum,x)=>sum+Number(x.impressions||0),0);
  const cpl=results>0?spend/results:null;
  const best=[...summary].filter(x=>x.cpl!=null).sort((a,b)=>a.cpl-b.cpl)[0]||null;
  const highest=[...summary].sort((a,b)=>Number(b.results)-Number(a.results)||Number(b.spend)-Number(a.spend))[0]||null;
  const zeroResultSpend=summary.filter(x=>Number(x.results)===0).reduce((sum,x)=>sum+Number(x.spend||0),0);

  const kpis=[
    ["Days tracked",number(summary.length),`${number(rows.length)} filtered ad-day rows`],
    ["Spend",money(spend),"Detailed ad export total"],
    ["Registrations",number(results),highest?`Highest: ${number(highest.results)} on ${formatDate(highest.report_date)}`:"No registrations"],
    ["Cost / registration",money(cpl),best?`Best day: ${formatDate(best.report_date)} at ${money(best.cpl)}`:"No day with registrations"],
    ["Link clicks",number(clicks),`CPC ${money(clicks>0?spend/clicks:null)}`],
    ["Spend with zero-result days",money(zeroResultSpend),`${number(impressions)} impressions tracked`]
  ];
  document.getElementById("dailyKpis").innerHTML=kpis.map(x=>`<article class="card kpi"><div class="kpi-label">${x[0]}</div><div><div class="kpi-value">${x[1]}</div><div class="kpi-note">${x[2]}</div></div></article>`).join("");

  renderDailySpendResults(summary);
  renderDailyCpl(summary);

  table("dailySummaryTable",[
    {label:"Day",name:true,render:r=>formatDate(r.report_date)},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"CPL",numeric:true,render:r=>money(r.cpl)},
    {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
    {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
    {label:"CPC",numeric:true,render:r=>money(r.cpc)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"LPV",numeric:true,render:r=>Number(r.landing_page_views)>0?number(r.landing_page_views):"—"},
    {label:"Conversion basis",render:r=>r.conversion_basis==="landing_page_views"?"Landing-page views":"Link clicks proxy"},
    {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)},
    {label:"Ads delivered",numeric:true,render:r=>number(r.ad_count)}
  ],[...summary].sort((a,b)=>b.report_date.localeCompare(a.report_date)),"No daily rows match the selected filters.");

  const detail=[...rows].sort((a,b)=>b.report_date.localeCompare(a.report_date)||Number(b.spend)-Number(a.spend));
  table("dailyAdTable",[
    {label:"Day",render:r=>formatDate(r.report_date)},
    {label:"Ad",name:true,render:r=>`<span>${r.entity_name}</span>`},
    {label:"Ad set",render:r=>r.adset_name||"—"},
    {label:"Campaign",render:r=>r.campaign_name||"—"},
    {label:"Page",render:r=>`${pageBadge(r)}<span class="sub-cell">${r.page_name||"Main page"}</span>`},
    {label:"Status",render:r=>statusPill(r.status)},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"CPL",numeric:true,render:r=>money(calculatedCpl(r))},
    {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
    {label:"Reach",numeric:true,render:r=>number(r.reach)},
    {label:"Frequency",numeric:true,render:r=>decimal(r.frequency)},
    {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
    {label:"CPC",numeric:true,render:r=>money(r.cpc)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"LPV",numeric:true,render:r=>Number(r.landing_page_views)>0?number(r.landing_page_views):"—"},
    {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)}
  ],detail,"No ad-by-day rows match the selected filters.");
}


function localPageIdentity(ad){
  const name=String(ad.entity_name||"");
  const match=name.match(/\[\s*LP\s*[-_: ]\s*([^\]]+?)\s*\]/i);
  if(!match) return {page_key:"main",page_code:"MAIN",page_name:"Main page",is_default:true};
  const code=String(match[1]||"").trim().toUpperCase().replace(/\s+/g,"-");
  if(!code || ["MAIN","PRINCIPAL","DEFAULT"].includes(code)) return {page_key:"main",page_code:"MAIN",page_name:"Main page",is_default:true};
  return {page_key:`lp-${code.toLowerCase()}`,page_code:code,page_name:`Page ${code}`,is_default:false};
}

function fallbackPageGroups(ads){
  const map=new Map();
  (ads||[]).forEach(ad=>{
    const identity=localPageIdentity(ad);
    if(!map.has(identity.page_key)){
      map.set(identity.page_key,{...identity,status:"active",effective_start_date:ad.effective_start_date||null,start_date_source:"first_tagged_ad",spend:0,results:0,impressions:0,link_clicks:0,landing_page_views:0,ad_count:0,ad_names:[]});
    }
    const g=map.get(identity.page_key);
    g.spend+=Number(ad.spend||0);
    g.results+=Number(ad.results||0);
    g.impressions+=Number(ad.impressions||0);
    g.link_clicks+=Number(ad.link_clicks||0);
    g.landing_page_views+=Number(ad.landing_page_views||0);
    g.ad_count+=1;
    if(ad.entity_name && !g.ad_names.includes(ad.entity_name)) g.ad_names.push(ad.entity_name);
    if(ad.effective_start_date && (!g.effective_start_date || ad.effective_start_date<g.effective_start_date)) g.effective_start_date=ad.effective_start_date;
  });
  return [...map.values()].map(g=>{
    const denominator=g.landing_page_views>0?g.landing_page_views:g.link_clicks;
    g.cpl=g.results>0?g.spend/g.results:null;
    g.cpc=g.link_clicks>0?g.spend/g.link_clicks:null;
    g.ctr=g.impressions>0?g.link_clicks*100/g.impressions:null;
    g.conversion_denominator=denominator;
    g.conversion_basis=g.landing_page_views>0?"landing_page_views":"link_clicks_proxy";
    g.conversion_rate=denominator>0?g.results*100/denominator:null;
    g.drop_off_rate=denominator>0?(denominator-g.results)*100/denominator:null;
    return g;
  }).sort((a,b)=>b.spend-a.spend);
}

function conversionBasis(summary){
  return summary.conversion_basis==="landing_page_views"?{
    denominator:"Landing-page views",description:"True LPV → registration conversion from Meta landing-page-view data."
  }:{
    denominator:"Link clicks",description:"The export does not include landing-page views, so conversion is calculated as link clicks → registrations."
  };
}

function renderConversion(data){
  const c=data.conversion_summary||{};
  const p=data.previous_conversion_summary||{};
  const basis=conversionBasis(c);
  const groups=(data.page_groups&&data.page_groups.length)?data.page_groups:fallbackPageGroups(data.ads||[]);
  const pageComparison=data.page_comparison||[];

  document.getElementById("conversionNotice").innerHTML=`<strong>Page attribution:</strong> the dashboard reads tags such as <code>[LP-A]</code> from each ad name. Ads without a tag are grouped under <strong>Main page</strong>. <strong>Conversion calculation:</strong> ${basis.description}`;
  document.getElementById("conversionBasisText").textContent=`${basis.denominator} → complete registrations, grouped by page tag.`;
  document.getElementById("pageCount").textContent=`${groups.length} page${groups.length===1?"":"s"}`;

  const cards=[
    [basis.denominator,number(c.conversion_denominator),"Conversion denominator"],
    ["Registrations",number(c.results),"Meta complete registrations only"],
    ["Page conversion",percent(c.conversion_rate),`${basis.denominator} → registration`],
    ["Drop-off",percent(c.drop_off_rate),"Did not complete registration"],
    ["Spend",money(c.spend),"Selected reporting week"],
    ["Cost / registration",money(c.cpl),"Spend ÷ registrations"]
  ];
  document.getElementById("conversionKpis").innerHTML=cards.map(x=>`<article class="card kpi"><div class="kpi-label">${x[0]}</div><div><div class="kpi-value">${x[1]}</div><div class="kpi-note">${x[2]}</div></div></article>`).join("");

  document.getElementById("conversionPages").innerHTML=groups.length?groups.map(item=>`
    <div class="compare-card">
      <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start">
        <div class="compare-title">${item.page_name}</div>${pageBadge(item)}
      </div>
      <div class="compare-metrics">
        <div class="mini-metric"><span>Spend</span><strong>${money(item.spend)}</strong></div>
        <div class="mini-metric"><span>Registrations</span><strong>${number(item.results)}</strong></div>
        <div class="mini-metric"><span>CPL</span><strong>${money(item.cpl)}</strong></div>
      </div>
      <div class="entity-sub">Conversion ${percent(item.conversion_rate)} · ${number(item.ad_count)} ad${Number(item.ad_count)===1?"":"s"}</div>
      <div class="entity-sub">Started ${formatDate(item.effective_start_date)} · ${startSourceLabel(item.start_date_source)}</div>
    </div>`).join(""):`<div class="empty">No ads are available for this period.</div>`;

  const validGroups=groups.filter(x=>x.conversion_rate!=null).sort((a,b)=>Number(b.conversion_rate)-Number(a.conversion_rate));
  const max=Math.max(1,...validGroups.map(x=>Number(x.conversion_rate)||0));
  document.getElementById("pageConversionBars").innerHTML=validGroups.length?validGroups.map(item=>`
    <div class="bar-row">
      <div class="bar-label" title="${item.page_name}">${item.page_name}</div>
      <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2,Number(item.conversion_rate)/max*100)}%"></div></div>
      <div class="bar-value">${percent(item.conversion_rate)}</div>
    </div>`).join(""):`<div class="empty">No conversion rate available.</div>`;

  const comparisonCards=[
    ["Page conversion",percent(c.conversion_rate),`Previous ${percent(p.conversion_rate)}`,change(c.conversion_rate,p.conversion_rate)],
    ["Registrations",number(c.results),`Previous ${number(p.results)}`,change(c.results,p.results)],
    ["Cost / registration",money(c.cpl),`Previous ${money(p.cpl)}`,change(c.cpl,p.cpl,true)]
  ];
  document.getElementById("conversionComparison").innerHTML=comparisonCards.map(x=>`
    <div class="compare-card">
      <div class="kpi-label">${x[0]}</div>
      <div class="kpi-value">${x[1]}</div>
      <div class="kpi-note">${x[2]}</div>
      ${deltaHtml(x[3])}
    </div>`).join("");

  table("pageGroupTable",[
    {label:"Conversion page",name:true,render:r=>`<span>${r.page_name}</span><span class="sub-cell">${r.is_default?"Ads without [LP-...] tag":`Ad tag: [LP-${r.page_code}]`}</span>`},
    {label:"Start date",render:startCell},
    {label:"Status",render:r=>statusPill(r.status)},
    {label:"Ads",numeric:true,render:r=>number(r.ad_count)},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
    {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
    {label:"CPC",numeric:true,render:r=>money(r.cpc)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"LPV",numeric:true,render:r=>number(r.landing_page_views)},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"Conversion basis",render:r=>r.conversion_basis==="landing_page_views"?"Landing-page views":"Link clicks proxy"},
    {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)},
    {label:"Drop-off",numeric:true,render:r=>percent(r.drop_off_rate)},
    {label:"CPL",numeric:true,render:r=>money(r.cpl)},
    {label:"Ads included",render:r=>`<span class="sub-cell ad-name-list">${(r.ad_names||[]).join(" · ")||"—"}</span>`},
    {label:"URL",render:r=>r.page_url?`<a href="${r.page_url}" target="_blank" rel="noopener">Open page ↗</a>`:"—"}
  ],groups,"No ads are available for page aggregation.");

  renderPageComparisonTable("pageWeekComparisonTable",pageComparison);
  if(typeof renderPageFunnels==="function") renderPageFunnels(groups);
}

function deliveryBadge(row){
  const labels={continued:"Both weeks",new:"New this week",not_in_current_week:"Not in current week"};
  return `<span class="status-badge ${row.delivery_status}">${labels[row.delivery_status]||row.delivery_status}</span>`;
}

function filteredComparisonRows(rows){
  if(!document.getElementById("hideZeroDelivery").checked) return rows;
  return rows.filter(row=>(Number(row.current.spend)||0)>0 || (Number(row.previous.spend)||0)>0);
}

function renderComparisonTable(container,rows){
  table(container,[
    {label:"Entity",name:true,render:r=>`<span>${r.entity_name}</span>${r.relation_name?`<span class="sub-cell">${r.relation_name}</span>`:""}`},
    {label:"Delivery",render:deliveryBadge},
    {label:"Previous spend",numeric:true,render:r=>money(r.previous.spend)},
    {label:"Current spend",numeric:true,render:r=>money(r.current.spend)},
    {label:"Δ spend",numeric:true,render:r=>comparisonDelta(r.change.spend,true,r.current.spend,r.previous.spend)},
    {label:"Previous results",numeric:true,render:r=>number(r.previous.results)},
    {label:"Current results",numeric:true,render:r=>number(r.current.results)},
    {label:"Δ results",numeric:true,render:r=>comparisonDelta(r.change.results,false,r.current.results,r.previous.results)},
    {label:"Previous CPL",numeric:true,render:r=>money(r.previous.cpl)},
    {label:"Current CPL",numeric:true,render:r=>money(r.current.cpl)},
    {label:"Δ CPL",numeric:true,render:r=>comparisonDelta(r.change.cpl,true,r.current.cpl,r.previous.cpl)},
    {label:"Previous clicks",numeric:true,render:r=>number(r.previous.link_clicks)},
    {label:"Current clicks",numeric:true,render:r=>number(r.current.link_clicks)},
    {label:"Δ clicks",numeric:true,render:r=>comparisonDelta(r.change.link_clicks,false,r.current.link_clicks,r.previous.link_clicks)},
    {label:"Previous CPC",numeric:true,render:r=>money(r.previous.cpc)},
    {label:"Current CPC",numeric:true,render:r=>money(r.current.cpc)},
    {label:"Δ CPC",numeric:true,render:r=>comparisonDelta(r.change.cpc,true,r.current.cpc,r.previous.cpc)},
    {label:"Previous CTR",numeric:true,render:r=>percent(r.previous.ctr)},
    {label:"Current CTR",numeric:true,render:r=>percent(r.current.ctr)},
    {label:"Δ CTR",numeric:true,render:r=>comparisonDelta(r.change.ctr,false,r.current.ctr,r.previous.ctr)}
  ],filteredComparisonRows(rows));
}

function renderPageComparisonTable(container,rows){
  table(container,[
    {label:"Conversion page",name:true,render:r=>`<span>${r.page_name}</span><span class="sub-cell">${r.page_code==="MAIN"?"Main page":`[LP-${r.page_code}]`}</span>`},
    {label:"Delivery",render:deliveryBadge},
    {label:"Start date",render:r=>formatDate(r.effective_start_date)},
    {label:"Previous ads",numeric:true,render:r=>number(r.previous.ad_count)},
    {label:"Current ads",numeric:true,render:r=>number(r.current.ad_count)},
    {label:"Previous spend",numeric:true,render:r=>money(r.previous.spend)},
    {label:"Current spend",numeric:true,render:r=>money(r.current.spend)},
    {label:"Δ spend",numeric:true,render:r=>comparisonDelta(r.change.spend,true,r.current.spend,r.previous.spend)},
    {label:"Previous clicks",numeric:true,render:r=>number(r.previous.link_clicks)},
    {label:"Current clicks",numeric:true,render:r=>number(r.current.link_clicks)},
    {label:"Previous results",numeric:true,render:r=>number(r.previous.results)},
    {label:"Current results",numeric:true,render:r=>number(r.current.results)},
    {label:"Δ results",numeric:true,render:r=>comparisonDelta(r.change.results,false,r.current.results,r.previous.results)},
    {label:"Previous conversion",numeric:true,render:r=>percent(r.previous.conversion_rate)},
    {label:"Current conversion",numeric:true,render:r=>percent(r.current.conversion_rate)},
    {label:"Δ conversion",numeric:true,render:r=>comparisonDelta(r.change.conversion_rate,false,r.current.conversion_rate,r.previous.conversion_rate)},
    {label:"Previous CPL",numeric:true,render:r=>money(r.previous.cpl)},
    {label:"Current CPL",numeric:true,render:r=>money(r.current.cpl)},
    {label:"Δ CPL",numeric:true,render:r=>comparisonDelta(r.change.cpl,true,r.current.cpl,r.previous.cpl)}
  ],filteredComparisonRows(rows),"No page comparison is available for the selected periods.");
}

function renderComparisonKpis(data){
  const c=data.current_totals,p=data.previous_totals;
  const items=[
    ["Spend",money(c.spend),`Previous ${money(p.spend)}`,change(c.spend,p.spend,true)],
    ["Registrations",number(c.results),`Previous ${number(p.results)}`,change(c.results,p.results)],
    ["CPL",money(c.cpl),`Previous ${money(p.cpl)}`,change(c.cpl,p.cpl,true)],
    ["Link clicks",number(c.link_clicks),`Previous ${number(p.link_clicks)}`,change(c.link_clicks,p.link_clicks)],
    ["CPC",money(c.cpc),`Previous ${money(p.cpc)}`,change(c.cpc,p.cpc,true)],
    ["CTR",percent(c.ctr),`Previous ${percent(p.ctr)}`,change(c.ctr,p.ctr)]
  ];
  document.getElementById("comparisonKpis").innerHTML=items.map(x=>`<article class="card kpi"><div class="kpi-label">${x[0]}</div><div><div class="kpi-value">${x[1]}</div><div class="kpi-note">${x[2]}</div>${deltaHtml(x[3])}</div></article>`).join("");
}

function renderDetailedComparison(data){
  renderComparisonKpis(data);
  renderComparisonTable("campaignComparisonTable",data.campaigns);
  renderComparisonTable("adsetComparisonTable",data.adsets);
  renderComparisonTable("adComparisonTable",data.ads);
  renderPageComparisonTable("pageComparisonTable",data.pages||[]);
}

async function loadComparison(){
  const currentId=document.getElementById("compareCurrent").value;
  const previousId=document.getElementById("comparePrevious").value;
  if(!currentId || !previousId || currentId===previousId) return;
  const response=await fetch(`/api/comparison?current_week_id=${currentId}&previous_week_id=${previousId}`);
  const data=await response.json();
  if(!response.ok){alert(data.detail||"Could not load comparison.");return}
  comparisonData=data;
  renderDetailedComparison(data);
}

async function loadDashboard(weekId){
  const url=weekId?`/api/dashboard?week_id=${weekId}`:"/api/dashboard";
  dashboard=await fetch(url).then(r=>r.json());
  const empty=!dashboard.current_week;
  document.getElementById("emptyState").classList.toggle("hidden",!empty);
  if(empty){document.getElementById("kpis").innerHTML="";return}
  document.getElementById("heroPeriod").textContent=dashboard.current_week.label;
  document.getElementById("heroComparison").textContent=dashboard.previous_week?dashboard.previous_week.label:"No earlier week imported";
  const safe=(label,fn)=>{
    try{fn()}catch(error){
      console.error(`Dashboard render error in ${label}:`,error);
    }
  };
  safe("overview KPIs",()=>renderKpis(dashboard));
  safe("campaign cards",()=>renderCampaignCards(dashboard.campaigns));
  safe("ad-set bars",()=>renderAdsetBars(dashboard.adsets));
  safe("top ads",()=>renderTopAds(dashboard.ads));
  // Page conversion renders independently, so another table can never leave it blank.
  safe("page conversion",()=>renderConversion(dashboard));
  safe("performance tables",()=>renderPerformanceTables(dashboard));
  safe("daily performance",()=>renderDaily());
  safe("campaign hierarchy",()=>renderHierarchy(dashboard));
  if(typeof renderAdvancedCurrent==="function" && advancedState?.rows?.length) safe("management intelligence",()=>renderAdvancedCurrent());
}


[
  "campaignSearch","campaignStatusFilter"
].forEach(id=>document.getElementById(id)?.addEventListener("input",renderCampaignTable));
[
  "adsetSearch","adsetCampaignFilter","adsetStatusFilter"
].forEach(id=>document.getElementById(id)?.addEventListener("input",renderAdsetTable));
[
  "adSearch","adCampaignFilter","adAdsetFilter","adPageFilter","adStatusFilter","adResultFilter"
].forEach(id=>document.getElementById(id)?.addEventListener("input",renderAdTable));
[
  "dailyAdSearch","dailyCampaignFilter","dailyAdsetFilter","dailyPageFilter","dailyHideZero"
].forEach(id=>document.getElementById(id)?.addEventListener("input",renderDaily));



/* Responsive SVG charts for goals and historical comparisons */
function chartNumber(value,formatter){return value==null||!Number.isFinite(Number(value))?"—":formatter(Number(value))}
function shortMonthLabel(key){if(!/^\d{4}-\d{2}$/.test(String(key||"")))return String(key||"");return new Intl.DateTimeFormat("en-GB",{month:"short",year:"2-digit",timeZone:"UTC"}).format(new Date(`${key}-01T12:00:00Z`))}
function chartEmpty(id,message="No chart data is available."){const el=document.getElementById(id);if(el)el.innerHTML=`<div class="chart-empty">${message}</div>`}
function svgPolyline(points){return points.map(point=>`${point.x.toFixed(1)},${point.y.toFixed(1)}`).join(" ")}
function renderCumulativePacingChart(containerId,{month,totalDays,cutoff,rows,targetTotal,metricKey,formatter,actualLabel="Actual",targetLabel="Target"}){
  const container=document.getElementById(containerId);if(!container)return;
  if(!targetTotal||!month){chartEmpty(containerId,"Add a monthly goal to display the pacing curve.");return}
  const width=780,height=300,left=58,right=22,top=24,bottom=50,plotW=width-left-right,plotH=height-top-bottom;
  const values=new Map();(rows||[]).forEach(row=>values.set(row.key,safeNum(row[metricKey])));
  let cumulative=0;const actual=[];for(let day=1;day<=totalDays;day++){
    const dateKey=`${month}-${String(day).padStart(2,"0")}`;if(dateKey>cutoff)break;cumulative+=safeNum(values.get(dateKey));actual.push({day,value:cumulative});
  }
  const target=Array.from({length:totalDays},(_,i)=>({day:i+1,value:targetTotal*(i+1)/totalDays}));
  const projected=actual.length?actual.at(-1).value/actual.length*totalDays:0;
  const max=Math.max(1,targetTotal,projected,...actual.map(x=>x.value));
  const x=day=>left+(day-1)/Math.max(1,totalDays-1)*plotW,y=value=>top+plotH-(value/max)*plotH;
  const actualPts=actual.map(item=>({x:x(item.day),y:y(item.value)}));const targetPts=target.map(item=>({x:x(item.day),y:y(item.value)}));
  const ticks=[0,.25,.5,.75,1];
  const grid=ticks.map(t=>{const yy=top+plotH-(t*plotH);return `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" class="chart-grid-line"/><text x="${left-9}" y="${yy+4}" class="chart-axis-text" text-anchor="end">${formatter(max*t)}</text>`}).join("");
  const dayTicks=[1,Math.ceil(totalDays/4),Math.ceil(totalDays/2),Math.ceil(totalDays*3/4),totalDays].filter((v,i,a)=>a.indexOf(v)===i).map(day=>`<text x="${x(day)}" y="${height-20}" class="chart-axis-text" text-anchor="middle">${day}</text>`).join("");
  const points=actualPts.map((point,index)=>`<circle cx="${point.x}" cy="${point.y}" r="3.2" class="chart-point actual"><title>${actualLabel}, day ${actual[index].day}: ${formatter(actual[index].value)}</title></circle>`).join("");
  container.innerHTML=`<div class="chart-legend"><span><i class="legend-line actual"></i>${actualLabel}: <strong>${formatter(actual.at(-1)?.value||0)}</strong></span><span><i class="legend-line target"></i>${targetLabel}: <strong>${formatter(targetTotal)}</strong></span><span>Projection: <strong>${formatter(projected)}</strong></span></div><div class="chart-scroll"><svg class="goal-svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="${actualLabel} versus ${targetLabel}">${grid}<line x1="${left}" y1="${top+plotH}" x2="${width-right}" y2="${top+plotH}" class="chart-axis-line"/>${dayTicks}<polyline points="${svgPolyline(targetPts)}" class="chart-line target"/><polyline points="${svgPolyline(actualPts)}" class="chart-line actual"/>${points}</svg></div>`;
}
function renderGroupedGoalChart(containerId,{rows,actualValue,goalValue,formatter,title,actualLabel="Actual",goalLabel="Goal",lowerIsBetter=false}){
  const container=document.getElementById(containerId);if(!container)return;
  const data=(rows||[]).filter(row=>safeNum(actualValue(row))>0||safeNum(goalValue(row))>0).slice(-18);
  if(!data.length){chartEmpty(containerId);return}
  const groupW=92,width=Math.max(680,70+data.length*groupW),height=310,left=56,right=18,top=26,bottom=66,plotH=height-top-bottom;
  const values=data.flatMap(row=>[safeNum(actualValue(row)),safeNum(goalValue(row))]);const max=Math.max(1,...values)*1.12;
  const y=value=>top+plotH-(safeNum(value)/max)*plotH;const barW=24;const ticks=[0,.25,.5,.75,1];
  const grid=ticks.map(t=>{const yy=top+plotH-t*plotH;return `<line x1="${left}" y1="${yy}" x2="${width-right}" y2="${yy}" class="chart-grid-line"/><text x="${left-8}" y="${yy+4}" class="chart-axis-text" text-anchor="end">${formatter(max*t)}</text>`}).join("");
  const bars=data.map((row,index)=>{const center=left+groupW*index+groupW/2,actual=safeNum(actualValue(row)),goal=safeNum(goalValue(row)),actualY=y(actual),goalY=y(goal);return `<g><rect x="${center-barW-3}" y="${actualY}" width="${barW}" height="${Math.max(0,top+plotH-actualY)}" rx="5" class="chart-bar actual"><title>${row.label} · ${actualLabel}: ${formatter(actual)}</title></rect><rect x="${center+3}" y="${goalY}" width="${barW}" height="${Math.max(0,top+plotH-goalY)}" rx="5" class="chart-bar goal"><title>${row.label} · ${goalLabel}: ${formatter(goal)}</title></rect><text x="${center}" y="${height-34}" class="chart-axis-text chart-x-label" text-anchor="middle">${shortMonthLabel(row.key)}</text></g>`}).join("");
  container.innerHTML=`<div class="chart-title-inline"><strong>${title}</strong><div class="chart-legend"><span><i class="legend-box actual"></i>${actualLabel}</span><span><i class="legend-box goal"></i>${goalLabel}</span></div></div><div class="chart-scroll"><svg class="goal-svg grouped" viewBox="0 0 ${width} ${height}" style="min-width:${width}px" role="img" aria-label="${title}">${grid}<line x1="${left}" y1="${top+plotH}" x2="${width-right}" y2="${top+plotH}" class="chart-axis-line"/>${bars}</svg></div>`;
}
function currentMonthDailyGroups(p){return groupRangeRows((advancedState.rows||[]).filter(row=>row.report_date>=p.start&&row.report_date<=p.cutoff),row=>row.report_date,row=>formatDate(row.report_date)).sort((a,b)=>a.key.localeCompare(b.key))}
function renderMonthlyPacingCharts(p=buildGoalProjection()){
  const rows=currentMonthDailyGroups(p);
  ["overviewSpendPacingChart","strategySpendPacingChart"].forEach(id=>renderCumulativePacingChart(id,{month:p.month,totalDays:p.totalDays,cutoff:p.cutoff,rows,targetTotal:p.targetBudget,metricKey:"spend",formatter:value=>money(value),actualLabel:"Actual spend",targetLabel:"Budget pace"}));
  ["overviewRegistrationPacingChart","strategyRegistrationPacingChart"].forEach(id=>renderCumulativePacingChart(id,{month:p.month,totalDays:p.totalDays,cutoff:p.cutoff,rows,targetTotal:p.targetRegistrations,metricKey:"results",formatter:value=>decimal(value),actualLabel:"Registrations",targetLabel:"Registration pace"}));
}
function renderGoalHistoryCharts(rows){
  const target=document.getElementById("monthlyGoalHistoryCharts");if(!target)return;
  const chronological=[...(rows||[])].sort((a,b)=>a.key.localeCompare(b.key));
  target.innerHTML=`<div class="goal-chart-panel"><div id="goalBudgetHistoryChart" class="svg-chart"></div></div><div class="goal-chart-panel"><div id="goalRegistrationHistoryChart" class="svg-chart"></div></div><div class="goal-chart-panel full-chart"><div id="goalCplHistoryChart" class="svg-chart"></div></div>`;
  renderGroupedGoalChart("goalBudgetHistoryChart",{rows:chronological,actualValue:r=>r.actual.spend,goalValue:r=>r.goal?.total_budget,formatter:value=>money(value),title:"Monthly budget: actual versus goal",actualLabel:"Spend",goalLabel:"Budget"});
  renderGroupedGoalChart("goalRegistrationHistoryChart",{rows:chronological,actualValue:r=>r.actual.results,goalValue:r=>r.goal?.target_registrations,formatter:value=>decimal(value),title:"Monthly registrations: actual versus goal",actualLabel:"Registrations",goalLabel:"Target"});
  renderGroupedGoalChart("goalCplHistoryChart",{rows:chronological,actualValue:r=>r.actual.cpl,goalValue:r=>r.goal?.target_cpl,formatter:value=>money(value),title:"Monthly CPL: actual versus target",actualLabel:"Actual CPL",goalLabel:"Target CPL",lowerIsBetter:true});
}
function renderRangeMonthlyCharts(months){
  const target=document.getElementById("monthlyPerformanceCharts");if(!target)return;
  const chronological=[...(months||[])].sort((a,b)=>a.key.localeCompare(b.key));
  target.innerHTML=`<div class="goal-chart-panel"><div id="rangeSpendMonthChart" class="svg-chart"></div></div><div class="goal-chart-panel"><div id="rangeRegistrationMonthChart" class="svg-chart"></div></div><div class="goal-chart-panel full-chart"><div id="rangeCplMonthChart" class="svg-chart"></div></div>`;
  renderGroupedGoalChart("rangeSpendMonthChart",{rows:chronological,actualValue:r=>r.spend,goalValue:r=>r.goal?.total_budget,formatter:value=>money(value),title:"Spend by month",actualLabel:"Spend",goalLabel:"Budget"});
  renderGroupedGoalChart("rangeRegistrationMonthChart",{rows:chronological,actualValue:r=>r.results,goalValue:r=>r.goal?.target_registrations,formatter:value=>decimal(value),title:"Registrations by month",actualLabel:"Registrations",goalLabel:"Target"});
  renderGroupedGoalChart("rangeCplMonthChart",{rows:chronological,actualValue:r=>r.cpl,goalValue:r=>r.goal?.target_cpl,formatter:value=>money(value),title:"CPL by month",actualLabel:"Actual CPL",goalLabel:"Target CPL",lowerIsBetter:true});
}

/* Date-range and monthly analysis */
let allDashboardsCache=null;
let rangeAnalysisState=null;

function isoDateObject(value){
  const [year,month,day]=String(value||"").split("-").map(Number);
  return new Date(Date.UTC(year,month-1,day));
}
function isoFromDate(value){return value.toISOString().slice(0,10)}
function addDaysIso(value,days){const d=isoDateObject(value);d.setUTCDate(d.getUTCDate()+days);return isoFromDate(d)}
function daysInclusive(start,end){return Math.floor((isoDateObject(end)-isoDateObject(start))/86400000)+1}
function clampIso(value,min,max){return value<min?min:value>max?max:value}
function monthStart(value){return `${String(value).slice(0,7)}-01`}
function monthEnd(value){const d=isoDateObject(monthStart(value));d.setUTCMonth(d.getUTCMonth()+1);d.setUTCDate(0);return isoFromDate(d)}
function shiftYearIso(value,years){const d=isoDateObject(value);d.setUTCFullYear(d.getUTCFullYear()+years);return isoFromDate(d)}
function shiftMonthIso(value,months){
  const original=isoDateObject(value), day=original.getUTCDate();
  const d=new Date(Date.UTC(original.getUTCFullYear(),original.getUTCMonth()+months,1));
  const last=new Date(Date.UTC(d.getUTCFullYear(),d.getUTCMonth()+1,0)).getUTCDate();
  d.setUTCDate(Math.min(day,last));
  return isoFromDate(d);
}
function fridayWeekStart(value){
  const d=isoDateObject(value), day=d.getUTCDay(), distance=(day-5+7)%7;
  d.setUTCDate(d.getUTCDate()-distance);
  return isoFromDate(d);
}
function dateRangeLabel(start,end){return `${formatDate(start)} – ${formatDate(end)}`}
function safeCsv(value){
  const text=String(value??"");
  return /[",\n]/.test(text)?`"${text.replaceAll('"','""')}"`:text;
}

async function loadAllDashboards(){
  if(allDashboardsCache) return allDashboardsCache;
  if(typeof IS_STATIC!=="undefined" && IS_STATIC){
    allDashboardsCache=Object.values(STATIC_DATA.dashboards||{});
  }else{
    allDashboardsCache=await Promise.all((weeks||[]).map(w=>fetch(`/api/dashboard?week_id=${w.id}`).then(r=>r.json())));
  }
  return allDashboardsCache;
}

function flattenDailyHistory(dashboards){
  const sorted=[...(dashboards||[])].sort((a,b)=>String(b.current_week?.week_end||"").localeCompare(String(a.current_week?.week_end||"")));
  const seen=new Set(), rows=[];
  sorted.forEach(data=>(data.daily_ads||[]).forEach(row=>{
    const key=`${row.report_date}::${row.entity_key}`;
    if(seen.has(key)) return;
    seen.add(key);
    rows.push({...row,source_week_id:data.current_week?.id});
  }));
  return rows.sort((a,b)=>a.report_date.localeCompare(b.report_date));
}

function rangeFilters(){
  return {
    campaign:document.getElementById("rangeCampaignFilter")?.value||"",
    adset:document.getElementById("rangeAdsetFilter")?.value||"",
    page:document.getElementById("rangePageFilter")?.value||"",
    hideZero:document.getElementById("rangeHideZero")?.checked!==false
  };
}
function filterRangeRows(rows,start,end,filters=rangeFilters()){
  return (rows||[]).filter(row=>{
    const inDate=row.report_date>=start && row.report_date<=end;
    const hasDelivery=Number(row.spend)||Number(row.impressions)||Number(row.link_clicks)||Number(row.results);
    return inDate && (!filters.campaign||row.campaign_key===filters.campaign) && (!filters.adset||row.adset_key===filters.adset) && (!filters.page||row.page_key===filters.page) && (!filters.hideZero||hasDelivery);
  });
}
function rangeMetrics(rows){
  const metrics=(rows||[]).reduce((acc,row)=>{
    acc.spend+=Number(row.spend)||0;
    acc.results+=Number(row.results)||0;
    acc.impressions+=Number(row.impressions)||0;
    acc.link_clicks+=Number(row.link_clicks)||0;
    acc.landing_page_views+=Number(row.landing_page_views)||0;
    acc.denominator+=Number(row.conversion_denominator)||0;
    if(row.conversion_basis) acc.bases.add(row.conversion_basis);
    return acc;
  },{spend:0,results:0,impressions:0,link_clicks:0,landing_page_views:0,denominator:0,bases:new Set()});
  metrics.cpl=metrics.results?metrics.spend/metrics.results:null;
  metrics.cpc=metrics.link_clicks?metrics.spend/metrics.link_clicks:null;
  metrics.ctr=metrics.impressions?metrics.link_clicks*100/metrics.impressions:null;
  metrics.cost_per_lpv=metrics.landing_page_views?metrics.spend/metrics.landing_page_views:null;
  metrics.conversion_rate=metrics.denominator?metrics.results*100/metrics.denominator:null;
  metrics.drop_off_rate=metrics.conversion_rate==null?null:100-metrics.conversion_rate;
  metrics.conversion_basis=metrics.bases.size===1?[...metrics.bases][0]:metrics.bases.size>1?"mixed":"unavailable";
  return metrics;
}
function groupRangeRows(rows,keyFn,labelFn){
  const groups=new Map();
  (rows||[]).forEach(row=>{
    const key=keyFn(row);
    if(!groups.has(key)) groups.set(key,{key,label:labelFn(row),rows:[]});
    groups.get(key).rows.push(row);
  });
  return [...groups.values()].map(group=>({...group,...rangeMetrics(group.rows)}));
}
function rangeEntityGroups(rows,type){
  const config={
    campaign:[r=>r.campaign_key||normalized(r.campaign_name),r=>r.campaign_name||"Unknown campaign"],
    adset:[r=>r.adset_key||normalized(r.adset_name),r=>r.adset_name||"Unknown ad set"],
    ad:[r=>r.entity_key,r=>r.entity_name||"Unknown ad"],
    page:[r=>r.page_key||"main",r=>r.page_name||"Main page"]
  }[type];
  return groupRangeRows(rows,config[0],config[1]).map(group=>{
    const first=group.rows[0]||{};
    return {...group,
      entity_key:group.key,entity_name:group.label,
      campaign_name:first.campaign_name,adset_name:first.adset_name,
      page_key:first.page_key||"main",page_code:first.page_code||"MAIN",page_name:first.page_name||"Main page",
      is_default:Boolean(first.is_default),ad_count:new Set(group.rows.map(r=>r.entity_key)).size
    };
  });
}
function trendGroupKey(row,granularity){
  if(granularity==="day") return row.report_date;
  if(granularity==="week") return fridayWeekStart(row.report_date);
  return row.report_date.slice(0,7);
}
function trendLabel(key,granularity){
  if(granularity==="day") return formatDate(key);
  if(granularity==="week") return `${formatDate(key)} – ${formatDate(addDaysIso(key,6))}`;
  const [year,month]=key.split("-").map(Number);
  return new Intl.DateTimeFormat("en-GB",{month:"short",year:"numeric"}).format(new Date(Date.UTC(year,month-1,1)));
}
function resolveGranularity(start,end){
  const selected=document.getElementById("rangeGranularity")?.value||"auto";
  if(selected!=="auto") return selected;
  const days=daysInclusive(start,end);
  return days<=45?"day":days<=240?"week":"month";
}
function periodComparisonDates(start,end,mode){
  if(mode==="none") return null;
  if(mode==="custom") return {start:document.getElementById("compareRangeStart").value,end:document.getElementById("compareRangeEnd").value};
  if(mode==="previousMonth") return {start:shiftMonthIso(start,-1),end:shiftMonthIso(end,-1)};
  if(mode==="previousYear") return {start:shiftYearIso(start,-1),end:shiftYearIso(end,-1)};
  const days=daysInclusive(start,end);
  return {start:addDaysIso(start,-days),end:addDaysIso(start,-1)};
}
function rangePresetDates(preset,minDate,maxDate){
  if(preset==="all") return {start:minDate,end:maxDate};
  if(preset==="yearToDate") return {start:`${maxDate.slice(0,4)}-01-01`,end:maxDate};
  if(preset==="currentMonth") return {start:monthStart(maxDate),end:maxDate};
  if(preset==="previousMonth"){
    const end=addDaysIso(monthStart(maxDate),-1);return {start:monthStart(end),end};
  }
  const days=preset==="latest7"?7:preset==="latest90"?90:30;
  return {start:clampIso(addDaysIso(maxDate,-days+1),minDate,maxDate),end:maxDate};
}
function populateRangeFilters(rows){
  const populate=(id,items,key,label,placeholder)=>{
    const select=document.getElementById(id),current=select.value;
    const unique=[...new Map(items.filter(x=>x[key]).map(x=>[x[key],x])).values()].sort((a,b)=>String(a[label]||"").localeCompare(String(b[label]||"")));
    select.innerHTML=`<option value="">${placeholder}</option>`+unique.map(x=>`<option value="${x[key]}">${x[label]}</option>`).join("");
    if([...select.options].some(o=>o.value===current)) select.value=current;
  };
  populate("rangeCampaignFilter",rows,"campaign_key","campaign_name","All campaigns");
  populate("rangeAdsetFilter",rows,"adset_key","adset_name","All ad sets");
  populate("rangePageFilter",rows,"page_key","page_name","All pages");
}
function setRangePreset(){
  if(!rangeAnalysisState) return;
  const preset=document.getElementById("rangePreset").value;
  if(preset==="custom") return;
  const dates=rangePresetDates(preset,rangeAnalysisState.minDate,rangeAnalysisState.maxDate);
  document.getElementById("rangeStart").value=dates.start;
  document.getElementById("rangeEnd").value=dates.end;
}
function renderRangeKpis(current,previous){
  const items=[
    ["Spend",money(current.spend),previous?`Comparison ${money(previous.spend)}`:"No comparison",previous?change(current.spend,previous.spend,true):null],
    ["Registrations",number(current.results),previous?`Comparison ${number(previous.results)}`:"Meta complete registrations only",previous?change(current.results,previous.results):null],
    ["Cost / registration",money(current.cpl),previous?`Comparison ${money(previous.cpl)}`:"Recalculated CPL",previous?change(current.cpl,previous.cpl,true):null],
    ["Link clicks",number(current.link_clicks),previous?`Comparison ${number(previous.link_clicks)}`:`${number(current.impressions)} impressions`,previous?change(current.link_clicks,previous.link_clicks):null],
    ["CPC",money(current.cpc),previous?`Comparison ${money(previous.cpc)}`:`CTR ${percent(current.ctr)}`,previous?change(current.cpc,previous.cpc,true):null],
    ["Conversion",percent(current.conversion_rate),previous?`Comparison ${percent(previous.conversion_rate)}`:current.conversion_basis==="landing_page_views"?"LPV → registration":current.conversion_basis==="mixed"?"Mixed LPV / click basis":"Click → registration proxy",previous?change(current.conversion_rate,previous.conversion_rate):null]
  ];
  document.getElementById("rangeKpis").innerHTML=items.map(x=>`<article class="card kpi"><div class="kpi-label">${x[0]}</div><div><div class="kpi-value">${x[1]}</div><div class="kpi-note">${x[2]}</div>${previous?deltaHtml(x[3]):""}</div></article>`).join("");
}
function renderRangeTrend(rows,start,end){
  const granularity=resolveGranularity(start,end);
  const grouped=groupRangeRows(rows,r=>trendGroupKey(r,granularity),r=>trendLabel(trendGroupKey(r,granularity),granularity)).sort((a,b)=>a.key.localeCompare(b.key));
  const container=document.getElementById("rangeTrend");
  document.getElementById("rangeTrendSubtitle").textContent=`Grouped by ${granularity}. Spend, registrations and recalculated CPL.`;
  if(!grouped.length){container.innerHTML='<div class="empty">No detailed delivery exists for this range.</div>';return}
  const maxSpend=Math.max(...grouped.map(x=>x.spend),1),maxResults=Math.max(...grouped.map(x=>x.results),1);
  container.innerHTML=grouped.map(item=>`<div class="range-trend-row">
    <div class="range-trend-date">${item.label}</div>
    <div class="range-trend-series"><span>Spend</span><div class="daily-track"><div class="daily-fill spend" style="width:${Math.max(2,item.spend/maxSpend*100)}%"></div></div><strong>${money(item.spend)}</strong></div>
    <div class="range-trend-series"><span>Registrations</span><div class="daily-track"><div class="daily-fill results" style="width:${item.results?Math.max(4,item.results/maxResults*100):0}%"></div></div><strong>${number(item.results)}</strong></div>
    <div class="range-trend-cpl"><span>CPL</span><strong>${money(item.cpl)}</strong></div>
  </div>`).join("");
}
function renderRangeComparisonCards(current,previous,currentDates,previousDates){
  const container=document.getElementById("rangeComparisonCards");
  if(!previous){container.innerHTML='<div class="empty">Comparison disabled.</div>';return}
  document.getElementById("rangeComparisonSubtitle").textContent=`${dateRangeLabel(currentDates.start,currentDates.end)} versus ${dateRangeLabel(previousDates.start,previousDates.end)}.`;
  const cards=[
    ["Spend",current.spend,previous.spend,money,true],
    ["Registrations",current.results,previous.results,number,false],
    ["CPL",current.cpl,previous.cpl,money,true],
    ["Conversion",current.conversion_rate,previous.conversion_rate,percent,false]
  ];
  container.innerHTML=cards.map(([label,c,p,formatter,invert])=>`<div class="range-comparison-card"><div class="kpi-label">${label}</div><div class="range-comparison-values"><span>Current <strong>${formatter(c)}</strong></span><span>Comparison <strong>${formatter(p)}</strong></span></div>${deltaHtml(change(c,p,invert))}</div>`).join("");
}
function rangeTableColumns(extra=[]){return [
  ...extra,
  {label:"Spend",numeric:true,render:r=>money(r.spend)},
  {label:"Registrations",numeric:true,render:r=>number(r.results)},
  {label:"CPL",numeric:true,render:r=>money(r.cpl)},
  {label:"Impressions",numeric:true,render:r=>number(r.impressions)},
  {label:"Link clicks",numeric:true,render:r=>number(r.link_clicks)},
  {label:"CPC",numeric:true,render:r=>money(r.cpc)},
  {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
  {label:"LPV",numeric:true,render:r=>number(r.landing_page_views)},
  {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)}
]}
function buildRangeComparison(currentGroups,previousGroups,type){
  const previousMap=new Map(previousGroups.map(x=>[x.key,x]));
  const currentMap=new Map(currentGroups.map(x=>[x.key,x]));
  return [...new Set([...currentMap.keys(),...previousMap.keys()])].map(key=>{
    const c=currentMap.get(key),p=previousMap.get(key),sample=c||p;
    const current=c||rangeMetrics([]),previous=p||rangeMetrics([]);
    return {
      entity_key:key,entity_name:sample.label,relation_name:type==="adset"?sample.campaign_name:type==="ad"?sample.adset_name:null,
      delivery_status:c&&p?"continued":c?"new":"not_in_current_week",current_status:c?"active":"inactive",previous_status:p?"active":"inactive",
      current,previous,change:{spend:change(current.spend,previous.spend)?.value??null,results:change(current.results,previous.results)?.value??null,cpl:change(current.cpl,previous.cpl)?.value??null,link_clicks:change(current.link_clicks,previous.link_clicks)?.value??null,cpc:change(current.cpc,previous.cpc)?.value??null,ctr:change(current.ctr,previous.ctr)?.value??null},
      page_key:sample.page_key,page_code:sample.page_code,page_name:sample.page_name,effective_start_date:null
    };
  }).sort((a,b)=>Number(b.current.spend)-Number(a.current.spend));
}
function renderMonthTable(rows){
  const data=groupRangeRows(rows,r=>r.report_date.slice(0,7),r=>monthLabelFromKey(r.report_date.slice(0,7))).sort((a,b)=>a.key.localeCompare(b.key));
  const dataMap=new Map(data.map(item=>[item.key,item])),goalMap=new Map((advancedConfig.monthly_goals||[]).map(item=>[item.month,item]));
  const months=[...new Set([...dataMap.keys(),...goalMap.keys()])].sort().map(key=>{const actual=dataMap.get(key)||rangeMetrics([]),goal=goalMap.get(key)||null;return {key,label:monthLabelFromKey(key),...actual,goal,budget_variance:goal?actual.spend-safeNum(goal.total_budget):null,result_variance:goal?actual.results-safeNum(goal.target_registrations):null}});
  months.forEach((item,index)=>{const prev=months[index-1];item.spend_change=prev?change(item.spend,prev.spend,true):null;item.results_change=prev?change(item.results,prev.results):null;item.cpl_change=prev?change(item.cpl,prev.cpl,true):null});
  renderRangeMonthlyCharts(months);
  table("monthlyPerformanceTable",[
    {label:"Month",name:true,render:r=>`<span>${r.label}</span>${r.goal?.note?`<span class="sub-cell">${r.goal.note}</span>`:""}`},
    {label:"Goal budget",numeric:true,render:r=>r.goal?money(r.goal.total_budget):"—"},
    {label:"Spend",numeric:true,render:r=>money(r.spend)},
    {label:"Budget variance",numeric:true,render:r=>r.goal?`${r.budget_variance>=0?"+":""}${money(r.budget_variance)}`:"—"},
    {label:"Goal registrations",numeric:true,render:r=>r.goal?number(r.goal.target_registrations):"—"},
    {label:"Registrations",numeric:true,render:r=>number(r.results)},
    {label:"Registration variance",numeric:true,render:r=>r.goal?`${r.result_variance>=0?"+":""}${decimal(r.result_variance)}`:"—"},
    {label:"Target CPL",numeric:true,render:r=>r.goal?money(r.goal.target_cpl):"—"},
    {label:"Actual CPL",numeric:true,render:r=>money(r.cpl)},
    {label:"Δ CPL",render:r=>deltaHtml(r.cpl_change)},
    {label:"CTR",numeric:true,render:r=>percent(r.ctr)},
    {label:"Conversion",numeric:true,render:r=>percent(r.conversion_rate)}
  ],months,"No monthly data is available for this range.");
}
function renderWeekdayTable(rows){
  const formatter=new Intl.DateTimeFormat("en-GB",{weekday:"long"});
  const groups=groupRangeRows(rows,r=>String(isoDateObject(r.report_date).getUTCDay()),r=>formatter.format(isoDateObject(r.report_date)));
  const order=[1,2,3,4,5,6,0];groups.sort((a,b)=>order.indexOf(Number(a.key))-order.indexOf(Number(b.key)));
  groups.forEach(g=>g.days=new Set(g.rows.map(r=>r.report_date)).size);
  table("weekdayPerformanceTable",rangeTableColumns([
    {label:"Weekday",name:true,render:r=>r.label},
    {label:"Days",numeric:true,render:r=>number(r.days)}
  ]),groups,"No weekday data is available.");
}
function renderRangeEntityTables(currentRows,previousRows){
  const campaigns=rangeEntityGroups(currentRows,"campaign").sort((a,b)=>b.spend-a.spend);
  const adsets=rangeEntityGroups(currentRows,"adset").sort((a,b)=>b.spend-a.spend);
  const ads=rangeEntityGroups(currentRows,"ad").sort((a,b)=>b.spend-a.spend);
  const pages=rangeEntityGroups(currentRows,"page").sort((a,b)=>b.spend-a.spend);
  table("rangeCampaignTable",rangeTableColumns([{label:"Campaign",name:true,render:r=>r.label}]),campaigns,"No campaign delivery exists for this range.");
  table("rangeAdsetTable",rangeTableColumns([{label:"Ad set",name:true,render:r=>`<span>${r.label}</span><span class="sub-cell">${r.campaign_name||""}</span>`}]),adsets,"No ad-set delivery exists for this range.");
  table("rangePageTable",rangeTableColumns([{label:"Conversion page",name:true,render:r=>`<span>${r.page_name}</span><span class="sub-cell">${r.is_default?"Ads without a page tag":`[LP-${r.page_code}]`}</span>`},{label:"Ads",numeric:true,render:r=>number(r.ad_count)}]),pages,"No conversion-page delivery exists for this range.");
  table("rangeAdTable",rangeTableColumns([{label:"Ad",name:true,render:r=>`<span>${r.label}</span><span class="sub-cell">${r.adset_name||""}</span><span class="sub-cell">${r.campaign_name||""}</span>`},{label:"Page",render:r=>r.page_name||"Main page"}]),ads.slice(0,150),"No ad delivery exists for this range.");
  if(previousRows){
    renderComparisonTable("rangeCampaignComparisonTable",buildRangeComparison(campaigns,rangeEntityGroups(previousRows,"campaign"),"campaign"));
    const pageRows=buildRangeComparison(pages,rangeEntityGroups(previousRows,"page"),"page").map(r=>({...r,page_name:r.entity_name,page_code:r.page_code||"MAIN"}));
    renderPageComparisonTable("rangePageComparisonTable",pageRows);
  }else{
    document.getElementById("rangeCampaignComparisonTable").innerHTML='<div class="empty">Comparison disabled.</div>';
    document.getElementById("rangePageComparisonTable").innerHTML='<div class="empty">Comparison disabled.</div>';
  }
}
function exportRangeCsv(rows,start,end){
  const columns=["report_date","campaign_name","adset_name","entity_name","page_name","spend","results","impressions","link_clicks","cpc","ctr","landing_page_views","conversion_rate","calculated_cpl"];
  const content=[columns.join(","),...rows.map(row=>columns.map(col=>safeCsv(row[col])).join(","))].join("\n");
  const blob=new Blob(["\ufeff"+content],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob),link=document.createElement("a");
  link.href=url;link.download=`presubs_${start}_${end}.csv`;link.click();URL.revokeObjectURL(url);
}
async function renderDateAnalysis(){
  if(!rangeAnalysisState) return;
  const start=document.getElementById("rangeStart").value,end=document.getElementById("rangeEnd").value;
  if(!start||!end||end<start){alert("Choose a valid start and end date.");return}
  const filters=rangeFilters(),currentRows=filterRangeRows(rangeAnalysisState.rows,start,end,filters);
  const compareMode=document.getElementById("rangeCompareMode").value,comparisonDates=periodComparisonDates(start,end,compareMode);
  const previousRows=comparisonDates&&comparisonDates.start&&comparisonDates.end?filterRangeRows(rangeAnalysisState.rows,comparisonDates.start,comparisonDates.end,filters):null;
  const current=rangeMetrics(currentRows),previous=previousRows?rangeMetrics(previousRows):null;
  const expected=daysInclusive(start,end),availableDates=new Set(rangeAnalysisState.rows.filter(r=>r.report_date>=start&&r.report_date<=end).map(r=>r.report_date));
  const coverage=expected?availableDates.size*100/expected:0;
  document.getElementById("rangeCoverageBadge").textContent=`${availableDates.size}/${expected} calendar days`;
  document.getElementById("rangeNotice").innerHTML=`<strong>Selected period:</strong> ${dateRangeLabel(start,end)}. Detailed rows exist on ${availableDates.size} of ${expected} calendar days (${decimal(coverage)}%). Dates without rows can mean zero delivery or unavailable daily data. Spend, registrations, clicks, LPV, CPL, CPC, CTR and conversion are recalculated. Reach and frequency are intentionally excluded because daily reach cannot be summed safely.`;
  renderRangeKpis(current,previous);renderRangeTrend(currentRows,start,end);renderRangeComparisonCards(current,previous,{start,end},comparisonDates);renderMonthTable(currentRows);renderWeekdayTable(currentRows);renderRangeEntityTables(currentRows,previousRows);if(typeof renderRangeAnnotations==="function")renderRangeAnnotations();
  rangeAnalysisState.currentRows=currentRows;rangeAnalysisState.currentDates={start,end};
}
async function initializeDateAnalysis(){
  const dashboards=await loadAllDashboards(),rows=flattenDailyHistory(dashboards);
  if(!rows.length){document.getElementById("rangeNotice").innerHTML='<strong>No daily history yet.</strong> Finish the historical API import and publish again.';return}
  const minDate=rows[0].report_date,maxDate=rows[rows.length-1].report_date;
  rangeAnalysisState={dashboards,rows,minDate,maxDate};populateRangeFilters(rows);
  ["rangeStart","rangeEnd","compareRangeStart","compareRangeEnd"].forEach(id=>{const el=document.getElementById(id);el.min=minDate;el.max=maxDate});
  setRangePreset();
  const customEls=document.querySelectorAll(".range-custom-comparison");
  const toggleCustom=()=>customEls.forEach(el=>el.classList.toggle("hidden",document.getElementById("rangeCompareMode").value!=="custom"));
  document.getElementById("rangePreset").addEventListener("change",()=>{setRangePreset();renderDateAnalysis()});
  document.getElementById("rangeCompareMode").addEventListener("change",()=>{toggleCustom();if(document.getElementById("rangeCompareMode").value==="custom"){const dates=periodComparisonDates(document.getElementById("rangeStart").value,document.getElementById("rangeEnd").value,"previousPeriod");document.getElementById("compareRangeStart").value=dates.start;document.getElementById("compareRangeEnd").value=dates.end}renderDateAnalysis()});
  document.getElementById("applyDateRange").addEventListener("click",()=>{document.getElementById("rangePreset").value="custom";renderDateAnalysis()});
  document.getElementById("exportRangeCsv").addEventListener("click",()=>{if(rangeAnalysisState.currentRows) exportRangeCsv(rangeAnalysisState.currentRows,rangeAnalysisState.currentDates.start,rangeAnalysisState.currentDates.end)});
  ["rangeCampaignFilter","rangeAdsetFilter","rangePageFilter","rangeHideZero","rangeGranularity"].forEach(id=>document.getElementById(id).addEventListener("change",renderDateAnalysis));
  toggleCustom();await renderDateAnalysis();
}

function metricSnapshot(row){
  const spend=Number(row?.spend)||0,results=Number(row?.results)||0,impressions=Number(row?.impressions)||0,link_clicks=Number(row?.link_clicks)||0;
  return {spend,results,cpl:results?spend/results:null,impressions,link_clicks,cpc:link_clicks?spend/link_clicks:null,ctr:impressions?link_clicks*100/impressions:null,reach:Number(row?.reach)||0,frequency:Number(row?.frequency)||0};
}
function clientEntityComparison(currentRows,previousRows,relationField){
  const cMap=new Map((currentRows||[]).map(r=>[r.entity_key,r])),pMap=new Map((previousRows||[]).map(r=>[r.entity_key,r]));
  return [...new Set([...cMap.keys(),...pMap.keys()])].map(key=>{
    const c=cMap.get(key),p=pMap.get(key),sample=c||p,current=metricSnapshot(c),previous=metricSnapshot(p);
    return {entity_key:key,entity_name:sample?.entity_name||key,relation_name:sample?.[relationField]||null,delivery_status:c&&p?"continued":c?"new":"not_in_current_week",current_status:c?.status||null,previous_status:p?.status||null,current,previous,change:{spend:change(current.spend,previous.spend)?.value??null,results:change(current.results,previous.results)?.value??null,cpl:change(current.cpl,previous.cpl)?.value??null,link_clicks:change(current.link_clicks,previous.link_clicks)?.value??null,cpc:change(current.cpc,previous.cpc)?.value??null,ctr:change(current.ctr,previous.ctr)?.value??null}};
  });
}
function clientPageComparison(currentRows,previousRows){
  const cMap=new Map((currentRows||[]).map(r=>[r.page_key,r])),pMap=new Map((previousRows||[]).map(r=>[r.page_key,r]));
  return [...new Set([...cMap.keys(),...pMap.keys()])].map(key=>{
    const c=cMap.get(key),p=pMap.get(key),sample=c||p;
    const shape=x=>({spend:Number(x?.spend)||0,results:Number(x?.results)||0,cpl:x?.cpl??null,conversion_rate:x?.conversion_rate??null,link_clicks:Number(x?.link_clicks)||0,landing_page_views:Number(x?.landing_page_views)||0,ad_count:Number(x?.ad_count)||0});
    const current=shape(c),previous=shape(p);
    return {page_key:key,page_name:sample?.page_name||"Main page",page_code:sample?.page_code||"MAIN",delivery_status:c&&p?"continued":c?"new":"not_in_current_week",effective_start_date:sample?.effective_start_date||null,current,previous,change:{spend:change(current.spend,previous.spend)?.value??null,results:change(current.results,previous.results)?.value??null,cpl:change(current.cpl,previous.cpl)?.value??null,conversion_rate:change(current.conversion_rate,previous.conversion_rate)?.value??null}};
  });
}
function buildClientComparison(currentId,previousId){
  const currentData=STATIC_DATA.dashboards?.[String(currentId)],previousData=STATIC_DATA.dashboards?.[String(previousId)];
  if(!currentData||!previousData) return null;
  return {current_week:currentData.current_week,previous_week:previousData.current_week,current_totals:currentData.totals,previous_totals:previousData.totals,campaigns:clientEntityComparison(currentData.campaigns,previousData.campaigns,"none"),adsets:clientEntityComparison(currentData.adsets,previousData.adsets,"campaign_name"),ads:clientEntityComparison(currentData.ads,previousData.ads,"adset_name"),pages:clientPageComparison(currentData.page_groups,previousData.page_groups)};
}


/* v10 management intelligence, creative health and data quality */
let advancedConfig={
  goals:{target_cpl:45,total_budget:70000,target_registrations:1556,launch_start:"2026-01-01",launch_end:"2026-12-31"},
  monthly_goals:[],
  thresholds:{spend_without_result_multiplier:1,high_cpl_percent:20,ctr_drop_percent:25,page_click_to_lpv_min:70,frequency_limit:3,no_result_days:3},
  annotations:[]
};
let advancedState={dashboards:[],rows:[],creativeRows:[],alerts:[],quality:[]};

async function loadAdvancedConfig(){
  try{
    if(typeof IS_STATIC!=="undefined" && IS_STATIC) return STATIC_DATA.config||advancedConfig;
    const response=await fetch("/api/dashboard-config");
    return response.ok?await response.json():advancedConfig;
  }catch(error){console.warn("Could not load dashboard settings",error);return advancedConfig}
}

function safeNum(value){const n=Number(value);return Number.isFinite(n)?n:0}
function ratioPercent(numerator,denominator){return denominator?safeNum(numerator)*100/safeNum(denominator):null}
function metricChange(current,previous){return previous?safeNum(current)*100/safeNum(previous)-100:null}
function dateDiffDays(start,end){return Math.max(0,Math.floor((isoDateObject(end)-isoDateObject(start))/86400000))}
function clamp(value,min,max){return Math.min(max,Math.max(min,value))}
function monthKey(dateValue){return String(dateValue||"").slice(0,7)}
function monthLabelFromKey(key){if(!/^\d{4}-\d{2}$/.test(key||""))return key||"";return new Intl.DateTimeFormat("en-GB",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(`${key}-01T12:00:00Z`))}
function monthBounds(key){const [year,month]=String(key).split("-").map(Number),last=new Date(Date.UTC(year,month,0)).getUTCDate();return {start:`${key}-01`,end:`${key}-${String(last).padStart(2,"0")}`,days:last}}
function goalReferenceDate(){return dashboard?.current_week?.week_end||advancedState.rows.at(-1)?.report_date||new Date().toISOString().slice(0,10)}
function monthlyGoalForMonth(key){return (advancedConfig?.monthly_goals||[]).find(item=>item.month===key)||null}
function activeMonthlyGoal(){return monthlyGoalForMonth(monthKey(goalReferenceDate()))}
function configGoal(key,fallback=0){const monthly=activeMonthlyGoal();if(monthly&&monthly[key]!=null)return safeNum(monthly[key]);return safeNum(fallback)}
function configThreshold(key,fallback=0){return safeNum(advancedConfig?.thresholds?.[key]??fallback)}
function overlapDays(startA,endA,startB,endB){const start=startA>startB?startA:startB,end=endA<endB?endA:endB;return end<start?0:daysInclusive(start,end)}
function metricsForDates(start,end){return rangeMetrics((advancedState.rows||[]).filter(row=>row.report_date>=start&&row.report_date<=end))}
function buildGoalProjection(){
  const reference=goalReferenceDate(),month=monthKey(reference),goal=monthlyGoalForMonth(month),bounds=monthBounds(month);
  const availableEnd=advancedState.rows.at(-1)?.report_date||reference;
  const cutoff=[reference,availableEnd,bounds.end].sort()[0];
  const metrics=metricsForDates(bounds.start,cutoff);
  const elapsedDays=Math.max(1,overlapDays(bounds.start,cutoff,bounds.start,bounds.end)),remainingDays=Math.max(0,bounds.days-elapsedDays);
  const targetBudget=safeNum(goal?.total_budget),targetRegistrations=safeNum(goal?.target_registrations),targetCpl=safeNum(goal?.target_cpl)||null;
  const projectedSpend=elapsedDays?metrics.spend/elapsedDays*bounds.days:null,projectedResults=elapsedDays?metrics.results/elapsedDays*bounds.days:null;
  const weekStart=dashboard?.current_week?.week_start||cutoff,weekEnd=dashboard?.current_week?.week_end||cutoff;
  const weekDays=overlapDays(weekStart,weekEnd,bounds.start,bounds.end);
  const weekActual=metricsForDates(weekStart>bounds.start?weekStart:bounds.start,weekEnd<bounds.end?weekEnd:bounds.end);
  const dailyBudget=targetBudget?targetBudget/bounds.days:null,dailyRegistrations=targetRegistrations?targetRegistrations/bounds.days:null;
  const weeklyBudget=dailyBudget!=null?dailyBudget*weekDays:null,weeklyRegistrations=dailyRegistrations!=null?dailyRegistrations*weekDays:null;
  return {...metrics,month,monthLabel:monthLabelFromKey(month),goalConfigured:Boolean(goal),goalNote:goal?.note||"",start:bounds.start,end:bounds.end,cutoff,totalDays:bounds.days,elapsedDays,remainingDays,targetBudget,targetRegistrations,targetCpl,
    budgetProgress:targetBudget?metrics.spend*100/targetBudget:null,registrationProgress:targetRegistrations?metrics.results*100/targetRegistrations:null,
    projectedSpend,projectedResults,projectedCpl:projectedResults?projectedSpend/projectedResults:null,requiredDailySpend:remainingDays?Math.max(0,targetBudget-metrics.spend)/remainingDays:null,requiredDailyResults:remainingDays?Math.max(0,targetRegistrations-metrics.results)/remainingDays:null,
    budgetVariance:projectedSpend!=null&&targetBudget?projectedSpend-targetBudget:null,resultVariance:projectedResults!=null&&targetRegistrations?projectedResults-targetRegistrations:null,
    dailyBudget,dailyRegistrations,weekDays,weeklyBudget,weeklyRegistrations,weekActual,weekStart,weekEnd};
}

function progressCard(label,value,goal,percentValue,note,good=true){
  const width=clamp(percentValue||0,0,100);
  return `<div class="goal-progress-card"><div class="goal-progress-head"><span>${label}</span><strong>${value}</strong></div><div class="goal-progress-track"><span class="${good?"good":"warn"}" style="width:${width}%"></span></div><div class="goal-progress-foot"><span>Goal ${goal}</span><span>${percent(percentValue)}</span></div><p>${note}</p></div>`;
}

function renderGoalProgress(){
  const p=buildGoalProjection();
  const targetCpl=p.targetCpl,cplGood=!targetCpl||!p.cpl||p.cpl<=targetCpl;
  const cards=p.goalConfigured?[
    progressCard(`${p.monthLabel} budget`,money(p.spend),money(p.targetBudget),p.budgetProgress,`${number(p.remainingDays)} calendar days remaining`,p.budgetProgress<=100),
    progressCard(`${p.monthLabel} registrations`,number(p.results),number(p.targetRegistrations),p.registrationProgress,`Projected ${number(p.projectedResults)}`,p.projectedResults>=p.targetRegistrations),
    progressCard("Monthly CPL",money(p.cpl),money(targetCpl),targetCpl&&p.cpl?targetCpl*100/p.cpl:0,`Projected CPL ${money(p.projectedCpl)}`,cplGood)
  ]:[`<div class="goal-progress-card"><div class="goal-progress-head"><span>${p.monthLabel}</span><strong>Goal missing</strong></div><p>Add the monthly budget, registration target and CPL target in the local admin.</p></div>`];
  ["overviewGoalProgress","strategyGoalKpis"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=cards.join("")});
  const projection=p.goalConfigured?[
    ["Monthly target",`${money(p.targetBudget)} · ${number(p.targetRegistrations)} registrations`,p.goalNote||`${money(p.dailyBudget)} and ${decimal(p.dailyRegistrations)} registrations per calendar day`],
    ["Selected week target",`${money(p.weeklyBudget)} · ${decimal(p.weeklyRegistrations)} registrations`,`${number(p.weekDays)} days of ${p.monthLabel} inside ${dateRangeLabel(p.weekStart,p.weekEnd)}`],
    ["Selected week actual",`${money(p.weekActual.spend)} · ${number(p.weekActual.results)} registrations`,`CPL ${money(p.weekActual.cpl)}`],
    ["Projected month end",`${money(p.projectedSpend)} · ${number(p.projectedResults)} registrations`,p.budgetVariance==null?"No projection":`${p.budgetVariance>=0?"Over":"Under"} budget by ${money(Math.abs(p.budgetVariance))}`],
    ["Required daily spend",money(p.requiredDailySpend),`For the remaining ${number(p.remainingDays)} days`],
    ["Required daily registrations",decimal(p.requiredDailyResults),`To reach ${number(p.targetRegistrations)}`]
  ]:[["Monthly goal missing","—",`Configure ${p.monthLabel} in the local admin.`]];
  const target=document.getElementById("projectionCards");
  if(target)target.innerHTML=projection.map(item=>`<div class="projection-card"><span>${item[0]}</span><strong>${item[1]}</strong><p>${item[2]}</p></div>`).join("");
  renderMonthlyPacingCharts(p);
}

function monthlyGoalHistoryRows(){
  const dataMonths=groupRangeRows(advancedState.rows||[],r=>r.report_date.slice(0,7),r=>monthLabelFromKey(r.report_date.slice(0,7)));
  const dataMap=new Map(dataMonths.map(item=>[item.key,item]));
  const goalMap=new Map((advancedConfig.monthly_goals||[]).map(item=>[item.month,item]));
  return [...new Set([...dataMap.keys(),...goalMap.keys()])].sort().reverse().map(key=>{
    const actual=dataMap.get(key)||rangeMetrics([]),goal=goalMap.get(key)||null;
    const budgetVariance=goal?safeNum(actual.spend)-safeNum(goal.total_budget):null,resultVariance=goal?safeNum(actual.results)-safeNum(goal.target_registrations):null;
    let status="Not configured";if(goal){if(actual.results>=safeNum(goal.target_registrations)&&actual.cpl<=safeNum(goal.target_cpl))status="Goal achieved";else if(actual.results>=safeNum(goal.target_registrations))status="Volume achieved";else if(actual.cpl&&actual.cpl<=safeNum(goal.target_cpl))status="CPL achieved";else status="Below goal"}
    return {key,label:monthLabelFromKey(key),actual,goal,budgetVariance,resultVariance,status};
  });
}
function goalStatusPill(status){const cls=status==="Goal achieved"?"good":status==="CPL achieved"||status==="Volume achieved"?"info":status==="Not configured"?"inactive":"warn";return `<span class="pill ${cls}">${status}</span>`}
function renderMonthlyGoalHistory(){
  const target=document.getElementById("monthlyGoalHistoryTable");if(!target)return;
  const historyRows=monthlyGoalHistoryRows();
  renderGoalHistoryCharts(historyRows);
  table("monthlyGoalHistoryTable",[
    {label:"Month",name:true,render:r=>`<span>${r.label}</span>${r.goal?.note?`<span class="sub-cell">${r.goal.note}</span>`:""}`},
    {label:"Goal budget",numeric:true,render:r=>r.goal?money(r.goal.total_budget):"—"},
    {label:"Actual spend",numeric:true,render:r=>money(r.actual.spend)},
    {label:"Budget variance",numeric:true,render:r=>r.goal?`${r.budgetVariance>=0?"+":""}${money(r.budgetVariance)}`:"—"},
    {label:"Goal registrations",numeric:true,render:r=>r.goal?number(r.goal.target_registrations):"—"},
    {label:"Actual registrations",numeric:true,render:r=>number(r.actual.results)},
    {label:"Registration variance",numeric:true,render:r=>r.goal?`${r.resultVariance>=0?"+":""}${decimal(r.resultVariance)}`:"—"},
    {label:"Target CPL",numeric:true,render:r=>r.goal?money(r.goal.target_cpl):"—"},
    {label:"Actual CPL",numeric:true,render:r=>money(r.actual.cpl)},
    {label:"Result",render:r=>goalStatusPill(r.status)}
  ],historyRows,"No monthly data or goals are available.");
}

function comparisonPreviousDashboard(){
  if(!dashboard?.previous_week) return null;
  return advancedState.dashboards.find(item=>String(item.current_week?.id)===String(dashboard.previous_week.id))||null;
}

function buildAlerts(){
  if(!dashboard?.current_week) return [];
  const targetCpl=configGoal("target_cpl")||safeNum(dashboard.totals?.cpl)||1;
  const thresholds=advancedConfig.thresholds||{};
  const spendNoResult=targetCpl*configThreshold("spend_without_result_multiplier",1);
  const highCplLimit=targetCpl*(1+configThreshold("high_cpl_percent",20)/100);
  const ctrDropLimit=configThreshold("ctr_drop_percent",25);
  const frequencyLimit=configThreshold("frequency_limit",3);
  const clickLpvMin=configThreshold("page_click_to_lpv_min",70);
  const previousData=comparisonPreviousDashboard();
  const previousAds=new Map((previousData?.ads||[]).map(row=>[row.entity_key,row]));
  const previousPages=new Map((previousData?.page_groups||[]).map(row=>[row.page_key,row]));
  const alerts=[];

  (dashboard.ads||[]).forEach(ad=>{
    const spend=safeNum(ad.spend),results=safeNum(ad.results),cpl=calculatedCpl(ad),frequency=safeNum(ad.frequency),ctr=safeNum(ad.ctr),previous=previousAds.get(ad.entity_key);
    if(spend>=spendNoResult&&results===0) alerts.push({severity:"critical",type:"Ad",title:`${ad.entity_name} spent ${money(spend)} without registrations`,detail:`Threshold: ${money(spendNoResult)}. Candidate to pause or investigate.`,entity:ad.entity_name});
    else if(results>0&&cpl>highCplLimit) alerts.push({severity:"warning",type:"Ad",title:`${ad.entity_name} is above the CPL target`,detail:`CPL ${money(cpl)} versus target ${money(targetCpl)}.`,entity:ad.entity_name});
    if(previous&&safeNum(previous.ctr)>0&&ctr>0){const drop=(safeNum(previous.ctr)-ctr)*100/safeNum(previous.ctr);if(drop>=ctrDropLimit)alerts.push({severity:"warning",type:"Creative",title:`CTR dropped ${decimal(drop)}% for ${ad.entity_name}`,detail:`${percent(previous.ctr)} → ${percent(ctr)} week over week.`,entity:ad.entity_name});}
    if(frequency>=frequencyLimit) alerts.push({severity:"warning",type:"Frequency",title:`High frequency on ${ad.entity_name}`,detail:`Frequency ${decimal(frequency)} versus warning level ${decimal(frequencyLimit)}.`,entity:ad.entity_name});
  });

  (dashboard.page_groups||[]).forEach(page=>{
    const clicks=safeNum(page.link_clicks),lpv=safeNum(page.landing_page_views),clickToLpv=ratioPercent(lpv,clicks),previous=previousPages.get(page.page_key);
    if(clicks>0&&lpv>0&&clickToLpv<clickLpvMin) alerts.push({severity:"warning",type:"Page",title:`${page.page_name} has a low click → LPV rate`,detail:`${percent(clickToLpv)} versus minimum ${percent(clickLpvMin)}. Check page speed and redirects.`,entity:page.page_name});
    if(previous&&safeNum(previous.conversion_rate)>0&&safeNum(page.conversion_rate)>0){const drop=(safeNum(previous.conversion_rate)-safeNum(page.conversion_rate))*100/safeNum(previous.conversion_rate);if(drop>=20)alerts.push({severity:"warning",type:"Page",title:`${page.page_name} conversion declined`,detail:`${percent(previous.conversion_rate)} → ${percent(page.conversion_rate)}.`,entity:page.page_name});}
  });

  if(String(dashboard.current_week?.id)===String(weeks?.[0]?.id)){
    const noResultDays=configThreshold("no_result_days",3);
    (advancedState.creativeRows||[]).forEach(item=>{
      if(item.m7?.spend>0&&item.daysSinceResult!=null&&item.daysSinceResult>=noResultDays){
        alerts.push({severity:"warning",type:"Creative",title:`${item.entity_name} has gone ${number(item.daysSinceResult)} days without a registration`,detail:`Recent 7-day spend: ${money(item.m7.spend)}.`,entity:item.entity_name});
      }
    });
  }

  const p=buildGoalProjection();
  if(!p.goalConfigured) alerts.push({severity:"warning",type:"Goal",title:`Monthly goal missing for ${p.monthLabel}`,detail:"Add the monthly budget, registration target and CPL target in the local admin.",entity:"Monthly goal"});
  if(p.projectedSpend&&p.targetBudget&&p.projectedSpend>p.targetBudget*1.05) alerts.push({severity:"warning",type:"Budget",title:"Projected spend is above the launch budget",detail:`Projection ${money(p.projectedSpend)} versus budget ${money(p.targetBudget)}.`,entity:"Budget"});
  if(p.projectedResults!=null&&p.targetRegistrations&&p.projectedResults<p.targetRegistrations*.95) alerts.push({severity:"critical",type:"Goal",title:"Projected registrations are below target",detail:`Projection ${number(p.projectedResults)} versus target ${number(p.targetRegistrations)}.`,entity:"Registrations"});
  if(!alerts.length) alerts.push({severity:"good",type:"Account",title:"No critical management alerts for this period",detail:"The configured thresholds were not breached.",entity:"Account"});
  return alerts.sort((a,b)=>severityOrder(a.severity)-severityOrder(b.severity));
}

function alertHtml(alert){return `<div class="management-alert ${alert.severity}"><div class="alert-icon">${alert.severity==="critical"?"!":alert.severity==="warning"?"△":alert.severity==="good"?"✓":"i"}</div><div><div class="alert-heading"><strong>${alert.title}</strong><span>${severityLabel(alert.severity)} · ${alert.type}</span></div><p>${alert.detail}</p></div></div>`}
function renderAlerts(){
  const alerts=buildAlerts();advancedState.alerts=alerts;
  const actionable=alerts.filter(item=>item.severity!=="good");
  ["overviewAlerts","strategyAlerts"].forEach(id=>{const el=document.getElementById(id);if(el)el.innerHTML=alerts.slice(0,id==="overviewAlerts"?5:50).map(alertHtml).join("")});
  const labels=["overviewAlertCount","strategyAlertCount"];
  labels.forEach(id=>{const el=document.getElementById(id);if(el)el.textContent=`${actionable.length} alert${actionable.length===1?"":"s"}`});
}

function bestEntity(rows){return [...(rows||[])].filter(row=>safeNum(row.results)>0).sort((a,b)=>(calculatedCpl(a)||Infinity)-(calculatedCpl(b)||Infinity))[0]||null}
function renderExecutiveSummary(){
  const current=dashboard?.totals||{},previous=dashboard?.previous_totals||{};
  const spendDelta=metricChange(current.spend,previous.spend),resultDelta=metricChange(current.results,previous.results),cplDelta=metricChange(current.cpl,previous.cpl);
  const bestCampaign=bestEntity(dashboard?.campaigns),bestPage=[...(dashboard?.page_groups||[])].filter(row=>safeNum(row.results)>0).sort((a,b)=>safeNum(b.conversion_rate)-safeNum(a.conversion_rate))[0];
  const actionable=advancedState.alerts.filter(item=>item.severity!=="good");
  const sentences=[];
  const monthly=buildGoalProjection();
  if(monthly.goalConfigured) sentences.push(`${monthly.monthLabel} is at ${decimal(monthly.budgetProgress)}% of budget and ${decimal(monthly.registrationProgress)}% of the registration target.`);
  else sentences.push(`No monthly goal is configured for ${monthly.monthLabel}.`);
  if(spendDelta!=null)sentences.push(`Spend ${spendDelta>=0?"increased":"decreased"} ${decimal(Math.abs(spendDelta))}% versus the previous imported week.`);
  if(resultDelta!=null)sentences.push(`Registrations ${resultDelta>=0?"increased":"decreased"} ${decimal(Math.abs(resultDelta))}%.`);
  if(cplDelta!=null)sentences.push(`CPL ${cplDelta<=0?"improved":"worsened"} ${decimal(Math.abs(cplDelta))}% to ${money(current.cpl)}.`);
  if(bestCampaign)sentences.push(`${bestCampaign.entity_name} had the strongest campaign CPL at ${money(calculatedCpl(bestCampaign))}.`);
  if(bestPage)sentences.push(`${bestPage.page_name} led page conversion at ${percent(bestPage.conversion_rate)}.`);
  sentences.push(actionable.length?`${actionable.length} management alert${actionable.length===1?" requires":"s require"} attention.`:"No configured alert threshold was breached.");
  const el=document.getElementById("executiveSummary");if(el)el.innerHTML=`<p>${sentences.join(" ")}</p><div class="summary-facts"><span>CompleteRegistration only</span><span>Quiz/Lead excluded</span><span>${dashboard?.current_week?.label||""}</span></div>`;
}

function renderTimeline(containerId,start=null,end=null){
  const rows=[...(advancedConfig.annotations||[])].filter(item=>(!start||item.event_date>=start)&&(!end||item.event_date<=end)).sort((a,b)=>String(b.event_date).localeCompare(String(a.event_date)));
  const container=document.getElementById(containerId);if(!container)return;
  container.innerHTML=rows.length?rows.map(item=>`<div class="timeline-item ${item.category||"change"}"><div class="timeline-date">${formatDate(item.event_date)}</div><div><strong>${item.title}</strong><span>${item.category||"change"}</span>${item.description?`<p>${item.description}</p>`:""}</div></div>`).join(""):`<div class="empty">No timeline events in this period. Add them in the local admin.</div>`;
}

function aggregateAdHistory(rows){
  const map=new Map();
  rows.forEach(row=>{
    let item=map.get(row.entity_key);
    if(!item){item={entity_key:row.entity_key,entity_name:row.entity_name,campaign_name:row.campaign_name,adset_name:row.adset_name,page_key:row.page_key||"main",page_name:row.page_name||"Main page",rows:[],spend:0,results:0,impressions:0,link_clicks:0,landing_page_views:0};map.set(row.entity_key,item)}
    item.rows.push(row);["spend","results","impressions","link_clicks","landing_page_views"].forEach(key=>item[key]+=safeNum(row[key]));
  });
  const maxDate=rows.at(-1)?.report_date;
  const targetCpl=configGoal("target_cpl")||45,frequencyLimit=configThreshold("frequency_limit",3),ctrDropLimit=configThreshold("ctr_drop_percent",25);
  return [...map.values()].map(item=>{
    item.rows.sort((a,b)=>a.report_date.localeCompare(b.report_date));
    const recent7=item.rows.filter(r=>!maxDate||r.report_date>=addDaysIso(maxDate,-6));
    const recent3=item.rows.filter(r=>!maxDate||r.report_date>=addDaysIso(maxDate,-2));
    const m7=rangeMetrics(recent7),m3=rangeMetrics(recent3),overall=rangeMetrics(item.rows);
    const resultDates=item.rows.filter(r=>safeNum(r.results)>0).map(r=>r.report_date);
    const lastResult=resultDates.at(-1)||null;
    const daysSinceResult=lastResult&&maxDate?dateDiffDays(lastResult,maxDate):null;
    const meta=(dashboard?.ads||[]).find(ad=>ad.entity_key===item.entity_key)||{};
    const frequency=safeNum(meta.frequency);
    const ctrDrop=m7.ctr?((m7.ctr-safeNum(m3.ctr))*100/m7.ctr):0;
    let recommendation="Monitor",reason="Limited or mixed recent delivery.";
    if(m7.spend>=targetCpl&&m7.results===0){recommendation="Pause candidate";reason=`Spent ${money(m7.spend)} in 7 days without a registration.`}
    else if(m7.results>0&&m7.cpl<=targetCpl*.85&&safeNum(m3.ctr)>=safeNum(m7.ctr)*.9){recommendation="Scale";reason=`7-day CPL ${money(m7.cpl)} is materially below target.`}
    else if(frequency>=frequencyLimit||ctrDrop>=ctrDropLimit){recommendation="Refresh";reason=frequency>=frequencyLimit?`Frequency ${decimal(frequency)} is above the warning level.`:`Recent CTR declined ${decimal(ctrDrop)}%.`}
    else if(m7.results>0&&m7.cpl<=targetCpl*1.15){recommendation="Keep";reason=`7-day CPL ${money(m7.cpl)} remains near target.`}
    return {...item,overall,m7,m3,frequency,lastResult,daysSinceResult,recommendation,reason,firstDate:item.rows[0]?.report_date,lastDate:item.rows.at(-1)?.report_date,activeDays:new Set(item.rows.filter(r=>safeNum(r.spend)>0).map(r=>r.report_date)).size};
  }).sort((a,b)=>({"Pause candidate":0,"Refresh":1,"Scale":2,"Keep":3,"Monitor":4}[a.recommendation]-{"Pause candidate":0,"Refresh":1,"Scale":2,"Keep":3,"Monitor":4}[b.recommendation])||b.m7.spend-a.m7.spend);
}

function creativeActionPill(value){const cls=({"Scale":"good","Keep":"info","Monitor":"inactive","Refresh":"warn","Pause candidate":"bad"})[value]||"inactive";return `<span class="pill ${cls}">${value}</span>`}
function renderCreativeHealth(){
  const search=normalized(document.getElementById("creativeSearch")?.value),action=document.getElementById("creativeActionFilter")?.value||"",page=document.getElementById("creativePageFilter")?.value||"";
  const rows=advancedState.creativeRows.filter(row=>(!search||normalized(row.entity_name).includes(search))&&(!action||row.recommendation===action)&&(!page||row.page_key===page));
  const counts={Scale:0,Keep:0,Monitor:0,Refresh:0,"Pause candidate":0};advancedState.creativeRows.forEach(row=>counts[row.recommendation]++);
  const kpis=[["Scale",counts.Scale,"Efficient and stable"],["Keep",counts.Keep,"Near target"],["Refresh",counts.Refresh,"Fatigue signal"],["Pause candidates",counts["Pause candidate"],"High-cost / no result"]];
  document.getElementById("creativeHealthKpis").innerHTML=kpis.map(item=>`<article class="card kpi"><div class="kpi-label">${item[0]}</div><div><div class="kpi-value">${number(item[1])}</div><div class="kpi-note">${item[2]}</div></div></article>`).join("");
  table("creativeHealthTable",[
    {label:"Recommendation",render:r=>creativeActionPill(r.recommendation)},
    {label:"Ad",name:true,render:r=>`<span>${r.entity_name}</span><span class="sub-cell">${r.adset_name||""}</span><span class="sub-cell">${r.reason}</span>`},
    {label:"Page",render:r=>r.page_name},
    {label:"Active days",numeric:true,render:r=>number(r.activeDays)},
    {label:"Total spend",numeric:true,render:r=>money(r.overall.spend)},
    {label:"Total registrations",numeric:true,render:r=>number(r.overall.results)},
    {label:"7d spend",numeric:true,render:r=>money(r.m7.spend)},
    {label:"7d registrations",numeric:true,render:r=>number(r.m7.results)},
    {label:"7d CPL",numeric:true,render:r=>money(r.m7.cpl)},
    {label:"7d CTR",numeric:true,render:r=>percent(r.m7.ctr)},
    {label:"3d CPL",numeric:true,render:r=>money(r.m3.cpl)},
    {label:"3d CTR",numeric:true,render:r=>percent(r.m3.ctr)},
    {label:"Frequency",numeric:true,render:r=>decimal(r.frequency)},
    {label:"Last registration",render:r=>r.lastResult?`${formatDate(r.lastResult)}<span class="sub-cell">${number(r.daysSinceResult)} days ago</span>`:"Never"}
  ],rows,"No creatives match the selected filters.");
}

function buildQualityChecks(){
  const checks=[];if(!dashboard?.current_week)return checks;
  const daily=dashboard.daily_summary||[],ads=dashboard.ads||[],campaigns=dashboard.campaigns||[];
  const expected=daysInclusive(dashboard.current_week.week_start,dashboard.current_week.week_end),actual=new Set(daily.map(r=>r.report_date)).size;
  checks.push({status:actual===expected?"pass":"warning",title:"Daily coverage",detail:`${actual}/${expected} days available for the selected reporting period.`});
  const dailyTotals=rangeMetrics(dashboard.daily_ads||[]),weeklyAdTotals=rangeMetrics(ads);
  [["Spend",dailyTotals.spend,weeklyAdTotals.spend,.11],["Registrations",dailyTotals.results,weeklyAdTotals.results,.01],["Clicks",dailyTotals.link_clicks,weeklyAdTotals.link_clicks,1.01],["Impressions",dailyTotals.impressions,weeklyAdTotals.impressions,1.01]].forEach(([name,a,b,tolerance])=>{const diff=Math.abs(a-b);checks.push({status:diff<=tolerance?"pass":"critical",title:`Weekly vs daily ${name.toLowerCase()}`,detail:`Weekly ${name}: ${decimal(b)} · Daily sum: ${decimal(a)} · Difference: ${decimal(diff)}.`})});
  const campaignSpend=campaigns.reduce((sum,row)=>sum+safeNum(row.spend),0),adSpend=ads.reduce((sum,row)=>sum+safeNum(row.spend),0);checks.push({status:Math.abs(campaignSpend-adSpend)<=.11?"pass":"critical",title:"Campaign vs ad spend",detail:`Campaign total ${money(campaignSpend)} · Ad total ${money(adSpend)}.`});
  const missingRelations=ads.filter(ad=>!ad.campaign_name||!ad.adset_name).length;checks.push({status:missingRelations?"warning":"pass",title:"Campaign and ad-set relations",detail:missingRelations?`${missingRelations} ads have incomplete relations.`:"All ads have campaign and ad-set relations."});
  const mainAds=ads.filter(ad=>(ad.page_key||"main")==="main").length;checks.push({status:mainAds?"info":"pass",title:"Conversion-page tagging",detail:mainAds?`${mainAds} ads are assigned to Main page because their names have no [LP-...] tag.`:"Every ad uses an [LP-...] page tag."});
  const quizRows=[...campaigns,...(dashboard.adsets||[]),...ads].filter(row=>/quiz/i.test(row.entity_name||""));checks.push({status:quizRows.length?"critical":"pass",title:"Quiz / Lead exclusion",detail:quizRows.length?`${quizRows.length} excluded-name rows were found. Reimport with v10.`:"No Quiz-named campaign, ad set or ad is present. CompleteRegistration scope is active."});
  checks.push({status:safeNum(dashboard.totals?.landing_page_views)>0?"pass":"warning",title:"Landing-page-view availability",detail:safeNum(dashboard.totals?.landing_page_views)>0?"LPV is available, so page conversion uses LPV → registration.":"LPV is unavailable; conversion uses link clicks as a proxy."});
  return checks;
}

function renderQuality(){
  const checks=buildQualityChecks();advancedState.quality=checks;
  const counts={pass:0,warning:0,critical:0,info:0};checks.forEach(c=>counts[c.status]++);
  const kpis=[["Checks",checks.length,"Automated controls"],["Passed",counts.pass,"No issue detected"],["Warnings",counts.warning,"Review recommended"],["Critical",counts.critical,"Fix before decisions"]];
  document.getElementById("qualityKpis").innerHTML=kpis.map(item=>`<article class="card kpi"><div class="kpi-label">${item[0]}</div><div><div class="kpi-value">${number(item[1])}</div><div class="kpi-note">${item[2]}</div></div></article>`).join("");
  document.getElementById("qualityChecks").innerHTML=checks.map(check=>`<div class="quality-check ${check.status}"><span>${check.status==="pass"?"✓":check.status==="critical"?"!":check.status==="warning"?"△":"i"}</span><div><strong>${check.title}</strong><p>${check.detail}</p></div></div>`).join("");
}

function renderPageFunnels(groups=(dashboard?.page_groups||[])){
  const target=document.getElementById("pageFunnels");if(!target)return;
  target.innerHTML=groups.length?groups.map(page=>{
    const clicks=safeNum(page.link_clicks),lpv=safeNum(page.landing_page_views),results=safeNum(page.results),clickToLpv=ratioPercent(lpv,clicks),lpvToResult=ratioPercent(results,lpv),clickToResult=ratioPercent(results,clicks);
    return `<div class="page-funnel-card"><div class="funnel-title"><strong>${page.page_name}</strong>${pageBadge(page)}</div><div class="funnel-step"><span>Link clicks</span><strong>${number(clicks)}</strong></div><div class="funnel-rate">↓ ${lpv?percent(clickToLpv):"LPV unavailable"}</div><div class="funnel-step"><span>Landing-page views</span><strong>${lpv?number(lpv):"—"}</strong></div><div class="funnel-rate">↓ ${lpv?percent(lpvToResult):percent(clickToResult)+" click → registration"}</div><div class="funnel-step result"><span>Complete registrations</span><strong>${number(results)}</strong></div><div class="funnel-footer"><span>CPL ${money(page.cpl)}</span><span>Spend ${money(page.spend)}</span></div></div>`;
  }).join(""):`<div class="empty">No page funnel data.</div>`;
}

function renderAdvancedCurrent(){
  if(!dashboard?.current_week)return;
  renderGoalProgress();renderAlerts();renderExecutiveSummary();renderMonthlyGoalHistory();renderTimeline("managementTimeline");renderCreativeHealth();renderQuality();renderPageFunnels();
}

async function initializeAdvancedFeatures(){
  advancedConfig=await loadAdvancedConfig();
  advancedState.dashboards=await loadAllDashboards();
  advancedState.rows=flattenDailyHistory(advancedState.dashboards);
  advancedState.creativeRows=aggregateAdHistory(advancedState.rows);
  const pages=[...new Map(advancedState.creativeRows.map(row=>[row.page_key,row.page_name])).entries()];
  const pageFilter=document.getElementById("creativePageFilter");if(pageFilter)pageFilter.insertAdjacentHTML("beforeend",pages.map(([key,name])=>`<option value="${key}">${name}</option>`).join(""));
  ["creativeSearch","creativeActionFilter","creativePageFilter"].forEach(id=>document.getElementById(id)?.addEventListener("input",renderCreativeHealth));
  renderAdvancedCurrent();
}

function renderRangeAnnotations(){
  const start=document.getElementById("rangeStart")?.value,end=document.getElementById("rangeEnd")?.value;
  renderTimeline("rangeAnnotations",start,end);
}

function togglePresentationMode(){
  const enabled=document.body.classList.toggle("presentation-mode");
  const button=document.getElementById("presentationModeBtn");if(button)button.textContent=enabled?"Exit presentation":"Presentation mode";
  if(enabled){
    document.querySelectorAll(".tab").forEach(tab=>tab.classList.remove("active"));document.querySelectorAll(".view").forEach(view=>view.classList.remove("active"));
    document.querySelector('.tab[data-view="overview"]')?.classList.add("active");document.getElementById("overview")?.classList.add("active");
    window.scrollTo({top:0,behavior:"smooth"});
  }
}
document.getElementById("presentationModeBtn")?.addEventListener("click",togglePresentationMode);


async function bootstrapDashboard(){
  advancedConfig=await loadAdvancedConfig();
  await loadWeeks();
  await initializeDateAnalysis();
  await initializeAdvancedFeatures();
}
bootstrapDashboard();
