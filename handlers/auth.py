# stalcraft_bot/handlers/auth.py

from telegram import Update
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    ContextTypes,
)
from db import users_collection

# Состояния для ConversationHandler
LOGIN, PASSWORD = range(2)


def get_handler():
    return ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            LOGIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_login)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, check_password)],
        },
        fallbacks=[],
    )


async def login_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Введите ваш email (логин):")
    return LOGIN


async def get_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["login"] = update.message.text.strip()
    await update.message.reply_text("Введите ваш пароль:")
    return PASSWORD


async def check_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    login = context.user_data.get("login")
    password = update.message.text.strip()

    user = users_collection.find_one({"login": login, "password": password})
    if not user:
        await update.message.reply_text("Неверный логин или пароль. Попробуйте снова.")
        return LOGIN

    # Проверка привязки user_id
    if user["user_id"]:
        if user["user_id"] != update.effective_chat.id:
            await update.message.reply_text(
                "⚠️ Этот аккаунт уже привязан к другому Telegram-профилю."
            )
        else:
            await update.message.reply_text("✅ Вы уже авторизованы.")
        return ConversationHandler.END

    # Привязываем user_id
    users_collection.update_one(
        {"login": login}, {"$set": {"user_id": update.effective_chat.id}}
    )

    await update.message.reply_text(
        "✅ Вы успешно авторизованы!\nДля вывода команд — используйте /help."
    )
    return ConversationHandler.END
