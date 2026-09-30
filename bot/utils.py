# -*- coding: utf-8 -*-
"""Мелкие помощники: склонения, форматирование, скачивание фото."""
from __future__ import annotations

import html
from datetime import date, datetime, timedelta, timezone

from aiogram import Bot

from . import config, money


def esc(text) -> str:
    return html.escape(str(text if text is not None else ""), quote=False)


def plural(number: int, one: str, few: str, many: str) -> str:
    number = abs(int(number))
    if number % 10 == 1 and number % 100 != 11:
        return one
    if 2 <= number % 10 <= 4 and not 12 <= number % 100 <= 14:
        return few
    return many


def marks(number: int) -> str:
    return f"{number} {plural(number, 'оценка', 'оценки', 'оценок')}"


def photos_word(number: int) -> str:
    return f"{number} {plural(number, 'фото', 'фото', 'фото')}"


def subject_word(number: int) -> str:
    return f"{number} {plural(number, 'предмет', 'предмета', 'предметов')}"


def money_text(value: float, currency: str = "₽", sign: bool = False) -> str:
    return money.format_money(value, currency, sign=sign)


def coefficient_text(value: float) -> str:
    if abs(float(value) - 1) < 1e-9:
        return "×1"
    rounded = f"{float(value):.2f}".rstrip("0").rstrip(".")
    return f"×{rounded}"


def local_now(tz_offset: float | None = None) -> datetime:
    offset = float(tz_offset if tz_offset is not None else config.get("tz_offset", 3))
    return datetime.now(timezone.utc) + timedelta(hours=offset)


def today(tz_offset: float | None = None) -> date:
    return local_now(tz_offset).date()


def user_today(user_id: int) -> date:
    """«Сегодня» в часовом поясе конкретного пользователя."""
    from . import db

    settings = db.get_settings(user_id)
    return today(settings.get("tz_offset") or 0)


def fmt_dt(value: datetime) -> str:
    return value.strftime("%d.%m.%Y в %H:%M")


def truncate(text: str, limit: int = 60) -> str:
    text = str(text or "")
    return text if len(text) <= limit else text[: limit - 1] + "…"


async def download_photo(bot: Bot, file_id: str, limit_bytes: int = 12_000_000) -> bytes | None:
    """Скачивает фото в память. Возвращает None, если файл слишком большой."""
    buffer = await bot.download(file_id)
    if buffer is None:
        return None
    data = buffer.read() if hasattr(buffer, "read") else bytes(buffer)
    if not data or len(data) > limit_bytes:
        return None
    return data
