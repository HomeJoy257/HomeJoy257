# RailRadar Alta Velocidad — MVP

Mapa en directo con **solo posiciones GPS reales** de los feeds oficiales de Renfe.
Sin interpolación ni map matching. Si la posición tiene más de **120 s** (según el
timestamp del *vehículo*), el tren no aparece.

```
Renfe (CKAN → GTFS-RT JSON)
   │  sondeo adaptativo + ETag/If-Modified-Since
collector ──► validación (ts vehículo, ≤120 s, bbox, 0,0) ──► Redis (TTL = 120 s − edad)
                                                                │ pub/sub
                                                    api (FastAPI: REST + SSE + web)
                                                                │
                                                    navegador (MapLibre, caduca con su reloj)
```

## Arrancar

### Con datos reales (Docker)
```bash
cd railradar
cp .env.example .env
docker compose up -d --build
open http://localhost:8000
docker compose logs -f collector     # ver qué acepta/rechaza
```

### Desarrollo sin Docker (feed SIMULADO)
```bash
cd railradar/backend
pip install -r requirements-dev.txt
python3 mock_feed.py &                                   # datos falsos en :8090
EMBEDDED_COLLECTOR=1 \
FEEDS=demo=http://127.0.0.1:8090/vehicle_positions.json \
uvicorn railradar.api:app --reload
# http://localhost:8000
```
Sin `REDIS_URL` usa memoria (un solo proceso).

### Tests
```bash
cd railradar/backend && python3 -m pytest -q
```

## API
| Endpoint | Qué devuelve |
|---|---|
| `GET /api/v1/trains/live` (`/geojson`) | GeoJSON de trenes con GPS ≤120 s. Filtros `?source=`, `?max_age=` |
| `GET /api/v1/trains/{source}:{id}` | Ficha de un tren (404 si no tiene GPS fresco) |
| `GET /api/v1/sources` | Estado de cada feed: periodo real, rechazos, mediana de antigüedad |
| `GET /api/v1/stats` | Visibles por fuente y por franja de antigüedad |
| `GET /api/v1/stream` | SSE: `hello`, `train.position`, `source.status` |
| `GET /health/live`, `/health/ready` | Salud |

## Solo alta velocidad
`PRODUCTS` filtra por el producto que Renfe asigna en su GTFS oficial (`routes.txt → route_short_name`,
cruzado por `trip_id`; 156/158 trenes casan): AVE, AVLO, AVE INT, EUROMED, AVANT, AVANT EXP, ALVIA.
Se excluyen MD, REGIONAL, REG.EXP., Intercity, PROXIMDAD, TRENCELTA. Si el índice GTFS no carga,
no se muestra ningún tren (fail-closed). Iryo y Ouigo no están: no publican datos abiertos.

## Reglas de datos (tras auditar Renfe con datos reales)
La auditoría del 31-10-2026 mostró que el `timestamp` de Cercanías es de **lote**
(no de la fijación GPS) y que AV/LD/MD **no trae hora por tren**. Por eso:
- La edad se mide desde que RailRadar **ve cambiar la coordenada**, no con la hora del feed.
- **Cercanías** (`strict`): solo se muestra si la coordenada cambió hace ≤120 s, o si Renfe dice `STOPPED_AT`.
  Al arrancar, hasta ver el primer cambio, la edad es desconocida y no se muestra.
- **AVE/LD/MD** (`unknown_age`): siempre en **gris**, rotulado "Renfe no publica la hora".
- **Estaciones**: evento real `STOPPED_AT`/`INCOMING_AT` del feed + retraso oficial (`trip_updates`).
  Coordenadas de estación del GTFS oficial de Renfe. Nunca se dibuja un tren entre estaciones.
- Un tren que deja de aparecer en el feed se retira a los 90 s.
- Coordenadas `0,0` o fuera de España → descartadas. Sin interpolación ni ajuste a la vía.
- **Solo Renfe**: Iryo y Ouigo no publican datos abiertos; Adif no tiene dataset abierto.
- **No apto para seguridad ferroviaria.**

## Mapa
- Teselas: OpenFreeMap (gratis, sin clave). Cambiar con `?style=https://…/style.json`.
- Color = frescura: verde 0–30 s, amarillo 30–90 s, naranja 90–120 s.
- Flecha = `bearing` del feed (solo si viene).

## Pendiente (fase 2)
- Histórico en Postgres (tabla particionada por día, `UNIQUE(train_id, observed_at)`).
- GTFS estático de Renfe para nombres/colores de línea.
- Soporte Protocol Buffers (más ligero que JSON).
- Proxy HTTPS (Caddy/nginx) con `proxy_buffering off` para SSE.
