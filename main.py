# main.py
import asyncio
import logging
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from sqlalchemy.dialects.postgresql import insert

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

    # 1. Инициализируем БД
    await db.init_db()

    async with db.AsyncSessionLocal() as session:
        async with session.begin():
            admin_insert_stmt = insert(db.Admins).values(
                user_id=settings.get_admin_ids[0],
                is_super_admin=True
            )
            # Указываем PostgreSQL игнорировать конфликт по 'user_id'
            admin_do_nothing_stmt = admin_insert_stmt.on_conflict_do_nothing(
                index_elements=['user_id']
            )
            await session.execute(admin_do_nothing_stmt)

            all_tariffs = [
                # Финляндия
                {'name': '30 дней', 'price': 199.0, 'duration_days': 30, 'country': 'Финляндия'},
                {'name': '60 дней', 'price': 369.0, 'duration_days': 60, 'country': 'Финляндия'},
                {'name': '90 дней', 'price': 529.0, 'duration_days': 90, 'country': 'Финляндия'},
                # Остальные страны (Германия)
                {'name': '30 дней', 'price': 149.0, 'duration_days': 30, 'country': 'Германия'},
                {'name': '60 дней', 'price': 269.0, 'duration_days': 60, 'country': 'Германия'},
                {'name': '90 дней', 'price': 379.0, 'duration_days': 90, 'country': 'Германия'},
                # Остальные страны (Нидерланды)
                {'name': '30 дней', 'price': 149.0, 'duration_days': 30, 'country': 'Нидерланды'},
                {'name': '60 дней', 'price': 269.0, 'duration_days': 60, 'country': 'Нидерланды'},
                {'name': '90 дней', 'price': 379.0, 'duration_days': 90, 'country': 'Нидерланды'},
            ]

            # Очистим старые тарифы перед добавлением новых (на всякий случай)
            await session.execute(db.Products.delete())

            # Добавляем новые тарифы
            await session.execute(
                insert(db.Products),
                all_tariffs
            )

            await session.commit()
    print("База данных инициализирована, админ и тарифы добавлены.")

    await bot.delete_webhook(drop_pending_updates=True)

    print("Бот запущен (polling)!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Бот остановлен.")
