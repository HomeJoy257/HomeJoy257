from datetime import datetime, timezone
from math import isfinite

from pydantic import AwareDatetime, BaseModel, Field, field_validator

from .config import CLOCK_SKEW_TOLERANCE, MAX_AGE_SECONDS, SPAIN_BBOX


class RealTrainPosition(BaseModel):
    source: str
    external_id: str
    observed_at: AwareDatetime          # rechaza fechas sin zona horaria
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    trip_id: str | None = None
    label: str | None = None
    route_id: str | None = None
    speed_mps: float | None = None
    bearing: float | None = None
    position_type: str = "reported_gps"

    @field_validator("observed_at")
    @classmethod
    def _utc(cls, v: datetime) -> datetime:
        return v.astimezone(timezone.utc)


def rejection_reason(p: RealTrainPosition, now: datetime | None = None) -> str | None:
    """None = válida. Si no, el motivo (para estadísticas de auditoría)."""
    now = now or datetime.now(timezone.utc)
    age = (now - p.observed_at).total_seconds()
    if age < -CLOCK_SKEW_TOLERANCE:
        return "future"
    if age > MAX_AGE_SECONDS:
        return "stale"
    if not (isfinite(p.latitude) and isfinite(p.longitude)):
        return "nan"
    if p.latitude == 0 and p.longitude == 0:
        return "null_island"
    lat0, lat1, lon0, lon1 = SPAIN_BBOX
    if not (lat0 <= p.latitude <= lat1 and lon0 <= p.longitude <= lon1):
        return "out_of_bbox"
    return None


def age_seconds(p: RealTrainPosition, now: datetime | None = None) -> float:
    now = now or datetime.now(timezone.utc)
    return max(0.0, (now - p.observed_at).total_seconds())
