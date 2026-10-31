"""Feeds GTFS-RT SIMULADOS para desarrollo. NO son datos reales.

Imita lo que la auditoría vio en Renfe (31-10-2026):
  /vehicle_positions.json     Cercanías: timestamp de lote, coordenada a veces congelada
  /vehicle_positions_LD.json  AV/LD/MD: SIN timestamp por vehículo
  /trip_updates_LD.json       retrasos
  /gtfs.zip                   stops.txt
Uso: python3 mock_feed.py   ->  http://127.0.0.1:8090/...
"""
import io, json, math, time, zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STOPS = {"60000": ("Madrid Pta. de Atocha", 40.4065, -3.6896), "71801": ("Barcelona Sants", 41.3792, 2.1400),
         "65000": ("València Joaquín Sorolla", 39.4594, -0.3829), "51003": ("Sevilla Santa Justa", 37.3917, -5.9750),
         "50500": ("Córdoba", 37.8888, -4.7894), "04040": ("Zaragoza Delicias", 41.6585, -0.9112)}
LD = [  # (tren, origen, destino, producto) – recorridos ficticios entre estaciones reales
    ("03063", "60000", "71801", "AVE"), ("02151", "60000", "51003", "AVE"), ("05121", "60000", "65000", "AVLO"),
    ("02260", "51003", "60000", "ALVIA"), ("03190", "71801", "60000", "AVE"), ("08155", "50500", "51003", "AVANT"),
    ("17041", "60000", "04040", "MD"), ("15012", "65000", "60000", "REG.EXP."),
]
CER = [("C1-23542", 40.42, -3.70), ("C2-23015", 41.38, 2.17), ("C3-23801", 39.47, -0.38), ("C5-23721", 37.36, -6.21)]
PERIOD = 20


def lerp(a, b, f):
    return a + (b - a) * f


def ld_doc(now):
    pub = now - now % PERIOD
    ents = []
    for i, (num, o, d, _p) in enumerate(LD):
        f = ((pub / 3600 + i / len(LD)) % 1.0)
        if f > 0.7:                            # parado en destino
            lat, lon, st, sid = STOPS[d][1], STOPS[d][2], "STOPPED_AT", d
        else:
            g = f / 0.7
            lat, lon = lerp(STOPS[o][1], STOPS[d][1], g), lerp(STOPS[o][2], STOPS[d][2], g)
            st, sid = ("IN_TRANSIT_TO", d)
        ents.append({"id": f"VP_{num}", "vehicle": {"trip": {"tripId": f"{num}D"}, "vehicle": {"id": num, "label": f"AVE-{num}"},
                     "position": {"latitude": round(lat, 6), "longitude": round(lon, 6)},
                     "currentStatus": st, "stopId": sid}})
    return {"header": {"gtfsRealtimeVersion": "2.0", "timestamp": str(pub - 3600)}, "entity": ents}, pub


def cer_doc(now):
    pub = now - now % PERIOD
    ents = []
    for i, (lab, lat, lon) in enumerate(CER):
        frozen = (pub // 60 + i) % 3 == 0      # 1 de cada 3 minutos: coordenada congelada
        t = (pub - (pub % 60) if frozen else pub) / 300 + i
        ents.append({"id": f"VP_{lab}", "vehicle": {"trip": {"tripId": f"T{lab}"}, "vehicle": {"id": lab.split('-')[1], "label": lab},
                     "position": {"latitude": round(lat + 0.03 * math.sin(t), 6), "longitude": round(lon + 0.03 * math.cos(t), 6)},
                     "currentStatus": "IN_TRANSIT_TO", "timestamp": str(pub - 10)}})
    ents.append({"id": "zero", "vehicle": {"vehicle": {"id": "ZERO"}, "position": {"latitude": 0, "longitude": 0}, "timestamp": str(pub)}})
    return {"header": {"timestamp": str(pub)}, "entity": ents}, pub


def tu_doc(now):
    ents = [{"id": f"TU_{n}", "tripUpdate": {"trip": {"tripId": f"{n}D"}, "delay": (i * 137) % 900}} for i, (n, *_r) in enumerate(LD)]
    return {"header": {"timestamp": str(now)}, "entity": ents}, now // 30


def gtfs_zip():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("stops.txt", "stop_id,stop_name,stop_lat,stop_lon\n" +
                   "\n".join(f"{k},{v[0]},{v[1]},{v[2]}" for k, v in STOPS.items()))
        z.writestr("routes.txt", "route_id,agency_id,route_short_name,route_type\n" +
                   "\n".join(f"R{n},1071,{p},2" for n, _, _, p in LD))
        z.writestr("trips.txt", "route_id,service_id,trip_id,trip_short_name\n" +
                   "\n".join(f"R{n},S,{n}D,{n}" for n, _, _, _ in LD))
    return buf.getvalue()


class H(BaseHTTPRequestHandler):
    def do_GET(self):
        now = int(time.time())
        route = {"/vehicle_positions.json": cer_doc, "/vehicle_positions_LD.json": ld_doc, "/trip_updates_LD.json": tu_doc}
        if self.path == "/gtfs.zip":
            data, ctype, etag = gtfs_zip(), "application/zip", '"gtfs"'
        elif self.path in route:
            body, ver = route[self.path](now)
            data, ctype, etag = json.dumps(body).encode(), "application/json", f'"{ver}"'
        else:
            self.send_response(404); self.end_headers(); return
        if self.headers.get("If-None-Match") == etag:
            self.send_response(304); self.end_headers(); return
        self.send_response(200)
        self.send_header("Content-Type", ctype); self.send_header("ETag", etag)
        self.end_headers(); self.wfile.write(data)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Mock Renfe en http://127.0.0.1:8090 (DATOS SIMULADOS)")
    ThreadingHTTPServer(("127.0.0.1", 8090), H).serve_forever()
