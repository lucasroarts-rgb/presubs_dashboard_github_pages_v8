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
