# stalcraft_bot/main.py

import asyncio
import logging
from telegram.ext import Application, CommandHandler, CallbackQueryHandler
from telegram.error import TelegramError
from config import TELEGRAM_TOKEN
from handlers import start, auth, tracking, admin, subscription
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
    # Тут можно будет задать команды бота
    await application.bot.set_my_commands(
        [
            # Примеры, потом будем расширять
            ("start", "Начать работу с ботом"),
            ("help", "Помощь по командам"),
            ("login", "Авторизация"),
            ("add", "Добавить товар или артефакт"),
            (
                "list",
                "Выводит лимит,данные о каждом товаре/артефакте в остлеживаемом. Тут можно изменить,удалить или отключить оповещения для каждого товара",
            ),
            ("remove_all", "Удаляет все отслеживаемые товары"),
            ("not_on", "Включение уведомлений по каждому товару"),
            ("not_off", "Выключение уведомлений по каждому товару"),
            ("sub_info", "Информация о лимите и дате окончания подписки"),
        ]
    )


async def error_handler(update, context):
    print("Error: {context.error}")


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

    # Кнопки удаления и уведомлений
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

    # TODO: Добавим позже:
    # application.add_handler(admin.get_handler())
    # application.add_handler(subscription.get_handler())

    # Запускаем polling
    application.run_polling()


if __name__ == "__main__":
    main()
