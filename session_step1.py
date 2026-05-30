"""
Шаг 1: Отправка кода подтверждения на телефон.
"""
import asyncio
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

load_dotenv()

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
PHONE = "+13656666523"  # +1 365 666 65 23

async def main():
    print(f"\n📱 Отправляю код на {PHONE}...\n")
    
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    
    # Проверяем, не авторизован ли уже
    if await client.is_user_authorized():
        print("✅ Этот номер уже авторизован!")
        session_str = client.session.save()
        print(f"\n🔑 Строковая сессия:\n{session_str}\n")
        
        # Сразу сохраняем
        env_path = Path(".env")
        env_content = env_path.read_text()
        lines = env_content.split("\n")
        new_lines = []
        found = False
        for line in lines:
            if line.startswith("TELETHON_STRING_SESSION="):
                new_lines.append(f"TELETHON_STRING_SESSION={session_str}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"TELETHON_STRING_SESSION={session_str}")
        env_path.write_text("\n".join(new_lines))
        print("✅ Сессия сохранена в .env")
        await client.disconnect()
        return
    
    # Отправляем код
    try:
        sent_code = await client.send_code_request(PHONE)
        phone_code_hash = sent_code.phone_code_hash
        
        # Сохраняем состояние для шага 2
        state = {
            "phone": PHONE,
            "phone_code_hash": phone_code_hash,
            "session_string": client.session.save()  # пустая строка
        }
        Path("/tmp/telethon_state.json").write_text(json.dumps(state))
        
        print("✅ Код отправлен на ваш телефон!")
        print("📧 Проверьте Telegram или SMS")
        print("\n⏳ Жду код от вас...")
        print("   Пришлите код в формате: 12345")
        print("   Или слово RESEND чтобы отправить код повторно\n")
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        if "PHONE_NUMBER_INVALID" in str(e):
            print("   Номер должен быть в международном формате без пробелов")
        elif "PHONE_NUMBER_BANNED" in str(e):
            print("   Этот номер заблокирован Telegram")
    
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
