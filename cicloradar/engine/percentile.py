"""Percentiles deterministas en Python puro (sin numpy: stack mínimo)."""

from __future__ import annotations

import bisect


def percentile_rank(x: float, sample: list[float]) -> float:
    """Percentil (0-100) de `x` dentro de `sample`: % de la muestra <= x.

    Determinista y estable. Con muestra vacía devuelve 50 (neutro).
    """
    if not sample:
        return 50.0
    s = sorted(sample)
    # nº de elementos <= x
    cnt = bisect.bisect_right(s, x)
    return 100.0 * cnt / len(s)


def momentum(values: list[float], window: int) -> list[float | None]:
    """Δ sobre `window` periodos: v[t] - v[t-window]. Los primeros `window`
    quedan None (sin base de comparación)."""
    out: list[float | None] = []
    for i in range(len(values)):
        if i < window:
            out.append(None)
        else:
            out.append(values[i] - values[i - window])
    return out
