import logging
from datetime import datetime
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)

TOKEN    = "8777144457:AAFUEAviXipFH0nQCdCtguvB6gOJR15n73I"
BASE_URL = "https://joycaravaning.com/product-category/alquiler/?swoof=1&fecha_ini={fi}&fecha_fin={ff}&paged=1&tax_plazas-dormir={plazas}&tax_plazas={plazas}-plazas&really_curr_tax=104-product_cat"

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

FECHA_INI, FECHA_FIN, PERSONAS = range(3)

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
    print("✅ Bot arrancado...")
    app.run_polling()

if __name__ == "__main__":
    main()
