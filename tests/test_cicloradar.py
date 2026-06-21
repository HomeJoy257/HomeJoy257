"""Tests deterministas de CicloRadar (eval-driven). Sin red."""

from __future__ import annotations

from datetime import date

import pytest

from cicloradar.config import settings
from cicloradar.constants.cfc_chronology import (CFC_RECESSIONS, is_in_recession,
                                                recession_peaks)
from cicloradar.constants.series_registry import BLOCK_WEIGHT, N_BLOCKS
from cicloradar.constants.structural_breaks import BreakPolicy, breaks_for
from cicloradar.data.base import Obs, Series, spread
from cicloradar.data.demo import demo_series
from cicloradar.engine.aggregate import compute
from cicloradar.engine.alert import State, evaluate
from cicloradar.engine.percentile import momentum, percentile_rank


# --- percentiles / momentum ------------------------------------------------ #
def test_percentile_rank_bounds():
    s = [1, 2, 3, 4, 5]
    assert percentile_rank(0, s) == 0.0
    assert percentile_rank(5, s) == 100.0
    assert percentile_rank(3, s) == 60.0
    assert percentile_rank(7, []) == 50.0  # muestra vacía -> neutro


def test_momentum_window():
    vals = [10, 11, 12, 13, 14]
    m = momentum(vals, 2)
    assert m[:2] == [None, None]
    assert m[2:] == [2, 2, 2]


# --- limpieza de series ---------------------------------------------------- #
def test_series_clean_dedup_and_sort():
    s = Series("x", "t", [Obs(date(2020, 2, 1), 2.0),
                          Obs(date(2020, 1, 1), 1.0),
                          Obs(date(2020, 2, 1), 9.0)])  # dup: gana el último
    c = s.clean()
    assert c.periods() == [date(2020, 1, 1), date(2020, 2, 1)]
    assert c.values() == [1.0, 9.0]


def test_series_clean_drops_nan():
    s = Series("x", "t", [Obs(date(2020, 1, 1), float("nan")),
                          Obs(date(2020, 2, 1), 3.0)])
    assert s.clean().values() == [3.0]


def test_spread_intersection():
    a = Series("a", "t", [Obs(date(2020, 1, 1), 5), Obs(date(2020, 2, 1), 6)])
    b = Series("b", "t", [Obs(date(2020, 2, 1), 1), Obs(date(2020, 3, 1), 2)])
    sp = spread(a, b)
    assert sp.periods() == [date(2020, 2, 1)]
    assert sp.values() == [5]


# --- pesos / cobertura ----------------------------------------------------- #
def test_block_weights_sum_to_one():
    assert N_BLOCKS == 5
    assert abs(BLOCK_WEIGHT * N_BLOCKS - 1.0) < 1e-9


# --- cronología CFC -------------------------------------------------------- #
def test_cfc_chronology_nonempty_and_ordered():
    peaks = recession_peaks()
    assert len(peaks) == len(CFC_RECESSIONS) >= 6
    assert peaks == sorted(peaks)


def test_is_in_recession():
    # 2008Q2 pico (abr) -> recesión empieza jul-2008; valle 2009Q4 (oct).
    assert not is_in_recession(date(2008, 4, 1))   # pico, aún expansión
    assert is_in_recession(date(2009, 1, 1))       # dentro de la recesión
    assert not is_in_recession(date(2010, 6, 1))   # recuperación


# --- rupturas estructurales ------------------------------------------------ #
def test_structural_break_policies():
    assert breaks_for("visados")[0].policy == BreakPolicy.DROP_PRE
    assert breaks_for("esi")[0].policy == BreakPolicy.OFFICIAL_LINK
    assert breaks_for("real_m1")[0].policy == BreakPolicy.OFFICIAL_LINK


# --- pipeline demo (integración offline) ----------------------------------- #
def test_demo_pipeline_produces_valid_index():
    history = compute(demo_series())
    assert history, "el pipeline demo debe producir historia"
    for pt in history:
        assert 0 <= pt.index <= 100
        assert 1 <= pt.blocks_available <= N_BLOCKS
        assert pt.blocks_available >= settings.min_blocks_for_index
    # el índice debe escalar a su máximo histórico en algún punto.
    assert max(p.index for p in history) == 100
    assert min(p.index for p in history) >= 0


def test_demo_index_peaks_near_recessions():
    """El estrés sintético está centrado en 2008/2011/2020: el índice debe ser,
    en MEDIA, más alto dentro de las ventanas de recesión (±9 meses del centro)
    que fuera. Más robusto que comparar un único mes (el momentum desfasa)."""
    centers = [date(2008, 4, 1), date(2011, 7, 1), date(2020, 2, 1)]

    def near_center(p):
        return any(abs((p.year - c.year) * 12 + (p.month - c.month)) <= 9
                   for c in centers)

    history = compute(demo_series())
    inside = [p.index for p in history if near_center(p.period)]
    outside = [p.index for p in history if not near_center(p.period)]
    assert inside and outside
    assert sum(inside) / len(inside) > sum(outside) / len(outside)


# --- alerta: doble gatillo + persistencia ---------------------------------- #
def _mk(idx_values):
    from cicloradar.engine.aggregate import IndexPoint
    return [IndexPoint(date(2000, 1, 1), v, float(v), 5, 1.0) for v in idx_values]


def test_alert_green_when_low():
    assert evaluate(_mk([10, 12, 15])).state == State.GREEN


def test_alert_amber_on_level():
    a = evaluate(_mk([10, 20, 85]))         # 85 >= p80
    assert a.state == State.AMBER


def test_alert_red_needs_persistence():
    one = evaluate(_mk([10, 20, 95]))       # 1 lectura roja -> ámbar
    assert one.state == State.AMBER
    two = evaluate(_mk([10, 95, 96]))       # 2 consecutivas -> rojo
    assert two.state == State.RED


def test_qa_passes_on_demo():
    """El harness de calidad debe pasar todos los gates críticos sobre demo."""
    from cicloradar import quality
    rep = quality.run_qa(demo_series())
    assert rep.ok, [g.name for g in rep.gates if g.critical and not g.passed]
    assert rep.score == 100.0


def test_qa_backtest_catches_recessions():
    """El backtest debe avisar (ÁMBAR+) de las 3 recesiones cubiertas con lead."""
    from cicloradar import quality
    from cicloradar.engine.aggregate import compute
    bt = quality.backtest(compute(demo_series()))
    assert bt["covered_recessions"] == 3
    assert bt["recall"] == 1.0
    assert bt["false_alarm_rate"] <= quality.MAX_FALSE_ALARM_RATE


def test_qa_reproducible():
    from cicloradar import quality
    s = demo_series()
    assert quality.run_qa(s).score == quality.run_qa(s).score


def test_structural_break_applied_in_demo():
    """visados no debe conservar tramo pre-2008 (DROP_PRE) en la ruta offline."""
    s = demo_series()["visados"]
    assert all(o.period >= date(2008, 1, 1) for o in s.obs)


def test_verify_hand_check():
    """La comprobación manual del momentum no debe lanzar (motor == aritmética)."""
    from cicloradar import verify
    out = verify.hand_check()
    assert "cuadra" in out


def test_verify_csv_roundtrip(tmp_path):
    from cicloradar import verify
    p = tmp_path / "d.csv"
    p.write_text("periodo,valor\n2025-01,3.0\n2025-02,3.5\n2025-03,4.0\n"
                 "2025-04,4.6\n", encoding="utf-8")
    s = verify.from_csv(str(p))
    assert s.values() == [3.0, 3.5, 4.0, 4.6]            # cabecera ignorada
    assert s.periods()[0] == date(2025, 1, 1)
    # Δ3m del último = 4.6 - 3.0 = 1.6
    from cicloradar.engine.percentile import momentum
    assert abs(momentum(s.values(), 3)[-1] - 1.6) < 1e-9


def test_both_momentum_windows_computed():
    """Se calculan AMBAS ventanas (3m primaria, 6m secundaria) y ambas dan un
    índice válido sobre el mismo dataset."""
    series = demo_series()
    h3 = compute(series, 3)
    h6 = compute(series, 6)
    assert h3 and h6
    assert all(0 <= p.index <= 100 for p in h3)
    assert all(0 <= p.index <= 100 for p in h6)
    # ventanas distintas -> en general lecturas distintas (no idénticas siempre).
    assert [p.index for p in h3] != [p.index for p in h6]


def test_alert_acceleration_trigger():
    # Salto de +30 dispara por aceleración aunque el nivel no llegue a p80.
    a = evaluate(_mk([10, 12, 60]))
    assert a.state == State.AMBER
    assert "aceleración" in a.trigger
