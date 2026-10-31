// RailRadar — cliente. Sin interpolación: un punto solo se mueve cuando llega una coordenada nueva.
const MAX_AGE = 120;
const params = new URLSearchParams(location.search);
const API = params.get("api") || "";
const STYLE = params.get("style") || "https://tiles.openfreemap.org/styles/positron";
const BLANK = { version: 8, sources: {}, layers: [{ id: "bg", type: "background", paint: { "background-color": "#dfe3e8" } }] };

const trains = new Map();      // id -> {props, coords, observedMs}
let clockOffset = 0;           // serverNow - clientNow (ms)
let maxAgeFilter = MAX_AGE;
let selected = null;
const now = () => Date.now() + clockOffset;
const $ = (id) => document.getElementById(id);

const map = new maplibregl.Map({ container: "map", style: STYLE, center: [-3.7, 40.2], zoom: 5.3, attributionControl: true });
map.addControl(new maplibregl.NavigationControl(), "top-right");
let styleFailed = false;
map.on("error", (e) => {  // si el estilo de teselas falla, fondo neutro para no perder los trenes
  if (!styleFailed && !map.isStyleLoaded()) { styleFailed = true; map.setStyle(BLANK); }
});

function addLayers() {
  if (map.getSource("trains")) return;
  map.addSource("trains", { type: "geojson", data: fc() });
  map.addLayer({ id: "trains-halo", type: "circle", source: "trains",
    paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 7, 12, 12], "circle-color": "#fff", "circle-opacity": 0.9 } });
  map.addLayer({ id: "trains", type: "circle", source: "trains",
    paint: {
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 5, 5, 12, 9],
      "circle-color": ["step", ["get", "age"], "#14a44d", 30, "#e0a800", 90, "#e8590c"],
      "circle-stroke-width": ["case", ["boolean", ["feature-state", "sel"], false], 3, 0],
      "circle-stroke-color": "#6c2bd9",
    } });
  if (!map.hasImage("arrow")) map.addImage("arrow", arrowIcon(), { pixelRatio: 2 });
  map.addLayer({ id: "trains-dir", type: "symbol", source: "trains", filter: ["has", "bearing"],
    layout: { "icon-image": "arrow", "icon-rotate": ["get", "bearing"], "icon-rotation-alignment": "map",
              "icon-allow-overlap": true, "icon-ignore-placement": true } });
  map.on("click", "trains", (e) => select(e.features[0].properties.id));
  map.on("mouseenter", "trains", () => (map.getCanvas().style.cursor = "pointer"));
  map.on("mouseleave", "trains", () => (map.getCanvas().style.cursor = ""));
}
map.on("style.load", addLayers);

// Flecha de rumbo (dato "bearing" del feed, nunca calculado)
function arrowIcon() {
  const c = document.createElement("canvas"); c.width = c.height = 48;
  const g = c.getContext("2d");
  g.fillStyle = "#14181f"; g.beginPath(); g.moveTo(24, 0); g.lineTo(31, 11); g.lineTo(17, 11); g.closePath(); g.fill();
  return g.getImageData(0, 0, 48, 48);
}

function fc() {
  const t = now(), features = [];
  for (const [id, tr] of trains) {
    const age = (t - tr.observedMs) / 1000;
    if (age > MAX_AGE) { trains.delete(id); if (selected === id) select(null); continue; }   // caduca con reloj local
    if (age > maxAgeFilter) continue;
    const p = { id, age: Math.max(0, age) };
    if (tr.props.bearing != null) p.bearing = tr.props.bearing;
    features.push({ type: "Feature", id: hashId(id), geometry: { type: "Point", coordinates: tr.coords }, properties: p });
  }
  return { type: "FeatureCollection", features };
}
const hashId = (s) => { let h = 0; for (const c of s) h = (h * 31 + c.charCodeAt(0)) | 0; return Math.abs(h); };

function upsert(props, coords) {
  const id = props.id || `${props.source}:${props.external_id}`;
  const observedMs = Date.parse(props.observed_at);
  const cur = trains.get(id);
  if (cur && cur.observedMs >= observedMs) return;   // nunca retroceder
  trains.set(id, { props: { ...props, id }, coords, observedMs });
}

function render() {
  const src = map.getSource("trains");
  const data = fc();
  if (src) src.setData(data);
  $("k-visible").textContent = data.features.length;
  if (selected) renderDetails();
}

async function snapshot() {
  const r = await fetch(`${API}/api/v1/trains/live`, { cache: "no-store" });
  const j = await r.json();
  clockOffset = Date.parse(j.generated_at) - Date.now();
  trains.clear();
  for (const f of j.features) upsert(f.properties, f.geometry.coordinates);
  render();
}

async function loadSources() {
  try {
    const j = await (await fetch(`${API}/api/v1/sources`, { cache: "no-store" })).json();
    renderSources(j.sources);
  } catch {}
}
const sourcesState = {};
function renderSources(s) {
  Object.assign(sourcesState, s);
  const el = $("f-sources"); el.innerHTML = "";
  let active = 0;
  for (const [name, st] of Object.entries(sourcesState)) {
    const ok = st.status === "healthy"; if (ok) active++;
    const last = st.last_success_at ? Math.round((now() - Date.parse(st.last_success_at)) / 1000) + " s" : "—";
    const row = document.createElement("div"); row.className = "src";
    row.innerHTML = `<span><i class="dot" style="background:${ok ? "var(--fresh)" : "var(--old)"}"></i>${name}</span>
      <small>${ok ? `cada ~${st.publish_period_s ?? "?"} s · hace ${last}` : (st.error || "error").slice(0, 60)}</small>`;
    el.appendChild(row);
  }
  $("k-sources").textContent = Object.keys(sourcesState).length ? `${active}/${Object.keys(sourcesState).length}` : "—";
}

function select(id) {
  if (selected && map.getSource("trains")) map.setFeatureState({ source: "trains", id: hashId(selected) }, { sel: false });
  selected = id;
  if (id) map.setFeatureState({ source: "trains", id: hashId(id) }, { sel: true });
  $("details").hidden = !id;
  if (id) renderDetails();
}
function renderDetails() {
  const tr = trains.get(selected); if (!tr) return;
  const p = tr.props, age = Math.round((now() - tr.observedMs) / 1000);
  $("d-id").textContent = p.label || p.external_id;
  const rows = [["Fuente", p.source], ["Tipo", "GPS reportado"], ["Observado", new Date(tr.observedMs).toLocaleTimeString("es-ES")],
    ["Antigüedad", `${age} s`], ["Viaje", p.trip_id], ["Línea", p.route_id],
    ["Velocidad", p.speed_mps != null ? `${Math.round(p.speed_mps * 3.6)} km/h` : null],
    ["Lat, Lon", `${tr.coords[1].toFixed(5)}, ${tr.coords[0].toFixed(5)}`]];
  $("d-body").innerHTML = rows.filter(([, v]) => v != null && v !== "").map(([k, v]) => `<dt>${k}</dt><dd>${esc(String(v))}</dd>`).join("");
}
const esc = (s) => s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

function connect() {
  const es = new EventSource(`${API}/api/v1/stream`);
  const conn = $("conn");
  es.addEventListener("hello", async (e) => {
    clockOffset = Date.parse(JSON.parse(e.data).server_time) - Date.now();
    conn.textContent = "En directo"; conn.className = "pill on";
    await snapshot();   // instantánea completa tras (re)conectar
    loadSources();
  });
  es.addEventListener("train.position", (e) => {
    const p = JSON.parse(e.data);
    upsert(p, [p.longitude, p.latitude]);
  });
  es.addEventListener("source.status", (e) => { const s = JSON.parse(e.data); renderSources({ [s.source]: s }); });
  es.onerror = () => { conn.textContent = "Reconectando…"; conn.className = "pill off"; };
}

$("f-age").addEventListener("input", (e) => { maxAgeFilter = +e.target.value; $("o-age").textContent = maxAgeFilter; render(); });
setInterval(render, 1000);    // recolorea por antigüedad y elimina caducados
setInterval(() => renderSources({}), 5000);
connect();
