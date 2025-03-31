# stalcraft_bot/utils/decorators.py

from functools import wraps
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
