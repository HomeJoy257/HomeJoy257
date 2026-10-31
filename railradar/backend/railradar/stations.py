"""Estaciones (GTFS estático oficial de Renfe) y eventos 'tren en estación'.

Fuente: datasets CKAN de Renfe (CC BY 4.0). El stop_id del GTFS coincide con
el stop_id que publican los feeds en tiempo real.
"""
import csv
import io
import logging
import time
import zipfile
from pathlib import Path

import os

import httpx

from .config import CKAN_URL

log = logging.getLogger("railradar.stations")

GTFS_DATASETS = {
    "renfe_ld": "horarios-de-alta-velocidad-larga-distancia-y-media-distancia",
    "renfe_cercanias": "horarios-cercanias",
}
CACHE = Path(__file__).resolve().parent.parent / ".cache"


async def _gtfs_url(c: httpx.AsyncClient, dataset: str) -> str:
    r = await c.get(f"{CKAN_URL}/package_show", params={"id": dataset})
    r.raise_for_status()
    res = [x for x in r.json()["result"]["resources"]
           if (x.get("format") or "").upper() in ("GTFS", "ZIP") and x.get("url")]
    if not res:
        raise RuntimeError(f"{dataset}: sin recurso GTFS")
    return res[0]["url"]


def _csv(z: zipfile.ZipFile, suffix: str):
    name = next((n for n in z.namelist() if n.endswith(suffix)), None)
    if not name:
        return []
    text = z.read(name).decode("utf-8-sig", "replace")
    # Renfe rellena cabeceras y valores con espacios: se normalizan
    return [{(k or "").strip(): (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(io.StringIO(text))]


def parse_products(zip_bytes: bytes) -> dict[str, str]:
    """trip_id -> producto (route_short_name) y nº de tren -> producto."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        routes = {r["route_id"]: r.get("route_short_name", "").upper() for r in _csv(z, "routes.txt")}
        out = {}
        for t in _csv(z, "trips.txt"):
            prod = routes.get(t.get("route_id"))
            if not prod:
                continue
            out[t["trip_id"]] = prod
            if t.get("trip_short_name"):
                out.setdefault(f"#{t['trip_short_name']}", prod)
    return out


def product_for(products: dict, trip_id: str | None, train: str | None) -> str | None:
    if trip_id and trip_id in products:
        return products[trip_id]
    for num in (train, (trip_id or "")[:5]):
        if num and f"#{num}" in products:
            return products[f"#{num}"]
    return None


def parse_stops(zip_bytes: bytes) -> dict[str, dict]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
        rows = _csv(z, "stops.txt")
    out = {}
    for row in rows:
        try:
            out[row["stop_id"]] = {"name": row.get("stop_name") or row["stop_id"],
                                   "lat": float(row["stop_lat"]), "lon": float(row["stop_lon"])}
        except (KeyError, ValueError):
            continue
    return out


async def load_gtfs(client: httpx.AsyncClient, max_age_s: int = 86400,
                    sources=("renfe_ld",)) -> tuple[dict[str, dict], dict[str, str]]:
    """(estaciones stop_id -> {name, lat, lon}, productos trip_id -> AVE/ALVIA/...).
    Cachea en disco 24 h (el GTFS de Renfe cambia con frecuencia)."""
    CACHE.mkdir(exist_ok=True)
    stations: dict[str, dict] = {}
    products: dict[str, str] = {}
    override = [u for u in os.getenv("STATIONS_GTFS_URLS", "").split(",") if u]
    for u in override:                      # desarrollo / pruebas
        r = await client.get(u)
        stations.update(parse_stops(r.content))
        products.update(parse_products(r.content))
    if override:
        return stations, products
    for src, ds in GTFS_DATASETS.items():
        if src not in sources:
            continue
        f = CACHE / f"{src}_gtfs.zip"
        try:
            if not f.exists() or time.time() - f.stat().st_mtime > max_age_s:
                url = await _gtfs_url(client, ds)
                r = await client.get(url, timeout=120)
                r.raise_for_status()
                f.write_bytes(r.content)
            data = f.read_bytes()
            stops = parse_stops(data)
            stations.update(stops)
            prods = parse_products(data)
            products.update(prods)
            log.info("GTFS %s: %d estaciones, %d viajes", src, len(stops), len(prods))
        except Exception as e:  # noqa: BLE001
            log.warning("no pude cargar GTFS %s: %s", src, e)
    return stations, products


def parse_trip_updates(doc: dict) -> dict[str, dict]:
    """trip_id -> {delay_s, stops: {stop_id: delay_s}} (GTFS-RT TripUpdates, JSON)."""
    def g(d, *ks):
        for k in ks:
            if isinstance(d, dict) and d.get(k) not in (None, ""):
                return d[k]
        return None
    out = {}
    for ent in g(doc, "entity") or []:
        tu = g(ent, "tripUpdate", "trip_update")
        if not tu:
            continue
        trip_id = g(g(tu, "trip") or {}, "tripId", "trip_id")
        if not trip_id:
            continue
        stops = {}
        for stu in g(tu, "stopTimeUpdate", "stop_time_update") or []:
            ev = g(stu, "arrival") or g(stu, "departure") or {}
            d = g(ev, "delay")
            if g(stu, "stopId", "stop_id") and d is not None:
                stops[str(g(stu, "stopId", "stop_id"))] = int(d)
        delay = g(tu, "delay")
        if delay is None and stops:
            delay = next(iter(stops.values()))
        out[str(trip_id)] = {"delay_s": int(delay) if delay is not None else None, "stops": stops}
    return out
