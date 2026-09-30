# -*- coding: utf-8 -*-
"""Ключ нейросети: /key, /ai, провайдеры, модель, проверка."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import ai as ai_module
from .. import db, keyboards as kb, pipeline, texts, utils
from ..states import Flow

log = logging.getLogger("ai_key")
router = Router(name="ai_key")


async def show_ai(message: Message, user_id: int) -> None:
    ai = db.get_ai(user_id)
    info = ai_module.provider_info(ai.get("provider") or "")
    has_key = bool(ai.get("api_key"))
    lines = [
        "🤖 <b>Нейросеть</b>",
        "",
        f"Провайдер: <b>{utils.esc(info['title'] if ai.get('provider') else 'не выбран')}</b>",
        f"Модель: <code>{utils.esc(ai.get('model') or '—')}</code>",
        f"Адрес API: <code>{utils.esc(ai.get('base_url') or '—')}</code>",
        f"Ключ: {'<b>подключён</b> ✅' if has_key else '<b>нет</b> ❌'}",
        "",
        "Ключ твой личный: запросы к нейросети идут от него, бот за них не платит.",
    ]
    if has_key:
        lines.append("Если фото не читаются — жми «✅ Проверить ключ».")
    else:
        lines.append("Нажми «🔑 Ввести ключ», а если ключа ещё нет — «📖 Где взять ключ».")
    if ai.get("provider") and not info.get("vision"):
        lines += ["", f"⚠️ {utils.esc(info['hint'])}"]
    await message.answer("\n".join(lines), reply_markup=kb.ai_menu(has_key))


@router.message(Command("key", "ai", "provider", "model"))
@router.message(F.text == kb.BTN_AI)
async def cmd_ai(message: Message, command: CommandObject, state: FSMContext, db_user: dict) -> None:
    user_id = int(db_user["user_id"])
    name = (command.command or "").lower() if command else ""
    args = ((command.args or "").strip() if command else "")

    if name == "key" and args:
        await _store_key(message, state, user_id, args)
        return
    if name == "model" and args:
        ai = db.set_ai(user_id, model=args)
        await message.answer(f"✅ Модель: <code>{utils.esc(ai['model'])}</code>")
        await show_ai(message, user_id)
        return
    await state.clear()
    await show_ai(message, user_id)


@router.callback_query(F.data == "ai:menu")
async def cb_ai_menu(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    await call.answer()
    try:
        await call.message.delete()
    except Exception:  # noqa: BLE001
        pass
    await show_ai(call.message, int(db_user["user_id"]))


@router.callback_query(F.data == "ai:guide")
async def cb_guide(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(texts.KEY_GUIDE, reply_markup=kb.providers_menu())


@router.callback_query(F.data == "ai:provider")
async def cb_providers(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    await call.message.edit_text(
        "🌐 <b>Выбери провайдера</b>\n\n"
        "🆓 — есть бесплатный лимит, 💳 — только платно.\n"
        "Пометка «(без фото)» значит, что модель не читает фотографии.",
        reply_markup=kb.providers_menu())


@router.callback_query(F.data.startswith("prov:"))
async def cb_pick_provider(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    key = call.data.split(":", 1)[1]
    info = ai_module.provider_info(key)
    db.set_ai(int(db_user["user_id"]), provider=key, base_url=info["base_url"], model=info["model"])
    await call.answer(f"Выбран: {info['title']}")
    await state.set_state(Flow.ai_key)
    await call.message.edit_text(
        f"🌐 Провайдер: <b>{info['title']}</b>\n"
        f"Модель: <code>{utils.esc(info['model'] or 'укажи вручную')}</code>\n\n"
        f"{utils.esc(info['hint'])}\n\n"
        "Теперь пришли <b>API-ключ</b> одним сообщением — я постараюсь сразу его удалить.",
        reply_markup=kb.back_to_menu())


@router.callback_query(F.data == "ai:key")
async def cb_ask_key(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    ai = db.get_ai(int(db_user["user_id"]))
    await call.answer()
    if not ai.get("provider"):
        await call.message.answer(
            "🔑 <b>Пришли API-ключ одним сообщением.</b>\n\n"
            "Сначала выбери провайдера, если ещё не выбрал.",
            reply_markup=kb.providers_menu())
        return
    await call.message.answer(
        "🔑 <b>Пришли API-ключ одним сообщением.</b>\n\n"
        "Ключ хранится только в базе бота и в чат больше не выводится. "
        "Сообщение с ключом я сразу удалю.\n\n"
        "Нет ключа? Нажми 📖 <b>Где взять ключ</b>.",
        reply_markup=kb.cancel_menu())
    await state.set_state(Flow.ai_key)


@router.callback_query(F.data == "ai:model")
async def cb_ask_model(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    ai = db.get_ai(int(db_user["user_id"]))
    info = ai_module.provider_info(ai.get("provider") or "")
    await call.answer()
    await call.message.answer(
        "🧠 <b>Модель</b>\n\n"
        f"Сейчас: <code>{utils.esc(ai.get('model') or '—')}</code>\n"
        f"Для провайдера «{utils.esc(info['title'])}» по умолчанию: "
        f"<code>{utils.esc(info['model'] or '—')}</code>\n\n"
        "Пришли название модели одним сообщением (можно посмотреть в личном кабинете "
        "провайдера).",
        reply_markup=kb.cancel_menu())
    await state.set_state(Flow.ai_model)


@router.message(Flow.ai_model, F.text)
async def got_model(message: Message, state: FSMContext, db_user: dict) -> None:
    model = (message.text or "").strip()
    if model == kb.BTN_CANCEL:
        return
    if len(model) < 2 or " " in model:
        await message.answer("Название модели обычно без пробелов, например "
                             "<code>gemini-2.0-flash</code>.")
        return
    ai = db.set_ai(int(db_user["user_id"]), model=model)
    await state.clear()
    await message.answer(f"✅ Модель: <code>{utils.esc(ai['model'])}</code>")
    await show_ai(message, int(db_user["user_id"]))


@router.callback_query(F.data == "ai:check")
async def cb_check(call: CallbackQuery, db_user: dict) -> None:
    user_id = int(db_user["user_id"])
    ai = db.get_ai(user_id)
    await call.answer("Проверяю…")
    status = await call.message.answer("🔎 Проверяю ключ… это пара секунд.")
    try:
        answer = await ai_module.ping(ai)
    except ai_module.AIError as error:
        await status.edit_text(f"❌ <b>Ключ не работает</b>\n\n{utils.esc(str(error))}\n\n"
                               f"Подсказки по ключам — /guide")
        return
    except Exception as error:  # noqa: BLE001
        log.exception("ошибка проверки ключа")
        await status.edit_text(f"❌ Не смог проверить: {utils.esc(type(error).__name__)}")
        return
    await status.edit_text(
        "✅ <b>Ключ рабочий!</b>\n\n"
        f"Модель ответила: <i>{utils.esc(answer[:80])}</i>\n\n"
        "Присылай фото дневника — разберу оценки 📸",
        reply_markup=kb.ai_menu(True))


@router.callback_query(F.data == "ai:clear")
async def cb_clear(call: CallbackQuery, db_user: dict) -> None:
    db.clear_ai_key(int(db_user["user_id"]))
    await call.answer("Удалил ключ")
    await call.message.answer("🗑 Ключ удалён. Фото читать не смогу, пока не подключишь новый.",
                              reply_markup=kb.ai_menu(False))


@router.message(Flow.ai_key, F.text)
async def got_key(message: Message, state: FSMContext, db_user: dict) -> None:
    key = (message.text or "").strip()
    if key == kb.BTN_CANCEL:
        return
    await _store_key(message, state, int(db_user["user_id"]), key)


async def _store_key(message: Message, state: FSMContext, user_id: int, key: str) -> None:
    key = key.strip().strip('"').strip("'")
    try:
        await message.delete()
    except Exception:  # noqa: BLE001 — нет прав удалить, не страшно
        pass

    if len(key) < 12 or " " in key:
        await message.answer("❌ Это не похоже на API-ключ: он длинный и без пробелов.\n"
                             "Где взять — /guide, попробовать снова — /key")
        return

    if not db.get_ai(user_id).get("provider"):
        db.set_ai(user_id, provider="openrouter",
                  base_url=ai_module.PROVIDERS["openrouter"]["base_url"],
                  model=ai_module.PROVIDERS["openrouter"]["model"])

    db.set_ai(user_id, api_key=key)
    photos = await pipeline.pending_photos(state)
    await state.clear()
    if photos:
        await state.update_data(pending_photos=photos)

    await message.answer("🔎 Ключ сохранён, проверяю…")
    try:
        answer = await ai_module.ping(db.get_ai(user_id))
    except ai_module.AIError as error:
        await message.answer(
            f"⚠️ <b>Ключ сохранён, но проверка не прошла</b>\n\n{utils.esc(str(error))}\n\n"
            "Поправь модель в 🤖 Нейросеть → «Модель» или возьми ключ другого провайдера "
            "(подсказки — /guide).",
            reply_markup=kb.ai_menu(True))
    except Exception as error:  # noqa: BLE001
        log.exception("ошибка проверки ключа")
        await message.answer(f"⚠️ Ключ сохранён, но проверить не смог: "
                             f"{utils.esc(type(error).__name__)}",
                             reply_markup=kb.ai_menu(True))
    else:
        await message.answer(f"✅ <b>Ключ подключён и работает!</b>\n"
                             f"Модель ответила: <i>{utils.esc(answer[:60])}</i>",
                             reply_markup=kb.ai_menu(True))

    if photos:
        await message.answer("📸 А вот и твои фото — обрабатываю!",
                             reply_markup=kb.retry_menu(has_key=True))
