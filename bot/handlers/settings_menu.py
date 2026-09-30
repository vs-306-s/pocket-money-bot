# -*- coding: utf-8 -*-
"""Настройки: стартовая сумма, ставки за оценки, коэффициенты, валюта, пояс."""
from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from .. import db, keyboards as kb, money, texts, utils
from ..states import Flow

router = Router(name="settings")


def _settings_view(settings: dict, count: int = 0) -> str:
    currency = settings.get("currency") or "₽"
    rates = settings.get("rates") or {}
    coefficients = settings.get("coefficients") or {}

    rate_parts = [
        f"{money.GRADE_TITLES.get(grade, grade)} {money.format_money(rate, currency, sign=True)}"
        for grade, rate in money.sorted_rates(rates)
    ]
    coefficient_parts = [
        f"{money.pretty_subject(subject)} ×{value:g}"
        for subject, value in sorted(coefficients.items())
    ]

    lines = [
        texts.SETTINGS_HINT,
        "",
        f"💵 Стартовая сумма: <b>{utils.esc(utils.money_text(settings.get('start_sum') or 0, currency))}</b>",
        f"📈 Ставки: {utils.esc(', '.join(rate_parts) if rate_parts else 'не заданы')}",
        f"✖️ Коэффициенты: {utils.esc(', '.join(coefficient_parts) if coefficient_parts else 'все предметы ×1')}",
        f"💱 Валюта: <b>{utils.esc(currency)}</b>   ·   🕒 Пояс: <b>UTC+{int(settings.get('tz_offset') or 0)}</b>",
        f"📋 Оценок в базе: <b>{utils.marks(count)}</b>",
    ]
    return "\n".join(lines)


async def _send_settings(message: Message, user_id: int) -> None:
    settings = db.get_settings(user_id)
    await message.answer(_settings_view(settings, db.count_grades(user_id)),
                         reply_markup=kb.settings_menu(settings))


@router.message(Command("settings"))
@router.message(F.text == kb.BTN_SETTINGS)
async def cmd_settings(message: Message, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    await _send_settings(message, int(db_user["user_id"]))


@router.callback_query(F.data == "st:main")
async def cb_main(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await state.clear()
    user_id = int(db_user["user_id"])
    settings = db.get_settings(user_id)
    text = _settings_view(settings, db.count_grades(user_id))
    await call.answer()
    try:
        await call.message.edit_text(text, reply_markup=kb.settings_menu(settings))
    except Exception:  # noqa: BLE001
        await call.message.answer(text, reply_markup=kb.settings_menu(settings))


# ------------------------------------------------------------- стартовая сумма
@router.callback_query(F.data == "st:start_sum")
async def cb_start_sum(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    currency = settings.get("currency") or "₽"
    await call.answer()
    await call.message.answer(
        "💵 <b>Стартовая сумма</b>\n\n"
        "Это сумма, с которой начинается счёт. Дальше я прибавляю и отнимаю деньги за оценки.\n\n"
        f"Сейчас: <b>{utils.esc(utils.money_text(settings.get('start_sum') or 0, currency))}</b>\n\n"
        f"Пришли новое число (например <code>1000</code> или <code>500</code>). "
        f"Валюта — {utils.esc(currency)}.",
        reply_markup=kb.cancel_menu())
    await state.set_state(Flow.start_sum)


@router.message(Flow.start_sum, F.text)
async def got_start_sum(message: Message, state: FSMContext, db_user: dict) -> None:
    if (message.text or "").strip() == kb.BTN_CANCEL:
        return
    value = money.parse_amount(message.text)
    if value is None:
        await message.answer("Не понял число 🤔 Пришли, например: <code>1000</code>")
        return
    settings = db.save_settings(int(db_user["user_id"]), start_sum=value)
    await state.clear()
    currency = settings.get("currency") or "₽"
    await message.answer(
        f"✅ Стартовая сумма: <b>{utils.esc(utils.money_text(value, currency))}</b>",
        reply_markup=kb.settings_menu(settings))


# ------------------------------------------------------------------ ставки
@router.callback_query(F.data == "st:rates")
async def cb_rates(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    currency = settings.get("currency") or "₽"
    await call.answer()
    rows = money.sorted_rates(settings.get("rates") or {})
    listing = "\n".join(
        f"{money.GRADE_EMOJI.get(grade, '•')} {money.GRADE_TITLES.get(grade, grade)}: "
        f"<b>{utils.esc(utils.money_text(rate, currency, sign=True))}</b>"
        for grade, rate in rows
    ) or "ставки ещё не заданы"
    text = ("📈 <b>Ставки за оценки</b>\n\n"
            f"{listing}\n\n"
            "Нажми на оценку, чтобы изменить ставку. Плюс — деньги приходят, минус — списываются.")
    await call.message.answer(text, reply_markup=kb.rates_menu(settings.get("rates") or {}, currency))
    await state.clear()


async def _ask_rate(message: Message, state: FSMContext, db_user: dict, grade: str) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    currency = settings.get("currency") or "₽"
    current = (settings.get("rates") or {}).get(grade)
    now = (f"\n\nСейчас: <b>{utils.esc(utils.money_text(current, currency, sign=True))}</b>"
           if current is not None else "")
    await message.answer(
        f"📈 Ставка за «{utils.esc(grade)}»{now}\n\n"
        f"Пришли число. Например <code>300</code> — приходит 300 {utils.esc(currency)}, "
        f"<code>-150</code> — списывается 150.",
        reply_markup=kb.cancel_menu())
    await state.set_state(Flow.rate_value)
    await state.update_data(rate_key=grade)


@router.callback_query(F.data.startswith("st:rate:"))
async def cb_rate(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    grade = call.data.split(":", 2)[2]
    await call.answer()
    await _ask_rate(call.message, state, db_user, grade)


@router.callback_query(F.data == "st:rate_add")
async def cb_rate_add(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await call.message.answer(
        "➕ Пришли оценку и ставку одним сообщением, например:\n"
        "<code>Зачёт 200</code> или <code>н/а -50</code>",
        reply_markup=kb.cancel_menu())
    await state.set_state(Flow.rate_value)
    await state.update_data(rate_key=None)


@router.message(Flow.rate_value, F.text)
async def got_rate(message: Message, state: FSMContext, db_user: dict) -> None:
    text = (message.text or "").strip()
    if text == kb.BTN_CANCEL:
        return
    data = await state.get_data()
    grade = data.get("rate_key")
    user_id = int(db_user["user_id"])
    settings = db.get_settings(user_id)
    currency = settings.get("currency") or "₽"

    if not grade:
        parts = text.split()
        if len(parts) < 2:
            await message.answer("Напиши оценку и число через пробел, например: "
                                 "<code>Зачёт 200</code>")
            return
        grade = " ".join(parts[:-1])
        value = money.parse_amount(parts[-1])
    else:
        value = money.parse_amount(text)

    if value is None:
        await message.answer("Не понял число 🤔 Пришли, например: <code>300</code> или <code>-150</code>")
        return

    rates = dict(settings.get("rates") or {})
    rates[str(grade)] = value
    settings = db.save_settings(user_id, rates=rates)
    await state.clear()
    await message.answer(
        f"✅ Ставка за «{utils.esc(grade)}»: "
        f"<b>{utils.esc(utils.money_text(value, currency, sign=True))}</b>",
        reply_markup=kb.rates_menu(settings.get("rates") or {}, currency))


# ------------------------------------------------------------- коэффициенты
@router.callback_query(F.data == "st:coef")
async def cb_coefficients(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    coefficients = settings.get("coefficients") or {}
    await call.answer()
    lines = ["✖️ <b>Коэффициенты по предметам</b>", ""]
    lines.append("Множитель показывает, во сколько раз умножаются деньги по предмету.")
    lines.append("Например: ставка за «5» 300 ₽, коэффициент по математике ×2 → придёт 600 ₽.")
    lines.append("")
    if coefficients:
        for subject, value in sorted(coefficients.items()):
            lines.append(f"• {utils.esc(money.pretty_subject(subject))} — <b>×{value:g}</b>")
    else:
        lines.append("Пока у всех предметов ×1 (обычные деньги).")
    await call.message.answer("\n".join(lines), reply_markup=kb.coefficients_menu(coefficients))
    await state.clear()


def _sorted_coefficient_keys(coefficients: dict) -> list[str]:
    return [key for key, _ in sorted(coefficients.items())]


@router.callback_query(F.data.startswith("st:coef_del:"))
async def cb_coefficient_delete(call: CallbackQuery, db_user: dict) -> None:
    user_id = int(db_user["user_id"])
    settings = db.get_settings(user_id)
    coefficients = dict(settings.get("coefficients") or {})
    keys = _sorted_coefficient_keys(coefficients)
    try:
        index = int(call.data.split(":")[-1])
        subject = keys[index]
    except (ValueError, IndexError):
        await call.answer("Такого предмета уже нет")
        return
    coefficients.pop(subject, None)
    settings = db.save_settings(user_id, coefficients=coefficients)
    await call.answer(f"Убрал {money.pretty_subject(subject)}")
    try:
        await call.message.edit_reply_markup(reply_markup=kb.coefficients_menu(coefficients))
    except Exception:  # noqa: BLE001
        pass


@router.callback_query(F.data == "st:coef_add")
async def cb_coefficient_add(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    await call.answer()
    subjects = db.known_subjects(int(db_user["user_id"]))
    await call.message.answer(
        "➕ По какому предмету сделать множитель?\n\nНапиши название предмета — я приму "
        "любое написание (регистр и «ё» не важны).",
        reply_markup=kb.subjects_menu(subjects))
    await state.set_state(Flow.coefficient_subject)


@router.message(Flow.coefficient_subject, F.text)
async def got_coefficient_subject(message: Message, state: FSMContext) -> None:
    subject = (message.text or "").strip()
    if subject == kb.BTN_CANCEL:
        return
    if len(subject) > 40:
        await message.answer("Название длинновато. Напиши покороче, например «Математика».")
        return
    await state.update_data(coef_subject=subject)
    await state.set_state(Flow.coefficient_value)
    await message.answer(
        f"Предмет: <b>{utils.esc(money.pretty_subject(subject))}</b>\n\n"
        "Во сколько раз умножать деньги? Пришли число: <code>2</code>, <code>1.5</code>, "
        "<code>3</code>.\n\n<i>×1 — как обычно, ×2 — двойные деньги, ×0.5 — половинные.</i>",
        reply_markup=kb.cancel_menu())


@router.callback_query(F.data.startswith("st:coef_edit:"))
async def cb_coefficient_edit(call: CallbackQuery, state: FSMContext, db_user: dict) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    coefficients = settings.get("coefficients") or {}
    keys = _sorted_coefficient_keys(coefficients)
    try:
        index = int(call.data.split(":")[-1])
        subject = keys[index]
    except (ValueError, IndexError):
        await call.answer("Такого предмета уже нет")
        return
    await call.answer()
    await state.update_data(coef_subject=subject)
    await state.set_state(Flow.coefficient_value)
    await call.message.answer(
        f"✖️ <b>{utils.esc(money.pretty_subject(subject))}</b> — сейчас ×{coefficients[subject]:g}\n\n"
        "Пришли новый множитель (<code>2</code>, <code>1.5</code>, <code>1</code>).",
        reply_markup=kb.cancel_menu())


@router.message(Flow.coefficient_value, F.text)
async def got_coefficient_value(message: Message, state: FSMContext, db_user: dict) -> None:
    text = (message.text or "").strip()
    if text == kb.BTN_CANCEL:
        return
    value = money.parse_multiplier(text)
    if value is None:
        await message.answer("Нужно положительное число, например <code>2</code> или <code>1.5</code>.")
        return
    data = await state.get_data()
    subject = str(data.get("coef_subject") or "").strip()
    if not subject:
        await message.answer("Предмет потерялся. Начни заново: ⚙️ Настройки → ✖️ Коэффициенты")
        await state.clear()
        return

    user_id = int(db_user["user_id"])
    settings = db.get_settings(user_id)
    coefficients = dict(settings.get("coefficients") or {})
    coefficients[money.normalize_subject(subject)] = value
    settings = db.save_settings(user_id, coefficients=coefficients)
    await state.clear()
    await message.answer(
        f"✅ {utils.esc(money.pretty_subject(subject))}: <b>×{value:g}</b>\n\n"
        "Коэффициент применяется ко всем деньгам по этому предмету.",
        reply_markup=kb.coefficients_menu(coefficients))


# ------------------------------------------------------------------- валюта
@router.callback_query(F.data == "st:currency")
async def cb_currency(call: CallbackQuery, db_user: dict) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    await call.answer()
    await call.message.answer("💱 Выбери символ валюты или пришли свой.",
                             reply_markup=kb.currency_menu(settings.get("currency") or "₽"))


@router.callback_query(F.data.startswith("st:cur:"))
async def cb_currency_pick(call: CallbackQuery, db_user: dict) -> None:
    symbol = call.data.split(":", 2)[2]
    settings = db.save_settings(int(db_user["user_id"]), currency=symbol)
    await call.answer(f"Валюта: {symbol}")
    await call.message.answer(f"✅ Валюта: <b>{utils.esc(symbol)}</b>",
                              reply_markup=kb.settings_menu(settings))


@router.callback_query(F.data == "st:cur_custom")
async def cb_currency_custom(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await call.message.answer("✏️ Пришли символ валюты (1–3 знака), например <code>₸</code> "
                              "или <code>kr</code>.", reply_markup=kb.cancel_menu())
    await state.set_state(Flow.currency)


@router.message(Flow.currency, F.text)
async def got_currency(message: Message, state: FSMContext, db_user: dict) -> None:
    symbol = (message.text or "").strip()
    if symbol == kb.BTN_CANCEL:
        return
    if not 1 <= len(symbol) <= 3:
        await message.answer("Нужно 1–3 знака, например <code>₽</code> или <code>kr</code>.")
        return
    settings = db.save_settings(int(db_user["user_id"]), currency=symbol)
    await state.clear()
    await message.answer(f"✅ Валюта: <b>{utils.esc(symbol)}</b>", reply_markup=kb.settings_menu(settings))


# ------------------------------------------------------------- часовой пояс
@router.callback_query(F.data == "st:tz")
async def cb_timezone(call: CallbackQuery, db_user: dict) -> None:
    settings = db.get_settings(int(db_user["user_id"]))
    await call.answer()
    await call.message.answer(
        "🕒 <b>Часовой пояс</b>\n\n"
        "По нему я понимаю, что такое «сегодня» и где кончается месяц.\n"
        f"Сейчас: <b>UTC+{int(settings.get('tz_offset') or 0)}</b>",
        reply_markup=kb.timezone_menu(int(settings.get("tz_offset") or 0)))


@router.callback_query(F.data.startswith("st:tz_set:"))
async def cb_timezone_pick(call: CallbackQuery, db_user: dict) -> None:
    try:
        offset = int(call.data.split(":")[-1])
    except ValueError:
        await call.answer("Не понял сдвиг")
        return
    settings = db.save_settings(int(db_user["user_id"]), tz_offset=offset)
    await call.answer(f"UTC+{offset}")
    await call.message.answer(f"✅ Часовой пояс: <b>UTC+{offset}</b>",
                              reply_markup=kb.settings_menu(settings))


@router.callback_query(F.data == "st:tz_custom")
async def cb_timezone_custom(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await call.message.answer("✏️ Пришли сдвиг от UTC числом от −12 до 14, например <code>3</code>.",
                              reply_markup=kb.cancel_menu())
    await state.set_state(Flow.timezone)


@router.message(Flow.timezone, F.text)
async def got_timezone(message: Message, state: FSMContext, db_user: dict) -> None:
    raw = (message.text or "").strip()
    if raw == kb.BTN_CANCEL:
        return
    value = money.parse_amount(raw)
    if value is None or not -12 <= value <= 14:
        await message.answer("Нужно число от −12 до 14, например <code>3</code>.")
        return
    offset = int(value)
    settings = db.save_settings(int(db_user["user_id"]), tz_offset=offset)
    await state.clear()
    await message.answer(f"✅ Часовой пояс: <b>UTC+{offset}</b>", reply_markup=kb.settings_menu(settings))


# ------------------------------------------------------------------ сброс
@router.callback_query(F.data == "st:reset")
async def cb_reset(call: CallbackQuery, db_user: dict) -> None:
    count = db.count_grades(int(db_user["user_id"]))
    await call.answer()
    await call.message.answer(
        f"🗑 <b>Удалить все оценки?</b>\n\nСейчас в базе {utils.marks(count)}. "
        "Действие необратимо, отчёт после этого будет пустым.",
        reply_markup=kb.reset_menu())


@router.callback_query(F.data == "st:reset_yes")
async def cb_reset_yes(call: CallbackQuery, db_user: dict) -> None:
    removed = db.clear_grades(int(db_user["user_id"]))
    await call.answer("Удалил")
    settings = db.get_settings(int(db_user["user_id"]))
    await call.message.answer(f"🗑 Удалил {utils.marks(removed)}. Настройки не тронул.",
                              reply_markup=kb.settings_menu(settings))
