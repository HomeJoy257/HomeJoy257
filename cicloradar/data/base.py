"""
Tipos base de datos y utilidades de LIMPIEZA (señal sin ruido).

Una `Series` es una secuencia ordenada de `Obs` (fecha -> valor). El objetivo
de este módulo es que lo que sale del data layer esté ya limpio: orden temporal,
sin duplicados, sin sentinelas tipo "." o NaN, frecuencia normalizada a fin de
mes, y con el tramo afectado por rupturas estructurales ya tratado.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Obs:
    period: date   # normalizada a primer día del mes
    value: float


@dataclass
class Series:
    series_id: str
    provider: str
    obs: list[Obs] = field(default_factory=list)
    meta: dict = field(default_factory=dict)

    # --- construcción / limpieza ---------------------------------------- #
    def clean(self) -> "Series":
        """Devuelve una copia limpia: sin NaN/inf, ordenada, sin duplicados
        (último valor gana), periodos a primer día de mes."""
        by_period: dict[date, float] = {}
        for o in self.obs:
            if o.value is None:
                continue
            if isinstance(o.value, float) and (math.isnan(o.value) or math.isinf(o.value)):
                continue
            by_period[_month_floor(o.period)] = o.value
        cleaned = [Obs(p, by_period[p]) for p in sorted(by_period)]
        return Series(self.series_id, self.provider, cleaned, dict(self.meta))

    def to_monthly(self) -> "Series":
        """Lleva una serie (posiblemente trimestral) a frecuencia mensual por
        forward-fill determinista: cada mes hereda el último valor publicado.
        No interpola — evita introducir ruido sintético."""
        s = self.clean()
        if not s.obs:
            return s
        out: list[Obs] = []
        cur = s.obs[0].period
        end = s.obs[-1].period
        idx = 0
        last = s.obs[0].value
        while cur <= end:
            while idx < len(s.obs) and s.obs[idx].period <= cur:
                last = s.obs[idx].value
                idx += 1
            out.append(Obs(cur, last))
            cur = _month_add(cur, 1)
        return Series(s.series_id, s.provider, out, dict(s.meta))

    def values(self) -> list[float]:
        return [o.value for o in self.obs]

    def periods(self) -> list[date]:
        return [o.period for o in self.obs]

    def as_of(self, d: date) -> "Series":
        """Recorta a observaciones con periodo <= d (no point-in-time real,
        solo recorte temporal; el point-in-time lo da ALFRED en el fetch)."""
        return Series(self.series_id, self.provider,
                      [o for o in self.obs if o.period <= d], dict(self.meta))

    def latest(self) -> Obs | None:
        return self.obs[-1] if self.obs else None


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def _month_add(d: date, n: int) -> date:
    m = d.month - 1 + n
    y = d.year + m // 12
    return date(y, m % 12 + 1, 1)


def align(a: Series, b: Series) -> tuple[list[date], list[float], list[float]]:
    """Intersección temporal de dos series ya mensuales. Devuelve periodos
    comunes y los valores alineados — base para spreads sin ruido."""
    ma = {o.period: o.value for o in a.obs}
    mb = {o.period: o.value for o in b.obs}
    common = sorted(set(ma) & set(mb))
    return common, [ma[p] for p in common], [mb[p] for p in common]


def spread(a: Series, b: Series) -> Series:
    """Serie a - b sobre periodos comunes."""
    common, va, vb = align(a, b)
    return Series(f"{a.series_id}-{b.series_id}", "derived",
                  [Obs(p, x - y) for p, x, y in zip(common, va, vb)])


def ratio(a: Series, b: Series, scale: float = 100.0) -> Series:
    """Serie (a / b) * scale sobre periodos comunes (p.ej. deflactar)."""
    common, va, vb = align(a, b)
    return Series(f"{a.series_id}/{b.series_id}", "derived",
                  [Obs(p, (x / y) * scale) for p, x, y in zip(common, va, vb) if y])
