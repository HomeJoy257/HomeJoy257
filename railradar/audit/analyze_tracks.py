#!/usr/bin/env python3
"""
RailRadar · Análisis de 24 h: procedencia, realismo de la posición, sentido y vía.

Entrada:  uno o varios directorios generados por audit_feeds.py
          (samples.jsonl, tracks.csv.gz, raw/)
Opcional: --rails rails.geojson  (vías de OpenStreetMap, railway=rail)

    python3 analyze_tracks.py runs/part1 runs/part2 ... --rails rails.geojson --out analysis

Requiere: numpy, shapely>=2, pyproj
Salida: analysis/report.md + analysis/summary.json + analysis/provenance_manifest.csv

NOTA: este análisis es estadístico y para producto informativo. No es, ni puede
sustituir, un sistema de seguridad ferroviaria.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import numpy as np

R_EARTH = 6_371_000.0
OFFICIAL_HOSTS = ("renfe.com",)      # dominio(s) que aceptamos como fuente oficial


# ------------------------------------------------------------------ utilidades
def hav(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * R_EARTH * np.arcsin(np.sqrt(a))


def heading(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    y = np.sin(dl) * np.cos(p2)
    x = np.cos(p1) * np.sin(p2) - np.sin(p1) * np.cos(p2) * np.cos(dl)
    return (np.degrees(np.arctan2(y, x)) + 360) % 360


def angdiff(a, b):
    d = np.abs((np.asarray(a) - np.asarray(b) + 180) % 360 - 180)
    return d


def pct(x, q):
    x = np.asarray([v for v in x if v is not None and not (isinstance(v, float) and math.isnan(v))])
    return round(float(np.percentile(x, q)), 1) if len(x) else None


def share(n, d):
    return f"{(100 * n / d):.1f} %" if d else "—"


def decimals(s: str) -> int:
    s = s.strip()
    return len(s.split(".")[1].rstrip("0")) if "." in s else 0


# ------------------------------------------------------------------ carga
def load(dirs):
    rows, samples = [], []
    for d in map(Path, dirs):
        tp = d / "tracks.csv.gz"
        if tp.exists():
            with gzip.open(tp, "rt", newline="") as f:
                try:
                    for r in csv.DictReader(f):
                        rows.append(r)
                except EOFError:
                    pass  # fichero cortado: usamos lo leído
        sp = d / "samples.jsonl"
        if sp.exists():
            for line in sp.read_text().splitlines():
                try:
                    r = json.loads(line)
                    r["_dir"] = str(d)
                    samples.append(r)
                except json.JSONDecodeError:
                    pass
    return rows, samples


# ------------------------------------------------------------------ 1. procedencia
def provenance(dirs, samples, out: Path):
    hosts = Counter(urlparse(s.get("final_url") or "").hostname for s in samples if "error" not in s)
    http = Counter(s.get("http") for s in samples if "error" not in s)
    errors = sum(1 for s in samples if "error" in s)
    # Comprobar que cada respuesta guardada coincide con su hash registrado
    manifest, verified, mismatch = [], 0, 0
    known = {s.get("raw_sha256") for s in samples if s.get("raw_sha256")}
    for d in map(Path, dirs):
        for f in sorted((d / "raw").rglob("*.json.gz")):
            body = gzip.decompress(f.read_bytes())
            h = hashlib.sha256(body).hexdigest()
            ok = h in known and h[:12] in f.name
            verified += ok
            mismatch += not ok
            manifest.append([str(f), h, len(body), ok])
    with (out / "provenance_manifest.csv").open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["file", "sha256", "bytes", "hash_matches_log"])
        w.writerows(manifest)
    unofficial = {h: n for h, n in hosts.items() if not (h or "").endswith(OFFICIAL_HOSTS)}
    return {
        "polls_ok": sum(http.values()), "polls_error": errors, "http_codes": dict(http),
        "hosts": dict(hosts), "unofficial_hosts": unofficial,
        "raw_files_verified": verified, "raw_files_mismatch": mismatch,
        "first_poll": min((s["polled_at"] for s in samples), default=None),
        "last_poll": max((s["polled_at"] for s in samples), default=None),
        "ts_equals_header_ratio": round(
            sum(s.get("ts_equals_header", 0) for s in samples) / max(1, sum(s.get("n", 0) for s in samples)), 4),
    }


# ------------------------------------------------------------------ 2-5. trayectorias
def build_tracks(rows):
    """feed -> vehicle -> arrays ordenados por ts (sin duplicados)."""
    by = defaultdict(lambda: defaultdict(list))
    dec = Counter()
    for r in rows:
        try:
            lat, lon = float(r["lat"]), float(r["lon"])
            ts = datetime.fromisoformat(r["ts"]).timestamp()
            polled = datetime.fromisoformat(r["polled_at"]).timestamp()
        except (ValueError, TypeError, KeyError):
            continue
        if not (27 <= lat <= 45 and -19 <= lon <= 5):
            continue
        dec[min(decimals(r["lat"]), decimals(r["lon"]))] += 1
        b = float(r["bearing"]) if r.get("bearing") not in (None, "") else np.nan
        sp = float(r["speed"]) if r.get("speed") not in (None, "") else np.nan
        key = r.get("vehicle_id") or r.get("entity_id")
        by[r["feed"]][key].append((ts, lat, lon, b, sp, polled, r.get("trip_id") or "", r.get("direction_id") or ""))
    out = {}
    for feed, vs in by.items():
        out[feed] = {}
        for k, pts in vs.items():
            pts = sorted(set(pts), key=lambda p: p[0])
            out[feed][k] = np.array([p[:6] for p in pts], dtype=float), [p[6:] for p in pts]
    return out, dec


def estimate_noise(arr, max_spread=60.0, min_pts=4, min_dur=60.0):
    """σ del GPS en parado: grupos de puntos consecutivos que no se mueven."""
    sig = []
    i = 0
    n = len(arr)
    while i < n:
        j = i + 1
        while j < n and j - i < 60:
            seg = arr[i:j + 1]
            c_lat, c_lon = seg[:, 1].mean(), seg[:, 2].mean()
            if hav(seg[:, 1], seg[:, 2], c_lat, c_lon).max() > max_spread:
                break
            j += 1
        seg = arr[i:j]
        if len(seg) >= min_pts and seg[-1, 0] - seg[0, 0] >= min_dur:
            c_lat, c_lon = seg[:, 1].mean(), seg[:, 2].mean()
            d = hav(seg[:, 1], seg[:, 2], c_lat, c_lon)
            if d.max() > 0:                   # si todo es idéntico es "congelado", no ruido
                sig.append(float(np.sqrt((d ** 2).mean())))
        i = max(j, i + 1)
    return sig


def analyze_feed(vehicles, rails=None, max_speed_kmh=360.0):
    lat_age, dts, speeds, implausible, nonmono = [], [], [], 0, 0
    noise, frozen = [], 0
    pairs, dir_ok, bearing_diff, reversals = 0, 0, [], 0
    reported_bearing, reported_speed, with_dir_id = 0, 0, 0
    travel_since_obs = []
    track_stats = Counter()
    track_gap, track_margin = [], []
    total_pts = 0
    for vid, (arr, meta) in vehicles.items():
        n = len(arr)
        total_pts += n
        if n == 0:
            continue
        lat_age += list(arr[:, 5] - arr[:, 0])
        reported_bearing += int(np.isfinite(arr[:, 3]).sum())
        reported_speed += int(np.isfinite(arr[:, 4]).sum())
        with_dir_id += sum(1 for m in meta if m[1] != "")
        noise += estimate_noise(arr)
        if n >= 2:
            dt = np.diff(arr[:, 0])
            d = hav(arr[:-1, 1], arr[:-1, 2], arr[1:, 1], arr[1:, 2])
            nonmono += int((dt <= 0).sum())
            ok = dt > 0
            v = np.where(ok, d / np.where(ok, dt, 1), np.nan) * 3.6
            dts += list(dt[ok])
            speeds += list(v[ok & (d > 0)])
            implausible += int((v[ok] > max_speed_kmh).sum())
            frozen += int(((d == 0) & (dt > 0)).sum())
            # distancia que pudo recorrer el tren desde la observación (seguridad)
            age = arr[1:, 5] - arr[1:, 0]
            travel_since_obs += list((v[ok] / 3.6) * age[ok])
            hd = heading(arr[:-1, 1], arr[:-1, 2], arr[1:, 1], arr[1:, 2])
            pairs += len(d)
            # sentido determinable: desplazamiento claramente mayor que el ruido
            movable = (d > 40) & ok & (v < max_speed_kmh)
            dir_ok += int(movable.sum())
            rb = arr[1:, 3]
            m = movable & np.isfinite(rb)
            bearing_diff += list(angdiff(hd[m], rb[m]))
            # cambios de sentido (>150°) entre tramos consecutivos con movimiento claro
            idx = np.where(movable)[0]
            if len(idx) >= 2:
                h = hd[idx]
                reversals += int((angdiff(h[:-1], h[1:]) > 150).sum())
        if rails is not None:
            for st, gap, margin in rails.classify(arr[:, 1], arr[:, 2]):
                track_stats[st] += 1
                if gap is not None:
                    track_gap.append(gap)
                    track_margin.append(margin)
    sigma = pct(noise, 50)
    res = {
        "vehicles": len(vehicles), "points": total_pts,
        "age_at_first_seen_s": {"p50": pct(lat_age, 50), "p90": pct(lat_age, 90), "p99": pct(lat_age, 99)},
        "share_age_le_120s": share(sum(1 for a in lat_age if 0 <= a <= 120), len(lat_age)),
        "update_interval_s": {"p50": pct(dts, 50), "p90": pct(dts, 90)},
        "implied_speed_kmh": {"p50": pct(speeds, 50), "p90": pct(speeds, 90), "p99": pct(speeds, 99)},
        "implausible_jumps": implausible, "non_monotonic_ts": nonmono,
        "frozen_repeats": frozen,
        "gps_noise_rms_2d_m": {"p50": sigma, "p90": pct(noise, 90), "clusters": len(noise)},
        "direction_determinable": share(dir_ok, pairs),
        "reported_bearing": share(reported_bearing, total_pts),
        "reported_speed": share(reported_speed, total_pts),
        "direction_id_present": share(with_dir_id, total_pts),
        "bearing_vs_computed_deg": {"p50": pct(bearing_diff, 50), "p90": pct(bearing_diff, 90), "n": len(bearing_diff)},
        "direction_reversals": reversals,
        "travel_since_observation_m": {"p50": pct(travel_since_obs, 50), "p90": pct(travel_since_obs, 90),
                                       "p99": pct(travel_since_obs, 99)},
    }
    if rails is not None:
        t = sum(track_stats.values())
        res["track"] = {
            "points": t,
            "within_10m_of_rail": share(track_stats["single_10"] + track_stats["multi_10"], t),
            "within_25m_of_rail": share(t - track_stats["far"] - track_stats["near_50"], t),
            "far_gt_50m": share(track_stats["far"], t),
            "multi_track_zone": share(track_stats["multi_10"] + track_stats["multi_25"], t),
            # en doble vía: la más cercana gana por más de 2σ -> vía identificable con ~95 %
            "track_identifiable_in_multi": share(sum(1 for m in track_margin if sigma and m > 2 * sigma),
                                                 len(track_margin)) if sigma else "sin σ",
            "parallel_track_separation_m": {"p50": pct(track_gap, 50), "p10": pct(track_gap, 10)},
        }
        if sigma:
            res["track"]["note"] = (f"σ GPS ≈ {sigma} m. Separación típica entre vías ≈ "
                                    f"{pct(track_gap, 50)} m. Si σ ≥ separación/2, la vía NO es identificable.")
    return res


# ------------------------------------------------------------------ vías OSM
class Rails:
    """Índice espacial de vías (OSM railway=rail) en UTM 30N (EPSG:25830)."""

    def __init__(self, geojson: Path):
        from pyproj import Transformer
        from shapely import STRtree
        from shapely.geometry import shape
        from shapely.ops import transform
        self.tf = Transformer.from_crs(4326, 25830, always_xy=True)
        geoms = []
        for f in json.loads(geojson.read_text())["features"]:
            g = f.get("geometry") or {}
            if g.get("type") not in ("LineString", "MultiLineString"):
                continue
            if (f.get("properties") or {}).get("railway", "rail") != "rail":
                continue
            geoms.append(transform(self.tf.transform, shape(g)))
        self.geoms = geoms
        self.tree = STRtree(geoms)

    def classify(self, lats, lons):
        from shapely.geometry import Point
        from shapely.ops import nearest_points
        xs, ys = self.tf.transform(np.asarray(lons), np.asarray(lats))
        for x, y, lat in zip(xs, ys, lats):
            if lat < 34:              # Canarias: fuera de UTM30, se omite
                continue
            p = Point(x, y)
            idx = self.tree.query(p.buffer(50))
            if len(idx) == 0:
                yield "far", None, None
                continue
            cands = sorted(((self.geoms[i].distance(p), i) for i in idx))
            d1, i1 = cands[0]
            n1 = nearest_points(self.geoms[i1], p)[0]
            # segunda vía PARALELA: su punto más cercano está a >2,5 m del de la primera
            second, gap = None, None
            for d, i in cands[1:]:
                n2 = nearest_points(self.geoms[i], p)[0]
                sep = n1.distance(n2)
                if sep > 2.5:
                    second, gap = d, sep
                    break
            band = "10" if d1 <= 10 else "25" if d1 <= 25 else "50"
            if band == "50":
                yield "near_50", None, None
            elif second is not None and second <= 25:
                yield f"multi_{band}", gap, second - d1
            else:
                yield f"single_{band}", None, None


# ------------------------------------------------------------------ informe
def verdict(r):
    out = []
    s = (r.get("gps_noise_rms_2d_m") or {}).get("p50")
    gap = ((r.get("track") or {}).get("parallel_track_separation_m") or {}).get("p50")
    if s is not None and gap:
        out.append("**Vía:** " + ("identificable en general" if s < gap / 4 else
                                  "NO identificable de forma fiable en tramos de doble vía" if s >= gap / 2 else
                                  "dudosa; solo con alta confianza en parte de los puntos"))
    elif s is not None:
        out.append(f"**Vía:** sin capa de vías OSM; con σ≈{s} m y entrevía típica ~4–4,7 m en España, "
                   f"{'no' if s >= 2.3 else 'quizá'} distinguible")
    out.append(f"**Sentido:** determinable en {r['direction_determinable']} de los pares de puntos")
    t = r["travel_since_observation_m"]
    out.append(f"**Realismo:** al recibirse, el tren puede haber avanzado p50 {t['p50']} m / p90 {t['p90']} m "
               f"desde la coordenada publicada")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    ap.add_argument("--rails")
    ap.add_argument("--out", default="analysis")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rows, samples = load(a.dirs)
    prov = provenance(a.dirs, samples, out)
    tracks, dec = build_tracks(rows)
    rails = Rails(Path(a.rails)) if a.rails else None
    summary = {"provenance": prov, "coordinate_decimals": dict(dec), "feeds": {}}
    for feed, vs in tracks.items():
        summary["feeds"][feed] = analyze_feed(vs, rails)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False))

    md = ["# RailRadar · Análisis de datos reales\n",
          "> Análisis estadístico para un producto **informativo**. Nada de esto valida su uso para "
          "seguridad ferroviaria ni para evitar accidentes.\n",
          "## 1. Procedencia (¿son datos reales y oficiales?)\n",
          f"- Periodo: {prov['first_poll']} → {prov['last_poll']}",
          f"- Sondeos OK / error: {prov['polls_ok']} / {prov['polls_error']}  ·  HTTP: {prov['http_codes']}",
          f"- Hosts servidores: {prov['hosts']}",
          f"- Hosts NO oficiales: {prov['unofficial_hosts'] or 'ninguno'}",
          f"- Respuestas originales guardadas y verificadas por SHA-256: {prov['raw_files_verified']} "
          f"(discrepancias: {prov['raw_files_mismatch']}) → ver `provenance_manifest.csv`",
          f"- Ratio ts vehículo == ts cabecera: {prov['ts_equals_header_ratio']:.1%}",
          f"- Decimales de las coordenadas (resolución): {dict(sorted(dec.items()))}  "
          f"(4 dec ≈ 11 m, 5 ≈ 1,1 m, 6 ≈ 0,11 m)\n"]
    for feed, r in summary["feeds"].items():
        md += [f"## {feed}\n", *[f"- {v}" for v in verdict(r)], "",
               "| Métrica | Valor |", "|---|---|"]
        for k, v in r.items():
            md.append(f"| {k} | {json.dumps(v, ensure_ascii=False) if isinstance(v, dict) else v} |")
        md.append("")
    (out / "report.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
