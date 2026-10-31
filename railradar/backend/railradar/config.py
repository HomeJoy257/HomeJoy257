import os

MAX_AGE_SECONDS = 120
CLOCK_SKEW_TOLERANCE = 5          # s: ts ligeramente futuro por desfase de reloj
SPAIN_BBOX = (27.0, 45.0, -19.0, 5.0)  # lat_min, lat_max, lon_min, lon_max

REDIS_URL = os.getenv("REDIS_URL")            # vacío = memoria (dev)
EMBEDDED_COLLECTOR = os.getenv("EMBEDDED_COLLECTOR", "0") == "1"
CKAN_URL = os.getenv("CKAN_URL", "https://data.renfe.com/api/3/action")
CKAN_REFRESH_S = int(os.getenv("CKAN_REFRESH_S", "3600"))

# Feeds: "nombre=dataset_ckan" o "nombre=https://url-directa"
FEEDS = [
    tuple(x.split("=", 1))
    for x in os.getenv(
        "FEEDS",
        "renfe_cercanias=ubicacion-vehiculos,renfe_ld=posicion-vehiculos-av-ld-md",
    ).split(",")
    if "=" in x
]

# Política por feed: strict = solo GPS con edad medida ≤120 s; unknown_age = gris
FEED_POLICY = dict(
    x.split("=", 1) for x in os.getenv(
        "FEED_POLICY", "renfe_cercanias=strict,renfe_ld=unknown_age").split(",") if "=" in x
)
# Si un tren deja de aparecer en el feed, se retira tras este tiempo
PRESENCE_TTL_S = int(os.getenv("PRESENCE_TTL_S", "90"))

# Si el ts del vehículo == ts de cabecera, se descarta (puede ser hora de
# generación del fichero, no de la coordenada). Poner a 1 solo tras verificar
# con la auditoría que Renfe usa ts real por vehículo.
TRUST_TS_EQUAL_HEADER = os.getenv("TRUST_TS_EQUAL_HEADER", "0") == "1"

# Retrasos oficiales (GTFS-RT TripUpdates de Renfe): "nombre=dataset_o_url"
TRIP_UPDATE_FEEDS = [
    tuple(x.split("=", 1)) for x in os.getenv(
        "TRIP_UPDATE_FEEDS",
        "renfe_ld=horarios-viaje-alta-velocidad-larga-media-distancia,renfe_cercanias=horarios-viaje-cercanias",
    ).split(",") if "=" in x
]
STATIONS_ENABLED = os.getenv("STATIONS_ENABLED", "1") == "1"
STATION_EVENT_TTL_S = int(os.getenv("STATION_EVENT_TTL_S", "1800"))   # 30 min de historial
