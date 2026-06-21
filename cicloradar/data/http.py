"""Cliente HTTP con reintentos y backoff exponencial. Único punto de red."""

from __future__ import annotations

import time

import requests

from ..config import settings


class EgressBlocked(RuntimeError):
    """El host no está en el allowlist de egress del entorno."""


def get(url: str, params: dict | None = None, *, timeout: int | None = None) -> requests.Response:
    timeout = timeout or settings.http_timeout
    last_exc: Exception | None = None
    for attempt in range(settings.http_retries):
        try:
            r = requests.get(url, params=params, timeout=timeout,
                             headers={"User-Agent": "CicloRadar/0.1 (macro research)"})
            if r.status_code == 403 and "not in allowlist" in r.text.lower():
                raise EgressBlocked(r.text.strip()[:200])
            r.raise_for_status()
            return r
        except EgressBlocked:
            raise  # no reintentar: es config del entorno, no transitorio
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < settings.http_retries - 1:
                time.sleep(2 ** (attempt + 1))  # 2s, 4s, 8s, 16s
    raise RuntimeError(f"GET {url} falló tras {settings.http_retries} intentos: {last_exc}")
