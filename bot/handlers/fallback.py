# -*- coding: utf-8 -*-
"""Что делать с сообщениями, которые не подошли ни под один сценарий.

Важно не «терять разговор»: если человек прислал что-то похожее на ключ
нейросети или на токен Telegram-бота — это надо распознать и объяснить,
а не отвечать «не понял».
"""
from __future__ import annotations

import re

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards as kb

router = Router(name="fallback")

HINT = ("🤔 Не понял сообщение.\n\n"
        "• Пришли <b>фото дневника</b> — разберу оценки.\n"
        "• Или добавь оценку вручную: <code>/add 5 математика</code>.\n"
        "• Справка — /help, где взять ключ — /guide.")

# токен бота от @BotFather: 123456789:AA...
BOT_TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_\-]{30,}$")
# ключ нейросети: sk-..., gsk_..., xai-..., AIza..., либо очень длинная строка без пробелов
KEY_RE = re.compile(
    r"^(?:sk-[A-Za-z0-9_\-]{8,}|gsk_[A-Za-z0-9_\-]{8,}|xai-[A-Za-z0-9_\-]{8,}|"
    r"AIza[A-Za-z0-9_\-]{20,}|[A-Za-z0-9_\-]{32,})$"
)


@router.message(F.text)
async def unknown_text(message: Message, state: FSMContext, db_user: dict) -> None:
    text = (message.text or "").strip()

    if BOT_TOKEN_RE.match(text):
        await message.answer(
            "🧩 Похоже, это <b>токен Telegram-бота</b> (вида <code>12345:AA...</code>), "
            "а мне нужен <b>ключ нейросети</b> — это другая строка.\n\n"
            "• Токен бота вписывается в <code>config.json</code> того, кто запускает бота.\n"
            "• Мне нужен API-ключ (например <code>sk-...</code> от DeepSeek или OpenRouter).\n\n"
            "Где его взять — /guide",
            reply_markup=kb.main_menu())
        return

    if KEY_RE.match(text):
        # похоже на настоящий ключ — принимаем, не заставляя присылать заново
        from .ai_key import store_key

        await store_key(message, state, int(db_user["user_id"]), text)
        return

    await message.answer(HINT, reply_markup=kb.main_menu())


@router.message()
async def unknown_content(message: Message, state: FSMContext) -> None:
    await message.answer("Такой файл я не разберу 🙂 Пришли <b>фотографию</b> дневника "
                         "или введи оценку вручную: /add",
                         reply_markup=kb.main_menu())

