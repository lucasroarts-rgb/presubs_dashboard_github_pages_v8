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
    ["Registrations",number(t.results),"Meta complete registrations"],
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
    ["Registrations",number(c.results),"Meta complete registrations"],
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

loadWeeks();
