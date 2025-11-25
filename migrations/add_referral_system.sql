-- Миграция для добавления реферальной системы
-- Дата: 2025-11-25

-- Добавляем поле referrer_id в таблицу users
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS referrer_id BIGINT;

-- Создаем таблицу referrals
CREATE TABLE IF NOT EXISTS referrals (
    id SERIAL PRIMARY KEY,
    referrer_id BIGINT NOT NULL REFERENCES users(user_id),
    referred_id BIGINT NOT NULL REFERENCES users(user_id),
    created_at TIMESTAMP DEFAULT NOW(),
    has_purchased BOOLEAN NOT NULL DEFAULT FALSE,
    first_purchase_at TIMESTAMP,
    UNIQUE(referrer_id, referred_id)
);

-- Создаем индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_referrals_referrer_id ON referrals(referrer_id);
CREATE INDEX IF NOT EXISTS idx_referrals_referred_id ON referrals(referred_id);
CREATE INDEX IF NOT EXISTS idx_users_referrer_id ON users(referrer_id);

