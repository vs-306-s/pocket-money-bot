# -*- coding: utf-8 -*-
"""Оценки: приём фото, ручное добавление, список и удаление записей."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import ai as ai_module
from .. import config, db, keyboards as kb, money, pipeline, texts, utils, views
from ..states import Flow

log = logging.getLogger("grades")
router = Router(name="grades")

MEDIA_FILTER = F.photo | F.document
PHOTO_WAIT_SECONDS = 2.2       # ждём остальные фото из «альбома»
PER_PAGE = 5

_tasks: set[asyncio.Task] = set()   # чтобы сборщик мусора не убил фоновые задачи


# ----------------------------------------------------------------- фото
def _file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.document and (message.document.mime_type or "").startswith("image/"):
        return message.document.file_id
    return None


@router.message(MEDIA_FILTER)
async def got_photo(message: Message, state: FSMContext, db_user: dict, bot: Bot) -> None:
    file_id = _file_id(message)
    if not file_id:
        await message.answer("Похоже, это не фото 🤔 Пришли снимок дневника картинкой — "
                             "или добавь оценку вручную: /add")
        return

    data = await state.get_data()
    waiting = list(data.get("_incoming") or [])
    waiting.append(file_id)
    batch = int(data.get("_batch") or 0) + 1
    await state.update_data(_incoming=waiting, _batch=batch)
    await state.set_state(None)

    task = asyncio.create_task(_collect(bot, message, state, db_user, batch))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def _collect(bot: Bot, message: Message, state: FSMContext, db_user: dict, batch: int) -> None:
    """Ждёт паузу: если фото из альбома ещё летят — обработает последняя задача."""
    await asyncio.sleep(PHOTO_WAIT_SECONDS)
    data = await state.get_data()
    if int(data.get("_batch") or 0) != batch:
        return
    file_ids = list(data.get("_incoming") or [])
    await state.update_data(_incoming=[], _batch=batch)
    if not file_ids:
        return
    await _process_photos(bot, message, state, db_user, file_ids)


async def _process_photos(bot: Bot, message: Message, state: FSMContext, db_user: dict,
                          file_ids: list[str]) -> None:
    user_id = int(db_user["user_id"])
    limit = int(config.get("max_photos", 8) or 8)
    file_ids = file_ids[-limit:]

    status = await message.answer(
        f"🔍 Читаю {utils.photos_word(len(file_ids))}… Обычно это занимает до минуты."
    )

    photos: list[bytes] = []
    for file_id in file_ids:
        try:
            data = await utils.download_photo(bot, file_id)
        except Exception as error:  # noqa: BLE001 — фото могло устареть
            log.warning("не смог скачать фото: %s", error)
            data = None
        if data:
            photos.append(data)

    try:
        await status.delete()
    except Exception:  # noqa: BLE001
        pass

    if not photos:
        await message.answer("😕 Не получилось скачать фото. Попробуй прислать ещё раз.")
        return

    if not pipeline.is_ai_ready(user_id):
        await pipeline.remember_photos(state, photos)
        await message.answer(texts.NO_AI_KEY, reply_markup=kb.retry_menu(has_key=False))
        return

    try:
        entries, note = await pipeline.recognize(user_id, photos)
    except ai_module.AIError as error:
        await pipeline.remember_photos(state, photos)
        await message.answer(
            f"😕 <b>Не получилось прочитать оценки</b>\n\n{utils.esc(str(error))}\n\n"
            "Фото я сохранил — нажми «🔁 Попробовать снова», когда поправишь настройки.",
            reply_markup=kb.retry_menu(has_key=True),
        )
        return

    await pipeline.drop_photos(state)
    await pipeline.show_preview(message, state, user_id, entries, note)


@router.callback_query(F.data == "gr:retry")
async def cb_retry(call: CallbackQuery, state: FSMContext, db_user: dict, bot: Bot) -> None:
    photos = await pipeline.pending_photos(state)
    await call.answer()
    if not photos:
        await call.message.answer("Фото уже не в памяти — пришли их заново 📸")
        return
    user_id = int(db_user["user_id"])
    if not pipeline.is_ai_ready(user_id):
        await call.message.answer(texts.NO_AI_KEY, reply_markup=kb.retry_menu(has_key=False))
        return
    try:
        entries, note = await pipeline.recognize(user_id, photos)
    except ai_module.AIError as error:
        await call.message.answer(f"😕 <b>Опять не вышло:</b>\n\n{utils.esc(str(error))}",
                                  reply_markup=kb.retry_menu(has_key=True))
        return
    await pipeline.drop_photos(state)
    await pipeline.show_preview(call.message, state, user_id, entries, note)


# ------------------------------------------------------- подтверждение записи
@router.callback_query(F.data.startswith("gr:del"))
async def cb_delete_entry(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    entries = await pipeline.current_entries(state)
    user_id = int(db_user["user_id"])
    suffix = call.data.split(":", 1)[1]        # "del_all" или "del:2"

    if suffix == "del_all":
        entries = []
        await call.answer("Убрал все")
    else:
        try:
            index = int(suffix.split(":", 1)[1])
        except (IndexError, ValueError):
            index = -1
        if 0 <= index < len(entries):
            entries.pop(index)
        await call.answer("Убрал")

    await state.update_data(entries=entries)
    settings = db.get_settings(user_id)
    try:
        await call.message.edit_text(views.preview_text(entries, settings),
                                     reply_markup=kb.confirm_entries(len(entries)))
    except Exception as error:  # noqa: BLE001 — сообщение могло устареть
        log.info("не смог обновить предпросмотр: %s", error)


@router.callback_query(F.data == "gr:ok")
async def cb_confirm(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    entries = await pipeline.current_entries(state)
    await call.answer("Записываю…")
    if not entries:
        await call.message.answer("Записывать нечего 🙂")
        return
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:  # noqa: BLE001
        pass
    await pipeline.save_entries(call.message, state, int(db_user["user_id"]), entries)


@router.callback_query(F.data == "gr:no")
async def cb_cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(entries=[], pending_photos=[])
    await call.answer("Отменил")
    try:
        await call.message.edit_text("❌ Отменил — ничего не записал.")
    except Exception:  # noqa: BLE001
        await call.message.answer("❌ Отменил — ничего не записал.")


# ------------------------------------------------------------- ручное добавление
def _parse_add_args(args: str | None, today) -> tuple[str | None, str | None, str | None]:
    """«5 математика 15.09» → (grade, subject, date)."""
    grade: str | None = None
    when: str | None = None
    words: list[str] = []
    for token in (args or "").split():
        if grade is None and (money.grade_key(token) or token.lower() in money.SPECIAL_MARKS):
            grade = token
            continue
        if when is None and money.parse_date(token, today=today):
            when = token
            continue
        words.append(token)
    subject = " ".join(words).strip() or None
    return grade, subject, when


@router.message(Command("add"))
async def cmd_add(message: Message, command: CommandObject, state: FSMContext,
                  db_user: dict) -> None:
    args = (command.args or "").strip()
    if not args:
        await state.clear()
        await message.answer("➕ <b>Добавляем оценку вручную</b>\n\nКакая оценка?",
                             reply_markup=kb.grades_menu())
        return

    grade, subject, when = _parse_add_args(args, utils.user_today(int(db_user["user_id"])))
    if not subject:
        await state.update_data(new_grade=grade or "", new_date=when or "")
        await state.set_state(Flow.add_subject)
        await message.answer("📚 По какому предмету?", reply_markup=kb.subjects_menu(_subjects(db_user)))
        return

    today = utils.user_today(int(db_user["user_id"]))
    parsed_date = money.parse_date(when, today=today) if when else today
    await _save_one(message, state, int(db_user["user_id"]), subject, grade or "5",
                    parsed_date or today, "")


def _subjects(db_user: dict) -> list[str]:
    return db.known_subjects(int(db_user["user_id"]))


@router.callback_query(F.data.startswith("gr:new:"))
async def cb_new_grade(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    value = call.data.split(":", 2)[2]
    await call.answer()
    if value == "other":
        await state.set_state(Flow.add_grade)
        await call.message.answer("✏️ Пришли оценку текстом (например «Зачёт» или «4+»).",
                                  reply_markup=kb.cancel_menu())
        return
    await state.update_data(new_grade=value, new_date="")
    await state.set_state(Flow.add_subject)
    await call.message.answer(f"Оценка: <b>{utils.esc(value)}</b>\n\n📚 По какому предмету?",
                              reply_markup=kb.subjects_menu(_subjects(db_user)))


@router.message(Flow.add_grade, F.text)
async def got_manual_grade(message: Message, state: FSMContext, db_user: dict) -> None:
    value = (message.text or "").strip()
    if value == kb.BTN_CANCEL:
        return
    await state.update_data(new_grade=value)
    await state.set_state(Flow.add_subject)
    await message.answer(f"Оценка: <b>{utils.esc(value)}</b>\n\n📚 По какому предмету?",
                         reply_markup=kb.subjects_menu(_subjects(db_user)))


@router.message(Flow.add_subject, F.text)
async def got_manual_subject(message: Message, state: FSMContext, db_user: dict) -> None:
    subject = (message.text or "").strip()
    if subject == kb.BTN_CANCEL:
        return
    if len(subject) > 60:
        await message.answer("Слишком длинное название предмета. Напиши покороче 🙂")
        return
    await state.update_data(new_subject=subject)
    await state.set_state(Flow.add_date)
    await message.answer(f"📅 Когда получил «{utils.esc(subject)}»?",
                         reply_markup=kb.date_menu())


@router.callback_query(F.data.startswith("gr:date:"))
async def cb_manual_date(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    kind = call.data.split(":", 2)[2]
    await call.answer()
    if kind == "manual":
        await state.set_state(Flow.add_date)
        await call.message.answer("✏️ Пришли дату, например <code>15.09.2026</code> или «вчера».",
                                  reply_markup=kb.cancel_menu())
        return

    data = await state.get_data()
    subject = str(data.get("new_subject") or "")
    grade = str(data.get("new_grade") or "")
    today = utils.user_today(int(db_user["user_id"]))
    when = today if kind == "today" else today - timedelta(days=1)
    if not subject:
        await call.message.answer("Что-то потерялось. Начни заново: /add")
        return
    await _save_one(call.message, state, int(db_user["user_id"]), subject, grade, when, "")


@router.message(Flow.add_date, F.text)
async def got_manual_date(message: Message, state: FSMContext, db_user: dict) -> None:
    parsed = money.parse_date(message.text, today=utils.user_today(int(db_user["user_id"])))
    if not parsed:
        await message.answer("Не понял дату 🤔 Напиши так: <code>15.09.2026</code>, "
                             "<code>15.09</code> или «сегодня».")
        return
    data = await state.get_data()
    subject = str(data.get("new_subject") or "")
    grade = str(data.get("new_grade") or "")
    if not subject:
        await message.answer("Что-то потерялось. Начни заново: /add")
        return
    await _save_one(message, state, int(db_user["user_id"]), subject, grade, parsed, "")


async def _save_one(message: Message, state: FSMContext, user_id: int, subject: str,
                    grade: str, when, comment: str) -> None:
    settings = db.get_settings(user_id)
    computed = money.compute(grade, subject, settings)
    entry = {
        "date": when.isoformat(),
        "subject": computed["subject"],
        "grade": computed["grade"],
        "comment": comment,
        "coefficient": computed["coefficient"],
        "base": computed["base"],
        "amount": computed["amount"],
    }
    await state.clear()
    if computed.get("unknown"):
        await message.answer(
            f"⚠️ Для оценки «{utils.esc(computed['grade'])}» не задана ставка — запись "
            f"добавлена с нулём. Настрой ставки в ⚙️ Настройках, потом добавь её снова: /add"
        )
    await pipeline.save_entries(message, state, user_id, [entry])


@router.callback_query(F.data == "gr:cancel_new")
async def cb_cancel_new(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("Отменил")
    await call.message.answer("✖️ Отменил добавление.", reply_markup=kb.main_menu())


# ------------------------------------------------------------------- список
@router.message(Command("list", "grades", "last"))
@router.message(F.text == kb.BTN_LAST)
async def cmd_list(message: Message, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    await _show_list(message, int(db_user["user_id"]), 0)


async def _show_list(message: Message, user_id: int, page: int) -> None:
    rows = db.list_grades(user_id, newest_first=True)
    settings = db.get_settings(user_id)
    currency = settings.get("currency") or "₽"
    await message.answer(views.ledger_text(rows, currency=currency, page=page, per_page=PER_PAGE),
                         reply_markup=kb.list_entries_menu(rows, page, PER_PAGE))


@router.callback_query(F.data.startswith("lg:"))
async def cb_list(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    user_id = int(db_user["user_id"])
    parts = call.data.split(":")
    action = parts[1]
    page = 0
    try:
        page = int(parts[-1])
    except ValueError:
        page = 0

    if action == "del":
        try:
            grade_id = int(parts[2])
        except (IndexError, ValueError):
            grade_id = 0
        removed = db.delete_grade(grade_id, user_id)
        await call.answer("Удалил" if removed else "Уже нет")
    elif action == "undo":
        removed = db.delete_last(user_id)
        await call.answer("Удалил последнюю" if removed else "Записей нет")
    else:
        await call.answer()

    rows = db.list_grades(user_id, newest_first=True)
    settings = db.get_settings(user_id)
    currency = settings.get("currency") or "₽"
    if page * PER_PAGE >= len(rows):
        page = 0
    try:
        await call.message.edit_text(
            views.ledger_text(rows, currency=currency, page=page, per_page=PER_PAGE),
            reply_markup=kb.list_entries_menu(rows, page, PER_PAGE))
    except Exception as error:  # noqa: BLE001
        log.info("список не обновился: %s", error)
        if not rows:
            await call.message.answer("📋 Записей больше нет.")


@router.message(Command("undo"))
async def cmd_undo(message: Message, db_user: dict) -> None:
    removed = db.delete_last(int(db_user["user_id"]))
    if not removed:
        await message.answer("Записей и так нет 🙂")
        return
    settings = db.get_settings(db_user["user_id"])
    currency = settings.get("currency") or "₽"
    await message.answer(
        f"↩️ Убрал последнюю запись:\n{money.fmt_date(removed['date'])} · "
        f"{utils.esc(removed['subject'])} · {utils.esc(removed['grade'])} · "
        f"{utils.esc(utils.money_text(removed['amount'], currency, sign=True))}",
        reply_markup=kb.main_menu())
