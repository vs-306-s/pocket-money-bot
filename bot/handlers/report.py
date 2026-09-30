# -*- coding: utf-8 -*-
"""Отчёты: баланс, период и выгрузка в Excel."""
from __future__ import annotations

import asyncio
import logging
import os

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from .. import config, db, excel, keyboards as kb, money, utils, views
from ..states import Flow

log = logging.getLogger("report")
router = Router(name="report")


@router.message(Command("balance", "money"))
@router.message(F.text == kb.BTN_BALANCE)
async def cmd_balance(message: Message, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    await message.answer(views.balance_text(int(db_user["user_id"])), reply_markup=kb.main_menu())


@router.message(Command("report", "excel", "xlsx", "table"))
@router.message(F.text == kb.BTN_REPORT)
async def cmd_report(message: Message, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    settings = db.get_settings(int(db_user["user_id"]))
    currency = settings.get("currency") or "₽"
    rows = db.list_grades(int(db_user["user_id"]))
    stats = money.snapshot(settings, rows)
    await message.answer(
        "📊 <b>Отчёт в Excel</b>\n\n"
        f"Всего записей: <b>{len(rows)}</b>\n"
        f"Остаток: <b>{utils.esc(utils.money_text(stats['closing'], currency))}</b>\n\n"
        "Выбери период — соберу таблицу с датами, предметами, оценками и коэффициентами:",
        reply_markup=kb.period_menu())


@router.callback_query(F.data == "rp:custom")
async def cb_custom_period(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(Flow.period_from)
    await call.message.answer("📅 Пришли <b>дату начала</b>, например <code>01.09.2026</code>.",
                              reply_markup=kb.cancel_menu())


@router.message(Flow.period_from, F.text)
async def got_period_from(message: Message, state: FSMContext, db_user: dict) -> None:
    if (message.text or "").strip() == kb.BTN_CANCEL:
        return
    parsed = money.parse_date(message.text, today=utils.user_today(int(db_user["user_id"])))
    if not parsed:
        await message.answer("Не понял дату 🤔 Напиши, например, <code>01.09.2026</code>.")
        return
    await state.update_data(period_from=parsed.isoformat())
    await state.set_state(Flow.period_to)
    await message.answer(f"Начало: <b>{money.fmt_date(parsed)}</b>\n\n"
                         "Теперь пришли <b>дату конца</b> (можно «сегодня»).",
                         reply_markup=kb.cancel_menu())


@router.message(Flow.period_to, F.text)
async def got_period_to(message: Message, state: FSMContext, db_user: dict) -> None:
    if (message.text or "").strip() == kb.BTN_CANCEL:
        return
    parsed = money.parse_date(message.text, today=utils.user_today(int(db_user["user_id"])))
    if not parsed:
        await message.answer("Не понял дату 🤔 Напиши, например, <code>30.09.2026</code>.")
        return
    data = await state.get_data()
    start = money.parse_date(data.get("period_from"))
    if not start:
        await message.answer("Начало потерялось. Начни заново: /report")
        await state.clear()
        return
    if parsed < start:
        start, parsed = parsed, start
    await state.clear()
    await _send_report(message, int(db_user["user_id"]), start, parsed,
                       f"с {money.fmt_date(start)} по {money.fmt_date(parsed)}")


@router.callback_query(F.data.startswith("rp:"))
async def cb_report(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    kind = call.data.split(":", 1)[1]
    await call.answer("Собираю таблицу…")
    await state.clear()
    user_id = int(db_user["user_id"])
    settings = db.get_settings(user_id)
    date_from, date_to, title = money.period_bounds(kind, settings.get("tz_offset") or 0)
    await _send_report(call.message, user_id, date_from, date_to, title)


async def _send_report(message: Message, user_id: int, date_from, date_to, title: str) -> None:
    settings = db.get_settings(user_id)
    all_rows = db.list_grades(user_id)
    rows = views.period_rows(user_id, date_from, date_to)
    stats = money.snapshot(settings, all_rows, date_from)
    user = db.get_user(user_id)
    label = user.get("full_name") or (f"@{user['username']}" if user.get("username") else "")

    filename = excel.default_report_name(user_id, title)
    path = os.path.join(config.REPORTS_DIR, filename)
    config.ensure_dirs()

    try:
        await asyncio.to_thread(
            excel.build_report, path, rows, stats, settings,
            period_title=title,
            user_label=label,
            tz_offset=settings.get("tz_offset") or 0,
            ai=db.get_ai(user_id),
        )
    except RuntimeError as error:
        await message.answer(f"😕 <b>Не смог собрать Excel</b>\n\n{utils.esc(str(error))}")
        return
    except Exception as error:  # noqa: BLE001 — не роняем бота из-за файла
        log.exception("ошибка сборки отчёта")
        await message.answer(f"😕 Не получилось собрать файл: {utils.esc(type(error).__name__)}.\n"
                             "Попробуй ещё раз или напиши /help.")
        return

    caption = views.report_caption(rows, settings, stats, title)
    try:
        await message.answer_document(
            FSInputFile(path, filename=filename),
            caption=caption,
            reply_markup=kb.after_save_menu(),
        )
    except Exception as error:  # noqa: BLE001
        log.warning("не смог отправить отчёт: %s", error)
        await message.answer(f"😕 Не получилось отправить файл: {utils.esc(type(error).__name__)}")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
