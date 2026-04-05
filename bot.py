import os
import logging
from datetime import datetime
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
except ImportError:
    pass  # python-dotenv no instalado; usar variables de entorno del sistema
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

from helpers import parse_fecha, calcular_precio, construir_url

TOKEN    = os.environ.get("TELEGRAM_TOKEN")
if not TOKEN:
    raise RuntimeError("Falta la variable de entorno TELEGRAM_TOKEN. Crea un archivo .env o expórtala.")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

FECHA_INI, FECHA_FIN, PERSONAS = range(3)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text(
        "👋 Bienvenido a *Joy Caravaning* 🚐\n\n"
        "⭐ 4,9/5 · +297 familias · Asistencia 24/7\n\n"
        "📅 ¿Cuál es la *fecha de recogida*?\n"
        "Formato: DD/MM/YYYY — Ejemplo: 20/05/2026",
        parse_mode="Markdown"
    )
    return FECHA_INI

async def recibir_fecha_ini(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fecha = parse_fecha(update.message.text)
    if not fecha:
        await update.message.reply_text("❌ Formato incorrecto. Usa DD/MM/YYYY — Ejemplo: 20/05/2026")
        return FECHA_INI
    if fecha < datetime.now():
        await update.message.reply_text("❌ La fecha debe ser futura. Inténtalo de nuevo.")
        return FECHA_INI
    context.user_data["fecha_ini"] = fecha
    await update.message.reply_text(
        f"✅ Recogida: *{fecha.strftime('%d/%m/%Y')}*\n\n"
        "📅 ¿Fecha de *devolución*? — Ejemplo: 27/05/2026",
        parse_mode="Markdown"
    )
    return FECHA_FIN

async def recibir_fecha_fin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    fecha = parse_fecha(update.message.text)
    fi    = context.user_data["fecha_ini"]
    if not fecha:
        await update.message.reply_text("❌ Formato incorrecto. Usa DD/MM/YYYY — Ejemplo: 27/05/2026")
        return FECHA_FIN
    if fecha <= fi:
        await update.message.reply_text("❌ La devolución debe ser posterior a la recogida.")
        return FECHA_FIN
    noches = (fecha - fi).days
    context.user_data["fecha_fin"] = fecha
    context.user_data["noches"]    = noches
    await update.message.reply_text(
        f"✅ Devolución: *{fecha.strftime('%d/%m/%Y')}* — {noches} noches\n\n"
        "👥 ¿Cuántas *personas* viajáis? (2 a 6)",
        parse_mode="Markdown"
    )
    return PERSONAS

async def recibir_personas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = update.message.text.strip()
    if not texto.isdigit() or not (2 <= int(texto) <= 6):
        await update.message.reply_text("❌ Introduce un número entre 2 y 6.")
        return PERSONAS
    fi       = context.user_data["fecha_ini"]
    ff       = context.user_data["fecha_fin"]
    noches   = context.user_data["noches"]
    personas = int(texto)
    precio   = calcular_precio(noches)
    total    = precio * noches
    km       = "Ilimitado ✅" if noches >= 7 else f"Máx. {'800' if noches <= 3 else '1.600'} km (0,35€/km extra)"
    url      = construir_url(fi, ff, personas)
    await update.message.reply_text(
        f"🌄 *¡Aquí tienes tu aventura!*\n\n"
        f"📅 {fi.strftime('%d/%m/%Y')} → {ff.strftime('%d/%m/%Y')} ({noches} noches)\n"
        f"👥 {personas} personas\n\n"
        f"💶 Desde *{precio}€/noche* — Total orientativo: *{total}€*\n"
        f"🛣️ Kilometraje: {km}\n"
        f"✅ Asistencia 24/7 incluida\n\n"
        f"👉 *Ver autocaravanas disponibles:*\n"
        f"{url}\n\n"
        f"¿Dudas antes de reservar?\n"
        f"📞 +34 948 481 490 | Lun–Vie 10:00–18:00",
        parse_mode="Markdown",
        disable_web_page_preview=True
    )
    await update.message.reply_text("¿Otras fechas? Escribe /start")
    return ConversationHandler.END

async def cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelado. Escribe /start para empezar de nuevo.")
    return ConversationHandler.END

FAQ_TEXT = (
    "❓ *Preguntas Frecuentes — Joy Caravaning*\n\n"
    "🪪 *¿Qué carnet necesito?*\n"
    "Carnet B (coche). Todas nuestras autocaravanas pesan menos de 3.500 kg.\n\n"
    "💰 *¿Qué incluye el precio?*\n"
    "Seguro a todo riesgo, asistencia en carretera 24/7, kit de cocina, "
    "ropa de cama, mesa y sillas de exterior.\n\n"
    "🐾 *¿Se admiten mascotas?*\n"
    "Sí, con suplemento de limpieza (consultar al reservar).\n\n"
    "⛽ *¿Combustible?*\n"
    "Diésel. Se entrega con el depósito lleno y se devuelve lleno.\n\n"
    "🔑 *¿Fianza?*\n"
    "Entre 1.000€ y 1.500€ según el vehículo (se devuelve íntegra si no hay daños).\n\n"
    "🕐 *Horario de recogida/devolución?*\n"
    "Recogida: 10:00–13:00 · Devolución: 9:00–12:00\n\n"
    "🛣️ *Kilometraje*\n"
    "• 1–3 noches: máx. 800 km (0,35€/km extra)\n"
    "• 4–6 noches: máx. 1.600 km (0,35€/km extra)\n"
    "• 7+ noches: ilimitado ✅\n\n"
    "🚿 *¿Cómo funciona el agua?*\n"
    "Depósito de agua limpia (100–150L). Puedes rellenar en áreas de servicio "
    "o campings. El agua gris se vacía en puntos habilitados.\n\n"
    "🔌 *¿Electricidad?*\n"
    "Batería auxiliar + toma 230V para conectar en camping. "
    "Algunos modelos incluyen panel solar.\n\n"
    "📞 ¿Más dudas? Llámanos: *+34 948 481 490* (Lun–Vie 10:00–18:00)"
)

async def faq(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(FAQ_TEXT, parse_mode="Markdown")

async def mensaje_no_reconocido(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤔 No he entendido tu mensaje.\n\n"
        "Prueba con uno de estos comandos:\n"
        "/start — Buscar autocaravana disponible\n"
        "/faq — Preguntas frecuentes\n"
        "/cancelar — Cancelar la consulta actual"
    )

def main():
    app = Application.builder().token(TOKEN).build()
    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            FECHA_INI: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_fecha_ini)],
            FECHA_FIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_fecha_fin)],
            PERSONAS:  [MessageHandler(filters.TEXT & ~filters.COMMAND, recibir_personas)],
        },
        fallbacks=[CommandHandler("cancelar", cancelar)],
    )
    app.add_handler(conv)
    app.add_handler(CommandHandler("faq", faq))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, mensaje_no_reconocido))
    print("✅ Bot arrancado...")
    app.run_polling()

if __name__ == "__main__":
    main()
