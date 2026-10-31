"""Feed GTFS-RT JSON SIMULADO para desarrollo. NO son datos reales.

Uso: python3 mock_feed.py  ->  http://127.0.0.1:8090/vehicle_positions.json
Incluye a propósito casos que deben rechazarse (caducados, sin ts, 0,0).
"""
import json
import math
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEEDS = [  # puntos de partida aproximados, solo para la demo
    ("C1-001", 40.41, -3.69), ("C2-014", 41.38, 2.17), ("C3-007", 39.47, -0.38),
    ("C4-022", 37.39, -5.99), ("C5-003", 43.26, -2.93), ("AV-0310", 40.10, -3.20),
    ("AV-0402", 41.60, -0.90), ("MD-1201", 42.85, -2.67), ("LD-0700", 38.35, -0.48),
]
PERIOD = 20


def doc():
    now = int(time.time())
    pub = now - now % PERIOD                      # "publica" cada 20 s
    ents = []
    for i, (vid, lat, lon) in enumerate(SEEDS):
        lag = 3 + (i * 11) % 100                   # antigüedad variada 3..102 s
        t = pub - lag
        ang = (t / 600 + i) % (2 * math.pi)
        ents.append({"id": f"e{i}", "vehicle": {
            "trip": {"tripId": f"T{vid}", "routeId": vid.split("-")[0]},
            "vehicle": {"id": vid, "label": vid},
            "position": {"latitude": lat + 0.05 * math.sin(ang), "longitude": lon + 0.05 * math.cos(ang),
                         "bearing": math.degrees(ang) % 360},
            "timestamp": str(t)}})
    ents += [  # deben ser rechazados
        {"id": "stale", "vehicle": {"vehicle": {"id": "OLD-1"}, "position": {"latitude": 40, "longitude": -4},
                                    "timestamp": str(pub - 900)}},
        {"id": "nots", "vehicle": {"vehicle": {"id": "NOTS-1"}, "position": {"latitude": 40, "longitude": -4}}},
        {"id": "zero", "vehicle": {"vehicle": {"id": "ZERO-1"}, "position": {"latitude": 0, "longitude": 0},
                                   "timestamp": str(pub - 5)}},
    ]
    return {"header": {"gtfsRealtimeVersion": "2.0", "timestamp": str(pub)}, "entity": ents}, pub


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        body, pub = doc()
        etag = f'"{pub}"'
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304); self.end_headers(); return
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("ETag", etag)
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Mock GTFS-RT en http://127.0.0.1:8090/vehicle_positions.json (DATOS SIMULADOS)")
    ThreadingHTTPServer(("127.0.0.1", 8090), H).serve_forever()
