import httpx
import logging
import json

from typing import Optional, Dict, Any
from config import settings

log = logging.getLogger(__name__)

API_URL = "https://pay.crypt.bot/api"
API_TOKEN = settings.CRYPTO_BOT_TOKEN.get_secret_value()
log.info(f"Crypto Bot Token used in headers: {API_TOKEN[:5]}...{API_TOKEN[-5:] if len(API_TOKEN) > 10 else ''}")

headers = {
    "Crypto-Pay-API-Token": API_TOKEN
}


async def create_crypto_invoice(amount_rub: float, currency: str, order_id: int, metadata: Dict[str, Any]) -> Optional[
    str]:
    """
    Создает счет в Crypto Bot и возвращает URL для оплаты.
    """
    try:
        amount_usdt = await get_rub_to_usdt_amount(amount_rub)
        if amount_usdt is None:
            log.error(f"Не удалось конвертировать {amount_rub} RUB в USDT для заказа {order_id}.")
            return None
        amount_usdt_str = f"{amount_usdt:.6f}".rstrip('0').rstrip('.')
        payload_str = json.dumps(metadata)

        async with httpx.AsyncClient(headers=headers) as client:
            response = await client.post(
                f"{API_URL}/createInvoice",
                json={
                    "asset": "USDT",
                    "amount": amount_usdt_str,
                    "description": f"Заказ #{order_id}",
                    "payload": payload_str,  #
                    "paid_btn_name": "openBot",
                    "paid_btn_url": f'''https://t.me/{settings.BOT_USERNAME}'''
                }
            )

            if response.status_code == 200 or response.status_code == 201:
                data = response.json()
                if data.get("ok"):
                    log.info(f"Crypto Bot: Счет {data['result']['invoice_id']} для заказа {order_id} создан.")
                    return data['result']['pay_url']
                else:
                    log.error(f"Ошибка создания счета Crypto Bot (API Error): {response.status_code} - {response.text}")
                    return None
            else:
                log.error(f"Ошибка создания счета Crypto Bot (HTTP Error): {response.status_code} - {response.text}")
                return None

    except Exception as e:
        log.error(f"Исключение при создании счета Crypto Bot: {e}")
        return None


async def get_rub_to_usdt_amount(amount_rub: float) -> Optional[float]:
    """
    Получает курс USDT к RUB через Coingecko API
    и конвертирует сумму из рублей в USDT.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Получаем цену USDT в RUB
            response = await client.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "tether",  # ID для USDT
                    "vs_currencies": "rub"  # Валюта, в которой нужна цена
                }
            )
            response.raise_for_status()
            data = response.json()

            if "tether" in data and "rub" in data["tether"]:
                price_rub_per_usdt = data["tether"]["rub"]
                if price_rub_per_usdt <= 0:
                    log.error(f"Coingecko API вернул некорректный курс: {price_rub_per_usdt}")
                    return None

                amount_usdt = round(amount_rub / price_rub_per_usdt, 2)
                log.info(
                    f"Конвертация (Coingecko): {amount_rub} RUB = {amount_usdt} USDT (курс ~{price_rub_per_usdt:.2f} RUB/USDT)")
                return amount_usdt
            else:
                log.error(f"Ошибка API Coingecko: Не найден курс tether/rub в ответе: {data}")
                return None

    except Exception as e:
        log.error(f"Исключение при получении курса USDT/RUB (Coingecko): {e}")
        return None
