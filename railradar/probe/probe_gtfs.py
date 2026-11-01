#!/usr/bin/env python3
"""Inspecciona el GTFS AV/LD/MD de Renfe y lo cruza con el feed en tiempo real
para saber cómo identificar trenes de ALTA VELOCIDAD."""
import csv, io, json, sys, urllib.request, zipfile, collections
from pathlib import Path
OUT = Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
def get(u):
    with urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "RailRadar probe"}), timeout=120) as r:
        return r.read()
z = zipfile.ZipFile(io.BytesIO(get("https://ssl.renfe.com/gtransit/Fichero_AV_LD/google_transit.zip")))
rep = {"files": z.namelist()}
def rows(name, n=None):
    t = z.read(name).decode("utf-8-sig", "replace")
    r = list(csv.DictReader(io.StringIO(t)))
    return r if n is None else r[:n]
for f in z.namelist():
    rep[f + "_head"] = rows(f, 5)
routes = rows("routes.txt"); trips = rows("trips.txt")
rep["route_short_names"] = collections.Counter(r.get("route_short_name", "").strip() for r in routes).most_common(60)
rep["route_long_sample"] = [(r.get("route_id"), r.get("route_short_name"), r.get("route_long_name"), r.get("route_desc"), r.get("route_type")) for r in routes[:40]]
rep["agencies"] = rows("agency.txt")
rt = {r["route_id"]: r for r in routes}
# cruce con tiempo real
vp = json.loads(get("https://gtfsrt.renfe.com/vehicle_positions_LD.json"))
tu = json.loads(get("https://gtfsrt.renfe.com/trip_updates_LD.json"))
trip_ids = {t["trip_id"]: t for t in trips}
match, sample = collections.Counter(), []
for e in vp.get("entity", []):
    v = e.get("vehicle", {}); tid = (v.get("trip") or {}).get("tripId") or (v.get("trip") or {}).get("trip_id")
    lab = (v.get("vehicle") or {}).get("label")
    t = trip_ids.get(tid)
    match["exact_trip_id"] += bool(t)
    # intentar por número de tren (prefijo de 5 dígitos)
    num = (tid or "")[:5]
    cands = [x for x in trips if x["trip_id"].startswith(num) or x.get("trip_short_name") == num][:3]
    match["by_number_prefix"] += bool(cands)
    if len(sample) < 25:
        r = rt.get((t or (cands[0] if cands else {})).get("route_id"), {})
        sample.append({"rt_trip_id": tid, "label": lab, "gtfs_trip": (t or (cands[0] if cands else None)),
                       "route_short_name": r.get("route_short_name"), "route_long_name": r.get("route_long_name")})
rep["rt_vs_gtfs"] = dict(match); rep["rt_entities"] = len(vp.get("entity", [])); rep["sample"] = sample
rep["rt_vp_example"] = vp.get("entity", [])[:2]; rep["rt_tu_example"] = tu.get("entity", [])[:2]
# índice completo nº de tren / trip_id -> producto (para filtrar análisis a alta velocidad)
with open(OUT / "products.csv", "w", newline="") as fh:
    w = csv.writer(fh); w.writerow(["trip_id", "train_number", "product"])
    for t in trips:
        w.writerow([t["trip_id"], (t.get("trip_short_name") or "").strip(),
                    rt.get(t["route_id"], {}).get("route_short_name", "").strip().upper()])
(OUT / "gtfs_probe.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
print(json.dumps({k: rep[k] for k in ("files", "route_short_names", "rt_vs_gtfs", "rt_entities")}, ensure_ascii=False, indent=1))
