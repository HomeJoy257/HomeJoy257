# Fuentes de datos reales — CicloRadar

España y la UE publican estos datos por **API pública gratuita**. El sistema ya
está cableado a ellas. La tabla mapea cada indicador a su API real.

> El único motivo por el que no se descargan desde el sandbox de Claude Code web
> es el **egress bloqueado** (`Host not in allowlist`). En tu servidor (Hetzner)
> o con los hosts en el allowlist del entorno, fluyen sin tocar el código.

## Mapa indicador → API real

| Indicador | Bloque | API real (pública) | Key | Vintage |
|-----------|--------|--------------------|-----|---------|
| Curva euro 10y−2y | Tipos | **ECB Data Portal** `data-api.ecb.europa.eu` (dataset YC) | No | No |
| Prima de riesgo ES (10y−Bund) | Tipos | **FRED/ALFRED** `IRLTLT01ESM156N` − `IRLTLT01DEM156N` | Sí (gratis) | **Sí** |
| Bank Lending Survey | Crédito | **ECB Data Portal** (dataset BLS) | No | No |
| Spread HY euro (OAS) | Crédito | **FRED/ALFRED** `BAMLHE00EHYIOAS` | Sí (gratis) | **Sí** |
| ESI España | Confianza | **Eurostat** `ec.europa.eu` (`ei_bssi_m_r2`) / DG ECFIN | No | No |
| Visados obra nueva | Actividad | **INE Tempus3** `servicios.ine.es` | **No** | No |
| IBEX 35 (momentum) | Mercado | **FRED/ALFRED** `SPASTT01ESM661N` (OECD share prices ES) | Sí (gratis) | **Sí** |
| M1 real | Mercado | **FRED/ALFRED** `MANMM101EZM189S` / HICP `CP0000EZ19M086NEST` | Sí (gratis) | **Sí** |

**Alternativas/duplicados de calidad (todas gratis):**
- **Banco de España** (`www.bde.es`, capítulos estadísticos) — prima de riesgo,
  tipos, agregados monetarios. Buen duplicado nacional.
- **datos.gob.es** (`apidata`) — catálogo abierto del Estado.
- **ECB** también tiene Spain 10Y (dataset IRS) y M1 euro — duplican FRED sin key.

El **point-in-time** (lo que se sabía en cada pico, clave del spec) solo lo da
**FRED/ALFRED** vía `get_series_as_of`. INE/ECB/Eurostat entran como confirmación
(sin vintage nativo → sesgo documentado en el código).

## Cómo conseguir el feed real (elige una)

### A) Producción en tu servidor (Hetzner) — recomendado (OQ-06)
No tiene egress bloqueado. Ver `deploy/SETUP.md`. En 5 minutos:
```bash
git clone <repo> && cd HomeJoy257
bash deploy/setup.sh          # venv + deps + .env
nano .env                     # pon FRED_API_KEY (gratis) y Telegram
python -m cicloradar.cli check   # debe dar ✅ alcanzable
python -m cicloradar.cli run --save --notify   # datos REALES
```
Luego el cron mensual (también en `deploy/`).

### B) En Claude Code web — abrir el allowlist del entorno
El entorno se creó con una política de red restrictiva. Para datos reales aquí,
añade estos hosts al **egress allowlist** del entorno (Settings de red del
entorno en claude.ai/code):
```
api.stlouisfed.org
data-api.ecb.europa.eu
ec.europa.eu
servicios.ine.es
api.telegram.org
```
Docs: https://code.claude.com/docs/en/claude-code-on-the-web

## FRED API key (gratis, 1 minuto)
https://fred.stlouisfed.org/docs/api/api_key.html → pegar en `.env` como
`FRED_API_KEY=...`. Sin key, los 5 indicadores FRED no cargan (los de ECB/INE/
Eurostat sí, sin key).
