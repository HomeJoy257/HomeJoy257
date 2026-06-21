"""
Notificador Telegram (FR-04). Alerta ACCIONABLE, no un número pelado:
estado · valor del índice · cobertura · qué bloques/indicadores tiran de la señal.

Usa la Bot API por HTTP (sin dependencias async). Requiere TELEGRAM_BOT_TOKEN y
TELEGRAM_CHAT_ID.
"""

from __future__ import annotations

from ..config import settings
from ..engine.aggregate import IndexPoint
from ..engine.alert import Alert, State
from .http_send import send_message

_EMOJI = {State.GREEN: "🟢", State.AMBER: "🟡", State.RED: "🔴"}


def format_alert(pt: IndexPoint, alert: Alert) -> str:
    emoji = _EMOJI[alert.state]
    cov = f"{pt.blocks_available}/5 bloques"
    delta = f"{alert.delta:+.0f}" if alert.delta is not None else "n/d"

    lines = [
        f"{emoji} *CicloRadar — {alert.state.value}*",
        "",
        f"📊 Índice de riesgo: *{pt.index}/100*  (Δ {delta})",
        f"🧩 Cobertura: {cov}  ·  gatillo: {alert.trigger}",
        f"📅 Periodo: {pt.period.isoformat()}",
        "",
        "*Qué tira de la señal:*",
    ]
    for name, score in pt.drivers(top=3):
        lines.append(f"  • {name}: {score:.0f}")
    top_inds = pt.top_indicators(top=3)
    if top_inds:
        lines.append("")
        lines.append("*Indicadores más tensionados:*")
        for ind in top_inds:
            lines.append(f"  • {ind.name}: {ind.score:.0f}")
    lines.append("")
    lines.append(f"_{alert.reason}_")
    return "\n".join(lines)


def notify(pt: IndexPoint, alert: Alert, *, only_non_green: bool = True) -> bool:
    """Envía la alerta. Si `only_non_green`, no molesta en VERDE."""
    if only_non_green and alert.state == State.GREEN:
        return False
    if not (settings.telegram_token and settings.telegram_chat_id):
        return False
    send_message(settings.telegram_token, settings.telegram_chat_id,
                 format_alert(pt, alert))
    return True
