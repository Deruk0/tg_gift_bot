"""Step-by-step graph configuration inside Telegram messages."""
import re
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import GIFTGRAPH_WEB_URL
from miniapp import graph_keyboard

router = Router()
STEPS = ('type', 'users', 'depth', 'gifts', 'bots', 'review')
DEFAULTS = {'depth': 2, 'mode': 'tree', 'gifts': 'public', 'no_bots': False}


class SearchSettings(StatesGroup):
    home = State()
    configuring = State()
    usernames = State()


def valid_users(data: dict) -> bool:
    required = 1 if data['mode'] == 'tree' else 2
    return len(data['users']) == required and len({u.lower() for u in data['users']}) == required


def parse_usernames(text: str, mode: str) -> list[str]:
    users = [part.lstrip('@') for part in text.split()]
    required = 1 if mode == 'tree' else 2
    if len(users) != required:
        raise ValueError('Отправь один ник: @username.' if required == 1 else
                         'Отправь два ника через пробел: @user1 @user2.')
    if any(not re.fullmatch(r'[A-Za-z0-9_]+', user) for user in users):
        raise ValueError('Укажи ники без ссылок и знаков препинания. Пример: ' +
                         ('@username' if required == 1 else '@user1 @user2'))
    if len({u.lower() for u in users}) != required:
        raise ValueError('Для цепи нужны два разных пользователя: @user1 @user2.')
    return users


def settings_text(data: dict) -> str:
    step = data['step']
    if step == 'home':
        return ('🕸 <b>GiftGraph</b>\n\n'
                'Построй граф связей через подарки Telegram или открой сохранённые графы.\n\n'
                'Нажми «Построить граф», чтобы начать.\n'
                'Бесплатно: 3 попытки. Купить попытки или подписку: /subscribe · Промокод: /promo КОД')
    if step == 'type':
        return ('<b>1/5 · Тип графа</b>\n\n'
                '🌲 <b>Дерево</b> — связи вокруг одного пользователя.\n'
                '🔗 <b>Цепь</b> — кратчайший путь между двумя пользователями.\n\n'
                'Выбери, какой граф построить.')
    if step == 'users':
        prompt = ('Отправь ник пользователя.\nПример: <code>@durov</code>' if data['mode'] == 'tree' else
                  'Отправь два разных ника <b>через пробел</b>.\nПример: <code>@user1 @user2</code>')
        selected = '\n\nСейчас: ' + ' '.join('@' + escape(u) for u in data['users']) if valid_users(data) else ''
        return '<b>2/5 · Пользователи</b>\n\n' + prompt + '\nМожно вводить ники без @.' + selected
    if step == 'depth':
        explanation = ('Сколько уровней связей раскрыть от пользователя.' if data['mode'] == 'tree' else
                       'Насколько глубоко искать цепь между пользователями.')
        return (f'<b>3/5 · Глубина</b>\n\n{explanation}\n'
                'Большая глубина увеличивает время поиска. Рекомендуем начать с 2.\n\n'
                f'Выбрано: <b>{data["depth"]}</b>. Нажми число, чтобы продолжить.')
    if step == 'gifts':
        return ('<b>4/5 · Подарки</b>\n\n'
                '🎁 <b>Публичные</b> — только подарки с видимым отправителем.\n'
                '🎁 <b>Все</b> — также анонимные подарки; их отправитель отображается как «?».\n\n'
                'Выбери, какие подарки учитывать.')
    if step == 'bots':
        return ('<b>5/5 · Боты</b>\n\n'
                'Учитывать Telegram-ботов среди отправителей подарков?')
    return ('🕸 <b>Всё готово к построению</b>\n\n'
            f'Тип: <b>{"Дерево" if data["mode"] == "tree" else "Цепь"}</b>\n'
            f'Пользователи: <b>{" ".join("@" + escape(u) for u in data["users"])}</b>\n'
            f'Глубина: <b>{data["depth"]}</b>\n'
            f'Подарки: <b>{"публичные" if data["gifts"] == "public" else "все"}</b>\n'
            f'Боты: <b>{"исключены" if data["no_bots"] else "включены"}</b>\n\n'
            'Проверь параметры и нажми «Начать построение».\n'
            'Одна попытка расходуется только при запуске. При подписке — без ограничений.')


def settings_keyboard(data: dict, private: bool) -> InlineKeyboardMarkup:
    def button(text, action):
        return InlineKeyboardButton(text=text, callback_data=f'settings:{data["owner"]}:{action}')
    step = data['step']
    if step == 'home':
        return InlineKeyboardMarkup(inline_keyboard=[
            [button('🕸 Построить граф', 'begin')],
            *graph_keyboard(GIFTGRAPH_WEB_URL, private, text='🗂 Архив графов').inline_keyboard,
            [button('📖 Как пользоваться', 'help'),
             InlineKeyboardButton(text='🎟 Попытки и подписка', callback_data='show_subscription')],
        ])
    rows = []
    if step == 'type':
        rows = [[button('🌲 Дерево', 'tree'), button('🔗 Цепь', 'path')]]
    elif step == 'users':
        if valid_users(data):
            rows = [[button('Далее →', 'next')]]
    elif step == 'depth':
        rows = [[button(('✓ ' if data['depth'] == n else '') + str(n), f'depth{n}')
                 for n in range(first, first + 5)] for first in (1, 6)]
    elif step == 'gifts':
        rows = [[button('🎁 Публичные', 'public'), button('🎁 Все', 'all')]]
    elif step == 'bots':
        rows = [[button('🤖 Учитывать ботов', 'include'), button('🚫 Исключить ботов', 'exclude')]]
    elif step == 'review':
        rows = [[button('🚀 Начать построение', 'run')], [button('⚙️ Изменить параметры', 'edit')]]
    rows.append([button('← Назад', 'back'), button('✖ Отмена', 'cancel')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def save_step(state: FSMContext, data: dict) -> None:
    await state.set_data(data)
    await state.set_state(SearchSettings.home if data['step'] == 'home' else
                          SearchSettings.usernames if data['step'] == 'users' else SearchSettings.configuring)


async def show_step(message: Message, state: FSMContext, data: dict) -> None:
    await save_step(state, data)
    await message.edit_text(settings_text(data), parse_mode='HTML',
                            reply_markup=settings_keyboard(data, message.chat.type == 'private'))


async def open_home(message: Message, state: FSMContext) -> None:
    await open_settings(message, state, step='home')


async def open_settings(message: Message, state: FSMContext, users=None, params=None, step=None, owner_id=None) -> None:
    await state.clear()
    data = dict(params or DEFAULTS)
    data.update(users=users or [], owner=owner_id if owner_id is not None else message.from_user.id,
                step=step or ('review' if users else 'type'))
    panel = await message.answer(settings_text(data), parse_mode='HTML',
                                 reply_markup=settings_keyboard(data, message.chat.type == 'private'))
    await save_step(state, {**data, 'panel_id': panel.message_id})


@router.callback_query(F.data.startswith('new_graph:'))
async def new_graph_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data != f'new_graph:{callback.from_user.id}':
        await callback.answer('Построй свой граф через /start.', show_alert=True)
        return
    await callback.answer()
    if callback.message:
        await open_settings(callback.message, state, owner_id=callback.from_user.id)


@router.callback_query(F.data.startswith('settings:'))
async def settings_callback(callback: CallbackQuery, state: FSMContext, telethon_client) -> None:
    parts = callback.data.split(':', 2)
    if len(parts) != 3:
        await callback.answer('Открой новое меню через /start.')
        return
    _, owner, action = parts
    if owner != str(callback.from_user.id):
        await callback.answer('Это меню другого пользователя. Открой своё через /start.', show_alert=True)
        return
    data = await state.get_data()
    if not callback.message or data.get('panel_id') != callback.message.message_id or 'step' not in data:
        await callback.answer('Меню устарело. Открой новое через /start.', show_alert=True)
        return
    step = data['step']
    if action == 'help':
        from handlers.start import HELP_TEXT
        await callback.answer()
        await callback.message.answer(HELP_TEXT, parse_mode='HTML')
        return
    if action == 'cancel':
        data = {**DEFAULTS, 'owner': data['owner'], 'users': [], 'step': 'home', 'panel_id': data['panel_id']}
    elif action == 'begin' and step == 'home':
        data['step'] = 'type'
    elif action == 'back' and step != 'home':
        data['step'] = STEPS[STEPS.index(step) - 1] if step != 'type' else 'home'
    elif action == 'edit' and step == 'review':
        data['step'] = 'type'
    elif action in {'tree', 'path'} and step == 'type':
        if data['mode'] != action:
            data['users'] = []
        data.update(mode=action, step='users')
    elif action == 'next' and step == 'users' and valid_users(data):
        data['step'] = 'depth'
    elif step == 'depth' and action.startswith('depth') and action[5:] in {str(n) for n in range(1, 11)}:
        data.update(depth=int(action[5:]), step='gifts')
    elif action in {'public', 'all'} and step == 'gifts':
        data.update(gifts=action, step='bots')
    elif action in {'include', 'exclude'} and step == 'bots':
        data.update(no_bots=action == 'exclude', step='review')
    elif action == 'run' and step == 'review' and valid_users(data):
        await state.clear()
        await callback.answer('Запускаем построение')
        await callback.message.edit_reply_markup(reply_markup=None)
        from handlers.search import execute_search
        completed = await execute_search(callback.message, telethon_client, data['users'], data, callback.from_user.id)
        if completed is True:
            return  # The result already offers "Построить ещё".
        # Offer the next search after the result or a recoverable failure.
        home = {**DEFAULTS, 'owner': callback.from_user.id, 'users': [], 'step': 'home'}
        panel = await callback.message.answer(settings_text(home), parse_mode='HTML',
                                              reply_markup=settings_keyboard(home, callback.message.chat.type == 'private'))
        await save_step(state, {**home, 'panel_id': panel.message_id})
        return
    else:
        await callback.answer('Этот шаг уже пройден. Используй кнопки текущего сообщения.')
        return
    await callback.answer()
    await show_step(callback.message, state, data)


@router.message(SearchSettings.usernames, F.text, ~F.text.startswith('/'))
async def receive_usernames(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    try:
        users = parse_usernames(message.text, data['mode'])
    except ValueError as exc:
        await message.answer(escape(str(exc)), parse_mode='HTML')
        return
    data.update(users=users, step='depth')
    # Continue in the same panel to keep the wizard together.
    await message.bot.edit_message_text(chat_id=message.chat.id, message_id=data['panel_id'],
                                       text=settings_text(data), parse_mode='HTML',
                                       reply_markup=settings_keyboard(data, message.chat.type == 'private'))
    await save_step(state, data)
