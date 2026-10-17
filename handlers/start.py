"""
Обработчики команд /start и /help.
Приветствие, описание бота, краткая и подробная справка.
"""
import logging

from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from handlers.settings import open_home
from aiogram.types import Message

from database.db import get_or_create_user
from config import GIFTGRAPH_WEB_URL, FREE_SEARCHES_LIMIT, MAX_NODES_PER_GRAPH
from miniapp import graph_keyboard

logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    """Приветственное сообщение с кратким описанием функциональности"""
    # Регистрируем пользователя если он новый
    await get_or_create_user(message.from_user.id)

    await open_home(message, state)
    logger.info("Пользователь %d запустил бота", message.from_user.id)


@router.message(Command("app"))
async def cmd_app(message: Message) -> None:
    """Open the graph archive inside Telegram in private chats."""
    await message.answer(
        "🕸 GiftGraph — открой архив и выбери граф.\n"
        "Для нового графа отправь /start и нажми «Построить граф».",
        reply_markup=graph_keyboard(GIFTGRAPH_WEB_URL, message.chat.type == "private"),
    )


HELP_TEXT = (
    "📖 <b>GiftGraph: граф связей через подарки</b>\n\n"
    "Нажми <b>«Построить граф»</b> в /start, выбери тип и параметры, затем запусти построение.\n\n"
    "🌲 <b>Дерево</b> — связи вокруг одного пользователя. Ник: <code>@username</code>.\n"
    "🔗 <b>Цепь</b> — кратчайший путь между двумя пользователями. Ники через пробел: "
    "<code>@user1 @user2</code>. Можно без @.\n\n"
    "📏 <b>Что такое глубина</b>\n"
    "Это число уровней, на которых бот изучает подарки.\n"
    "<b>1</b> — кто отправлял подарки указанному пользователю.\n"
    "<b>2</b> — ещё и кто отправлял подарки этим отправителям.\n"
    "<b>3</b> — ещё один уровень связей, и так далее.\n"
    "В режиме цепи бот изучает окружение обоих пользователей до выбранной глубины "
    "и ищет путь в найденных связях. Это глубина поиска, а не длина готовой цепи.\n"
    "Начни с 2. Большая глубина расширяет поиск, но занимает больше времени.\n\n"
    "🎁 <b>Публичные подарки</b> — с видимым отправителем. <b>Все</b> — также анонимные, "
    "обозначенные «?». Анонимные подарки одному получателю объединяются: «? ×7» означает семь подарков. "
    "Это число подарков, а не разных отправителей.\n"
    "🤖 <b>Боты</b> — учитывать или исключить ботов среди отправителей.\n\n"
    f"Бот анализирует доступные подарки публичных профилей, до {MAX_NODES_PER_GRAPH} узлов. "
    "В цепи также отображается до 8 соседей на звено. Построение может занять несколько минут.\n\n"
    "🎟 <b>Попытки и подписка</b>\n"
    f"Бесплатно: {FREE_SEARCHES_LIMIT} попытки на аккаунт. Можно купить дополнительные без срока действия "
    "или подписку с неограниченными поисками: /subscribe.\n"
    "Одна попытка — один запуск построения. Настройка не расходует попытки. "
    "При активной подписке купленные попытки сохраняются.\n\n"
    "/app — архив графов · /promo КОД — промокод · /paysupport — помощь с оплатой"
)


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(HELP_TEXT, parse_mode="HTML")
