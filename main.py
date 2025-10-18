# main.py
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from sqlalchemy.dialects.sqlite import insert

from config import settings
from database import db_commands as db
from handlers import user_handlers, admin_handlers, webhook_handlers


async def main():
    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    # === НАЧАЛО ИЗМЕНЕНИЙ ===

    # 1. Инициализируем БД здесь, а не в on_startup
    await db.init_db()
    # [ВАЖНО] Добавляем тестовые данные (удалить в продакшене)
    async with db.AsyncSessionLocal() as session:
        async with session.begin():
            # Добавляем админа
            # ИЗМЕНЕНИЕ: убираем 'db.'
            await session.execute(
                insert(db.Admins).values(user_id=settings.get_admin_ids[0], is_super_admin=True)
                .on_conflict_do_nothing()
            )
            # Добавляем продукты
            # ИЗМЕНЕНИЕ: убираем 'db.'
            await session.execute(
                insert(db.Products).values([
                    {'name': '30 дней', 'price': 100.0, 'duration_days': 30},
                    {'name': '90 дней', 'price': 250.0, 'duration_days': 90},
                    {'name': '180 дней', 'price': 450.0, 'duration_days': 180},
                ]).on_conflict_do_nothing()
            )
            await session.commit()
    print("База данных инициализирована.")

    # 2. Удаляем ВЕСЬ код, связанный с aiohttp, web.Application, runner, site

    # 3. Удаляем вебхук (на всякий случай, если он был установлен)
    await bot.delete_webhook(drop_pending_updates=True)

    # 4. Запускаем polling
    print("Бот запущен (polling)!")
    await dp.start_polling(bot)

    # === КОНЕЦ ИЗМЕНЕНИЙ ===


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")