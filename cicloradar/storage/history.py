"""
Almacenamiento del histórico del índice (OQ-06): SQLite en fichero.

Stack mínimo, sin servidor, reproducible y versionable. Guarda una fila por
periodo con el índice, cobertura, estado de alerta y el JSON de descomposición
por bloque para auditoría.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date

from ..config import settings
from ..engine.aggregate import IndexPoint
from ..engine.alert import Alert

_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_history (
    period           TEXT PRIMARY KEY,
    index_value      INTEGER NOT NULL,
    raw_composite    REAL NOT NULL,
    blocks_available INTEGER NOT NULL,
    coverage         REAL NOT NULL,
    state            TEXT,
    trigger          TEXT,
    delta            REAL,
    block_scores     TEXT,
    computed_at      TEXT DEFAULT (datetime('now'))
);
"""


def _conn(path: str | None = None) -> sqlite3.Connection:
    c = sqlite3.connect(path or settings.db_path)
    c.execute(_SCHEMA)
    return c


def save_point(pt: IndexPoint, alert: Alert | None = None, path: str | None = None) -> None:
    with _conn(path) as c:
        c.execute(
            """INSERT INTO index_history
               (period, index_value, raw_composite, blocks_available, coverage,
                state, trigger, delta, block_scores)
               VALUES (?,?,?,?,?,?,?,?,?)
               ON CONFLICT(period) DO UPDATE SET
                 index_value=excluded.index_value,
                 raw_composite=excluded.raw_composite,
                 blocks_available=excluded.blocks_available,
                 coverage=excluded.coverage,
                 state=excluded.state, trigger=excluded.trigger,
                 delta=excluded.delta, block_scores=excluded.block_scores,
                 computed_at=datetime('now')""",
            (pt.period.isoformat(), pt.index, pt.raw_composite, pt.blocks_available,
             pt.coverage,
             alert.state.value if alert else None,
             alert.trigger if alert else None,
             alert.delta if alert else None,
             json.dumps(pt.block_scores, ensure_ascii=False)),
        )


def save_history(history: list[IndexPoint], path: str | None = None) -> int:
    for pt in history:
        save_point(pt, None, path)
    return len(history)


def last_state(path: str | None = None) -> str | None:
    with _conn(path) as c:
        row = c.execute(
            "SELECT state FROM index_history ORDER BY period DESC LIMIT 1").fetchone()
    return row[0] if row else None
