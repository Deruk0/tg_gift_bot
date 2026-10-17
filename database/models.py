"""
SQL-схема базы данных.
Хранятся только пользователи, их лимиты и подписки.
Данные графов в БД не сохраняются — только в памяти в рамках сессии.
"""

CREATE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id            INTEGER PRIMARY KEY,
    free_searches_used INTEGER DEFAULT 0,        -- использовано бесплатных поисков (макс. 3)
    subscription_until DATE    DEFAULT NULL,      -- дата окончания подписки (NULL = нет)
    promo_used         TEXT    DEFAULT NULL,      -- использованный промокод (один навсегда)
    paid_searches      INTEGER NOT NULL DEFAULT 0 CHECK (paid_searches >= 0)
);

CREATE TABLE IF NOT EXISTS search_payments (
    charge_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    attempts INTEGER NOT NULL,
    stars INTEGER NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""
