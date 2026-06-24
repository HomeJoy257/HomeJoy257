#!/usr/bin/env bash
# Ejecuta un ciclo: fetch real + índice + guarda histórico + alerta Telegram.
# Pensado para cron. Carga .env y usa el venv del proyecto.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# Cargar variables de .env si existe.
if [ -f .env ]; then
  set -a; # shellcheck disable=SC1091
  source .env; set +a
fi

PY="$ROOT/.venv/bin/python"
[ -x "$PY" ] || PY="python3"

# 1) Calidad: si el QA en vivo falla de forma crítica, avisa y NO emite señal dudosa.
if ! "$PY" -m cicloradar.cli qa --live >/tmp/cicloradar_qa.log 2>&1; then
  echo "$(date -Is) QA FAIL — revisar /tmp/cicloradar_qa.log" >&2
fi

# 2) Cálculo + alerta (ciclo).
"$PY" -m cicloradar.cli run --save --notify

# 3) Fragilidad del hogar (datos reales, fuentes independientes).
"$PY" -m cicloradar.cli fragility
