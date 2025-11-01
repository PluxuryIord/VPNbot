import asyncio
import logging
import datetime

from aiogram import Bot
from database import db_commands as db
from keyboards import get_renewal_kb, get_main_menu_kb
from config import settings

log = logging.getLogger(__name__)


async def check_expirations(bot: Bot):
    """
    Главная задача планировщика:
    Запускается 1 раз в час и проверяет истекающие/истекшие ключи.
    """
    log.info("Starting background expiration checker...")
    while True:
        try:
            # === 1. ПРОВЕРКА КЛЮЧЕЙ, ИСТЕКАЮЩИХ ЧЕРЕЗ 24 ЧАСА (ЗАПРОС 3) ===

            #
            warning_keys = await db.get_keys_for_renewal_warning(hours=24)
            for key in warning_keys:
                try:
                    kb = get_renewal_kb(key.id)
                    await bot.send_message(
                        key.user_id,
                        f"🔔 **Напоминание:**\n\n"
                        f"Ваш ключ для тарифа «{key.name}» истекает менее чем через 24 часа.\n\n"
                        "Чтобы избежать прерывания, вы можете продлить его прямо сейчас.",
                        reply_markup=kb
                    )
                    await db.mark_renewal_warning_sent(key.id)
                except Exception as e:
                    log.warning(f"Failed to send 24h warning to {key.user_id} for key {key.id}: {e}")

            # === 2. ПРОВЕРКА КЛЮЧЕЙ, КОТОРЫЕ ИСТЕКЛИ В ЭТОТ ЧАС (ЗАПРОС 1 и 3) ===

            expired_keys = await db.get_keys_for_expiry_notification()

            for key in expired_keys:
                try:
                    #
                    if key.order_id is None:
                        #
                        await bot.send_message(
                            key.user_id,
                            "⌛️ **Ваш пробный период (24ч) истек.**\n\n"
                            "Надеемся, вам понравилась скорость! 🇫🇮\n"
                            "Чтобы продолжить, вы можете приобрести любой тариф в главном меню (кнопка \"🛒 Купить VPN\").",
                            reply_markup=get_main_menu_kb(user_id=key.user_id),
                            parse_mode="Markdown"
                        )
                    else:
                        await bot.send_message(
                            key.user_id,
                            f"❌ **Срок действия вашего ключа истек.**\n\n"
                            "Вы можете продлить его, чтобы восстановить доступ.",
                            reply_markup=get_renewal_kb(key.id),
                            parse_mode="Markdown"
                        )
                    await db.mark_expiry_notification_sent(key.id)
                except Exception as e:
                    log.warning(f"Failed to send expiry notification to {key.user_id} for key {key.id}: {e}")

        except Exception as e:
            log.error(f"Error in expiration checker task: {e}")

        await asyncio.sleep(600)