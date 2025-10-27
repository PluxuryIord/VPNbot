from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update, func
from database.models import metadata, DB_URL, Users, Products, Orders, Keys, Admins
import datetime

engine = create_async_engine(DB_URL)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Инициализация БД и создание таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def get_or_create_user(user_id: int, username: str, first_name: str) -> tuple[bool, bool]:
    """
    Добавляет нового пользователя, если его нет.
    Возвращает кортеж: (user_created: bool, has_received_trial: bool)
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(Users).where(Users.c.user_id == user_id)
            )
            user = result.fetchone()

            if not user:
                await session.execute(
                    insert(Users).values(
                        user_id=user_id,
                        username=username,
                        first_name=first_name,
                        has_received_trial=False # Явно указываем при создании
                    )
                )
                await session.commit()
                return True, False # Создан, триал не получал
            else:
                # Возвращаем статус триала существующего пользователя
                return False, user.has_received_trial # Не создан, статус триала


async def get_products(country: str | None = None):
    """
    Получает список тарифов.
    Если указана страна, фильтрует по ней.
    """
    async with AsyncSessionLocal() as session:
        stmt = select(Products)
        if country:
            # Фильтруем по стране ИЛИ выбираем общие тарифы (где country is NULL)
            stmt = stmt.where((Products.c.country == country) | (Products.c.country == None))
        else:
            # Если страна не указана, показываем все (или только общие? Решай сам)
            pass # Показываем все
        result = await session.execute(stmt)
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


async def get_user_keys(user_id: int, page: int = 0, page_size: int = 5): # Добавили page, page_size
    """Получает ключи пользователя для указанной страницы."""
    async with AsyncSessionLocal() as session:
        offset = page * page_size
        stmt = (
            select(Keys)
            .where(Keys.c.user_id == user_id)
            .order_by(Keys.c.expires_at.desc())
            .limit(page_size)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return result.fetchall()


async def count_user_keys(user_id: int) -> int:
    """Считает общее количество ключей пользователя."""
    async with AsyncSessionLocal() as session:
        stmt = select(func.count()).select_from(Keys).where(Keys.c.user_id == user_id)
        result = await session.execute(stmt)
        count = result.scalar_one_or_none()
        return count if count is not None else 0



async def get_key_by_id(key_id: int):
    """Получает один ключ по его ID."""
    async with AsyncSessionLocal() as session:
        stmt = select(Keys).where(Keys.c.id == key_id)
        result = await session.execute(stmt)
        return result.fetchone()


async def update_key_expiry(key_id: int, new_expires_at: datetime.datetime):
    """Обновляет дату истечения срока действия ключа."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Keys)
                .where(Keys.c.id == key_id)
                .values(expires_at=new_expires_at)
            )
            await session.execute(stmt)
            await session.commit()

async def get_user_key_by_order_id(order_id: int):
    """Получает ключ по ID заказа"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Keys).where(Keys.c.order_id == order_id)
        )
        return result.fetchone()


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


# async def delete_order(order_id: int):
#     """Удаляет заказ по ID."""
#     async with AsyncSessionLocal() as session:
#         async with session.begin():
#             stmt = delete(Orders).where(Orders.c.id == order_id)
#             await session.execute(stmt)
#             await session.commit()


async def check_trial_status(user_id: int) -> bool:
    """Проверяет, получал ли пользователь пробный ключ."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users.c.has_received_trial).where(Users.c.user_id == user_id)
        )
        status = result.scalar_one_or_none()
        return status if status is not None else False


async def mark_trial_received(user_id: int):
    """Отмечает, что пользователь получил пробный ключ."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Users)
                .where(Users.c.user_id == user_id)
                .values(has_received_trial=True)
            )
            await session.execute(stmt)
            await session.commit()


async def get_all_active_keys_details():
    """
    Получает детальную информацию по всем АКТИВНЫМ ключам.
    Джойнит Keys, Users, Orders, Products.
    Учитывает пробные ключи (где order_id is None).
    """
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()

        stmt = (
            select(
                Keys.c.vless_key,
                Keys.c.expires_at,
                Users.c.user_id,
                Users.c.first_name,
                Products.c.name.label("product_name"),
                Products.c.duration_days
            )
            .join(Users, Keys.c.user_id == Users.c.user_id)
            .outerjoin(Orders, Keys.c.order_id == Orders.c.id)
            .outerjoin(Products, Orders.c.product_id == Products.c.id)
            .where(Keys.c.expires_at > now)  # Выбираем только активные ключи
            .order_by(Keys.c.expires_at.asc())  # Сначала те, что скоро истекут
        )

        result = await session.execute(stmt)
        return result.fetchall()