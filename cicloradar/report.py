"""
Render de informe LIMPIO en consola (señal sin ruido).

Una sola tabla con: índice, estado, cobertura y la descomposición por bloque e
indicador (nivel / momentum / score). Sin dependencias de terminal.
"""

from __future__ import annotations

from .constants.series_registry import Block, indicators_by_block
from .data.fetcher import FetchResult
from .engine.aggregate import IndexPoint
from .engine.alert import Alert

_STATE_EMOJI = {"VERDE": "🟢", "ÁMBAR": "🟡", "ROJO": "🔴"}


def _bar(score: float | None, width: int = 20) -> str:
    if score is None:
        return "·" * width + "  n/d"
    filled = round(score / 100 * width)
    return "█" * filled + "░" * (width - filled) + f"  {score:5.1f}"


def render(pt: IndexPoint, alert: Alert, fetch: FetchResult | None = None) -> str:
    L: list[str] = []
    em = _STATE_EMOJI.get(alert.state.value, "")
    L.append("═" * 64)
    L.append(f"  CicloRadar · Índice de riesgo de recesión (España)")
    L.append("═" * 64)
    L.append(f"  Periodo            : {pt.period.isoformat()}")
    L.append(f"  ÍNDICE             : {pt.index}/100   {em} {alert.state.value}")
    delta = f"{alert.delta:+.0f}" if alert.delta is not None else "n/d"
    L.append(f"  Aceleración (Δ)    : {delta}   ·   gatillo: {alert.trigger}")
    L.append(f"  Cobertura          : {pt.blocks_available}/5 bloques "
             f"({pt.coverage:.0%})")
    L.append(f"  Compuesto bruto    : {pt.raw_composite}")
    L.append("─" * 64)
    L.append("  DESCOMPOSICIÓN POR BLOQUE  (más alto = más riesgo)")
    L.append("─" * 64)

    by_block = indicators_by_block()
    for block in Block:
        bscore = pt.block_scores.get(block.value)
        L.append(f"  ▸ {block.value:<20} {_bar(bscore)}")
        for ind in by_block[block]:
            sc = pt.indicators.get(ind.key)
            if sc and sc.available:
                lv = f"{sc.level_score:.0f}" if sc.level_score is not None else "·"
                mo = f"{sc.momentum_score:.0f}" if sc.momentum_score is not None else "·"
                L.append(f"      - {ind.name:<34} "
                         f"score {sc.score:5.1f}  (niv {lv} / mom {mo})")
            else:
                L.append(f"      - {ind.name:<34} {'SIN DATO':>16}")
    L.append("─" * 64)
    L.append("  QUÉ TIRA DE LA SEÑAL")
    L.append("─" * 64)
    for name, score in pt.drivers(top=3):
        L.append(f"    • {name}: {score:.0f}")
    L.append("")
    L.append(f"  {alert.reason}")

    if fetch and (fetch.break_log or fetch.errors):
        L.append("─" * 64)
        if fetch.break_log:
            L.append("  RUPTURAS ESTRUCTURALES APLICADAS:")
            for d in fetch.break_log:
                L.append(f"    • {d.indicator} [{d.policy}] {d.break_date}: {d.reason}")
        if fetch.errors:
            L.append("  INDICADORES NO DISPONIBLES:")
            for k, e in fetch.errors.items():
                L.append(f"    • {k}: {e}")
    L.append("═" * 64)
    return "\n".join(L)
