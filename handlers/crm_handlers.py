"""
Обработчики команд для CRM-топиков.
Работают только в топиках CRM-группы.
"""
import logging
import datetime
import html
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command
from config import settings
from database import db_commands as db
from utils import issue_trial_key
import crm
import vpn_api

log = logging.getLogger(__name__)
router = Router()


async def is_crm_topic(message: Message) -> bool:
    """
    Проверяет, что сообщение отправлено в топике CRM-группы.
    
    Returns:
        True если это топик в CRM-группе, False иначе
    """
    if not settings.CRM_GROUP_ID:
        return False
    
    # Проверяем, что это CRM-группа и есть message_thread_id (топик)
    if message.chat.id == settings.CRM_GROUP_ID and message.message_thread_id:
        return True
    
    return False


def format_bytes(bytes_value: int) -> str:
    """Форматирует байты в читаемый вид"""
    if bytes_value is None:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"


def format_datetime(dt: datetime.datetime) -> str:
    """Форматирует дату и время"""
    if dt is None:
        return "Неизвестно"
    return dt.strftime("%d.%m.%Y %H:%M")


async def get_user_total_traffic(keys: list) -> dict:
    """
    Получает общий трафик пользователя по всем его ключам.

    Args:
        keys: Список ключей пользователя из БД

    Returns:
        dict с полями:
        - total_traffic: общий трафик в байтах
        - total_traffic_formatted: отформатированная строка
        - keys_checked: количество проверенных ключей
        - keys_with_traffic: количество ключей с трафиком
    """
    total_traffic = 0
    keys_checked = 0
    keys_with_traffic = 0

    for key in keys:
        try:
            # Получаем статистику трафика для каждого ключа
            traffic_data = await vpn_api.get_traffic_by_vless_key(key.vless_key)

            if traffic_data:
                keys_checked += 1
                key_traffic = traffic_data.get('total', 0)

                if key_traffic > 0:
                    keys_with_traffic += 1
                    total_traffic += key_traffic

                log.debug(f"Ключ {key.id}: {vpn_api.format_traffic(key_traffic)}")
        except Exception as e:
            log.warning(f"Не удалось получить трафик для ключа {key.id}: {e}")
            continue

    return {
        'total_traffic': total_traffic,
        'total_traffic_formatted': vpn_api.format_traffic(total_traffic),
        'keys_checked': keys_checked,
        'keys_with_traffic': keys_with_traffic
    }


@router.message(Command("info"))
async def cmd_info(message: Message):
    """
    Команда /info - показывает полную информацию о пользователе.
    Работает только в топиках CRM-группы.
    """
    # Проверяем, что это топик в CRM-группе
    if not await is_crm_topic(message):
        return
    
    try:
        # Получаем user_id из топика
        # Ищем пользователя по crm_topic_id
        from sqlalchemy import select
        from database.db_commands import AsyncSessionLocal
        from database.models import Users
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Users).where(Users.c.crm_topic_id == message.message_thread_id)
            )
            user = result.fetchone()
        
        if not user:
            await message.reply(
                "❌ Пользователь не найден.\n"
                "Возможно, топик создан вручную или данные не синхронизированы."
            )
            return
        
        user_id = user.user_id
        
        # Получаем детальную статистику
        stats = await db.get_user_stats_detailed(user_id)
        
        if not stats:
            await message.reply("❌ Не удалось получить информацию о пользователе.")
            return
        
        user_data = stats['user']

        # Получаем статистику трафика
        log.info(f"CRM: Получение статистики трафика для пользователя {user_id}...")
        traffic_stats = await get_user_total_traffic(stats['keys'])

        # Формируем информацию о пользователе
        info_text = "📊 <b>Полная информация о пользователе</b>\n\n"

        # Основная информация
        info_text += "👤 <b>Основные данные:</b>\n"
        info_text += f"├ ID: <code>{user_data.user_id}</code>\n"
        info_text += f"├ Имя: {html.escape(user_data.first_name)}\n"

        if user_data.username:
            info_text += f"├ Username: @{html.escape(user_data.username)}\n"
        else:
            info_text += f"├ Username: <i>не указан</i>\n"

        info_text += f"└ Дата регистрации: {format_datetime(user_data.created_at)}\n\n"
        
        # Статистика по заказам
        info_text += "💰 <b>Финансы:</b>\n"
        info_text += f"├ Всего заказов: {stats['total_orders']}\n"
        info_text += f"└ Потрачено: {stats['total_spent']:.2f} ₽\n\n"

        # Статистика по ключам
        info_text += "🔑 <b>Ключи:</b>\n"
        info_text += f"├ Всего ключей: {stats['total_keys_count']}\n"
        info_text += f"├ Активных: {stats['active_keys_count']}\n"
        info_text += f"└ Истекших: {stats['total_keys_count'] - stats['active_keys_count']}\n\n"

        # Статистика по трафику
        info_text += "📊 <b>Трафик:</b>\n"
        info_text += f"├ Всего потрачено: <b>{traffic_stats['total_traffic_formatted']}</b>\n"
        info_text += f"├ Проверено ключей: {traffic_stats['keys_checked']}/{stats['total_keys_count']}\n"
        info_text += f"└ Ключей с трафиком: {traffic_stats['keys_with_traffic']}\n\n"
        
        # Статус триала
        info_text += "🎁 <b>Пробный период:</b>\n"
        if user_data.has_received_trial:
            info_text += "└ ✅ Использован\n\n"
        else:
            info_text += "└ ❌ Не использован\n\n"
        
        # Детали по ключам
        if stats['keys']:
            info_text += "📋 <b>Детали ключей:</b>\n"
            now = datetime.datetime.now()
            
            for i, key in enumerate(stats['keys'][:10], 1):  # Показываем первые 10
                is_active = key.expires_at > now
                status_emoji = "✅" if is_active else "❌"
                
                if key.order_id:
                    key_type = f"Платный ({html.escape(key.product_name or 'Неизвестно')})"
                else:
                    key_type = "Пробный (24ч)"
                
                info_text += f"\n{i}. {status_emoji} {key_type}\n"
                info_text += f"   ├ Создан: {format_datetime(key.created_at)}\n"
                info_text += f"   └ Истекает: {format_datetime(key.expires_at)}\n"
            
            if len(stats['keys']) > 10:
                info_text += f"\n<i>... и ещё {len(stats['keys']) - 10} ключей</i>\n"
        
        # Отправляем информацию
        await message.reply(info_text, parse_mode="HTML")
        
        log.info(f"CRM: Показана информация о пользователе {user_id} в топике {message.message_thread_id}")
        
    except Exception as e:
        log.error(f"Ошибка в команде /info: {e}", exc_info=True)
        await message.reply(
            "❌ Произошла ошибка при получении информации.\n"
            f"Детали: {str(e)}"
        )


@router.message(Command("trial"))
async def cmd_trial(message: Message, bot: Bot):
    """
    Команда /trial - выдаёт пробный ключ пользователю.
    Работает только в топиках CRM-группы.
    Выдаёт триал независимо от того, получал ли пользователь его ранее.
    """
    # Проверяем, что это топик в CRM-группе
    if not await is_crm_topic(message):
        return
    
    try:
        # Получаем user_id из топика
        from sqlalchemy import select
        from database.db_commands import AsyncSessionLocal
        from database.models import Users
        
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Users).where(Users.c.crm_topic_id == message.message_thread_id)
            )
            user = result.fetchone()
        
        if not user:
            await message.reply(
                "❌ Пользователь не найден.\n"
                "Возможно, топик создан вручную или данные не синхронизированы."
            )
            return
        
        user_id = user.user_id
        first_name = user.first_name
        
        # Выдаём триал (независимо от статуса has_received_trial)
        log.info(f"CRM: Выдача триала пользователю {user_id} через команду /trial в топике")
        
        vless_key = await issue_trial_key(bot, user_id, first_name, force=True)
        
        if vless_key:
            await message.reply(
                f"✅ <b>Пробный ключ выдан!</b>\n\n"
                f"👤 Пользователь: {html.escape(first_name)} (ID: <code>{user_id}</code>)\n"
                f"⏱ Срок действия: 24 часа\n\n"
                f"🔑 Ключ:\n<code>{html.escape(vless_key)}</code>\n\n"
                f"<i>Ключ также отправлен пользователю в личные сообщения.</i>",
                parse_mode="HTML"
            )
            
            # Уведомляем в CRM
            await crm.notify_trial_taken(
                bot=bot,
                user_id=user_id,
                expires_at=(datetime.datetime.now() + datetime.timedelta(hours=24)).strftime("%d.%m.%Y %H:%M")
            )
            
            log.info(f"CRM: Триал успешно выдан пользователю {user_id}")
        else:
            await message.reply(
                "❌ Не удалось выдать пробный ключ.\n"
                "Проверьте логи бота для деталей."
            )
            log.error(f"CRM: Не удалось выдать триал пользователю {user_id}")
        
    except Exception as e:
        log.error(f"Ошибка в команде /trial: {e}", exc_info=True)
        await message.reply(
            "❌ Произошла ошибка при выдаче пробного ключа.\n"
            f"Детали: {str(e)}"
        )

