"""
FragilidadRadar — Índice de FRAGILIDAD del hogar español (0-100).

Complemento de CicloRadar. No mide *cuándo* llega la recesión (eso es el radar
de ciclo), sino *cuánto dolería* si llega: cuán expuesto está el hogar medio.

  CicloRadar    -> ¿viene el ciclo?      (condiciones de crédito, momentum)
  FragilidadR.  -> ¿cómo de expuesto?    (deuda, ahorro, inflación, consumo)

100% determinista. Cada eje se ancla entre una referencia SANA y la de CRISIS
2008, y se coloca el valor real de hoy en esa escala 0-100. Anclas = referencias
documentadas (NO optimizadas): hard block intacto.

INDEPENDENCIA DE LA FUENTE (decisión de diseño): los datos del gobierno español
(INE, Banco de España) pueden tener sesgo de interés político. Por eso el sistema
PRIORIZA fuentes independientes:
  - INDEPENDIENTE : BIS (Basilea), datos de MERCADO (precios, spreads) -> no cocinables.
  - SUPRANACIONAL : ECB / Eurostat -> armonizado por la UE, no por Madrid.
  - NACIONAL ⚠️    : INE / BdE -> marcado; se usa solo si no hay alternativa, y
                     se contrasta con una señal de mercado.

La defensa más fuerte contra el dato cocinado son los PRECIOS DE MERCADO (prima
de riesgo, spread HY): si el gobierno maquilla cuentas, el mercado lo refleja en
el coste de financiación. CicloRadar ya los usa; aquí entran como contraste.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Independence(str, Enum):
    MARKET = "mercado · no cocinable"
    INDEPENDENT = "independiente (BIS)"
    SUPRANATIONAL = "supranacional (ECB/Eurostat)"
    NATIONAL = "nacional ⚠️ (INE/BdE)"


@dataclass(frozen=True)
class Axis:
    key: str
    name: str
    today: float
    ref_2008: float
    healthy: float        # ancla "sano" -> fragilidad 0
    crisis: float         # ancla "crisis" -> fragilidad 100
    unit: str
    as_of: str
    source: str
    independence: Independence
    note: str = ""

    def score(self, value: float | None = None) -> float:
        v = self.today if value is None else value
        denom = (self.crisis - self.healthy)
        if denom == 0:
            return 0.0
        s = (v - self.healthy) / denom * 100.0
        return round(max(0.0, min(100.0, s)), 1)


# --------------------------------------------------------------------------- #
#  Snapshot REAL, re-anclado a fuentes INDEPENDIENTES (sin BdE/INE de cabecera)
# --------------------------------------------------------------------------- #
AXES: list[Axis] = [
    Axis(
        key="dsr",
        name="Carga financiera (deuda/renta, DSR)",
        today=5.3, ref_2008=11.6, healthy=5.3, crisis=11.6,
        unit="% renta disponible", as_of="2024 (último BIS)",
        source="BIS — Debt Service Ratio (hogares ES)",
        independence=Independence.INDEPENDENT,
        note="Mínimo histórico. Hoy se destina la mitad que en 2008 a pagar deuda.",
    ),
    Axis(
        key="hicp",
        name="Inflación (HICP armonizado UE)",
        today=2.7, ref_2008=5.1, healthy=2.0, crisis=5.1,
        unit="% interanual", as_of="2025 (media, Eurostat)",
        source="Eurostat — HICP España (no el IPC del INE)",
        independence=Independence.SUPRANATIONAL,
        note="Armonizado por Eurostat. Por encima del 2% pero lejos del pico 2008.",
    ),
    Axis(
        key="ahorro",
        name="Tasa de ahorro de los hogares",
        today=12.0, ref_2008=13.4, healthy=18.0, crisis=5.0,
        unit="% renta disp. bruta", as_of="2025 (Eurostat sector accounts)",
        source="Eurostat — cuentas de sectores (armonizado)",
        independence=Independence.SUPRANATIONAL,
        note="Menos ahorro = menos colchón. Dato base nacional, agregado por Eurostat.",
    ),
    Axis(
        key="credito_consumo",
        name="Crédito al consumo (crecim. saldo)",
        today=8.0, ref_2008=12.0, healthy=0.0, crisis=12.0,
        unit="% interanual saldo (ECB BSI)", as_of="2025 (ECB)",
        source="ECB — préstamos al consumo a hogares (BSI), no prensa BdE",
        independence=Independence.SUPRANATIONAL,
        note=("Crecimiento del SALDO (ECB), más estable que el flujo de prensa. "
              "El flujo nuevo va a máximos de 2008, pero el saldo crece menos."),
    ),
    # Contraste de MERCADO — no cocinable. Valida si los datos oficiales 'mienten'.
    Axis(
        key="risk_premium",
        name="Prima de riesgo ES (mercado)",
        today=0.65, ref_2008=0.80, healthy=0.20, crisis=4.00,
        unit="ES10y − Bund (p.p.)", as_of="2025 (mercado)",
        source="Mercado — bono ES 10y vs Bund (FRED/ECB)",
        independence=Independence.MARKET,
        note=("Precio real: si el gobierno cocina cuentas, el mercado lo cobra. "
              "Hoy contenida -> el mercado NO ve estrés soberano agudo."),
    ),
]


@dataclass
class FragilityResult:
    index: int
    index_2008: int
    axis_scores: dict[str, float]
    axis_scores_2008: dict[str, float]


def compute() -> FragilityResult:
    today = {a.key: a.score() for a in AXES}
    y2008 = {a.key: a.score(a.ref_2008) for a in AXES}
    idx = round(sum(today.values()) / len(today))
    idx08 = round(sum(y2008.values()) / len(y2008))
    return FragilityResult(int(idx), int(idx08), today, y2008)


def render() -> str:
    r = compute()

    def bar(score: float, width: int = 16) -> str:
        f = round(score / 100 * width)
        return "█" * f + "░" * (width - f)

    L = ["═" * 72,
         "  FragilidadRadar · Exposición del hogar español (0-100)",
         "═" * 72,
         f"  ÍNDICE HOY     : {r.index}/100",
         f"  Referencia 2008: {r.index_2008}/100",
         "─" * 72,
         f"  {'Eje':<36}{'hoy':>6}{'2008':>6}  fragilidad", "─" * 72]
    for a in AXES:
        sc = r.axis_scores[a.key]
        L.append(f"  {a.name:<36}{a.today:>6.2f}{a.ref_2008:>6.2f}  {bar(sc)} {sc:>5.1f}")
        L.append(f"      ↳ {a.independence.value} · {a.source} · {a.as_of}")
    L.append("─" * 72)
    worst = max(AXES, key=lambda a: r.axis_scores[a.key])
    best = min(AXES, key=lambda a: r.axis_scores[a.key])
    ratio = r.index / r.index_2008 if r.index_2008 else 0
    L.append(f"  Eje más tensionado : {worst.name} ({r.axis_scores[worst.key]:.0f})")
    L.append(f"  Eje más sano       : {best.name} ({r.axis_scores[best.key]:.0f})")
    L.append(f"  Lectura            : fragilidad hoy ≈ {ratio:.0%} de la de 2008.")
    L.append("─" * 72)
    L.append("  Fuentes priorizadas: BIS / Eurostat / ECB / MERCADO. INE/BdE evitados.")
    L.append("  Anclas = referencias documentadas (sano/crisis-2008), NO optimizadas.")
    L.append("═" * 72)
    return "\n".join(L)
