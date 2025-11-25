"""
Скрипт для применения миграции реферальной системы
"""
import asyncio
import asyncpg
from config import settings

async def apply_migration():
    """Применяет миграцию для реферальной системы"""
    
    # Подключаемся к базе данных
    conn = await asyncpg.connect(
        user=settings.POSTGRESQL_USER,
        password=settings.POSTGRESQL_PASSWORD.get_secret_value(),
        database=settings.POSTGRESQL_DBNAME,
        host=settings.POSTGRESQL_HOST,
        port=settings.POSTGRESQL_PORT
    )
    
    try:
        print("Применяю миграцию реферальной системы...")
        
        # Читаем SQL файл миграции
        with open('migrations/add_referral_system.sql', 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        # Выполняем миграцию
        await conn.execute(migration_sql)
        
        print("✅ Миграция успешно применена!")
        print("\nДобавлены:")
        print("  - Поле referrer_id в таблицу users")
        print("  - Таблица referrals")
        print("  - Индексы для оптимизации запросов")
        
    except Exception as e:
        print(f"❌ Ошибка при применении миграции: {e}")
        raise
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(apply_migration())

