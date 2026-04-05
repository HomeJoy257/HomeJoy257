"""Tests unitarios para las funciones del bot de Joy Caravaning."""
from datetime import datetime
from helpers import parse_fecha, calcular_precio, construir_url


# --- parse_fecha ---

def test_parse_fecha_formato_barra():
    resultado = parse_fecha("20/05/2026")
    assert resultado == datetime(2026, 5, 20)

def test_parse_fecha_formato_guion():
    resultado = parse_fecha("20-05-2026")
    assert resultado == datetime(2026, 5, 20)

def test_parse_fecha_con_espacios():
    resultado = parse_fecha("  20/05/2026  ")
    assert resultado == datetime(2026, 5, 20)

def test_parse_fecha_invalida():
    assert parse_fecha("not-a-date") is None

def test_parse_fecha_formato_incorrecto():
    assert parse_fecha("2026/05/20") is None

def test_parse_fecha_vacia():
    assert parse_fecha("") is None


# --- calcular_precio ---

def test_precio_corta_estancia():
    assert calcular_precio(1) == 145
    assert calcular_precio(3) == 145
    assert calcular_precio(6) == 145

def test_precio_media_estancia():
    assert calcular_precio(7) == 135
    assert calcular_precio(14) == 135
    assert calcular_precio(20) == 135

def test_precio_larga_estancia():
    assert calcular_precio(21) == 125
    assert calcular_precio(30) == 125


# --- construir_url ---

def test_construir_url_formato():
    fi = datetime(2026, 5, 20)
    ff = datetime(2026, 5, 27)
    url = construir_url(fi, ff, 4)
    assert "fecha_ini=20-05-2026" in url
    assert "fecha_fin=27-05-2026" in url
    assert "tax_plazas-dormir=4" in url
    assert "tax_plazas=4-plazas" in url

def test_construir_url_dos_personas():
    fi = datetime(2026, 6, 1)
    ff = datetime(2026, 6, 5)
    url = construir_url(fi, ff, 2)
    assert "tax_plazas-dormir=2" in url
