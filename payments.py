# payments.py
import uuid
from typing import Optional, Dict, Any

from yookassa import Configuration, Payment
from config import settings

# Настройка SDK ЮKassa
Configuration.account_id = settings.YOOKASSA_SHOP_ID.get_secret_value()
Configuration.secret_key = settings.YOOKASSA_SECRET_KEY.get_secret_value()


async def create_yookassa_payment(amount: float, description: str, order_id: int, metadata: Optional[Dict[str, Any]] = None): # Добавили metadata
    """
    Создает платеж в ЮKassa и возвращает URL для оплаты и ID платежа.
"""
    idempotence_key = str(uuid.uuid4())

    # Добавляем order_id в metadata по умолчанию
    payment_metadata = metadata or {}
    payment_metadata["order_id"] = str(order_id)

    payment_data = {
        "amount": {
            "value": f"{amount:.2f}",
            "currency": "RUB"
        },
        "confirmation": {

            "type": "redirect",
            "return_url": f"https://t.me/{settings.BOT_USERNAME}"
        },
        "capture": True,
        "description": description,
        "metadata": payment_metadata,

        # ⬇️ ⬇️ ⬇️ ВОТ ИЗМЕНЕНИЕ ⬇️ ⬇️ ⬇️
        "receipt": {
            "customer": {

            },
            "items": [
                {
                    "description": description,  #
                    "quantity": "1.00",
                    "amount": {
                        "value": f"{amount:.2f}",
                        "currency": "RUB"
                    },
                    "vat_code": "6"
                }
            ],
            "send": False
        }
    }

    payment = Payment.create(payment_data, idempotence_key)

    return payment.confirmation.confirmation_url, payment.id


async def check_yookassa_payment(payment_id: str):
    """
    Проверяет статус платежа в ЮKassa по его ID.
    Возвращает объект Payment.
    """
    try:
        payment_info = Payment.find_one(payment_id)
        return payment_info
    except Exception as e:
        print(f"Ошибка проверки платежа YooKassa {payment_id}: {e}")
        return None