# 🕸 GiftGraph Bot

Telegram-бот для визуализации социальных связей через подарки профилей. Строит граф в стиле Obsidian: тёмный фон, фиолетовые узлы, анимированные рёбра.

## Что умеет

- `/search @username` — построить граф связей
- `/search @u1,@u2 --mode path` — найти путь между пользователями
- `/subscribe` — подписка через Telegram Stars
- `/promo КОД` — активировать промокод
- `/help` — полная справка

## Быстрый старт

### 1) Установка зависимостей

```bash
pip install -r requirements.txt
```

Для PNG-рендеринга нужен Chrome или Chromium:

```bash
# Ubuntu/Debian
apt-get install -y google-chrome-stable
# или
apt-get install -y chromium-browser
```

### 2) Настройка `.env`

```env
BOT_TOKEN=7123456789:AAF...
API_ID=12345678
API_HASH=abcdef1234567890abcdef
TELETHON_SESSION=userbot
PROMO_CODES={"LAUNCH2024": 30, "YEAR2024": 365}
```

`API_ID` и `API_HASH` берутся из https://my.telegram.org/apps.

### 3) Создание Telethon-сессии

```bash
python setup_session.py
```

Введите номер телефона и код из Telegram. После этого появится файл `userbot.session`.

### 4) Запуск

```bash
python main.py
```

## Параметры поиска

```bash
/search @username [--depth 1-10] [--mode tree|path] [--gifts all|public]
```

- `--depth 2` — глубина BFS по умолчанию
- `--mode tree` — полный граф от одного пользователя
- `--mode path` — кратчайший путь между двумя пользователями
- `--gifts public` — только публичные отправители
- `--gifts all` — включая анонимные подарки

## Структура проекта

```text
bot/
├── main.py
├── config.py
├── setup_session.py
├── database/
├── handlers/
├── services/
└── middlewares/
```

## Данные и лимиты

- SQLite база: `giftgraph.db`
- Бесплатно: 3 поиска на аккаунт навсегда
- Подписка: Telegram Stars
- Промокоды: задаются через `PROMO_CODES`
- Максимум: 120 узлов на один граф

## Визуализация

- фон: `#0d1117`
- стартовый узел: белый
- обычный узел: фиолетовый
- узел на пути: янтарный
- анонимный узел: серый
- рёбра: тёмно-серые

## Требования

- Python 3.11+
- Google Chrome или Chromium
- Активный Telegram аккаунт для userbot-сессии
- Telethon ≥ 1.29
