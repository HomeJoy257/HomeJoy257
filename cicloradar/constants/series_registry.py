"""
Registro de SERIES e INDICADORES (FR-03 + OQ-04).

8 indicadores adelantados agrupados en 5 bloques temáticos. Cada BLOQUE pesa
1/5; reparto igual dentro del bloque (pesos por bloque, no por indicador, para
que la economía real no quede aplastada por las series financieras).

HARD BLOCK: los pesos son fijos. PROHIBIDO optimizarlos contra el histórico.

Cada indicador declara:
  - block            bloque temático (5 en total).
  - sources          1..N fuentes (series_id + proveedor). La primera con
                     vintage nativo es el backbone point-in-time; el resto son
                     confirmación (documentar sesgo de no-vintage).
  - direction        +1 si "valor alto = más riesgo de recesión";
                     -1 si "valor alto = menos riesgo" (se invierte el percentil).
  - level_weight /   reparto nivel vs momentum dentro del indicador (suman 1).
    momentum_weight  IBEX es momentum puro (level_weight=0).
  - transform        None | "real_deflate" | "diff" — preproceso determinista.
  - coverage_peaks   nº de picos CFC que la serie alcanza (cobertura desigual).

Validación de series_id: confirmada por FRED para las series point-in-time
(IRLTLT01ESM156N, IRLTLT01DEM156N, BAMLHE00EHYIOAS, SPASTT01ESM661N). ECB/
Eurostat/INE entran como confirmación sin vintage nativo — sesgo documentado.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Provider(str, Enum):
    FRED = "fred"          # FRED/ALFRED — vintage nativo (point-in-time)
    ECB = "ecb"            # ECB Data Portal (SDMX) — sin vintage nativo
    EUROSTAT = "eurostat"  # Eurostat dissemination API — sin vintage nativo
    INE = "ine"            # INE Tempus3 — sin vintage nativo


class Block(str, Enum):
    TIPOS = "Tipos"
    CREDITO = "Crédito"
    CONFIANZA = "Confianza"
    ACTIVIDAD = "Actividad real"
    MERCADO = "Mercado / monetario"


# El número de bloques fija el peso: cada bloque = 1/len(Block).
N_BLOCKS = len(Block)
BLOCK_WEIGHT = 1.0 / N_BLOCKS  # 0.20


@dataclass(frozen=True)
class Source:
    provider: Provider
    series_id: str
    has_vintage: bool          # True solo FRED/ALFRED
    note: str = ""


@dataclass(frozen=True)
class Indicator:
    key: str
    name: str
    block: Block
    sources: list[Source]
    direction: int             # +1 o -1
    level_weight: float = 0.5
    momentum_weight: float = 0.5
    transform: str | None = None
    coverage_peaks: int = 0    # nº de picos CFC alcanzados (informativo)
    # Para 'real_deflate': series_id del deflactor (HICP) en su provider.
    deflator: Source | None = None
    description: str = ""

    def primary(self) -> Source:
        return self.sources[0]


# --------------------------------------------------------------------------- #
#  Los 8 indicadores / 5 bloques
# --------------------------------------------------------------------------- #
INDICATORS: list[Indicator] = [
    # === Bloque 1: TIPOS =================================================== #
    Indicator(
        key="euro_curve",
        name="Curva euro (10y − 2y)",
        block=Block.TIPOS,
        sources=[
            Source(Provider.ECB, "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y", False,
                   "Curva spot AAA zona euro 10Y (ECB YC). Se resta el 2Y."),
            Source(Provider.ECB, "YC/B.U2.EUR.4F.G_N_A.SV_C_YM.SR_2Y", False,
                   "Curva spot AAA zona euro 2Y."),
        ],
        direction=-1,  # curva más plana/invertida = MÁS riesgo
        level_weight=0.5, momentum_weight=0.5,
        transform="spread",  # 10y - 2y
        coverage_peaks=3,    # ~1999+ -> 2008/2011/COVID
        description="Pendiente de la curva: aplanamiento/inversión anticipa recesión.",
    ),
    Indicator(
        key="spain_risk_premium",
        name="Prima de riesgo España (ES10y − Bund)",
        block=Block.TIPOS,
        sources=[
            Source(Provider.FRED, "IRLTLT01ESM156N", True, "España 10Y (OECD/FRED)."),
            Source(Provider.FRED, "IRLTLT01DEM156N", True, "Alemania 10Y (Bund)."),
        ],
        direction=+1,  # prima alta = MÁS riesgo
        level_weight=0.5, momentum_weight=0.5,
        transform="spread_es_de",  # ES10y - DE10y
        coverage_peaks=4,  # desde 1980 -> 1980 parcial, 1992, 2008, 2011, COVID
        description="Sobrecoste de financiación soberana frente a Alemania.",
    ),

    # === Bloque 2: CRÉDITO ================================================= #
    Indicator(
        key="bls",
        name="Bank Lending Survey (endurecimiento)",
        block=Block.CREDITO,
        sources=[
            # Net % de bancos que endurecen criterios de crédito a empresas (ES).
            Source(Provider.ECB, "BLS/Q.ES.ALL.O.E.Z.B3.ST.S.BWFNET", False,
                   "BLS: criterios de crédito a empresas, neto, España."),
        ],
        direction=+1,  # más endurecimiento = MÁS riesgo
        level_weight=0.5, momentum_weight=0.5,
        transform=None,
        coverage_peaks=3,  # trimestral desde 2002/2003
        description="Encuesta de préstamos bancarios del BCE; gatillo de crédito.",
    ),
    Indicator(
        key="hy_spread",
        name="Spread corporativo HY euro (OAS)",
        block=Block.CREDITO,
        sources=[
            Source(Provider.FRED, "BAMLHE00EHYIOAS", True,
                   "ICE BofA Euro High Yield Option-Adjusted Spread."),
        ],
        direction=+1,  # spread alto = MÁS riesgo
        level_weight=0.5, momentum_weight=0.5,
        transform=None,
        coverage_peaks=3,  # desde ~1998 -> 2008/2011/COVID
        description="Coste de financiación del crédito corporativo de alto riesgo.",
    ),

    # === Bloque 3: CONFIANZA ============================================== #
    Indicator(
        key="esi",
        name="ESI España (sentimiento económico)",
        block=Block.CONFIANZA,
        sources=[
            Source(Provider.EUROSTAT, "ei_bssi_m_r2", False,
                   "Economic Sentiment Indicator, España, mensual (DG ECFIN/Eurostat)."),
        ],
        direction=-1,  # ESI alto = MENOS riesgo
        level_weight=0.5, momentum_weight=0.5,
        transform=None,
        coverage_peaks=4,  # desde 1985 -> 1992/2008/2011/COVID
        description="Indicador compuesto de confianza de la Comisión Europea.",
    ),

    # === Bloque 4: ACTIVIDAD REAL ========================================= #
    Indicator(
        key="visados",
        name="Visados de obra nueva",
        block=Block.ACTIVIDAD,
        sources=[
            # INE Tempus3 — visados de dirección de obra, vivienda nueva.
            Source(Provider.INE, "DCO_VISADO_NUEVA", False,
                   "Visados de obra nueva (INE/Mitma). Código provisional, validar."),
        ],
        direction=-1,  # más visados = MENOS riesgo
        level_weight=0.4, momentum_weight=0.6,  # la actividad real avisa por momentum
        transform=None,
        coverage_peaks=3,  # post-2008 por ruptura (ver structural_breaks)
        description="Permisos de construcción residencial; adelantado de inversión.",
    ),

    # === Bloque 5: MERCADO / MONETARIO ==================================== #
    Indicator(
        key="ibex",
        name="IBEX 35 (momentum)",
        block=Block.MERCADO,
        sources=[
            # Índice mensual de cotizaciones España (OECD/FRED) como proxy IBEX.
            Source(Provider.FRED, "SPASTT01ESM661N", True,
                   "Share Prices: All Shares for Spain (OECD/FRED), índice mensual."),
        ],
        direction=-1,  # bolsa al alza = MENOS riesgo
        level_weight=0.0, momentum_weight=1.0,  # MOMENTUM PURO (spec)
        transform=None,
        coverage_peaks=6,  # serie larga desde los 70
        description="Momentum de la bolsa española; cae antes de la recesión.",
    ),
    Indicator(
        key="real_m1",
        name="M1 real",
        block=Block.MERCADO,
        sources=[
            Source(Provider.FRED, "MANMM101EZM189S", True,
                   "M1 zona euro (OECD/FRED), nivel nominal."),
        ],
        deflator=Source(Provider.FRED, "CP0000EZ19M086NEST", True,
                        "HICP zona euro (índice 2015=100), deflactor oficial."),
        direction=-1,  # M1 real creciente = MENOS riesgo (liquidez)
        level_weight=0.3, momentum_weight=0.7,  # el impulso monetario avisa por momentum
        transform="real_deflate",
        coverage_peaks=3,
        description="Dinero estrecho deflactado; impulso/contracción de liquidez real.",
    ),
]


def indicators_by_block() -> dict[Block, list[Indicator]]:
    out: dict[Block, list[Indicator]] = {b: [] for b in Block}
    for ind in INDICATORS:
        out[ind.block].append(ind)
    return out


def get_indicator(key: str) -> Indicator:
    for ind in INDICATORS:
        if ind.key == key:
            return ind
    raise KeyError(key)
