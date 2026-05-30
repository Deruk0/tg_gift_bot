"""
Обработчики подписок и промокодов.

/subscribe      — показать тарифы
/promo CODE     — активировать промокод
callback:       — кнопки выбора тарифа
invoice:        — Telegram Stars платёж
successful_payment — активация подписки после оплаты
"""
import logging
from datetime import date, timedelta
from html import escape

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

from config import (
    ADMIN_USER_ID,
    PROMO_CODES,
    SUBSCRIPTION_MONTHLY_STARS,
    SUBSCRIPTION_YEARLY_STARS,
)
from database.db import get_or_create_user, set_promo_used, set_subscription

logger = logging.getLogger(__name__)
router = Router()


# ── Вспомогательные функции ────────────────────────────────────────────────────

def _subscription_keyboard() -> InlineKeyboardMarkup:
    """Клавиатура с кнопками выбора тарифа"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"📅 Месяц — {SUBSCRIPTION_MONTHLY_STARS} ⭐",
                    callback_data="subscribe_monthly",
                )
            ],
            [
                InlineKeyboardButton(
                    text=f"📆 Год — {SUBSCRIPTION_YEARLY_STARS} ⭐ (экономия 58%)",
                    callback_data="subscribe_yearly",
                )
            ],
        ]
    )


def _pluralize_days(n: int) -> str:
    """Склонение слова 'день' для русского языка"""
    if 11 <= n % 100 <= 14:
        return f"{n} дней"
    rem = n % 10
    if rem == 1:
        return f"{n} день"
    if 2 <= rem <= 4:
        return f"{n} дня"
    return f"{n} дней"


# ── /subscribe ─────────────────────────────────────────────────────────────────

@router.message(Command("subscribe"))
async def cmd_subscribe(message: Message) -> None:
    """Показать статус подписки и доступные тарифы"""
    user = await get_or_create_user(message.from_user.id)

    # Формируем строку статуса подписки
    sub_status_lines = []
    if user["subscription_until"]:
        try:
            sub_until = date.fromisoformat(user["subscription_until"])
            if sub_until >= date.today():
                days_left = (sub_until - date.today()).days
                sub_status_lines.append(
                    f"✅ Подписка активна до: <b>{sub_until.strftime('%d.%m.%Y')}</b> "
                    f"({_pluralize_days(days_left)} осталось)\n"
                )
            else:
                sub_status_lines.append("⏰ Ваша подписка истекла.\n")
        except ValueError:
            pass

    if not sub_status_lines:
        searches_left = max(0, 3 - user["free_searches_used"])
        sub_status_lines.append(f"🆓 Бесплатных поисков осталось: <b>{searches_left}</b>\n")

    status_text = "".join(sub_status_lines)

    await message.answer(
        "⭐ <b>Подписка GiftGraph</b>\n\n"
        f"{status_text}"
        "━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💰 <b>Тарифы (оплата Telegram Stars):</b>\n"
        f"• Месяц: <b>{SUBSCRIPTION_MONTHLY_STARS} ⭐</b>\n"
        f"• Год: <b>{SUBSCRIPTION_YEARLY_STARS} ⭐</b> — экономия 58%\n\n"
        "Выберите тариф:",
        parse_mode="HTML",
        reply_markup=_subscription_keyboard(),
    )


# ── Callback-кнопка из сообщения «лимит исчерпан» ─────────────────────────────

@router.callback_query(F.data == "show_subscription")
async def callback_show_subscription(callback: CallbackQuery) -> None:
    """Открыть страницу подписки по нажатию кнопки"""
    await callback.answer()
    await cmd_subscribe(callback.message)


# ── Создание инвойсов ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "subscribe_monthly")
async def callback_subscribe_monthly(callback: CallbackQuery) -> None:
    """Выставить инвойс на месячную подписку"""
    await callback.answer()
    await callback.message.answer_invoice(
        title="GiftGraph — Подписка 1 месяц",
        description=(
            "Неограниченный доступ к графу социальных связей на 30 дней. "
            "Оплата Telegram Stars."
        ),
        payload="subscription_monthly",
        currency="XTR",              # Telegram Stars
        prices=[
            LabeledPrice(
                label="Месячная подписка",
                amount=SUBSCRIPTION_MONTHLY_STARS,
            )
        ],
    )
    logger.info(
        "Инвойс (месяц) выставлен пользователю %d", callback.from_user.id
    )


@router.callback_query(F.data == "subscribe_yearly")
async def callback_subscribe_yearly(callback: CallbackQuery) -> None:
    """Выставить инвойс на годовую подписку"""
    await callback.answer()
    await callback.message.answer_invoice(
        title="GiftGraph — Подписка 1 год",
        description=(
            "Неограниченный доступ к графу социальных связей на 365 дней. "
            "Экономия 58% по сравнению с месячной подпиской."
        ),
        payload="subscription_yearly",
        currency="XTR",              # Telegram Stars
        prices=[
            LabeledPrice(
                label="Годовая подписка",
                amount=SUBSCRIPTION_YEARLY_STARS,
            )
        ],
    )
    logger.info(
        "Инвойс (год) выставлен пользователю %d", callback.from_user.id
    )


# ── Обработка платежей ─────────────────────────────────────────────────────────

@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout: PreCheckoutQuery) -> None:
    """
    Подтверждение инвойса перед оплатой.
    Telegram требует ответа в течение 10 секунд.
    """
    await pre_checkout.answer(ok=True)
    logger.info(
        "Pre-checkout подтверждён: user=%d payload=%s",
        pre_checkout.from_user.id,
        pre_checkout.invoice_payload,
    )


@router.message(F.successful_payment)
async def process_successful_payment(message: Message) -> None:
    """
    Активация подписки после успешного платежа через Telegram Stars.

    При повторной оплате подписка продлевается от текущей даты окончания
    (а не от сегодня) — пользователь не теряет оставшиеся дни.
    """
    payment = message.successful_payment
    payload = payment.invoice_payload
    user_id = message.from_user.id

    logger.info(
        "Успешный платёж: user=%d payload=%s amount=%d %s",
        user_id,
        payload,
        payment.total_amount,
        payment.currency,
    )

    user = await get_or_create_user(user_id)

    # Определяем стартовую дату для расчёта нового срока
    today = date.today()
    if user["subscription_until"]:
        try:
            current_until = date.fromisoformat(user["subscription_until"])
            # Продлеваем от актуальной даты окончания если она ещё не истекла
            start_date = current_until if current_until > today else today
        except ValueError:
            start_date = today
    else:
        start_date = today

    # Рассчитываем новую дату окончания
    if payload == "subscription_monthly":
        new_until = start_date + timedelta(days=30)
        period_text = "1 месяц"
        stars_spent = SUBSCRIPTION_MONTHLY_STARS
    elif payload == "subscription_yearly":
        new_until = start_date + timedelta(days=365)
        period_text = "1 год"
        stars_spent = SUBSCRIPTION_YEARLY_STARS
    else:
        logger.error("Неизвестный payload платежа: %s от пользователя %d", payload, user_id)
        await message.answer("❌ Ошибка обработки платежа. Обратитесь в поддержку.")
        return

    await set_subscription(user_id, new_until)

    await message.answer(
        "🎉 <b>Оплата прошла успешно!</b>\n\n"
        f"⭐ Потрачено: <b>{stars_spent} Stars</b>\n"
        f"📅 Подписка активирована на <b>{period_text}</b>\n"
        f"📅 Действует до: <b>{new_until.strftime('%d.%m.%Y')}</b>\n\n"
        "Теперь у вас неограниченный доступ к GiftGraph! 🕸",
        parse_mode="HTML",
    )


# ── /promo ─────────────────────────────────────────────────────────────────────

@router.message(Command("promo"))
async def cmd_promo(message: Message) -> None:
    """Активация промокода"""
    parts = (message.text or "").strip().split()

    if len(parts) < 2:
        await message.answer(
            "❌ Укажите промокод:\n<code>/promo КОД</code>",
            parse_mode="HTML",
        )
        return

    code = parts[1].upper().strip()
    user_id = message.from_user.id
    user = await get_or_create_user(user_id)

    # Проверяем, не использовал ли уже промокод
    if user["promo_used"]:
        await message.answer(
            f"❌ Вы уже использовали промокод <code>{escape(user['promo_used'])}</code>.\n"
            "Каждый аккаунт может использовать только один промокод.",
            parse_mode="HTML",
        )
        return

    # Проверяем код в списке активных
    if code not in PROMO_CODES:
        available = "FOREVER" if "FOREVER" in PROMO_CODES else None
        extra = f"\n\nПробуйте: <code>{available}</code>" if available else ""
        await message.answer(
            "❌ Промокод не найден или истёк.\n"
            "Проверьте правильность написания." + extra,
            parse_mode="HTML",
        )
        logger.info("Неверный промокод от пользователя %d: %s", user_id, code)
        return

    days: int = PROMO_CODES[code]

    # Рассчитываем новую дату подписки (накапливаем поверх существующей)
    today = date.today()
    if user["subscription_until"]:
        try:
            current_until = date.fromisoformat(user["subscription_until"])
            start_date = current_until if current_until > today else today
        except ValueError:
            start_date = today
    else:
        start_date = today

    # days == 0 означает «навсегда»
    if days == 0:
        new_until = date(9999, 12, 31)
        duration_text = "навсегда 🔮"
    else:
        new_until = start_date + timedelta(days=days)
        duration_text = f"на {_pluralize_days(days)}"

    await set_subscription(user_id, new_until)
    await set_promo_used(user_id, code)

    await message.answer(
        "🎁 <b>Промокод активирован!</b>\n\n"
        f"✅ Код: <code>{escape(code)}</code>\n"
        f"📅 Подписка продлена <b>{duration_text}</b>\n"
        f"📅 Действует до: <b>{new_until.strftime('%d.%m.%Y')}</b>",
        parse_mode="HTML",
    )

    logger.info(
        "Пользователь %d активировал промокод %s, продление: %s (до %s)",
        user_id,
        code,
        duration_text,
        new_until,
    )


# ── Админ-панель (доступна только ADMIN_USER_ID) ──────────────────────────────

def _is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id == ADMIN_USER_ID


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Главное меню админ-панели"""
    if not _is_admin(message.from_user.id):
        return  # молча игнорируем для не-админов

    await message.answer(
        "⚙️ <b>Админ-панель GiftGraph</b>\n\n"
        "Доступные команды:\n"
        "/admin_stats — 📊 Статистика пользователей\n"
        "/admin_grant <user_id> <дней> — 🎁 Выдать подписку (0 = навсегда)\n"
        "/admin_msg <текст> — 📨 Рассылка сообщения всем пользователям",
        parse_mode="HTML",
    )


@router.message(Command("admin_stats"))
async def cmd_admin_stats(message: Message) -> None:
    """Статистика пользователей бота"""
    if not _is_admin(message.from_user.id):
        return

    import aiosqlite

    async with aiosqlite.connect("giftgraph.db") as db:
        # Общее количество
        total_row = await db.execute_fetchall("SELECT COUNT(*) FROM users")
        total = total_row[0][0] if total_row else 0

        # С активной подпиской
        sub_row = await db.execute_fetchall(
            "SELECT COUNT(*) FROM users WHERE subscription_until >= ?",
            (date.today().isoformat(),),
        )
        active_subs = sub_row[0][0] if sub_row else 0

        # Использовали промокод
        promo_row = await db.execute_fetchall(
            "SELECT COUNT(*) FROM users WHERE promo_used IS NOT NULL"
        )
        promo_users = promo_row[0][0] if promo_row else 0

    await message.answer(
        "📊 <b>Статистика GiftGraph</b>\n\n"
        f"👥 Всего пользователей: <b>{total}</b>\n"
        f"⭐ С активной подпиской: <b>{active_subs}</b>\n"
        f"🎁 Использовали промокод: <b>{promo_users}</b>",
        parse_mode="HTML",
    )


@router.message(Command("admin_grant"))
async def cmd_admin_grant(message: Message) -> None:
    """Выдать подписку указанному пользователю"""
    if not _is_admin(message.from_user.id):
        return

    parts = (message.text or "").strip().split()
    if len(parts) < 3:
        await message.answer(
            "❌ Формат: <code>/admin_grant USER_ID ДНЕЙ</code>\n"
            "Дней = 0 для вечной подписки.",
            parse_mode="HTML",
        )
        return

    try:
        target_id = int(parts[1])
        days = int(parts[2])
    except ValueError:
        await message.answer("❌ USER_ID и ДНЕЙ должны быть числами.")
        return

    user = await get_or_create_user(target_id)
    today = date.today()

    if user["subscription_until"]:
        try:
            current_until = date.fromisoformat(user["subscription_until"])
            start_date = current_until if current_until > today else today
        except ValueError:
            start_date = today
    else:
        start_date = today

    if days == 0:
        new_until = date(9999, 12, 31)
        duration_text = "навсегда 🔮"
    else:
        new_until = start_date + timedelta(days=days)
        duration_text = f"на {_pluralize_days(days)}"

    await set_subscription(target_id, new_until)

    await message.answer(
        f"✅ Подписка выдана пользователю <code>{target_id}</code>\n"
        f"📅 Продление: <b>{duration_text}</b>\n"
        f"📅 До: <b>{new_until.strftime('%d.%m.%Y')}</b>",
        parse_mode="HTML",
    )
    logger.info("Админ %d выдал подписку пользователю %d: %s", message.from_user.id, target_id, duration_text)


@router.message(Command("admin_msg"))
async def cmd_admin_msg(message: Message) -> None:
    """Рассылка сообщения всем пользователям бота"""
    if not _is_admin(message.from_user.id):
        return

    # Текст — всё после команды
    text = (message.text or "").strip()
    prefix = "/admin_msg"
    broadcast_text = text[len(prefix):].strip()

    if not broadcast_text:
        await message.answer(
            "❌ Укажите текст рассылки:\n"
            "<code>/admin_msg Привет, большое обновление уже в боте!</code>",
            parse_mode="HTML",
        )
        return

    import aiosqlite

    async with aiosqlite.connect("giftgraph.db") as db:
        rows = await db.execute_fetchall("SELECT user_id FROM users")
        user_ids = [row[0] for row in rows]

    sent = 0
    failed = 0
    for uid in user_ids:
        try:
            await message.bot.send_message(uid, f"📨 <b>Сообщение от GiftGraph:</b>\n\n{broadcast_text}", parse_mode="HTML")
            sent += 1
        except Exception as exc:
            logger.warning("Не удалось отправить сообщение пользователю %d: %s", uid, exc)
            failed += 1

    await message.answer(
        f"📨 Рассылка завершена\n\n"
        f"✅ Отправлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML",
    )