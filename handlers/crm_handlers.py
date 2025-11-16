"""
Обработчики команд для CRM-топиков.
Работают только в топиках CRM-группы.
"""
import logging
import datetime
import html
import math
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import settings
from database import db_commands as db
from utils import issue_trial_key
from keyboards import get_crm_keys_list_kb, get_crm_key_details_kb, get_crm_country_selection_kb
import crm
import vpn_api

log = logging.getLogger(__name__)
router = Router()

# Состояния для FSM
class CRMStates(StatesGroup):
    waiting_for_days = State()  # Ожидание ввода количества дней
    waiting_for_payment_amount = State()  # Ожидание суммы для счета
    waiting_for_key_days = State()  # Ожидание количества дней для нового ключа
    waiting_for_notification_text = State()  # Ожидание текста уведомления


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
    Команда /info - показывает полную информацию о пользователе с кликабельными ключами.
    Работает только в топиках CRM-группы.
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
            info_text += "└ ✅ Использован\n"
        else:
            info_text += "└ ❌ Не использован\n"

        # Отправляем информацию
        await message.reply(info_text, parse_mode="HTML")

        # Если есть ключи, показываем их список с пагинацией
        if stats['keys']:
            page = 0
            page_size = 5
            total_keys = len(stats['keys'])
            keys_on_page = stats['keys'][page * page_size:(page + 1) * page_size]

            total_pages = math.ceil(total_keys / page_size)
            keys_text = "\n🔑 <b>Список ключей:</b>"
            if total_pages > 1:
                keys_text += f"\n📄 Страница {page + 1} из {total_pages}"
            keys_text += "\n\n<i>Нажмите на ключ для подробной информации</i>"

            kb = get_crm_keys_list_kb(keys_on_page, total_keys, page=page, page_size=page_size)
            await message.reply(keys_text, reply_markup=kb, parse_mode="HTML")

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

        subscription_url = await issue_trial_key(bot, user_id, first_name, force=True)

        if subscription_url:
            # Отправляем ключ пользователю в личные сообщения
            try:
                await bot.send_message(
                    user_id,
                    f"🎁 <b>Вам выдан пробный ключ!</b>\n\n"
                    f"⏱ Срок действия: 24 часа\n\n"
                    f"🔑 <b>Ваш ключ:</b>\n"
                    f"<code>{subscription_url}</code>\n\n"
                    f"📱 Нажмите на ключ, чтобы скопировать, и добавьте его в приложение VPN.",
                    parse_mode="HTML"
                )
                log.info(f"CRM: Ключ отправлен пользователю {user_id} в личные сообщения")
            except Exception as send_error:
                log.error(f"CRM: Не удалось отправить ключ пользователю {user_id}: {send_error}")

            # Подтверждение в CRM-топике
            await message.reply(
                f"✅ <b>Пробный ключ выдан!</b>\n\n"
                f"👤 Пользователь: {html.escape(first_name)} (ID: <code>{user_id}</code>)\n"
                f"⏱ Срок действия: 24 часа\n\n"
                f"🔑 Ключ:\n<code>{html.escape(subscription_url)}</code>\n\n"
                f"<i>Ключ отправлен пользователю в личные сообщения.</i>",
                parse_mode="HTML"
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


@router.callback_query(F.data.startswith("crm_keys_page:"))
async def crm_keys_pagination(callback: CallbackQuery):
    """Обработчик пагинации списка ключей в CRM."""
    if not await is_crm_topic(callback.message):
        await callback.answer("Эта функция работает только в CRM-топиках", show_alert=True)
        return

    try:
        page = int(callback.data.split(":")[1])
        page_size = 5

        # Получаем user_id из топика
        from sqlalchemy import select
        from database.db_commands import AsyncSessionLocal
        from database.models import Users

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(Users).where(Users.c.crm_topic_id == callback.message.message_thread_id)
            )
            user = result.fetchone()

        if not user:
            await callback.answer("Пользователь не найден", show_alert=True)
            return

        user_id = user.user_id
        stats = await db.get_user_stats_detailed(user_id)

        if not stats or not stats['keys']:
            await callback.answer("Ключи не найдены", show_alert=True)
            return

        total_keys = len(stats['keys'])
        keys_on_page = stats['keys'][page * page_size:(page + 1) * page_size]

        total_pages = math.ceil(total_keys / page_size)
        keys_text = "\n🔑 <b>Список ключей:</b>"
        if total_pages > 1:
            keys_text += f"\n📄 Страница {page + 1} из {total_pages}"
        keys_text += "\n\n<i>Нажмите на ключ для подробной информации</i>"

        kb = get_crm_keys_list_kb(keys_on_page, total_keys, page=page, page_size=page_size)

        await callback.message.edit_text(keys_text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        log.error(f"Ошибка в пагинации ключей CRM: {e}", exc_info=True)
        await callback.answer("Ошибка при загрузке страницы", show_alert=True)


@router.callback_query(F.data.startswith("crm_key_details:"))
async def crm_key_details(callback: CallbackQuery):
    """Показывает детальную информацию о ключе в CRM."""
    if not await is_crm_topic(callback.message):
        await callback.answer("Эта функция работает только в CRM-топиках", show_alert=True)
        return

    try:
        _, key_id_str, page_str = callback.data.split(":")
        key_id = int(key_id_str)
        current_page = int(page_str)

        # Получаем ключ
        key = await db.get_key_by_id(key_id)

        if not key:
            await callback.answer("Ключ не найден", show_alert=True)
            return

        # Получаем информацию о сервере
        server_ip_to_country = {s.vless_server: s.country for s in settings.XUI_SERVERS}
        country = "Unknown"
        flag = "🏳️"
        try:
            server_ip = key.vless_key.split('@')[1].split(':')[0]
            country = server_ip_to_country.get(server_ip, "Unknown")
            from keyboards import _get_flag_for_country
            flag = _get_flag_for_country(country)
        except Exception:
            pass

        server_info = f"{country} {flag}"

        # Определяем статус
        now = datetime.datetime.now()
        if key.expires_at > now:
            status = "✅ <b>Активен</b>"
            remaining = key.expires_at - now
            days = remaining.days
            hours = remaining.seconds // 3600
            time_left = f"{days} дн. {hours} ч."
        else:
            status = "❌ <b>Истек</b>"
            time_left = "0"

        # Получаем статистику трафика
        traffic_info = "Трафик: н/д"
        try:
            if key.vless_key:
                traffic_data = await vpn_api.get_traffic_by_vless_key(key.vless_key)
                if traffic_data:
                    traffic_formatted = vpn_api.format_traffic(traffic_data['total'])
                    traffic_info = f"Использовано: <b>{traffic_formatted}</b> / ∞"
        except Exception as e:
            log.error(f"Ошибка получения трафика для ключа {key.id}: {e}")

        # Получаем информацию о продукте
        key_type = "Пробный (24ч)"
        if key.order_id:
            order = await db.get_order_by_id(key.order_id)
            if order:
                product = await db.get_product_by_id(order.product_id)
                if product:
                    key_type = f"Платный ({product.name})"

        subscription_url = f"{settings.WEBHOOK_HOST}/sub/{key.subscription_token}"

        text = (
            f"🔑 <b>Детали ключа</b> ({status})\n\n"
            f"🆔 ID ключа: <code>{key.id}</code>\n"
            f"📦 Тип: {key_type}\n"
            f"🌍 Сервер: <b>{server_info}</b>\n"
            f"📅 Создан: <code>{format_datetime(key.created_at)}</code>\n"
            f"⏰ Истекает: <code>{format_datetime(key.expires_at)}</code>\n"
            f"⏳ Осталось: {time_left}\n"
            f"📊 {traffic_info}\n\n"
            "🔗 <b>Ключ подписки:</b>\n"
            f"<code>{subscription_url}</code>"
        )

        kb = get_crm_key_details_kb(key_id, current_page)

        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()

    except Exception as e:
        log.error(f"Ошибка в детальной информации о ключе CRM: {e}", exc_info=True)
        await callback.answer("Ошибка при загрузке информации", show_alert=True)


@router.callback_query(F.data.startswith("crm_add_days:"))
async def crm_add_days_start(callback: CallbackQuery, state: FSMContext):
    """Начинает процесс добавления дней к ключу."""
    if not await is_crm_topic(callback.message):
        await callback.answer("Эта функция работает только в CRM-топиках", show_alert=True)
        return

    try:
        _, key_id_str, page_str = callback.data.split(":")
        key_id = int(key_id_str)
        current_page = int(page_str)

        # Сохраняем данные в состояние
        await state.update_data(key_id=key_id, current_page=current_page, topic_id=callback.message.message_thread_id)
        await state.set_state(CRMStates.waiting_for_days)

        await callback.message.reply(
            "➕ <b>Добавление дней к ключу</b>\n\n"
            f"🆔 ID ключа: <code>{key_id}</code>\n\n"
            "Введите количество дней для добавления (целое число):",
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        log.error(f"Ошибка при начале добавления дней: {e}", exc_info=True)
        await callback.answer("Ошибка", show_alert=True)


@router.message(CRMStates.waiting_for_days)
async def crm_add_days_process(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод количества дней и добавляет их к ключу."""
    if not await is_crm_topic(message):
        return

    try:
        # Получаем количество дней
        days = int(message.text.strip())

        if days <= 0:
            await message.reply("❌ Количество дней должно быть положительным числом.")
            return

        # Получаем данные из состояния
        data = await state.get_data()
        key_id = data['key_id']

        # Получаем ключ
        key = await db.get_key_by_id(key_id)

        if not key:
            await message.reply("❌ Ключ не найден.")
            await state.clear()
            return

        # Вычисляем новую дату истечения
        old_expires_at = key.expires_at
        new_expires_at = old_expires_at + datetime.timedelta(days=days)

        # Обновляем ключ в БД
        await db.update_key_expiry(key_id, new_expires_at)

        # Обновляем ключ на сервере VPN
        try:
            # Извлекаем UUID и сервер из vless ключа
            client_uuid = key.vless_key.split('vless://')[1].split('@')[0]
            server_host = key.vless_key.split('@')[1].split(':')[0]

            # Находим конфигурацию сервера
            server_config = None
            for s in settings.XUI_SERVERS:
                if s.vless_server == server_host:
                    server_config = s
                    break

            if server_config:
                new_expiry_timestamp = int(new_expires_at.timestamp() * 1000)
                success = await vpn_api.update_vless_user_expiry(server_config, client_uuid, new_expiry_timestamp)

                if not success:
                    log.warning(f"CRM: Не удалось обновить срок на сервере для ключа {key_id}")
        except Exception as e:
            log.error(f"CRM: Ошибка обновления срока на сервере: {e}")

        # Удаляем сообщение админа с числом
        try:
            await message.delete()
        except Exception:
            pass

        # Отправляем подтверждение в топик
        await message.answer(
            f"✅ <b>Дни успешно добавлены!</b>\n\n"
            f"🆔 ID ключа: <code>{key_id}</code>\n"
            f"➕ Добавлено дней: <b>{days}</b>\n"
            f"📅 Старая дата истечения: <code>{format_datetime(old_expires_at)}</code>\n"
            f"📅 Новая дата истечения: <code>{format_datetime(new_expires_at)}</code>",
            parse_mode="HTML"
        )

        # Отправляем уведомление пользователю
        try:
            # Получаем user_id из топика
            from sqlalchemy import select
            from database.db_commands import AsyncSessionLocal
            from database.models import Users

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(Users).where(Users.c.crm_topic_id == data['topic_id'])
                )
                user = result.fetchone()

            if user:
                await bot.send_message(
                    user.user_id,
                    f"🎁 <b>Вам добавлены дни!</b>\n\n"
                    f"➕ Добавлено: <b>{days} дней</b>\n"
                    f"📅 Новая дата истечения: <code>{format_datetime(new_expires_at)}</code>\n\n"
                    f"Приятного пользования! 🚀",
                    parse_mode="HTML"
                )
                log.info(f"CRM: Уведомление о добавлении дней отправлено пользователю {user.user_id}")
        except Exception as e:
            log.error(f"CRM: Не удалось отправить уведомление пользователю: {e}")

        # Очищаем состояние
        await state.clear()

        log.info(f"CRM: Добавлено {days} дней к ключу {key_id}")

    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое число.")
    except Exception as e:
        log.error(f"Ошибка при добавлении дней: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")
        await state.clear()


@router.message(Command("payment"))
async def cmd_payment(message: Message, state: FSMContext):
    """
    Команда /payment - создает счет на произвольную сумму для пользователя.
    Работает только в топиках CRM-группы.
    """
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
            await message.reply("❌ Пользователь не найден.")
            return

        # Сохраняем данные в состояние
        await state.update_data(user_id=user.user_id, topic_id=message.message_thread_id)
        await state.set_state(CRMStates.waiting_for_payment_amount)

        await message.reply(
            "💰 <b>Создание счета</b>\n\n"
            f"👤 Пользователь: {html.escape(user.first_name)} (ID: <code>{user.user_id}</code>)\n\n"
            "Введите сумму счета в рублях (целое число):",
            parse_mode="HTML"
        )

        log.info(f"CRM: Начато создание счета для пользователя {user.user_id}")

    except Exception as e:
        log.error(f"Ошибка в команде /payment: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")


@router.message(CRMStates.waiting_for_payment_amount)
async def crm_payment_process(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод суммы и создает счет."""
    if not await is_crm_topic(message):
        return

    try:
        # Получаем сумму
        amount = int(message.text.strip())

        if amount <= 0:
            await message.reply("❌ Сумма должна быть положительным числом.")
            return

        # Получаем данные из состояния
        data = await state.get_data()
        user_id = data['user_id']

        # Создаем заказ с product_id = None (кастомный платеж)
        order_id = await db.create_order(user_id, product_id=None, amount=amount)

        if not order_id:
            await message.reply("❌ Не удалось создать заказ.")
            await state.clear()
            return

        # Удаляем сообщение админа с суммой
        try:
            await message.delete()
        except Exception:
            pass

        # Отправляем подтверждение в топик
        await message.answer(
            f"✅ <b>Счет создан!</b>\n\n"
            f"🆔 ID заказа: <code>{order_id}</code>\n"
            f"💰 Сумма: <b>{amount} ₽</b>\n"
            f"👤 Пользователь: <code>{user_id}</code>\n\n"
            "Счет отправлен пользователю в личные сообщения.",
            parse_mode="HTML"
        )

        # Отправляем счет пользователю
        try:
            from keyboards import get_payment_method_kb

            # Отправляем выбор способа оплаты
            await bot.send_message(
                user_id,
                f"💰 <b>Счет на оплату</b>\n\n"
                f"Сумма: <b>{amount} ₽</b>\n\n"
                "Выберите способ оплаты:",
                reply_markup=get_payment_method_kb(order_id, back_callback_data="menu:main"),
                parse_mode="HTML"
            )

            log.info(f"CRM: Счет на {amount} ₽ отправлен пользователю {user_id}")
        except Exception as e:
            log.error(f"CRM: Не удалось отправить счет пользователю: {e}")
            await message.answer(f"⚠️ Ошибка при отправке счета: {str(e)}")

        # Очищаем состояние
        await state.clear()

    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое число.")
    except Exception as e:
        log.error(f"Ошибка при создании счета: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")
        await state.clear()


@router.message(Command("key"))
async def cmd_key(message: Message, state: FSMContext):
    """
    Команда /key - выдает ключ пользователю с произвольными параметрами.
    Работает только в топиках CRM-группы.
    """
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
            await message.reply("❌ Пользователь не найден.")
            return

        # Сохраняем данные в состояние
        await state.update_data(user_id=user.user_id, topic_id=message.message_thread_id)

        # Показываем выбор страны
        await message.reply(
            "🔑 <b>Выдача ключа</b>\n\n"
            f"👤 Пользователь: {html.escape(user.first_name)} (ID: <code>{user.user_id}</code>)\n\n"
            "Выберите страну:",
            reply_markup=get_crm_country_selection_kb(),
            parse_mode="HTML"
        )

        log.info(f"CRM: Начата выдача ключа для пользователя {user.user_id}")

    except Exception as e:
        log.error(f"Ошибка в команде /key: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")


@router.callback_query(F.data.startswith("crm_key_country:"))
async def crm_key_country_selected(callback: CallbackQuery, state: FSMContext):
    """Обрабатывает выбор страны для выдачи ключа."""
    if not await is_crm_topic(callback.message):
        await callback.answer("Эта функция работает только в CRM-топиках", show_alert=True)
        return

    try:
        country = callback.data.split(":", 1)[1]

        # Сохраняем страну в состояние
        await state.update_data(country=country)
        await state.set_state(CRMStates.waiting_for_key_days)

        from keyboards import _get_flag_for_country
        flag = _get_flag_for_country(country)

        await callback.message.edit_text(
            f"🔑 <b>Выдача ключа</b>\n\n"
            f"🌍 Страна: {flag} {country}\n\n"
            "Введите количество дней (целое число):",
            parse_mode="HTML"
        )
        await callback.answer()

    except Exception as e:
        log.error(f"Ошибка при выборе страны для ключа: {e}", exc_info=True)
        await callback.answer("Ошибка", show_alert=True)


@router.message(CRMStates.waiting_for_key_days)
async def crm_key_days_process(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод количества дней и выдает ключ."""
    if not await is_crm_topic(message):
        return

    try:
        # Получаем количество дней
        days = int(message.text.strip())

        if days <= 0:
            await message.reply("❌ Количество дней должно быть положительным числом.")
            return

        # Получаем данные из состояния
        data = await state.get_data()
        user_id = data['user_id']
        country = data['country']

        # Удаляем сообщение админа с числом
        try:
            await message.delete()
        except Exception:
            pass

        # Генерируем ключ
        from utils import generate_vless_key, get_least_loaded_server
        import uuid

        # Получаем сервер для выбранной страны
        server_config = await get_least_loaded_server(country=country)
        if not server_config:
            await message.answer(f"❌ Не найдены доступные серверы для страны: {country}")
            await state.clear()
            return

        new_uuid = str(uuid.uuid4())
        expires_at = datetime.datetime.now() + datetime.timedelta(days=days)

        # Добавляем пользователя на сервер VPN
        api_success = await vpn_api.add_vless_user(
            server_config=server_config,
            user_id=user_id,
            days=days,
            new_uuid=new_uuid
        )

        if not api_success:
            await message.answer("❌ Не удалось создать ключ на сервере VPN.")
            await state.clear()
            return

        # Генерируем VLESS строку
        vless_string = generate_vless_key(
            user_uuid=new_uuid,
            product_name="CRM_Admin",
            user_id=user_id,
            server_config=server_config
        )

        # Сохраняем ключ в БД
        subscription_token = await db.add_vless_key(
            user_id=user_id,
            order_id=None,  # Бесплатный ключ от админа
            vless_key=vless_string,
            expires_at=expires_at
        )

        subscription_url = f"{settings.WEBHOOK_HOST}/sub/{subscription_token}"

        from keyboards import _get_flag_for_country
        flag = _get_flag_for_country(country)

        # Отправляем подтверждение в топик
        await message.answer(
            f"✅ <b>Ключ успешно выдан!</b>\n\n"
            f"👤 Пользователь: <code>{user_id}</code>\n"
            f"🌍 Страна: {flag} {country}\n"
            f"⏳ Срок: <b>{days} дней</b>\n"
            f"📅 Истекает: <code>{format_datetime(expires_at)}</code>\n\n"
            f"🔗 Ключ подписки:\n<code>{subscription_url}</code>",
            parse_mode="HTML"
        )

        # Отправляем ключ пользователю
        try:
            await bot.send_message(
                user_id,
                f"🎁 <b>Вам выдан VPN-ключ!</b>\n\n"
                f"🌍 Сервер: {flag} <b>{country}</b>\n"
                f"⏳ Срок действия: <b>{days} дней</b>\n"
                f"📅 Истекает: <code>{format_datetime(expires_at)}</code>\n\n"
                "🔑 <b>Ваш ключ подписки:</b>\n"
                f"<code>{subscription_url}</code>\n\n"
                "Нажмите на ключ 👆👆👆, чтобы скопировать\n\n"
                "Приятного пользования! 🚀",
                parse_mode="HTML"
            )
            log.info(f"CRM: Ключ на {days} дней ({country}) выдан пользователю {user_id}")
        except Exception as e:
            log.error(f"CRM: Не удалось отправить ключ пользователю: {e}")
            await message.answer(f"⚠️ Ключ создан, но не удалось отправить пользователю: {str(e)}")

        # Очищаем состояние
        await state.clear()

    except ValueError:
        await message.reply("❌ Пожалуйста, введите целое число.")
    except Exception as e:
        log.error(f"Ошибка при выдаче ключа: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")
        await state.clear()


@router.message(Command("notification"))
async def cmd_notification(message: Message, state: FSMContext):
    """
    Команда /notification - отправляет произвольное сообщение пользователю.
    Работает только в топиках CRM-группы.
    """
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
            await message.reply("❌ Пользователь не найден.")
            return

        # Сохраняем данные в состояние
        await state.update_data(user_id=user.user_id, topic_id=message.message_thread_id)
        await state.set_state(CRMStates.waiting_for_notification_text)

        await message.reply(
            "📨 <b>Отправка уведомления</b>\n\n"
            f"👤 Пользователь: {html.escape(user.first_name)} (ID: <code>{user.user_id}</code>)\n\n"
            "Введите текст сообщения, которое будет отправлено пользователю:",
            parse_mode="HTML"
        )

        log.info(f"CRM: Начата отправка уведомления пользователю {user.user_id}")

    except Exception as e:
        log.error(f"Ошибка в команде /notification: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")


@router.message(CRMStates.waiting_for_notification_text)
async def crm_notification_process(message: Message, state: FSMContext, bot: Bot):
    """Обрабатывает ввод текста и отправляет уведомление пользователю."""
    if not await is_crm_topic(message):
        return

    try:
        # Получаем текст сообщения
        notification_text = message.text.strip()

        if not notification_text:
            await message.reply("❌ Текст сообщения не может быть пустым.")
            return

        # Получаем данные из состояния
        data = await state.get_data()
        user_id = data['user_id']

        # Удаляем сообщение админа с текстом
        try:
            await message.delete()
        except Exception:
            pass

        # Отправляем уведомление пользователю
        try:
            await bot.send_message(
                user_id,
                notification_text,
                parse_mode="HTML"
            )

            # Отправляем подтверждение в топик
            await message.answer(
                f"✅ <b>Уведомление отправлено!</b>\n\n"
                f"👤 Пользователь: <code>{user_id}</code>\n\n"
                f"📨 Текст сообщения:\n{html.escape(notification_text)}",
                parse_mode="HTML"
            )

            log.info(f"CRM: Уведомление отправлено пользователю {user_id}")
        except Exception as e:
            log.error(f"CRM: Не удалось отправить уведомление пользователю: {e}")
            await message.answer(f"❌ Не удалось отправить уведомление: {str(e)}")

        # Очищаем состояние
        await state.clear()

    except Exception as e:
        log.error(f"Ошибка при отправке уведомления: {e}", exc_info=True)
        await message.reply(f"❌ Произошла ошибка: {str(e)}")
        await state.clear()

