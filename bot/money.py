# -*- coding: utf-8 -*-
"""
Денежная арифметика: ставки за оценки, коэффициенты по предметам, баланс.

Главная формула:

    сумма = ставка_за_оценку × коэффициент_предмета

Пример: ставка за «5» = 300 ₽, коэффициент по математике = 2 → +600 ₽.
Двойка со ставкой −300 ₽ и коэффициентом 2 → −600 ₽.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone

GRADES = ("5", "4", "3", "2")
GRADE_TITLES = {"5": "Пятёрка", "4": "Четвёрка", "3": "Тройка", "2": "Двойка"}
GRADE_EMOJI = {"5": "🟢", "4": "🔵", "3": "🟡", "2": "🔴"}

MONTHS = ["январь", "февраль", "март", "апрель", "май", "июнь",
          "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь"]

# Оценки-исключения: деньги не начисляются, но в таблицу они попадают
SPECIAL_MARKS = {"зач", "зачет", "н/а", "нб", "осв", "см"}

_CLEAN_RE = re.compile(r"[^\w\s\-]", re.UNICODE)
_SPACES_RE = re.compile(r"\s+")
_MARK_RE = re.compile(r"^\s*([2-5])(?:\s*[+\-])?\s*$")


# ------------------------------------------------------------------- предметы
def normalize_subject(name: str) -> str:
    """«Математика (алгебра)» → «математика алгебра» — ключ для настроек."""
    text = str(name or "").strip().lower().replace("ё", "е")
    text = text.replace("(", " ").replace(")", " ").replace("/", " ")
    text = _CLEAN_RE.sub(" ", text)
    text = _SPACES_RE.sub(" ", text).strip()
    return text


def pretty_subject(name: str) -> str:
    """«математика» → «Математика», «русский язык» → «Русский язык»."""
    text = _SPACES_RE.sub(" ", str(name or "").strip())
    if not text:
        return ""
    parts = []
    for word in text.split(" "):
        parts.append(word[:1].upper() + word[1:] if word else word)
    return " ".join(parts)


# --------------------------------------------------------------------- оценки
def grade_key(value) -> str | None:
    """«5» → «5», «5+» → «5», «4-» → «4». Для «зачёт»/«н/а» вернёт None."""
    if value is None:
        return None
    text = str(value).strip().replace(",", ".").replace(" ", "")
    if not text:
        return None
    match = _MARK_RE.match(text)
    if match:
        return match.group(1)
    digits = re.findall(r"[2-5]", text)
    if len(digits) == 1 and len(text) <= 3:
        return digits[0]
    return None


def is_mark(grade: str) -> bool:
    return grade_key(grade) is not None


def clean_grade(value) -> str:
    """Приводит оценку к аккуратному виду: 5.0 → «5», « зачёт » → «Зачёт»."""
    text = str(value if value is not None else "").strip()
    if not text:
        return ""
    key = grade_key(text)
    if key and text.strip() in (key, key + ".0", key + ",0", key + "+", key + "-",
                                key + " +", key + " -"):
        return key
    if key and re.fullmatch(r"[2-5]\.0+", text):
        return key
    if text.lower().replace("ё", "е") in SPECIAL_MARKS:
        return pretty_subject(text)
    return text[:20]


def average_mark(rows: list[dict]) -> float | None:
    marks = [int(k) for k in (grade_key(row.get("grade")) for row in rows) if k]
    if not marks:
        return None
    return sum(marks) / len(marks)


# ------------------------------------------------------------------ настройки
def sorted_rates(rates: dict) -> list[tuple[str, float]]:
    """Ставки в порядке 5, 4, 3, 2, потом всё остальное."""
    result: list[tuple[str, float]] = []
    for key in GRADES:
        if key in rates:
            result.append((key, float(rates[key])))
    for key in sorted(k for k in rates if k not in GRADES):
        result.append((str(key), float(rates[key])))
    return result


def rate_for(rates: dict, grade: str) -> float | None:
    key = grade_key(grade)
    if key and key in rates:
        return float(rates[key])
    if grade and str(grade).lower() in rates:
        return float(rates[str(grade).lower()])
    return None


def coefficient_for(coefficients: dict, subject: str) -> tuple[float, str | None]:
    """
    Ищет коэффициент для предмета.
    Сначала точное совпадение, потом самое длинное вхождение
    (коэффициент по «математика» сработает и для «Математика (алгебра)»).
    Возвращает (коэффициент, найденный_ключ).
    """
    target = normalize_subject(subject)
    if not target:
        return 1.0, None

    exact = coefficients.get(target)
    if exact is not None:
        return float(exact), target

    best: tuple[int, str] | None = None
    for key in coefficients:
        normalized = normalize_subject(key)
        if not normalized:
            continue
        if normalized in target or target in normalized:
            if best is None or len(normalized) > best[0]:
                best = (len(normalized), key)
    if best is not None:
        return float(coefficients[best[1]]), best[1]
    return 1.0, None


def compute(grade: str, subject: str, settings: dict) -> dict:
    """Считает деньги за одну оценку."""
    rates = settings.get("rates") or {}
    base = rate_for(rates, grade)
    coefficient, matched = coefficient_for(settings.get("coefficients") or {}, subject)
    if base is None:
        return {
            "grade": clean_grade(grade),
            "subject": pretty_subject(subject),
            "coefficient": coefficient,
            "base": 0.0,
            "amount": 0.0,
            "matched": matched,
            "unknown": True,
        }
    return {
        "grade": clean_grade(grade),
        "subject": pretty_subject(subject),
        "coefficient": coefficient,
        "base": float(base),
        "amount": round(float(base) * coefficient, 2),
        "matched": matched,
        "unknown": False,
    }


# --------------------------------------------------------------------- деньги
def total(rows: list[dict]) -> float:
    return round(sum(float(row.get("amount") or 0) for row in rows), 2)


def row_date(row: dict) -> date | None:
    return parse_date(row.get("date"))


def snapshot(settings: dict, rows: list[dict], date_from: date | None = None) -> dict:
    """
    Считает деньги.

    `start_sum`   — стартовая сумма из настроек;
    `opening`     — сколько было на начало периода (стартовая + всё, что раньше периода);
    `change`      — изменение за период;
    `earned`      — сколько начислено за период (только плюсы);
    `spent`       — сколько списано за период (только минусы, по модулю);
    `closing`     — сколько стало.
    """
    start_sum = float(settings.get("start_sum") or 0)
    opening = start_sum
    change = 0.0
    earned = 0.0
    spent = 0.0

    for row in rows:
        amount = float(row.get("amount") or 0)
        current = row_date(row)
        if date_from and current and current < date_from:
            opening += amount
            continue
        change += amount
        if amount >= 0:
            earned += amount
        else:
            spent += -amount

    return {
        "start_sum": round(start_sum, 2),
        "opening": round(opening, 2),
        "change": round(change, 2),
        "earned": round(earned, 2),
        "spent": round(spent, 2),
        "closing": round(opening + change, 2),
    }


def format_money(value: float, currency: str = "₽", sign: bool = False) -> str:
    """1234.5 → «1 235 ₽», -600 → «−600 ₽», +600 → «+600 ₽» (при sign=True)."""
    value = float(value or 0)
    rounded = int(round(abs(value)))
    body = f"{rounded:,}".replace(",", " ")
    if value < 0:
        result = f"−{body}"
    elif sign and value > 0:
        result = f"+{body}"
    else:
        result = body
    return f"{result} {currency}".strip()


def parse_amount(text) -> float | None:
    """«1 200 ₽» → 1200.0, «-300,50» → -300.5."""
    if text is None:
        return None
    cleaned = str(text).strip().replace("\u00a0", "").replace(" ", "").replace(",", ".")
    cleaned = re.sub(r"[^0-9.\-+]", "", cleaned)
    if cleaned in ("", "-", "+", ".", "-.", "+."):
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_multiplier(text) -> float | None:
    """Коэффициент: «2», «x2», «×1,5», «1.5» → число больше нуля."""
    if text is None:
        return None
    cleaned = str(text).strip().lower().replace(",", ".")
    cleaned = cleaned.replace("x", "").replace("×", "").replace("х", "")
    value = parse_amount(cleaned)
    if value is None or value <= 0 or value > 1000:
        return None
    return round(value, 3)


# ---------------------------------------------------------------------- даты
def parse_date(text, today: date | None = None) -> date | None:
    """Понимает 2026-09-15, 15.09.2026, 15.09, 15/09/26, «сегодня», «вчера»."""
    if text is None:
        return None
    if isinstance(text, date) and not isinstance(text, datetime):
        return text
    raw = str(text).strip().lower()
    if not raw:
        return None

    base = today or datetime.now(timezone.utc).date()
    if raw in ("сегодня", "today", "сейчас"):
        return base
    if raw in ("вчера", "yesterday"):
        return base - timedelta(days=1)
    if raw in ("завтра", "tomorrow"):
        return base + timedelta(days=1)

    iso = re.search(r"(\d{4})[-./](\d{1,2})[-./](\d{1,2})", raw)
    if iso:
        return _safe_date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))

    short = re.search(r"(\d{1,2})[-./](\d{1,2})[-./](\d{2,4})", raw)
    if short:
        day, month, year = int(short.group(1)), int(short.group(2)), int(short.group(3))
        if year < 100:
            year += 2000
        return _safe_date(year, month, day)

    day_month = re.search(r"(\d{1,2})[-./](\d{1,2})\b", raw)
    if day_month:
        day, month = int(day_month.group(1)), int(day_month.group(2))
        for year in (base.year, base.year - 1):
            found = _safe_date(year, month, day)
            if found:
                return found
    return None


def _safe_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def today_local(tz_offset: float = 3) -> date:
    return (datetime.now(timezone.utc) + timedelta(hours=float(tz_offset or 0))).date()


def month_bounds(reference: date, shift: int = 0) -> tuple[date, date]:
    """Границы месяца: shift=0 — текущий, -1 — прошлый."""
    year, month = reference.year, reference.month + shift
    while month < 1:
        month += 12
        year -= 1
    while month > 12:
        month -= 12
        year += 1
    first = date(year, month, 1)
    if month == 12:
        last = date(year, 12, 31)
    else:
        last = date(year, month + 1, 1) - timedelta(days=1)
    return first, last


def month_title(reference: date) -> str:
    return f"{MONTHS[reference.month - 1]} {reference.year}"


def period_bounds(kind: str, tz_offset: float = 3) -> tuple[date | None, date | None, str]:
    """Возвращает (с, по, название периода) для отчёта."""
    today = today_local(tz_offset)
    if kind == "month":
        start, end = month_bounds(today)
        return start, end, month_title(today)
    if kind == "prev":
        previous = (today.replace(day=1) - timedelta(days=1))
        start, end = month_bounds(previous)
        return start, end, month_title(previous)
    if kind == "days30":
        return today - timedelta(days=29), today, "последние 30 дней"
    if kind == "year":
        return date(today.year, 1, 1), date(today.year, 12, 31), f"{today.year} год"
    return None, None, "всё время"


def fmt_date(value) -> str:
    parsed = parse_date(value) if not isinstance(value, date) else value
    if not parsed:
        return str(value or "")
    return parsed.strftime("%d.%m.%Y")


def fmt_date_short(value) -> str:
    parsed = parse_date(value) if not isinstance(value, date) else value
    if not parsed:
        return str(value or "")
    return parsed.strftime("%d.%m")
