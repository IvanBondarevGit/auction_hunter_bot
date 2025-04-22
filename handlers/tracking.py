# stalcraft_bot/handlers/tracking.py

from bson import ObjectId  # импорт сверху, для работы с MongoDB _id
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from db import users_collection, tracked_items
from utils.decorators import require_auth
from services.search import load_item_by_name
from utils.validation import get_percent_range_by_rarity, get_rarity_by_percent_range
from datetime import datetime, timedelta

# conversation states для добавления
(
    CHOOSE_TYPE,
    ENTER_ITEM_NAME,
    SELECT_ITEM,
    SET_PRICE,
    SET_QUANTITY,
    CONFIRM_ITEM,
    SELECT_RARITY,
    ASK_TRACK_PERCENT,
    SET_MIN_PERCENT,
    SET_MAX_PERCENT,
) = range(10)

# conversation states для редактирования
(
    EDIT_SELECT_FIELD,
    EDIT_SET_VALUE,
) = range(100, 102)


def get_handler():
    return ConversationHandler(
        entry_points=[
            CommandHandler("add", start_add),
            CommandHandler("list", show_list),
        ],
        states={
            CHOOSE_TYPE: [CallbackQueryHandler(type_chosen)],
            ENTER_ITEM_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_item_name)
            ],
            SELECT_ITEM: [CallbackQueryHandler(select_item)],
            SET_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_price)],
            SET_QUANTITY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, enter_quantity)
            ],
            CONFIRM_ITEM: [
                CallbackQueryHandler(confirm_add, pattern="^confirm_add$"),
                CallbackQueryHandler(cancel_add, pattern="^cancel_add$"),
            ],
            SELECT_RARITY: [CallbackQueryHandler(select_rarity, pattern="^rarity_")],
            ASK_TRACK_PERCENT: [
                CallbackQueryHandler(
                    handle_track_percent_choice, pattern="^track_percent_"
                )
            ],
            SET_MIN_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_min_percent)
            ],
            SET_MAX_PERCENT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_max_percent)
            ],
        },
        fallbacks=[],
    )


def get_edit_handler():
    print("[INIT] get_edit_handler active")
    return ConversationHandler(
        entry_points=[
            CallbackQueryHandler(start_edit_item, pattern=r"^edit_[a-f0-9]{24}$")
        ],
        states={
            EDIT_SELECT_FIELD: [
                CallbackQueryHandler(
                    select_edit_field, pattern=r"^edit_(price|count|rarity|percent)$"
                )
            ],
            EDIT_SET_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, set_new_value),
                CallbackQueryHandler(set_new_value, pattern=r"^rarity_\d$"),
            ],
        },
        fallbacks=[],
        name="edit_handler",
        persistent=False,
        per_chat=True,
    )


@require_auth
async def start_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user = users_collection.find_one({"user_id": user_id})

    # Проверка лимита
    if user["current_items"] >= user["max_items"]:
        await update.message.reply_text(
            f"⚠️ Вы достигли лимита отслеживаемых товаров: {user['max_items']}."
        )
        return ConversationHandler.END

    # Выбор: Товар или Артефакт
    buttons = [
        [InlineKeyboardButton("🧱 Товар", callback_data="item")],
        [InlineKeyboardButton("🌀 Артефакт", callback_data="artifact")],
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    await update.message.reply_text(
        "Вы хотите отслеживать товар или артефакт?", reply_markup=reply_markup
    )
    return CHOOSE_TYPE


async def type_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "item":
        context.user_data["type"] = "item"
        await query.edit_message_text(
            "🧱 Отлично! Введите название товара для отслеживания:"
        )
        return ENTER_ITEM_NAME

    elif query.data == "artifact":
        context.user_data["type"] = "artifact"
        await query.edit_message_text(
            "🌀 Отлично! Введите название артефакта для отслеживания:"
        )
        return ENTER_ITEM_NAME  # пока используем тот же шаг

    else:
        await query.edit_message_text("Ошибка выбора. Попробуйте снова.")
        return ConversationHandler.END


async def enter_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text.strip()
    search_type = context.user_data.get("type", "item")
    found = load_item_by_name(query, search_type)

    if not found:
        await update.message.reply_text(
            "❌ Товар не найден. Попробуйте ввести другое название."
        )
        return ENTER_ITEM_NAME

    # Убираем дубликаты по ID
    unique = {}
    for item in found:
        item_id = item["data"].get("id")
        if item_id not in unique:
            unique[item_id] = item

    filtered = list(unique.values())

    context.user_data["item_results"] = filtered
    buttons = [
        [InlineKeyboardButton(item["name"], callback_data=f"select_item_{i}")]
        for i, item in enumerate(filtered)
    ]
    reply_markup = InlineKeyboardMarkup(buttons)

    if context.user_data.get("type") == "artifact":
        caption = "🔍 Похожие артефакты:"
    else:
        caption = "🔍 Похожие товары:"

    await update.message.reply_text(caption, reply_markup=reply_markup)
    return SELECT_ITEM


async def select_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    idx = int(query.data.replace("select_item_", ""))
    item = context.user_data["item_results"][idx]
    context.user_data["selected_item"] = item

    if context.user_data.get("type") == "item":
        await query.edit_message_text(
            f"Вы выбрали: *{item['name']}*\nТеперь введите цену в рублях, ниже которой бот будет отслеживать товар:",
            parse_mode="Markdown",
        )
        return SET_PRICE
    else:
        # Артефакт: предлагаем выбрать редкость
        buttons = [
            [InlineKeyboardButton("Обычный", callback_data="rarity_0")],
            [InlineKeyboardButton("Необычный", callback_data="rarity_1")],
            [InlineKeyboardButton("Особый", callback_data="rarity_2")],
            [InlineKeyboardButton("Редкий", callback_data="rarity_3")],
            [InlineKeyboardButton("Исключительный", callback_data="rarity_4")],
            [InlineKeyboardButton("Легендарный", callback_data="rarity_5")],
        ]
        await query.edit_message_text(
            f"Вы выбрали: *{item['name']}*\n\nТеперь укажите редкость артефакта:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return SELECT_RARITY


async def enter_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text("❌ Пожалуйста, введите число (цену в рублях).")
        return SET_PRICE

    context.user_data["price"] = int(text)

    if context.user_data.get("type") == "item":
        await update.message.reply_text(
            "Теперь укажите минимальное количество для отслеживания:"
        )
        return SET_QUANTITY

    else:
        # У артефакта количество всегда 1
        context.user_data["quantity"] = 1

        # Готовим подтверждение
        item = context.user_data["selected_item"]
        price = context.user_data["price"]
        min_percent = context.user_data.get("min_percent")
        max_percent = context.user_data.get("max_percent")
        rarity = context.user_data["rarity"]

        text = (
            f"📦 Подтвердите отслеживание:\n\n"
            f"🔹 Артефакт: *{item['name']}*\n"
            f"✨ Редкость: *{['Обычный','Необычный','Особый','Редкий','Исключительный','Легендарный'][rarity]}*\n"
            f"💰 Цена до: *{price}* руб.\n"
        )

        if min_percent is not None and max_percent is not None:
            text += f"🧪 Процент: *{min_percent}% – {max_percent}%*\n"

        text += "\nПодтвердить добавление?"

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ Да", callback_data="confirm_add"),
                        InlineKeyboardButton("❌ Нет", callback_data="cancel_add"),
                    ]
                ]
            ),
        )
        return CONFIRM_ITEM


async def enter_quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    if not text.isdigit():
        await update.message.reply_text(
            "❌ Пожалуйста, введите целое число (минимальное количество)."
        )
        return SET_QUANTITY

    context.user_data["quantity"] = int(text)

    # Готовим данные для подтверждения
    item = context.user_data["selected_item"]
    price = context.user_data["price"]
    quantity = context.user_data["quantity"]

    await update.message.reply_text(
        f"📦 Подтвердите отслеживание:\n\n"
        f"🔹 Товар: *{item['name']}*\n"
        f"💰 Цена до: *{price}* руб.\n"
        f"📦 Мин. количество: *{quantity}* шт.\n\n"
        f"Подтвердить добавление?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Да", callback_data="confirm_add"),
                    InlineKeyboardButton("❌ Нет", callback_data="cancel_add"),
                ]
            ]
        ),
    )
    return CONFIRM_ITEM


async def confirm_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    user_id = update.effective_chat.id
    user_type = context.user_data.get("type")
    item = context.user_data["selected_item"]

    document = {
        "user_id": user_id,
        "type": user_type,
        "name": item["name"],
        "item_id": item["data"]["id"],
        "price": context.user_data["price"],
        "notify": True,
    }

    if user_type == "item":
        document["min_count"] = context.user_data["quantity"]
    else:
        document["min_count"] = 1
        document["rarity"] = context.user_data["rarity"]
        if context.user_data.get("min_percent") is not None:
            document["min_percent"] = context.user_data["min_percent"]
            document["max_percent"] = context.user_data["max_percent"]

    # Сохраняем в БД
    tracked_items.insert_one(document)

    # Обновляем счётчик
    users_collection.update_one({"user_id": user_id}, {"$inc": {"current_items": 1}})

    if user_type == "item":
        success_text = "✅ Товар успешно добавлен для отслеживания!"
    else:
        success_text = "✅ Артефакт успешно добавлен для отслеживания!"

    await query.edit_message_text(success_text)
    return ConversationHandler.END


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "❌ Добавление отменено. Введите название товара ещё раз:"
    )
    return ENTER_ITEM_NAME


async def select_rarity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    rarity = int(query.data.replace("rarity_", ""))
    context.user_data["rarity"] = rarity

    # Сохраняем допустимые пределы для процента
    percent_ranges = {
        0: (0, 100),
        1: (100, 110),
        2: (110, 120),
        3: (120, 130),
        4: (130, 140),
        5: (140, 150),
    }

    context.user_data["percent_range"] = percent_ranges[rarity]

    # Спрашиваем: отслеживать процент?
    buttons = [
        [
            InlineKeyboardButton("✅ Да", callback_data="track_percent_yes"),
            InlineKeyboardButton("❌ Нет", callback_data="track_percent_no"),
        ]
    ]
    await query.edit_message_text(
        f"🎯 Вы выбрали редкость: *{['Обычный','Необычный','Особый','Редкий','Исключительный','Легендарный'][rarity]}*\n\n"
        f"Хотите отслеживать процент артефакта?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    return ASK_TRACK_PERCENT


async def handle_track_percent_choice(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    if query.data == "track_percent_yes":
        min_p, max_p = context.user_data["percent_range"]
        await query.edit_message_text(
            f"Введите минимальный процент артефакта (от {min_p} до {max_p}):"
        )
        return SET_MIN_PERCENT

    else:
        context.user_data["min_percent"] = None
        context.user_data["max_percent"] = None
        await query.edit_message_text(
            "Теперь введите цену, ниже которой бот будет отслеживать артефакт:"
        )
        return SET_PRICE


async def set_min_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите целое число.")
        return SET_MIN_PERCENT

    min_p, max_p = context.user_data["percent_range"]
    if not (min_p <= value <= max_p):
        await update.message.reply_text(f"❌ Введите значение от {min_p} до {max_p}.")
        return SET_MIN_PERCENT

    context.user_data["min_percent"] = value
    await update.message.reply_text(
        f"Теперь введите максимальный процент (от {value} до {max_p}):"
    )
    return SET_MAX_PERCENT


async def set_max_percent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        value = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("❌ Введите целое число.")
        return SET_MAX_PERCENT

    min_p = context.user_data["min_percent"]
    _, max_p = context.user_data["percent_range"]

    if not (min_p <= value <= max_p):
        await update.message.reply_text(f"❌ Введите значение от {min_p} до {max_p}.")
        return SET_MAX_PERCENT

    context.user_data["max_percent"] = value
    await update.message.reply_text(
        "Теперь введите цену, ниже которой бот будет отслеживать артефакт:"
    )
    return SET_PRICE


@require_auth
async def show_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user = users_collection.find_one({"user_id": user_id})
    items = list(tracked_items.find({"user_id": user_id}))

    if not items:
        await update.message.reply_text("🗂️ Вы пока не отслеживаете ни одного лота.")
        return

    text = f"📋 Вы отслеживаете {user['current_items']} из {user['max_items']} доступных:\n\n"
    await update.message.reply_text(text)

    for i, item in enumerate(items):
        item_type = item["type"]
        name = item["name"]
        price = item["price"]
        notify = "🔔 Вкл" if item["notify"] else "🔕 Откл"

        if item_type == "item":
            desc = (
                f"📦 Товар: *{name}*\n"
                f"💰 Цена до: *{price}* руб\n"
                f"🔢 Мин. кол-во: *{item.get('min_count', 1)}*\n"
                f"{notify}"
            )
        else:
            rarity_names = [
                "Обычный",
                "Необычный",
                "Особый",
                "Редкий",
                "Исключительный",
                "Легендарный",
            ]
            desc = (
                f"🌀 Артефакт: *{name}*\n"
                f"✨ Редкость: *{rarity_names[item.get('rarity', 0)]}*\n"
                f"💰 Цена до: *{price}* руб\n"
            )
            if "min_percent" in item and "max_percent" in item:
                desc += f"🧪 %: *{item['min_percent']}–{item['max_percent']}*\n"
            desc += f"{notify}"

        # Кнопки под каждым лотом
        buttons = [
            [
                InlineKeyboardButton("✏️ Изменить", callback_data=f"edit_{item['_id']}"),
                InlineKeyboardButton(
                    "❌ Удалить", callback_data=f"delete_{item['_id']}"
                ),
                InlineKeyboardButton(
                    "🔕 Выкл" if item["notify"] else "🔔 Вкл",
                    callback_data=f"toggle_{item['_id']}",
                ),
            ]
        ]

        await update.message.reply_text(
            desc, reply_markup=InlineKeyboardMarkup(buttons), parse_mode="Markdown"
        )


@require_auth
async def delete_tracked_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _id = query.data.replace("delete_", "")
    item = tracked_items.find_one({"_id": ObjectId(_id)})

    if not item:
        await query.edit_message_text("❌ Лот не найден.")
        return ConversationHandler.END

    tracked_items.delete_one({"_id": ObjectId(_id)})
    users_collection.update_one(
        {"user_id": update.effective_chat.id}, {"$inc": {"current_items": -1}}
    )

    await query.edit_message_text("🗑️ Лот успешно удалён.")
    return ConversationHandler.END


@require_auth
async def toggle_notify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _id = query.data.replace("toggle_", "")
    item = tracked_items.find_one({"_id": ObjectId(_id)})

    if not item:
        await query.edit_message_text("❌ Лот не найден.")
        return ConversationHandler.END

    new_notify = not item.get("notify", True)
    tracked_items.update_one({"_id": ObjectId(_id)}, {"$set": {"notify": new_notify}})

    status = "включены" if new_notify else "отключены"
    await query.edit_message_text(f"🔔 Уведомления {status}. Обновите /list.")
    return ConversationHandler.END


@require_auth
async def start_edit_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _id = query.data.replace("edit_", "")
    item = tracked_items.find_one({"_id": ObjectId(_id)})

    if not item:
        await query.edit_message_text("❌ Лот не найден.")
        return ConversationHandler.END

    context.user_data["edit_item_id"] = _id
    context.user_data["edit_type"] = item["type"]

    # Кнопки в зависимости от типа
    buttons = [[InlineKeyboardButton("💰 Цена", callback_data="edit_price")]]

    if item["type"] == "item":
        buttons.append([InlineKeyboardButton("🔢 Кол-во", callback_data="edit_count")])
    else:
        buttons.append(
            [InlineKeyboardButton("✨ Редкость", callback_data="edit_rarity")]
        )
        if "min_percent" in item:
            buttons.append(
                [InlineKeyboardButton("🧪 Процент", callback_data="edit_percent")]
            )

    await query.edit_message_text(
        "Что вы хотите изменить?", reply_markup=InlineKeyboardMarkup(buttons)
    )
    return EDIT_SELECT_FIELD


async def select_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    context.user_data["edit_field"] = query.data.replace("edit_", "")
    print("[DEBUG] Выбранное поле:", context.user_data["edit_field"])

    if query.data == "edit_rarity":
        buttons = [
            [InlineKeyboardButton("Обычный", callback_data="rarity_0")],
            [InlineKeyboardButton("Необычный", callback_data="rarity_1")],
            [InlineKeyboardButton("Особый", callback_data="rarity_2")],
            [InlineKeyboardButton("Редкий", callback_data="rarity_3")],
            [InlineKeyboardButton("Исключительный", callback_data="rarity_4")],
            [InlineKeyboardButton("Легендарный", callback_data="rarity_5")],
        ]
        await query.edit_message_text(
            "Выберите новую редкость артефакта:",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return EDIT_SET_VALUE

    elif query.data == "edit_percent":
        await query.edit_message_text(
            "Введите новый диапазон процента (пример: 130-140):"
        )
        return EDIT_SET_VALUE

    elif query.data in ["edit_price", "edit_count"]:
        await query.edit_message_text("Введите новое значение:")
        return EDIT_SET_VALUE

    else:
        await query.edit_message_text("❌ Неизвестное поле для редактирования.")
        return EDIT_SET_VALUE


async def set_new_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    item_id = context.user_data.get("edit_item_id")
    field = context.user_data.get("edit_field")

    if not item_id or not field:
        await (update.message or update.callback_query).reply_text(
            "❌ Что-то пошло не так. Попробуйте заново."
        )
        return EDIT_SET_VALUE

    update_data = {}

    if update.message:
        value = update.message.text.strip()
    elif update.callback_query:
        await update.callback_query.answer()
        value = update.callback_query.data.replace("rarity_", "")
    else:
        return ConversationHandler.END

    # Получаем текущий объект из базы
    item = tracked_items.find_one({"_id": ObjectId(item_id)})

    if field == "price":
        if not value.isdigit():
            await update.message.reply_text("❌ Введите корректное число для цены.")
            return EDIT_SET_VALUE
        update_data["price"] = int(value)

    elif field == "count":
        if not value.isdigit():
            await update.message.reply_text(
                "❌ Введите корректное число для количества."
            )
            return EDIT_SET_VALUE
        update_data["min_count"] = int(value)

    elif field == "percent":
        try:
            min_p, max_p = map(int, value.replace(" ", "").split("-"))
            if min_p >= max_p:
                raise ValueError

            rarity = get_rarity_by_percent_range(min_p, max_p)
            if rarity is None:
                await update.message.reply_text(
                    "❌ Указанный диапазон не соответствует ни одной редкости."
                )
                return EDIT_SET_VALUE

            update_data["min_percent"] = min_p
            update_data["max_percent"] = max_p

            # Если текущая редкость не соответствует — обновляем
            if item["rarity"] != rarity:
                update_data["rarity"] = rarity

        except:
            await update.message.reply_text("❌ Введите диапазон как: 130-140")
            return EDIT_SET_VALUE

    elif field == "rarity":
        try:
            rarity_value = int(value)
            update_data["rarity"] = rarity_value

            if "min_percent" in item and "max_percent" in item:
                min_p = item["min_percent"]
                max_p = item["max_percent"]
                allowed_min, allowed_max = get_percent_range_by_rarity(rarity_value)

                if not (allowed_min <= min_p < max_p <= allowed_max):
                    # Удаляем старые проценты, просим ввести новые
                    tracked_items.update_one(
                        {"_id": ObjectId(item_id)},
                        {"$unset": {"min_percent": "", "max_percent": ""}},
                    )
                    context.user_data["edit_field"] = "percent"
                    await (update.message or update.callback_query.message).reply_text(
                        f"⚠️ Указанная редкость не соответствует текущему диапазону процентов.\n"
                        f"Пожалуйста, введите новый диапазон (пример: {allowed_min}-{allowed_max})"
                    )
                    return EDIT_SET_VALUE

        except ValueError:
            await update.message.reply_text("❌ Неверное значение редкости.")
            return EDIT_SET_VALUE

    else:
        await (update.message or update.callback_query.message).reply_text(
            "❌ Неизвестное поле для редактирования."
        )
        return ConversationHandler.END

    tracked_items.update_one({"_id": ObjectId(item_id)}, {"$set": update_data})
    await (update.message or update.callback_query.message).reply_text(
        "✅ Параметры успешно обновлены. Используйте /list для просмотра."
    )
    return ConversationHandler.END


@require_auth
async def remove_all_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    buttons = [
        [InlineKeyboardButton("✅ Удалить всё", callback_data="confirm_remove_all")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_remove_all")],
    ]
    await update.message.reply_text(
        "❗ Вы уверены, что хотите удалить ВСЕ отслеживаемые товары и артефакты? Это действие безвозвратно.",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


@require_auth
async def confirm_remove_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    user_id = update.effective_user.id

    result = tracked_items.delete_many({"user_id": user_id})

    users_collection.update_one({"user_id": user_id}, {"$set": {"current_items": 0}})

    await update.callback_query.edit_message_text(
        f"✅ Удалено {result.deleted_count} отслеживаемых позиций."
    )


@require_auth
async def cancel_remove_all(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text(
        "❌ Отмена удаления. Всё осталось на месте."
    )


@require_auth
async def not_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = tracked_items.update_many(
        {"user_id": user_id}, {"$set": {"notify": False}}
    )
    await update.message.reply_text(
        f"🔕 Уведомления отключены для {result.modified_count} позиций."
    )


@require_auth
async def not_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    result = tracked_items.update_many({"user_id": user_id}, {"$set": {"notify": True}})
    await update.message.reply_text(
        f"🔔 Уведомления включены для {result.modified_count} позиций."
    )


@require_auth
async def sub_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = users_collection.find_one({"user_id": user_id})

    if not user:
        await update.message.reply_text("❌ Не удалось найти информацию о подписке.")
        return

    reg_date = user.get("reg_date")
    max_items = user.get("max_items", 0)
    current_items = user.get("current_items", 0)

    if isinstance(reg_date, str):
        reg_date = datetime.fromisoformat(reg_date)

    expire_date = reg_date + timedelta(days=30)
    expire_str = expire_date.strftime("%d.%m.%Y")

    await update.message.reply_text(
        f"📅 Подписка активна до: {expire_str}\n"
        f"🎯 Лимит отслеживания: {current_items} / {max_items}"
    )
