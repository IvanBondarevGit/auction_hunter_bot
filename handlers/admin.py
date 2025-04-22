from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from db import users_collection, tracked_items
from datetime import date, datetime, timedelta, time
import secrets
from utils.decorators import admin_required
from bson import ObjectId
from config import ADMIN_ID


# Состояния
ASK_EMAIL, ASK_LIMIT = range(2)
ASK_USER_IDENTIFIER = range(1000, 1001)
ASK_USER_FOR_LIMIT_CHANGE, ASK_NEW_LIMIT = range(1001, 1003)
ASK_USER_TO_CLEAR_ITEMS = 106
ASK_USER_TO_REMOVE, CONFIRM_USER_REMOVAL = range(107, 109)


def get_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("add_user", add_user_start),
            CommandHandler("user_list", user_list),
            CommandHandler("find_user", find_user_start),
            CommandHandler("change_limit", change_limit_start),
            CommandHandler("clear_user_items", clear_user_items_start),
            CommandHandler("remove_user", remove_user_start),
        ],
        states={
            ASK_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_email)
            ],
            ASK_LIMIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_user_limit)
            ],
            ASK_USER_IDENTIFIER: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_user_identifier)
            ],
            ASK_USER_FOR_LIMIT_CHANGE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, process_limit_user)
            ],
            ASK_NEW_LIMIT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_new_limit)
            ],
            ASK_USER_TO_CLEAR_ITEMS: [
                MessageHandler(
                    filters.TEXT & ~filters.COMMAND, clear_user_items_process
                )
            ],
            ASK_USER_TO_REMOVE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, remove_user_lookup)
            ],
            CONFIRM_USER_REMOVAL: [
                CallbackQueryHandler(
                    confirm_user_removal, pattern="^confirm_remove_user$"
                ),
                CallbackQueryHandler(
                    cancel_user_removal, pattern="^cancel_remove_user$"
                ),
            ],
        },
        fallbacks=[],
    )


@admin_required
async def add_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📧 Введите email (логин) нового пользователя:")
    return ASK_EMAIL


async def add_user_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_email"] = update.message.text.strip()
    await update.message.reply_text("🔢 Укажите лимит на отслеживание:")
    return ASK_LIMIT


async def add_user_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        limit = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите число.")
        return ASK_LIMIT

    email = context.user_data["new_email"]
    password = secrets.token_urlsafe(6)  # генерация пароля
    reg_date = datetime.now()

    users_collection.insert_one(
        {
            "login": email,
            "password": password,
            "user_id": None,
            "is_admin": False,
            "max_items": limit,
            "current_items": 0,
            "reg_date": reg_date,
        }
    )

    await update.message.reply_text(
        f"✅ Пользователь добавлен:\n"
        f"📧 Логин: `{email}`\n"
        f"🔑 Пароль: `{password}`\n"
        f"📆 Подписка с {reg_date.strftime('%d.%m.%Y')}",
        parse_mode="Markdown",
    )
    return ConversationHandler.END


@admin_required
async def user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = list(users_collection.find())
    total = len(users)

    if total == 0:
        await update.message.reply_text("👥 Пользователей пока нет.")
        return

    msg = f"👥 Всего пользователей: {total}\n\n"
    for i, user in enumerate(users, start=1):
        email = user.get("login", "—")
        current = user.get("current_items", 0)
        max_items = user.get("max_items", 0)
        reg_date = user.get("reg_date")
        if isinstance(reg_date, str):
            reg_date = datetime.fromisoformat(reg_date)
        date_str = reg_date.strftime("%d.%m.%Y") if reg_date else "—"

        msg += (
            f"{i}. 📧 {email}\n"
            f"   🎯 Лимит: {current} / {max_items}\n"
            f"   📆 Подписка с: {date_str}\n\n"
        )

    await update.message.reply_text(msg)


# Команда /find_user
@admin_required
async def find_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Введите логин или Telegram ID пользователя:")
    return ASK_USER_IDENTIFIER


# Обработка ввода
@admin_required
async def process_user_identifier(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identifier = update.message.text.strip()

    query = {"$or": [{"login": identifier}, {"user_id": identifier}]}
    if identifier.isdigit():
        query["$or"].append({"user_id": int(identifier)})

    user = users_collection.find_one(query)

    if not user:
        await update.message.reply_text("❌ Пользователь не найден.")
    else:
        login = user.get("login", "—")
        user_id = user.get("user_id", "—")
        current = user.get("current_items", 0)
        max_items = user.get("max_items", 0)
        reg_date = user.get("reg_date")
        date_str = reg_date.strftime("%d.%m.%Y") if reg_date else "—"

        await update.message.reply_text(
            f"👤 Логин: {login}\n"
            f"📱 Telegram ID: {user_id}\n"
            f"📊 Лимит: {current} / {max_items}\n"
            f"📅 Подписка: {date_str}"
        )

    return ConversationHandler.END


@admin_required
async def change_limit_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔁 Введите логин или Telegram ID пользователя:")
    return ASK_USER_FOR_LIMIT_CHANGE


@admin_required
async def process_limit_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identifier = update.message.text.strip()
    query = {"$or": [{"login": identifier}]}
    if identifier.isdigit():
        query["$or"].append({"user_id": int(identifier)})

    user = users_collection.find_one(query)

    if not user:
        await update.message.reply_text("❌ Пользователь не найден.")
        return ConversationHandler.END

    context.user_data["edit_user_mongo_id"] = user["_id"]
    await update.message.reply_text(
        f"🔢 Введите новый лимит отслеживаемых товаров для пользователя {user['login']}:"
    )
    return ASK_NEW_LIMIT


@admin_required
async def save_new_limit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        new_limit = int(update.message.text.strip())
        user_mongo_id = context.user_data.get("edit_user_mongo_id")

        if user_mongo_id is None:
            await update.message.reply_text("⚠️ Ошибка: не указан пользователь.")
            return ConversationHandler.END

        result = users_collection.update_one(
            {"_id": ObjectId(user_mongo_id)},
            {"$set": {"max_items": new_limit}},
        )

        if result.modified_count > 0:
            await update.message.reply_text(f"✅ Лимит обновлён до {new_limit}.")
        else:
            await update.message.reply_text("⚠️ Лимит не был обновлён.")

    except ValueError:
        await update.message.reply_text("❌ Введите корректное число.")
        return ASK_NEW_LIMIT

    return ConversationHandler.END


from bson import ObjectId
from db import tracked_items


@admin_required
async def clear_user_items_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🧹 Введите логин или Telegram ID пользователя:")
    return ASK_USER_TO_CLEAR_ITEMS


@admin_required
async def clear_user_items_process(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identifier = update.message.text.strip()
    query = {"$or": [{"login": identifier}]}
    if identifier.isdigit():
        query["$or"].append({"user_id": int(identifier)})

    user = users_collection.find_one(query)

    if not user:
        await update.message.reply_text("❌ Пользователь не найден.")
        return ConversationHandler.END

    user_id = user.get("user_id")
    result = tracked_items.delete_many({"user_id": user_id})

    # Обнуляем current_items
    users_collection.update_one({"_id": user["_id"]}, {"$set": {"current_items": 0}})

    await update.message.reply_text(
        f"✅ Удалено {result.deleted_count} отслеживаемых позиций у пользователя {user['login']}.\n"
        f"🔁 Лимит сброшен до 0 / {user.get('max_items', 0)}"
    )
    return ConversationHandler.END


@admin_required
async def remove_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🗑 Введите логин или Telegram ID пользователя для удаления:"
    )
    return ASK_USER_TO_REMOVE


@admin_required
async def remove_user_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    identifier = update.message.text.strip()
    query = {"$or": [{"login": identifier}]}
    if identifier.isdigit():
        query["$or"].append({"user_id": int(identifier)})

    user = users_collection.find_one(query)

    if not user:
        await update.message.reply_text("❌ Пользователь не найден.")
        return ConversationHandler.END

    context.user_data["delete_user_id"] = user["_id"]
    context.user_data["delete_user_login"] = user["login"]

    buttons = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data="confirm_remove_user"),
            InlineKeyboardButton("❌ Отмена", callback_data="cancel_remove_user"),
        ]
    ]
    await update.message.reply_text(
        f"Вы действительно хотите удалить пользователя {user['login']} и все его отслеживания?",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return CONFIRM_USER_REMOVAL


@admin_required
async def confirm_user_removal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()

    user_id = context.user_data.get("delete_user_id")
    login = context.user_data.get("delete_user_login")

    user = users_collection.find_one({"_id": user_id})
    if not user:
        await update.callback_query.edit_message_text("❌ Пользователь уже удалён.")
        return ConversationHandler.END

    # Удаляем отслеживания и самого пользователя
    tracked_items.delete_many({"user_id": user.get("user_id")})
    users_collection.delete_one({"_id": user_id})

    await update.callback_query.edit_message_text(
        f"✅ Пользователь {login} и все его данные удалены."
    )
    return ConversationHandler.END


@admin_required
async def cancel_user_removal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("❌ Отмена удаления.")
    return ConversationHandler.END


async def check_expired_subscriptions(app):
    print("[DEBUG] RUN check_expired_subscriptions")
    today = datetime.combine(datetime.utcnow().date(), time.min)

    users = users_collection.find(
        {
            "reg_date": {"$exists": True},
            "$or": [
                {"pending_control_until": {"$exists": False}},
                {"pending_control_until": None},
                {"pending_control_until": {"$lt": today}},
            ],
        }
    )

    for user in users:
        login = user["login"]
        reg_date = user["reg_date"]

        if isinstance(reg_date, str):
            reg_date = datetime.fromisoformat(reg_date)
        elif isinstance(reg_date, date) and not isinstance(reg_date, datetime):
            reg_date = datetime.combine(reg_date, time.min)

        end_date = reg_date + timedelta(days=30)

        # 💡 Здесь уже НЕ прерываем по дате окончания подписки
        # Вместо этого — если подписка истекла или нужен контроль
        if (
            end_date.date() != today.date()
            and user.get("pending_control_until", today + timedelta(seconds=1)) > today
        ):
            continue

        print(f"[DEBUG] Отправка уведомления по {login}")

        buttons = [
            [
                InlineKeyboardButton(
                    "🔁 Продлить", callback_data=f"extend_sub:{login}"
                ),
                InlineKeyboardButton("❌ Удалить", callback_data=f"remove_sub:{login}"),
                InlineKeyboardButton(
                    "🕓 На контроле", callback_data=f"control_sub:{login}"
                ),
            ]
        ]

        await app.bot.send_message(
            chat_id=ADMIN_ID,
            text=(
                f"📅 Подписка пользователя `{login}` истекла {end_date.strftime('%d.%m.%Y')}\n"
                f"Что сделать?"
            ),
            reply_markup=InlineKeyboardMarkup(buttons),
            parse_mode="Markdown",
        )


# ===============================
# 🔁 Циклическая проверка каждый день
# ===============================
import asyncio


async def daily_subscription_check(app):
    while True:
        await check_expired_subscriptions(app)
        await asyncio.sleep(86400)  # 24 часа


async def extend_subscription(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    login = update.callback_query.data.split(":")[1]

    users_collection.update_one(
        {"login": login},
        {"$set": {"reg_date": datetime.utcnow(), "pending_control_until": None}},
    )

    await update.callback_query.edit_message_text(
        f"✅ Подписка пользователя `{login}` продлена на 30 дней.",
        parse_mode="Markdown",
    )


async def remove_subscription_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    login = update.callback_query.data.split(":")[1]

    user = users_collection.find_one({"login": login})
    if user:
        tracked_items.delete_many({"user_id": user.get("user_id")})
        users_collection.delete_one({"_id": user["_id"]})

    await update.callback_query.edit_message_text(
        f"❌ Пользователь `{login}` удалён.", parse_mode="Markdown"
    )


async def put_subscription_on_control(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    await update.callback_query.answer()
    login = update.callback_query.data.split(":")[1]

    users_collection.update_one(
        {"login": login},
        {
            "$set": {
                "pending_control_until": datetime.combine(
                    datetime.utcnow().date() + timedelta(days=5), time.min
                )
            }
        },
    )

    await update.callback_query.edit_message_text(
        f"🕓 Пользователь `{login}` взят на контроль. Повтор через 5 дней.",
        parse_mode="Markdown",
    )
