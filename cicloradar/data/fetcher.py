"""
Orquestador de extracción: de fuentes crudas a UN indicador limpio.

Para cada indicador del registro:
  1. descarga su(s) fuente(s),
  2. aplica el transform determinista (spread, deflactado real, etc.),
  3. aplica la política de RUPTURA ESTRUCTURAL (FR-02) y la LOGUEA,
  4. normaliza a mensual y limpia.

Devuelve {indicator_key: Series} más un log de decisiones de ruptura.
Nunca empalma a mano (hard block); solo aplica official_link / drop_pre /
drop_series.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from ..constants.series_registry import (Indicator, INDICATORS, Provider,
                                         Source)
from ..constants.structural_breaks import BreakPolicy, breaks_for
from . import ecb, eurostat, fred, ine
from .base import Obs, Series, spread

log = logging.getLogger("cicloradar.fetch")


@dataclass
class BreakDecision:
    indicator: str
    break_date: date | None
    policy: str
    reason: str


@dataclass
class FetchResult:
    series: dict[str, Series] = field(default_factory=dict)
    break_log: list[BreakDecision] = field(default_factory=list)
    errors: dict[str, str] = field(default_factory=dict)


# --------------------------------------------------------------------------- #
#  Descarga de una fuente individual
# --------------------------------------------------------------------------- #
def _fetch_source(src: Source) -> Series:
    if src.provider == Provider.FRED:
        return fred.get_series(src.series_id).to_monthly()
    if src.provider == Provider.ECB:
        return ecb.get_series(src.series_id).to_monthly()
    if src.provider == Provider.EUROSTAT:
        # ESI: dataset + filtros. El series_id es el dataset; filtros mínimos.
        return eurostat.get_series(
            src.series_id,
            {"geo": "ES", "indic": "BS-ESI-I", "s_adj": "SA"},
        ).to_monthly()
    if src.provider == Provider.INE:
        return ine.get_series(src.series_id).to_monthly()
    raise ValueError(f"Proveedor no soportado: {src.provider}")


# --------------------------------------------------------------------------- #
#  Transforms deterministas
# --------------------------------------------------------------------------- #
def _apply_transform(ind: Indicator) -> Series:
    if ind.transform in ("spread", "spread_es_de"):
        a = _fetch_source(ind.sources[0])
        b = _fetch_source(ind.sources[1])
        return spread(a, b).to_monthly()

    if ind.transform == "real_deflate":
        nominal = _fetch_source(ind.sources[0])
        deflator = _fetch_source(ind.deflator)
        from .base import ratio
        return ratio(nominal, deflator).to_monthly()

    # Sin transform: una sola fuente.
    return _fetch_source(ind.sources[0])


# --------------------------------------------------------------------------- #
#  Política de ruptura estructural (FR-02)
# --------------------------------------------------------------------------- #
def _apply_breaks(ind: Indicator, s: Series, log_out: list[BreakDecision]) -> Series | None:
    for b in breaks_for(ind.key):
        if b.policy == BreakPolicy.DROP_SERIES:
            log_out.append(BreakDecision(ind.key, b.break_date, b.policy.value, b.reason))
            return None
        if b.policy == BreakPolicy.DROP_PRE:
            s = Series(s.series_id, s.provider,
                       [o for o in s.obs if o.period >= b.break_date], dict(s.meta))
            log_out.append(BreakDecision(ind.key, b.break_date, b.policy.value, b.reason))
        elif b.policy == BreakPolicy.OFFICIAL_LINK:
            # El enlace oficial ya viene resuelto en la propia serie (Eurostat/
            # Eurostat HICP publican la serie homogénea). Solo se LOGUEA.
            log_out.append(BreakDecision(ind.key, b.break_date, b.policy.value, b.reason))
        elif b.policy == BreakPolicy.HOMEMADE_SPLICE:
            raise RuntimeError(f"HARD BLOCK: empalme casero prohibido en {ind.key}")
    return s


# --------------------------------------------------------------------------- #
#  API pública
# --------------------------------------------------------------------------- #
def fetch_all(indicators: list[Indicator] | None = None) -> FetchResult:
    indicators = indicators or INDICATORS
    res = FetchResult()
    for ind in indicators:
        try:
            s = _apply_transform(ind)
            s = _apply_breaks(ind, s, res.break_log)
            if s is None or not s.obs:
                res.errors[ind.key] = "sin datos tras política de ruptura"
                continue
            res.series[ind.key] = s.clean()
        except Exception as exc:  # noqa: BLE001
            res.errors[ind.key] = f"{type(exc).__name__}: {exc}"
            log.warning("Indicador %s falló: %s", ind.key, exc)
    return res
