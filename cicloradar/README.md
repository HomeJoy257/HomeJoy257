# CicloRadar — Sistema de Alerta Temprana de Recesión (España)

Índice continuo **0-100** de riesgo de recesión para la economía española,
**100 % determinista** (reglas y aritmética, sin ML), construido sobre datos
**point-in-time** y la cronología oficial del **Comité de Fechado del Ciclo
(CFC)** de la Asociación Española de Economía.

Implementa el spec funcional v0.1. El índice no predice fecha ni horizonte:
mide cuánto se parecen las condiciones macro actuales a las observadas justo
antes de las recesiones históricas, y emite alertas escalonadas a Telegram.

---

## Arranque rápido

```bash
pip install -r requirements.txt

# 1) Demo offline (datos sintéticos deterministas; prueba el pipeline entero)
python -m cicloradar.cli demo

# 2) Diagnóstico de entorno (claves + egress)
python -m cicloradar.cli check

# 3) Fetch en vivo + índice + alerta (requiere FRED_API_KEY y egress abierto)
export FRED_API_KEY=xxxx
python -m cicloradar.cli run --save --notify

# 4) Ver el histórico almacenado
python -m cicloradar.cli history

# 5) Verificar el cálculo de momentum (auditable, paso a paso)
python -m cicloradar.cli verify                       # muestra fija + comprobación a mano
python -m cicloradar.cli verify --csv tus_datos.csv   # datos REALES sin red (YYYY-MM,valor)
python -m cicloradar.cli verify --indicator hy_spread # serie real en vivo (egress + key)
```

Flags de `run`/`demo`: `--save` (persiste en SQLite), `--notify` (Telegram si no
es VERDE), `--json` (salida JSON).

---

## ⚠️ Egress / red

Este repo se ha desarrollado en un entorno con **egress bloqueado**. Para el
fetch en vivo, los siguientes hosts deben estar en el **allowlist de egress** de
tu entorno (o ejecútalo en tu servidor — Hetzner cron, OQ-06):

```
api.stlouisfed.org        # FRED / ALFRED (point-in-time)
data-api.ecb.europa.eu    # ECB Data Portal (curva, BLS)
ec.europa.eu              # Eurostat (ESI)
servicios.ine.es          # INE Tempus3 (visados)
api.telegram.org          # alertas
```

`python -m cicloradar.cli check` te dice cuáles están alcanzables.

---

## Arquitectura

```
cicloradar/
├── constants/
│   ├── cfc_chronology.py     # GROUND TRUTH: recesiones CFC (versionado)
│   ├── structural_breaks.py  # FR-02: registro de rupturas + política en cascada
│   └── series_registry.py    # OQ-04: 8 indicadores / 5 bloques, fuentes, pesos
├── data/
│   ├── base.py               # Series + limpieza (sin ruido, mensual, sin dup)
│   ├── http.py               # cliente HTTP con backoff exponencial
│   ├── fred.py               # FRED/ALFRED — point-in-time (get_series_as_of)
│   ├── ecb.py, eurostat.py, ine.py
│   ├── fetcher.py            # orquesta: fuentes → transform → ruptura → limpio
│   └── demo.py               # dataset sintético determinista (offline)
├── engine/
│   ├── percentile.py         # percentiles y momentum (Python puro)
│   ├── aggregate.py          # FR-01/03: nivel+momentum, bloques, cobertura
│   └── alert.py              # FR-04: VERDE/ÁMBAR/ROJO, doble gatillo, persistencia
├── storage/history.py        # OQ-06: histórico en SQLite (stack mínimo)
├── notify/telegram.py        # FR-04: alerta accionable a Telegram
├── report.py                 # informe limpio en consola
└── cli.py                    # demo / run / check / history
```

### Cómo se calcula el índice (determinista)

1. **Orientación**: cada indicador se orienta con su `direction` para que
   *"más alto = más riesgo"* siempre.
2. **Nivel y momentum**: `level_score` = percentil del valor en su propia
   historia; `momentum_score` = percentil del Δ sobre la ventana. Se calculan
   **dos ventanas** (OQ-05): 3 meses (primaria, gobierna la alerta) y 6 meses
   (secundaria, se muestra como comparación). `indicator_score = level_w·nivel + momentum_w·momentum`.
   (IBEX es **momentum puro**.)
3. **Bloques**: cada bloque = media de sus indicadores vivos. **5 bloques,
   1/5 cada uno** (pesos por bloque, no por indicador → la economía real no
   queda aplastada por las financieras).
4. **Renormalización**: si falta un bloque, su peso se reparte entre los vivos
   (los pesos siempre suman 1).
5. **Índice 0-100**: percentil del compuesto sobre su **rango histórico**
   (0 = mejor lectura, 100 = peor).
6. **Cobertura**: siempre acompaña al índice (`bloques con dato / 5`).

**Hard blocks respetados**: pesos fijos (prohibido optimizar), umbrales por
percentil del propio índice (no absolutos ni optimizados), empalme casero
prohibido.

### Regla de alerta (FR-04)

- **Doble gatillo**: por **nivel** (índice ≥ p80 ámbar / p90 rojo) **o** por
  **aceleración** (Δ índice ≥ umbral).
- **Persistencia**: ROJO exige 2 lecturas consecutivas; ÁMBAR basta 1.
- **Payload**: estado · índice · cobertura · **qué bloques/indicadores tiran de
  la señal**.

---

## Resolución de Open Questions (arranque, no definitivo)

| OQ | Decisión de arranque (editable en `config.py` / env) |
|----|------|
| **OQ-01** cadencia | Recálculo mensual vía cron (`run`). Día fijo recomendado tras release ESI. |
| **OQ-02** umbrales | Como el índice ya es percentil, ámbar=80, rojo=90 (literal). |
| **OQ-03** aceleración | ámbar Δ≥10, rojo Δ≥15 puntos/mes (a recalibrar sobre histórico real, sin optimizar). |
| **OQ-04** series | Ver `series_registry.py`. Validadas en FRED las point-in-time; INE/ECB/Eurostat marcadas como confirmación. `visados` lleva código INE **provisional a validar**. |
| **OQ-05** ventana momentum | Se calculan **ambas**: 3m primaria (gobierna la alerta) + 6m secundaria (comparación). `MOMENTUM_WINDOW` / `MOMENTUM_WINDOW_ALT`. |
| **OQ-06** almacenamiento | SQLite en fichero (sin servidor). Cron en Hetzner. |

---

## Notas de integridad

- **CFC**: 7 episodios granulares 1974-2020 (el spec cita "6"; fusionar
  1978-1981 reproduce 6). Es **dato versionado**, no se ajusta al índice.
- **Point-in-time real** solo en FRED/ALFRED (`get_series_as_of`). ECB/Eurostat/
  INE no tienen vintage nativo → **sesgo documentado**, entran como confirmación.
- **El demo no es dato real.** Es un generador sintético determinista para
  probar el pipeline sin red. Para decisiones, `run` con datos reales.

## Tests

```bash
python -m pytest tests/ -q     # 15 tests deterministas, sin red
```
