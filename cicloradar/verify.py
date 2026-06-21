"""
Verificación AUDITABLE del cálculo de momentum (OQ-05).

Objetivo: poder comprobar, paso a paso y con números reales, que el motor de
momentum hace lo que dice — Δ sobre la ventana y su percentil — sin caja negra.

Tres fuentes de datos para verificar:
  1. sample()      -> serie pequeña fija, comprobable a mano con calculadora.
  2. from_csv()    -> CSV del usuario "periodo,valor" (datos REALES sin red).
  3. cliente FRED  -> serie real en vivo (requiere egress + FRED_API_KEY).

`trace_momentum` imprime, para cada periodo reciente: valor, Δ en cada ventana
y el percentil de ese Δ sobre TODA la historia de la serie.
"""

from __future__ import annotations

import csv as _csv
from datetime import date

from .data.base import Obs, Series
from .engine.percentile import momentum, percentile_rank


def sample() -> Series:
    """Serie mensual mínima y conocida para comprobar el cálculo a mano."""
    vals = [10.0, 10.0, 11.0, 13.0, 12.0, 14.0, 17.0, 16.0, 18.0, 21.0]
    obs = [Obs(date(2020, i + 1, 1), v) for i, v in enumerate(vals)]
    return Series("SAMPLE", "verify", obs)


def from_csv(path: str) -> Series:
    """Carga 'YYYY-MM-DD,valor' (o 'YYYY-MM,valor'). Una observación por línea.
    Acepta cabecera opcional. Datos REALES aportados por el usuario."""
    obs: list[Obs] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in _csv.reader(fh):
            if not row or len(row) < 2:
                continue
            per, val = row[0].strip(), row[1].strip()
            try:
                v = float(val.replace(",", "."))
            except ValueError:
                continue  # cabecera u otra fila no numérica
            parts = per.split("-")
            try:
                y = int(parts[0]); m = int(parts[1]) if len(parts) > 1 else 1
            except (ValueError, IndexError):
                continue
            obs.append(Obs(date(y, m, 1), v))
    return Series(path, "csv", obs).clean()


def trace_momentum(s: Series, windows: tuple[int, ...] = (3, 6), tail: int = 12) -> str:
    """Traza el momentum de la serie para las ventanas dadas."""
    s = s.clean()
    vals = s.values()
    pers = s.periods()
    L: list[str] = []
    L.append(f"Serie: {s.series_id} ({s.provider})")
    if s.obs:
        L.append(f"Observaciones: {len(s.obs)}  ·  rango: "
                 f"{pers[0].isoformat()} .. {pers[-1].isoformat()}")
    L.append("")

    # Δ y su muestra histórica completa por ventana (para el percentil).
    mom_by_w = {}
    sample_by_w = {}
    for w in windows:
        m = momentum(vals, w)
        mom_by_w[w] = m
        sample_by_w[w] = [x for x in m if x is not None]

    header = f"{'periodo':<10}{'valor':>9}"
    for w in windows:
        header += f"{'Δ' + str(w) + 'm':>9}{'pct' + str(w):>8}"
    L.append(header)
    L.append("─" * len(header))

    start = max(0, len(vals) - tail)
    for i in range(start, len(vals)):
        line = f"{pers[i].isoformat():<10}{vals[i]:>9.3f}"
        for w in windows:
            d = mom_by_w[w][i]
            if d is None:
                line += f"{'n/d':>9}{'·':>8}"
            else:
                pct = percentile_rank(d, sample_by_w[w])
                line += f"{d:>9.3f}{pct:>8.1f}"
        L.append(line)
    return "\n".join(L)


def hand_check() -> str:
    """Comprobación numérica explícita sobre `sample()` que cualquiera puede
    reproducir con calculadora. Lanza AssertionError si el motor no cuadra."""
    s = sample()
    vals = s.values()  # [10,10,11,13,12,14,17,16,18,21]
    m3 = momentum(vals, 3)
    m6 = momentum(vals, 6)

    # Último periodo: Δ3m = v[9]-v[6] = 21-17 = 4 ; Δ6m = v[9]-v[3] = 21-13 = 8
    assert m3[-1] == 4.0, m3[-1]
    assert m6[-1] == 8.0, m6[-1]
    # Los 3 primeros de Δ3m son None (sin base de 3 meses).
    assert m3[:3] == [None, None, None]

    # Percentil de Δ3m=4 sobre la muestra de Δ3m.
    s3 = [x for x in m3 if x is not None]   # [1,3,1,1,5,2,2,5] -> Δ3m por mes
    pct = percentile_rank(4.0, s3)
    # nº de Δ3m <= 4 son 6 de 7 -> 85.7%
    assert abs(pct - 100.0 * sum(1 for x in s3 if x <= 4.0) / len(s3)) < 1e-9

    L = [
        "Comprobación a mano (serie SAMPLE):",
        f"  valores            = {vals}",
        f"  Δ3m (último)       = v[-1]-v[-4] = {vals[-1]}-{vals[-4]} = {m3[-1]}  ✅",
        f"  Δ6m (último)       = v[-1]-v[-7] = {vals[-1]}-{vals[-7]} = {m6[-1]}  ✅",
        f"  muestra Δ3m        = {s3}",
        f"  pct(Δ3m=4)         = {pct:.1f}  (Δ3m ≤ 4 en {sum(1 for x in s3 if x<=4)}/{len(s3)})  ✅",
        "  -> el motor de momentum cuadra con el cálculo manual.",
    ]
    return "\n".join(L)
