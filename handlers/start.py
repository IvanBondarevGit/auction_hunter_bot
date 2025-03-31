# stalcraft_bot/handlers/start.py

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes


def get_handler():
    return [
        CommandHandler("start", start_command),
        CommandHandler("help", help_command),
    ]


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Приветствую, я бот по отслеживанию необходимых тебе лотов на аукционе в игре STALCRAFT:X.\n\n"
        "Чтобы пользоваться ботом, нужно авторизоваться через команду /login.\n"
        "Для вывода всех доступных команд — /help."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📌 Доступные команды:\n"
        "/start — Начать работу с ботом\n"
        "/login — Авторизация\n"
        "/add — Добавить товар/артефакт для отслеживания\n"
        "/list — Показать список отслеживаемых лотов\n"
        "/not_off — Выключить все уведомления\n"
        "/not_on — Включить все уведомления\n"
        "/cancel — Отменить текущее действие\n"
        "/remove_all — Удалить все отслеживаемые товары\n"
        "/sub_info — Информация о подписке\n"
        "/help — Показать эту справку"
    )
