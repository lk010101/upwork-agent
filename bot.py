import os
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
YOUR_CHAT_ID = os.environ.get("CHAT_ID", "")

print("====================================")
print("BOT FILE LOADED")
print("BOT_TOKEN EXISTS:", bool(BOT_TOKEN))
print("CHAT_ID:", YOUR_CHAT_ID)
print("====================================")


# ─────────────────────────────────────────────────────────────────────────────
# /start
# ─────────────────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    await update.message.reply_text(
        f"✅ Бот работает!\n\n"
        f"Твой Chat ID:\n"
        f"<code>{chat_id}</code>",
        parse_mode="HTML"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /status
# ─────────────────────────────────────────────────────────────────────────────
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 Бот активен\n"
        "🔍 Мониторинг включён"
    )


# ─────────────────────────────────────────────────────────────────────────────
# /settings
# ─────────────────────────────────────────────────────────────────────────────
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔑 Ключевые слова", callback_data="set_keywords")],
        [InlineKeyboardButton("💰 Минимальный бюджет", callback_data="set_budget")],
        [InlineKeyboardButton("📊 Статус фильтров", callback_data="show_filters")],
    ]

    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "⚙️ Настройки:",
        reply_markup=reply_markup
    )


# ─────────────────────────────────────────────────────────────────────────────
# Buttons
# ─────────────────────────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    if query.data == "show_filters":
        keywords = os.environ.get("KEYWORDS", "webflow, ux/ui")
        budget = os.environ.get("MIN_BUDGET", "100")

        await query.edit_message_text(
            f"📊 Фильтры:\n\n"
            f"Ключевые слова: {keywords}\n"
            f"Мин. бюджет: ${budget}"
        )

    elif query.data == "set_keywords":
        await query.edit_message_text(
            "Измени переменную KEYWORDS в Railway Variables."
        )

    elif query.data == "set_budget":
        await query.edit_message_text(
            "Измени переменную MIN_BUDGET в Railway Variables."
        )


# ─────────────────────────────────────────────────────────────────────────────
# Send job notification
# ─────────────────────────────────────────────────────────────────────────────
async def send_job_notification(app, job, draft):
    await app.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=f"Новая вакансия:\n\n{job}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def main():
    print("MAIN STARTED")

    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не найден в Railway Variables")

    print("TOKEN OK")

    app = Application.builder().token(BOT_TOKEN).build()

    print("APPLICATION CREATED")

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(button_handler))

    print("HANDLERS REGISTERED")

    logger.info("Бот запускается...")

    print("STARTING POLLING")

    app.run_polling()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    try:
        print("PROGRAM START")

        main()

    except Exception as e:
        print("====================================")
        print("FATAL ERROR:")
        print(repr(e))
        print("====================================")
        raise
