#!/usr/bin/env python3
"""
RailRadar · Análisis de 24 h SOLO ALTA VELOCIDAD (feed AV/LD/MD de Renfe).

    python3 av_analysis.py RUN_DIR --products products.csv [--rails rails.geojson] --out av_analysis

products.csv: trip_id,train_number,product  (del GTFS oficial de Renfe)
Mide: procedencia, refresco real de coordenadas, congelaciones, saltos imposibles,
distancia a la vía (OSM), identificabilidad de vía, sentido (incl. paridad del nº
de tren) y cuánto avanza el tren entre publicaciones.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from analyze_tracks import Rails, angdiff, hav, heading, pct, share  # noqa: E402

AV = {"AVE", "AVLO", "AVE INT", "EUROMED", "AVANT", "AVANT EXP", "ALVIA"}
LD_FEED = "larga_distancia"


def load_products(path):
    by_trip, by_num = {}, {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            by_trip[r["trip_id"]] = r["product"]
            if r["train_number"]:
                by_num.setdefault(r["train_number"], r["product"])
    return by_trip, by_num


def product(by_trip, by_num, trip_id, label, vid):
    if trip_id in by_trip:
        return by_trip[trip_id]
    for n in (label, vid, (trip_id or "")[:5]):
        if n and n in by_num:
            return by_num[n]
    return None


def load(run_dir, by_trip, by_num):
    rows, samples, prod_count, skipped = [], [], Counter(), Counter()
    for part in sorted(Path(run_dir).glob("part-*")):
        sp = part / "samples.jsonl.gz"
        if sp.exists():
            for line in gzip.open(sp, "rt"):
                r = json.loads(line)
                if r.get("feed") == LD_FEED:
                    samples.append(r)
        tp = part / "tracks.csv.gz"
        if not tp.exists():
            continue
        with gzip.open(tp, "rt", newline="") as f:
            try:
                for r in csv.DictReader(f):
                    if r["feed"] != LD_FEED or not r["lat"] or not r["lon"]:
                        continue
                    p = product(by_trip, by_num, r["trip_id"], r["label"], r["vehicle_id"])
                    if p not in AV:
                        skipped[p or "desconocido"] += 1
                        continue
                    r["product"] = p
                    prod_count[p] += 1
                    rows.append(r)
            except EOFError:
                pass
    return rows, samples, prod_count, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("run_dir")
    ap.add_argument("--products", required=True)
    ap.add_argument("--rails")
    ap.add_argument("--out", default="av_analysis")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    by_trip, by_num = load_products(a.products)
    rows, samples, prod_count, skipped = load(a.run_dir, by_trip, by_num)

    # ---------------- procedencia
    ok = [s for s in samples if "error" not in s]
    hosts = Counter((s.get("final_url") or "").split("/")[2] for s in ok if s.get("final_url"))
    hdr_lag = [(datetime.fromisoformat(s["polled_at"]) - datetime.fromisoformat(s["header_ts"])).total_seconds()
               for s in ok if s.get("header_ts")]
    prov = {"polls_ok": len(ok), "polls_error": len(samples) - len(ok), "hosts": dict(hosts),
            "header_minus_poll_s_p50": pct(hdr_lag, 50),
            "vehicle_ts_present": sum(1 for r in rows if r.get("ts"))}

    # ---------------- trayectorias por tren (filas = coordenada nueva vista en un sondeo)
    by = defaultdict(list)
    for r in rows:
        key = (r["vehicle_id"] or r["entity_id"], r["trip_id"])
        by[key].append((datetime.fromisoformat(r["polled_at"]).timestamp(), float(r["lat"]), float(r["lon"]),
                        r.get("status") or "", r["product"], r["label"] or r["vehicle_id"] or ""))
    refresh, refresh_moving, jumps, pairs_ok, speeds = [], [], 0, 0, []
    advance_between = []
    heads_by_cell = defaultdict(lambda: {"odd": [], "even": []})
    all_lat, all_lon, moving_mask = [], [], []
    per_hour = defaultdict(set)
    for key, pts in by.items():
        pts.sort()
        arr = np.array([p[:3] for p in pts])
        for t, *_ in pts:
            per_hour[datetime.fromtimestamp(t, timezone.utc).strftime("%H")].add(key)
        all_lat += list(arr[:, 1])
        all_lon += list(arr[:, 2])
        if len(arr) < 2:
            moving_mask += [False]
            continue
        dt = np.diff(arr[:, 0])
        d = hav(arr[:-1, 1], arr[:-1, 2], arr[1:, 1], arr[1:, 2])
        st = [p[3] for p in pts[1:]]
        refresh += list(dt)
        mv = np.array([s == "IN_TRANSIT_TO" for s in st])
        refresh_moving += list(dt[mv])
        good = dt >= 15                       # dt medido por sondeo (±10 s): evitar ruido
        v = np.where(good, d / np.maximum(dt, 1) * 3.6, np.nan)
        speeds += list(v[good & (d > 0)])
        pairs_ok += int(good.sum())
        jumps += int((v[good] > 350).sum())
        advance_between += list(d[mv & (d > 0)])
        hd = heading(arr[:-1, 1], arr[:-1, 2], arr[1:, 1], arr[1:, 2])
        num = "".join(ch for ch in pts[0][5] if ch.isdigit())
        par = "even" if num and int(num) % 2 == 0 else "odd"
        for i in np.where((d > 300) & good & (v < 350))[0]:
            cell = (round(arr[i, 1] * 4) / 4, round(arr[i, 2] * 4) / 4)   # celdas de ~25 km
            heads_by_cell[cell][par].append(hd[i])
        moving_mask += [True] * len(arr)

    # ---------------- sentido: ¿pares e impares van en sentidos opuestos?
    def circ_mean(h):
        r = np.radians(h)
        return (math.degrees(math.atan2(np.sin(r).mean(), np.cos(r).mean())) + 360) % 360

    cells_tested, cells_opposite, pts_pred, pts_ok = 0, 0, 0, 0
    for cell, hh in heads_by_cell.items():
        if len(hh["odd"]) >= 5 and len(hh["even"]) >= 5:
            # solo celdas con un corredor dominante (rumbos concentrados)
            mo, me = circ_mean(hh["odd"]), circ_mean(hh["even"])
            cells_tested += 1
            if angdiff(mo, me) > 135:
                cells_opposite += 1
            for h in hh["odd"]:
                pts_pred += 1
                pts_ok += angdiff(h, mo) < 90
            for h in hh["even"]:
                pts_pred += 1
                pts_ok += angdiff(h, (mo + 180) % 360) < 90

    # ---------------- vía (OSM)
    track = None
    if a.rails:
        rails = Rails(Path(a.rails))
        from shapely.geometry import Point
        dists, margins, states = [], [], Counter()
        lat_s, lon_s = np.array(all_lat), np.array(all_lon)
        idx = np.arange(len(lat_s))
        if len(idx) > 60000:                       # muestra para acotar tiempo
            idx = np.random.default_rng(0).choice(idx, 60000, replace=False)
        xs, ys = rails.tf.transform(lon_s[idx], lat_s[idx])
        for x, y, la in zip(xs, ys, lat_s[idx]):
            if la < 34:
                continue
            p = Point(x, y)
            cand = rails.tree.query(p.buffer(60))
            if len(cand) == 0:
                states["far"] += 1
                continue
            ds = sorted((rails.geoms[i].distance(p), i) for i in cand)
            dists.append(ds[0][0])
            from shapely.ops import nearest_points
            n1 = nearest_points(rails.geoms[ds[0][1]], p)[0]
            second = next((d for d, i in ds[1:] if nearest_points(rails.geoms[i], p)[0].distance(n1) > 2.5), None)
            if second is not None and second <= 25:
                states["multi"] += 1
                margins.append(second - ds[0][0])
            else:
                states["single"] += 1
        dists = np.array(dists)
        n = len(dists) or 1
        track = {
            "points": int(sum(states.values())),
            "dist_to_rail_m": {"p50": pct(dists, 50), "p90": pct(dists, 90), "p99": pct(dists, 99)},
            "share_lt_1m": share(int((dists < 1).sum()), n), "share_lt_3m": share(int((dists < 3).sum()), n),
            "share_lt_10m": share(int((dists < 10).sum()), n), "far_gt_60m": share(states["far"], sum(states.values())),
            "multi_track_share": share(states["multi"], sum(states.values())),
            "multi_margin_m": {"p50": pct(margins, 50), "p90": pct(margins, 90)},
            "multi_margin_gt_3m": share(sum(1 for m in margins if m > 3), len(margins)),
        }

    res = {
        "products": dict(prod_count), "excluded_rows": dict(skipped.most_common(12)),
        "trains_distinct": len({k[0] for k in by}), "trips_distinct": len(by),
        "trains_by_hour_utc": {h: len(v) for h, v in sorted(per_hour.items())},
        "provenance": prov,
        "coord_refresh_s": {"p50": pct(refresh, 50), "p90": pct(refresh, 90), "p99": pct(refresh, 99)},
        "coord_refresh_moving_s": {"p50": pct(refresh_moving, 50), "p90": pct(refresh_moving, 90),
                                   "p99": pct(refresh_moving, 99)},
        "gaps_moving_gt_60s": share(sum(1 for x in refresh_moving if x > 60), len(refresh_moving)),
        "gaps_moving_gt_120s": share(sum(1 for x in refresh_moving if x > 120), len(refresh_moving)),
        "implied_speed_kmh": {"p50": pct(speeds, 50), "p90": pct(speeds, 90), "p99": pct(speeds, 99),
                              "max_plausible_share_le_350": share(pairs_ok - jumps, pairs_ok)},
        "impossible_jumps_gt_350kmh": jumps,
        "advance_between_updates_m": {"p50": pct(advance_between, 50), "p90": pct(advance_between, 90),
                                      "p99": pct(advance_between, 99)},
        "direction": {"cells_tested": cells_tested, "cells_odd_even_opposite": cells_opposite,
                      "parity_predicts_heading": share(pts_ok, pts_pred)},
        "track": track,
    }
    (out / "av_summary.json").write_text(json.dumps(res, indent=2, ensure_ascii=False))
    print(json.dumps(res, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
