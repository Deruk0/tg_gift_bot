"""Telegram buttons for the existing GiftGraph web pages."""
from urllib.parse import urlsplit

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo


def miniapp_available(url: str) -> bool:
    parsed = urlsplit(url)
    return parsed.scheme == "https" and bool(parsed.hostname) and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}


def graph_keyboard(url: str, private_chat: bool, text: str = "🕸 Открыть в Telegram") -> InlineKeyboardMarkup:
    if private_chat and miniapp_available(url):
        button = InlineKeyboardButton(text=text, web_app=WebAppInfo(url=url))
    else:
        button = InlineKeyboardButton(text="🌐 Открыть сайт", url=url)
    return InlineKeyboardMarkup(inline_keyboard=[[button]])
