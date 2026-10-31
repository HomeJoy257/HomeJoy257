#!/usr/bin/env python3
"""
RailRadar · Fase 1 — Auditoría de feeds GPS oficiales de Renfe.

Descubre las URLs reales vía CKAN (data.renfe.com), sondea los feeds durante
un periodo y mide si las posiciones cumplen la regla de 120 s usando el
timestamp INDIVIDUAL de cada vehículo (no el de descarga ni el de cabecera).

Solo librería estándar. Uso:
    python3 audit_feeds.py --hours 24 --interval 15
    python3 audit_feeds.py --minutes 10 --url cercanias=https://...json
Salida (./audit_out/):
    raw/<feed>/<ts>.json.gz   respuesta original (auditoría)
    samples.jsonl             métricas por sondeo
    report.md                 informe de viabilidad
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

CKAN = "https://data.renfe.com/api/3/action"
DATASETS = {
    "cercanias": "ubicacion-vehiculos",
    "larga_distancia": "posicion-vehiculos-av-ld-md",
}
MAX_AGE = 120
BBOX = (27.0, 45.0, -19.0, 5.0)  # lat_min, lat_max, lon_min, lon_max
UA = "RailRadar-audit/1.0"


# ---------------------------------------------------------------- HTTP / CKAN
def http_get(url: str, timeout: int = 30) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # TLS verificado por defecto
        h = dict(r.headers)
        h["_final_url"] = r.geturl()
        return r.status, r.read(), h


def _json_resources(pkg: dict) -> list[dict]:
    return [r for r in pkg.get("resources", [])
            if (r.get("format") or "").upper() == "JSON" and r.get("url")]


def discover_feeds() -> dict[str, dict]:
    """Busca en CKAN de Renfe. Si el id del dataset no existe, busca por texto
    y lo deja registrado para revisión (nunca inventa URLs)."""
    feeds = {}
    for name, ds in DATASETS.items():
        pkg = None
        try:
            payload = json.loads(http_get(f"{CKAN}/package_show?id={ds}")[1])
            if payload.get("success"):
                pkg = payload["result"]
        except Exception as e:  # noqa: BLE001
            print(f"[CKAN] package_show {ds} falló: {e}", file=sys.stderr)
        if pkg is None:
            q = urllib.parse.quote("ubicacion vehiculos" if name == "cercanias" else "posicion vehiculos")
            payload = json.loads(http_get(f"{CKAN}/package_search?q={q}&rows=20")[1])
            cands = [p for p in payload.get("result", {}).get("results", []) if _json_resources(p)]
            print(f"[CKAN] candidatos para {name}: {[p['name'] for p in cands]}", file=sys.stderr)
            pkg = cands[0] if cands else None
        if pkg is None:
            raise RuntimeError(f"No encuentro el dataset de {name} en CKAN")
        res = _json_resources(pkg)
        pref = [r for r in res if "vehicle" in r["url"].lower() or "posicion" in r["url"].lower()
                or "ubicacion" in r["url"].lower()] or res
        print(f"[CKAN] {name}: dataset={pkg.get('name')} recursos JSON="
              f"{[(r.get('name'), r['url']) for r in res]}", file=sys.stderr)
        if len(pref) != 1:
            raise RuntimeError(f"{pkg.get('name')}: {len(pref)} recursos JSON candidatos, revisar log")
        r = pref[0]
        feeds[name] = {"url": r["url"], "dataset": pkg.get("name"), "resource_id": r.get("id"),
                       "resource_name": r.get("name"), "last_modified": r.get("last_modified"),
                       "license": pkg.get("license_title"), "organization": (pkg.get("organization") or {}).get("title")}
    return feeds


# ---------------------------------------------------------------- Parsing
def g(d: dict, *keys):
    """Lee camelCase o snake_case indistintamente."""
    for k in keys:
        if isinstance(d, dict) and k in d:
            return d[k]
    return None


def to_dt(v) -> datetime | None:
    if v in (None, "", 0, "0"):
        return None
    try:
        return datetime.fromtimestamp(int(float(v)), tz=timezone.utc)  # epoch s
    except (TypeError, ValueError):
        pass
    try:
        dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
        return dt if dt.tzinfo else None  # sin zona = no fiable
    except ValueError:
        return None


def parse_gtfsrt_json(doc: dict) -> tuple[datetime | None, list[dict]]:
    header_ts = to_dt(g(g(doc, "header") or {}, "timestamp"))
    out = []
    for ent in g(doc, "entity") or []:
        v = g(ent, "vehicle")
        if not v:
            continue
        pos = g(v, "position") or {}
        veh = g(v, "vehicle") or {}
        trip = g(v, "trip") or {}
        out.append({
            "entity_id": g(ent, "id"),
            "vehicle_id": g(veh, "id"),
            "label": g(veh, "label"),
            "trip_id": g(trip, "tripId", "trip_id"),
            "lat": g(pos, "latitude"),
            "lon": g(pos, "longitude"),
            "ts": to_dt(g(v, "timestamp")),
            "status": g(v, "currentStatus", "current_status"),
            "direction_id": g(trip, "directionId", "direction_id"),
            "route_id": g(trip, "routeId", "route_id"),
            "bearing": g(pos, "bearing"),
            "speed": g(pos, "speed"),
            "stop_id": g(v, "stopId", "stop_id"),
        })
    return header_ts, out


def valid_coord(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    if lat == 0 and lon == 0:
        return False
    return BBOX[0] <= lat <= BBOX[1] and BBOX[2] <= lon <= BBOX[3]


# ---------------------------------------------------------------- Métricas
def analyze(header_ts, vehicles, now: datetime) -> dict:
    ages, fresh, future, no_ts, bad_coord = [], 0, 0, 0, 0
    for v in vehicles:
        if not valid_coord(v["lat"], v["lon"]):
            bad_coord += 1
            continue
        if v["ts"] is None:
            no_ts += 1
            continue
        age = (now - v["ts"]).total_seconds()
        if age < -5:  # tolerancia de reloj
            future += 1
            continue
        ages.append(age)
        if age <= MAX_AGE:
            fresh += 1
    return {
        "n": len(vehicles),
        "header_age_s": round((now - header_ts).total_seconds(), 1) if header_ts else None,
        "no_vehicle_ts": no_ts,
        "bad_coord": bad_coord,
        "future_ts": future,
        "fresh_le_120s": fresh,
        "age_p50": round(statistics.median(ages), 1) if ages else None,
        "age_p90": round(statistics.quantiles(ages, n=10)[-1], 1) if len(ages) >= 10 else None,
        "age_max": round(max(ages), 1) if ages else None,
        "ts_equals_header": sum(1 for v in vehicles if header_ts and v["ts"] == header_ts),
    }


class Tracker:
    """Acumula estado entre sondeos: ids, duplicados, cambios de identidad."""

    def __init__(self):
        self.ids = set()
        self.last = {}                     # vehicle_key -> (ts, lat, lon)
        self.repeats = 0                   # misma ts y coords que el sondeo anterior
        self.moved_same_ts = 0             # coords cambian con mismo ts (sospechoso)
        self.updates = defaultdict(list)   # key -> intervalos entre ts nuevos
        self.trip_by_vehicle = defaultdict(set)

    def feed(self, vehicles):
        for v in vehicles:
            key = v["vehicle_id"] or v["entity_id"]
            if key is None:
                continue
            self.ids.add(key)
            if v["trip_id"]:
                self.trip_by_vehicle[key].add(v["trip_id"])
            cur = (v["ts"], v["lat"], v["lon"])
            prev = self.last.get(key)
            if prev:
                if cur == prev:
                    self.repeats += 1
                elif cur[0] == prev[0]:
                    self.moved_same_ts += 1
                elif cur[0] and prev[0]:
                    self.updates[key].append((cur[0] - prev[0]).total_seconds())
            self.last[key] = cur

    def summary(self):
        gaps = [x for lst in self.updates.values() for x in lst]
        return {
            "distinct_vehicles": len(self.ids),
            "repeated_positions": self.repeats,
            "coords_changed_same_ts": self.moved_same_ts,
            "update_interval_p50": round(statistics.median(gaps), 1) if gaps else None,
            "update_interval_p90": round(statistics.quantiles(gaps, n=10)[-1], 1) if len(gaps) >= 10 else None,
            "vehicles_multi_trip": sum(1 for s in self.trip_by_vehicle.values() if len(s) > 1),
        }


# ---------------------------------------------------------------- Bucle
TRACK_COLS = ["feed", "vehicle_id", "entity_id", "label", "trip_id", "route_id", "direction_id",
              "ts", "lat", "lon", "bearing", "speed", "status", "stop_id", "polled_at", "raw_sha256"]


def poll(feeds, duration_s, interval_s, out: Path, trackers, errors, raw_every=1):
    import csv
    samples = out / "samples.jsonl"
    end = time.monotonic() + duration_s
    raw_hashes = defaultdict(set)
    seen = defaultdict(set)             # feed -> {(vehicle, ts)}: una fila por posición nueva
    new_bodies = defaultdict(int)
    tp = out / "tracks.csv.gz"
    fresh_file = not tp.exists()
    tracks_f = gzip.open(tp, "at", newline="")
    tw = csv.writer(tracks_f)
    if fresh_file:
        tw.writerow(TRACK_COLS)
    n_poll = 0
    try:
        _loop(locals())
    finally:
        tracks_f.close()


def _loop(L):
    feeds, end, interval_s, out = L["feeds"], L["end"], L["interval_s"], L["out"]
    trackers, errors, raw_every, samples = L["trackers"], L["errors"], L["raw_every"], L["samples"]
    raw_hashes, seen, new_bodies, tw, tracks_f = L["raw_hashes"], L["seen"], L["new_bodies"], L["tw"], L["tracks_f"]
    n_poll = 0
    while time.monotonic() < end:
        n_poll += 1
        t0 = time.monotonic()
        for name, meta in feeds.items():
            now = datetime.now(timezone.utc)
            rec = {"feed": name, "polled_at": now.isoformat()}
            try:
                status, body, headers = http_get(meta["url"])
                rec["http"] = status
                h = hashlib.sha256(body).hexdigest()
                rec["raw_sha256"] = h
                rec["bytes"] = len(body)
                rec["final_url"] = headers.get("_final_url")
                rec["server_date"] = headers.get("Date")
                rec["raw_unchanged"] = h in raw_hashes[name]
                raw_hashes[name].add(h)
                header_ts, vehicles = parse_gtfsrt_json(json.loads(body))
                if not rec["raw_unchanged"]:
                    new_bodies[name] += 1
                    if new_bodies[name] % raw_every == 1 or raw_every == 1:
                        d = out / "raw" / name
                        d.mkdir(parents=True, exist_ok=True)
                        (d / f"{now:%Y%m%dT%H%M%S}_{h[:12]}.json.gz").write_bytes(gzip.compress(body))
                    for v in vehicles:
                        k = (v["vehicle_id"] or v["entity_id"], v["ts"])
                        if v["ts"] is None or k in seen[name]:
                            continue
                        seen[name].add(k)
                        tw.writerow([name, v["vehicle_id"], v["entity_id"], v["label"], v["trip_id"],
                                     v["route_id"], v["direction_id"], v["ts"].isoformat(), v["lat"],
                                     v["lon"], v["bearing"], v["speed"], v["status"], v["stop_id"],
                                     now.isoformat(), h])
                    tracks_f.flush()
                rec.update(analyze(header_ts, vehicles, now))
                rec["header_ts"] = header_ts.isoformat() if header_ts else None
                rec["last_modified_hdr"] = headers.get("Last-Modified")
                trackers[name].feed(vehicles)
            except Exception as e:  # noqa: BLE001 — auditoría: registrar todo
                rec["error"] = f"{type(e).__name__}: {e}"
                errors[name].append(rec["polled_at"])
            with samples.open("a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
            if n_poll <= 3 or n_poll % 30 == 0 or "error" in rec:
                print(json.dumps(rec, default=str), flush=True)
        time.sleep(max(0, interval_s - (time.monotonic() - t0)))


def report(feeds, trackers, errors, out: Path):
    rows = defaultdict(list)
    for line in (out / "samples.jsonl").read_text().splitlines():
        r = json.loads(line)
        rows[r["feed"]].append(r)
    md = ["# RailRadar · Informe de viabilidad GPS\n",
          f"Generado: {datetime.now(timezone.utc).isoformat()}  ·  Límite: {MAX_AGE} s\n"]
    for name in feeds:
        ok = [r for r in rows[name] if "error" not in r]
        tot = sum(r["n"] for r in ok) or 1
        fresh = sum(r["fresh_le_120s"] for r in ok)
        no_ts = sum(r["no_vehicle_ts"] for r in ok)
        eq_hdr = sum(r["ts_equals_header"] for r in ok)
        p50s = [r["age_p50"] for r in ok if r["age_p50"] is not None]
        s = trackers[name].summary()
        md += [
            f"\n## {name}\n",
            f"- URL: `{feeds[name]['url']}`",
            f"- Sondeos OK / error: {len(ok)} / {len(errors[name])}",
            f"- Respuestas idénticas a una anterior: {sum(1 for r in ok if r.get('raw_unchanged'))}",
            f"- Vehículos distintos: {s['distinct_vehicles']}",
            f"- Media de vehículos por sondeo: {tot / max(len(ok), 1):.1f}",
            f"- **Visibles con ≤120 s: {fresh / tot:.1%}** (media {fresh / max(len(ok), 1):.1f} por sondeo)",
            f"- Sin timestamp individual: {no_ts / tot:.1%}",
            f"- Timestamp de vehículo == cabecera: {eq_hdr / tot:.1%}  ⚠ si es alto, el ts NO es de la coordenada",
            f"- Antigüedad mediana (mediana de sondeos): {statistics.median(p50s) if p50s else '—'} s",
            f"- Intervalo real entre posiciones nuevas p50/p90: {s['update_interval_p50']} / {s['update_interval_p90']} s",
            f"- Posiciones repetidas sin cambio: {s['repeated_positions']}",
            f"- Coordenadas cambian con mismo ts (sospechoso): {s['coords_changed_same_ts']}",
            f"- Vehículos con varios trip_id: {s['vehicles_multi_trip']}",
        ]
    (out / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=0)
    ap.add_argument("--minutes", type=float, default=0)
    ap.add_argument("--interval", type=int, default=15)
    ap.add_argument("--out", default="audit_out")
    ap.add_argument("--raw-every", type=int, default=1,
                    help="guardar 1 de cada N respuestas originales nuevas (todas quedan hasheadas)")
    ap.add_argument("--url", action="append", default=[],
                    help="feed=url para saltar CKAN (repetible)")
    a = ap.parse_args()
    duration = a.hours * 3600 + a.minutes * 60 or 600
    if a.url:
        feeds = {k: {"url": v} for k, v in (u.split("=", 1) for u in a.url)}
    else:
        feeds = discover_feeds()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "feeds.json").write_text(json.dumps(feeds, indent=2))
    print(f"Feeds: {json.dumps(feeds, indent=2)}", file=sys.stderr)
    trackers, errors = {k: Tracker() for k in feeds}, defaultdict(list)
    try:
        poll(feeds, duration, a.interval, out, trackers, errors, a.raw_every)
    except KeyboardInterrupt:
        print("Interrumpido; generando informe parcial…", file=sys.stderr)
    report(feeds, trackers, errors, out)


if __name__ == "__main__":
    main()
