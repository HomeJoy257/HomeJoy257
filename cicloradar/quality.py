"""
Harness de CALIDAD (QA) autónomo de CicloRadar.

Verifica que el resultado del índice es BUENO mediante una batería de "gates"
deterministas y un BACKTEST contra la cronología CFC:

  G1 Bounds        — índice en [0,100], cobertura válida en todo punto.
  G2 Determinismo  — recomputar dos veces da exactamente lo mismo.
  G3 Momentum      — la comprobación a mano del motor de momentum cuadra.
  G4 Rupturas      — la política de ruptura se aplicó (p.ej. visados sin pre-2008).
  G5 Discriminación— el índice es, en media, más alto en ventanas pre-recesión.
  G6 Backtest      — recall (recesiones avisadas con ÁMBAR+) y tasa de falsas
                     alarmas dentro de criterios de aceptación.

Pensado para correr en BUCLE (cron/intervalo o `qa --loop N`): sale con código
!=0 si algún gate crítico falla, para encadenar con alertas/CI.

NOTA: los umbrales de aceptación de QA (recall objetivo, máx. falsas alarmas)
NO son parámetros del modelo — son criterios de CALIDAD del propio QA. El índice
sigue sin optimizarse contra el histórico (hard block intacto).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from .constants.cfc_chronology import CFC_RECESSIONS, recession_peaks
from .engine.aggregate import IndexPoint, compute
from .engine.alert import State, states_timeline

# Ventana de aviso aceptable alrededor del pico: hasta 12 meses ANTES y 3 DESPUÉS.
LEAD_BEFORE = 12
LAG_AFTER = 3

# Criterios de aceptación del QA (no del modelo).
TARGET_RECALL = 2 / 3          # avisar al menos 2 de cada 3 recesiones cubiertas
MAX_FALSE_ALARM_RATE = 0.35    # máx. fracción de meses tranquilos en falsa alarma
MIN_DISCRIMINATION = 3.0       # puntos de índice de diferencia media (pre vs calma)


@dataclass
class Gate:
    name: str
    passed: bool
    detail: str
    critical: bool = True


@dataclass
class QAReport:
    gates: list[Gate] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return all(g.passed for g in self.gates if g.critical)

    @property
    def score(self) -> float:
        """0-100: % de gates superados, ponderando críticos doble."""
        num = sum((2 if g.critical else 1) * (1 if g.passed else 0) for g in self.gates)
        den = sum(2 if g.critical else 1 for g in self.gates)
        return round(100 * num / den, 1) if den else 0.0


def _months_diff(a: date, b: date) -> int:
    return (a.year - b.year) * 12 + (a.month - b.month)


def _in_pre_window(p: date, peaks: list[date]) -> bool:
    return any(-LEAD_BEFORE <= _months_diff(p, pk) <= LAG_AFTER for pk in peaks)


def _covered_peaks(history: list[IndexPoint]) -> list[date]:
    """Picos CFC cuyo entorno cae dentro del rango de datos (con margen de lead)."""
    if not history:
        return []
    start, end = history[0].period, history[-1].period
    out = []
    for pk in recession_peaks():
        # necesitamos al menos parte de la ventana pre-pico dentro de los datos
        if pk >= start and _months_diff(end, pk) >= -LAG_AFTER and \
           _months_diff(pk, start) >= 0:
            out.append(pk)
    return out


def backtest(history: list[IndexPoint]) -> dict:
    """Recall, falsas alarmas y lead time del índice contra las recesiones CFC."""
    peaks = _covered_peaks(history)
    states = {p: s for p, s, _ in states_timeline(history)}
    alarm = {p for p, s in states.items() if s in (State.AMBER, State.RED)}

    # Recall + lead time por recesión cubierta.
    hits, leads = 0, []
    per_recession = []
    for pk in peaks:
        window = [p for p in states
                  if -LEAD_BEFORE <= _months_diff(p, pk) <= LAG_AFTER]
        win_alarms = sorted(p for p in window if p in alarm)
        hit = bool(win_alarms)
        hits += int(hit)
        lead = _months_diff(pk, win_alarms[0]) if hit else None  # +meses de antelación
        if lead is not None:
            leads.append(lead)
        per_recession.append({"peak": pk.isoformat(), "hit": hit, "lead_months": lead})

    recall = hits / len(peaks) if peaks else 0.0

    # Falsas alarmas: meses en alarma fuera de cualquier ventana pre-recesión.
    calm = [p for p in states if not _in_pre_window(p, peaks)]
    false_alarms = [p for p in calm if p in alarm]
    fa_rate = len(false_alarms) / len(calm) if calm else 0.0

    return {
        "covered_recessions": len(peaks),
        "recall": round(recall, 3),
        "hits": hits,
        "median_lead_months": (sorted(leads)[len(leads) // 2] if leads else None),
        "false_alarm_rate": round(fa_rate, 3),
        "alarm_months": len(alarm),
        "per_recession": per_recession,
    }


def discrimination(history: list[IndexPoint]) -> float:
    peaks = _covered_peaks(history)
    inside = [pt.index for pt in history if _in_pre_window(pt.period, peaks)]
    outside = [pt.index for pt in history if not _in_pre_window(pt.period, peaks)]
    if not inside or not outside:
        return 0.0
    return sum(inside) / len(inside) - sum(outside) / len(outside)


def run_qa(series: dict) -> QAReport:
    r = QAReport()
    history = compute(series)

    # G1 — bounds
    bad = [pt.period.isoformat() for pt in history
           if not (0 <= pt.index <= 100 and 1 <= pt.blocks_available <= 5)]
    r.gates.append(Gate("G1 Bounds", not bad,
                        "todos los puntos dentro de rango" if not bad
                        else f"fuera de rango: {bad[:3]}"))

    # G2 — determinismo
    h2 = compute(series)
    same = [pt.index for pt in history] == [pt.index for pt in h2]
    r.gates.append(Gate("G2 Determinismo", same,
                        "dos cómputos idénticos" if same else "¡resultado no determinista!"))

    # G3 — momentum
    try:
        from . import verify
        verify.hand_check()
        r.gates.append(Gate("G3 Momentum", True, "comprobación a mano OK"))
    except AssertionError as e:  # noqa: BLE001
        r.gates.append(Gate("G3 Momentum", False, f"falla: {e}"))

    # G4 — rupturas estructurales aplicadas
    vis = series.get("visados")
    pre2008 = bool(vis and any(o.period < date(2008, 1, 1) for o in vis.obs))
    r.gates.append(Gate("G4 Rupturas", not pre2008,
                        "visados sin tramo pre-2008 (DROP_PRE aplicado)" if not pre2008
                        else "¡visados conserva tramo pre-ruptura!", critical=False))

    # G5 — discriminación
    disc = discrimination(history)
    r.metrics["discrimination"] = round(disc, 2)
    r.gates.append(Gate("G5 Discriminación", disc >= MIN_DISCRIMINATION,
                        f"índice medio pre-recesión − calma = {disc:.1f} pts "
                        f"(≥ {MIN_DISCRIMINATION})"))

    # G6 — backtest
    bt = backtest(history)
    r.metrics["backtest"] = bt
    ok_bt = (bt["recall"] >= TARGET_RECALL
             and bt["false_alarm_rate"] <= MAX_FALSE_ALARM_RATE)
    r.gates.append(Gate(
        "G6 Backtest", ok_bt,
        f"recall={bt['recall']} (≥{TARGET_RECALL:.2f}) · "
        f"falsas alarmas={bt['false_alarm_rate']} (≤{MAX_FALSE_ALARM_RATE}) · "
        f"lead mediano={bt['median_lead_months']}m"))

    r.metrics["n_periods"] = len(history)
    return r


def render(report: QAReport) -> str:
    L = ["═" * 60, "  CicloRadar · Informe de CALIDAD (QA)", "═" * 60]
    for g in report.gates:
        mark = "✅" if g.passed else "❌"
        crit = "" if g.critical else "  (no crítico)"
        L.append(f"  {mark} {g.name}{crit}")
        L.append(f"       {g.detail}")
    L.append("─" * 60)
    bt = report.metrics.get("backtest", {})
    if bt:
        L.append(f"  Recesiones cubiertas : {bt['covered_recessions']}")
        L.append(f"  Avisadas (ÁMBAR+)    : {bt['hits']}  ·  recall {bt['recall']}")
        L.append(f"  Lead mediano         : {bt['median_lead_months']} meses")
        L.append(f"  Falsas alarmas       : {bt['false_alarm_rate']}")
        for pr in bt.get("per_recession", []):
            mk = "✅" if pr["hit"] else "❌"
            lead = f"{pr['lead_months']}m antes" if pr["lead_months"] is not None else "no avisada"
            L.append(f"     {mk} pico {pr['peak']}: {lead}")
    L.append("─" * 60)
    L.append(f"  PUNTUACIÓN DE CALIDAD : {report.score}/100   "
             f"{'PASS ✅' if report.ok else 'FAIL ❌'}")
    L.append("═" * 60)
    return "\n".join(L)
