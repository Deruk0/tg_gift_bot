"""
Обработчики команд /start и /help.
Приветствие, описание бота, краткая и подробная справка.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from database.db import get_or_create_user
from config import GIFTGRAPH_WEB_URL
from miniapp import graph_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Приветственное сообщение с кратким описанием функциональности"""
    # Регистрируем пользователя если он новый
    await get_or_create_user(message.from_user.id)

    name = message.from_user.first_name or "друг"

    await message.answer(
        f"👋 Привет, <b>{name}</b>!\n\n"
        "🕸 <b>GiftGraph Bot</b> — визуализация социальных связей через подарки Telegram.\n\n"
        "Бот анализирует подарки на профилях пользователей, выявляет отправителей "
        "и строит граф социальных связей в стиле <b>Obsidian</b>.\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 <b>Основные команды:</b>\n"
        "• /search @username — граф связей пользователя\n"
        "• /search @user1,@user2 --mode path — путь между пользователями\n\n"
        "⚙️ <b>Параметры /search:</b>\n"
        "• <code>--depth [1-10]</code> — глубина обхода (по умолчанию: 2)\n"
        "• <code>--mode tree</code> — полный граф от одного пользователя\n"
        "• <code>--mode path</code> — кратчайший путь между пользователями\n"
        "• <code>--gifts all</code> — включая анонимные подарки\n"
        "• <code>--gifts public</code> — только публичные отправители\n"
        "• <code>--no-bots</code> — исключить ботов из графа\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Лимиты:</b>\n"
        "• Бесплатно: 3 поиска навсегда\n"
        "• Подписка: /subscribe\n"
        "• Промокод: /promo КОД\n\n"
        "ℹ️ Полная справка: /help",
        parse_mode="HTML",
        reply_markup=graph_keyboard(GIFTGRAPH_WEB_URL, message.chat.type == "private"),
    )
    logger.info("Пользователь %d запустил бота", message.from_user.id)


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    """Open the graph archive inside Telegram in private chats."""
    await message.answer(
        "🕸 GiftGraph — открой архив и выбери граф.\n"
        "Для построения нового графа используй /search @username в чате бота.",
        reply_markup=graph_keyboard(GIFTGRAPH_WEB_URL, message.chat.type == "private"),
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Подробная справка по всем командам и параметрам"""
    await message.answer(
        "📖 <b>Подробная справка GiftGraph Bot</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "🔍 <b>Команда /search</b>\n"
        "<code>/search @username [параметры]</code>\n\n"
        "<b>Параметры:</b>\n\n"
        "📏 <code>--depth N</code> — глубина обхода (от 1 до 10, по умолчанию 2)\n"
        "   Чем больше — тем обширнее граф и дольше обработка.\n"
        "   Реальная глубина ограничена 120 узлами на граф.\n\n"
        "🌲 <code>--mode tree</code> — полный граф связей от одного пользователя\n"
        "   Пример: <code>/search @durov --mode tree --depth 3</code>\n\n"
        "🔗 <code>--mode path</code> — поиск пути между двумя+ пользователями\n"
        "   Пользователи указываются через запятую.\n"
        "   Пример: <code>/search @user1,@user2 --mode path</code>\n\n"
        "🎁 <code>--gifts all</code> — все подарки, включая анонимные\n"
        "   Анонимные отображаются как узел «?»\n\n"
        "🎁 <code>--gifts public</code> — только подарки с видимым отправителем\n\n"
        "🤖 <code>--no-bots</code> — исключить Telegram-ботов из графа\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 <b>Примеры:</b>\n"
        "<code>/search @telegram</code>\n"
        "<code>/search @user1 --depth 4 --gifts all</code>\n"
        "<code>/search @user1,@user2 --mode path --depth 3</code>\n"
        "<code>/search @user1 --mode tree --depth 2 --gifts public</code>\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "⚙️ <b>Технические ограничения:</b>\n"
        "• Максимум 120 узлов на один граф\n"
        "• Работает только с публичными профилями и открытыми подарками\n"
        "• Время построения: от 5 сек до нескольких минут (зависит от глубины)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💳 <b>Подписка и промокоды:</b>\n"
        "/subscribe — планы и оплата через Telegram Stars\n"
        "/promo КОД — активировать промокод\n\n"
        "📊 <b>Бесплатно:</b> 3 поиска навсегда.",
        parse_mode="HTML",
    )
