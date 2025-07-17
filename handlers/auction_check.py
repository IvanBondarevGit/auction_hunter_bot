import asyncio
from datetime import datetime, timezone
from db import tracked_items, processed_lots, users_collection
from config import API_BASE_URL, CLIENT_ID, CLIENT_SECRET, AUTH_URL
import httpx

REQUESTS_PER_MIN = 190  # с запасом для лимита
TRACK_WINDOW_MINUTES = 10  # интервал отслеживания (по твоему требованию)


# Авторизация к API
class StalcraftAuth:
    _token = None
    _token_created = None
    _token_lifetime = 3600  # секунд

    @classmethod
    async def get_token(cls):
        now = datetime.utcnow().timestamp()
        if (
            cls._token
            and cls._token_created
            and now - cls._token_created < cls._token_lifetime - 60
        ):
            return cls._token
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                AUTH_URL,
                data={
                    "grant_type": "client_credentials",
                    "client_id": CLIENT_ID,
                    "client_secret": CLIENT_SECRET,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            cls._token = data["access_token"]
            cls._token_created = now
            return cls._token


# Основная функция
async def check_auction_items(application):
    request_count = 0
    start_time = datetime.utcnow().timestamp()
    print("[INFO] Auction monitoring started")
    while True:
        all_items = list(tracked_items.find({"notify": True}))
        if not all_items:
            await asyncio.sleep(10)
            continue

        # Группируем по item_id
        items_by_id = {}
        for item in all_items:
            items_by_id.setdefault(item["item_id"], []).append(item)

        for item_id, items in items_by_id.items():
            # API limit control
            if request_count >= REQUESTS_PER_MIN:
                elapsed = datetime.utcnow().timestamp() - start_time
                if elapsed < 60:
                    await asyncio.sleep(60 - elapsed)
                request_count = 0
                start_time = datetime.utcnow().timestamp()
            try:
                token = await StalcraftAuth.get_token()
                headers = {"Authorization": f"Bearer {token}"}
                params = {"additional": "true"}
                async with httpx.AsyncClient(timeout=20) as client:
                    url = f"{API_BASE_URL}/ru/auction/{item_id}/lots"
                    resp = await client.get(url, headers=headers, params=params)
                    resp.raise_for_status()
                    data = resp.json()
                lots = data.get("lots", [])
                await process_auction_data(application, items, lots)
                request_count += 1
            except Exception as e:
                print(f"[ERROR] Auction check failed for item_id={item_id}: {e}")
                await asyncio.sleep(2)
        await asyncio.sleep(1)  # Пауза между циклами (регулируй под нагрузку)


async def process_auction_data(application, tracked_items_for_id, lots):
    now = datetime.now(timezone.utc)
    for lot in lots:
        # Проверка полей
        if not all(k in lot for k in ("itemId", "amount", "startPrice", "endTime")):
            continue
        # Проверка времени окончания лота
        try:
            end_time = datetime.fromisoformat(lot["endTime"].replace("Z", "+00:00"))
        except Exception:
            continue
        remaining_minutes = (end_time - now).total_seconds() / 60
        if remaining_minutes <= 0:
            continue
        # Пропуск уже отправленных лотов
        if processed_lots.find_one(
            {
                "item_id": lot["itemId"],
                "start_time": lot.get("startTime"),
                "end_time": lot["endTime"],
            }
        ):
            continue

        # Выбор цены: buyout или ставка
        if (
            lot.get("itemId") == "y5k0"
        ):  # вместо y5k0 укажи нужный ID или убери условие вообще для теста
            import json

            with open("debug_lot.json", "a", encoding="utf-8") as f:
                f.write(json.dumps(lot, ensure_ascii=False, indent=2))
                f.write("\n" + "=" * 40 + "\n")

        price_type = None
        if remaining_minutes > TRACK_WINDOW_MINUTES and lot.get("buyoutPrice", 0) > 0:
            total_price = lot["buyoutPrice"]
            price_per_unit = total_price / lot["amount"]
            price_type = "buyout"
        else:
            price_type = "bid"
            total_price = lot.get("currentPrice", 0) or lot["startPrice"]
            price_per_unit = total_price / lot["amount"]

        # Для каждого фильтра отслеживания
        for filter_ in tracked_items_for_id:
            # Пропуск если юзер не найден (на всякий случай)
            user = users_collection.find_one({"user_id": filter_["user_id"]})
            if not user:
                continue
            # Сравниваем условия (реализуй под свои нужды, пример для обычных товаров):
            if filter_["type"] == "item":
                # Обычные предметы: по цене и количеству
                if filter_["type"] == "item":
                    if (
                        price_per_unit > filter_["price"]
                        or lot["amount"] < filter_["min_count"]
                    ):
                        continue
                    # отправляем уведомление
            else:
                # Артефакты: тут добавишь свою фильтрацию по редкости/процентам когда будет надо
                pass

            # Всё подходит — отправляем уведомление
            await send_lot_notification(
                application,
                filter_,
                lot,
                price_type,
                price_per_unit,
                total_price,
                remaining_minutes,
            )
            processed_lots.insert_one(
                {
                    "item_id": lot["itemId"],
                    "start_time": lot.get("startTime"),
                    "end_time": lot["endTime"],
                    "notified_users": [filter_["user_id"]],
                    "created_at": datetime.now(timezone.utc),
                }
            )


async def send_lot_notification(
    application,
    filter_,
    lot,
    price_type,
    price_per_unit,
    total_price,
    remaining_minutes,
):
    """
    Отправка уведомления о лоте пользователю.
    Показывает:
    - Название товара
    - Тип цены (Выкуп/Ставка)
    - Количество
    - Общая цена
    - Цена за 1 шт (если amount > 1)
    - Время до конца
    """
    try:
        amount = lot["amount"]
        total_price_str = f"{int(total_price):,}".replace(",", " ")
        price_per_unit_str = f"{round(price_per_unit, 2):,}".replace(",", " ")
        msg = (
            f"🛒 Найден выгодный лот!\n"
            f"Товар: {filter_['name']}\n"
            f"Тип цены: {'Выкуп' if price_type == 'buyout' else 'Ставка'}\n"
            f"Количество: {amount}\n"
            f"Общая цена: {total_price_str} руб\n"
        )
        if amount > 1:
            msg += f"Цена за 1 шт: {price_per_unit_str} руб\n"
        msg += f"Время до конца: {int(remaining_minutes)} минут\n"
        await application.bot.send_message(chat_id=filter_["user_id"], text=msg)
        print(f"[INFO] Notification sent to {filter_['user_id']}")
    except Exception as e:
        print(f"[ERROR] Failed to send notification: {e}")
