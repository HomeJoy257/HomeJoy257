# INSTALAR CicloRadar en tu PC (los dos relojes)

Guía única para dejarlo corriendo en tu ordenador. Dos medidores:

- **CicloRadar** → ¿viene el ciclo? (índice 0-100 + alerta VERDE/ÁMBAR/ROJO)
- **FragilidadRadar** → ¿cómo de expuesto está el hogar? (0-100, datos reales)

Un solo comando los enseña juntos: `panel`.

---

## 1. Requisitos (instalar una vez)

1. **Python 3.11 o superior** → https://www.python.org/downloads/
   - En **Windows**: en el instalador marca **"Add Python to PATH"**.
2. **FRED API key** (gratis, 1 min) → https://fred.stlouisfed.org/docs/api/api_key.html
   - Solo para el reloj de CICLO. El de FRAGILIDAD funciona sin nada.
3. (Opcional) **Bot de Telegram** para alertas: crea un bot con @BotFather y
   coge el *token*; tu `chat_id` lo ves escribiendo al bot y mirando
   `https://api.telegram.org/bot<TOKEN>/getUpdates`.

---

## 2. Poner el proyecto en tu PC

**Opción A — descomprimir el ZIP** que te pasé (`CicloRadar.zip`) en una carpeta.

**Opción B — clonar de GitHub:**
```bash
git clone https://github.com/HomeJoy257/HomeJoy257.git
cd HomeJoy257
git checkout claude/cicloradar-recession-alert-acloh0
```

---

## 3. Instalar dependencias

Abre una terminal **en la carpeta del proyecto**:

**Windows (PowerShell):**
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Mac / Linux:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4. Configurar las claves

Copia la plantilla y rellénala:

**Windows:** `copy .env.example .env`  ·  **Mac/Linux:** `cp .env.example .env`

Edita `.env`:
```
FRED_API_KEY=tu_clave_de_fred
TELEGRAM_BOT_TOKEN=tu_token        # opcional
TELEGRAM_CHAT_ID=tu_chat_id        # opcional
```

> El proyecto carga `.env` solo. Si prefieres, exporta las variables a mano antes
> de ejecutar (ver más abajo).

---

## 5. Primer arranque — comprobar que entran datos reales

```bash
python -m cicloradar.cli check       # ¿claves puestas? ¿hosts alcanzables?
python -m cicloradar.cli probe       # prueba CADA API/serie una a una
```
`probe` te dice fuente por fuente qué responde ✅ y qué falla ❌. Si algo falla
(candidato: el código INE de visados), **pásame esa salida y lo corrijo**.

---

## 6. Los dos relojes en una foto

```bash
python -m cicloradar.cli panel
```
Verás el índice de **ciclo** (con datos reales de FRED/ECB/Eurostat) + el de
**fragilidad** (BIS/Eurostat/ECB/mercado, sin INE/BdE) + una **lectura conjunta**:

```
PANEL · Ciclo: 34/100 (VERDE)   ·   Fragilidad hogar: 29/100
🟢 Ciclo tranquilo y hogar con margen. Sin señales de alarma.
```

Otros comandos:
```bash
python -m cicloradar.cli run --save --notify   # ciclo + guarda histórico + Telegram
python -m cicloradar.cli fragility             # solo fragilidad
python -m cicloradar.cli qa --live             # control de calidad sobre datos reales
python -m cicloradar.cli verify --indicator hy_spread   # auditar momentum real
```

---

## 7. Dejarlo automático (cuando ya funcione bien)

- **Mac/Linux**: `deploy/crontab.example` o `deploy/cicloradar.timer` (systemd).
- **Windows**: Programador de tareas → acción `…\.venv\Scripts\python.exe -m
  cicloradar.cli run --save --notify`, mensual.
- Más adelante, al Hetzner: ver `deploy/SETUP.md`.

---

## Notas de realidad y rigor

- **Sin humo**: el cálculo es 100% reglas y aritmética, auditable (`verify`, `qa`).
- **Fuentes independientes** en fragilidad: BIS, Eurostat, ECB y mercado; se
  evitan INE/Banco de España como fuente de cabecera (posible sesgo político).
- **No es asesoramiento financiero.** Es un sistema de vigilancia macro.
- Si `probe` marca un `series_id` inválido, es un código a validar (OQ-04), no un
  fallo del motor. Mándame la salida y lo ajusto.
