import asyncio
import logging
import scheduler_tasks
from pathlib import Path
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from sqlalchemy.dialects.postgresql import insert

from config import settings
from database import db_commands as db
from handlers import user_handlers, admin_handlers, webhook_handlers, crm_handlers, webapp_handlers
from middlewares.crm_filter import CRMFilterMiddleware

TELEGRAM_WEBHOOK_PATH = "/webhook/telegram"
YOOKASSA_WEBHOOK_PATH = settings.WEBHOOK_PATH
APP_HOST = "127.0.0.1"
APP_PORT = 8080

log = logging.getLogger(__name__)


async def on_startup(bot: Bot):
    """Действия при старте: установка вебхука Telegram."""
    webhook_url = f"{settings.WEBHOOK_HOST}{TELEGRAM_WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    log.info(f"Telegram webhook set up at {webhook_url}")

    # Инициализация БД и добавление данных
    await db.init_db()
    async with db.AsyncSessionLocal() as session:
        async with session.begin():
            # Добавляем админа
            admin_insert_stmt = insert(db.Admins).values(
                user_id=settings.get_admin_ids[0],
                is_super_admin=True)
            admin_do_nothing_stmt = admin_insert_stmt.on_conflict_do_nothing(
                index_elements=['user_id']
            )
            await session.execute(admin_do_nothing_stmt)
            # Добавляем тарифы
            check_products = await session.execute(db.select(db.func.count()).select_from(db.Products))
            products_count = check_products.scalar_one_or_none()

            # Если тарифов нет (count = 0), то добавляем их
            if products_count == 0:
                log.info("Таблица Products пуста, добавляю начальные тарифы...")
                all_tariffs = [
                    {'name': '30 дней', 'price': 199.0, 'duration_days': 30, 'country': 'Финляндия'},
                    {'name': '60 дней', 'price': 369.0, 'duration_days': 60, 'country': 'Финляндия'},
                    {'name': '90 дней', 'price': 529.0, 'duration_days': 90, 'country': 'Финляндия'},
                    {'name': '30 дней', 'price': 149.0, 'duration_days': 30, 'country': 'Германия'},
                    {'name': '60 дней', 'price': 269.0, 'duration_days': 60, 'country': 'Германия'},
                    {'name': '90 дней', 'price': 379.0, 'duration_days': 90, 'country': 'Германия'},
                    {'name': '30 дней', 'price': 149.0, 'duration_days': 30, 'country': 'Нидерланды'},
                    {'name': '60 дней', 'price': 269.0, 'duration_days': 60, 'country': 'Нидерланды'},
                    {'name': '90 дней', 'price': 379.0, 'duration_days': 90, 'country': 'Нидерланды'},
                ]
                # Добавляем новые тарифы
                await session.execute(insert(db.Products), all_tariffs)
                log.info("Начальные тарифы добавлены.")
            else:
                log.info(f"В таблице Products уже есть {products_count} тарифов. Пропускаю добавление.")
            await session.commit()
    log.info("База данных инициализирована, админ и тарифы добавлены.")

    asyncio.create_task(scheduler_tasks.check_expirations(bot))


async def on_shutdown(bot: Bot):
    """Действия при остановке: удаление вебхука."""
    log.warning("Shutting down..")
    await bot.delete_webhook()
    log.warning("Telegram webhook removed.")


async def main():
    logging.basicConfig(level=logging.INFO)
    global log
    log = logging.getLogger(__name__)

    bot = Bot(token=settings.BOT_TOKEN.get_secret_value())
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Регистрируем middleware для фильтрации CRM-топиков
    dp.message.middleware(CRMFilterMiddleware())
    dp.callback_query.middleware(CRMFilterMiddleware())

    # Регистрируем роутеры (порядок важен!)
    dp.include_router(crm_handlers.router)  # CRM-команды первыми
    dp.include_router(admin_handlers.router)
    dp.include_router(user_handlers.router)

    # Регистрируем lifecycle хуки
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)

    # Создаем приложение aiohttp
    app = web.Application()

    # Передаем объект bot в приложение, чтобы вебхук ЮKassa мог его использовать
    app['bot'] = bot

    # Регистрируем обработчик для вебхуков Telegram
    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
    ).register(app, path=TELEGRAM_WEBHOOK_PATH)

    app.router.add_post(YOOKASSA_WEBHOOK_PATH, webhook_handlers.yookassa_webhook_handler)
    app.router.add_post(settings.CRYPTO_BOT_WEBHOOK_PATH, webhook_handlers.crypto_bot_webhook_handler)
    app.router.add_get("/sub/{token}", webhook_handlers.subscription_handler)

    # # Web App API endpoints
    # app.router.add_get("/api/webapp/health", webapp_handlers.webapp_health_check)
    # app.router.add_get("/api/webapp/user", webapp_handlers.webapp_get_user_info)
    #
    # # Статические файлы для Web App
    # webapp_dir = Path(__file__).parent / "webapp"
    # app.router.add_static("/webapp", webapp_dir, name="webapp")

    # Связываем aiohttp приложение с диспетчером aiogram
    setup_application(app, dp, bot=bot)

    # Запускаем веб-сервер aiohttp
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, APP_HOST, APP_PORT)
    log.info(f"Starting aiohttp server on http://{APP_HOST}:{APP_PORT}")
    await site.start()

    # Бесконечный цикл (чтобы процесс не завершался)
    await asyncio.Event().wait()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        log.warning("Bot stopped!")
