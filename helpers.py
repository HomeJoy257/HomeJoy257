"""Funciones auxiliares puras del bot de Joy Caravaning."""
from datetime import datetime

BASE_URL = "https://joycaravaning.com/product-category/alquiler/?swoof=1&fecha_ini={fi}&fecha_fin={ff}&paged=1&tax_plazas-dormir={plazas}&tax_plazas={plazas}-plazas&really_curr_tax=104-product_cat"


def parse_fecha(texto):
    for fmt in ("%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(texto.strip(), fmt)
        except ValueError:
            continue
    return None


def calcular_precio(noches):
    if noches <= 6:
        return 145
    elif noches <= 20:
        return 135
    else:
        return 125


def construir_url(fi, ff, personas):
    return BASE_URL.format(
        fi=fi.strftime("%d-%m-%Y"),
        ff=ff.strftime("%d-%m-%Y"),
        plazas=personas
    )
