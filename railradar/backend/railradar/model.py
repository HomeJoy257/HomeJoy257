"""Modelo de posición.

Hallazgo de la auditoría real (31-10-2026):
- Cercanías: el `timestamp` de Renfe es de LOTE, no de la fijación GPS; el 82 %
  de los puntos repite coordenada con hora nueva.
- AV/LD/MD: no trae timestamp por vehículo y la cabecera va 1 h desfasada.
Por eso la edad NO se toma del feed: se mide desde que RailRadar ve cambiar la
coordenada (`coord_since`). Si no la hemos visto cambiar, la edad es desconocida.
"""
from datetime import datetime, timezone
from math import isfinite

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from .config import MAX_AGE_SECONDS, SPAIN_BBOX

FRESH = "fresh_gps"          # edad medida y ≤ 120 s (o parado en estación según Renfe)
UNKNOWN = "unknown_age"      # posición real de Renfe, antigüedad no determinable


class RealTrainPosition(BaseModel):
    source: str
    external_id: str
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    seen_at: AwareDatetime                      # cuándo la vimos en el feed
    coord_since: AwareDatetime | None = None    # cuándo vimos aparecer ESTA coordenada
    feed_ts: AwareDatetime | None = None        # timestamp del feed (informativo, no fiable)
    age_class: str = UNKNOWN
    trip_id: str | None = None
    label: str | None = None
    route_id: str | None = None
    product: str | None = None                  # AVE / AVLO / ALVIA / AVANT / ... (GTFS Renfe)
    status: str | None = None                   # STOPPED_AT / INCOMING_AT / IN_TRANSIT_TO
    stop_id: str | None = None
    speed_mps: float | None = None
    bearing: float | None = None
    position_type: str = "reported_gps"

    @field_validator("seen_at", "coord_since", "feed_ts")
    @classmethod
    def _utc(cls, v):
        return v.astimezone(timezone.utc) if v else v


def coord_problem(p: RealTrainPosition) -> str | None:
    if not (isfinite(p.latitude) and isfinite(p.longitude)):
        return "nan"
    if p.latitude == 0 and p.longitude == 0:
        return "null_island"
    lat0, lat1, lon0, lon1 = SPAIN_BBOX
    if not (lat0 <= p.latitude <= lat1 and lon0 <= p.longitude <= lon1):
        return "out_of_bbox"
    return None


def age_seconds(p: RealTrainPosition, now: datetime | None = None) -> float | None:
    """Segundos desde que vimos aparecer la coordenada (None = desconocida)."""
    if p.coord_since is None:
        return None
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - p.coord_since).total_seconds())


def classify(p: RealTrainPosition, policy: str, now: datetime | None = None) -> str | None:
    """Devuelve FRESH / UNKNOWN, o None si no debe mostrarse.

    policy="strict":  solo se muestra si la coordenada cambió hace ≤120 s, o si
                      Renfe dice STOPPED_AT (parado en estación).
    policy="unknown_age": se muestra en gris mientras esté en el feed.
    """
    if coord_problem(p):
        return None
    if policy != "strict":
        # Sin hora fiable en el feed (AV/LD/MD): aunque veamos cambiar la coordenada,
        # no sabemos cuánto tardó Renfe en publicarla -> siempre gris.
        return UNKNOWN
    age = age_seconds(p, now)
    if age is not None and age <= MAX_AGE_SECONDS:
        return FRESH
    return FRESH if p.status == "STOPPED_AT" and p.coord_since is not None else None
