"""
Dataset DEMO determinista (offline). No es dato real: sirve para demostrar que
el pipeline produce señal limpia sin depender de la red (egress bloqueado en
este entorno). Genera series mensuales 1999-2026 con deterioro alrededor de los
picos CFC en rango (2008, 2011, 2020).

NO usar para decisiones. Para datos reales: `cli run` con egress habilitado.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date

from ..constants.series_registry import INDICATORS
from .base import Obs, Series

_START = date(1999, 1, 1)
_END = date(2026, 5, 1)

# Centros de estrés (picos CFC en rango) y su anchura en meses.
_STRESS = [(date(2008, 4, 1), 14), (date(2011, 7, 1), 16), (date(2020, 2, 1), 5)]


def _months(a: date, b: date) -> list[date]:
    out, cur = [], a
    while cur <= b:
        out.append(cur)
        m = cur.month % 12 + 1
        y = cur.year + (1 if cur.month == 12 else 0)
        cur = date(y, m, 1)
    return out


def _stress(d: date) -> float:
    """0..1 según cercanía a un pico de recesión (campana gaussiana)."""
    s = 0.0
    for center, width in _STRESS:
        dm = (d.year - center.year) * 12 + (d.month - center.month)
        s = max(s, math.exp(-(dm ** 2) / (2 * width ** 2)))
    return s


def _wave(d: date, period: int, phase: float) -> float:
    idx = (d.year - 1999) * 12 + d.month
    return math.sin(2 * math.pi * idx / period + phase)


def _series_for(key: str, periods: list[date]) -> Series:
    """Forma base + componente de estrés según el signo del indicador.

    Para `direction=+1` (alto=riesgo) el estrés SUBE el valor; para `-1`
    (alto=protege) el estrés lo BAJA.
    """
    base = {
        "euro_curve": (1.5, -1),        # pendiente cae (se aplana) en estrés
        "spain_risk_premium": (0.6, +1),
        "bls": (5.0, +1),
        "hy_spread": (3.5, +1),
        "esi": (100.0, -1),
        "visados": (12000.0, -1),
        "ibex": (10000.0, -1),
        "real_m1": (100.0, -1),
    }
    level, sign = base[key]
    amp = abs(level) * 0.6 + 1.0
    # Fase fija por indicador con hash ESTABLE (hash() está salado por proceso).
    seed = int(hashlib.md5(key.encode()).hexdigest(), 16) % 100
    phase = seed / 100 * 6.283
    out = []
    for d in periods:
        s = _stress(d)
        cyc = 0.08 * amp * _wave(d, 54, phase)      # ruido cíclico suave
        # El estrés DOMINA y va con la dirección del indicador: para sign=+1
        # (alto=riesgo) sube el valor; para sign=-1 (alto=protege) lo baja.
        stress_term = sign * amp * 2.5 * s
        val = level + cyc + stress_term
        out.append(Obs(d, round(val, 4)))
    return Series(key, "demo", out).clean()


def demo_series() -> dict[str, Series]:
    """Dataset demo que pasa por la MISMA política de ruptura que el fetch real,
    para que la ruta offline sea fiel al pipeline en vivo (FR-02)."""
    from .fetcher import apply_break_policy
    periods = _months(_START, _END)
    raw = {ind.key: _series_for(ind.key, periods) for ind in INDICATORS}
    series, _log = apply_break_policy(raw)
    return series
