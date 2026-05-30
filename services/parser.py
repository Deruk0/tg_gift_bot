"""
Парсер подарков профилей Telegram через Telethon userbot.

Блок валидации (запускается при старте бота) проверяет доступность
метода GetSavedStarGiftsRequest — официальная замена удалённого
getUserStarGifts в новых слоях Telegram API.

=== Критическое обновление (29.05.2026) ===
GetUserStarGiftsRequest удалён из API (Layer 189+).
Вместо него используем GetSavedStarGiftsRequest,
доступный в Telethon ≥ 1.43.
"""
import asyncio
import logging
from typing import Any, Dict, List, Optional

from telethon import TelegramClient
from telethon.errors import (
    FloodWaitError,
    UserPrivacyRestrictedError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.types import (
    Channel,
    PeerChannel,
    PeerChat,
    PeerUser,
    User,
)
from telethon.tl.functions.users import GetFullUserRequest

logger = logging.getLogger(__name__)

# Задержка между запросами к API (избегаем FloodWait)
REQUEST_DELAY: float = 0.5


# ── Блок валидации ─────────────────────────────────────────────────────────────

async def validate_gift_access(client: TelegramClient) -> bool:
    """
    КРИТИЧЕСКИ ВАЖНАЯ ПРОВЕРКА.

    Тестирует доступность метода GetSavedStarGiftsRequest и авторизацию
    userbot-сессии. Вызывается однократно при запуске бота.

    Возвращает True, если всё готово к работе.
    При любой проблеме — логирует детальную подсказку и возвращает False.
    """
    # 1. Проверяем импорт метода
    try:
        from telethon.tl.functions.payments import GetSavedStarGiftsRequest  # noqa: F401

        logger.info("✅  GetSavedStarGiftsRequest успешно импортирован (Telethon %s)", _get_telethon_version())
    except ImportError:
        logger.error(
            "❌  GetSavedStarGiftsRequest НЕДОСТУПЕН.\n"
            "    Обновите Telethon: pip install --upgrade telethon\n"
            "    Текущая версия Telethon: %s\n"
            "    Требуется: Telethon ≥ 1.43",
            _get_telethon_version(),
        )
        return False

    # 2. Проверяем подключение клиента
    if not client.is_connected():
        logger.error(
            "❌  Telethon клиент не подключён.\n"
            "    Убедитесь, что вы вызвали await client.start() перед проверкой."
        )
        return False

    # 3. Проверяем авторизацию userbot-сессии
    try:
        me = await client.get_me()
        if me is None:
            logger.error(
                "❌  Telethon не авторизован.\n"
                "    Запустите: python setup_session.py — для создания сессии."
            )
            return False
        logger.info(
            "✅  Telethon авторизован: @%s (id=%d)",
            me.username or "без username",
            me.id,
        )
    except Exception as exc:
        logger.error(
            "❌  Ошибка авторизации Telethon: %s\n"
            "    Попробуйте удалить файл userbot.session и перезапустить setup_session.py",
            exc,
        )
        return False

    # 4. Тестовый запрос к API — самое важное
    try:
        from telethon.tl.functions.payments import GetSavedStarGiftsRequest

        test_result = await client(
            GetSavedStarGiftsRequest(
                peer="me",
                offset="",
                limit=1,
            )
        )
        logger.info(
            "✅  Тестовый запрос GetSavedStarGiftsRequest выполнен успешно (gifts: %d)",
            len(getattr(test_result, "gifts", [])),
        )
    except Exception as exc:
        logger.error(
            "❌  Тестовый GetSavedStarGiftsRequest провален: %s",
            exc,
        )
        return False

    return True


def _get_telethon_version() -> str:
    """Вспомогательная функция — получить версию установленного Telethon"""
    try:
        import telethon

        return telethon.__version__
    except Exception:
        return "неизвестно"


# ── Разрешение отправителя из Peer ─────────────────────────────────────────────

def _resolve_sender(
    raw_from: Any,
    users_map: Dict[int, Any],
    chats_map: Dict[int, Any],
) -> tuple:
    """
    По Peer-объекту и картам users/chats из ответа API
    определить отправителя подарка.

    Args:
        raw_from:  PeerUser / PeerChannel / PeerChat или int
        users_map: {user_id: User} из ответа SavedStarGifts.users
        chats_map: {chat_id: Chat}   из ответа SavedStarGifts.chats

    Returns:
        (sender_id: int | None, sender_username: str | None, is_anonymous: bool, is_bot: bool)
    """
    # Если from_id отсутствует или None — анонимный отправитель
    if raw_from is None:
        return None, None, True, False

    try:
        if isinstance(raw_from, PeerUser):
            user = users_map.get(raw_from.user_id)
            if user is not None:
                name = user.username or f"id{user.id}"
                is_bot = getattr(user, 'bot', False)
                return user.id, name, False, is_bot
            else:
                return raw_from.user_id, f"id{raw_from.user_id}", False, False

        elif isinstance(raw_from, PeerChannel):
            chat = chats_map.get(raw_from.channel_id)
            name = getattr(chat, "username", None) or getattr(chat, "title", f"chat{raw_from.channel_id}")
            is_bot = getattr(chat, 'bot', False)
            return raw_from.channel_id, name, False, is_bot

        elif isinstance(raw_from, PeerChat):
            chat = chats_map.get(raw_from.chat_id)
            name = getattr(chat, "title", f"chat{raw_from.chat_id}")
            return raw_from.chat_id, name, False, False

        elif isinstance(raw_from, int):
            user = users_map.get(raw_from)
            if user is not None:
                name = user.username or f"id{user.id}"
                is_bot = getattr(user, 'bot', False)
                return user.id, name, False, is_bot
            chat = chats_map.get(raw_from)
            if chat is not None:
                name = getattr(chat, "username", None) or getattr(chat, "title", f"chat{raw_from}")
                is_bot = getattr(chat, 'bot', False)
                return raw_from, name, False, is_bot
            return raw_from, f"id{raw_from}", False, False

    except Exception as exc:
        logger.debug("Ошибка разрешения отправителя из Peer: %s", exc)

    return None, None, True, False


# ── Основная функция парсинга подарков ────────────────────────────────────────

async def get_user_gifts(
    client: TelegramClient,
    username: str,
    include_anonymous: bool = True,
) -> List[Dict[str, Any]]:
    """
    Получить список подарков пользователя через Telethon.

    Использует GetSavedStarGiftsRequest — официальный метод API
    на замену удалённому getUserStarGifts (Layer 189+).

    Args:
        client:            Активный экземпляр TelegramClient
        username:          @username или числовой ID пользователя
        include_anonymous: Включать ли анонимные подарки (без отправителя)

    Returns:
        Список словарей:
        {
            "recipient":       str,           # username получателя
            "sender_username": str | None,    # username отправителя (None = аноним)
            "sender_id":       int | None,    # Telegram ID отправителя
            "anonymous":       bool,          # True если отправитель скрыт
        }
    """
    try:
        from telethon.tl.functions.payments import GetSavedStarGiftsRequest
    except ImportError:
        logger.error("GetSavedStarGiftsRequest недоступен — обновите Telethon (pip install --upgrade telethon)")
        return []

    # Нормализуем username
    clean_username = username.lstrip("@").strip()
    if not clean_username:
        logger.warning("Передан пустой username")
        return []

    # Получаем entity и input_peer пользователя
    try:
        entity = await client.get_entity(clean_username)
        input_peer = await client.get_input_entity(entity)
    except (UsernameInvalidError, UsernameNotOccupiedError):
        logger.warning("Пользователь @%s не найден в Telegram", clean_username)
        return []
    except UserPrivacyRestrictedError:
        logger.warning("Профиль @%s закрыт настройками приватности", clean_username)
        return []
    except ValueError as exc:
        logger.warning("Невалидный идентификатор пользователя %s: %s", clean_username, exc)
        return []
    except Exception as exc:
        logger.error("Ошибка получения entity для @%s: %s", clean_username, exc)
        return []

    # Работаем только с пользователями и каналами
    if not isinstance(entity, (User, Channel)):
        logger.warning("@%s не является пользователем или каналом", clean_username)
        return []

    gifts: List[Dict[str, Any]] = []
    offset: str = ""

    while True:
        # Запрос списка подарков с пагинацией
        try:
            result = await client(
                GetSavedStarGiftsRequest(
                    peer=input_peer,
                    offset=offset,
                    limit=100,
                    exclude_unsaved=False,
                    exclude_saved=False,
                    exclude_unlimited=False,
                    exclude_unique=False,
                    sort_by_value=False,
                    exclude_upgradable=False,
                    exclude_unupgradable=False,
                    peer_color_available=None,
                    exclude_hosted=False,
                )
            )
        except FloodWaitError as exc:
            wait_time = min(exc.seconds, 60)
            logger.warning(
                "FloodWait при запросе подарков @%s: ждём %d с.",
                clean_username,
                wait_time,
            )
            await asyncio.sleep(wait_time)
            continue
        except UserPrivacyRestrictedError:
            logger.warning("Подарки @%s скрыты настройками приватности", clean_username)
            break
        except Exception as exc:
            logger.error(
                "Ошибка GetSavedStarGiftsRequest для @%s: %s",
                clean_username,
                exc,
            )
            break

        logger.info(
            "API вернул %d gifts для @%s на offset=%r",
            len(getattr(result, 'gifts', []) or []),
            clean_username,
            offset,
        )

        # Пустой ответ — конец списка
        if not getattr(result, "gifts", None):
            break

        # Строим карты users и chats из ответа для быстрого разрешения отправителей
        users_map: Dict[int, Any] = {}
        for u in getattr(result, "users", []) or []:
            users_map[u.id] = u

        chats_map: Dict[int, Any] = {}
        for c in getattr(result, "chats", []) or []:
            chats_map[c.id] = c

        for idx, gift_item in enumerate(result.gifts):
            if idx < 10:
                logger.debug(
                    "gift[%d] type=%s from_id=%r name_hidden=%r date=%r",
                    idx,
                    type(gift_item).__name__,
                    getattr(gift_item, 'from_id', None),
                    getattr(gift_item, 'name_hidden', None),
                    getattr(gift_item, 'date', None),
                )

            # --- определяем анонимность ---
            is_name_hidden = getattr(gift_item, "name_hidden", None)
            # name_hidden == True → анонимный отправитель
            is_anonymous = is_name_hidden is True

            # --- определяем отправителя ---
            raw_from = getattr(gift_item, "from_id", None)

            if is_anonymous or raw_from is None:
                if not include_anonymous:
                    continue
                sender_id = None
                sender_username = None
                is_bot = False
            else:
                sender_id, sender_username, _, is_bot = _resolve_sender(raw_from, users_map, chats_map)

            gifts.append(
                {
                    "recipient": clean_username,
                    "sender_username": sender_username,
                    "sender_id": sender_id,
                    "anonymous": is_anonymous,
                    "is_bot": is_bot,
                }
            )

        # Переходим на следующую страницу
        next_offset = getattr(result, "next_offset", None)
        if not next_offset:
            break
        offset = next_offset

        await asyncio.sleep(REQUEST_DELAY)

    logger.info(
        "Получено %d подарков у @%s (анонимных включено: %s)",
        len(gifts),
        clean_username,
        include_anonymous,
    )
    return gifts


async def get_user_bio(client: TelegramClient, username: str) -> Optional[str]:
    """Получить bio (описание) пользователя."""
    try:
        entity = await client.get_entity(username)
        full = await client(GetFullUserRequest(entity))
        about = getattr(full, "full_user", None)
        if about:
            return getattr(about, "about", None) or ""
        return ""
    except Exception:
        return None
