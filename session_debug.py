"""
Проверка номера и повторная отправка кода с разными опциями.
"""
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import FloodWaitError, PhoneNumberInvalidError, PhoneNumberBannedError

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]

# Номер в разных форматах для теста
PHONE_FORMATS = [
    "+13656666523",   # +1 365 666 65 23 (стандартный)
    "13656666523",    # без плюса
]

async def try_send_code(client, phone):
    """Попытка отправить код с детальной информацией."""
    print(f"\n🔄 Пробую номер: {phone}")
    
    try:
        # Сначала проверяем, не авторизован ли уже
        if await client.is_user_authorized():
            me = await client.get_me()
            print(f"✅ Уже авторизован как: {me.first_name} (@{me.username or 'no username'})")
            return True, None, None
        
        # Отправляем код
        sent_code = await client.send_code_request(phone)
        print(f"✅ Код отправлен! Hash: {sent_code.phone_code_hash[:20]}...")
        return True, sent_code.phone_code_hash, client.session.save()
        
    except FloodWaitError as e:
        print(f"⏳ FloodWait: нужно подождать {e.seconds} секунд")
        return False, None, None
    except PhoneNumberInvalidError:
        print(f"❌ Номер неверного формата")
        return False, None, None
    except PhoneNumberBannedError:
        print(f"❌ Номер заблокирован Telegram")
        return False, None, None
    except Exception as e:
        print(f"❌ Ошибка: {type(e).__name__}: {e}")
        return False, None, None

async def main():
    print("=" * 60)
    print("  Проверка номера и отправка кода")
    print("=" * 60)
    
    for phone in PHONE_FORMATS:
        print(f"\n{'='*60}")
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        
        try:
            await client.connect()
            print("✅ Подключено к Telegram")
            
            success, code_hash, session_str = await try_send_code(client, phone)
            
            if success and code_hash:
                # Сохраняем состояние
                import json
                state = {
                    "phone": phone,
                    "phone_code_hash": code_hash,
                    "session_string": session_str or ""
                }
                Path("/tmp/telethon_state.json").write_text(json.dumps(state))
                print(f"\n📱 Код отправлен на номер: {phone}")
                print("📧 Проверьте:")
                print("   - Приложение Telegram на других устройствах")
                print("   - SMS на этот номер")
                print("   - Звонок (Telegram может позвонить)")
                print("\n⏳ Жду код от вас...")
                await client.disconnect()
                return
            
            await client.disconnect()
            
        except Exception as e:
            print(f"❌ Ошибка подключения: {e}")
            try:
                await client.disconnect()
            except:
                pass
    
    print("\n" + "=" * 60)
    print("❌ Не удалось отправить код ни на один из форматов номера")
    print("=" * 60)
    print("\nВозможные причины:")
    print("1. Номер указан неверно")
    print("2. Telegram заблокировал этот номер")
    print("3. Слишком много попыток (нужно подождать)")
    print("\n💡 Попробуй проверить номер еще раз:")
    print("   Код страны: 1 (США/Канада)")
    print("   Полный номер: +1 365 666 65 23")
    print("   В формате Telegram: +13656666523")

if __name__ == "__main__":
    asyncio.run(main())
