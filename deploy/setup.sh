#!/usr/bin/env bash
# Setup de CicloRadar en un servidor (Hetzner, etc.) SIN egress bloqueado.
# Crea venv, instala deps y prepara .env. Idempotente.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "▶ Creando entorno virtual..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

echo "▶ Instalando dependencias..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

if [ ! -f .env ]; then
  echo "▶ Creando .env desde plantilla (rellénalo)..."
  cp .env.example .env
fi

echo "▶ Comprobando conectividad y configuración..."
python -m cicloradar.cli check || true

cat <<'EOF'

✅ Setup hecho.
   1) Edita .env  -> FRED_API_KEY (gratis) y TELEGRAM_BOT_TOKEN/CHAT_ID
   2) Prueba en vivo:  .venv/bin/python -m cicloradar.cli run --save
   3) Calidad real:    .venv/bin/python -m cicloradar.cli qa --live
   4) Programa el cron: ver deploy/crontab.example o deploy/cicloradar.timer
EOF
