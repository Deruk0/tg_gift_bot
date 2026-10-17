"""Search access: active subscription, free attempts, then paid balance.

allow_search is called only when the user confirms graph construction.
The middleware adapter is retained for compatibility with older callers.
"""
import logging
from datetime import date
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, TelegramObject

from config import FREE_SEARCHES_LIMIT
from database.db import get_or_create_user, reserve_free_search, reserve_paid_search

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
        command = (event.text or "").split(maxsplit=1)
        if not command or command[0].split("@")[0] != "/search":
            return await handler(event, data)

        # Let the handler explain invalid arguments without spending a search.
        from handlers.search import _parse_args

        try:
            usernames, params = _parse_args(event.text)
        except ValueError:
            return await handler(event, data)
        if not usernames or (params["mode"] == "path" and len(usernames) < 2):
            return await handler(event, data)

        if await allow_search(event, event.from_user.id):
            return await handler(event, data)
        return None


async def allow_search(event: Message, user_id: int) -> bool:
    """Reserve quota only when a configured search is confirmed."""
    user = await get_or_create_user(user_id)

    # ── Шаг 1: Проверяем активную подписку ────────────────────────────────
    if user["subscription_until"]:
        try:
            sub_until = date.fromisoformat(user["subscription_until"])
            if sub_until >= date.today():
                # Подписка активна — пропускаем без ограничений
                return True
        except ValueError:
            logger.warning(
                "Некорректный формат даты подписки у пользователя %d: %s",
                user_id,
                user["subscription_until"],
            )

    # ── Шаг 2: Проверяем бесплатные поиски ────────────────────────────────
    searches_used: int = user["free_searches_used"]

    reserved_count = await reserve_free_search(user_id, FREE_SEARCHES_LIMIT)
    if reserved_count is not None:
        remaining = FREE_SEARCHES_LIMIT - reserved_count
        user["free_searches_used"] = reserved_count

        # Предупреждаем когда лимит на исходе
        if remaining == 0:
            await event.answer(
                "⚠️ Это ваш <b>последний</b> бесплатный поиск.\n"
                "Купить попытки или подписку: /subscribe.",
                parse_mode="HTML",
            )
        elif remaining == 1:
            await event.answer(
                f"⚠️ Осталось бесплатных поисков: <b>{remaining}</b>.\n"
                "Купить попытки или подписку: /subscribe.",
                parse_mode="HTML",
            )

        return True

    paid_remaining = await reserve_paid_search(user_id)
    if paid_remaining is not None:
        if paid_remaining <= 1:
            await event.answer(
                f"🎟 Купленных попыток осталось: <b>{paid_remaining}</b>.\n"
                "Пополнить баланс: /subscribe.", parse_mode="HTML",
            )
        return True

    # ── Шаг 3: Попытки закончились — предлагаем покупку ───────────────────
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="🎟 Купить попытки или подписку",
                    callback_data="show_subscription",
                )
            ]
        ]
    )

    await event.answer(
        "🎟 Попытки закончились.\n\n"
        "Купи попытки без срока действия или подписку с неограниченным числом поисков:",
        parse_mode="HTML",
        reply_markup=keyboard,
    )

    logger.info(
        "Пользователь %d заблокирован лимитом (использовано: %d/%d)",
        user_id,
        searches_used,
        FREE_SEARCHES_LIMIT,
    )
    return False
