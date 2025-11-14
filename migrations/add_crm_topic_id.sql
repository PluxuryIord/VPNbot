-- Миграция: Добавление поля crm_topic_id в таблицу users
-- Дата: 2025-11-14
-- Описание: Добавляет поле для хранения ID топика пользователя в CRM-группе

-- Проверяем и добавляем колонку crm_topic_id
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name = 'crm_topic_id'
    ) THEN
        ALTER TABLE users ADD COLUMN crm_topic_id INTEGER;
        RAISE NOTICE '✅ Колонка crm_topic_id успешно добавлена';
    ELSE
        RAISE NOTICE 'ℹ️  Колонка crm_topic_id уже существует, пропускаем';
    END IF;
END $$;

-- Проверяем и создаем индекс
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE indexname = 'idx_users_crm_topic_id'
    ) THEN
        CREATE INDEX idx_users_crm_topic_id ON users(crm_topic_id);
        RAISE NOTICE '✅ Индекс idx_users_crm_topic_id успешно создан';
    ELSE
        RAISE NOTICE 'ℹ️  Индекс idx_users_crm_topic_id уже существует, пропускаем';
    END IF;
END $$;

-- Добавляем комментарий к полю
COMMENT ON COLUMN users.crm_topic_id IS 'ID топика пользователя в CRM-группе Telegram';

-- Выводим итоговую информацию
DO $$
DECLARE
    col_exists BOOLEAN;
    idx_exists BOOLEAN;
BEGIN
    -- Проверяем колонку
    SELECT EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'users'
        AND column_name = 'crm_topic_id'
    ) INTO col_exists;

    -- Проверяем индекс
    SELECT EXISTS (
        SELECT 1
        FROM pg_indexes
        WHERE indexname = 'idx_users_crm_topic_id'
    ) INTO idx_exists;

    RAISE NOTICE '';
    RAISE NOTICE '========================================';
    RAISE NOTICE '📊 Результат миграции:';
    RAISE NOTICE '========================================';

    IF col_exists THEN
        RAISE NOTICE '✅ Колонка users.crm_topic_id: EXISTS';
    ELSE
        RAISE NOTICE '❌ Колонка users.crm_topic_id: NOT FOUND';
    END IF;

    IF idx_exists THEN
        RAISE NOTICE '✅ Индекс idx_users_crm_topic_id: EXISTS';
    ELSE
        RAISE NOTICE '❌ Индекс idx_users_crm_topic_id: NOT FOUND';
    END IF;

    RAISE NOTICE '========================================';
    RAISE NOTICE '';

    IF col_exists AND idx_exists THEN
        RAISE NOTICE '🎉 Миграция завершена успешно!';
    ELSE
        RAISE EXCEPTION '❌ Миграция завершилась с ошибками!';
    END IF;
END $$;

