import asyncio
import logging
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.filters import Command, Filter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import settings
from database import db_commands as db


# Кастомный фильтр для проверки ID админа
class IsAdmin(Filter):
    async def __call__(self, message: Message) -> bool:
        return message.from_user.id in settings.get_admin_ids


router = Router()
router.message.filter(IsAdmin())


# --- FSM для рассылки ---
class BroadcastState(StatesGroup):
    waiting_for_message = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    """Главное меню админа"""
    # TODO: Сделать админскую клавиатуру
    await message.answer("Добро пожаловать в админ-панель.\n"
                         "/broadcast - Начать рассылку\n"
                         "/stats - Показать статистику (TODO)")


@router.message(Command("broadcast"))
async def start_broadcast(message: Message, state: FSMContext):
    """Начало рассылки"""
    await state.set_state(BroadcastState.waiting_for_message)
    await message.answer("Введите сообщение для рассылки всем пользователям:")


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
        f"Заблокировано/Ошибка: {fail_count}"
    )