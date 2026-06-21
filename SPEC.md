# Spec: CicloRadar — Sistema de Alerta Temprana de Recesión (España)
Version: 0.1 | Date: 2026-06-21 | Status: DRAFT
> Nombre provisional. Encaja en la familia *Radar*; renombrable.

## 1. Overview

CicloRadar es un sistema determinista que calcula un **índice continuo de riesgo de recesión (0-100)** para la economía española. El índice no predice una fecha ni un horizonte: mide **cuánto se parecen las condiciones macro actuales a las observadas justo antes de las recesiones históricas**.

El ground truth son las recesiones fechadas por el **Comité de Fechado del Ciclo (CFC) de la Asociación Española de Economía** (equivalente español al NBER): 6 recesiones desde 1970. El sistema construye la "firma" pre-recesión a partir de datos **point-in-time** (lo que se sabía en cada momento, no la serie revisada) y puntúa el estado actual contra esa firma, emitiendo alertas escalonadas a Telegram.

Filosofía: determinista primero, eval-driven, cero optimización de parámetros contra el histórico (solo hay 6 episodios → cualquier ajuste fino sobreajusta).

## 2. Users & Actors

- **Operador / decisor (Ramón):** consume el índice y las alertas para decisiones de negocio (stock, caja, timing) en un sector de ticket alto y financiado, sensible al ciclo.
- **Sistema (automatizado):** ingiere datos, recalcula el índice con cadencia fija, evalúa la regla de alerta, notifica.
- **Receptor de alertas:** bot de Telegram.

## 3. Functional Requirements

### FR-01 — Índice de riesgo
- **Output:** índice continuo **0-100**.
- **Escala:** percentil sobre el **rango histórico** del propio índice (0 = mejor lectura registrada desde 1970; 100 = peor). No es distancia a una "media de picos" (descartado: con n=6 el centroide es inestable y los episodios son heterogéneos).
- **Composición:** núcleo de indicadores **adelantados** (ver FR-03).
- **Señal:** combina **nivel** (percentil del valor) **y momentum** (percentil del cambio). El momentum es crítico: 2008 y 2020 avisaron por deterioro rápido desde buen nivel, no por nivel malo sostenido.
- **Given/When/Then:** *Given* un mes con datos disponibles, *When* se recalcula, *Then* devuelve un entero 0-100 + su descomposición por bloque.

### FR-02 — Registro de rupturas estructurales
Segundo modo de fallo, **independiente** del de revisiones. El point-in-time corrige revisiones del *mismo* concepto; no corrige que el concepto **cambie de definición**.
- **Componente:** constante versionada (como la cronología CFC) que lista por serie los cambios de definición conocidos. Ejemplos: reforma laboral 2022 (fijos discontinuos), cambios de base del PIB (SEC-95 → ESA-2010), rebases del IPC.
- **Política en cascada** ante una ruptura conocida:
  1. ¿Existe enlace **oficial/publicado**? → empalmar con la serie enlazada oficial *(default)*.
  2. ¿No hay enlace pero el tramo post-ruptura cubre ciclo suficiente? → excluir el tramo pre-ruptura.
  3. ¿El tramo post-ruptura es tan corto que el percentil pierde sentido? → descartar el indicador.
- **Hard block:** **empalme casero prohibido** en cualquier serie que alimente el índice (contaminaría el ground truth con supuestos de modelado).
- Cada decisión queda **logueada** (serie, ruptura, política aplicada, motivo).

### FR-03 — Agregación
- **8 indicadores adelantados** agrupados en **5 bloques temáticos**. Cada **bloque** pesa **1/5**; reparto igual dentro del bloque. (Pesos iguales por bloque, no por indicador, para que la economía real no quede aplastada por las series financieras, que son más numerosas.)

  | Bloque | Indicadores |
  |---|---|
  | Tipos | Curva euro (10y−2y Bund) · Prima de riesgo España (bono ES 10y − Bund) |
  | Crédito | Bank Lending Survey (BCE) · Spread corporativo HY euro |
  | Confianza | ESI (Comisión Europea) |
  | Actividad real | Visados de obra nueva |
  | Mercado / monetario | IBEX 35 (momentum) · M1 real |

- **Cobertura desigual:** no todas las series ven las 6 recesiones (varias arrancan ~1999 → solo ven 2008/2011/COVID). Se registra por indicador cuántos picos CFC alcanza.
- **Renormalización:** si un bloque carece de datos en una fecha, su peso se reparte entre los bloques vivos (los pesos siempre suman 1).
- **Cobertura visible:** el índice se acompaña SIEMPRE de un indicador de cobertura (bloques con dato / 5). Un 80 con 5/5 ≠ un 80 con 2/5.
- **Hard block:** pesos fijos, **prohibido optimizarlos** contra el histórico.

### FR-04 — Regla de alerta
- **3 estados:** VERDE (sin aviso) / ÁMBAR (vigilancia) / ROJO (alerta).
- **Umbrales:** percentiles de la distribución histórica **del propio índice** (no valores absolutos ni optimizados). Punto de partida: ámbar = p80, rojo = p90 (a confirmar sobre la distribución real → OQ-02).
- **Doble gatillo:** dispara por **nivel** (índice ≥ umbral) **o** por **aceleración** (variación del índice ≥ umbral de cambio). La aceleración recupera el momentum en la capa de alerta para no llegar tarde a crisis rápidas.
- **Persistencia:** transición a ROJO exige **2 lecturas consecutivas**; ÁMBAR puede dispararse con 1.
- **Payload Telegram:** estado · valor del índice · cobertura de bloques · **qué bloques/indicadores tiran de la señal** (una alerta accionable, no un número pelado).

## 4. Non-Functional Requirements

- **GDPR / residencia:** solo datos macro públicos y agregados, **sin PII** → riesgo bajo. Sin llamadas a APIs que traten datos personales.
- **Coste:** APIs gratuitas. FRED (key gratuita), INE Tempus3 / ECB Data Portal / Eurostat (sin key). Stack mínimo.
- **Determinismo:** el índice es 100% reglas y aritmética. Sin modelo ML en el cálculo. Reproducible y auditable.
- **Datos point-in-time:** backbone **FRED/ALFRED** (`get_series_as_of_date`) para construir la firma con lo que se sabía en cada pico. INE/ECB/Eurostat entran como confirmación (sin vintage nativo → documentar el sesgo).
- **Cadencia:** recálculo mensual (la mayoría de adelantadas son mensuales; BLS es trimestral). Exacta → OQ-01.

## 5. Out of Scope (v0.1)

- No predice fecha ni horizonte de recesión (FR-01 es índice sin horizonte).
- No optimiza pesos ni umbrales contra el histórico (hard block transversal).
- No usa **paro registrado SEPE** (ruptura de definición 2022 no declarada; el más distorsionable).
- No usa empalmes caseros.
- No es asesoramiento financiero ni de inversión.
- No incluye dashboard visual: solo índice + alerta Telegram. UI queda para fase posterior.

## 6. Open Questions

- **OQ-01:** cadencia exacta de ejecución (día fijo mensual vs trigger por release de datos).
- **OQ-02:** valores de arranque de umbrales (ámbar p80 / rojo p90) — confirmar tras ver la distribución histórica real del índice.
- **OQ-03:** umbral de aceleración (qué variación dispara ámbar) — calcular sobre histórico.
- **OQ-04:** serie concreta y **validada** por cada indicador (series_id FRED + códigos INE/ECB/Eurostat). Validación en Plan.
- **OQ-05:** ventana de momentum (3 vs 6 meses) para el percentil del cambio.
- **OQ-06:** ejecución y almacenamiento del histórico del índice (Hetzner cron vs n8n; Airtable vs Postgres vs fichero).

## 7. Technical Plan (Phase 2)

Implementado en `cicloradar/` (ver `cicloradar/README.md`). Resumen de decisiones
de arranque de las Open Questions y trazabilidad de cada requisito funcional a su
módulo allí documentados.
