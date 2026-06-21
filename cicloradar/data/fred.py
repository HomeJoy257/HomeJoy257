"""
Cliente FRED / ALFRED — backbone POINT-IN-TIME.

`get_series` devuelve la serie revisada (última vintage). `get_series_as_of`
usa ALFRED (`realtime_start`/`realtime_end`) para devolver lo que se conocía en
una fecha dada — esto es lo que permite construir la firma pre-recesión con la
información disponible en cada pico, sin contaminar con revisiones posteriores.

Requiere FRED_API_KEY (gratuita).
"""

from __future__ import annotations

from datetime import date

from ..config import settings
from .base import Obs, Series
from .http import get

BASE = "https://api.stlouisfed.org/fred/series/observations"


def _parse(series_id: str, payload: dict) -> Series:
    obs: list[Obs] = []
    for row in payload.get("observations", []):
        v = row.get("value", ".")
        if v in (".", "", None):          # sentinela FRED para "sin dato"
            continue
        try:
            val = float(v)
        except ValueError:
            continue
        y, m, d = row["date"].split("-")
        obs.append(Obs(date(int(y), int(m), 1), val))
    return Series(series_id, "fred", obs).clean()


def get_series(series_id: str, *, frequency: str | None = None) -> Series:
    """Serie revisada (última vintage)."""
    if not settings.fred_api_key:
        raise RuntimeError("FRED_API_KEY no configurada (clave gratuita en fred.stlouisfed.org).")
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
    }
    if frequency:
        params["frequency"] = frequency      # p.ej. 'm' para forzar mensual
    return _parse(series_id, get(BASE, params).json())


def get_series_as_of(series_id: str, as_of: date) -> Series:
    """Vintage point-in-time: lo conocido en `as_of` (ALFRED).

    Usamos realtime_start=realtime_end=as_of para recuperar exactamente la
    fotografía de datos publicada en esa fecha.
    """
    if not settings.fred_api_key:
        raise RuntimeError("FRED_API_KEY no configurada.")
    iso = as_of.isoformat()
    params = {
        "series_id": series_id,
        "api_key": settings.fred_api_key,
        "file_type": "json",
        "realtime_start": iso,
        "realtime_end": iso,
    }
    return _parse(series_id, get(BASE, params).json())
