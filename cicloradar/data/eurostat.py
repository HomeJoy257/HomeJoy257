"""
Cliente Eurostat dissemination API (JSON-stat) — confirmación, SIN vintage.

Sirve el ESI (Economic Sentiment Indicator) para España. Endpoint:
  https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/{dataset}

JSON-stat codifica las dimensiones como índices; reconstruimos la dimensión
temporal a partir de `dimension.time.category.index`.
"""

from __future__ import annotations

from datetime import date

from .base import Obs, Series
from .http import get

BASE = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"


def _period_to_date(p: str) -> date | None:
    p = p.strip()
    try:
        if "M" in p:                 # 2008M03
            y, m = p.split("M")
            return date(int(y), int(m), 1)
        if "Q" in p:                 # 2008Q1
            y, q = p.split("Q")
            return date(int(y), (int(q) - 1) * 3 + 1, 1)
        return date(int(p), 1, 1)
    except (ValueError, IndexError):
        return None


def get_series(dataset: str, filters: dict[str, str]) -> Series:
    """`filters` ej.: {'geo': 'ES', 'indic': 'BS-ESI-I', 's_adj': 'SA'}."""
    params = {"format": "JSON", "lang": "EN", **filters}
    payload = get(f"{BASE}/{dataset}", params).json()

    time_dim = payload["dimension"]["time"]["category"]["index"]  # {period: idx}
    idx_to_period = {v: k for k, v in time_dim.items()}
    values = payload.get("value", {})  # {flat_index_str: value}

    # Con una sola serie filtrada, el índice plano coincide con el índice de tiempo.
    obs: list[Obs] = []
    for flat_idx_str, val in values.items():
        period = idx_to_period.get(int(flat_idx_str))
        d = _period_to_date(period) if period else None
        if d is None or val is None:
            continue
        try:
            obs.append(Obs(d, float(val)))
        except (TypeError, ValueError):
            continue
    return Series(dataset, "eurostat", obs).clean()
