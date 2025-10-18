# utils.py
# ИЗМЕНЕНИЕ: uuid и logging нам больше не нужны
# import uuid
# import logging
import datetime
import secrets

from aiogram import Bot

from config import settings
from database import db_commands as db


def generate_vless_key(user_id: int, product_name: str) -> str:
    """
    Генерирует ТЕСТОВУЮ строку VLESS с ГАРАНТИЕЙ уникальности.
    Уникальность достигается за счет случайного суффикса.
    """
    unique_suffix = secrets.token_hex(6)  # 12 hex-символов
    dummy_key = (
        f"vless://DUMMY-KEY-FOR-{user_id}-{unique_suffix}"
        f"@{settings.VLESS_SERVER}:{settings.VLESS_PORT}?type=ws&security=tls&sni={settings.VLESS_SNI}"
        f"#{product_name}"
    )
    return dummy_key


async def issue_key_to_user(bot: Bot, user_id: int, product_id: int, order_id: int) -> bool:
    """
    Упрощенный цикл выдачи ключа: генерация пустышки,
    добавление в БД и уведомление пользователя.
    """
    try:
        product = await db.get_product_by_id(product_id)
        if not product:
            raise ValueError(f"Product {product_id} not found")

        # 1. Генерируем ключ-пустышку
        vless_string = generate_vless_key(user_id, product.name)

        # 2. Рассчитываем дату истечения
        expires_at = datetime.datetime.now() + datetime.timedelta(days=product.duration_days)

        # 3. [ИЗМЕНЕНИЕ] Убрали симуляцию API-вызова
        # logging.info(f"Simulating adding UUID {vless_uuid} to VLESS server... SUCCESS.")

        # 4. Сохраняем ключ в нашей БД
        await db.add_vless_key(
            user_id=user_id,
            order_id=order_id,
            vless_key=vless_string,
            expires_at=expires_at
        )

        # 5. Отправляем ключ пользователю
        await bot.send_message(
            user_id,
            "✅ **Оплата прошла успешно!**\n\n"
            "Ваш **тестовый** ключ доступа:\n"  # <- Добавил "тестовый"
            f"```\n{vless_string}\n```\n\n"
            f"Срок действия: **{product.duration_days} дней** (до {expires_at.strftime('%Y-%m-%d %H:%M')})\n\n"
            "Скопируйте ключ и добавьте его в V2Box.",
            parse_mode="Markdown"
        )
        return True

    except Exception as e:
        # logging нам недоступен, если мы его закомментировали
        print(f"Failed to issue key for order {order_id} (user {user_id}): {e}")
        # Уведомляем админа о провале
        try:
            for admin_id in settings.get_admin_ids:
                await bot.send_message(
                    admin_id,
                    f"⚠️ **СБОЙ ВЫДАЧИ КЛЮЧА** ⚠️\n\n"
                    f"Не удалось выдать ключ для заказа #{order_id} (Пользователь: {user_id}).\n"
                    f"Ошибка: {e}\n\n"
                    "**Требуется ручное вмешательство!**"
                )
        except Exception as admin_notify_e:
            print(f"Failed to notify admin about failure: {admin_notify_e}")

        return False