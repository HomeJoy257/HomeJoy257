"""Recolector: sondeo adaptativo -> validación -> Redis/SSE.

Una sola instancia en producción (no escalar con la API).
"""
import asyncio
import logging
import time
from collections import Counter

import httpx

from .ckan import resolve_feed
from .config import CKAN_REFRESH_S, FEEDS, REDIS_URL
from .model import age_seconds, rejection_reason
from .parser import parse_vehicle_positions
from .store import make_store, utcnow_iso

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
        positions, parse_stats = parse_vehicle_positions(doc, self.name)
        rejected = Counter()
        accepted = 0
        ages = []
        for p in positions:
            reason = rejection_reason(p)
            if reason:
                rejected[reason] += 1
                continue
            if await self.store.upsert(p):
                accepted += 1
                ages.append(age_seconds(p))
                await self.store.publish("train.position", p.model_dump(mode="json"))
        status = {
            "source": self.name, "status": "healthy", "url": self.url,
            "last_success_at": utcnow_iso(), "publish_period_s": round(self.period, 1),
            "entities": len(doc.get("entity") or []), "new_positions": accepted,
            "rejected": dict(rejected), "parse_dropped": {k: v for k, v in parse_stats.items() if v},
            "median_age_s": round(sorted(ages)[len(ages) // 2], 1) if ages else None,
        }
        await self.store.set_source(self.name, status)
        await self.store.publish("source.status", status)
        log.info("%s: %d nuevas, rechazadas=%s, descartes=%s",
                 self.name, accepted, dict(rejected), status["parse_dropped"])

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


async def run_collector(store=None):
    store = store or make_store(REDIS_URL)
    async with httpx.AsyncClient(timeout=15, follow_redirects=True,
                                 headers={"User-Agent": "RailRadar/0.1"}) as client:
        workers = [FeedWorker(n, ref, store, client) for n, ref in FEEDS]
        await asyncio.gather(*(w.run() for w in workers))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run_collector())
