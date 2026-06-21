"""
Motor de AGREGACIÓN (FR-01 + FR-03). 100% reglas y aritmética.

Pipeline determinista:
  1. Orientar cada indicador: oriented = direction * valor  -> "más alto = más
     riesgo" SIEMPRE.
  2. level_score(t)    = percentil del valor orientado en su propia historia.
     momentum_score(t) = percentil del Δ orientado (ventana OQ-05) en su historia.
     indicator_score   = level_w*level + momentum_w*momentum.
  3. block_score(t)    = media de los indicadores VIVOS del bloque en t.
  4. raw_composite(t)  = media ponderada de bloques (1/5 c/u) RENORMALIZADA por
     los bloques vivos en t (los pesos siempre suman 1).
  5. index(t)          = percentil de raw_composite(t) sobre su rango histórico
     (0 = mejor lectura, 100 = peor). FR-01.
  6. coverage(t)       = bloques con dato / 5.  (Un 80 con 5/5 != un 80 con 2/5.)

PROHIBIDO optimizar pesos o umbrales (hard block).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from ..config import settings
from ..constants.series_registry import (BLOCK_WEIGHT, Block, INDICATORS,
                                         Indicator, N_BLOCKS, get_indicator)
from ..data.base import Series
from .percentile import momentum, percentile_rank


@dataclass
class IndicatorScore:
    key: str
    name: str
    block: str
    available: bool
    level_score: float | None = None
    momentum_score: float | None = None
    score: float | None = None        # 0-100, "más alto = más riesgo"


@dataclass
class IndexPoint:
    period: date
    index: int                         # 0-100 (FR-01)
    raw_composite: float
    blocks_available: int
    coverage: float                    # blocks_available / N_BLOCKS
    block_scores: dict[str, float | None] = field(default_factory=dict)
    indicators: dict[str, IndicatorScore] = field(default_factory=dict)

    def drivers(self, top: int = 3) -> list[tuple[str, float]]:
        """Bloques que más tiran de la señal (score más alto)."""
        live = [(b, s) for b, s in self.block_scores.items() if s is not None]
        return sorted(live, key=lambda kv: kv[1], reverse=True)[:top]

    def top_indicators(self, top: int = 3) -> list[IndicatorScore]:
        live = [i for i in self.indicators.values() if i.score is not None]
        return sorted(live, key=lambda i: i.score, reverse=True)[:top]


# --------------------------------------------------------------------------- #
def _indicator_score_timeline(ind: Indicator, s: Series, window: int
                              ) -> dict[date, IndicatorScore]:
    """Calcula el score del indicador para cada periodo de su serie."""
    oriented = [ind.direction * v for v in s.values()]
    periods = s.periods()

    # percentiles de nivel: cada punto contra TODA la historia del indicador.
    level_scores = [percentile_rank(v, oriented) for v in oriented]

    # momentum y sus percentiles.
    mom = momentum(oriented, window)
    mom_clean = [m for m in mom if m is not None]
    mom_scores: list[float | None] = [
        (percentile_rank(m, mom_clean) if m is not None else None) for m in mom
    ]

    out: dict[date, IndicatorScore] = {}
    for i, p in enumerate(periods):
        lv = level_scores[i]
        mv = mom_scores[i]
        if ind.momentum_weight > 0 and mv is None:
            # sin base de momentum aún: cae a nivel puro para no inventar señal.
            score = lv
            mv_used = None
        else:
            score = ind.level_weight * lv + ind.momentum_weight * (mv or 0.0)
        out[p] = IndicatorScore(
            key=ind.key, name=ind.name, block=ind.block.value, available=True,
            level_score=round(lv, 2),
            momentum_score=(round(mv, 2) if mv is not None else None),
            score=round(score, 2),
        )
    return out


def compute(series: dict[str, Series], window: int | None = None) -> list[IndexPoint]:
    """Devuelve la historia completa del índice (un IndexPoint por periodo)."""
    window = window or settings.momentum_window_months

    # 1-2. score por indicador y periodo.
    per_ind: dict[str, dict[date, IndicatorScore]] = {}
    for ind in INDICATORS:
        s = series.get(ind.key)
        if s and len(s.obs) > window:
            per_ind[ind.key] = _indicator_score_timeline(ind, s, window)

    # Línea temporal: unión de todos los periodos con algún indicador.
    all_periods = sorted({p for d in per_ind.values() for p in d})

    # 3-4. compose raw por periodo.
    raw_points: list[tuple[date, float, int, dict, dict]] = []
    for p in all_periods:
        block_vals: dict[str, list[float]] = {}
        ind_scores: dict[str, IndicatorScore] = {}
        for ind in INDICATORS:
            sc = per_ind.get(ind.key, {}).get(p)
            if sc and sc.score is not None:
                block_vals.setdefault(ind.block.value, []).append(sc.score)
                ind_scores[ind.key] = sc
            else:
                ind_scores[ind.key] = IndicatorScore(
                    ind.key, ind.name, ind.block.value, available=False)
        block_scores: dict[str, float | None] = {b.value: None for b in Block}
        for b, vals in block_vals.items():
            block_scores[b] = round(sum(vals) / len(vals), 2)

        live_blocks = [v for v in block_scores.values() if v is not None]
        n_live = len(live_blocks)
        if n_live < settings.min_blocks_for_index:
            continue  # cobertura insuficiente para emitir
        # renormalización: pesos iguales entre bloques vivos.
        raw = sum(live_blocks) / n_live
        raw_points.append((p, raw, n_live, block_scores, ind_scores))

    # 5. índice = percentil del compuesto sobre su rango histórico.
    raw_values = [rp[1] for rp in raw_points]
    history: list[IndexPoint] = []
    for (p, raw, n_live, block_scores, ind_scores) in raw_points:
        idx = round(percentile_rank(raw, raw_values))
        history.append(IndexPoint(
            period=p, index=int(idx), raw_composite=round(raw, 3),
            blocks_available=n_live, coverage=round(n_live / N_BLOCKS, 2),
            block_scores=block_scores, indicators=ind_scores,
        ))
    return history
