# -*- coding: utf-8 -*-
"""Конвейер распознавания: фото → нейросеть → предпросмотр → запись."""
from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from . import ai as ai_module
from . import config, db, keyboards as kb, money, utils, views

ENTRIES_KEY = "entries"
PHOTOS_KEY = "pending_photos"


def is_ai_ready(user_id: int) -> bool:
    ai = db.get_ai(user_id)
    return bool(ai.get("api_key") and ai.get("base_url") and ai.get("model"))


async def remember_photos(state: FSMContext, photos: list[bytes]) -> None:
    """Оставляет фото в памяти диалога — чтобы обработать их после подключения ключа."""
    data = await state.get_data()
    existing = list(data.get(PHOTOS_KEY) or [])
    existing.extend(photos)
    limit = int(config.get("max_photos", 8) or 8)
    await state.update_data(**{PHOTOS_KEY: existing[-limit:]})


async def pending_photos(state: FSMContext) -> list[bytes]:
    data = await state.get_data()
    return list(data.get(PHOTOS_KEY) or [])


async def drop_photos(state: FSMContext) -> None:
    await state.update_data(**{PHOTOS_KEY: []})


async def recognize(user_id: int, photos: list[bytes]) -> tuple[list[dict], str]:
    """Отправляет фото в нейросеть пользователя. Бросает ai.AIError с понятным текстом."""
    ai = db.get_ai(user_id)
    if not ai.get("api_key"):
        raise ai_module.AIError("Ключ нейросети не подключён.")
    subjects = db.known_subjects(user_id)
    return await ai_module.recognize_grades(ai, photos, subjects, utils.user_today(user_id))


async def show_preview(message: Message, state: FSMContext, user_id: int,
                       entries: list[dict], note: str = "") -> None:
    """Показывает найденные оценки и кнопки подтверждения."""
    settings = db.get_settings(user_id)
    prepared = [money.compute(entry["grade"], entry["subject"], settings) for entry in entries]
    full = [{**entry, "coefficient": computed["coefficient"],
             "base": computed["base"], "amount": computed["amount"],
             "unknown": computed["unknown"]} for entry, computed in zip(entries, prepared)]

    await state.set_state(None)
    await state.update_data(**{ENTRIES_KEY: full, PHOTOS_KEY: []})
    await message.answer(views.preview_text(full, settings, note),
                         reply_markup=kb.confirm_entries(len(full)))


async def current_entries(state: FSMContext) -> list[dict]:
    data = await state.get_data()
    return list(data.get(ENTRIES_KEY) or [])


async def save_entries(message: Message, state: FSMContext, user_id: int,
                       entries: list[dict]) -> None:
    """Записывает подтверждённые оценки в базу и показывает итог."""
    settings = db.get_settings(user_id)
    before = money.snapshot(settings, db.list_grades(user_id))["closing"]
    saved = db.add_grades(user_id, entries, source="photo")
    after = money.snapshot(settings, db.list_grades(user_id))["closing"]
    await state.update_data(**{ENTRIES_KEY: []})
    await message.answer(views.saved_text(saved, settings, before, after),
                         reply_markup=kb.after_save_menu())


async def on_error(message: Message, error: Exception) -> None:
    await message.answer(f"😕 <b>Не получилось прочитать оценки.</b>\n\n"
                         f"{utils.esc(str(error))}\n\n"
                         f"Что можно сделать: прислать фото по одному, снять почётче, "
                         f"сменить модель в «🤖 Нейросеть» или ввести оценки вручную: /add",
                         reply_markup=kb.main_menu())
