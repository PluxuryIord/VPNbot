# handlers/webhook_handlers.py
import logging
from aiohttp import web
from aiogram import Bot
from yookassa.domain.notification import WebhookNotification

from database import db_commands as db


async def yookassa_webhook_handler(request: web.Request):
    """
    Обработчик вебхуков от ЮKassa.
    """
    bot: Bot = request.app['bot']

    try:
        data = await request.json()
        notification = WebhookNotification(data)
    except Exception as e:
        logging.error(f"Failed to parse YooKassa notification: {e}")
        return web.Response(status=400)

    payment = notification.object

    if notification.event == "payment.succeeded" and payment.status == "succeeded":
        try:
            order_id = int(payment.metadata.get("order_id"))
            if not order_id:
                raise ValueError("Order ID not in metadata")

            # 1. Проверяем заказ в нашей БД
            order = await db.get_order_by_id(order_id)
            if not order:
                logging.error(f"Order {order_id} not found in DB.")
                return web.Response(status=200)  # Отвечаем 200, чтобы ЮKassa не повторяла

            # 2. Проверяем, что он еще не оплачен (защита от двойной обработки)
            if order.status == 'paid':
                logging.warning(f"Order {order_id} is already paid.")
                return web.Response(status=200)

            # 3. Обновляем статус заказа
            await db.update_order_status(order_id, payment.id, status='paid')

            # 4. Inline-flow: ключ НЕ выдаем из вебхука, только отмечаем оплату.
            # Пользователь получит ключ при нажатии "Проверить оплату" в боте,
            # где мы отредактируем текущее меню и покажем ключ.
            logging.info(f"Order {order_id} marked as paid by webhook. Awaiting user check in bot.")

        except Exception as e:
            logging.critical(f"Error processing payment {payment.id}: {e}")
            return web.Response(status=200)

    elif notification.event == "payment.canceled":
        #обработка отмены
        pass

    # Обязательно отвечаем 200 OK
    return web.Response(status=200)