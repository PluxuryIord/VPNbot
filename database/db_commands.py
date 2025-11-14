import uuid

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import select, insert, update, func
from database.models import metadata, DB_URL, Users, Products, Orders, Keys, Admins
import datetime

engine = create_async_engine(
    DB_URL,
    pool_recycle=1800,
    pool_pre_ping=True
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    """Инициализация БД и создание таблиц"""
    async with engine.begin() as conn:
        await conn.run_sync(metadata.create_all)


async def get_or_create_user(user_id: int, username: str, first_name: str) -> int | None:
    """
    Добавляет нового пользователя, если его нет.
    Возвращает last_menu_id (int) или None.
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
                        has_received_trial=False,
                        last_menu_id=None  #
                    )
                )
                await session.commit()
                return None  #
            else:
                #
                return user.last_menu_id  #


async def update_user_menu_id(user_id: int, message_id: int):
    """Обновляет ID последнего меню пользователя."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(
                update(Users)
                .where(Users.c.user_id == user_id)
                .values(last_menu_id=message_id)
            )
            await session.commit()


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
            pass  # Показываем все
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


async def add_vless_key(user_id: int, order_id: int, vless_key: str, expires_at: datetime.datetime) -> uuid.UUID:
    """
    Добавляет сгенерированный ключ в БД и возвращает его токен подписки.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            new_token = uuid.uuid4()
            await session.execute(
                insert(Keys).values(
                    user_id=user_id,
                    order_id=order_id,
                    vless_key=vless_key,
                    expires_at=expires_at,
                    subscription_token=new_token  #
                )
            )
            await session.commit()
            return new_token


async def get_user_keys(user_id: int, page: int = 0, page_size: int = 5):  # Добавили page, page_size
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
                Users.c.username,
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


async def get_keys_for_renewal_warning(hours: int = 24):
    """
    Находит ПЛАТНЫЕ ключи, которые истекают через 23-24 часа,
    И о которых ЕЩЕ НЕ ПРЕДУПРЕЖДАЛИ.
    """
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()
        in_X_minus_1_hours = now + datetime.timedelta(hours=hours - 1)
        in_X_hours = now + datetime.timedelta(hours=hours)

        stmt = (
            select(Keys.c.user_id, Keys.c.id, Products.c.name)
            .join(Orders, Keys.c.order_id == Orders.c.id)
            .join(Products, Orders.c.product_id == Products.c.id)
            .where(
                (Keys.c.expires_at > in_X_minus_1_hours) &
                (Keys.c.expires_at <= in_X_hours) &
                (Keys.c.order_id.is_not(None)) &
                (Keys.c.has_sent_renewal_warning == False)
            )
        )
        result = await session.execute(stmt)
        return result.fetchall()


async def get_keys_for_expiry_notification():
    """
    Находит ВСЕ ключи (включая пробные), которые УЖЕ ИСТЕКЛИ,
    И о которых ЕЩЕ НЕ УВЕДОМЛЯЛИ.
    """
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()

        stmt = (
            select(Keys.c.user_id, Keys.c.id, Keys.c.order_id)
            .where(
                (Keys.c.expires_at <= now) &  #
                (Keys.c.has_sent_expiry_notification == False)  #
            )
        )
        result = await session.execute(stmt)
        return result.fetchall()


async def get_keys_for_renewal_warning(hours: int = 24):
    """Находит ПЛАТНЫЕ ключи, которые истекают через указанное время."""
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()
        in_X_hours = now + datetime.timedelta(hours=hours)
        # Берем диапазон, чтобы не спамить, если бот лежал
        in_X_minus_some_hours = now + datetime.timedelta(hours=max(1, hours - 2))

        stmt = (
            select(Keys.c.user_id, Keys.c.id, Products.c.name)
            .join(Orders, Keys.c.order_id == Orders.c.id)
            .join(Products, Orders.c.product_id == Products.c.id)
            .where(
                (Keys.c.expires_at > in_X_minus_some_hours) &
                (Keys.c.expires_at <= in_X_hours) &
                (Keys.c.order_id.is_not(None)) &
                (Keys.c.has_sent_renewal_warning == False)
            )
        )
        result = await session.execute(stmt)
        return result.fetchall()


async def get_trial_keys_for_warning(hours: int = 2):
    """Находит ПРОБНЫЕ ключи, истекающие скоро (для Task 4)."""
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()
        in_X_hours = now + datetime.timedelta(hours=hours)

        stmt = (
            select(Keys.c.user_id, Keys.c.id)
            .where(
                (Keys.c.expires_at > now) &
                (Keys.c.expires_at <= in_X_hours) &
                (Keys.c.order_id.is_(None)) &  # Только пробные
                (Keys.c.has_sent_trial_warning == False)
            )
        )
        result = await session.execute(stmt)
        return result.fetchall()


async def mark_trial_warning_sent(key_id: int):
    """Отмечает, что предупреждение о триале отправлено."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Keys)
                .where(Keys.c.id == key_id)
                .values(has_sent_trial_warning=True)
            )
            await session.execute(stmt)
            await session.commit()


async def mark_renewal_warning_sent(key_id: int):
    """Отмечает, что предупреждение за 24ч было отправлено."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Keys)
                .where(Keys.c.id == key_id)
                .values(has_sent_renewal_warning=True)
            )
            await session.execute(stmt)
            await session.commit()


async def mark_expiry_notification_sent(key_id: int):
    """Отмечает, что уведомление об истечении было отправлено."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Keys)
                .where(Keys.c.id == key_id)
                .values(has_sent_expiry_notification=True)
            )
            await session.execute(stmt)
            await session.commit()


async def get_key_by_subscription_token(token: str):
    """Находит ОДИН vless_key по токену подписки (из таблицы Keys)."""
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()
        try:
            #
            stmt = select(Keys.c.vless_key).where(
                (Keys.c.subscription_token == token) &
                (Keys.c.expires_at > now)  #
            )
            result = await session.execute(stmt)
            return result.scalar_one_or_none()  #
        except Exception:
            #
            return None



async def get_users_for_trial_reminder(hours_min: int = 24, hours_max: int = 25):
    """
    Находит пользователей, которые зарегистрировались X часов назад,
    не брали триал и не получали напоминание.
    """
    async with AsyncSessionLocal() as session:
        now = datetime.datetime.now()
        # Ищем тех, кто зарегистрировался 24-25 часов назад
        min_time_ago = now - datetime.timedelta(hours=hours_max)
        max_time_ago = now - datetime.timedelta(hours=hours_min)

        stmt = (
            select(Users.c.user_id)
            .where(
                (Users.c.created_at > min_time_ago) &
                (Users.c.created_at <= max_time_ago) &
                (Users.c.has_received_trial == False) &
                (Users.c.has_sent_trial_reminder == False)
            )
        )
        result = await session.execute(stmt)
        return result.scalars().all()


async def mark_trial_reminder_sent(user_id: int):
    """Отмечает, что напоминание о триале было отправлено."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Users)
                .where(Users.c.user_id == user_id)
                .values(has_sent_trial_reminder=True)
            )
            await session.execute(stmt)
            await session.commit()


async def update_user_topic_id(user_id: int, topic_id: int):
    """Обновляет ID топика для пользователя в CRM-группе."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = (
                update(Users)
                .where(Users.c.user_id == user_id)
                .values(crm_topic_id=topic_id)
            )
            await session.execute(stmt)
            await session.commit()


async def get_user_topic_id(user_id: int) -> int | None:
    """Получает ID топика пользователя в CRM-группе."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users.c.crm_topic_id).where(Users.c.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def count_all_users() -> int:
    """Считает общее количество пользователей."""
    async with AsyncSessionLocal() as session:
        stmt = select(func.count()).select_from(Users)
        result = await session.execute(stmt)
        count = result.scalar_one_or_none()
        return count if count is not None else 0


async def get_all_users_paginated(page: int = 0, page_size: int = 10):
    """
    Получает список всех пользователей с пагинацией.
    Возвращает базовую информацию: user_id, username, first_name, created_at.
    """
    async with AsyncSessionLocal() as session:
        offset = page * page_size
        stmt = (
            select(Users)
            .order_by(Users.c.created_at.desc())  # Сначала новые пользователи
            .limit(page_size)
            .offset(offset)
        )
        result = await session.execute(stmt)
        return result.fetchall()


async def get_user_stats_detailed(user_id: int):
    """
    Получает детальную статистику по пользователю:
    - Информация о пользователе
    - Количество заказов и общая сумма
    - Список всех ключей с деталями
    """
    async with AsyncSessionLocal() as session:
        # 1. Информация о пользователе
        user_stmt = select(Users).where(Users.c.user_id == user_id)
        user_result = await session.execute(user_stmt)
        user = user_result.fetchone()

        if not user:
            return None

        # 2. Статистика по заказам
        orders_stmt = (
            select(
                func.count(Orders.c.id).label('total_orders'),
                func.sum(Orders.c.amount).label('total_spent')
            )
            .where(
                (Orders.c.user_id == user_id) &
                (Orders.c.status == 'paid')
            )
        )
        orders_result = await session.execute(orders_stmt)
        orders_stats = orders_result.fetchone()

        # 3. Список всех ключей с деталями
        now = datetime.datetime.now()
        keys_stmt = (
            select(
                Keys.c.id,
                Keys.c.vless_key,
                Keys.c.created_at,
                Keys.c.expires_at,
                Keys.c.order_id,
                Products.c.name.label("product_name"),
                Products.c.duration_days
            )
            .outerjoin(Orders, Keys.c.order_id == Orders.c.id)
            .outerjoin(Products, Orders.c.product_id == Products.c.id)
            .where(Keys.c.user_id == user_id)
            .order_by(Keys.c.expires_at.desc())  # Сначала активные
        )
        keys_result = await session.execute(keys_stmt)
        keys = keys_result.fetchall()

        return {
            'user': user,
            'total_orders': orders_stats.total_orders or 0,
            'total_spent': orders_stats.total_spent or 0.0,
            'keys': keys,
            'active_keys_count': sum(1 for k in keys if k.expires_at > now),
            'total_keys_count': len(keys)
        }