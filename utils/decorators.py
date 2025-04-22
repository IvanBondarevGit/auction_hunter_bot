# stalcraft_bot/utils/decorators.py

from functools import wraps
from telegram.ext import ContextTypes
from telegram import Update
from db import users_collection


def require_auth(func):
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        chat_id = update.effective_chat.id
        user = users_collection.find_one({"user_id": chat_id})
        if not user:
            await update.message.reply_text("Вы не авторизованы. Используйте /login.")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper


def admin_required(func):
    @wraps(func)
    async def wrapper(
        update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs
    ):
        user_id = update.effective_user.id
        user = users_collection.find_one({"user_id": user_id})
        if not user or not user.get("is_admin", False):
            await update.message.reply_text("⛔ У вас нет прав администратора.")
            return
        return await func(update, context, *args, **kwargs)

    return wrapper
