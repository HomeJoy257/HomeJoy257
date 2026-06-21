"""
Cliente INE Tempus3 (JSON) — confirmación, SIN vintage.

Sirve los visados de obra nueva. Endpoint público sin clave:
  https://servicios.ine.es/wstempus/js/ES/DATOS_SERIE/{COD}?nult={n}

El código de serie (COD) de visados de obra nueva debe validarse contra el
catálogo INE (OQ-04); el del registro es provisional. La estructura de respuesta
es {Data: [{Anyo, FK_TipoDato, Fecha(ms), Valor}, ...]}.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from .base import Obs, Series
from .http import get

BASE = "https://servicios.ine.es/wstempus/js/ES"


def get_series(cod: str, nult: int = 600) -> Series:
    url = f"{BASE}/DATOS_SERIE/{cod}"
    payload = get(url, {"nult": nult}).json()
    rows = payload.get("Data", payload) if isinstance(payload, dict) else payload
    obs: list[Obs] = []
    for row in rows or []:
        val = row.get("Valor")
        ms = row.get("Fecha")
        if val is None or ms is None:
            continue
        d = datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date()
        obs.append(Obs(date(d.year, d.month, 1), float(val)))
    return Series(cod, "ine", obs).clean()
