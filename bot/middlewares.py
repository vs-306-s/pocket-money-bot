# -*- coding: utf-8 -*-
"""Middleware: подкладывает в хендлеры запись пользователя из базы."""
from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

from . import db


class DbUserMiddleware(BaseMiddleware):
    """Добавляет в хендлеры параметр `db_user` — запись пользователя из базы.

    Хендлеры объявляют его как обычный аргумент:  async def cmd(message, db_user): ...
    """

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        user = data.get("event_from_user")
        if user is not None and not getattr(user, "is_bot", False):
            data["db_user"] = db.touch_user(user.id, user.username, user.full_name)
        else:
            data["db_user"] = {"user_id": 0, "username": "", "full_name": ""}
        return await handler(event, data)
