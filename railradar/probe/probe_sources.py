#!/usr/bin/env python3
"""Sondeo de fuentes públicas para la capa 'pasos por estación' y para
coordenadas de estaciones. Solo GET a páginas/catálogos públicos; guarda lo
recibido para revisión manual. No usa claves ni APIs privadas."""
import json, re, sys, urllib.request, urllib.parse, gzip
from pathlib import Path

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "probe_out"); OUT.mkdir(parents=True, exist_ok=True)
UA = "Mozilla/5.0 (RailRadar research probe)"

def get(url, name):
    rec = {"url": url}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
            rec.update(status=r.status, final_url=r.geturl(), ctype=r.headers.get("Content-Type"), bytes=len(body))
            (OUT / name).write_bytes(body[:3_000_000])
            return body, rec
    except Exception as e:
        rec["error"] = f"{type(e).__name__}: {e}"
    return b"", rec

log = []
# 1) Renfe CKAN: datasets de horarios (GTFS estático) y trip updates
for q in ["horarios", "gtfs", "estaciones", "retrasos", "trip updates"]:
    b, rec = get(f"https://data.renfe.com/api/3/action/package_search?q={urllib.parse.quote(q)}&rows=50",
                 f"ckan_{q.replace(' ', '_')}.json")
    if b:
        try:
            res = json.loads(b)["result"]["results"]
            rec["datasets"] = [{"name": p["name"], "title": p.get("title"),
                                "resources": [(x.get("name"), x.get("format"), x.get("url")) for x in p.get("resources", [])]}
                               for p in res]
        except Exception as e:
            rec["parse_error"] = str(e)
    log.append(rec)

# 2) Adif: páginas públicas de información de viajeros
for url, name in [
    ("https://www.adif.es/", "adif_home.html"),
    ("https://www.adif.es/w/60000-madrid-pta.-de-atocha", "adif_station_atocha.html"),
    ("https://www.adif.es/robots.txt", "adif_robots.txt"),
    ("https://info.adif.es/", "info_adif.html"),
]:
    b, rec = get(url, name)
    if b:
        txt = b.decode("utf-8", "replace")
        rec["api_like_urls"] = sorted(set(re.findall(r"https?://[a-zA-Z0-9.\-]*adif[a-zA-Z0-9.\-]*/[^\s\"'<>]{0,120}", txt)))[:80]
        rec["mentions"] = {k: len(re.findall(k, txt, re.I)) for k in ["iryo", "ouigo", "salidas", "llegadas", "circulacion", "api"]}
    log.append(rec)

# 3) Datos abiertos del Estado: ¿hay algo de Adif / Iryo / Ouigo?
for q in ["adif circulaciones", "iryo", "ouigo", "trenes tiempo real"]:
    b, rec = get(f"https://datos.gob.es/apidata/catalog/dataset/title/{urllib.parse.quote(q)}?_pageSize=50",
                 f"datosgob_{q.replace(' ', '_')}.json")
    if b:
        try:
            items = json.loads(b)["result"]["items"]
            rec["datasets"] = [(i.get("title"), i.get("_about")) for i in items][:50]
        except Exception as e:
            rec["parse_error"] = str(e)
    log.append(rec)

(OUT / "probe_log.json").write_text(json.dumps(log, indent=2, ensure_ascii=False, default=str))
print(json.dumps(log, indent=1, ensure_ascii=False, default=str)[:20000])
