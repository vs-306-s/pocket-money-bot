# -*- coding: utf-8 -*-
"""Клавиатуры: нижнее меню и inline-кнопки."""
from __future__ import annotations

from aiogram.types import (InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton,
                           ReplyKeyboardMarkup)

from . import money

# --- кнопки нижнего меню ---
BTN_PHOTOS = "📸 Прислать оценки"
BTN_BALANCE = "💰 Баланс"
BTN_REPORT = "📊 Отчёт в Excel"
BTN_LAST = "📋 Последние оценки"
BTN_SETTINGS = "⚙️ Настройки"
BTN_AI = "🤖 Нейросеть"
BTN_HELP = "❓ Помощь"
BTN_CANCEL = "✖️ Отмена"
BTN_MENU = "🏠 Меню"


def main_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_PHOTOS), KeyboardButton(text=BTN_REPORT)],
            [KeyboardButton(text=BTN_BALANCE), KeyboardButton(text=BTN_LAST)],
            [KeyboardButton(text=BTN_SETTINGS), KeyboardButton(text=BTN_AI)],
            [KeyboardButton(text=BTN_HELP)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Пришли фото оценок или выбери пункт меню",
    )


def cancel_menu() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CANCEL)]],
        resize_keyboard=True,
        input_field_placeholder="Пришли значение или отмени ввод",
    )


def subjects_menu(subjects: list[str]) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    for index in range(0, min(len(subjects), 8), 2):
        rows.append([KeyboardButton(text=item) for item in subjects[index:index + 2]])
    rows.append([KeyboardButton(text=BTN_CANCEL)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True,
                               input_field_placeholder="Название предмета")


def grades_menu() -> InlineKeyboardMarkup:
    buttons = [InlineKeyboardButton(text=grade, callback_data=f"gr:new:{grade}")
               for grade in money.GRADES]
    buttons.append(InlineKeyboardButton(text="📝 Зачёт/другое", callback_data="gr:new:other"))
    return InlineKeyboardMarkup(inline_keyboard=[[button] for button in buttons] +
                                [[InlineKeyboardButton(text=BTN_CANCEL, callback_data="gr:cancel_new")]])


def date_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Сегодня", callback_data="gr:date:today"),
         InlineKeyboardButton(text="Вчера", callback_data="gr:date:yesterday")],
        [InlineKeyboardButton(text="📅 Ввести дату", callback_data="gr:date:manual")],
        [InlineKeyboardButton(text=BTN_CANCEL, callback_data="gr:cancel_new")],
    ])


def confirm_entries(count: int) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(text=f"✅ Записать ({count})", callback_data="gr:ok"),
        InlineKeyboardButton(text="❌ Отмена", callback_data="gr:no"),
    ]]
    chunks: list[InlineKeyboardButton] = []
    for index in range(count):
        chunks.append(InlineKeyboardButton(text=f"🗑 {index + 1}", callback_data=f"gr:del:{index}"))
    for start in range(0, len(chunks), 5):
        rows.append(chunks[start:start + 5])
    if count:
        rows.append([InlineKeyboardButton(text="🗑 Убрать все", callback_data="gr:del_all")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def after_save_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Отчёт в Excel", callback_data="rp:month"),
         InlineKeyboardButton(text="💰 Баланс", callback_data="mn:balance")],
    ])


def settings_menu(settings: dict) -> InlineKeyboardMarkup:
    currency = settings.get("currency") or "₽"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💵 Стартовая сумма: {money.format_money(settings.get('start_sum') or 0, currency)}",
                              callback_data="st:start_sum")],
        [InlineKeyboardButton(text="📈 Ставки за оценки", callback_data="st:rates")],
        [InlineKeyboardButton(text="✖️ Коэффициенты по предметам", callback_data="st:coef")],
        [InlineKeyboardButton(text=f"💱 Валюта: {currency}", callback_data="st:currency"),
         InlineKeyboardButton(text="🕒 Часовой пояс", callback_data="st:tz")],
        [InlineKeyboardButton(text="📊 Отчёт в Excel", callback_data="rp:month"),
         InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")],
        [InlineKeyboardButton(text="🗑 Удалить все оценки", callback_data="st:reset")],
    ])


def rates_menu(rates: dict, currency: str = "₽") -> InlineKeyboardMarkup:
    rows = []
    for grade, rate in money.sorted_rates(rates):
        title = money.GRADE_TITLES.get(grade, grade)
        rows.append([InlineKeyboardButton(
            text=f"{money.GRADE_EMOJI.get(grade, '•')} {title}: {money.format_money(rate, currency, sign=True)}",
            callback_data=f"st:rate:{grade}")])
    rows.append([InlineKeyboardButton(text="➕ Добавить другую оценку", callback_data="st:rate_add")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="st:main"),
                 InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def coefficients_menu(coefficients: dict) -> InlineKeyboardMarkup:
    rows = []
    for index, (subject, value) in enumerate(sorted(coefficients.items())):
        rows.append([
            InlineKeyboardButton(text=f"{money.pretty_subject(subject)} ×{value:g}",
                                 callback_data=f"st:coef_edit:{index}"),
            InlineKeyboardButton(text="🗑", callback_data=f"st:coef_del:{index}"),
        ])
    rows.append([InlineKeyboardButton(text="➕ Добавить предмет", callback_data="st:coef_add")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="st:main"),
                 InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def currency_menu(current: str) -> InlineKeyboardMarkup:
    presets = ["₽", "$", "€", "₸", "₴", "Br"]
    rows = [[InlineKeyboardButton(text=("✅ " if item == current else "") + item,
                                  callback_data=f"st:cur:{item}")]
            for item in presets]
    rows.append([InlineKeyboardButton(text="✏️ Свой символ", callback_data="st:cur_custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="st:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def timezone_menu(current: int) -> InlineKeyboardMarkup:
    rows = []
    for offset in range(0, 13, 2):
        mark = "✅ " if offset == current else ""
        rows.append([InlineKeyboardButton(text=f"{mark}UTC+{offset}", callback_data=f"st:tz_set:{offset}")])
    rows.append([InlineKeyboardButton(text="✏️ Другой сдвиг", callback_data="st:tz_custom")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="st:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def reset_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Да, удалить все оценки", callback_data="st:reset_yes")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="st:main")],
    ])


def period_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📅 Этот месяц", callback_data="rp:month"),
         InlineKeyboardButton(text="📅 Прошлый месяц", callback_data="rp:prev")],
        [InlineKeyboardButton(text="📅 Последние 30 дней", callback_data="rp:days30"),
         InlineKeyboardButton(text="📅 Этот год", callback_data="rp:year")],
        [InlineKeyboardButton(text="📚 Всё время", callback_data="rp:all"),
         InlineKeyboardButton(text="✏️ Свой период", callback_data="rp:custom")],
        [InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")],
    ])


def ai_menu(has_key: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🔑 Ввести ключ", callback_data="ai:key")],
        [InlineKeyboardButton(text="🌐 Сменить провайдера", callback_data="ai:provider")],
        [InlineKeyboardButton(text="🧠 Модель", callback_data="ai:model")],
        [InlineKeyboardButton(text="📖 Где взять ключ", callback_data="ai:guide")],
    ]
    if has_key:
        rows.append([InlineKeyboardButton(text="✅ Проверить ключ", callback_data="ai:check"),
                     InlineKeyboardButton(text="🗑 Удалить ключ", callback_data="ai:clear")])
    rows.append([InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def providers_menu() -> InlineKeyboardMarkup:
    from . import ai as ai_module

    rows = []
    for key, info in ai_module.PROVIDERS.items():
        mark = "🆓 " if info.get("free") else "💳 "
        rows.append([InlineKeyboardButton(
            text=f"{mark}{info['title']}" + ("" if info.get("vision") else " (без фото)"),
            callback_data=f"prov:{key}")])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="ai:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def list_entries_menu(rows: list[dict], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    buttons: list[list[InlineKeyboardButton]] = []
    start = page * per_page
    chunk = rows[start:start + per_page]
    for offset, entry in enumerate(chunk):
        number = start + offset + 1
        buttons.append([InlineKeyboardButton(
            text=f"🗑 {number}. {money.fmt_date_short(entry.get('date'))} · "
                 f"{entry.get('subject')} · {entry.get('grade')}",
            callback_data=f"lg:del:{entry.get('id')}")])
    navigation = []
    if page > 0:
        navigation.append(InlineKeyboardButton(text="⬅️", callback_data=f"lg:page:{page - 1}"))
    if start + per_page < len(rows):
        navigation.append(InlineKeyboardButton(text="➡️", callback_data=f"lg:page:{page + 1}"))
    if navigation:
        buttons.append(navigation)
    buttons.append([InlineKeyboardButton(text="↩️ Убрать последнюю", callback_data="lg:undo")])
    buttons.append([InlineKeyboardButton(text="📊 Отчёт в Excel", callback_data="rp:month"),
                    InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_to_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")],
    ])


def retry_menu(has_key: bool = True) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text="🔁 Попробовать снова", callback_data="gr:retry")]]
    rows.append([InlineKeyboardButton(
        text="✅ Проверить ключ" if has_key else "🔑 Подключить ключ",
        callback_data="ai:check" if has_key else "ai:key")])
    rows.append([InlineKeyboardButton(text="📖 Где взять ключ", callback_data="ai:guide"),
                 InlineKeyboardButton(text="🏠 Меню", callback_data="mn:main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)
