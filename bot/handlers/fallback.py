# -*- coding: utf-8 -*-
"""Что делать с сообщениями, которые не подошли ни под один сценарий."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from .. import keyboards as kb

router = Router(name="fallback")

HINT = ("🤔 Не понял сообщение.\n\n"
        "• Пришли <b>фото дневника</b> — разберу оценки.\n"
        "• Или добавь оценку вручную: <code>/add 5 математика</code>.\n"
        "• Справка — /help, где взять ключ — /guide.")


@router.message(F.text)
async def unknown_text(message: Message, state: FSMContext) -> None:
    await message.answer(HINT, reply_markup=kb.main_menu())


@router.message()
async def unknown_content(message: Message, state: FSMContext) -> None:
    await message.answer("Такой файл я не разберу 🙂 Пришли <b>фотографию</b> дневника "
                         "или введи оценку вручную: /add",
                         reply_markup=kb.main_menu())
