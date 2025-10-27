# handlers/webhook_handlers.py
import logging
from aiohttp import web
from aiogram import Bot
from yookassa.domain.notification import WebhookNotification

from database import db_commands as db
from utils import handle_payment_logic


async def yookassa_webhook_handler(request: web.Request):
    """
    Обработчик вебхуков от ЮKassa.
    Теперь он ВЫДАЕТ КЛЮЧИ.
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
            # [cite: 138]
            order_id_str = payment.metadata.get("order_id")
            if not order_id_str:
                logging.error(f"Webhook error: Order ID not in metadata for payment {payment.id}")
                return web.Response(status=200)  # Отвечаем 200, ЮKassa не будет повторять

            order_id = int(order_id_str)

            # 1. Проверяем заказ в нашей БД
            order = await db.get_order_by_id(order_id)
            if not order:
                logging.error(f"Order {order_id} not found in DB (Webhook).")
                return web.Response(status=200)

            # 2. Проверяем, что он еще не оплачен (защита от двойной обработки)
            if order.status == 'paid':
                logging.warning(f"Order {order_id} is already paid (Webhook).")
                return web.Response(status=200)

            # 3. Обновляем статус заказа
            await db.update_order_status(order_id, payment.id, status='paid')
            logging.info(f"Order {order_id} marked as 'paid' by webhook.")

            # 4. Вызываем универсальную функцию обработки
            success, message_text = await handle_payment_logic(bot, order, payment)

            # 5. Отправляем пользователю НОВОЕ СООБЩЕНИЕ с ключом или ошибкой
            await bot.send_message(
                chat_id=order.user_id,
                text=message_text,
                parse_mode="Markdown",
                disable_web_page_preview=True
            )
            logging.info(f"Webhook for order {order_id} completed. Success: {success}")


        except Exception as e:
            logging.critical(f"Error processing payment {payment.id} in webhook: {e}")
            return web.Response(status=200)

    elif notification.event == "payment.canceled":
        try:
            order_id_str = payment.metadata.get("order_id")
            if order_id_str:
                order_id = int(order_id_str)
                # Помечаем заказ как отмененный в нашей БД
                await db.update_order_status(order_id, payment.id, status='failed')
                logging.info(f"Order {order_id} marked as 'failed' (canceled) by webhook.")
        except Exception as e:
            logging.warning(f"Error processing payment.canceled webhook: {e}")

    # Обязательно отвечаем 200 OK
    return web.Response(status=200)
