"""
Motor de ALERTA (FR-04). 3 estados con doble gatillo y persistencia.

Estados: VERDE / ÁMBAR / ROJO.
Gatillo por NIVEL:        index >= umbral (ámbar p80, rojo p90).
Gatillo por ACELERACIÓN:  Δindex (mes a mes) >= umbral de cambio.
Persistencia:             ROJO exige 2 lecturas consecutivas en condición roja;
                          ÁMBAR se dispara con 1.

Los umbrales son percentiles de la distribución del propio índice (no valores
absolutos ni optimizados). Como el índice YA es percentil 0-100, p80=80 y p90=90.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..config import settings
from .aggregate import IndexPoint


class State(str, Enum):
    GREEN = "VERDE"
    AMBER = "ÁMBAR"
    RED = "ROJO"


@dataclass
class Alert:
    state: State
    index: int
    delta: float | None              # aceleración (Δ índice vs mes anterior)
    coverage: float
    trigger: str                     # "nivel" | "aceleración" | "nivel+aceleración" | "-"
    reason: str


def _condition(index: int, delta: float | None, level_thr: float,
               accel_thr: float) -> tuple[bool, str]:
    by_level = index >= level_thr
    by_accel = delta is not None and delta >= accel_thr
    if by_level and by_accel:
        return True, "nivel+aceleración"
    if by_level:
        return True, "nivel"
    if by_accel:
        return True, "aceleración"
    return False, "-"


def states_timeline(history: list[IndexPoint]):
    """Corre la máquina de estados HACIA ADELANTE y devuelve el estado en CADA
    periodo (para backtest). Misma lógica que `evaluate` pero acumulando la
    racha roja en orden temporal."""
    from datetime import date  # local
    out: list[tuple[date, State, str]] = []
    red_streak = 0
    for i, pt in enumerate(history):
        prev = history[i - 1] if i >= 1 else None
        delta = (pt.index - prev.index) if prev else None
        red_now, red_trig = _condition(pt.index, delta, settings.red_level, settings.red_accel)
        amber_now, amber_trig = _condition(pt.index, delta, settings.amber_level, settings.amber_accel)
        red_streak = red_streak + 1 if red_now else 0
        if red_streak >= settings.red_persistence:
            out.append((pt.period, State.RED, red_trig))
        elif amber_now:
            out.append((pt.period, State.AMBER, amber_trig))
        else:
            out.append((pt.period, State.GREEN, "-"))
    return out


def evaluate(history: list[IndexPoint]) -> Alert:
    """Evalúa el estado en la última lectura, usando la historia para la
    persistencia (ROJO necesita N consecutivas)."""
    if not history:
        return Alert(State.GREEN, 0, None, 0.0, "-", "sin datos")

    last = history[-1]
    prev = history[-2] if len(history) >= 2 else None
    delta = (last.index - prev.index) if prev else None

    # ¿condición roja en las últimas N lecturas?
    def red_cond(pt: IndexPoint, pv: IndexPoint | None) -> bool:
        d = (pt.index - pv.index) if pv else None
        ok, _ = _condition(pt.index, d, settings.red_level, settings.red_accel)
        return ok

    red_streak = 0
    for i in range(len(history) - 1, -1, -1):
        pv = history[i - 1] if i >= 1 else None
        if red_cond(history[i], pv):
            red_streak += 1
        else:
            break

    red_now, red_trig = _condition(last.index, delta, settings.red_level, settings.red_accel)
    amber_now, amber_trig = _condition(last.index, delta, settings.amber_level, settings.amber_accel)

    if red_now and red_streak >= settings.red_persistence:
        return Alert(State.RED, last.index, delta, last.coverage, red_trig,
                     f"ROJO: {red_trig} ≥ umbral en {red_streak} lecturas consecutivas.")
    if amber_now:
        # Roja pero aún sin persistencia -> se queda en ÁMBAR (vigilancia).
        extra = " (condición roja, esperando 2ª lectura)" if red_now else ""
        return Alert(State.AMBER, last.index, delta, last.coverage, amber_trig,
                     f"ÁMBAR: {amber_trig} ≥ umbral{extra}.")
    return Alert(State.GREEN, last.index, delta, last.coverage, "-",
                 "VERDE: sin gatillos por nivel ni aceleración.")
