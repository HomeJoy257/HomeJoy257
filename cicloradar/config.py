"""
Configuración central de CicloRadar.

Todo lo que es parámetro operativo (no del modelo) vive aquí o en variables de
entorno. Los pesos del índice y los umbrales del spec NO se optimizan: los de
arranque (OQ-02/03) están aquí como punto de partida documentado.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    # --- Credenciales / endpoints ---------------------------------------- #
    fred_api_key: str | None = _env("FRED_API_KEY")
    telegram_token: str | None = _env("TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str | None = _env("TELEGRAM_CHAT_ID")

    # --- Ventana de momentum (OQ-05): se calculan AMBAS ------------------ #
    # `momentum_window_months` es la PRIMARIA (la que gobierna la alerta);
    # `momentum_window_alt` es la secundaria, que se muestra como comparación.
    momentum_window_months: int = int(_env("MOMENTUM_WINDOW", "3"))
    momentum_window_alt: int = int(_env("MOMENTUM_WINDOW_ALT", "6"))

    # --- Umbrales de alerta (OQ-02/03) — punto de arranque, NO optimizado - #
    # El índice ya es un percentil 0-100, así que p80/p90 son literalmente 80/90.
    amber_level: float = float(_env("AMBER_LEVEL", "80"))
    red_level: float = float(_env("RED_LEVEL", "90"))
    # Aceleración: variación del índice (puntos/mes) que dispara por momentum.
    amber_accel: float = float(_env("AMBER_ACCEL", "10"))
    red_accel: float = float(_env("RED_ACCEL", "15"))
    # Persistencia: ROJO exige N lecturas consecutivas; ÁMBAR basta 1.
    red_persistence: int = int(_env("RED_PERSISTENCE", "2"))

    # --- Cobertura mínima para emitir índice ----------------------------- #
    min_blocks_for_index: int = int(_env("MIN_BLOCKS", "2"))

    # --- Almacenamiento (OQ-06): fichero SQLite, stack mínimo ------------- #
    db_path: str = _env("CICLORADAR_DB", "cicloradar_history.sqlite")

    # --- Red --------------------------------------------------------------#
    http_timeout: int = int(_env("HTTP_TIMEOUT", "30"))
    http_retries: int = int(_env("HTTP_RETRIES", "4"))


settings = Settings()

# Hosts que deben estar en el allowlist de egress para el fetch en vivo.
REQUIRED_EGRESS_HOSTS = [
    "api.stlouisfed.org",        # FRED / ALFRED
    "data-api.ecb.europa.eu",    # ECB Data Portal (SDMX)
    "ec.europa.eu",              # Eurostat dissemination API
    "servicios.ine.es",          # INE Tempus3
    "api.telegram.org",          # envío de alertas
]
