"""Recolector: sondeo adaptativo -> validación -> Redis/SSE.

Una sola instancia en producción (no escalar con la API).
"""
import asyncio
import logging
import time
from collections import Counter
from datetime import datetime, timezone

import httpx

from .ckan import resolve_feed
from .config import (CKAN_REFRESH_S, FEED_POLICY, FEEDS, REDIS_URL, STATION_EVENT_TTL_S,
                     STATIONS_ENABLED, TRIP_UPDATE_FEEDS)
from .model import age_seconds, classify
from .parser import parse_vehicle_positions
from .stations import load_stations, parse_trip_updates
from .store import DELAYS_KEY, EVENTS_KEY, STATIONS_KEY, make_store, utcnow_iso

log = logging.getLogger("railradar.collector")


class FeedWorker:
    """Aprende cada cuánto publica el feed y sondea justo después."""

    def __init__(self, name: str, ref: str, store, client: httpx.AsyncClient,
                 base_period: float = 15.0):
        self.name, self.ref, self.store, self.c = name, ref, store, client
        self.period = base_period
        self.url = None
        self.etag = self.lastmod = None
        self.last_change = None
        self.last_body_hash = None
        self.resolved_at = 0.0
        self.consecutive_errors = 0
        self.policy = FEED_POLICY.get(name, "strict")
        # id -> (lat, lon, coord_since|None). coord_since=None: coordenada vista desde
        # el arranque sin cambiar aún -> edad desconocida (no la inventamos)
        self.coords: dict[str, tuple[float, float, datetime | None]] = {}

    async def _resolve(self):
        if self.url and time.monotonic() - self.resolved_at < CKAN_REFRESH_S:
            return
        meta = await resolve_feed(self.c, self.ref)
        if meta["url"] != self.url:
            log.info("%s -> %s", self.name, meta["url"])
            self.etag = self.lastmod = None
        self.url, self.resolved_at = meta["url"], time.monotonic()

    async def tick(self) -> float:
        """Un sondeo. Devuelve segundos a esperar hasta el siguiente."""
        await self._resolve()
        h = {}
        if self.etag:
            h["If-None-Match"] = self.etag
        if self.lastmod:
            h["If-Modified-Since"] = self.lastmod
        r = await self.c.get(self.url, headers=h)
        if r.status_code == 304:
            return 1.0
        r.raise_for_status()
        body_hash = hash(r.content)
        if body_hash == self.last_body_hash:      # servidor sin ETag: mismo contenido
            return 1.0
        self.last_body_hash = body_hash
        self.etag, self.lastmod = r.headers.get("ETag"), r.headers.get("Last-Modified")
        now = time.monotonic()
        if self.last_change:
            observed = now - self.last_change
            if 1 < observed < 600:
                self.period = 0.8 * self.period + 0.2 * observed
        self.last_change = now
        await self._process(r.json())
        return max(1.0, self.period - 1.5)

    async def _process(self, doc: dict):
        now = datetime.now(timezone.utc)
        positions, parse_stats = parse_vehicle_positions(doc, self.name, seen_at=now)
        counts = Counter()
        ages = []
        present = set()
        events = {}
        first_load = not self.coords
        for p in positions:
            present.add(p.external_id)
            prev = self.coords.get(p.external_id)
            if prev and (prev[0], prev[1]) == (p.latitude, p.longitude):
                since = prev[2]                              # misma coordenada
            elif prev is None and first_load:
                since = None                                 # arranque: edad desconocida
            else:
                since = now                                  # coordenada nueva vista ahora
            self.coords[p.external_id] = (p.latitude, p.longitude, since)
            p.coord_since = since
            cls = classify(p, self.policy, now)
            if cls is None:
                counts["hidden"] += 1
                continue
            p.age_class = cls
            counts[cls] += 1
            if since is not None and since == now:
                counts["new_coord"] += 1
            a = age_seconds(p, now)
            if a is not None:
                ages.append(a)
            await self.store.upsert(p)
            await self.store.publish("train.position", p.model_dump(mode="json"))
            # Evento real: Renfe dice que el tren está en / llegando a una estación
            if p.stop_id and p.status in ("STOPPED_AT", "INCOMING_AT"):
                events[f"{p.stop_id}|{p.source}:{p.external_id}"] = {
                    "stop_id": p.stop_id, "train": f"{p.source}:{p.external_id}",
                    "label": p.label, "trip_id": p.trip_id, "status": p.status,
                    "source": p.source, "operator": "Renfe", "seen_at": now.isoformat()}
        if events:
            await self.store.hset_many(EVENTS_KEY, events)
        for gone in set(self.coords) - present:              # trenes que salen del feed
            del self.coords[gone]
        status = {
            "source": self.name, "status": "healthy", "url": self.url, "policy": self.policy,
            "last_success_at": now.isoformat(), "publish_period_s": round(self.period, 1),
            "entities": len(doc.get("entity") or []), **dict(counts),
            "parse_dropped": {k: v for k, v in parse_stats.items() if v},
            "median_age_s": round(sorted(ages)[len(ages) // 2], 1) if ages else None,
        }
        await self.store.set_source(self.name, status)
        await self.store.publish("source.status", status)
        log.info("%s: %s descartes=%s", self.name, dict(counts), status["parse_dropped"])

    async def run(self):
        while True:
            try:
                wait = await self.tick()
                self.consecutive_errors = 0
            except Exception as e:  # noqa: BLE001
                self.consecutive_errors += 1
                wait = min(60, 2 ** self.consecutive_errors)
                log.warning("%s error (%d): %s", self.name, self.consecutive_errors, e)
                status = {"source": self.name, "status": "error", "error": str(e)[:300],
                          "failed_at": utcnow_iso(), "consecutive_errors": self.consecutive_errors}
                old = (await self.store.sources()).get(self.name, {})
                status["last_success_at"] = old.get("last_success_at")
                await self.store.set_source(self.name, status)
                await self.store.publish("source.status", status)
            await asyncio.sleep(wait)


class TripUpdatesWorker:
    """Retrasos oficiales de Renfe (GTFS-RT TripUpdates)."""

    def __init__(self, name, ref, store, client, period=30.0):
        self.name, self.ref, self.store, self.c, self.period = name, ref, store, client, period
        self.url = None

    async def run(self):
        errors = 0
        while True:
            try:
                if not self.url:
                    self.url = (await resolve_feed(self.c, self.ref))["url"]
                r = await self.c.get(self.url)
                r.raise_for_status()
                delays = parse_trip_updates(r.json())
                await self.store.replace_hash(f"{DELAYS_KEY}:{self.name}", delays)
                log.info("retrasos %s: %d viajes", self.name, len(delays))
                errors = 0
            except Exception as e:  # noqa: BLE001
                errors += 1
                self.url = None if errors > 3 else self.url
                log.warning("trip_updates %s: %s", self.name, e)
            await asyncio.sleep(self.period if not errors else min(120, 5 * errors))


async def prune_events(store):
    while True:
        await asyncio.sleep(60)
        now = datetime.now(timezone.utc).timestamp()
        ev = await store.hgetall(EVENTS_KEY)
        old = [k for k, v in ev.items()
               if now - datetime.fromisoformat(v["seen_at"]).timestamp() > STATION_EVENT_TTL_S]
        await store.hdel(EVENTS_KEY, *old)


async def run_collector(store=None):
    store = store or make_store(REDIS_URL)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                 headers={"User-Agent": "RailRadar/0.1"}) as client:
        tasks = [FeedWorker(n, ref, store, client).run() for n, ref in FEEDS]
        if STATIONS_ENABLED:
            stations = await load_stations(client)
            await store.replace_hash(STATIONS_KEY, stations)
            tasks += [TripUpdatesWorker(n, ref, store, client).run() for n, ref in TRIP_UPDATE_FEEDS]
            tasks.append(prune_events(store))
        await asyncio.gather(*tasks)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run_collector())
