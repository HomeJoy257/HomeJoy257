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

from .config import EMBEDDED_COLLECTOR, MAX_AGE_SECONDS, REDIS_URL
from .model import RealTrainPosition, age_seconds, rejection_reason
from .store import make_store

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
    # Doble filtro: aunque el store caduque solo, re-validamos al servir.
    return [p for p in await request.app.state.store.snapshot() if rejection_reason(p, now) is None]


def to_feature(p: RealTrainPosition, now: datetime) -> dict:
    props = p.model_dump(mode="json", exclude={"latitude", "longitude"})
    props["id"] = f"{p.source}:{p.external_id}"
    props["age_seconds"] = round(age_seconds(p, now), 1)
    return {"type": "Feature", "id": props["id"],
            "geometry": {"type": "Point", "coordinates": [p.longitude, p.latitude]},
            "properties": props}


@app.get("/api/v1/trains/geojson")
@app.get("/api/v1/trains/live")
async def trains_live(request: Request, source: str | None = None, max_age: int = MAX_AGE_SECONDS):
    now = datetime.now(timezone.utc)
    max_age = min(max_age, MAX_AGE_SECONDS)
    ps = [p for p in await live_positions(request)
          if (not source or p.source == source) and age_seconds(p, now) <= max_age]
    return JSONResponse(
        {"type": "FeatureCollection", "generated_at": now.isoformat(),
         "max_age_seconds": MAX_AGE_SECONDS,
         "features": [to_feature(p, now) for p in ps]},
        headers={"Cache-Control": "no-store"},
    )


@app.get("/api/v1/trains/{train_id:path}")
async def train_detail(train_id: str, request: Request):
    now = datetime.now(timezone.utc)
    for p in await live_positions(request):
        if f"{p.source}:{p.external_id}" == train_id:
            return to_feature(p, now)
    raise HTTPException(404, "Tren sin posición GPS válida en los últimos 120 s")


@app.get("/api/v1/sources")
async def sources(request: Request):
    return {"generated_at": datetime.now(timezone.utc).isoformat(),
            "sources": await request.app.state.store.sources()}


@app.get("/api/v1/stats")
async def stats(request: Request):
    now = datetime.now(timezone.utc)
    ps = await live_positions(request)
    by_src: dict[str, int] = {}
    buckets = {"0-30": 0, "30-90": 0, "90-120": 0}
    for p in ps:
        by_src[p.source] = by_src.get(p.source, 0) + 1
        a = age_seconds(p, now)
        buckets["0-30" if a < 30 else "30-90" if a < 90 else "90-120"] += 1
    return {"generated_at": now.isoformat(), "visible": len(ps),
            "by_source": by_src, "age_buckets": buckets}


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
