"""
Генератор строковой Telethon-сессии (StringSession).

Запуск:
    python gen_session.py

Скрипт попросит номер телефона аккаунта-userbot, код из Telegram и,
при необходимости, пароль двухфакторной аутентификации. В конце выведет
строку сессии — её нужно вставить в .env в переменную TELETHON_STRING_SESSION.

ВАЖНО: используйте обычный пользовательский аккаунт (не бота). Именно через
него бот получает доступ к API подарков Telegram.
"""
import os

from dotenv import load_dotenv
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]


def main() -> None:
    print("=== Генерация строковой Telethon-сессии ===")
    with TelegramClient(StringSession(), API_ID, API_HASH) as client:
        session_str = client.session.save()
        me = client.get_me()
        print("\nУспешно авторизован как:", getattr(me, "username", None) or me.first_name)
        print("\n--- СКОПИРУЙТЕ СТРОКУ НИЖЕ В .env (TELETHON_STRING_SESSION=...) ---\n")
        print(session_str)
        print("\n------------------------------------------------------------------")


if __name__ == "__main__":
    main()
