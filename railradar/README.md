# RailRadar España — MVP

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

## Reglas de datos (no negociables)
- Solo `vehicle.timestamp` del feed. Sin él → descartado.
- `vehicle.timestamp == header.timestamp` → descartado por defecto (podría ser la hora del fichero).
  Activar `TRUST_TS_EQUAL_HEADER=1` solo tras verificarlo con `audit/audit_feeds.py`.
- Antigüedad > 120 s, futura (>5 s), `0,0` o fuera de España → descartado.
- Nunca se sustituye una posición por estación, tramo u horario.
- Redis nunca acepta una posición más vieja que la que ya tiene.
- El navegador elimina el tren a los 120 s con su propio reloj (sincronizado con el servidor), aunque se corte el SSE.

## Mapa
- Teselas: OpenFreeMap (gratis, sin clave). Cambiar con `?style=https://…/style.json`.
- Color = frescura: verde 0–30 s, amarillo 30–90 s, naranja 90–120 s.
- Flecha = `bearing` del feed (solo si viene).

## Pendiente (fase 2)
- Histórico en Postgres (tabla particionada por día, `UNIQUE(train_id, observed_at)`).
- GTFS estático de Renfe para nombres/colores de línea.
- Soporte Protocol Buffers (más ligero que JSON).
- Proxy HTTPS (Caddy/nginx) con `proxy_buffering off` para SSE.
