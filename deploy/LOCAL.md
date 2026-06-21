# Ejecutar CicloRadar en tu PC (depuración antes del Hetzner)

Tu PC no tiene el egress bloqueado, así que aquí SÍ bajan los datos reales de las
APIs españolas/europeas. Plan: dejarlo fino aquí y luego pasarlo al servidor.

## 0. Necesitas
- **Python 3.11+** — https://www.python.org/downloads/ (en Windows marca
  "Add Python to PATH" al instalar).
- **FRED API key** gratis (1 min): https://fred.stlouisfed.org/docs/api/api_key.html
  (sin ella cargan igual los 4 indicadores de INE/ECB/Eurostat, que no llevan key).
- Telegram opcional (token del bot + tu chat_id) para las alertas.

---

## 1. Instalar

### Windows (PowerShell)
```powershell
git clone <tu-repo> HomeJoy257
cd HomeJoy257
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env          # pon FRED_API_KEY=...  y, si quieres, Telegram
```

### macOS / Linux
```bash
git clone <tu-repo> HomeJoy257
cd HomeJoy257
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
nano .env             # FRED_API_KEY=...  y, si quieres, Telegram
```

> Para que `.env` se cargue, exporta las variables o instala `python-dotenv`.
> Lo más simple en PC: definirlas en la sesión antes de ejecutar.
> Windows: `$env:FRED_API_KEY="xxxx"`  ·  Mac/Linux: `export FRED_API_KEY=xxxx`

---

## 2. Depurar fuente por fuente (lo importante)

```bash
python -m cicloradar.cli probe
```
Verás una línea por API/serie:
- **✅** = responde (muestra nº de observaciones, última fecha y valor).
- **❌ con un series_id** = ese código hay que validarlo (p.ej. **visados INE**,
  marcado como provisional). Cópiame esa línea y lo corrijo.
- **⛔ EGRESS** = solo pasa en el sandbox; en tu PC NO debe salir. Si te sale en
  el PC es un proxy/cortafuegos corporativo.

El candidato a fallar es `visados · ine:DCO_VISADO_NUEVA` (código provisional).
Cuando me pases la salida de `probe`, ajusto el código real de INE Tempus3.

---

## 3. Ver el índice y la calidad con datos REALES
```bash
python -m cicloradar.cli check        # claves + conectividad
python -m cicloradar.cli run          # índice real + descomposición por bloque
python -m cicloradar.cli qa --live    # CALIDAD real: backtest contra recesiones CFC
```
- Si `qa --live` da **PASS**, el índice es bueno con datos reales.
- `run --save` guarda el histórico; `run --notify` manda la alerta a Telegram.

---

## 4. Cuando esté fino → al Hetzner
Mismo repo, `deploy/SETUP.md`: `setup.sh` + cron/systemd para el recálculo
mensual automático. Lo que depures aquí va igual allí.

---

## Si algo falla, mándame:
1. La salida completa de `python -m cicloradar.cli probe`.
2. La de `python -m cicloradar.cli run` (o `qa --live`).
Con eso corrijo los `series_id` que no validen y dejo el feed real redondo.
