import logging
import json
import base64
from aiohttp import web
from aiogram import Bot
from yookassa.domain.notification import WebhookNotification

from database import db_commands as db
from utils import handle_payment_logic
from keyboards import get_renewal_kb, get_main_menu_kb, get_payment_success_kb, get_instruction_platforms_kb

log = logging.getLogger(__name__)


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
            order_id_str = payment.metadata.get("order_id")
            if not order_id_str:
                logging.error(f"Yookassa Webhook error: Order ID not in metadata for payment {payment.id}")
                return web.Response(status=200)

            order_id = int(order_id_str)
            order = await db.get_order_by_id(order_id)
            if not order:
                logging.error(f"Order {order_id} not found in DB (Yookassa Webhook).")
                return web.Response(status=200)

            if order.status == 'paid':
                logging.warning(f"Order {order_id} is already paid (Yookassa Webhook).")
                return web.Response(status=200)

            await db.update_order_status(order_id, payment.id, status='paid')
            logging.info(f"Order {order_id} marked as 'paid' by Yookassa webhook.")

            metadata = payment.metadata
            success, message_text, operation_type = await handle_payment_logic(bot, order_id, metadata)
            kb = None
            if operation_type == "new_key":
                kb = get_instruction_platforms_kb()  #
            elif operation_type == "renewal":
                renewal_key_id = metadata.get("renewal_key_id")
                kb = get_payment_success_kb(renewal_key_id)  #

            await bot.send_message(
                chat_id=order.user_id,
                text=message_text,
                parse_mode="HTML",  #
                disable_web_page_preview=True,
                reply_markup=kb
            )
            logging.info(f"Yookassa Webhook for order {order_id} completed. Success: {success}")

        except Exception as e:
            logging.critical(f"Error processing payment {payment.id} in Yookassa webhook: {e}")
            return web.Response(status=200)

    elif notification.event == "payment.canceled":
        pass

    return web.Response(status=200)


async def crypto_bot_webhook_handler(request: web.Request):
    """
    Обработчик вебхуков от Crypto Bot.
    """
    bot: Bot = request.app['bot']

    try:
        data = await request.json()
        log.info(f"Crypto Bot Webhook received: {data}")

        if data.get("update_type") == "invoice_paid":
            invoice = data.get("payload", {})

            payload_str = invoice.get("payload")
            if not payload_str:
                log.error("Crypto Bot Webhook error: 'payload' (string) not in invoice data")
                return web.Response(status=200)

            metadata = json.loads(payload_str)
            order_id_str = metadata.get("order_id")

            if not order_id_str:
                log.error(
                    f"Crypto Bot Webhook error: 'order_id' not in payload for invoice {invoice.get('invoice_id')}")
                return web.Response(status=200)

            try:
                order_id = int(order_id_str)
            except (ValueError, TypeError):
                log.error(f"Crypto Bot Webhook error: Invalid order_id format '{order_id_str}'")
                return web.Response(status=200)

            order = await db.get_order_by_id(order_id)
            if not order:
                log.error(f"Order {order_id} not found in DB (Crypto Webhook).")
                return web.Response(status=200)

            if order.status == 'paid':
                logging.warning(f"Order {order_id} is already paid (Crypto Webhook).")
                return web.Response(status=200)

            invoice_id_str = str(invoice.get('invoice_id'))
            await db.update_order_status(order_id, invoice_id_str, status='paid')
            logging.info(f"Order {order_id} marked as 'paid' by Crypto Bot webhook (Invoice: {invoice_id_str}).")

            success, message_text, operation_type = await handle_payment_logic(bot, order_id, metadata)

            kb = None
            if operation_type == "new_key":
                kb = get_instruction_platforms_kb()  #
            elif operation_type == "renewal":
                renewal_key_id = metadata.get("renewal_key_id")
                kb = get_payment_success_kb(renewal_key_id)  #

            await bot.send_message(
                chat_id=order.user_id,
                text=message_text,
                parse_mode="HTML",
                disable_web_page_preview=True,
                reply_markup=kb
            )
            logging.info(f"Crypto Bot Webhook for order {order_id} completed. Success: {success}")

    except json.JSONDecodeError as e:
        logging.error(f"Crypto Bot Webhook: Failed to parse JSON body: {e}")
        return web.Response(status=400)
    except Exception as e:
        logging.critical(f"Error processing Crypto Bot webhook: {e}")
        return web.Response(status=200)

    return web.Response(status=200)


async def subscription_handler(request: web.Request):
    """
    Обработчик для V2Ray-клиентов (ссылка на подписку).
    (Модель 2: 1 токен = 1 ключ)
    """
    try:
        token = request.match_info.get('token')
        if not token:
            return web.Response(status=404, text="Token not found")

        #
        active_key = await db.get_key_by_subscription_token(token)

        if not active_key:
            #
            return web.Response(status=200, text="")

            #
        subscription_base64 = base64.b64encode(active_key.encode('utf-8')).decode('utf-8')

        log.info(f"Subscription link for key (token {token[:4]}...) accessed.")

        return web.Response(status=200, body=subscription_base64, content_type="text/plain")

    except Exception as e:
        log.error(f"Error in subscription_handler: {e}")
        return web.Response(status=500, text="Internal server error")