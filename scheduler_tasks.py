import asyncio
import logging
import datetime

from aiogram import Bot
from database import db_commands as db
from keyboards import get_renewal_kb, get_trial_discount_kb, get_take_trial_reminder_kb, get_trial_expired_kb
from config import settings
import crm

log = logging.getLogger(__name__)


async def check_expirations(bot: Bot):
    """Главная задача планировщика."""
    log.info("Starting background expiration checker...")
    while True:
        try:
            # === 1. ПРЕДУПРЕЖДЕНИЕ ЗА 24 ЧАСА (Платные ключи) ===
            warning_keys = await db.get_keys_for_renewal_warning(hours=24)
            for key in warning_keys:
                try:
                    await bot.send_message(
                        key.user_id,
                        f"🔔 **Напоминание:**\n\n"
                        f"Ваш ключ для тарифа «{key.name}» истекает менее чем через 24 часа.\n"
                        "Чтобы избежать прерывания, вы можете продлить его прямо сейчас.",
                        reply_markup=get_renewal_kb(key.id),
                        parse_mode="Markdown"
                    )
                    await db.mark_renewal_warning_sent(key.id)

                    # CRM: Уведомление об отправке предупреждения
                    await crm.notify_renewal_warning_sent(bot, key.user_id, key.name, 24)
                except Exception as e:
                    log.warning(f"Failed to send 24h warning to {key.user_id}: {e}")

            # === 2. TASK 4: ПРЕДУПРЕЖДЕНИЕ ЗА 2 ЧАСА (Пробные ключи) ===
            trial_warnings = await db.get_trial_keys_for_warning(hours=2)
            for key in trial_warnings:
                try:
                    await bot.send_message(
                        key.user_id,
                        "⏳ **Ваш пробный период истекает через 2 часа!**\n\n"
                        "Понравилась скорость? 🔥\n"
                        "Продлите доступ сейчас со скидкой: **1 месяц (Финляндия) всего за 119₽** вместо 199₽!",
                        reply_markup=get_trial_discount_kb(key.id),
                        parse_mode="Markdown"
                    )
                    await db.mark_trial_warning_sent(key.id)

                    # CRM: Уведомление об отправке предупреждения о триале
                    await crm.notify_trial_warning_sent(bot, key.user_id)
                except Exception as e:
                    log.warning(f"Failed to send 2h trial warning to {key.user_id}: {e}")

            # === 3. ИСТЕКШИЕ КЛЮЧИ (Task 3 update) ===
            expired_keys = await db.get_keys_for_expiry_notification()
            for key in expired_keys:
                try:
                    if key.order_id is None:
                        # TASK 3: Сообщение об истечении триала с кнопкой продления
                        await bot.send_message(
                            key.user_id,
                            "⌛️ **Ваш пробный период (24ч) истек.**\n\n"
                            "Надеемся, вам понравилась скорость! 🇫🇮\n\n"
                            "Чтобы продолжить пользоваться VPN, продлите подписку.\n\n"
                            "💬 **Напишите в поддержку свой отзыв и получите 7 дней бесплатно!**",
                            reply_markup=get_trial_expired_kb(key.id),
                            parse_mode="Markdown"
                        )
                    else:
                        # Обычное истечение платного ключа
                        await bot.send_message(
                            key.user_id,
                            "❌ **Срок действия вашего ключа истек.**\n\n"
                            "Вы можете продлить его, чтобы восстановить доступ.",
                            reply_markup=get_renewal_kb(key.id),
                            parse_mode="Markdown"
                        )
                    await db.mark_expiry_notification_sent(key.id)

                    # CRM: Уведомление об истечении ключа
                    await crm.notify_key_expired(bot, key.user_id, is_trial=(key.order_id is None))
                except Exception as e:
                    log.warning(f"Failed to send expiry notification to {key.user_id}: {e}")

            # === 4. ЗАДАЧА 2: НАПОМИНАНИЕ О ТРИАЛЕ (КТО НЕ ВЗЯЛ) ===
            users_to_remind = await db.get_users_for_trial_reminder(hours_min=24, hours_max=25)
            for user_id in users_to_remind:
                try:
                    await bot.send_message(
                        user_id,
                        "👋 Привет!\n\n"
                        "Вы были в боте 24 часа назад, но так и не попробовали наш VPN.\n\n"
                        "Не упускайте шанс оценить премиум-скорость (Финляндия 🇫🇮) бесплатно!\n\n"
                        "💬 Если нужна помощь — напишите в поддержку, мы всегда на связи!",
                        reply_markup=get_take_trial_reminder_kb(),
                        parse_mode="Markdown"
                    )
                    await db.mark_trial_reminder_sent(user_id)

                    # CRM: Уведомление об отправке напоминания о триале
                    await crm.notify_trial_reminder_sent(bot, user_id)
                except Exception as e:
                    log.warning(f"Failed to send trial reminder to {user_id}: {e}")
                    # Если юзер заблочил бота, тоже ставим метку, чтоб не пытаться снова
                    if "bot was blocked" in str(e).lower():
                        await db.mark_trial_reminder_sent(user_id)

        except Exception as e:
            log.error(f"Error in expiration checker task: {e}")

        await asyncio.sleep(600)  # Проверка каждые 10 минут
