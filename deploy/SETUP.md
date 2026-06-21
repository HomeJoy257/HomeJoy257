# Despliegue de CicloRadar (datos REALES, automático)

Este sandbox de Claude Code web tiene el egress bloqueado, por eso aquí no bajan
los datos. En un servidor normal (Hetzner) **no hay ese bloqueo** y todo el feed
real (INE, ECB, Eurostat, FRED) fluye sin tocar el código.

## 1. Requisitos
- Linux con Python 3.11+
- Una **FRED API key** gratis: https://fred.stlouisfed.org/docs/api/api_key.html
- Un bot de Telegram (token) y tu `chat_id` (opcional, para alertas)

## 2. Instalación (5 min)
```bash
git clone <tu-repo> HomeJoy257
cd HomeJoy257
bash deploy/setup.sh
nano .env          # FRED_API_KEY=...  TELEGRAM_BOT_TOKEN=...  TELEGRAM_CHAT_ID=...
```

## 3. Verificar que los datos REALES llegan
```bash
.venv/bin/python -m cicloradar.cli check          # hosts ✅ alcanzable
.venv/bin/python -m cicloradar.cli run            # índice con datos reales
.venv/bin/python -m cicloradar.cli qa --live      # calidad REAL (backtest vs CFC)
.venv/bin/python -m cicloradar.cli verify --indicator hy_spread   # momentum real
```
Si `qa --live` da PASS, el índice es bueno con datos reales. Si algún indicador
falla, el informe dice cuál y por qué (sin inventar señal).

## 4. Automatizar (elige una)

### Cron (simple)
```bash
crontab -e
# pega, ajustando la ruta:
0 8 2 * *   /ruta/HomeJoy257/deploy/run.sh >> /var/log/cicloradar.log 2>&1
```

### systemd timer (más robusto)
```bash
sudo cp deploy/cicloradar.service deploy/cicloradar.timer /etc/systemd/system/
sudo sed -i "s#/ruta/HomeJoy257#$(pwd)#" /etc/systemd/system/cicloradar.service
sudo systemctl daemon-reload
sudo systemctl enable --now cicloradar.timer
systemctl list-timers cicloradar*       # comprobar
```

`run.sh` corre primero `qa --live` (control de calidad) y luego `run --save
--notify` (índice + histórico + alerta Telegram si no es VERDE).

## 5. (Alternativa) Usarlo dentro de Claude Code web
Añade estos hosts al **egress allowlist** del entorno (ajustes de red del
entorno en claude.ai/code) y entonces `run`/`qa --live` funcionan también aquí:
```
api.stlouisfed.org  data-api.ecb.europa.eu  ec.europa.eu  servicios.ine.es  api.telegram.org
```
Docs: https://code.claude.com/docs/en/claude-code-on-the-web
