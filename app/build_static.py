from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd

APP_DIR = Path(__file__).resolve().parent
ROOT = APP_DIR.parents[0]
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from parser import load_all, adherence_by_worker, eligible_for_peer_average

RAW_DIR = ROOT / "data" / "raw"
PUBLIC_DIR = ROOT / "public"
ASSETS = ROOT / "assets"


def safe_records(df: pd.DataFrame):
    x = df.copy()
    for col in x.columns:
        if pd.api.types.is_datetime64_any_dtype(x[col]):
            x[col] = x[col].dt.strftime("%Y-%m-%d")
    return json.loads(x.to_json(orient="records", force_ascii=False))


def encode_logo() -> str:
    for p in [ASSETS / "logo.png", ASSETS / "SPL_logo.png"]:
        if p.exists():
            return "data:image/png;base64," + base64.b64encode(p.read_bytes()).decode("ascii")
    return ""


def build_integrity(df: pd.DataFrame) -> dict:
    total = int(len(df))
    pilots = int(df["crew_id"].nunique()) if total else 0
    null_raw_fleet_rows = int(df["fleet"].isna().sum()) if "fleet" in df else 0
    null_raw_fleet_pilots = int(df.loc[df["fleet"].isna(), "crew_id"].nunique()) if "fleet" in df else 0
    unclassified_pilots = int(df.loc[df["operation_type"].eq("Sin clasificar"), "crew_id"].nunique()) if "operation_type" in df else 0
    fleet_conflict_pilots = int(df.loc[df["fleet_conflict"].fillna(False), "crew_id"].nunique()) if "fleet_conflict" in df else 0
    unknown_activity = int((df["description"].eq("No clasificado")).sum()) if "description" in df else 0
    periods = sorted([str(x) for x in df["periodo"].dropna().unique()]) if total else []
    source_files = sorted([str(x) for x in df["source_file"].dropna().unique()]) if total else []
    rows_by_file = safe_records(df.groupby("source_file", dropna=False).size().reset_index(name="rows")) if total else []
    operation_counts = safe_records(df.drop_duplicates("crew_id").groupby("operation_type", dropna=False).size().reset_index(name="pilotos")) if total else []
    rank_counts = safe_records(df.drop_duplicates("crew_id").groupby(["operation_type", "rank_code"], dropna=False).size().reset_index(name="pilotos")) if total else []

    checks = [
        {"name": "Archivos de rol leídos", "status": "ok" if len(source_files) else "error", "value": len(source_files)},
        {"name": "Filas normalizadas", "status": "ok" if total > 0 else "error", "value": total},
        {"name": "Pilotos clasificados por habilitación", "status": "warn" if unclassified_pilots else "ok", "value": pilots - unclassified_pilots},
        {"name": "Pilotos sin clasificación", "status": "warn" if unclassified_pilots else "ok", "value": unclassified_pilots},
        {"name": "Pilotos con flota mixta detectada", "status": "warn" if fleet_conflict_pilots else "ok", "value": fleet_conflict_pilots},
        {"name": "Filas con actividad no clasificada", "status": "warn" if unknown_activity else "ok", "value": unknown_activity},
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "total_rows": total,
        "pilots": pilots,
        "periods": periods,
        "source_files": source_files,
        "rows_by_file": rows_by_file,
        "operation_counts": operation_counts,
        "rank_counts": rank_counts,
        "null_raw_fleet_rows": null_raw_fleet_rows,
        "null_raw_fleet_pilots": null_raw_fleet_pilots,
        "unclassified_pilots": unclassified_pilots,
        "fleet_conflict_pilots": fleet_conflict_pilots,
        "unknown_activity_rows": unknown_activity,
        "checks": checks,
    }


def aggregate(df: pd.DataFrame) -> dict:
    df = df.copy()
    for c in ["periodo", "operation_type", "rank_code", "tipo_rol", "crew_id", "nombre_completo", "activity_type", "description"]:
        if c in df.columns:
            df[c] = df[c].astype(str).fillna("")

    adherence = adherence_by_worker(df)
    eligible = eligible_for_peer_average(df)
    adherence = adherence.merge(eligible, on=["periodo", "operation_type", "rank_code", "crew_id"], how="left")
    adherence["eligible_peer_avg"] = adherence["eligible_peer_avg"].fillna(True)

    peers = adherence[adherence["eligible_peer_avg"]].copy()
    peer_avg = peers.groupby(["periodo", "operation_type", "rank_code"], dropna=False).agg(
        peer_avg_publicado=("Publicado", "mean"),
        peer_avg_ejecutado=("Ejecutado", "mean"),
        peer_avg_adherencia=("adherencia_horas", "mean"),
        peer_n=("crew_id", "nunique"),
    ).reset_index()
    adherence = adherence.merge(peer_avg, on=["periodo", "operation_type", "rank_code"], how="left")

    overview = df.groupby(["periodo", "operation_type", "rank_code", "tipo_rol"], dropna=False).agg(
        horas=("block_hours", "sum"),
        eventos=("activity_code", "count"),
        pilotos=("crew_id", "nunique"),
        vuelos=("is_flight", "sum"),
        ausencias_largas=("is_long_absence", "sum"),
    ).reset_index()

    mix = df.groupby(["periodo", "operation_type", "rank_code", "tipo_rol", "activity_type"], dropna=False).agg(
        eventos=("activity_code", "count"),
        horas=("block_hours", "sum"),
    ).reset_index()

    trend = df.groupby(["periodo", "operation_type", "rank_code", "tipo_rol"], dropna=False)["block_hours"].sum().reset_index(name="horas")
    worker_overview = df.groupby(["periodo", "operation_type", "rank_code", "crew_id", "nombre_completo", "tipo_rol"], dropna=False).agg(
        horas=("block_hours", "sum"),
        eventos=("activity_code", "count"),
        vuelos=("is_flight", "sum"),
        ausencias_largas=("is_long_absence", "sum"),
    ).reset_index()
    worker_mix = df.groupby(["periodo", "operation_type", "rank_code", "crew_id", "tipo_rol", "activity_type"], dropna=False).agg(
        eventos=("activity_code", "count"),
        horas=("block_hours", "sum"),
    ).reset_index()
    workers = df.drop_duplicates(["operation_type", "rank_code", "crew_id"])[["operation_type", "rank_code", "crew_id", "nombre_completo"]]
    workers = workers.sort_values(["operation_type", "rank_code", "nombre_completo", "crew_id"])

    return {
        "periods": sorted(df["periodo"].dropna().unique().tolist()),
        "operations": [x for x in ["Wide Body", "Narrow Body", "Sin clasificar"] if x in set(df["operation_type"])],
        "ranks": sorted(df["rank_code"].dropna().unique().tolist()),
        "workers": safe_records(workers),
        "overview": safe_records(overview),
        "worker_overview": safe_records(worker_overview),
        "mix": safe_records(mix),
        "worker_mix": safe_records(worker_mix),
        "trend": safe_records(trend),
        "adherence": safe_records(adherence),
    }


def write_html(payload: dict) -> None:
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(payload, ensure_ascii=False)
    html_template = r'''<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Dashboard SPL · Roles</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
<style>
:root{--navy:#1f0a7a;--blue:#2049c9;--cyan:#3AB7D6;--red:#e9064b;--gold:#F2B705;--bg:#F6F8FB;--ink:#16202A;--muted:#6A7785;--card:#fff;--line:#E4EAF1;}
*{box-sizing:border-box} body{margin:0;background:var(--bg);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}
.header{background:linear-gradient(120deg,#fff 0%,#fff 62%,rgba(233,6,75,.08));padding:22px clamp(16px,3vw,34px);display:flex;align-items:center;gap:22px;box-shadow:0 10px 28px rgba(31,10,122,.08);position:sticky;top:0;z-index:10}
.logo{height:62px;max-width:170px;object-fit:contain} h1{margin:0;font-size:clamp(1.45rem,3.5vw,2.5rem);letter-spacing:-.04em;color:var(--navy)} .subtitle{color:var(--muted);font-size:.96rem;margin-top:3px}
.wrap{max-width:1480px;margin:auto;padding:22px clamp(14px,3vw,30px) 50px}.panel,.card{background:var(--card);border:1px solid var(--line);border-radius:24px;box-shadow:0 12px 34px rgba(6,43,73,.07)}.panel{padding:18px;margin-bottom:18px}
.filters{display:grid;grid-template-columns:1.25fr 1fr 1.25fr 1fr;gap:14px;align-items:end}label{font-size:.82rem;color:var(--muted);font-weight:700;display:block;margin-bottom:6px}select{width:100%;padding:13px 12px;border-radius:14px;border:1px solid #dce3eb;background:#fff;color:var(--ink);font-size:15px;outline-color:var(--red)}
.empty{padding:54px 24px;text-align:center;border:2px dashed #dbe4ef;border-radius:24px;background:rgba(255,255,255,.72)}.empty h2{margin:0;color:var(--navy);font-size:clamp(1.4rem,3vw,2rem)}.empty p{color:var(--muted);max-width:760px;margin:12px auto 0;line-height:1.5}.hidden{display:none!important}
.kpis{display:grid;grid-template-columns:repeat(5,1fr);gap:14px;margin:18px 0}.kpi{padding:18px}.kpi .label{color:var(--muted);font-size:.78rem;font-weight:700;text-transform:uppercase;letter-spacing:.04em}.kpi .value{font-size:clamp(1.45rem,3vw,2.2rem);font-weight:850;color:var(--navy);margin-top:7px}.kpi .hint{font-size:.8rem;color:var(--muted);margin-top:4px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px}.card{padding:14px;min-height:430px}.full{grid-column:1/-1}.integrity{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:16px 0}.check{padding:14px;border-radius:18px;background:#fff;border:1px solid var(--line)}.dot{width:10px;height:10px;border-radius:50%;display:inline-block;margin-right:7px}.ok{background:#17A673}.warn{background:#F2B705}.error{background:#D8242F}
table{width:100%;border-collapse:collapse;font-size:.92rem}th,td{padding:10px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.04em}.note{color:var(--muted);font-size:.86rem;line-height:1.45;margin:10px 0 0}
@media(max-width:980px){.filters,.kpis,.grid,.integrity{grid-template-columns:1fr 1fr}.header{position:relative}}@media(max-width:640px){.filters,.kpis,.grid,.integrity{grid-template-columns:1fr}.header{display:block}.logo{height:44px;margin-bottom:8px}.card{min-height:360px}}
</style>
</head>
<body>
<header class="header"><img class="logo" id="logo" alt="SPL"><div><h1>Dashboard SPL · Roles Publicados y Ejecutados</h1><div class="subtitle">Filtro principal por habilitación: Wide Body / Narrow Body · Publicado en GitHub Pages desde GitHub Actions</div></div></header>
<main class="wrap">
<section class="panel"><div class="filters"><div><label>1. Flota / tipo de operación</label><select id="operation"><option value="">Escoger flota…</option></select></div><div><label>2. Cargo</label><select id="rank" disabled><option value="">Primero escoge flota</option></select></div><div><label>3. Trabajador</label><select id="worker" disabled><option value="__overview__">Overview general</option></select></div><div><label>4. Mes</label><select id="period" disabled></select></div></div></section>
<section id="empty" class="empty"><h2>Selecciona una flota para comenzar</h2><p>La primera vista queda intencionalmente sin datos. Al escoger Wide Body o Narrow Body se cargan los cargos disponibles, trabajadores de esa operación y el mes más reciente.</p></section>
<section id="dashboard" class="hidden"><div class="kpis" id="kpis"></div><div class="grid"><div class="card full" id="lineHours"></div><div class="card" id="mix"></div><div class="card" id="comparison"></div></div></section>
</main>
<script id="payload" type="application/json">__DATA__</script>
<script>
const payload = JSON.parse(document.getElementById('payload').textContent);
document.getElementById('logo').src = payload.logo || '';
const data = payload.data, integrity = payload.integrity;
const colors = ['#1f0a7a','#e9064b','#3AB7D6','#F2B705','#2049c9','#17A673'];
const fmt = new Intl.NumberFormat('es-CL', {maximumFractionDigits: 1});
const pct = x => ((Number(x)||0)*100).toFixed(1)+'%';
const byId = id => document.getElementById(id);
function unique(arr){ return [...new Set(arr.filter(x => x !== null && x !== undefined && String(x) !== ''))].sort(); }
function setOptions(sel, values, placeholder, selected=null){ sel.innerHTML=''; if(placeholder!==null){ let o=document.createElement('option'); o.value=''; o.textContent=placeholder; sel.appendChild(o); } values.forEach(v=>{ let o=document.createElement('option'); o.value=v; o.textContent=v; sel.appendChild(o); }); if(selected!==null) sel.value=selected; }
function latestPeriod(periods){ return [...periods].sort().slice(-1)[0] || ''; }
function layout(title){ return {title:{text:title,font:{color:'#1f0a7a',size:18}},paper_bgcolor:'rgba(0,0,0,0)',plot_bgcolor:'rgba(0,0,0,0)',font:{family:'Inter, Arial',color:'#16202A'},margin:{l:50,r:22,t:58,b:45},colorway:colors,hovermode:'closest',height:400}; }
function table(rows, cols){ if(!rows.length) return '<p class="note">Sin datos</p>'; return '<table><thead><tr>'+cols.map(c=>'<th>'+c.label+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+cols.map(c=>'<td>'+((r[c.key]??'') || '')+'</td>').join('')+'</tr>').join('')+'</tbody></table>'; }
function init(){
  const ops = data.operations.filter(o => o !== 'Sin clasificar');
  setOptions(byId('operation'), ops, 'Escoger flota…');
}

function renderIntegrity(){
  byId('checks').innerHTML = integrity.checks.map(c => `<div class="check"><span class="dot ${c.status}"></span><strong>${c.name}</strong><div class="note">${fmt.format(c.value)}</div></div>`).join('') + `<div class="check"><strong>Filas con flota nula original</strong><div class="note">${fmt.format(integrity.null_raw_fleet_rows)} filas / ${fmt.format(integrity.null_raw_fleet_pilots)} pilotos</div></div>`;
  byId('filesTable').innerHTML = table(integrity.rows_by_file, [{key:'source_file',label:'Archivo'}, {key:'rows',label:'Filas'}]);
  byId('rankTable').innerHTML = table(integrity.rank_counts, [{key:'operation_type',label:'Operación'}, {key:'rank_code',label:'Cargo'}, {key:'pilotos',label:'Pilotos'}]);
}
function onOperation(){
  const op = byId('operation').value;
  if(!op){ byId('dashboard').classList.add('hidden'); byId('empty').classList.remove('hidden'); byId('rank').disabled=true; byId('worker').disabled=true; byId('period').disabled=true; return; }
  const ranks = unique(data.workers.filter(w => w.operation_type===op).map(w => w.rank_code));
  setOptions(byId('rank'), ranks, null, ranks[0] || ''); byId('rank').disabled=false;
  updateWorkersAndMonths(true); renderDashboard();
}
function updateWorkersAndMonths(resetWorker=false){
  const op = byId('operation').value, rank = byId('rank').value;
  const workers = data.workers.filter(w => w.operation_type===op && w.rank_code===rank).map(w => ({value:w.crew_id, label:`${w.nombre_completo || 'Sin nombre'} · ${w.crew_id}`}));
  const workerSel = byId('worker'); workerSel.innerHTML = '<option value="__overview__">Overview general</option>' + workers.map(w=>`<option value="${w.value}">${w.label}</option>`).join(''); workerSel.disabled=false; if(resetWorker) workerSel.value='__overview__';
  const periods = unique(data.overview.filter(r => r.operation_type===op && r.rank_code===rank).map(r=>r.periodo));
  setOptions(byId('period'), periods, null, latestPeriod(periods)); byId('period').disabled=false;
}
function filterRows(rows){ const op=byId('operation').value, rank=byId('rank').value, per=byId('period').value; return rows.filter(r => r.operation_type===op && r.rank_code===rank && r.periodo===per); }
function filterRowsAllMonths(rows){ const op=byId('operation').value, rank=byId('rank').value; return rows.filter(r => r.operation_type===op && r.rank_code===rank); }
function sum(rows, key){ return rows.reduce((a,r)=>a+(Number(r[key])||0),0); }
function renderDashboard(){
  const op=byId('operation').value, rank=byId('rank').value, per=byId('period').value, worker=byId('worker').value;
  if(!op || !rank || !per){return;}
  byId('empty').classList.add('hidden'); byId('dashboard').classList.remove('hidden');
  let ov = filterRows(worker === '__overview__' ? data.overview : data.worker_overview).filter(r => worker === '__overview__' || r.crew_id === worker);
  let adh = filterRows(data.adherence); let mx = filterRows(worker === '__overview__' ? data.mix : data.worker_mix).filter(r => worker === '__overview__' || r.crew_id === worker);
  if(worker !== '__overview__'){ adh = adh.filter(r=>r.crew_id===worker); }
  const pub = sum(ov.filter(r=>r.tipo_rol==='Publicado'), 'horas'); const eje = sum(ov.filter(r=>r.tipo_rol==='Ejecutado'), 'horas');
  const pilots = worker === '__overview__' ? Math.max(...ov.map(r=>Number(r.pilotos)||0), 0) : 1;
  const flights = sum(ov, 'vuelos'); const avgAdh = adh.length ? adh.reduce((a,r)=>a+(Number(r.adherencia_horas)||0),0)/adh.length : 0;
  const selectedName = worker === '__overview__' ? `${op} · ${rank}` : ((data.workers.find(w=>w.crew_id===worker)||{}).nombre_completo || worker);
  byId('kpis').innerHTML = [
    [worker === '__overview__' ? 'Pilotos' : 'Trabajador', worker === '__overview__' ? pilots : worker, selectedName], ['Horas publicadas', fmt.format(pub), per], ['Horas ejecutadas', fmt.format(eje), `Δ ${fmt.format(eje-pub)}`], ['Adherencia', pct(avgAdh), '0 = ninguna · 1 = total'], ['Vuelos / tramos', fmt.format(flights), 'Eventos LA*']
  ].map(k=>`<div class="card kpi"><div class="label">${k[0]}</div><div class="value">${k[1]}</div><div class="hint">${k[2]}</div></div>`).join('');
  renderLineHours(worker);
  const mixRows = mx.reduce((acc,r)=>{ const k=r.activity_type; acc[k]=(acc[k]||0)+(Number(r.eventos)||0); return acc; }, {}); Plotly.react('mix', [{labels:Object.keys(mixRows), values:Object.values(mixRows), type:'pie', hole:.42}], layout(worker === '__overview__' ? 'Mix de actividades del mes seleccionado' : 'Mix de actividades del trabajador en el mes seleccionado'));
  renderComparison(adh, worker);
}
function renderLineHours(worker){
  let rows = filterRowsAllMonths(worker === '__overview__' ? data.overview : data.worker_overview);
  if(worker !== '__overview__') rows = rows.filter(r => r.crew_id === worker);
  const periods = unique(rows.map(r=>r.periodo));
  const tipos = unique(rows.map(r=>r.tipo_rol));
  const traces = tipos.map(tipo => {
    const y = periods.map(p => sum(rows.filter(r => r.periodo===p && r.tipo_rol===tipo), 'horas'));
    return {x: periods, y, type:'scatter', mode:'lines+markers', name: tipo, line:{width:3}, marker:{size:8}};
  });
  Plotly.react('lineHours', traces, layout(worker === '__overview__' ? 'Publicado vs Ejecutado · todos los meses disponibles' : 'Publicado vs Ejecutado del trabajador · todos los meses disponibles'));
}
function renderComparison(rows, worker){
  if(worker==='__overview__'){
    const r = rows.sort((a,b)=>(Number(b.delta_horas)||0)-(Number(a.delta_horas)||0)).slice(0,20);
    Plotly.react('comparison', [{x:r.map(x=>x.nombre_completo||x.crew_id), y:r.map(x=>x.delta_horas), type:'bar', name:'Delta horas'}], layout('Principales diferencias Ejecutado - Publicado · mes seleccionado'));
  } else {
    const r = rows[0] || {}; const cats=['Publicado','Ejecutado','Adherencia'];
    Plotly.react('comparison', [
      {x:cats, y:[r.Publicado||0, r.Ejecutado||0, r.adherencia_horas||0], type:'bar', name:'Trabajador'},
      {x:cats, y:[r.peer_avg_publicado||0, r.peer_avg_ejecutado||0, r.peer_avg_adherencia||0], type:'bar', name:'Promedio mismo cargo/flota'}
    ], layout('Trabajador vs promedio del mismo cargo y operación · mes seleccionado'));
  }
}
byId('operation').addEventListener('change', onOperation); byId('rank').addEventListener('change', ()=>{updateWorkersAndMonths(true); renderDashboard();}); byId('worker').addEventListener('change', renderDashboard); byId('period').addEventListener('change', renderDashboard);
init();
</script>
</body>
</html>'''
    html = html_template.replace("__DATA__", data_json.replace("</", "<\\/"))
    (PUBLIC_DIR / "index.html").write_text(html, encoding="utf-8")
    (PUBLIC_DIR / "data-integrity.json").write_text(json.dumps(payload["integrity"], ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    df = load_all(RAW_DIR)
    if df.empty:
        raise SystemExit("No se encontraron datos válidos en data/raw")
    required = ["crew_id", "rank_code", "periodo", "tipo_rol", "activity_code", "activity_type", "block_hours", "source_file", "operation_type"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise SystemExit(f"Faltan columnas requeridas: {missing}")
    payload = {"logo": encode_logo(), "integrity": build_integrity(df), "data": aggregate(df)}
    write_html(payload)
    print("Dashboard estático generado correctamente en public/index.html")
    print(f"Filas: {len(df):,}")
    print("Operaciones:", payload["data"]["operations"])
    print("Períodos:", payload["data"]["periods"])
    print("Checks:", payload["integrity"]["checks"])


if __name__ == "__main__":
    main()
