"""Estado en directo. Redis en producción, memoria en desarrollo/tests.

Cada tren se retira si deja de aparecer en el feed (PRESENCE_TTL_S).
"""
import asyncio
import json
import time
from datetime import datetime, timezone

from .config import PRESENCE_TTL_S
from .model import RealTrainPosition

CHANNEL = "railradar:events"
PREFIX = "live:"
SOURCES_KEY = "railradar:sources"


def _ttl(p: RealTrainPosition) -> int:
    """El tren se retira si deja de aparecer en el feed durante PRESENCE_TTL_S."""
    return int(PRESENCE_TTL_S - (time.time() - p.seen_at.timestamp()))


class MemoryStore:
    def __init__(self):
        self._live: dict[str, tuple[float, str]] = {}   # key -> (expires_at, json)
        self._sources: dict[str, str] = {}
        self._subs: set[asyncio.Queue] = set()
        self._h: dict[str, dict[str, str]] = {}

    async def upsert(self, p: RealTrainPosition) -> bool:
        ttl = _ttl(p)
        if ttl <= 0:
            return False
        key = f"{p.source}:{p.external_id}"
        cur = self._live.get(key)
        if cur and RealTrainPosition.model_validate_json(cur[1]).seen_at > p.seen_at:
            return False                                # no retroceder
        self._live[key] = (time.time() + ttl, p.model_dump_json())
        return True

    async def snapshot(self) -> list[RealTrainPosition]:
        now = time.time()
        for k in [k for k, (exp, _) in self._live.items() if exp <= now]:
            del self._live[k]
        return [RealTrainPosition.model_validate_json(v) for _, v in self._live.values()]

    async def set_source(self, name: str, status: dict):
        self._sources[name] = json.dumps(status, default=str)

    async def sources(self) -> dict:
        return {k: json.loads(v) for k, v in self._sources.items()}

    async def publish(self, event: str, data: dict):
        msg = json.dumps({"event": event, "data": data}, default=str)
        for q in list(self._subs):
            if q.qsize() < 1000:
                q.put_nowait(msg)

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue()
        self._subs.add(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._subs.discard(q)

    async def ping(self) -> bool:
        return True

    # --- hashes genéricos (estaciones, eventos, retrasos)
    async def hset_many(self, key: str, mapping: dict):
        self._h.setdefault(key, {}).update({k: json.dumps(v, default=str) for k, v in mapping.items()})

    async def hgetall(self, key: str) -> dict:
        return {k: json.loads(v) for k, v in self._h.get(key, {}).items()}

    async def hdel(self, key: str, *fields):
        for f in fields:
            self._h.get(key, {}).pop(f, None)

    async def replace_hash(self, key: str, mapping: dict):
        self._h[key] = {k: json.dumps(v, default=str) for k, v in mapping.items()}


class RedisStore:
    # Lua: solo escribe si la posición es más nueva que la guardada.
    _UPSERT = """
    local cur = redis.call('GET', KEYS[1])
    if cur then
      local ok, obj = pcall(cjson.decode, cur)
      if ok and tonumber(obj['t']) > tonumber(ARGV[2]) then return 0 end
    end
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
    return 1
    """

    def __init__(self, url: str):
        import redis.asyncio as aioredis
        self.r = aioredis.from_url(url, decode_responses=True)
        self._upsert = self.r.register_script(self._UPSERT)

    async def upsert(self, p: RealTrainPosition) -> bool:
        ttl = _ttl(p)
        if ttl <= 0:
            return False
        key = f"{PREFIX}{p.source}:{p.external_id}"
        t = p.seen_at.timestamp()
        data = json.dumps({"t": t, "p": p.model_dump(mode="json")})
        return bool(await self._upsert(keys=[key], args=[data, t, ttl]))

    async def snapshot(self) -> list[RealTrainPosition]:
        keys = [k async for k in self.r.scan_iter(f"{PREFIX}*", count=1000)]
        if not keys:
            return []
        vals = await self.r.mget(keys)
        return [RealTrainPosition.model_validate(json.loads(v)["p"]) for v in vals if v]

    async def set_source(self, name: str, status: dict):
        await self.r.hset(SOURCES_KEY, name, json.dumps(status, default=str))

    async def sources(self) -> dict:
        return {k: json.loads(v) for k, v in (await self.r.hgetall(SOURCES_KEY)).items()}

    async def publish(self, event: str, data: dict):
        await self.r.publish(CHANNEL, json.dumps({"event": event, "data": data}, default=str))

    async def subscribe(self):
        ps = self.r.pubsub()
        await ps.subscribe(CHANNEL)
        try:
            async for m in ps.listen():
                if m["type"] == "message":
                    yield m["data"]
        finally:
            await ps.unsubscribe(CHANNEL)
            await ps.aclose()

    async def ping(self) -> bool:
        try:
            return bool(await self.r.ping())
        except Exception:
            return False

    async def hset_many(self, key: str, mapping: dict):
        if mapping:
            await self.r.hset(key, mapping={k: json.dumps(v, default=str) for k, v in mapping.items()})

    async def hgetall(self, key: str) -> dict:
        return {k: json.loads(v) for k, v in (await self.r.hgetall(key)).items()}

    async def hdel(self, key: str, *fields):
        if fields:
            await self.r.hdel(key, *fields)

    async def replace_hash(self, key: str, mapping: dict):
        pipe = self.r.pipeline()
        pipe.delete(key)
        if mapping:
            pipe.hset(key, mapping={k: json.dumps(v, default=str) for k, v in mapping.items()})
        await pipe.execute()


def make_store(url: str | None):
    return RedisStore(url) if url else MemoryStore()


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

STATIONS_KEY = "railradar:stations"
EVENTS_KEY = "railradar:station_events"
DELAYS_KEY = "railradar:delays"
