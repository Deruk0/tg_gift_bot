"""
Скрипт первоначальной настройки Telethon userbot-сессии.

Запустите ОДИН РАЗ перед стартом бота:
    python setup_session.py

После авторизации файл сессии (userbot.session) будет создан в текущей
папке и использоваться при каждом запуске main.py.
"""
import asyncio
import sys

from dotenv import load_dotenv
import os

load_dotenv()

# Загружаем параметры из .env
API_ID = os.getenv("API_ID")
API_HASH = os.getenv("API_HASH")
SESSION_NAME = os.getenv("TELETHON_SESSION", "userbot")

if not API_ID or not API_HASH:
    print("❌ Ошибка: заполните API_ID и API_HASH в файле .env")
    print("   Получить на: https://my.telegram.org/apps")
    sys.exit(1)


async def setup() -> None:
    from telethon import TelegramClient

    print("=" * 50)
    print("  Настройка Telethon userbot-сессии")
    print("=" * 50)
    print(f"  API_ID    : {API_ID}")
    print(f"  API_HASH  : {API_HASH[:8]}...")
    print(f"  Файл сессии: {SESSION_NAME}.session")
    print("=" * 50)
    print()

    client = TelegramClient(SESSION_NAME, int(API_ID), API_HASH)

    # start() интерактивно запросит номер телефона и код подтверждения
    await client.start()

    me = await client.get_me()
    print()
    print("=" * 50)
    print(f"  ✅ Авторизован как: {me.first_name} ({me.username or 'нет username'})")
    print(f"  📱 Telegram ID: {me.id}")
    print(f"  💾 Сессия сохранена: {SESSION_NAME}.session")
    print("=" * 50)
    print()
    print("Теперь можно запускать бота: python main.py")

    await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup())
