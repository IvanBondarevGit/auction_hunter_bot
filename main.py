# stalcraft_bot/main.py

import asyncio
import logging
import traceback
from telegram import BotCommand, BotCommandScopeDefault, BotCommandScopeChat
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError
from config import TELEGRAM_TOKEN, ADMIN_ID
from handlers import start, auth, tracking, admin, subscription
from handlers.admin import daily_subscription_check
from handlers.tracking import (
    delete_tracked_item,
    toggle_notify,
    start_edit_item,
    select_edit_field,
)

# Настройка логов
logging.basicConfig(
    format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO
)


async def post_init(application):
    asyncio.create_task(daily_subscription_check(application))
    default_commands = [
        BotCommand("start", "Начать работу с ботом"),
        BotCommand("help", "Помощь по командам"),
        BotCommand("login", "Авторизация"),
        BotCommand("add", "Добавить товар или артефакт"),
        BotCommand(
            "list",
            "Показать список отслеживания. Все действия с товарами/артефактами. Изменить,удалить,откл/вкл уведомления",
        ),
        BotCommand("remove_all", "Удалить все отслеживаемые"),
        BotCommand("not_on", "Включить уведомления"),
        BotCommand("not_off", "Выключить уведомления"),
        BotCommand("sub_info", "Инфо о подписке"),
    ]

    admin_commands = default_commands + [
        BotCommand("add_user", "Добавить нового пользователя"),
        BotCommand("user_list", "Список всех пользователей"),
        BotCommand("find_user", "Найти пользователя"),
        BotCommand("change_limit", "Изменить лимит пользователя"),
        BotCommand("clear_user_items", "Удалить все отслеживаемые товары пользователя"),
        BotCommand("remove_user ", "Удалить пользователя и все его товары"),
    ]

    # Команды для всех
    await application.bot.set_my_commands(
        default_commands, scope=BotCommandScopeDefault()
    )

    # Команды только для админа
    await application.bot.set_my_commands(
        admin_commands, scope=BotCommandScopeChat(chat_id=ADMIN_ID)
    )


def error_handler(update, context):
    print("Unhandled error occurred:")
    traceback.print_exception(
        type(context.error), context.error, context.error.__traceback__
    )


def main():
    application = (
        Application.builder().token(TELEGRAM_TOKEN).post_init(post_init).build()
    )

    # Команды
    application.add_error_handler(error_handler)

    for handler in start.get_handler():
        application.add_handler(handler)
    application.add_handler(auth.get_handler())
    application.add_handler(tracking.get_handler())  # /add и /list
    application.add_handler(tracking.get_edit_handler())  # ✏️ Редактирование

    # Кнопки удаления и уведомлений 11
    application.add_handler(
        CallbackQueryHandler(delete_tracked_item, pattern=r"^delete_")
    )
    application.add_handler(CallbackQueryHandler(toggle_notify, pattern=r"^toggle_"))

    # Удаление всех товаров
    application.add_handler(CommandHandler("remove_all", tracking.remove_all_command))
    application.add_handler(
        CallbackQueryHandler(
            tracking.confirm_remove_all, pattern="^confirm_remove_all$"
        )
    )
    application.add_handler(
        CallbackQueryHandler(tracking.cancel_remove_all, pattern="^cancel_remove_all$")
    )

    # Включение и выключение уведомлений
    application.add_handler(CommandHandler("not_off", tracking.not_off))
    application.add_handler(CommandHandler("not_on", tracking.not_on))

    # Инфо о подписке
    application.add_handler(CommandHandler("sub_info", tracking.sub_info))

    # Админские команды
    application.add_handler(admin.get_handler())

    application.add_handler(
        CallbackQueryHandler(admin.extend_subscription, pattern=r"^extend_sub:")
    )
    application.add_handler(
        CallbackQueryHandler(admin.remove_subscription_user, pattern=r"^remove_sub:")
    )
    application.add_handler(
        CallbackQueryHandler(
            admin.put_subscription_on_control, pattern=r"^control_sub:"
        )
    )

    # Запускаем polling
    application.run_polling()


if __name__ == "__main__":
    main()
