# -*- coding: utf-8 -*-
"""Готовые «представления» — тексты, которые собираются из данных базы."""
from __future__ import annotations

from datetime import date

from . import db, money, utils


def period_rows(user_id: int, date_from: date | None = None, date_to: date | None = None) -> list[dict]:
    return db.list_grades(
        user_id,
        date_from.isoformat() if date_from else None,
        date_to.isoformat() if date_to else None,
    )


def in_period(entry: dict, date_from: date | None, date_to: date | None) -> bool:
    current = money.parse_date(entry.get("date"))
    if not current:
        return False
    if date_from and current < date_from:
        return False
    if date_to and current > date_to:
        return False
    return True


def entry_line(entry: dict, settings: dict, index: int | None = None,
               with_coefficient: bool = True) -> str:
    currency = settings.get("currency") or "₽"
    prefix = f"{index}. " if index else ""
    coefficient = float(entry.get("coefficient") or 1)
    coefficient_part = ""
    if with_coefficient and abs(coefficient - 1) > 1e-9:
        coefficient_part = f" · {utils.coefficient_text(coefficient)}"
    amount = float(entry.get("amount") or 0)
    return (f"{prefix}{money.fmt_date_short(entry.get('date'))} · "
            f"{utils.esc(entry.get('subject'))} · "
            f"<b>{utils.esc(entry.get('grade'))}</b>{coefficient_part} → "
            f"<b>{utils.esc(utils.money_text(amount, currency, sign=True))}</b>")


def balance_text(user_id: int) -> str:
    settings = db.get_settings(user_id)
    currency = settings.get("currency") or "₽"
    rows = db.list_grades(user_id)
    stats = money.snapshot(settings, rows)

    today = utils.user_today(user_id)
    month_start, month_end = money.month_bounds(today)
    month_entries = [entry for entry in rows if in_period(entry, month_start, month_end)]
    month_change = money.total(month_entries)
    average = money.average_mark(rows)

    lines = [
        "💰 <b>Баланс</b>",
        "",
        f"Стартовая сумма: <b>{utils.esc(utils.money_text(stats['start_sum'], currency))}</b>",
        f"Оценок записано: <b>{utils.marks(len(rows))}</b>",
    ]
    if average is not None:
        lines.append(f"Средний балл: <b>{average:.2f}</b>")
    lines += [
        "",
        f"📈 Начислено: <b>{utils.esc(utils.money_text(stats['earned'], currency, sign=True))}</b>",
        f"📉 Списано: <b>{utils.esc(utils.money_text(-stats['spent'], currency, sign=True))}</b>",
        "━━━━━━━━━━━━━━━━",
        f"💰 <b>Остаток: {utils.esc(utils.money_text(stats['closing'], currency))}</b>",
        "",
        f"<i>За {money.month_title(today)}: "
        f"{utils.esc(utils.money_text(month_change, currency, sign=True))} "
        f"({utils.marks(len(month_entries))})</i>",
    ]
    return "\n".join(lines)


def ledger_text(rows: list[dict], currency: str = "₽", page: int = 0,
                per_page: int = 5) -> str:
    if not rows:
        return ("📋 <b>Записей пока нет</b>\n\n"
                "Пришли фото дневника или добавь оценку вручную: /add")
    lines = ["📋 <b>Последние оценки</b>", ""]
    start = page * per_page
    for offset, entry in enumerate(rows[start:start + per_page]):
        coefficient = float(entry.get("coefficient") or 1)
        coefficient_part = "" if abs(coefficient - 1) < 1e-9 else f" {utils.coefficient_text(coefficient)}"
        amount = float(entry.get("amount") or 0)
        lines.append(
            f"<b>{start + offset + 1}.</b> {money.fmt_date(entry.get('date'))} · "
            f"{utils.esc(entry.get('subject'))} · <b>{utils.esc(entry.get('grade'))}</b>"
            f"{coefficient_part} · {utils.esc(utils.money_text(amount, currency, sign=True))}"
        )
    lines += ["", f"Всего записей: <b>{len(rows)}</b>. Нажми на запись, чтобы удалить её."]
    return "\n".join(lines)


def preview_text(entries: list[dict], settings: dict, note: str = "") -> str:
    """Предпросмотр распознанных оценок перед записью."""
    currency = settings.get("currency") or "₽"
    if not entries:
        return ("😕 <b>Оценки на фото не нашлись.</b>\n\n"
                "Попробуй снять страницу целиком, при ровном свете и без бликов. "
                "Или добавь оценки вручную: /add")

    prepared = [money.compute(entry["grade"], entry["subject"], settings) for entry in entries]
    previews = []
    for entry, computed in zip(entries, prepared):
        previews.append({
            **entry,
            "coefficient": computed["coefficient"],
            "base": computed["base"],
            "amount": computed["amount"],
        })

    earned = sum(item["amount"] for item in previews if item["amount"] > 0)
    spent = sum(-item["amount"] for item in previews if item["amount"] < 0)
    unknown = [item for item in previews if item.get("unknown")]

    lines = [f"📸 <b>Нашёл {utils.marks(len(previews))}.</b> Проверь, всё ли верно:", ""]
    for index, item in enumerate(previews, 1):
        coefficient = float(item.get("coefficient") or 1)
        coefficient_part = "" if abs(coefficient - 1) < 1e-9 else f" · {utils.coefficient_text(coefficient)}"
        comment = f" <i>({utils.esc(item['comment'])})</i>" if item.get("comment") else ""
        lines.append(
            f"<b>{index}.</b> {money.fmt_date_short(item['date'])} · {utils.esc(item['subject'])} · "
            f"<b>{utils.esc(item['grade'])}</b>{coefficient_part} → "
            f"<b>{utils.esc(utils.money_text(item['amount'], currency, sign=True))}</b>{comment}"
        )

    lines += [
        "",
        f"📈 Начислится: <b>{utils.esc(utils.money_text(earned, currency, sign=True))}</b>",
        f"📉 Спишется: <b>{utils.esc(utils.money_text(-spent, currency, sign=True))}</b>",
        f"💰 Итого: <b>{utils.esc(utils.money_text(earned - spent, currency, sign=True))}</b>",
    ]
    if unknown:
        subjects = ", ".join(utils.esc(item["subject"]) for item in unknown[:5])
        lines += ["", f"⚠️ Для {subjects} не задана ставка за оценку — такие записи пойдут с нулём. "
                      "Ставки правятся в ⚙️ Настройках."]
    if note:
        lines += ["", f"💬 <i>{utils.esc(note)}</i>"]
    lines += ["", "Нажимай «✅ Записать», если всё верно, или убери лишнее кнопкой 🗑."]
    return "\n".join(lines)


def saved_text(saved: list[dict], settings: dict, before: float, after: float) -> str:
    currency = settings.get("currency") or "₽"
    earned = sum(float(item.get("amount") or 0) for item in saved if float(item.get("amount") or 0) >= 0)
    spent = sum(-float(item.get("amount") or 0) for item in saved if float(item.get("amount") or 0) < 0)
    change = earned - spent
    lines = [
        f"✅ <b>Записал {utils.marks(len(saved))}</b>",
        "",
        f"📈 Начислено: <b>{utils.esc(utils.money_text(earned, currency, sign=True))}</b>",
        f"📉 Списано: <b>{utils.esc(utils.money_text(-spent, currency, sign=True))}</b>",
        f"💰 Изменение: <b>{utils.esc(utils.money_text(change, currency, sign=True))}</b>",
        "",
        f"Было: {utils.esc(utils.money_text(before, currency))} → "
        f"Стало: <b>{utils.esc(utils.money_text(after, currency))}</b>",
    ]
    return "\n".join(lines)


def report_caption(rows: list[dict], settings: dict, stats: dict, period_title: str) -> str:
    currency = settings.get("currency") or "₽"
    return "\n".join([
        f"📊 <b>Отчёт за {utils.esc(period_title)}</b>",
        "",
        f"Оценок в таблице: <b>{len(rows)}</b>",
        f"Начислено: <b>{utils.esc(utils.money_text(stats['earned'], currency, sign=True))}</b>",
        f"Списано: <b>{utils.esc(utils.money_text(-stats['spent'], currency, sign=True))}</b>",
        f"Итог за период: <b>{utils.esc(utils.money_text(stats['change'], currency, sign=True))}</b>",
        f"Остаток на конец: <b>{utils.esc(utils.money_text(stats['closing'], currency))}</b>",
        "",
        "<i>В файле три листа: «Оценки» — таблица, «Сводка» — итоги и диаграмма, "
        "«Настройки» — с чем считалось.</i>",
    ])
