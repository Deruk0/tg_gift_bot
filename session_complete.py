"""
Завершение авторизации с кодом 30525.
"""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError, PhoneCodeExpiredError

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

CODE = "30525"

async def main():
    print("=" * 60)
    print("  Завершение авторизации")
    print("=" * 60)
    
    # Загружаем сохранённое состояние
    state_path = Path("/tmp/telethon_state.json")
    if not state_path.exists():
        print("❌ Состояние не найдено. Сначала запусти session_ru.py")
        return
    
    state = json.loads(state_path.read_text())
    phone = state["phone"]
    phone_code_hash = state["phone_code_hash"]
    
    print(f"📞 Номер: {phone}")
    print(f"🔑 Код: {CODE}")
    
    # Восстанавливаем клиент
    client = TelegramClient(StringSession(state["session_string"]), API_ID, API_HASH)
    
    try:
        await client.connect()
        print("✅ Подключено к Telegram")
        
        # Пробуем авторизоваться с кодом
        print(f"\n🔐 Проверяю код...")
        
        try:
            await client.sign_in(phone, CODE, phone_code_hash=phone_code_hash)
        except SessionPasswordNeededError:
            # Нужен пароль 2FA
            print("\n⚠️ На аккаунте включена двухфакторная авторизация (2FA)!")
            print("   Введи пароль облачного пароль Telegram:")
            await client.disconnect()
            return
        except PhoneCodeInvalidError:
            print("\n❌ Неверный код!")
            await client.disconnect()
            return
        except PhoneCodeExpiredError:
            print("\n❌ Код истёк. Нужно запросить новый.")
            await client.disconnect()
            return
        
        # Успешная авторизация
        me = await client.get_me()
        print(f"\n✅ Авторизован!")
        print(f"   Имя: {me.first_name}")
        print(f"   Username: @{me.username or 'не указан'}")
        print(f"   Телефон: {me.phone}")
        
        # Получаем строковую сессию
        session_str = client.session.save()
        
        print(f"\n📋 Строковая сессия (сохрани её):")
        print("-" * 60)
        print(session_str)
        print("-" * 60)
        
        # Сохраняем в .env
        env_path = Path(".env")
        env_content = env_path.read_text() if env_path.exists() else ""
        
        # Обновляем или добавляем TELETHON_STRING_SESSION
        lines = env_content.split("\n")
        lines = [l for l in lines if not l.startswith("TELETHON_STRING_SESSION=")]
        lines.append(f"TELETHON_STRING_SESSION={session_str}")
        env_content = "\n".join(lines)
        env_path.write_text(env_content)
        
        print("\n✅ Сессия сохранена в .env")
        print("✅ Бот готов к работе!")
        
        # Чистим временное состояние
        state_path.unlink()
        
        await client.disconnect()
        
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
