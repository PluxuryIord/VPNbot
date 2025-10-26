import datetime
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, BigInteger,
    DateTime, ForeignKey, Float, Enum, Boolean
)

from sqlalchemy.sql import func
from config import settings


DB_URL = (
    f"postgresql+asyncpg://{settings.POSTGRESQL_USER}:{settings.POSTGRESQL_PASSWORD.get_secret_value()}"
    f"@{settings.POSTGRESQL_HOST}:{settings.POSTGRESQL_PORT}/{settings.POSTGRESQL_DBNAME}"
)
metadata = MetaData()

# Таблица пользователей
Users = Table(
    'users',
    metadata,
    Column('user_id', BigInteger, primary_key=True, unique=True, autoincrement=False),
    Column('username', String(255), nullable=True),
    Column('first_name', String(255)),
    Column('created_at', DateTime, server_default=func.now())
)

# Таблица продуктов (тарифов)
Products = Table(
    'products',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('name', String(255), nullable=False), # "30 дней", "60 дней"
    Column('price', Float, nullable=False), # 199.00
    Column('duration_days', Integer, nullable=False), # 30
    Column('country', String(100), nullable=True, index=True)
)

# Таблица заказов
Orders = Table(
    'orders',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('user_id', BigInteger, ForeignKey('users.user_id'), nullable=False),
    Column('product_id', Integer, ForeignKey('products.id'), nullable=False),
    Column('amount', Float, nullable=False),
    Column('status', Enum('pending', 'paid', 'failed', name='order_status'),
           nullable=False, default='pending'),
    Column('payment_id', String(255), nullable=True), # ID из ЮKassa
    Column('created_at', DateTime, server_default=func.now())
)

# Таблица ключей VLess
Keys = Table(
    'keys',
    metadata,
    Column('id', Integer, primary_key=True, autoincrement=True),
    Column('user_id', BigInteger, ForeignKey('users.user_id'), nullable=False),
    Column('order_id', Integer, ForeignKey('orders.id'), nullable=False),
    Column('vless_key', String, unique=True, nullable=False),
    Column('created_at', DateTime, server_default=func.now()),
    Column('expires_at', DateTime, nullable=False)
)

# Таблица для админов
Admins = Table(
    'admins',
    metadata,
    Column('user_id', BigInteger, primary_key=True, unique=True, autoincrement=False),
    Column('is_super_admin', Boolean, default=False) # На случай разных ролей
)