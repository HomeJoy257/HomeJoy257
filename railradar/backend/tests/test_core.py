from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from railradar.model import RealTrainPosition, rejection_reason
from railradar.parser import parse_vehicle_positions
from railradar.store import MemoryStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def pos(age=10, lat=40.4, lon=-3.7, ext="V1"):
    return RealTrainPosition(source="t", external_id=ext, observed_at=NOW - timedelta(seconds=age),
                             latitude=lat, longitude=lon)


@pytest.mark.parametrize("p,reason", [
    (pos(10), None), (pos(120), None), (pos(121), "stale"), (pos(-30), "future"),
    (pos(lat=0, lon=0), "null_island"), (pos(lat=48.8, lon=2.3), "out_of_bbox"),
])
def test_rejection(p, reason):
    assert rejection_reason(p, NOW) == reason


def test_naive_datetime_rejected():
    with pytest.raises(Exception):
        RealTrainPosition(source="t", external_id="x", observed_at=datetime.now(), latitude=40, longitude=-3)


def ent(vid, ts, lat=40.4, lon=-3.7):
    v = {"vehicle": {"id": vid}, "position": {"latitude": lat, "longitude": lon}}
    if ts is not None:
        v["timestamp"] = str(ts)
    return {"id": vid, "vehicle": v}


def test_parser_uses_vehicle_ts_and_drops_header_ts():
    h = int(NOW.timestamp())
    doc = {"header": {"timestamp": str(h)},
           "entity": [ent("A", h - 10), ent("B", None), ent("C", h), {"id": "x", "tripUpdate": {}}]}
    ps, st = parse_vehicle_positions(doc, "t", trust_header_ts=False)
    assert [p.external_id for p in ps] == ["A"]
    assert st["no_ts"] == 1 and st["ts_is_header"] == 1 and st["no_vehicle"] == 1
    ps, _ = parse_vehicle_positions(doc, "t", trust_header_ts=True)
    assert {p.external_id for p in ps} == {"A", "C"}


def test_parser_snake_case():
    doc = {"entity": [{"id": "1", "vehicle": {"vehicle": {"id": "S"}, "trip": {"trip_id": "T9"},
                                              "position": {"latitude": 41, "longitude": 2},
                                              "timestamp": int(NOW.timestamp()) - 5}}]}
    ps, _ = parse_vehicle_positions(doc, "t")
    assert ps[0].trip_id == "T9"


async def test_store_never_goes_back_in_time():
    s = MemoryStore()
    assert await s.upsert(pos(10))
    assert not await s.upsert(pos(10))     # duplicado
    assert not await s.upsert(pos(30))     # más viejo
    assert await s.upsert(pos(2))          # más nuevo
    assert not await s.upsert(pos(500))    # caducado
    snap = await s.snapshot()
    assert len(snap) == 1 and snap[0].observed_at == NOW - timedelta(seconds=2)


def test_api_serves_only_fresh():
    from railradar import api
    store = MemoryStore()
    api.app.state.store = store
    with TestClient(api.app) as c:
        import asyncio
        asyncio.run(store.upsert(pos(5, ext="fresh")))
        # forzamos uno caducado saltándonos el TTL del store
        stale = pos(5, ext="stale")
        asyncio.run(store.upsert(stale))
        store._live["t:stale"] = (9e12, stale.model_copy(update={"observed_at": NOW - timedelta(seconds=300)}).model_dump_json())
        j = c.get("/api/v1/trains/live").json()
        ids = [f["properties"]["external_id"] for f in j["features"]]
        assert ids == ["fresh"]
        f = j["features"][0]
        assert f["geometry"]["coordinates"] == [-3.7, 40.4]
        assert f["properties"]["position_type"] == "reported_gps"
        assert c.get("/api/v1/trains/t:stale").status_code == 404
        assert c.get("/health/ready").status_code == 200
