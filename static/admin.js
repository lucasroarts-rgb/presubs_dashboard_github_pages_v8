const message=(id,text,ok=true)=>{
  const el=document.getElementById(id);el.textContent=text;el.className=`message ${ok?"ok":"error"}`;
};

async function refreshOptions(){
  const [weeks,pages]=await Promise.all([
    fetch("/api/weeks").then(r=>r.json()),
    fetch("/api/pages").then(r=>r.json())
  ]);
  document.getElementById("metricsWeek").innerHTML=weeks.map(w=>`<option value="${w.id}">${w.label}</option>`).join("");
  document.getElementById("metricsPage").innerHTML=pages.map(p=>`<option value="${p.id}">${p.page_name} — ${p.variant_name}</option>`).join("");
}

document.getElementById("importForm").addEventListener("submit",async event=>{
  event.preventDefault();message("importMessage","Importing…");
  const response=await fetch("/api/import/meta",{method:"POST",body:new FormData(event.target)});
  const data=await response.json();
  if(!response.ok){message("importMessage",data.detail||"Import failed.",false);return}
  const dailyText=data.daily_detail_included
    ? ` Daily detail: ${data.counts.daily_ads} ad-day rows.`
    : " Daily detail was not included.";
  message("importMessage",`Imported ${data.week_start} to ${data.week_end}: ${data.counts.campaigns} campaigns, ${data.counts.adsets} ad sets and ${data.counts.ads} weekly ads.${dailyText}`);
  await refreshOptions();
});

document.getElementById("pageForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload=Object.fromEntries(new FormData(event.target).entries());
  const response=await fetch("/api/pages",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok){message("pageMessage",data.detail||"Could not save page.",false);return}
  message("pageMessage",`Saved: ${data.page_name} — ${data.variant_name}`);
  event.target.reset();await refreshOptions();
});

document.getElementById("metricsForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload=Object.fromEntries(new FormData(event.target).entries());
  const response=await fetch("/api/page-metrics",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok){message("metricsMessage",data.detail||"Could not save metrics.",false);return}
  message("metricsMessage","Weekly page metrics saved.");
});

refreshOptions();

let dashboardConfig=null;

function setFormValues(form, values){
  Object.entries(values||{}).forEach(([key,value])=>{
    const field=form.elements.namedItem(key);
    if(field && value!=null) field.value=value;
  });
}

function renderAnnotations(){
  const container=document.getElementById("annotationList");
  const rows=[...(dashboardConfig?.annotations||[])].sort((a,b)=>String(b.event_date).localeCompare(String(a.event_date)));
  container.innerHTML=rows.length?rows.map(item=>`
    <div class="annotation-admin-row">
      <div><strong>${item.event_date} · ${item.title}</strong><span>${item.category||"change"}${item.description?` · ${item.description}`:""}</span></div>
      <button class="btn annotation-delete" data-id="${item.id}">Delete</button>
    </div>`).join(""):`<div class="empty">No annotations yet.</div>`;
  container.querySelectorAll(".annotation-delete").forEach(button=>button.addEventListener("click",async()=>{
    if(!confirm("Delete this annotation?")) return;
    const response=await fetch(`/api/annotations/${encodeURIComponent(button.dataset.id)}`,{method:"DELETE"});
    dashboardConfig=await response.json();
    renderAnnotations();
  }));
}

function monthLabel(month){
  if(!/^\d{4}-\d{2}$/.test(month||"")) return month||"";
  return new Intl.DateTimeFormat("en-GB",{month:"long",year:"numeric",timeZone:"UTC"}).format(new Date(`${month}-01T12:00:00Z`));
}

function renderMonthlyGoals(){
  const container=document.getElementById("monthlyGoalsList");
  const rows=[...(dashboardConfig?.monthly_goals||[])].sort((a,b)=>String(b.month).localeCompare(String(a.month)));
  container.innerHTML=rows.length?rows.map(item=>`
    <div class="annotation-admin-row">
      <div><strong>${monthLabel(item.month)} · €${Number(item.total_budget||0).toLocaleString("en-IE",{minimumFractionDigits:2,maximumFractionDigits:2})}</strong><span>${Number(item.target_registrations||0).toLocaleString("en-IE")} registrations · Target CPL €${Number(item.target_cpl||0).toLocaleString("en-IE",{minimumFractionDigits:2,maximumFractionDigits:2})}${item.note?` · ${item.note}`:""}</span></div>
      <button class="btn monthly-goal-edit" data-month="${item.month}">Edit</button>
      <button class="btn monthly-goal-delete" data-month="${item.month}">Delete</button>
    </div>`).join(""):`<div class="empty">No monthly goals saved yet.</div>`;
  container.querySelectorAll(".monthly-goal-edit").forEach(button=>button.addEventListener("click",()=>{
    const item=rows.find(row=>row.month===button.dataset.month);if(!item)return;
    setFormValues(document.getElementById("monthlyGoalForm"),item);
    document.getElementById("monthlyGoalForm").scrollIntoView({behavior:"smooth",block:"center"});
  }));
  container.querySelectorAll(".monthly-goal-delete").forEach(button=>button.addEventListener("click",async()=>{
    if(!confirm(`Delete the goal for ${monthLabel(button.dataset.month)}?`)) return;
    const response=await fetch(`/api/monthly-goals/${encodeURIComponent(button.dataset.month)}`,{method:"DELETE"});
    dashboardConfig=await response.json();renderMonthlyGoals();
  }));
}

async function loadDashboardConfig(){
  dashboardConfig=await fetch("/api/dashboard-config").then(r=>r.json());
  setFormValues(document.getElementById("thresholdsForm"),dashboardConfig.thresholds);
  const monthInput=document.querySelector('#monthlyGoalForm [name="month"]');
  if(monthInput&&!monthInput.value) monthInput.value=new Date().toISOString().slice(0,7);
  renderMonthlyGoals();
  renderAnnotations();
}

document.getElementById("monthlyGoalForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const values=Object.fromEntries(new FormData(event.target).entries());
  const payload={month:values.month,target_cpl:Number(values.target_cpl||0),total_budget:Number(values.total_budget||0),target_registrations:Number(values.target_registrations||0),note:values.note||""};
  const response=await fetch("/api/monthly-goals",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok){message("monthlyGoalMessage",data.detail||"Could not save monthly goal.",false);return}
  dashboardConfig=data;renderMonthlyGoals();message("monthlyGoalMessage",`Monthly goal saved for ${monthLabel(values.month)}.`);
});

document.getElementById("thresholdsForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const values=Object.fromEntries(new FormData(event.target).entries());
  const numberValue=key=>Number(values[key]||0);
  const payload={thresholds:{spend_without_result_multiplier:numberValue("spend_without_result_multiplier"),high_cpl_percent:numberValue("high_cpl_percent"),ctr_drop_percent:numberValue("ctr_drop_percent"),page_click_to_lpv_min:numberValue("page_click_to_lpv_min"),frequency_limit:numberValue("frequency_limit"),no_result_days:numberValue("no_result_days")}};
  const response=await fetch("/api/dashboard-config",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  dashboardConfig=await response.json();
  message("thresholdsMessage",response.ok?"Alert thresholds saved.":dashboardConfig.detail||"Could not save thresholds.",response.ok);
});

document.getElementById("annotationForm").addEventListener("submit",async event=>{
  event.preventDefault();
  const payload=Object.fromEntries(new FormData(event.target).entries());
  const response=await fetch("/api/annotations",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const data=await response.json();
  if(!response.ok){message("annotationMessage",data.detail||"Could not save annotation.",false);return}
  dashboardConfig=data;event.target.reset();renderAnnotations();message("annotationMessage","Annotation added.");
});

loadDashboardConfig();
