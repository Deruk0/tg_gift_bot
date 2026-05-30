"""
Middleware для проверки лимитов поиска и статуса подписки.

Логика перед каждым /search:
  1. Активная подписка?  → пропускаем без ограничений
  2. free_searches_used < 3? → разрешаем + инкрементируем + предупреждаем при 1-2 оставшихся
  3. free_searches_used >= 3? → блокируем + кнопка подписки

Middleware прозрачен для всех команд кроме /search.
"""
import logging
from datetime import date
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from config import FREE_SEARCHES_LIMIT
from database.db import get_or_create_user, increment_search_count

logger = logging.getLogger(__name__)


class LimitsMiddleware(BaseMiddleware):
    """
    Проверяет подписку и лимиты до передачи обработчику /search.
    При блокировке возвращает None (не вызывает handler).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:

        # Пропускаем всё кроме сообщений
        if not isinstance(event, Message):
            return await handler(event, data)

        # Пропускаем всё кроме /search
        if not event.text or not event.text.startswith("/search"):
            return await handler(event, data)

        user_id = event.from_user.id
        user = await get_or_create_user(user_id)

        # ── Шаг 1: Проверяем активную подписку ────────────────────────────────
        if user["subscription_until"]:
            try:
                sub_until = date.fromisoformat(user["subscription_until"])
                if sub_until >= date.today():
                    # Подписка активна — пропускаем без ограничений
                    data["user_db"] = user
                    return await handler(event, data)
            except ValueError:
                logger.warning(
                    "Некорректный формат даты подписки у пользователя %d: %s",
                    user_id,
                    user["subscription_until"],
                )

        # ── Шаг 2: Проверяем бесплатные поиски ────────────────────────────────
        searches_used: int = user["free_searches_used"]

        if searches_used < FREE_SEARCHES_LIMIT:
            # Инкрементируем сразу (до обработки — защита от гонки)
            await increment_search_count(user_id)
            remaining = FREE_SEARCHES_LIMIT - searches_used - 1

            # Предупреждаем когда лимит на исходе
            if remaining == 0:
                await event.answer(
                    "⚠️ Это ваш <b>последний</b> бесплатный поиск.\n"
                    "Оформите подписку командой /subscribe для неограниченного доступа.",
                    parse_mode="HTML",
                )
            elif remaining == 1:
                await event.answer(
                    f"⚠️ Осталось бесплатных поисков: <b>{remaining}</b>.\n"
                    "Команда /subscribe — подробности подписки.",
                    parse_mode="HTML",
                )

            data["user_db"] = user
            return await handler(event, data)

        # ── Шаг 3: Лимит исчерпан — блокируем ────────────────────────────────
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="⭐ Оформить подписку",
                        callback_data="show_subscription",
                    )
                ]
            ]
        )

        await event.answer(
            "🚫 Вы использовали все <b>3 бесплатных поиска</b>.\n\n"
            "Оформите подписку для неограниченного доступа к графу связей:",
            parse_mode="HTML",
            reply_markup=keyboard,
        )

        logger.info(
            "Пользователь %d заблокирован лимитом (использовано: %d/%d)",
            user_id,
            searches_used,
            FREE_SEARCHES_LIMIT,
        )
        return None  # Не передаём управление обработчику
