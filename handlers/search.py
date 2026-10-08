"""
Обработчик команды /search — главный рабочий обработчик бота.

Пайплайн:
  Парсинг аргументов → Telethon запросы → BFS граф → PyVis → PNG → отправка

После отправки результата все данные графа удаляются из памяти (del).
"""
import logging
import os
import re
from html import escape
from typing import Dict, List, Optional, Tuple

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from telethon import TelegramClient

from config import GIFTGRAPH_WEB_URL, GIFTGRAPH_WEB_API_URL, GIFTGRAPH_WEB_SECRET
from miniapp import graph_keyboard
from services.graph import build_path_graph, build_tree_graph
from services.parser import validate_gift_access
from services.visualizer import cleanup_html, render_graph_to_html

logger = logging.getLogger(__name__)
router = Router()


# ── Парсинг аргументов команды ────────────────────────────────────────────────

def _parse_args(text: str) -> Tuple[List[str], Dict]:
    """
    Разбирает строку команды вида:
      /search @user1,@user2 --depth 3 --mode path --gifts all

    Возвращает:
      usernames — список чистых username (без @)
      params    — словарь с параметрами depth/mode/gifts
    """
    # Разбиваем на части, убираем саму команду
    raw = text.strip()
    # Удаляем команду (/search или /search@botname)
    raw = re.sub(r"^/search(?:@\S+)?", "", raw, flags=re.IGNORECASE).strip()

    if not raw:
        return [], {"depth": 2, "mode": "tree", "gifts": "public", "no_bots": False}

    parts = raw.split()

    # Первый аргумент — пользователи через запятую
    option_start = next((i for i, part in enumerate(parts) if part.startswith("--")), len(parts))
    usernames_raw = "".join(parts[:option_start])
    usernames = [
        u.strip().lstrip("@")
        for u in usernames_raw.split(",")
        if u.strip().lstrip("@")
    ]

    # Параметры по умолчанию
    params: Dict = {
        "depth": 2,
        "mode": "tree",
        "gifts": "public",
        "no_bots": False,
    }

    i = option_start
    while i < len(parts):
        option = parts[i]
        if option == "--no-bots":
            params["no_bots"] = True
            i += 1
            continue
        if option not in {"--depth", "--mode", "--gifts"}:
            raise ValueError(f"Неизвестный параметр: {option}")
        if i + 1 >= len(parts) or parts[i + 1].startswith("--"):
            raise ValueError(f"Укажите значение для {option}")
        value = parts[i + 1]
        if option == "--depth":
            if not value.isascii() or not value.isdigit() or not 1 <= int(value) <= 10:
                raise ValueError("Глубина должна быть целым числом от 1 до 10")
            params["depth"] = int(value)
        else:
            choices = {"--mode": {"tree", "path"}, "--gifts": {"all", "public"}}
            if value not in choices[option]:
                raise ValueError(f"Недопустимое значение для {option}: {value}")
            params[option[2:]] = value
        i += 2

    if any(not re.fullmatch(r"[A-Za-z0-9_]+", u) for u in usernames):
        raise ValueError("Укажите username без ссылки и специальных символов")

    # Если несколько пользователей — автоматически переключаем на path
    if len(usernames) > 1 and params["mode"] != "path":
        params["mode"] = "path"

    return usernames, params


def _format_usernames_html(usernames: List[str]) -> str:
    """Форматировать список пользователей для HTML-сообщения"""
    return " и ".join(f"<b>@{escape(u)}</b>" for u in usernames)


# ── Вспомогательная: загрузка графа в GiftGraph Web ───────────────────────────

async def _upload_to_web(html_path: str, label: str, node_count: int, edge_count: int, path_length: int = 0) -> Optional[str]:
    """Загружает HTML-граф в GiftGraph Web и возвращает публичную ссылку."""
    import aiohttp

    try:
        with open(html_path, "r", encoding="utf-8") as f:
            html = f.read()

        public_base_url = GIFTGRAPH_WEB_URL.rstrip("/")
        api_base_url = GIFTGRAPH_WEB_API_URL.rstrip("/")
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "GiftGraphBot/1.0",
        }
        if GIFTGRAPH_WEB_SECRET:
            headers["Authorization"] = f"Bearer {GIFTGRAPH_WEB_SECRET}"
            headers["X-GiftGraph-Secret"] = GIFTGRAPH_WEB_SECRET

        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{api_base_url}/api/graphs",
                json={
                    "html": html,
                    "label": label,
                    "nodes": node_count,
                    "edges": edge_count,
                    "path_length": path_length,
                },
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=45),
            ) as resp:
                if resp.status in (200, 201):
                    data = await resp.json()
                    return f"{public_base_url}{data['url']}"
                else:
                    logger.warning("GiftGraph Web upload failed: %s %s", resp.status, await resp.text())
                    return None
    except Exception as exc:
        logger.warning("GiftGraph Web недоступен: %s", exc)
        return None


# ── Обработчик /search ─────────────────────────────────────────────────────────

@router.message(Command("search"))
async def cmd_search(
    message: Message,
    telethon_client: TelegramClient,
) -> None:
    """
    Основной обработчик поиска.
    telethon_client передаётся через workflow_data из dp.start_polling().
    """
    try:
        usernames, params = _parse_args(message.text or "")
    except ValueError as exc:
        await message.answer(f"❌ {escape(str(exc))}\n\nПолная справка: /help", parse_mode="HTML")
        return

    # ── Валидация входных данных ───────────────────────────────────────────────

    if not usernames:
        await message.answer(
            "❌ Укажите пользователя:\n\n"
            "• <code>/search @username</code>\n"
            "• <code>/search @user1,@user2 --mode path</code>\n\n"
            "Полная справка: /help",
            parse_mode="HTML",
        )
        return

    if params["mode"] == "path" and len(usernames) < 2:
        await message.answer(
            "❌ Для режима <b>path</b> нужно минимум 2 пользователя:\n"
            "<code>/search @user1,@user2 --mode path</code>",
            parse_mode="HTML",
        )
        return

    # ── Валидация Telethon клиента ─────────────────────────────────────────────

    if not telethon_client or not telethon_client.is_connected():
        await message.answer(
            "⚠️ Сервис временно недоступен (userbot не подключён).\n"
            "Обратитесь к администратору.",
            parse_mode="HTML",
        )
        logger.error("Telethon клиент не подключён при попытке поиска от %d", message.from_user.id)
        return

    # ── Сообщение о начале обработки ──────────────────────────────────────────

    users_html = _format_usernames_html(usernames)
    mode_label = "дерево связей" if params["mode"] == "tree" else "поиск пути"
    gifts_label = params["gifts"]
    no_bots_text = " · без ботов" if params["no_bots"] else ""

    processing_msg = await message.answer(
        f"🔍 Строим граф для {users_html}...\n\n"
        f"⚙️ Глубина: <b>{params['depth']}</b> | "
        f"Режим: <b>{mode_label}</b> | "
        f"Подарки: <b>{gifts_label}</b>{no_bots_text}\n\n"
        "⏳ Это может занять от нескольких секунд до пары минут...",
        parse_mode="HTML",
    )

    graph_data: Optional[Dict] = None
    html_path: Optional[str] = None

    try:
        # ── Блок валидации API подарков ────────────────────────────────────────
        gift_ok = await validate_gift_access(telethon_client)
        if not gift_ok:
            await processing_msg.edit_text(
                "❌ <b>API подарков Telegram недоступен.</b>\n\n"
                "Возможные причины:\n"
                "• Устаревшая версия Telethon (требуется ≥ 1.29)\n"
                "• Userbot-сессия не авторизована\n\n"
                "Решение: <code>pip install --upgrade telethon</code>\n"
                "Затем запустите: <code>python setup_session.py</code>",
                parse_mode="HTML",
            )
            return

        # ── Построение графа ───────────────────────────────────────────────────
        if params["mode"] == "tree":
            graph_data = await build_tree_graph(
                telethon_client,
                usernames[0],
                depth=params["depth"],
                gifts_mode=params["gifts"],
                no_bots=params["no_bots"],
            )
            if not graph_data.get("nodes") and params["gifts"] != "all":
                graph_data = await build_tree_graph(
                    telethon_client,
                    usernames[0],
                    depth=params["depth"],
                    gifts_mode="all",
                    no_bots=params["no_bots"],
                )
        else:
            graph_data = await build_path_graph(
                telethon_client,
                usernames,
                depth=params["depth"],
                gifts_mode=params["gifts"],
                no_bots=params["no_bots"],
            )

        # ── Проверяем результат ────────────────────────────────────────────────
        if not graph_data or not graph_data.get("nodes"):
            await processing_msg.edit_text(
                "😔 <b>Не удалось построить граф.</b>\n\n"
                "Возможные причины:\n"
                "• Профиль закрыт или недоступен\n"
                "• У пользователя нет подарков с видимыми отправителями\n"
                "• Пользователь не найден в Telegram\n\n"
                "Попробуйте <code>--gifts all</code> для включения анонимных подарков.",
                parse_mode="HTML",
            )
            return

        node_count = len(graph_data["nodes"])
        edge_count = len(graph_data["edges"])

        # Сообщаем о прогрессе
        await processing_msg.edit_text(
            f"📊 Граф построен: <b>{node_count}</b> узлов, <b>{edge_count}</b> связей\n"
            "🎨 Рендерим визуализацию...",
            parse_mode="HTML",
        )

        # ── Рендеринг в HTML ───────────────────────────────────────────────────
        html_path = await render_graph_to_html(graph_data)

        # ── Формирование подписи ───────────────────────────────────────────────
        caption_parts = [
            f"🕸 <b>Граф связей</b> {users_html}",
            "",
            f"📊 Узлов: <b>{node_count}</b> | Рёбер: <b>{edge_count}</b>",
            f"⚙️ Глубина: <b>{params['depth']}</b> | Режим: <b>{mode_label}</b>",
        ]

        # Добавляем найденный путь если есть
        if params["mode"] == "path":
            paths = graph_data.get("paths", [])
            if paths:
                # Фильтруем анонимные узлы из отображения пути
                path_display = [
                    f"@{escape(p)}" if not p.startswith("anon_") else "?"
                    for p in paths
                ]
                caption_parts.append(
                    f"\n🔗 <b>Путь:</b> {' → '.join(path_display)} "
                    f"({len(paths) - 1} шаг{'а' if 2 <= len(paths) - 1 <= 4 else 'ов'})"
                )
            else:
                caption_parts.append(
                    "\n🔗 Прямой путь между пользователями <b>не найден</b> "
                    f"в пределах глубины {params['depth']}."
                )

        caption = "\n".join(caption_parts)

        # ── Отправка результата ────────────────────────────────────────────────
        web_url: Optional[str] = None
        if html_path and os.path.exists(html_path):
            paths = graph_data.get("paths", []) if graph_data else []
            path_len = max(0, len(paths) - 1) if paths else 0
            web_url = await _upload_to_web(
                html_path,
                f"Граф {users_html}",
                node_count,
                edge_count,
                path_len,
            )

        # Формируем caption с ссылкой на сайт
        if web_url:
            caption += (
                f"\n\n🌐 <b>Открыть граф:</b>\n"
                f"<a href=\"{web_url}\">{web_url}</a>\n"
                f"<i>Граф сохранён и доступен постоянно.</i>"
            )
        else:
            caption += "\n\n⚠️ <i>Веб-версия временно недоступна.</i>"

        await message.answer(
            caption,
            parse_mode="HTML",
            reply_markup=graph_keyboard(web_url, message.chat.type == "private") if web_url else None,
        )
        try:
            await processing_msg.delete()
        except Exception:
            logger.debug("Не удалось удалить сообщение о прогрессе", exc_info=True)

    except Exception as exc:
        logger.error(
            "Критическая ошибка в cmd_search для пользователя %d: %s",
            message.from_user.id,
            exc,
            exc_info=True,
        )
        try:
            await processing_msg.edit_text(
                "❌ <b>Произошла ошибка при построении графа.</b>\n"
                "Попробуйте ещё раз или обратитесь к администратору.",
                parse_mode="HTML",
            )
        except Exception:
            pass

    finally:
        # Удаляем временные файлы и очищаем память
        try:
            cleanup_html(html_path if 'html_path' in locals() else None)
        except Exception:
            pass
        if graph_data is not None:
            del graph_data
