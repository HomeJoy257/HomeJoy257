"""
Cronología del ciclo económico español — Comité de Fechado del Ciclo (CFC)
de la Asociación Española de Economía (AEE).

Este es el GROUND TRUTH del sistema. Es una constante VERSIONADA: cualquier
cambio en las fechas oficiales se refleja subiendo CHRONOLOGY_VERSION y dejando
constancia en el changelog de abajo. NUNCA se ajustan estas fechas para que el
índice "encaje" mejor (eso sería sobreajuste sobre n=6).

Fuente: Comité de Fechado del Ciclo, AEE — http://www.asesec.org/CFCweb/
        https://asesec.org/en/dating-committee/

Convención (idéntica a NBER/CEPR):
  - El PICO (peak) es el último periodo de expansión. La recesión empieza el
    periodo SIGUIENTE al pico.
  - El VALLE (trough) es el último periodo de recesión. La expansión empieza el
    periodo siguiente al valle.
  - El CFC fecha en TRIMESTRES hasta 2020 y en MESES para la recesión COVID.

Nota sobre el recuento: el spec v0.1 menciona "6 recesiones desde 1970". El CFC
y la literatura asociada (Bandrés, Gadea, Gómez-Loscos) documentan los episodios
de los años 70 y comienzos de los 80 con cierto grado de agregación según la
publicación. Aquí encodamos los episodios de forma granular (7 picos) porque
para construir la "firma pre-recesión" cuantos más picos válidos, mejor. El campo
`spec_count_note` deja registro de la discrepancia. Para fusionar 1978-1981 en un
único episodio, basta editar esta lista (es dato, no código).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

CHRONOLOGY_VERSION = "2026.06.21"
SOURCE = "Comité de Fechado del Ciclo (AEE) — asesec.org/CFCweb"

# Changelog:
#   2026.06.21  Versión inicial. Picos/valles trimestrales 1974-2013 + COVID
#               mensual (pico feb-2020). Fuente CFC/AEE.


@dataclass(frozen=True)
class Recession:
    """Un episodio de recesión fechado por el CFC.

    `peak` y `trough` son el PRIMER día del periodo (trimestre o mes) fechado.
    `granularity` indica si el fechado oficial es trimestral o mensual.
    """

    peak: date          # último periodo de expansión (inicio del periodo)
    trough: date        # último periodo de recesión (inicio del periodo)
    label: str
    granularity: str    # "quarter" | "month"
    note: str = ""

    @property
    def recession_start(self) -> date:
        """Primer periodo ya en recesión (el siguiente al pico)."""
        return _next_period(self.peak, self.granularity)


def _next_period(d: date, granularity: str) -> date:
    if granularity == "quarter":
        m = d.month + 3
        y = d.year + (m - 1) // 12
        m = ((m - 1) % 12) + 1
        return date(y, m, 1)
    # month
    m = d.month + 1
    y = d.year + (m - 1) // 12
    m = ((m - 1) % 12) + 1
    return date(y, m, 1)


# Picos y valles oficiales del CFC. Trimestres expresados como primer mes del
# trimestre (Q1=ene, Q2=abr, Q3=jul, Q4=oct).
CFC_RECESSIONS: list[Recession] = [
    Recession(date(1974, 10, 1), date(1975, 7, 1), "Crisis del petróleo I",
              "quarter", "Pico 1974Q4, valle 1975Q3"),
    Recession(date(1978, 4, 1), date(1979, 7, 1), "Crisis del petróleo II",
              "quarter", "Pico 1978Q2, valle 1979Q3"),
    Recession(date(1980, 7, 1), date(1981, 7, 1), "Ajuste energético/industrial",
              "quarter", "Pico 1980Q3, valle 1981Q3"),
    Recession(date(1992, 1, 1), date(1993, 10, 1), "Crisis del SME / Guerra del Golfo",
              "quarter", "Pico 1992Q1, valle 1993Q4"),
    Recession(date(2008, 4, 1), date(2009, 10, 1), "Gran Recesión (1ª fase)",
              "quarter", "Pico 2008Q2, valle 2009Q4"),
    Recession(date(2011, 7, 1), date(2013, 1, 1), "Crisis de deuda soberana (doble caída)",
              "quarter", "Pico 2011Q3, valle 2013Q1"),
    Recession(date(2020, 2, 1), date(2020, 5, 1), "COVID-19",
              "month", "Pico mensual feb-2020, valle may-2020"),
]

spec_count_note = (
    "El spec v0.1 cita 6 recesiones; aquí se encodan 7 episodios granulares. "
    "Fusionar 1978-1981 reproduce el recuento de 6. Es decisión editable."
)


def recession_peaks() -> list[date]:
    """Fechas de pico — los instantes contra los que se construye la firma."""
    return [r.peak for r in CFC_RECESSIONS]


def is_in_recession(d: date) -> bool:
    """True si la fecha cae dentro de un episodio de recesión (pico excluido,
    valle incluido), según la convención CFC."""
    for r in CFC_RECESSIONS:
        if r.recession_start <= d <= r.trough:
            return True
    return False
