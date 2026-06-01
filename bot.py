import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
YOUR_CHAT_ID = os.environ.get("CHAT_ID", "")


# ── Команда /start ──────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"✅ Бот запущен!\n\n"
        f"Твой Chat ID: <code>{chat_id}</code>\n\n"
        f"Скопируй этот ID и добавь его в настройки (.env файл).\n"
        f"Как только появится релевантная вакансия — ты получишь уведомление сюда.",
        parse_mode="HTML"
    )


# ── Команда /status ─────────────────────────────────────────────────────────
async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🟢 Агент активен\n"
        "🔍 Мониторинг Upwork: включён\n"
        "⏱ Интервал проверки: каждые 5 минут\n\n"
        "Используй /settings чтобы настроить фильтры."
    )


# ── Команда /settings ────────────────────────────────────────────────────────
async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("🔑 Ключевые слова", callback_data="set_keywords")],
        [InlineKeyboardButton("💰 Минимальный бюджет", callback_data="set_budget")],
        [InlineKeyboardButton("📊 Статус фильтров", callback_data="show_filters")],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "⚙️ Настройки агента:", reply_markup=reply_markup
    )


# ── Обработчик кнопок ────────────────────────────────────────────────────────
async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "show_filters":
        keywords = os.environ.get("KEYWORDS", "python, fastapi, django")
        min_budget = os.environ.get("MIN_BUDGET", "500")
        await query.edit_message_text(
            f"📊 Текущие фильтры:\n\n"
            f"🔑 Ключевые слова: {keywords}\n"
            f"💰 Мин. бюджет: ${min_budget}\n"
            f"🌍 Тип контракта: все\n\n"
            f"Чтобы изменить — отредактируй файл .env и перезапусти бота."
        )
    elif query.data == "set_keywords":
        await query.edit_message_text(
            "🔑 Ключевые слова задаются в файле .env:\n\n"
            "<code>KEYWORDS=python, fastapi, django, api</code>\n\n"
            "После изменения перезапусти бота.",
            parse_mode="HTML"
        )
    elif query.data == "set_budget":
        await query.edit_message_text(
            "💰 Минимальный бюджет задаётся в файле .env:\n\n"
            "<code>MIN_BUDGET=500</code>\n\n"
            "После изменения перезапусти бота.",
            parse_mode="HTML"
        )
    elif query.data == "apply":
        job_id = context.user_data.get("last_job_id", "—")
        await query.edit_message_text(
            f"✍️ Отлично! Открой Upwork и отправь готовый отклик.\n\n"
            f"Черновик отклика был выше 👆\n"
            f"Job ID: <code>{job_id}</code>",
            parse_mode="HTML"
        )
    elif query.data == "skip":
        await query.edit_message_text("⏭ Вакансия пропущена.")


# ── Функция отправки уведомления о вакансии ──────────────────────────────────
async def send_job_notification(app: Application, job: dict, draft: str):
    """
    Вызывается из upwork_scanner.py когда найдена релевантная вакансия.
    job = {
        "title": "...", "budget": "...", "url": "...",
        "description": "...", "client_rating": "...",
        "posted": "...", "score": 85
    }
    """
    score = job.get("score", 0)
    score_emoji = "🔥" if score >= 80 else "✅" if score >= 60 else "🟡"

    text = (
        f"{score_emoji} <b>Новая вакансия ({score}/100)</b>\n\n"
        f"📌 <b>{job['title']}</b>\n"
        f"💰 Бюджет: {job.get('budget', 'не указан')}\n"
        f"⭐ Рейтинг клиента: {job.get('client_rating', '—')}\n"
        f"🕐 Опубликовано: {job.get('posted', '—')}\n\n"
        f"📝 <b>Описание:</b>\n{job['description'][:300]}...\n\n"
        f"🤖 <b>Черновик отклика:</b>\n{draft}\n\n"
        f"🔗 <a href='{job['url']}'>Открыть на Upwork</a>"
    )

    keyboard = [
        [
            InlineKeyboardButton("✍️ Откликнуться", callback_data="apply"),
            InlineKeyboardButton("⏭ Пропустить", callback_data="skip"),
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await app.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=reply_markup,
        disable_web_page_preview=True
    )


# ── Запуск бота ──────────────────────────────────────────────────────────────
def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан! Добавь его в .env файл.")

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(button_handler))

    logger.info("Бот запущен. Ожидаю сообщений...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
