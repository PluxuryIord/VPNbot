# database/db_commands.py
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update
from .models import metadata, DB_URL, Users, Products, Orders, Keys, Admins
import datetime

# Создаем асинхронный "движок"
engine = create_async_engine(DB_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Инициализация БД и создание таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


# --- Функции для работы с БД ---

async def get_or_create_user(user_id: int, username: str, first_name: str):
    """Добавляет нового пользователя, если его нет"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Проверяем, существует ли пользователь
            result = await session.execute(
                select(Users).where(Users.c.user_id == user_id)
            )
            user = result.fetchone()

            if not user:
                # Создаем нового
                await session.execute(
                    insert(Users).values(
                        user_id=user_id,
                        username=username,
                        first_name=first_name
                    )
                )
                await session.commit()
                return True  # True = Cоздан
            return False  # False = Уже был


async def get_products():
    """Получает список всех активных тарифов"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Products))
        return result.fetchall()


async def get_product_by_id(product_id: int):
    """Получает продукт по ID"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Products).where(Products.c.id == product_id)
        )
        return result.fetchone()


async def create_order(user_id: int, product_id: int, amount: float) -> int:
    """Создает новый заказ в статусе 'pending' и возвращает его ID"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                insert(Orders).values(
                    user_id=user_id,
                    product_id=product_id,
                    amount=amount,
                    status='pending'
                ).returning(Orders.c.id)
            )
            order_id = result.scalar_one()
            await session.commit()
            return order_id


async def update_order_status(order_id: int, payment_id: str, status: str = 'paid'):
    """Обновляет статус заказа и ID платежа"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                update(Orders).
                where(Orders.c.id == order_id).
                values(status=status, payment_id=payment_id)
            )
            await session.commit()


async def get_order_by_id(order_id: int):
    """Получает заказ по ID"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Orders).where(Orders.c.id == order_id)
        )
        return result.fetchone()


async def add_vless_key(user_id: int, order_id: int, vless_key: str, expires_at: datetime.datetime):
    """Добавляет сгенерированный ключ в БД"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                insert(Keys).values(
                    user_id=user_id,
                    order_id=order_id,
                    vless_key=vless_key,
                    expires_at=expires_at
                )
            )
            await session.commit()


async def get_user_keys(user_id: int):
    """Получает все ключи пользователя"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Keys).where(Keys.c.user_id == user_id).order_by(Keys.c.expires_at.desc())
        )
        return result.fetchall()


async def is_admin(user_id: int) -> bool:
    """Проверяет, является ли пользователь админом"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Admins).where(Admins.c.user_id == user_id)
        )
        return result.fetchone() is not None


async def get_all_user_ids():
    """Получает ID всех пользователей для рассылки"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Users.c.user_id))
        return result.scalars().all()