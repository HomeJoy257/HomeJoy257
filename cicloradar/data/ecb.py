"""
Cliente ECB Data Portal (SDMX 2.1) — confirmación, SIN vintage nativo.

Sirve la curva euro (dataset YC) y el Bank Lending Survey (dataset BLS). El
formato `csvdata` es el más limpio de parsear. La clave de serie va en la URL:
  https://data-api.ecb.europa.eu/service/data/{FLOW}/{KEY}

Sesgo documentado: el BCE publica series ya revisadas; no hay fotografía
point-in-time. Se usa como confirmación del backbone FRED.
"""

from __future__ import annotations

import csv
import io
from datetime import date

from .base import Obs, Series
from .http import get

BASE = "https://data-api.ecb.europa.eu/service/data"


def _period_to_date(p: str) -> date | None:
    """Acepta 'YYYY-MM', 'YYYY-Qn', 'YYYY'. Devuelve primer día del periodo."""
    p = p.strip()
    try:
        if "-Q" in p:
            y, q = p.split("-Q")
            return date(int(y), (int(q) - 1) * 3 + 1, 1)
        if "-" in p:
            y, m = p.split("-")[:2]
            return date(int(y), int(m), 1)
        return date(int(p), 1, 1)
    except (ValueError, IndexError):
        return None


def get_series(flow_and_key: str) -> Series:
    """`flow_and_key` ej.: 'YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y'."""
    url = f"{BASE}/{flow_and_key}"
    r = get(url, {"format": "csvdata"})
    obs: list[Obs] = []
    reader = csv.DictReader(io.StringIO(r.text))
    for row in reader:
        p = _period_to_date(row.get("TIME_PERIOD", ""))
        raw = row.get("OBS_VALUE", "")
        if p is None or raw in ("", "NaN", None):
            continue
        try:
            obs.append(Obs(p, float(raw)))
        except ValueError:
            continue
    return Series(flow_and_key, "ecb", obs).clean()
