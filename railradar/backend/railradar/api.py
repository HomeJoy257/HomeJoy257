"""API pública de lectura + SSE. Sirve también la web estática."""
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .config import EMBEDDED_COLLECTOR, FEED_POLICY, MAX_AGE_SECONDS, REDIS_URL
from .model import FRESH, RealTrainPosition, age_seconds, classify
from .store import DELAYS_KEY, EVENTS_KEY, STATIONS_KEY, make_store

log = logging.getLogger("railradar.api")
WEB_DIR = Path(__file__).resolve().parents[2] / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = getattr(app.state, "store", None) or make_store(REDIS_URL)
    task = None
    if EMBEDDED_COLLECTOR:
        from .collector import run_collector
        task = asyncio.create_task(run_collector(app.state.store))
    yield
    if task:
        task.cancel()


app = FastAPI(title="RailRadar España", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["GET"])


async def live_positions(request: Request) -> list[RealTrainPosition]:
    now = datetime.now(timezone.utc)
    out = []
    # Re-clasificamos al servir: un FRESH puede haber pasado de 120 s desde que se guardó
    for p in await request.app.state.store.snapshot():
        cls = classify(p, FEED_POLICY.get(p.source, "strict"), now)
        if cls:
            p.age_class = cls
            out.append(p)
    return out


async def delays(request: Request) -> dict:
    out = {}
    for src in {p for p in FEED_POLICY} | {"renfe_ld", "renfe_cercanias"}:
        out[src] = await request.app.state.store.hgetall(f"{DELAYS_KEY}:{src}")
    return out


def to_feature(p: RealTrainPosition, now: datetime, dl: dict | None = None) -> dict:
    props = p.model_dump(mode="json", exclude={"latitude", "longitude"})
    d = ((dl or {}).get(p.source) or {}).get(p.trip_id or "")
    props["delay_s"] = d.get("delay_s") if d else None
    props["id"] = f"{p.source}:{p.external_id}"
    a = age_seconds(p, now)
    props["age_seconds"] = round(a, 1) if a is not None else None
    return {"type": "Feature", "id": props["id"],
            "geometry": {"type": "Point", "coordinates": [p.longitude, p.latitude]},
            "properties": props}


@app.get("/api/v1/trains/geojson")
@app.get("/api/v1/trains/live")
async def trains_live(request: Request, source: str | None = None, age_class: str | None = None):
    now = datetime.now(timezone.utc)
    ps = [p for p in await live_positions(request)
          if (not source or p.source == source) and (not age_class or p.age_class == age_class)]
    dl = await delays(request)
    return JSONResponse(
        {"type": "FeatureCollection", "generated_at": now.isoformat(),
         "max_age_seconds": MAX_AGE_SECONDS,
         "features": [to_feature(p, now, dl) for p in ps]},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/stations/events")
async def station_events(request: Request):
    """Estaciones con trenes parados/llegando según Renfe (últimos 30 min). Datos reales,
    sin posiciones entre estaciones."""
    store = request.app.state.store
    stations = await store.hgetall(STATIONS_KEY)
    events = await store.hgetall(EVENTS_KEY)
    dl = await delays(request)
    now = datetime.now(timezone.utc)
    by_stop: dict[str, list] = {}
    for e in events.values():
        d = (dl.get(e["source"]) or {}).get(e.get("trip_id") or "")
        e["delay_s"] = d.get("stops", {}).get(e["stop_id"], d.get("delay_s")) if d else None
        e["minutes_ago"] = round((now - datetime.fromisoformat(e["seen_at"])).total_seconds() / 60, 1)
        by_stop.setdefault(e["stop_id"], []).append(e)
    feats = []
    for stop_id, evs in by_stop.items():
        st = stations.get(stop_id)
        if not st:
            continue
        evs.sort(key=lambda e: e["seen_at"], reverse=True)
        feats.append({"type": "Feature", "id": stop_id,
                      "geometry": {"type": "Point", "coordinates": [st["lon"], st["lat"]]},
                      "properties": {"stop_id": stop_id, "name": st["name"], "count": len(evs),
                                     "events": evs[:20]}})
    return JSONResponse({"type": "FeatureCollection", "generated_at": now.isoformat(),
                         "note": "Solo trenes de Renfe. Iryo y Ouigo no publican datos abiertos.",
                         "features": feats}, headers={"Cache-Control": "no-store"})


@app.get("/api/v1/trains/{train_id:path}")
async def train_detail(train_id: str, request: Request):
    now = datetime.now(timezone.utc)
    for p in await live_positions(request):
        if f"{p.source}:{p.external_id}" == train_id:
            return to_feature(p, now, await delays(request))
    raise HTTPException(404, "Tren sin posición publicada ahora mismo")


@app.get("/api/v1/sources")
async def sources(request: Request):
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": await request.app.state.store.sources()}


@app.get("/api/v1/stats")
async def stats(request: Request):
    now = datetime.now(timezone.utc)
    ps = await live_positions(request)
    by_src: dict[str, int] = {}
    buckets = {"0-30": 0, "30-90": 0, "90-120": 0, "stopped_at_station": 0, "unknown_age": 0}
    for p in ps:
        by_src[p.source] = by_src.get(p.source, 0) + 1
        a = age_seconds(p, now)
        if p.age_class != FRESH:
            buckets["unknown_age"] += 1
        elif a is not None and a <= MAX_AGE_SECONDS:
            buckets["0-30" if a < 30 else "30-90" if a < 90 else "90-120"] += 1
        else:
            buckets["stopped_at_station"] += 1
    return {"generated_at": now.isoformat(), "visible": len(ps),
            "by_source": by_src, "by_class": buckets}


@app.get("/api/v1/stream")
async def stream(request: Request):
    store = request.app.state.store

    async def gen():
        # Primero: hora del servidor, para que el navegador calcule su desfase
        yield f"event: hello\ndata: {json.dumps({'server_time': datetime.now(timezone.utc).isoformat(), 'max_age_seconds': MAX_AGE_SECONDS})}\n\n"
        sub = store.subscribe()
        nxt = asyncio.ensure_future(sub.__anext__())
        try:
            while not await request.is_disconnected():
                done, _ = await asyncio.wait({nxt}, timeout=15)
                if not done:
                    yield ": keepalive\n\n"
                    continue
                msg = json.loads(nxt.result())
                nxt = asyncio.ensure_future(sub.__anext__())
                yield f"event: {msg['event']}\ndata: {json.dumps(msg['data'])}\n\n"
        finally:
            nxt.cancel()
            await sub.aclose()

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})


@app.get("/health/live")
async def health_live():
    return {"status": "ok"}


@app.get("/health/ready")
async def health_ready(request: Request):
    ok = await request.app.state.store.ping()
    return JSONResponse({"status": "ok" if ok else "degraded", "store": ok},
                        status_code=200 if ok else 503)


if WEB_DIR.exists():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
