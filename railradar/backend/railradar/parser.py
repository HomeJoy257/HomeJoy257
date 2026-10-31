"""GTFS-Realtime (JSON) -> RealTrainPosition. Acepta camelCase y snake_case."""
from datetime import datetime, timezone

from pydantic import ValidationError

from .model import RealTrainPosition


def _g(d, *keys):
    if not isinstance(d, dict):
        return None
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return None


def _ts(v) -> datetime | None:
    if v in (None, "", 0, "0"):
        return None
    try:
        return datetime.fromtimestamp(int(float(v)), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def parse_vehicle_positions(doc: dict, source: str, seen_at: datetime | None = None
                            ) -> tuple[list[RealTrainPosition], dict]:
    """GTFS-RT JSON -> posiciones (sin decidir aún la edad: eso lo hace el colector
    comparando con la coordenada anterior). Solo coordenadas publicadas por el feed."""
    seen_at = seen_at or datetime.now(timezone.utc)
    out, stats = [], {"no_vehicle": 0, "no_position": 0, "no_id": 0, "invalid": 0, "no_vehicle_ts": 0}
    used = set()
    for ent in _g(doc, "entity") or []:
        v = _g(ent, "vehicle")
        if not v:
            stats["no_vehicle"] += 1
            continue
        pos = _g(v, "position")
        if not pos or _g(pos, "latitude") is None or _g(pos, "longitude") is None:
            stats["no_position"] += 1
            continue
        veh = _g(v, "vehicle") or {}
        trip = _g(v, "trip") or {}
        ext_id = _g(veh, "id") or _g(veh, "label") or _g(ent, "id")
        if not ext_id:
            stats["no_id"] += 1
            continue
        ext_id = str(ext_id)
        trip_id = _g(trip, "tripId", "trip_id")
        if ext_id in used and trip_id:          # mismo nº de tren en varias entidades
            ext_id = f"{ext_id}~{trip_id}"
        used.add(ext_id)
        ts = _ts(_g(v, "timestamp"))
        stats["no_vehicle_ts"] += ts is None
        try:
            out.append(RealTrainPosition(
                source=source, external_id=ext_id,
                latitude=float(_g(pos, "latitude")), longitude=float(_g(pos, "longitude")),
                seen_at=seen_at, feed_ts=ts,
                trip_id=trip_id, route_id=_g(trip, "routeId", "route_id"),
                label=_g(veh, "label"), status=_g(v, "currentStatus", "current_status"),
                stop_id=_g(v, "stopId", "stop_id"),
                speed_mps=_g(pos, "speed"), bearing=_g(pos, "bearing"),
            ))
        except (ValidationError, TypeError, ValueError):
            stats["invalid"] += 1
    return out, stats
