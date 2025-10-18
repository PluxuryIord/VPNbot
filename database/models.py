# database/models.py
import datetime
from sqlalchemy import (
    create_engine, MetaData, Table, Column, Integer, String, BigInteger,
    DateTime, ForeignKey, Float, Enum, Boolean
)
from sqlalchemy.engine import URL
from sqlalchemy.sql import func

# Конфигурация для SQLite
# Для PostgreSQL, используй: "postgresql+asyncpg://user:pass@host/db"
DB_URL = "sqlite+aiosqlite:///./vpn_bot.db"

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
    Column('name', String(255), nullable=False, unique=True), # "30 дней"
    Column('price', Float, nullable=False), # 100.00
    Column('duration_days', Integer, nullable=False) # 30
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
    Column('vless_key', String, unique=True, nullable=False), # vless://...
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