"""
Точка входа GiftGraph Bot.

Порядок запуска:
  1. Настройка логирования
  2. Инициализация базы данных
  3. Подключение Telethon userbot
  4. Валидация API подарков
  5. Запуск aiogram polling
"""
import asyncio
import logging
import sys
from urllib.parse import unquote, urlparse

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from telethon import TelegramClient
from telethon.sessions import StringSession

import config
from database.db import init_db
from handlers import search, start, subscription
from middlewares.limits import LimitsMiddleware
from services.parser import validate_gift_access


# ── Настройка логирования ──────────────────────────────────────────────────────

def _setup_logging() -> None:
    """Настраиваем логирование: stdout + файл"""
    fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    date_fmt = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=date_fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("giftgraph.log", encoding="utf-8"),
        ],
    )

    # Уменьшаем шум от сторонних библиотек
    logging.getLogger("telethon").setLevel(logging.WARNING)
    logging.getLogger("aiogram").setLevel(logging.INFO)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("WDM").setLevel(logging.WARNING)


logger = logging.getLogger(__name__)
BUILD_TAG = "v2026-05-29-tree-ui"


def _proxy_log_label(proxy_url: str) -> str:
    parsed = urlparse(proxy_url)
    host = parsed.hostname or "?"
    port = parsed.port or "?"
    return f"{parsed.scheme}://{host}:{port}"


def _telethon_proxy_from_url(proxy_url: str):
    if not proxy_url:
        return None

    parsed = urlparse(proxy_url)
    scheme = parsed.scheme.lower()
    if scheme not in {"socks4", "socks5", "socks5h", "http", "https"}:
        raise ValueError("TELEGRAM_PROXY must use socks4, socks5, socks5h, http, or https")
    if not parsed.hostname or not parsed.port:
        raise ValueError("TELEGRAM_PROXY must include host and port")

    try:
        import socks
    except ImportError as exc:
        raise RuntimeError("Install PySocks to use TELEGRAM_PROXY") from exc

    proxy_type = {
        "socks4": socks.SOCKS4,
        "socks5": socks.SOCKS5,
        "socks5h": socks.SOCKS5,
        "http": socks.HTTP,
        "https": socks.HTTP,
    }[scheme]
    username = unquote(parsed.username) if parsed.username else None
    password = unquote(parsed.password) if parsed.password else None
    rdns = scheme in {"socks5", "socks5h"}

    return (proxy_type, parsed.hostname, parsed.port, rdns, username, password)


# ── Жизненный цикл бота ────────────────────────────────────────────────────────

async def _start_telethon() -> TelegramClient:
    """
    Инициализация и подключение Telethon userbot (неинтерактивно).

    Использует строковую сессию (TELETHON_STRING_SESSION), если она задана,
    иначе — файловую сессию по имени TELETHON_SESSION. При отсутствии валидной
    авторизации не запрашивает телефон/код (чтобы сервис не зависал), а выводит
    понятную инструкцию и завершает работу.
    """
    if config.TELETHON_STRING_SESSION:
        session = StringSession(config.TELETHON_STRING_SESSION)
        logger.info("Подключаем Telethon userbot (строковая сессия)...")
    else:
        session = config.TELETHON_SESSION
        logger.info("Подключаем Telethon userbot (файл-сессия: %s)...", config.TELETHON_SESSION)

    proxy = _telethon_proxy_from_url(config.TELEGRAM_PROXY)
    if proxy:
        logger.info("Telethon proxy: %s", _proxy_log_label(config.TELEGRAM_PROXY))

    client = TelegramClient(session, config.API_ID, config.API_HASH, proxy=proxy)

    try:
        await client.connect()
    except Exception as exc:
        logger.critical("❌ Не удалось подключиться к Telegram: %s", exc)
        sys.exit(1)

    if not await client.is_user_authorized():
        logger.critical(
            "❌ Userbot-сессия отсутствует или недействительна.\n"
            "   Создайте сессию командой: python gen_session.py\n"
            "   и вставьте полученную строку в TELETHON_STRING_SESSION (.env)."
        )
        await client.disconnect()
        sys.exit(1)

    me = await client.get_me()
    logger.info("Telethon авторизован как: %s (id=%s)", getattr(me, "username", None) or me.first_name, me.id)
    return client


async def main() -> None:
    _setup_logging()
    logger.info("╔═══════════════════════════════╗")
    logger.info("║   GiftGraph Bot — запуск      ║")
    logger.info("║   build: %s", BUILD_TAG)
    logger.info("╚═══════════════════════════════╝")

    # ── Инициализация базы данных ──────────────────────────────────────────────
    await init_db()

    # ── Подключение Telethon userbot ───────────────────────────────────────────
    telethon_client = await _start_telethon()

    # ── Валидация API подарков (критический шаг) ───────────────────────────────
    gift_ok = await validate_gift_access(telethon_client)
    if not gift_ok:
        logger.critical(
            "❌ API подарков недоступен — бот не может выполнять основную функцию.\n"
            "   Проверьте версию Telethon: pip install --upgrade telethon"
        )
        # Продолжаем запуск: бот будет работать, но /search выдаст понятную ошибку

    # ── Создание бота и диспетчера ─────────────────────────────────────────────
    bot_session = AiohttpSession(proxy=config.TELEGRAM_PROXY or None)
    if config.TELEGRAM_PROXY:
        logger.info("Bot API proxy: %s", _proxy_log_label(config.TELEGRAM_PROXY))

    bot = Bot(
        token=config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=bot_session,
    )
    dp = Dispatcher()

    # ── Регистрация команд (меню при вводе / в чате Telegram) ─────────────────
    from aiogram.types import BotCommand, BotCommandScopeDefault

    commands = [
        BotCommand(command="start", description="👋 Начать работу с ботом"),
        BotCommand(command="search", description="🕸 Построить граф связей (tree/path)"),
        BotCommand(command="subscribe", description="⭐ Купить/проверить подписку"),
        BotCommand(command="promo", description="🎁 Активировать промокод"),
        BotCommand(command="help", description="📖 Подробная справка по командам"),
        BotCommand(command="admin", description="⚙️ Админ-панель (только для админа)"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())
    logger.info("Команды бота зарегистрированы в BotFather")

    # ── Регистрация middleware ─────────────────────────────────────────────────
    # LimitsMiddleware применяется ТОЛЬКО к сообщениям (Message events)
    dp.message.middleware(LimitsMiddleware())

    # ── Регистрация роутеров ───────────────────────────────────────────────────
    dp.include_router(start.router)
    dp.include_router(search.router)
    dp.include_router(subscription.router)

    # ── Запуск polling ─────────────────────────────────────────────────────────
    logger.info("Бот запущен. Ожидаем сообщений...")

    try:
        # Передаём Telethon клиент через workflow_data — доступен в любом хендлере
        await dp.start_polling(
            bot,
            allowed_updates=dp.resolve_used_update_types(),
            telethon_client=telethon_client,
            drop_pending_updates=True,
        )
    finally:
        logger.info("Бот остановлен. Закрываем соединения...")
        await bot.session.close()
        await telethon_client.disconnect()
        logger.info("Все соединения закрыты.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (Ctrl+C)")
    except Exception as exc:
        logger.critical("Критическая ошибка при запуске: %s", exc, exc_info=True)
        sys.exit(1)
