import asyncio
import logging
import datetime
import math  # ⬅️ Новый импорт
from collections import defaultdict

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import AiogramError  # ⬅️ Новый импорт

from config import settings
from database import db_commands as db
# ⬇️ Обновленные импорты клавиатур
from keyboards import get_admin_menu_kb, get_back_to_admin_kb, get_admin_stats_kb


# Кастомный фильтр для проверки ID админа
class IsAdmin(Filter):
    async def __call__(self, update: Message | CallbackQuery) -> bool:
        user_id = update.from_user.id
        return user_id in settings.get_admin_ids


router = Router()
router.message.filter(IsAdmin())
router.callback_query.filter(IsAdmin())


# --- FSM для рассылки ---
class BroadcastState(StatesGroup):
    waiting_for_message = State()


async def build_and_send_stats_page(update_obj: Message | CallbackQuery, page: int = 0):
    """
    Единая функция для генерации и отправки страницы статистики.
    (Версия с флагами стран)
    """
    try:
        active_keys = await db.get_all_active_keys_details()
    except Exception as e:
        logging.error(f"Ошибка получения статистики из БД: {e}")
        error_text = f"❌ Ошибка при получении данных из БД: {e}"
        if isinstance(update_obj, Message):
            await update_obj.answer(error_text, reply_markup=get_back_to_admin_kb())
        else:
            await update_obj.answer("Ошибка БД", show_alert=True)
        return

    if not active_keys:
        no_keys_text = "Активных ключей не найдено."
        if isinstance(update_obj, Message):
            await update_obj.answer(no_keys_text, reply_markup=get_back_to_admin_kb())
        else:
            await update_obj.message.edit_text(no_keys_text, reply_markup=get_back_to_admin_kb())
            await update_obj.answer()
        return

    # --- 1. Считаем общую статистику (для хедера) ---
    total_active = len(active_keys)
    server_stats = defaultdict(int)
    for key in active_keys:
        try:
            server_address = key.vless_key.split('@')[1].split(':')[0]
        except Exception:
            server_address = "Unknown"
        server_stats[server_address] += 1


    server_to_country = {s.vless_server: s.country for s in settings.XUI_SERVERS}

    def _get_flag_for_country(country_name: str) -> str:
        """Вспомогательная функция для получения флага (как в keyboards.py)"""
        if country_name == "Финляндия": return "🇫🇮"
        if country_name == "Германия": return "🇩🇪"
        if country_name == "Нидерланды": return "🇳🇱"
        return "🏳️"  # Флаг по умолчанию

    summary = f"📊 **Общая статистика**\n\n"
    summary += f"Всего активных ключей: **{total_active}**\n"
    summary += "Распределение по серверам (IP/домен):\n"

    sorted_servers = sorted(server_stats.items(), key=lambda item: item[1], reverse=True)

    for server_ip, count in sorted_servers:
        # Получаем страну по IP
        country = server_to_country.get(server_ip, "Unknown")
        # Получаем флаг по стране
        flag = _get_flag_for_country(country)
        # Добавляем флаг в строку
        summary += f"  - {flag} `{server_ip}`: **{count}** шт.\n"


    # --- 2. Готовим пагинацию (по 5 шт) ---
    page_size = 5
    total_pages = math.ceil(total_active / page_size)
    page = max(0, min(page, total_pages - 1))

    start_index = page * page_size
    end_index = start_index + page_size
    keys_on_page = active_keys[start_index:end_index]

    # --- 3. Собираем детальный отчет ДЛЯ ЭТОЙ СТРАНИЦЫ ---
    detailed_report = "📈 **Детальный отчет по активным ключам:**\n\n"
    if not keys_on_page and total_active > 0:
        detailed_report += "На этой странице ключей нет."

    for key in keys_on_page:
        server_address = "Unknown"
        flag = "🏳️"
        try:
            server_address = key.vless_key.split('@')[1].split(':')[0]
            country = server_to_country.get(server_address, "Unknown")
            flag = _get_flag_for_country(country)
        except Exception:
            pass

        user_info = f"{key.first_name} (ID: {key.user_id})"
        product_info = "Пробный (1 день)"
        if key.product_name:
            product_info = f"{key.product_name} ({key.duration_days} дн.)"

        expires_str = key.expires_at.strftime('%Y-%m-%d %H:%M')

        detailed_report += (
            f"👤 **{user_info}**\n"
            f"  - 🖥️ Сервер: {flag} `{server_address}`\n"
            f"  - 📦 Тариф: {product_info}\n"
            f"  - ⏰ Истекает: {expires_str}\n\n"
        )

    # --- 4. Собираем финальный текст и клавиатуру ---
    page_indicator = ""
    if total_pages > 1:
        page_indicator = f"\n\n📄 Страница {page + 1} / {total_pages}"

    final_text = summary + detailed_report + page_indicator

    kb = get_admin_stats_kb(page, total_pages)

    # --- 5. Отправляем или редактируем ---
    try:
        if isinstance(update_obj, Message):
            await update_obj.answer(final_text, reply_markup=kb, parse_mode="Markdown")
        else:
            await update_obj.message.edit_text(final_text, reply_markup=kb, parse_mode="Markdown")
            await update_obj.answer()

    except AiogramError as e:
        if "message is not modified" in str(e).lower():
            await update_obj.answer("Вы уже на этой странице.")
        else:
            logging.error(f"Error sending stats page: {e}")
            await update_obj.answer("Ошибка при обновлении страницы.", show_alert=True)
    except Exception as e:
        logging.error(f"Unexpected error sending stats page: {e}")
        if isinstance(update_obj, Message):
            await update_obj.answer("Неожиданная ошибка.")
        else:
            await update_obj.answer("Неожиданная ошибка.", show_alert=True)



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
    """Показывает статистику (команда) - СТРАНИЦА 1"""
    await message.answer("⏳ Собираю статистику... Пожалуйста, подождите.")
    await build_and_send_stats_page(message, page=0)


@router.message(Command("broadcast"))
async def start_broadcast(message: Message, state: FSMContext):
    """Начало рассылки (команда, дублирует кнопку)"""
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer(
        "Введите сообщение для рассылки всем пользователям:",
        reply_markup=get_back_to_admin_kb()
    )


@router.message(BroadcastState.waiting_for_message)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    """Выполняет рассылку"""
    await state.clear()
    user_ids = await db.get_all_user_ids()
    await message.answer(f"Начинаю рассылку... Всего пользователей: {len(user_ids)}")

    success_count = 0
    fail_count = 0

    for user_id in user_ids:
        try:
            await message.copy_to(user_id)
            success_count += 1
            await asyncio.sleep(0.1)
        except Exception as e:
            fail_count += 1
            logging.warning(f"Failed to send broadcast to {user_id}: {e}")

    await message.answer(
        f"✅ Рассылка завершена.\n\n"
        f"Успешно: {success_count}\n"
        f"Заблокировано/Ошибка: {fail_count}",
        reply_markup=get_back_to_admin_kb()
    )


# --- ОБРАБОТЧИКИ КНОПОК АДМИН-ПАНЕЛИ ---

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
    """Кнопка 'Статистика' - СТРАНИЦА 1"""
    await callback.answer("⏳ Собираю статистику...")
    await build_and_send_stats_page(callback, page=0)


# ⬇️ ⬇️ ⬇️ НОВЫЙ ОБРАБОТЧИК ДЛЯ ПАГИНАЦИИ ⬇️ ⬇️ ⬇️
@router.callback_query(F.data.startswith("admin:stats_page:"))
async def paginate_admin_stats(callback: CallbackQuery):
    """Пагинация для статистики"""
    try:
        # data = "admin:stats_page:1" -> split(":")[-1] = "1"
        page = int(callback.data.split(":")[-1])
    except (ValueError, IndexError):
        await callback.answer("Ошибка страницы.", show_alert=True)
        return

    await build_and_send_stats_page(callback, page=page)


@router.callback_query(F.data == "admin:broadcast")
async def menu_admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Кнопка 'Рассылка'"""
    await state.set_state(BroadcastState.waiting_for_message)
    try:
        await callback.message.edit_text(
            "Введите сообщение для рассылки всем пользователям:",
            reply_markup=get_back_to_admin_kb()
        )
        await callback.answer()
    except Exception as e:
        logging.warning(f"Error editing message for broadcast: {e}")
        await callback.answer()
        await start_broadcast(callback.message, state)  # Fallback