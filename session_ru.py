"""
Отправка кода на российский номер +7 995 880 43 89.
"""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, PhoneNumberInvalidError, PhoneNumberBannedError

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

PHONE = "+79958804389"  # +7 995 880 43 89

async def main():
    print("=" * 60)
    print(f"  Отправка кода на номер: {PHONE}")
    print("=" * 60)
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    
    try:
        await client.connect()
        print("✅ Подключено к Telegram")
        
        # Проверяем, не авторизован ли уже
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"\n✅ Уже авторизован как: {me.first_name} (@{me.username or 'no username'})")
            session_str = client.session.save()
            print(f"\n📋 Строковая сессия:")
            print(session_str)
            
            # Сохраняем в .env
            env_path = Path(".env")
            env_content = env_path.read_text() if env_path.exists() else ""
            
            # Добавляем TELETHON_STRING_SESSION
            if "TELETHON_STRING_SESSION=" in env_content:
                lines = env_content.split("\n")
                lines = [l for l in lines if not l.startswith("TELETHON_STRING_SESSION=")]
                env_content = "\n".join(lines)
            
            env_content += f"\nTELETHON_STRING_SESSION={session_str}\n"
            env_path.write_text(env_content)
            print("\n✅ Сессия сохранена в .env")
            
            await client.disconnect()
            return
        
        # Отправляем код
        print(f"\n📱 Отправляю код на {PHONE}...")
        sent_code = await client.send_code_request(PHONE)
        
        print(f"\n✅ Код отправлен!")
        print(f"   Phone code hash: {sent_code.phone_code_hash[:20]}...")
        
        # Сохраняем состояние
        state = {
            "phone": PHONE,
            "phone_code_hash": sent_code.phone_code_hash,
            "session_string": client.session.save()
        }
        Path("/tmp/telethon_state.json").write_text(json.dumps(state))
        
        print("\n" + "=" * 60)
        print("📧 Код должен прийти в:")
        print("   1. Приложение Telegram (на других устройствах)")
        print("   2. SMS на номер +7 995 880 43 89")
        print("=" * 60)
        print("\n⏳ Жду код от вас...")
        print("   Пришли код цифрами (например: 12345)")
        
        await client.disconnect()
        
    except FloodWaitError as e:
        print(f"\n⏳ Слишком много попыток!")
        print(f"   Нужно подождать {e.seconds} секунд ({e.seconds // 60} минут)")
        await client.disconnect()
    except PhoneNumberInvalidError:
        print(f"\n❌ Номер неверного формата")
        await client.disconnect()
    except PhoneNumberBannedError:
        print(f"\n❌ Этот номер заблокирован Telegram")
        await client.disconnect()
    except Exception as e:
        print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
        try:
            await client.disconnect()
        except:
            pass

if __name__ == "__main__":
    asyncio.run(main())
