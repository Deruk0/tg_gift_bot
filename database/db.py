"""
Асинхронные операции с базой данных SQLite через aiosqlite.
Все функции полностью асинхронны.
"""
import logging
from datetime import date
from typing import Optional

import aiosqlite

from database.models import CREATE_TABLES_SQL

logger = logging.getLogger(__name__)

# Путь к файлу базы данных
DB_PATH = "giftgraph.db"


async def init_db() -> None:
    """Инициализация базы данных и создание таблиц (идемпотентно)"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(CREATE_TABLES_SQL)
        await db.commit()
    logger.info("База данных инициализирована: %s", DB_PATH)


async def get_user(user_id: int) -> Optional[dict]:
    """Получить запись пользователя по Telegram ID"""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(user_id: int) -> dict:
    """Создать запись нового пользователя с нулевыми счётчиками"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id) VALUES (?)",
            (user_id,),
        )
        await db.commit()
    user = await get_user(user_id)
    logger.info("Новый пользователь зарегистрирован: %d", user_id)
    return user


async def get_or_create_user(user_id: int) -> dict:
    """Получить пользователя или создать новую запись (upsert)"""
    user = await get_user(user_id)
    if user is None:
        user = await create_user(user_id)
    return user


async def increment_search_count(user_id: int) -> None:
    """Увеличить счётчик использованных бесплатных поисков на 1"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET free_searches_used = free_searches_used + 1 "
            "WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def set_subscription(user_id: int, until_date: date) -> None:
    """Установить или продлить подписку до указанной даты"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET subscription_until = ? WHERE user_id = ?",
            (until_date.isoformat(), user_id),
        )
        await db.commit()
    logger.info(
        "Подписка пользователя %d активирована до %s",
        user_id,
        until_date,
    )


async def set_promo_used(user_id: int, promo_code: str) -> None:
    """Зафиксировать использование промокода пользователем"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET promo_used = ? WHERE user_id = ?",
            (promo_code, user_id),
        )
        await db.commit()
