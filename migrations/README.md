# 📁 Миграции базы данных

## Применение миграции CRM

### Способ 1: Через psql (рекомендуется)

```bash
psql -U your_user -d your_database -f migrations/add_crm_topic_id.sql
```

**Пример:**
```bash
psql -U postgres -d vpnbot -f migrations/add_crm_topic_id.sql
```

### Способ 2: Через pgAdmin

1. Откройте pgAdmin
2. Подключитесь к вашей базе данных
3. Откройте Query Tool (Инструменты → Query Tool)
4. Скопируйте содержимое файла `add_crm_topic_id.sql`
5. Вставьте в Query Tool
6. Нажмите Execute (F5)

### Способ 3: Через Python скрипт

Создайте файл `apply_migration.py`:

```python
import asyncio
import asyncpg
from config import settings

async def apply_migration():
    # Подключаемся к БД
    conn = await asyncpg.connect(settings.DATABASE_URL)
    
    try:
        # Читаем миграцию
        with open('migrations/add_crm_topic_id.sql', 'r', encoding='utf-8') as f:
            migration_sql = f.read()
        
        # Применяем миграцию
        await conn.execute(migration_sql)
        
        print("✅ Миграция успешно применена!")
        
    except Exception as e:
        print(f"❌ Ошибка при применении миграции: {e}")
    
    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(apply_migration())
```

Запустите:
```bash
python apply_migration.py
```

## Что делает миграция?

1. **Проверяет наличие колонки** `crm_topic_id` в таблице `users`
2. **Добавляет колонку**, если её нет:
   ```sql
   ALTER TABLE users ADD COLUMN crm_topic_id INTEGER;
   ```
3. **Создаёт индекс** для быстрого поиска:
   ```sql
   CREATE INDEX idx_users_crm_topic_id ON users(crm_topic_id);
   ```
4. **Добавляет комментарий** к полю
5. **Выводит отчёт** о результатах миграции

## Ожидаемый вывод

При успешном применении вы увидите:

```
NOTICE:  ✅ Колонка crm_topic_id успешно добавлена
NOTICE:  ✅ Индекс idx_users_crm_topic_id успешно создан
NOTICE:  
NOTICE:  ========================================
NOTICE:  📊 Результат миграции:
NOTICE:  ========================================
NOTICE:  ✅ Колонка users.crm_topic_id: EXISTS
NOTICE:  ✅ Индекс idx_users_crm_topic_id: EXISTS
NOTICE:  ========================================
NOTICE:  
NOTICE:  🎉 Миграция завершена успешно!
```

При повторном применении:

```
NOTICE:  ℹ️  Колонка crm_topic_id уже существует, пропускаем
NOTICE:  ℹ️  Индекс idx_users_crm_topic_id уже существует, пропускаем
NOTICE:  
NOTICE:  ========================================
NOTICE:  📊 Результат миграции:
NOTICE:  ========================================
NOTICE:  ✅ Колонка users.crm_topic_id: EXISTS
NOTICE:  ✅ Индекс idx_users_crm_topic_id: EXISTS
NOTICE:  ========================================
NOTICE:  
NOTICE:  🎉 Миграция завершена успешно!
```

## Проверка результата

### Через psql:

```sql
-- Проверить наличие колонки
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name = 'crm_topic_id';

-- Проверить наличие индекса
SELECT indexname, indexdef 
FROM pg_indexes 
WHERE indexname = 'idx_users_crm_topic_id';

-- Посмотреть данные
SELECT user_id, first_name, crm_topic_id 
FROM users 
LIMIT 10;
```

### Через Python:

```python
import asyncio
from database.db_commands import AsyncSessionLocal
from database.models import Users
from sqlalchemy import select

async def check_migration():
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(Users.c.user_id, Users.c.crm_topic_id).limit(5)
        )
        rows = result.fetchall()
        
        print("Первые 5 пользователей:")
        for row in rows:
            print(f"User ID: {row.user_id}, Topic ID: {row.crm_topic_id}")

asyncio.run(check_migration())
```

## Откат миграции (если нужно)

Если нужно откатить изменения:

```sql
-- Удалить индекс
DROP INDEX IF EXISTS idx_users_crm_topic_id;

-- Удалить колонку
ALTER TABLE users DROP COLUMN IF EXISTS crm_topic_id;
```

Или создайте файл `migrations/rollback_crm_topic_id.sql`:

```sql
-- Откат миграции: Удаление поля crm_topic_id

DO $$
BEGIN
    -- Удаляем индекс
    IF EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE indexname = 'idx_users_crm_topic_id'
    ) THEN
        DROP INDEX idx_users_crm_topic_id;
        RAISE NOTICE '✅ Индекс idx_users_crm_topic_id удалён';
    ELSE
        RAISE NOTICE 'ℹ️  Индекс idx_users_crm_topic_id не найден';
    END IF;
END $$;

DO $$
BEGIN
    -- Удаляем колонку
    IF EXISTS (
        SELECT 1 
        FROM information_schema.columns 
        WHERE table_name = 'users' 
        AND column_name = 'crm_topic_id'
    ) THEN
        ALTER TABLE users DROP COLUMN crm_topic_id;
        RAISE NOTICE '✅ Колонка crm_topic_id удалена';
    ELSE
        RAISE NOTICE 'ℹ️  Колонка crm_topic_id не найдена';
    END IF;
END $$;

RAISE NOTICE '🎉 Откат миграции завершён!';
```

Применить откат:
```bash
psql -U your_user -d your_database -f migrations/rollback_crm_topic_id.sql
```

## Безопасность

✅ **Миграция безопасна:**
- Проверяет наличие колонки перед добавлением
- Проверяет наличие индекса перед созданием
- Можно применять многократно без ошибок
- Не удаляет и не изменяет существующие данные
- Использует `INTEGER` (nullable), поэтому не требует значений по умолчанию

## Troubleshooting

### Ошибка: "permission denied"

```
ERROR:  permission denied for table users
```

**Решение:** Используйте пользователя с правами на изменение таблиц:
```bash
psql -U postgres -d vpnbot -f migrations/add_crm_topic_id.sql
```

### Ошибка: "database does not exist"

```
FATAL:  database "vpnbot" does not exist
```

**Решение:** Проверьте название базы данных:
```bash
psql -U postgres -l  # Список всех баз
```

### Ошибка: "relation users does not exist"

```
ERROR:  relation "users" does not exist
```

**Решение:** Убедитесь, что таблица `users` создана. Проверьте:
```bash
psql -U postgres -d vpnbot -c "\dt"
```

## История миграций

| Дата | Файл | Описание |
|------|------|----------|
| 2025-11-14 | `add_crm_topic_id.sql` | Добавление поля для CRM-топиков |

---

**Автор:** VPNbot Team  
**Версия:** 1.0.0

