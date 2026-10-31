"""GTFS-Realtime (JSON) -> RealTrainPosition. Acepta camelCase y snake_case."""
from datetime import datetime, timezone

from pydantic import ValidationError

from .config import TRUST_TS_EQUAL_HEADER
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


def parse_vehicle_positions(doc: dict, source: str,
                            trust_header_ts: bool = TRUST_TS_EQUAL_HEADER
                            ) -> tuple[list[RealTrainPosition], dict]:
    """Devuelve posiciones y contadores de descarte de parseo.

    Regla: solo se usa el timestamp del VEHÍCULO. Si falta, o es idéntico al
    de la cabecera (indicio de que es la hora de generación del fichero),
    la posición se descarta: no podemos garantizar su antigüedad.
    """
    header_ts = _ts(_g(_g(doc, "header") or {}, "timestamp"))
    out, stats = [], {"no_vehicle": 0, "no_position": 0, "no_ts": 0,
                      "ts_is_header": 0, "no_id": 0, "invalid": 0}
    for ent in _g(doc, "entity") or []:
        v = _g(ent, "vehicle")
        if not v:
            stats["no_vehicle"] += 1
            continue
        pos = _g(v, "position")
        if not pos or _g(pos, "latitude") is None or _g(pos, "longitude") is None:
            stats["no_position"] += 1
            continue
        ts = _ts(_g(v, "timestamp"))
        if ts is None:
            stats["no_ts"] += 1
            continue
        if not trust_header_ts and header_ts is not None and ts == header_ts:
            stats["ts_is_header"] += 1
            continue
        veh = _g(v, "vehicle") or {}
        trip = _g(v, "trip") or {}
        ext_id = _g(veh, "id") or _g(veh, "label") or _g(ent, "id")
        if not ext_id:
            stats["no_id"] += 1
            continue
        try:
            out.append(RealTrainPosition(
                source=source,
                external_id=str(ext_id),
                observed_at=ts,
                latitude=float(_g(pos, "latitude")),
                longitude=float(_g(pos, "longitude")),
                trip_id=_g(trip, "tripId", "trip_id"),
                route_id=_g(trip, "routeId", "route_id"),
                label=_g(veh, "label"),
                speed_mps=_g(pos, "speed"),
                bearing=_g(pos, "bearing"),
            ))
        except (ValidationError, TypeError, ValueError):
            stats["invalid"] += 1
    return out, stats
