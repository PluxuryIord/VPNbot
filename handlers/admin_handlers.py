import asyncio
import html
import logging
import datetime
import math
from collections import defaultdict

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import AiogramError

from config import settings
from database import db_commands as db
from keyboards import (get_admin_menu_kb, get_back_to_admin_kb, get_admin_stats_kb,
                       get_broadcast_confirmation_kb, get_users_list_kb, get_user_card_kb)
import vpn_api


# Кастомный фильтр для проверки ID админа
class IsAdmin(Filter):
    async def __call__(self, update: Message | CallbackQuery) -> bool:
        user_id = update.from_user.id
        return user_id in settings.get_admin_ids


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


class BroadcastState(StatesGroup):
    waiting_for_message = State()
    waiting_for_confirmation = State()



async def build_and_send_users_list(update_obj: Message | CallbackQuery, page: int = 0):
    """
    Единая функция для генерации и отправки списка пользователей с пагинацией.
    """
    page_size = 10

    try:
        total_users = await db.count_all_users()
        users_on_page = await db.get_all_users_paginated(page=page, page_size=page_size)
    except Exception as e:
        logging.error(f"Ошибка получения списка пользователей из БД: {e}")
        error_text = f"❌ Ошибка при получении данных из БД: {e}"
        if isinstance(update_obj, Message):
            await update_obj.answer(error_text, reply_markup=get_back_to_admin_kb())
        else:
            await update_obj.answer("Ошибка БД", show_alert=True)
        return

    if total_users == 0:
        no_users_text = "Пользователей не найдено."
        if isinstance(update_obj, Message):
            await update_obj.answer(no_users_text, reply_markup=get_back_to_admin_kb())
        else:
            await update_obj.message.edit_text(no_users_text, reply_markup=get_back_to_admin_kb())
            await update_obj.answer()
        return

    total_pages = math.ceil(total_users / page_size)
    page = max(0, min(page, total_pages - 1))

    # Формируем текст сообщения
    text = f"📊 <b>Статистика пользователей</b> (Стр. {page + 1}/{total_pages})\n\n"
    text += f"Всего пользователей: <b>{total_users}</b>\n\n"
    text += "Нажмите на пользователя для просмотра деталей:"

    kb = get_users_list_kb(users_on_page, total_users, page=page, page_size=page_size)

    try:
        if isinstance(update_obj, Message):
            await update_obj.answer(text, reply_markup=kb, parse_mode="HTML")
        else:
            await update_obj.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            await update_obj.answer()

    except AiogramError as e:
        if "message is not modified" in str(e).lower():
            await update_obj.answer("Вы уже на этой странице.")
        else:
            logging.error(f"Error sending users list: {e}")
            await update_obj.answer("Ошибка при обновлении страницы.", show_alert=True)
    except Exception as e:
        logging.error(f"Unexpected error sending users list: {e}")
        if isinstance(update_obj, Message):
            await update_obj.answer("Неожиданная ошибка.")
        else:
            await update_obj.answer("Неожиданная ошибка.", show_alert=True)


async def build_and_send_user_card(callback: CallbackQuery, user_id: int, page: int):
    """
    Формирует и отправляет детальную карточку пользователя.
    """
    try:
        user_stats = await db.get_user_stats_detailed(user_id)
    except Exception as e:
        logging.error(f"Ошибка получения статистики пользователя {user_id}: {e}")
        await callback.answer("Ошибка при получении данных пользователя.", show_alert=True)
        return

    if not user_stats:
        await callback.answer("Пользователь не найден.", show_alert=True)
        return

    user = user_stats['user']

    # Формируем заголовок карточки
    username_display = f"@{user.username}" if user.username else user.first_name
    if not user.username and not user.first_name:
        username_display = f"User {user.user_id}"

    text = f"👤 <b>Пользователь: {html.escape(username_display)}</b>\n"
    text += f"ID: <code>{user.user_id}</code>\n"
    if user.first_name:
        text += f"Имя: {html.escape(user.first_name)}\n"
    text += f"Регистрация: {user.created_at.strftime('%Y-%m-%d %H:%M')}\n\n"

    # Финансовая статистика
    text += f"💰 <b>Финансы:</b>\n"
    text += f"Всего потрачено: <b>{user_stats['total_spent']:.2f} ₽</b>\n"
    text += f"Всего заказов: <b>{user_stats['total_orders']}</b>\n\n"

    # Статистика по ключам
    text += f"🔑 <b>Ключи</b> (Активные: {user_stats['active_keys_count']}, Всего: {user_stats['total_keys_count']}):\n\n"

    if user_stats['keys']:
        now = datetime.datetime.now()
        server_to_country = {s.vless_server: s.country for s in settings.XUI_SERVERS}

        def _get_flag_for_country(country_name: str) -> str:
            if country_name == "Финляндия": return "🇫🇮"
            if country_name == "Германия": return "🇩🇪"
            if country_name == "Нидерланды": return "🇳🇱"
            return "🏳️"

        for idx, key in enumerate(user_stats['keys'], 1):
            # Определяем статус ключа
            is_active = key.expires_at > now
            status_icon = "✅" if is_active else "❌"
            status_text = "Активен" if is_active else "Истек"

            # Определяем сервер и страну
            server_address = "Unknown"
            country = "Unknown"
            flag = "🏳️"
            try:
                server_address = key.vless_key.split('@')[1].split(':')[0]
                country = server_to_country.get(server_address, "Unknown")
                flag = _get_flag_for_country(country)
            except Exception:
                pass

            # Определяем тариф
            if key.product_name:
                tariff = f"{key.product_name}"
            else:
                tariff = "Пробный (1 день)"

            # Формируем информацию о сроке действия
            expires_str = key.expires_at.strftime('%Y-%m-%d')
            if is_active:
                remaining = key.expires_at - now
                days_left = remaining.days
                if days_left > 0:
                    time_info = f"через {days_left} д."
                else:
                    hours_left = remaining.seconds // 3600
                    time_info = f"через {hours_left} ч." if hours_left > 0 else "меньше часа"
            else:
                time_info = f"истек {expires_str}"

            # Получаем статистику трафика
            traffic_info = "Трафик: н/д"
            try:
                if key.vless_key:
                    traffic_data = await vpn_api.get_traffic_by_vless_key(key.vless_key)
                    if traffic_data:
                        traffic_formatted = vpn_api.format_traffic(traffic_data['total'])
                        traffic_info = f"Трафик: {traffic_formatted} / ∞"
            except Exception as e:
                logging.error(f"Error getting traffic for key {key.id}: {e}")

            text += f"{status_icon} <b>Ключ #{idx}</b> ({status_text})\n"
            text += f"  Сервер: {flag} {country}\n"
            text += f"  Тариф: {tariff}\n"
            text += f"  Истекает: {expires_str} ({time_info})\n"
            text += f"  {traffic_info}\n"
            text += "\n"
    else:
        text += "У пользователя нет ключей.\n"

    kb = get_user_card_kb(page)

    try:
        await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await callback.answer()
    except AiogramError as e:
        if "message is not modified" not in str(e).lower():
            logging.error(f"Error sending user card: {e}")
            await callback.answer("Ошибка при отображении карточки.", show_alert=True)



@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Главное меню админа (команда)"""
    await message.answer(
        "Добро пожаловать в админ-панель.\n\n"
        "Выберите действие:",
        reply_markup=get_admin_menu_kb()
    )


@router.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показывает статистику пользователей (команда) - СТРАНИЦА 1"""
    await message.answer("⏳ Собираю статистику... Пожалуйста, подождите.")
    await build_and_send_users_list(message, page=0)


@router.message(Command("broadcast"))
async def start_broadcast(message: Message, state: FSMContext):
    """Начало рассылки (команда, дублирует кнопку)"""
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer(
        "Введите сообщение для рассылки всем пользователям:",
        reply_markup=get_back_to_admin_kb()
    )


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast_get_message(message: Message, state: FSMContext):
    """
    Шаг 1: Получает сообщение от админа и просит подтверждения.
    """

    await state.update_data(message_to_send_id=message.message_id, chat_id=message.chat.id)
    await state.set_state(BroadcastState.waiting_for_confirmation)

    await message.answer(
        "Вы уверены, что хотите отправить **это** сообщение всем пользователям?",
        reply_markup=get_broadcast_confirmation_kb(),  #
        parse_mode="Markdown"
    )


#
@router.callback_query(BroadcastState.waiting_for_confirmation, F.data.startswith("broadcast:"))
async def process_broadcast_confirmation(callback: CallbackQuery, state: FSMContext, bot: Bot):
    """
    Шаг 2: Обрабатывает нажатие 'Да' или 'Отмена'.
    """
    action = callback.data.split(":")[-1]

    if action == "cancel":
        await state.clear()
        await callback.message.edit_text("❌ Рассылка отменена.", reply_markup=None)
        await callback.answer()
        await cmd_admin(callback.message)
        return

    await callback.message.edit_text("⏳ Начинаю рассылку... Это может занять время.", reply_markup=None)
    await callback.answer()

    data = await state.get_data()
    message_to_send_id = data.get("message_to_send_id")
    chat_id = data.get("chat_id")

    await state.clear()

    if not message_to_send_id or not chat_id:
        await callback.message.answer(
            "❌ Ошибка! Не удалось найти сообщение для рассылки. Попробуйте снова.",
            reply_markup=get_back_to_admin_kb()
        )
        return

    user_ids = await db.get_all_user_ids()
    success_count = 0
    fail_count = 0

    for user_id in user_ids:
        try:
            #
            await bot.copy_message(
                chat_id=user_id,
                from_chat_id=chat_id,
                message_id=message_to_send_id
            )
            success_count += 1
            await asyncio.sleep(0.1)  #
        except Exception as e:
            fail_count += 1
            logging.warning(f"Failed to send broadcast to {user_id}: {e}")

    await callback.message.answer(
        f"✅ Рассылка завершена.\n\n"
        f"Успешно: {success_count}\n"
        f"Заблокировано/Ошибка: {fail_count}",
        reply_markup=get_back_to_admin_kb()
    )



@router.callback_query(F.data == "admin:main")
async def menu_admin_main(callback: CallbackQuery):
    """Главное меню админа (кнопка 'Назад')"""
    try:
        await callback.message.edit_text(
            "Добро пожаловать в админ-панель.\n\n"
            "Выберите действие:",
            reply_markup=get_admin_menu_kb()
        )
    except Exception as e:
        logging.info(f"Admin menu 'admin:main' error: {e}")
        await callback.message.delete()
        await cmd_admin(callback.message)
    await callback.answer()


@router.callback_query(F.data == "admin:stats")
async def menu_admin_stats(callback: CallbackQuery):
    """Кнопка 'Статистика' - показывает список пользователей"""
    await callback.answer("⏳ Собираю статистику...")
    await build_and_send_users_list(callback, page=0)


@router.callback_query(F.data.startswith("admin:users_page:"))
async def paginate_users_list(callback: CallbackQuery):
    """Пагинация для списка пользователей"""
    try:
        page = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка страницы.", show_alert=True)
        return

    await build_and_send_users_list(callback, page=page)


@router.callback_query(F.data.startswith("admin:user_card:"))
async def show_user_card(callback: CallbackQuery):
    """Показывает детальную карточку пользователя"""
    try:
        parts = callback.data.split(":")
        user_id = int(parts[2])
        page = int(parts[3])
    except (ValueError, IndexError):
        await callback.answer("Ошибка получения данных пользователя.", show_alert=True)
        return

    await build_and_send_user_card(callback, user_id, page)


@router.callback_query(F.data == "admin:broadcast")
async def menu_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Кнопка 'Рассылка'"""
    await state.set_state(BroadcastState.waiting_for_message)  #
    try:
        await callback.message.edit_text(
            "Введите сообщение для рассылки всем пользователям:",
            reply_markup=get_back_to_admin_kb()
        )
        await callback.answer()
    except Exception as e:
        logging.warning(f"Error editing message for broadcast: {e}")
        await callback.answer()
        await start_broadcast(callback.message, state)