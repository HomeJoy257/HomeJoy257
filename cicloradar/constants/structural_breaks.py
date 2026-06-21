"""
Registro de RUPTURAS ESTRUCTURALES (FR-02).

Segundo modo de fallo, independiente del de revisiones. El point-in-time
(ALFRED) corrige revisiones del MISMO concepto; NO corrige que el concepto
cambie de definición. Aquí listamos, por serie, los cambios de definición
conocidos y la política a aplicar.

Política en cascada ante una ruptura conocida:
  1. OFFICIAL_LINK  -> existe enlace oficial/publicado: empalmar con la serie
                       enlazada oficial. (DEFAULT)
  2. DROP_PRE       -> no hay enlace pero el tramo post-ruptura cubre ciclo
                       suficiente: excluir el tramo pre-ruptura.
  3. DROP_SERIES    -> el tramo post-ruptura es tan corto que el percentil
                       pierde sentido: descartar el indicador.

HARD BLOCK: empalme casero PROHIBIDO en cualquier serie que alimente el índice.
Solo se admite OFFICIAL_LINK con una serie de enlace oficialmente publicada.

Cada aplicación de política queda logueada por el fetcher (serie, ruptura,
política, motivo) — ver data/fetcher.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

BREAKS_VERSION = "2026.06.21"


class BreakPolicy(str, Enum):
    OFFICIAL_LINK = "official_link"   # empalmar con serie enlazada oficial
    DROP_PRE = "drop_pre"             # excluir tramo pre-ruptura
    DROP_SERIES = "drop_series"       # descartar indicador
    HOMEMADE_SPLICE = "homemade"      # PROHIBIDO — solo para detectar y bloquear


@dataclass(frozen=True)
class StructuralBreak:
    indicator: str          # clave del indicador en el series_registry
    break_date: date        # fecha efectiva de la ruptura de definición
    description: str
    policy: BreakPolicy
    official_link_series: str | None = None  # series_id de enlace oficial, si OFFICIAL_LINK
    reason: str = ""


# Empalme casero: cualquier intento de unir series por cuenta propia está
# prohibido. Esta lista existe para DOCUMENTAR rupturas conocidas y forzar una
# de las 3 políticas admitidas.
STRUCTURAL_BREAKS: list[StructuralBreak] = [
    # --- IPC / HICP (deflactor de M1 real) ---
    StructuralBreak(
        indicator="real_m1",
        break_date=date(2016, 1, 1),
        description="Rebases sucesivos del IPC/HICP y cambios de ponderación anual.",
        policy=BreakPolicy.OFFICIAL_LINK,
        official_link_series="CP0000EZ19M086NEST",  # HICP zona euro, índice ya enlazado oficialmente
        reason=("Eurostat publica el HICP como índice encadenado oficial ya "
                "empalmado; usamos esa serie enlazada, sin empalme casero."),
    ),
    # --- PIB (solo ground-truth de fechado, NO alimenta el índice) ---
    # Documentado para trazabilidad: SEC-95 -> ESA-2010. No requiere acción
    # porque el PIB no es un indicador del índice; el fechado lo da el CFC.
    # --- ESI (sentimiento económico) ---
    StructuralBreak(
        indicator="esi",
        break_date=date(2018, 1, 1),
        description="Revisión metodológica DG ECFIN (ponderaciones y muestras).",
        policy=BreakPolicy.OFFICIAL_LINK,
        official_link_series="ei_bssi_m_r2",  # serie ya reconstruida hacia atrás por DG ECFIN
        reason=("DG ECFIN reconstruye el ESI hacia atrás con la metodología "
                "vigente; la serie publicada ya es homogénea."),
    ),
    # --- Visados de obra nueva ---
    StructuralBreak(
        indicator="visados",
        break_date=date(2008, 1, 1),
        description=("Cambio de fuente/criterio en visados de dirección de obra "
                     "(Colegios de Aparejadores -> Mitma) y reclasificación."),
        policy=BreakPolicy.DROP_PRE,
        official_link_series=None,
        reason=("No hay enlace oficial homogéneo pre-2008; el tramo post cubre "
                "2008/2011/COVID, suficiente para el percentil. Se excluye el "
                "tramo pre-ruptura en vez de empalmar a mano."),
    ),
    # --- Paro registrado SEPE: EXCLUIDO del índice (out of scope v0.1) ---
    # Ruptura de definición 2022 (reforma laboral, fijos discontinuos) no
    # declarada oficialmente. El más distorsionable. Se documenta el bloqueo.
    StructuralBreak(
        indicator="__excluded__paro_registrado_sepe",
        break_date=date(2022, 1, 1),
        description=("Reforma laboral 2022: los fijos discontinuos en inactividad "
                     "dejan de contar como paro registrado. Ruptura no declarada."),
        policy=BreakPolicy.DROP_SERIES,
        official_link_series=None,
        reason="Fuera de alcance v0.1: indicador descartado por ruptura no declarada.",
    ),
]


def breaks_for(indicator: str) -> list[StructuralBreak]:
    return [b for b in STRUCTURAL_BREAKS if b.indicator == indicator]
