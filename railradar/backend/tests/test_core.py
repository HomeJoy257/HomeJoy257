from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from railradar.collector import FeedWorker
from railradar.model import FRESH, UNKNOWN, RealTrainPosition, classify
from railradar.parser import parse_vehicle_positions
from railradar.stations import parse_products, parse_stops, parse_trip_updates, product_for
from railradar.store import EVENTS_KEY, STATIONS_KEY, MemoryStore

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def pos(since_age=10, lat=40.4, lon=-3.7, ext="V1", status=None, unknown=False):
    return RealTrainPosition(source="t", external_id=ext, latitude=lat, longitude=lon, seen_at=NOW,
                             coord_since=None if unknown else NOW - timedelta(seconds=since_age), status=status)


@pytest.mark.parametrize("p,policy,expected", [
    (pos(10), "strict", FRESH),
    (pos(120), "strict", FRESH),
    (pos(121), "strict", None),                        # coordenada sin cambiar >120 s
    (pos(600, status="STOPPED_AT"), "strict", FRESH),  # parado en estación según Renfe
    (pos(unknown=True), "strict", None),               # edad desconocida: no se muestra
    (pos(unknown=True), "unknown_age", UNKNOWN),       # LD: gris
    (pos(900), "unknown_age", UNKNOWN),
    (pos(5), "unknown_age", UNKNOWN),                  # aunque cambie, sin hora del feed: gris
    (pos(lat=0, lon=0), "unknown_age", None),
    (pos(lat=48.8, lon=2.3), "strict", None),
])
def test_classify(p, policy, expected):
    assert classify(p, policy, NOW) == expected


def test_naive_datetime_rejected():
    with pytest.raises(Exception):
        RealTrainPosition(source="t", external_id="x", latitude=40, longitude=-3, seen_at=datetime.now())


def test_parser_accepts_missing_vehicle_ts():
    doc = {"header": {"timestamp": "1"}, "entity": [
        {"id": "1", "vehicle": {"vehicle": {"id": "A"}, "position": {"latitude": 40, "longitude": -3},
                                "currentStatus": "STOPPED_AT", "stopId": "60000"}},
        {"id": "2", "vehicle": {"vehicle": {"id": "B"}, "position": {"latitude": 41, "longitude": 2},
                                "timestamp": str(int(NOW.timestamp()))}},
        {"id": "x", "tripUpdate": {}}]}
    ps, st = parse_vehicle_positions(doc, "t", NOW)
    assert [p.external_id for p in ps] == ["A", "B"]
    assert ps[0].feed_ts is None and ps[0].status == "STOPPED_AT" and ps[0].stop_id == "60000"
    assert st["no_vehicle"] == 1 and st["no_vehicle_ts"] == 1


async def test_collector_measures_age_from_coordinate_change(monkeypatch):
    monkeypatch.setattr("railradar.collector.PRODUCTS", set())
    store = MemoryStore()
    w = FeedWorker("renfe_cercanias", "http://x", store, client=None)
    w.policy = "strict"

    def doc(lat):
        return {"entity": [{"id": "1", "vehicle": {"vehicle": {"id": "A"}, "timestamp": "1",
                                                   "position": {"latitude": lat, "longitude": -3.7}}}]}
    await w._process(doc(40.40))                 # arranque: edad desconocida -> oculto
    assert await store.snapshot() == []
    await w._process(doc(40.40))                 # misma coordenada: sigue desconocida
    assert await store.snapshot() == []
    await w._process(doc(40.41))                 # cambia: ahora sí sabemos su edad
    snap = await store.snapshot()
    assert len(snap) == 1 and snap[0].age_class == FRESH and snap[0].coord_since is not None


async def test_ld_unknown_age_and_station_event():
    store = MemoryStore()
    w = FeedWorker("renfe_ld", "http://x", store, client=None, gtfs={"products": {"03063D": "AVE"}})
    w.policy = "unknown_age"
    await w._process({"entity": [{"id": "1", "vehicle": {
        "vehicle": {"id": "03063", "label": "AVE-03063"}, "trip": {"tripId": "03063D"},
        "position": {"latitude": 40.4065, "longitude": -3.6896},
        "currentStatus": "STOPPED_AT", "stopId": "60000"}}]})
    snap = await store.snapshot()
    assert snap[0].age_class == UNKNOWN
    ev = await store.hgetall(EVENTS_KEY)
    assert list(ev) == ["60000|renfe_ld:03063"]


def test_trip_updates_and_stops():
    tu = parse_trip_updates({"entity": [
        {"tripUpdate": {"trip": {"tripId": "T1"}, "delay": 300}},
        {"tripUpdate": {"trip": {"tripId": "T2"}, "stopTimeUpdate": [{"stopId": "60000", "arrival": {"delay": 120}}]}}]})
    assert tu["T1"]["delay_s"] == 300 and tu["T2"]["stops"]["60000"] == 120
    import io, zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("stops.txt", "﻿stop_id,stop_name,stop_lat,stop_lon\n60000,Atocha,40.4,-3.69\nbad,x,,\n")
    assert parse_stops(b.getvalue()) == {"60000": {"name": "Atocha", "lat": 40.4, "lon": -3.69}}


def test_api_layers():
    import asyncio
    from railradar import api
    store = MemoryStore()
    api.app.state.store = store
    fresh = pos(5, ext="fresh").model_copy(update={"source": "renfe_cercanias"})
    old = pos(300, ext="old").model_copy(update={"source": "renfe_cercanias"})
    gray = pos(unknown=True, ext="gray", lat=41).model_copy(update={"source": "renfe_ld", "trip_id": "X"})
    for p in (fresh, old, gray):
        asyncio.run(store.upsert(p))
    asyncio.run(store.hset_many(f"railradar:delays:renfe_ld", {"X": {"delay_s": 240, "stops": {}}}))
    asyncio.run(store.replace_hash(STATIONS_KEY, {"60000": {"name": "Atocha", "lat": 40.4, "lon": -3.69}}))
    asyncio.run(store.hset_many(EVENTS_KEY, {"60000|renfe_ld:gray": {
        "stop_id": "60000", "train": "renfe_ld:gray", "trip_id": "X", "status": "STOPPED_AT",
        "source": "renfe_ld", "operator": "Renfe", "seen_at": NOW.isoformat()}}))
    with TestClient(api.app) as c:
        feats = {f["properties"]["external_id"]: f["properties"] for f in c.get("/api/v1/trains/live").json()["features"]}
        assert set(feats) == {"fresh", "gray"}                  # 'old' (300 s sin cambiar) fuera
        assert feats["gray"]["age_class"] == "unknown_age" and feats["gray"]["age_seconds"] is None
        assert feats["gray"]["delay_s"] == 240
        st = c.get("/api/v1/stations/events").json()["features"]
        assert st[0]["properties"]["name"] == "Atocha" and st[0]["properties"]["events"][0]["delay_s"] == 240
        assert c.get("/health/ready").status_code == 200


def _gtfs(routes, trips):
    import io, zipfile
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("routes.txt", "route_id,route_short_name   \n" + "\n".join(f"{a},{c}  " for a, c in routes))
        z.writestr("trips.txt", "route_id,trip_id,trip_short_name\n" + "\n".join(f"{a},{b_},{c}" for a, b_, c in trips))
    return b.getvalue()


def test_products_index_and_lookup():
    prods = parse_products(_gtfs([("R1", "AVE"), ("R2", "MD")],
                                 [("R1", "0595112026-10-30", "05951"), ("R2", "1580412026-10-30", "15804")]))
    assert product_for(prods, "0595112026-10-30", "05951") == "AVE"
    assert product_for(prods, "0595122026-11-02", "05951") == "AVE"   # otra fecha: por nº de tren
    assert product_for(prods, "1580412026-10-30", None) == "MD"
    assert product_for(prods, "9999912026-10-30", None) is None


async def test_only_high_speed_shown():
    store = MemoryStore()
    w = FeedWorker("renfe_ld", "http://x", store, client=None,
                   gtfs={"products": {"A": "AVE", "B": "MD", "C": "ALVIA"}})
    w.policy = "unknown_age"
    ent = lambda i, trip: {"id": i, "vehicle": {"vehicle": {"id": i}, "trip": {"tripId": trip},
                                                "position": {"latitude": 40.4, "longitude": -3.7}}}
    await w._process({"entity": [ent("1", "A"), ent("2", "B"), ent("3", "C"), ent("4", "Z")]})
    snap = {p.external_id: p.product for p in await store.snapshot()}
    assert snap == {"1": "AVE", "3": "ALVIA"}


async def test_no_product_index_fails_closed():
    store = MemoryStore()
    w = FeedWorker("renfe_ld", "http://x", store, client=None, gtfs={"products": {}})
    w.policy = "unknown_age"
    await w._process({"entity": [{"id": "1", "vehicle": {"vehicle": {"id": "1"},
                                  "position": {"latitude": 40.4, "longitude": -3.7}}}]})
    assert await store.snapshot() == []


def test_duplicate_train_number_gets_distinct_ids():
    doc = {"entity": [{"id": str(i), "vehicle": {"vehicle": {"id": "05951"}, "trip": {"tripId": f"059511{i}"},
                                                 "position": {"latitude": 40, "longitude": -3}}} for i in range(3)]}
    ps, _ = parse_vehicle_positions(doc, "t", NOW)
    assert len({p.external_id for p in ps}) == 3
