# -*- coding: utf-8 -*-
"""База: /start, меню, справка, гайд по ключам, отмена ввода."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import config, db, keyboards as kb, texts, utils, views

router = Router(name="base")


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    name = (db_user.get("full_name") or "").split(" ")[0]
    greeting = f"<b>{utils.esc(name)}</b>, привет!\n\n" if name else ""
    await message.answer(greeting + texts.START, reply_markup=kb.main_menu())


@router.message(Command("help"))
@router.message(F.text == kb.BTN_HELP)
async def cmd_help(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.HELP, reply_markup=kb.main_menu())


@router.message(Command("guide"))
async def cmd_guide(message: Message) -> None:
    await message.answer(texts.KEY_GUIDE, reply_markup=kb.main_menu())


@router.message(Command("cancel"))
@router.message(F.text == kb.BTN_CANCEL)
async def cmd_cancel(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    await state.clear()
    if current:
        await message.answer("✖️ Отменил. Ничего не изменилось.", reply_markup=kb.main_menu())
    else:
        await message.answer("Нечего отменять 🙂", reply_markup=kb.main_menu())


@router.message(Command("photos"))
@router.message(F.text == kb.BTN_PHOTOS)
async def cmd_photos(message: Message, state: FSMContext) -> None:
    await state.clear()
    limit = int(config.get("max_photos", 8) or 8)
    await message.answer(texts.HOW_PHOTOS.format(max_photos=limit),
                         reply_markup=kb.cancel_menu())


@router.message(Command("id"))
async def cmd_id(message: Message, db_user: dict) -> None:
    await message.answer(f"Твой id: <code>{message.from_user.id}</code>")


@router.message(Command("admin"))
async def cmd_admin(message: Message, db_user: dict) -> None:
    user_id = int(message.from_user.id)
    if not config.cfg.is_owner(user_id):
        await message.answer("Эта команда только для владельца бота.")
        return
    stats = db.totals()
    lines = [
        "🛠 <b>Служебная информация</b>",
        "",
        f"Пользователей: <b>{stats['users']}</b>",
        f"Оценок в базе: <b>{stats['grades']}</b>",
        f"Подключённых ключей: <b>{stats['keys']}</b>",
        f"База: <code>{utils.esc(db.DB_PATH)}</code>",
        f"Прокси: <code>{utils.esc(config.cfg.proxy or 'не используется')}</code>",
        "",
        f"Ставки по умолчанию: <code>{utils.esc(config.get('default_rates'))}</code>",
        f"Коэффициенты по умолчанию: <code>{utils.esc(config.get('default_coefficients'))}</code>",
        f"Фото за раз: <b>{config.get('max_photos')}</b>",
    ]
    await message.answer("\n".join(lines), reply_markup=kb.main_menu())


@router.callback_query(F.data == "mn:main")
async def cb_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    await call.message.answer("🏠 Главное меню", reply_markup=kb.main_menu())


@router.callback_query(F.data == "mn:balance")
async def cb_balance(call: CallbackQuery, db_user: dict) -> None:
    await call.answer()
    await call.message.answer(views.balance_text(db_user["user_id"]), reply_markup=kb.main_menu())
