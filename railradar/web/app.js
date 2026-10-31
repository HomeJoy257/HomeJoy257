// RailRadar — cliente. Sin interpolación: un punto solo se mueve cuando Renfe publica otra coordenada.
const MAX_AGE = 120, PRESENCE_TTL = 90;
const params = new URLSearchParams(location.search);
const API = params.get("api") || "";
const STYLE = params.get("style") || "https://tiles.openfreemap.org/styles/positron";
const BLANK = { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#dfe3e8" } }] };
const COLORS = { fresh: "#14a44d", mid: "#e0a800", old: "#e8590c", gray: "#7b8594", station: "#6c2bd9" };

const trains = new Map();     // id -> {p, coords, seenMs, sinceMs|null}
let stationsFC = { type: "FeatureCollection", features: [] };
let clockOffset = 0, selected = null, selectedStation = null;
const show = { ld: true, st: true, cer: false };
const PRODUCTS = ["AVE", "AVLO", "ALVIA", "AVANT", "AVANT EXP", "EUROMED", "AVE INT"];
const prodOn = new Set(PRODUCTS);
const prodOk = (prod) => !prod || prodOn.has(prod);
const now = () => Date.now() + clockOffset;
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const isCer = (p) => p.source === "renfe_cercanias";
const fmtDelay = (s) => s == null ? "" : s <= 60 ? `<span class="ontime">en hora</span>` : `<span class="late">+${Math.round(s / 60)} min</span>`;
const ago = (sec) => sec < 90 ? `${Math.round(sec)} s` : `${Math.round(sec / 60)} min`;

const map = new maplibregl.Map({ container: "map", style: STYLE, center: [-3.7, 40.2], zoom: 5.3 });
map.addControl(new maplibregl.NavigationControl(), "top-right");
let styleFailed = false;
map.on("error", () => { if (!styleFailed && !map.isStyleLoaded()) { styleFailed = true; map.setStyle(BLANK); } });

function addLayers() {
  if (map.getSource("trains")) return;
  map.addSource("stations", { type: "geojson", data: stationsFC });
  map.addSource("trains", { type: "geojson", data: trainsFC() });
  map.addLayer({ id: "stations", type: "circle", source: "stations",
    paint: { "circle-radius": ["interpolate", ["linear"], ["get", "count"], 1, 10, 10, 18],
             "circle-color": COLORS.station, "circle-opacity": 0.28, "circle-stroke-color": COLORS.station, "circle-stroke-width": 2.5 } });
  map.addLayer({ id: "stations-count", type: "symbol", source: "stations", minzoom: 9,
    layout: { "text-field": ["get", "name"], "text-size": 11, "text-offset": [0, 1.4], "text-anchor": "top",
              "text-font": ["Noto Sans Regular"] },
    paint: { "text-color": COLORS.station, "text-halo-color": "#fff", "text-halo-width": 1.5 } });
  map.addLayer({ id: "trains", type: "circle", source: "trains",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 5, 12, 9],
      "circle-color": ["match", ["get", "cls"], "gray", COLORS.gray, "stopped", COLORS.fresh,
        ["step", ["get", "age"], COLORS.fresh, 30, COLORS.mid, 90, COLORS.old]],
      "circle-stroke-color": ["case", ["boolean", ["feature-state", "sel"], false], COLORS.station, "#fff"],
      "circle-stroke-width": ["case", ["boolean", ["feature-state", "sel"], false], 3, 1.5],
    } });
  map.on("click", (e) => {
    const box = [[e.point.x - 6, e.point.y - 6], [e.point.x + 6, e.point.y + 6]];
    const t = map.queryRenderedFeatures(box, { layers: ["trains"] });
    if (t.length) return selectTrain(t[0].properties.id);
    const s = map.queryRenderedFeatures(box, { layers: ["stations"] });
    if (s.length) return selectStation(String(s[0].properties.stop_id));
  });
  for (const l of ["trains", "stations"]) {
    map.on("mouseenter", l, () => (map.getCanvas().style.cursor = "pointer"));
    map.on("mouseleave", l, () => (map.getCanvas().style.cursor = ""));
  }
}
map.on("style.load", addLayers);

const hashId = (s) => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h); };

// Reglas en el cliente (por si se corta la conexión):
//  - cualquier tren desaparece si no se ha visto en el feed en 90 s
//  - Cercanías: desaparece si su coordenada lleva >120 s sin cambiar (salvo parado en estación)
function classifyClient(tr, t) {
  if ((t - tr.seenMs) / 1000 > PRESENCE_TTL) return null;
  const age = tr.sinceMs != null ? (t - tr.sinceMs) / 1000 : null;
  if (isCer(tr.p)) {
    if (age != null && age <= MAX_AGE) return { cls: "fresh", age };
    if (tr.p.status === "STOPPED_AT" && tr.sinceMs != null) return { cls: "stopped", age };
    return null;
  }
  return { cls: "gray", age };      // AV/LD/MD: Renfe no publica la hora -> siempre gris
}

function trainsFC() {
  const t = now(), features = [];
  let nLd = 0, nCer = 0, nLate = 0;
  for (const [id, tr] of trains) {
    const c = classifyClient(tr, t);
    if (!c) { trains.delete(id); if (selected === id) selectTrain(null); continue; }
    if (!prodOk(tr.p.product)) continue;
    isCer(tr.p) ? nCer++ : nLd++;
    if (tr.p.delay_s != null && tr.p.delay_s > 300) nLate++;
    if (isCer(tr.p) ? !show.cer : !show.ld) continue;
    features.push({ type: "Feature", id: hashId(id), geometry: { type: "Point", coordinates: tr.coords },
      properties: { id, cls: c.cls, age: c.age ?? 0 } });
  }
  $("k-ld").textContent = nLd; $("k-late").textContent = nLate;
  renderChips();
  return { type: "FeatureCollection", features };
}

function upsert(p) {
  const id = `${p.source}:${p.external_id}`;
  const seenMs = Date.parse(p.seen_at);
  const cur = trains.get(id);
  if (cur && cur.seenMs > seenMs) return;
  // El canal en directo no trae el retraso: se conserva el último conocido
  const delay = p.delay_s !== undefined ? p.delay_s : cur?.p.delay_s;
  trains.set(id, { p: { ...p, id, delay_s: delay }, coords: [p.longitude, p.latitude], seenMs, sinceMs: p.coord_since ? Date.parse(p.coord_since) : null });
}

function render() {
  const src = map.getSource("trains");
  if (src) src.setData(trainsFC()); else trainsFC();
  const vis = visibleStations();
  const st = map.getSource("stations");
  if (st) st.setData(show.st ? vis : { type: "FeatureCollection", features: [] });
  $("k-st").textContent = vis.features.length;
  if (selected) renderTrain();
}

async function snapshot() {
  const j = await (await fetch(`${API}/api/v1/trains/live`, { cache: "no-store" })).json();
  clockOffset = Date.parse(j.generated_at) - Date.now();
  trains.clear();
  for (const f of j.features) upsert({ ...f.properties, longitude: f.geometry.coordinates[0], latitude: f.geometry.coordinates[1] });
  render();
}
// Estaciones: solo eventos de las capas de tren encendidas (AVE/LD/MD y/o Cercanías)
function visibleStations() {
  const features = [];
  for (const f of stationsFC.features) {
    const evs = f.properties.events.filter((e) => (e.source === "renfe_cercanias" ? show.cer : show.ld) && prodOk(e.product));
    if (evs.length) features.push({ ...f, properties: { ...f.properties, count: evs.length, events: evs } });
  }
  return { type: "FeatureCollection", features };
}

async function loadStations() {
  try {
    stationsFC = await (await fetch(`${API}/api/v1/stations/events`, { cache: "no-store" })).json();
    render(); if (selectedStation) renderStation();
  } catch {}
}
async function loadSources() {
  try { renderSources((await (await fetch(`${API}/api/v1/sources`, { cache: "no-store" })).json()).sources); } catch {}
}

const sourcesState = {};
function renderSources(s) {
  Object.assign(sourcesState, s);
  const el = $("f-sources"); el.innerHTML = "";
  for (const [name, st] of Object.entries(sourcesState)) {
    const ok = st.status === "healthy";
    const last = st.last_success_at ? ago((now() - Date.parse(st.last_success_at)) / 1000) : "—";
    const row = document.createElement("div"); row.className = "src";
    row.innerHTML = `<span><i class="dot" style="background:${ok ? "var(--fresh)" : "var(--old)"}"></i>${esc(name)}</span>
      <small>${ok ? `cada ~${st.publish_period_s ?? "?"} s · hace ${last}` : esc((st.error || "error").slice(0, 60))}</small>`;
    el.appendChild(row);
  }
}

function selectTrain(id) {
  if (selected && map.getSource("trains")) map.setFeatureState({ source: "trains", id: hashId(selected) }, { sel: false });
  selected = id; selectedStation = null;
  if (id) map.setFeatureState({ source: "trains", id: hashId(id) }, { sel: true });
  $("details").hidden = !id;
  if (id) renderTrain();
}
function renderTrain() {
  const tr = trains.get(selected); if (!tr) return;
  const p = tr.p, t = now(), c = classifyClient(tr, t) || {};
  $("d-id").textContent = p.label || p.external_id;
  const ageTxt = tr.sinceMs == null
    ? "Desconocida: Renfe no publica la hora y aún no la hemos visto cambiar"
    : c.cls === "gray"
      ? `Desconocida. La coordenada cambió por última vez hace ${ago((t - tr.sinceMs) / 1000)} (visto por RailRadar; Renfe no indica cuándo se tomó)`
      : `${ago((t - tr.sinceMs) / 1000)} desde que cambió la coordenada (medido por RailRadar)`;
  const rows = [["Producto", p.product], ["Operadora", "Renfe"], ["Tipo", "GPS publicado por Renfe"],
    ["Antigüedad", ageTxt], ["Estado", { STOPPED_AT: "Parado en estación", INCOMING_AT: "Llegando a estación", IN_TRANSIT_TO: "En marcha" }[p.status]],
    ["Retraso oficial", p.delay_s != null ? (p.delay_s <= 60 ? "En hora" : `+${Math.round(p.delay_s / 60)} min`) : null],
    ["Viaje", p.trip_id], ["Lat, Lon", `${tr.coords[1].toFixed(5)}, ${tr.coords[0].toFixed(5)}`]];
  $("d-body").innerHTML = rows.filter(([, v]) => v != null && v !== "").map(([k, v]) => `<dt>${k}</dt><dd>${esc(v)}</dd>`).join("");
}

function selectStation(stopId) {
  selectTrain(null); selectedStation = stopId;
  if (stopId) setTimeout(() => $("details").scrollIntoView({ block: "nearest" }), 0);
  $("details").hidden = !stopId; if (stopId) renderStation();
}
function renderStation() {
  const f = visibleStations().features.find((x) => x.properties.stop_id === selectedStation); if (!f) return;
  const p = f.properties, evs = p.events;
  $("d-id").textContent = p.name;
  $("d-body").innerHTML = `<dt>Trenes</dt><dd><ul class="evs">${evs.map((e) =>
    `<li><span>${esc((e.product ? e.product + " " : "") + (e.label || e.train.split(":")[1]))}<br><small>${e.status === "STOPPED_AT" ? "parado" : "llegando"} · hace ${e.minutes_ago} min</small></span>${fmtDelay(e.delay_s)}</li>`).join("")}</ul></dd>
    <dt>Fuente</dt><dd>Renfe (estado del tren + retrasos oficiales)</dd>`;
}

function connect() {
  const es = new EventSource(`${API}/api/v1/stream`), conn = $("conn");
  es.addEventListener("hello", async (e) => {
    clockOffset = Date.parse(JSON.parse(e.data).server_time) - Date.now();
    conn.textContent = "Directo"; conn.className = "pill on";
    await snapshot(); loadSources(); loadStations();
  });
  es.addEventListener("train.position", (e) => upsert(JSON.parse(e.data)));
  es.addEventListener("source.status", (e) => { const s = JSON.parse(e.data); renderSources({ [s.source]: s }); });
  es.onerror = () => { conn.textContent = "Reconectando…"; conn.className = "pill off"; };
}

for (const k of ["ld", "st"]) $(`l-${k}`).addEventListener("change", (e) => { show[k] = e.target.checked; render(); });

// Chips de producto con recuento en vivo
let chipsKey = "";
function renderChips() {
  const n = {};
  for (const tr of trains.values()) if (tr.p.product) n[tr.p.product] = (n[tr.p.product] || 0) + 1;
  const key = PRODUCTS.map((p) => `${p}:${n[p] || 0}:${prodOn.has(p)}`).join("|");
  if (key === chipsKey) return; chipsKey = key;
  $("chips").innerHTML = PRODUCTS.filter((p) => n[p] || ["AVE", "AVLO", "ALVIA", "AVANT"].includes(p))
    .map((p) => `<button class="chip ${prodOn.has(p) ? "on" : ""}" data-p="${p}">${p}<small>${n[p] || 0}</small></button>`).join("");
}
$("chips").addEventListener("click", (e) => {
  const b = e.target.closest(".chip"); if (!b) return;
  const p = b.dataset.p; prodOn.has(p) ? prodOn.delete(p) : prodOn.add(p); chipsKey = ""; render();
});
setInterval(render, 1000);
setInterval(loadStations, 30000);
setInterval(() => snapshot().catch(() => {}), 60000);   // refresca retrasos oficiales
setInterval(() => renderSources({}), 5000);
connect();
