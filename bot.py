import os
import asyncio
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from upwork_scanner import run_scanner

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
YOUR_CHAT_ID = os.environ.get("CHAT_ID", "")
SCAN_INTERVAL = int(os.environ.get("SCAN_INTERVAL_MINUTES", "5"))


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        f"✅ Бот запущен!\n\n"
        f"Твой Chat ID: <code>{chat_id}</code>\n\n"
        f"Агент мониторит Upwork каждые {SCAN_INTERVAL} минут.\n"
        f"Как только появится релевантная вакансия — пришлю сюда.",
        parse_mode="HTML"
    )


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keywords = os.environ.get("KEYWORDS", "python, fastapi, django")
    min_budget = os.environ.get("MIN_BUDGET", "500")
    query = os.environ.get("UPWORK_QUERY", "python+developer")
    await update.message.reply_text(
        f"🟢 Агент активен\n"
        f"🔍 Запрос: {query}\n"
        f"🔑 Ключевые слова: {keywords}\n"
        f"💰 Мин. бюджет: ${min_budget}\n"
        f"⏱ Интервал проверки: каждые {SCAN_INTERVAL} мин"
    )


async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📊 Текущие фильтры", callback_data="show_filters")],
        [InlineKeyboardButton("❓ Как изменить настройки", callback_data="how_to_change")],
    ]
    await update.message.reply_text(
        "⚙️ Настройки агента:", reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "show_filters":
        keywords = os.environ.get("KEYWORDS", "python, fastapi, django")
        min_budget = os.environ.get("MIN_BUDGET", "500")
        upwork_query = os.environ.get("UPWORK_QUERY", "python+developer")
        profile = os.environ.get("MY_PROFILE", "не задан")[:120]
        await query.edit_message_text(
            f"📊 Текущие фильтры:\n\n"
            f"🔍 Upwork запрос: <code>{upwork_query}</code>\n"
            f"🔑 Ключевые слова: {keywords}\n"
            f"💰 Мин. бюджет: ${min_budget}\n"
            f"👤 Профиль: {profile}...",
            parse_mode="HTML"
        )
    elif query.data == "how_to_change":
        await query.edit_message_text(
            "✏️ Чтобы изменить фильтры:\n\n"
            "1. Зайди в Railway → твой проект\n"
            "2. Variables → измени нужную переменную\n"
            "3. Railway автоматически перезапустит бота\n\n"
            "Доступные переменные:\n"
            "<code>KEYWORDS</code> — ключевые слова через запятую\n"
            "<code>MIN_BUDGET</code> — минимальный бюджет в $\n"
            "<code>UPWORK_QUERY</code> — поисковый запрос\n"
            "<code>MY_PROFILE</code> — описание твоего профиля\n"
            "<code>SCAN_INTERVAL_MINUTES</code> — интервал (мин)",
            parse_mode="HTML"
        )
    elif query.data == "apply":
        await query.edit_message_text(
            "✍️ Отлично! Черновик выше 👆\n\n"
            "Открой ссылку на вакансию → скопируй черновик → доработай под себя → отправь!\n\n"
            "💡 Совет: добавь 1-2 конкретных примера из своего опыта."
        )
    elif query.data == "skip":
        await query.edit_message_text("⏭ Вакансия пропущена.")


async def send_notification(app: Application, job: dict, draft: str):
    score = job.get("score", 0)
    score_emoji = "🔥" if score >= 80 else "✅" if score >= 60 else "🟡"

    text = (
        f"{score_emoji} <b>Новая вакансия — {score}/100</b>\n\n"
        f"📌 <b>{job['title']}</b>\n"
        f"💰 {job.get('budget', 'не указан')}\n"
        f"⭐ Рейтинг клиента: {job.get('client_rating', '—')}\n\n"
        f"📝 <b>Описание:</b>\n{job['description'][:350]}...\n\n"
        f"✍️ <b>Черновик отклика (EN):</b>\n<i>{draft}</i>\n\n"
        f"🔗 <a href='{job['url']}'>Открыть вакансию</a>"
    )

    keyboard = [[
        InlineKeyboardButton("✍️ Откликнуться", callback_data="apply"),
        InlineKeyboardButton("⏭ Пропустить", callback_data="skip"),
    ]]

    await app.bot.send_message(
        chat_id=YOUR_CHAT_ID,
        text=text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(keyboard),
        disable_web_page_preview=True
    )


async def main():
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN не задан!")
    if not YOUR_CHAT_ID:
        raise ValueError("CHAT_ID не задан!")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status))
    app.add_handler(CommandHandler("settings", settings))
    app.add_handler(CallbackQueryHandler(button_handler))

    async def notification_fn(job, draft):
        await send_notification(app, job, draft)

    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=Update.ALL_TYPES)

    logger.info("🚀 Бот и сканер запущены!")
    await run_scanner(notification_fn, interval_minutes=SCAN_INTERVAL)


if __name__ == "__main__":
    asyncio.run(main())
