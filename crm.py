"""
CRM модуль для работы с топиками в Telegram группе.
Каждому пользователю создается отдельный топик для отслеживания активности.

Основные функции:
- create_user_topic() - Создание топика для нового пользователя
- send_to_crm() - Отправка произвольного сообщения в топик пользователя
- notify_* - Набор функций для уведомлений о различных событиях

Требования:
- Группа с включенными топиками (форумами)
- Бот должен быть администратором с правами "Управление темами"
- CRM_GROUP_ID должен быть настроен в .env

Использование:
    from crm import create_user_topic, notify_trial_taken

    # Создание топика
    topic_id = await create_user_topic(bot, user_id, username, first_name)

    # Отправка уведомления
    await notify_trial_taken(bot, user_id, expires_at)
"""
import logging
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from config import settings
from database import db_commands as db

log = logging.getLogger(__name__)


async def create_user_topic(bot: Bot, user_id: int, username: str | None, first_name: str) -> int | None:
    """
    Создает топик для пользователя в CRM-группе.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        username: Username пользователя (может быть None)
        first_name: Имя пользователя
        
    Returns:
        ID созданного топика или None при ошибке
    """
    if not settings.CRM_GROUP_ID:
        log.warning("CRM_GROUP_ID не настроен, топик не создан")
        return None
    
    try:
        # Формируем название топика: только имя пользователя
        topic_name = first_name[:128]  # Telegram ограничивает длину названия

        # Создаем топик (форум-тред)
        forum_topic = await bot.create_forum_topic(
            chat_id=settings.CRM_GROUP_ID,
            name=topic_name
        )
        
        topic_id = forum_topic.message_thread_id
        
        # Сохраняем ID топика в БД
        await db.update_user_topic_id(user_id, topic_id)
        
        # Отправляем приветственное сообщение в топик
        await bot.send_message(
            chat_id=settings.CRM_GROUP_ID,
            message_thread_id=topic_id,
            text=(
                f"🆕 <b>Новый пользователь</b>\n\n"
                f"👤 Имя: {first_name}\n"
                f"🆔 User ID: <code>{user_id}</code>\n"
                f"📱 Username: @{username if username else 'не указан'}\n"
                f"📅 Дата регистрации: {format_datetime_now()}"
            ),
            parse_mode="HTML"
        )
        
        log.info(f"Создан топик {topic_id} для пользователя {user_id}")
        return topic_id
        
    except TelegramBadRequest as e:
        log.error(f"Ошибка создания топика для {user_id}: {e}")
        return None
    except Exception as e:
        log.error(f"Неожиданная ошибка при создании топика для {user_id}: {e}")
        return None


async def send_to_crm(
    bot: Bot,
    user_id: int,
    message: str,
    parse_mode: str = "HTML"
) -> bool:
    """
    Отправляет сообщение в топик пользователя в CRM-группе.
    
    Args:
        bot: Экземпляр бота
        user_id: ID пользователя
        message: Текст сообщения
        parse_mode: Режим парсинга (HTML/Markdown)
        
    Returns:
        True если сообщение отправлено успешно, False иначе
    """
    if not settings.CRM_GROUP_ID:
        return False
    
    try:
        # Получаем ID топика пользователя
        topic_id = await db.get_user_topic_id(user_id)
        
        if not topic_id:
            log.warning(f"Топик для пользователя {user_id} не найден")
            return False
        
        # Отправляем сообщение в топик
        await bot.send_message(
            chat_id=settings.CRM_GROUP_ID,
            message_thread_id=topic_id,
            text=message,
            parse_mode=parse_mode
        )
        
        return True
        
    except Exception as e:
        log.error(f"Ошибка отправки в CRM для {user_id}: {e}")
        return False


async def notify_trial_taken(bot: Bot, user_id: int, expires_at: str):
    """Уведомление о взятии пробного периода"""
    message = (
        f"🎁 <b>Взят пробный период</b>\n\n"
        f"⏰ Истекает: <code>{expires_at}</code>\n"
        f"⏳ Длительность: 24 часа"
    )
    await send_to_crm(bot, user_id, message)


async def notify_key_purchased(bot: Bot, user_id: int, product_name: str, amount: float, expires_at: str):
    """Уведомление о покупке ключа"""
    message = (
        f"💰 <b>Куплен ключ</b>\n\n"
        f"📦 Тариф: <b>{product_name}</b>\n"
        f"💵 Сумма: <b>{amount} ₽</b>\n"
        f"⏰ Истекает: <code>{expires_at}</code>"
    )
    await send_to_crm(bot, user_id, message)


async def notify_renewal_warning_sent(bot: Bot, user_id: int, product_name: str, hours_left: int):
    """Уведомление об отправке предупреждения о продлении (за 24ч)"""
    message = (
        f"🔔 <b>Отправлено предупреждение о продлении</b>\n\n"
        f"📦 Тариф: <b>{product_name}</b>\n"
        f"⏰ Осталось: <b>{hours_left} часов</b>"
    )
    await send_to_crm(bot, user_id, message)


async def notify_trial_warning_sent(bot: Bot, user_id: int):
    """Уведомление об отправке предупреждения о триале (за 2ч)"""
    message = (
        f"⏳ <b>Отправлено предупреждение о триале</b>\n\n"
        f"⏰ До истечения: <b>2 часа</b>\n"
        f"💡 Предложена скидка на продление"
    )
    await send_to_crm(bot, user_id, message)


async def notify_key_expired(bot: Bot, user_id: int, is_trial: bool):
    """Уведомление об истечении ключа"""
    key_type = "пробного периода" if is_trial else "платного ключа"
    message = (
        f"❌ <b>Истек срок {key_type}</b>\n\n"
        f"📤 Отправлено уведомление пользователю"
    )
    await send_to_crm(bot, user_id, message)


async def notify_trial_reminder_sent(bot: Bot, user_id: int):
    """Уведомление об отправке напоминания о триале (кто не взял)"""
    message = (
        f"👋 <b>Отправлено напоминание о триале</b>\n\n"
        f"📊 Пользователь зарегистрирован 24ч назад\n"
        f"❌ Триал не взят"
    )
    await send_to_crm(bot, user_id, message)


async def notify_payment_pending(bot: Bot, user_id: int, product_name: str, amount: float, order_id: int):
    """Уведомление о создании заказа (ожидание оплаты)"""
    message = (
        f"🕐 <b>Создан заказ (ожидание оплаты)</b>\n\n"
        f"📦 Тариф: <b>{product_name}</b>\n"
        f"💵 Сумма: <b>{amount} ₽</b>\n"
        f"🆔 Order ID: <code>{order_id}</code>"
    )
    await send_to_crm(bot, user_id, message)


def format_datetime_now() -> str:
    """Форматирует текущую дату и время"""
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

