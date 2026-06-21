"""Envío a la Bot API de Telegram por HTTP (con los reintentos del cliente)."""

from __future__ import annotations

from ..data.http import get


def send_message(token: str, chat_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    # La Bot API acepta parámetros por query string en GET.
    get(url, {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": "true",
    })
