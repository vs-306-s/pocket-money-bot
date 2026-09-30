# -*- coding: utf-8 -*-
"""
Самопроверка бота: считает деньги на примерах и собирает тестовый отчёт Excel.

Запуск:   python scripts/selftest.py

Рабочая база не трогается — всё пишется во временную папку.
Файл полезен и как пример работы с модулями money/db/excel.
"""
from __future__ import annotations

import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Русская консоль часто в cp1251 — без этого print с эмодзи падает
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TMP = tempfile.mkdtemp(prefix="pmb-selftest-")
os.environ["DATA_DIR"] = TMP

from bot import config, db, excel, money, utils  # noqa: E402

CHECKS = 0


def check(condition: bool, label: str) -> None:
    global CHECKS
    CHECKS += 1
    if not condition:
        raise AssertionError(f"❌ {label}")
    print(f"  ✅ {label}")


def main() -> int:
    print(f"🧪 Временная папка: {TMP}")
    config.ensure_dirs()
    db.init()

    print("\n1) Разбор оценок, дат и чисел")
    check(money.grade_key("5") == "5", "«5» → оценка 5")
    check(money.grade_key("5+") == "5", "«5+» → оценка 5")
    check(money.grade_key("4-") == "4", "«4-» → оценка 4")
    check(money.grade_key("зачёт") is None, "«зачёт» → не цифра")
    check(money.clean_grade(5.0) == "5", "5.0 → «5»")
    check(money.clean_grade(" зачёт ") == "Зачёт", "« зачёт » → «Зачёт»")
    check(money.parse_date("15.09.2026") == date(2026, 9, 15), "15.09.2026")
    check(money.parse_date("2026-09-15") == date(2026, 9, 15), "2026-09-15")
    check(money.parse_date("вчера") == utils.today() - timedelta(days=1), "«вчера»")
    check(money.parse_amount("1 200 ₽") == 1200, "«1 200 ₽» → 1200")
    check(money.parse_amount("-300,5") == -300.5, "«-300,5» → -300.5")
    check(money.parse_multiplier("×1,5") == 1.5, "«×1,5» → 1.5")
    check(money.parse_multiplier("0") is None, "нулевой коэффициент → ошибка")

    print("\n2) Ставки и коэффициенты")
    settings = {
        "start_sum": 1000,
        "currency": "₽",
        "rates": {"5": 300, "4": 150, "3": -100, "2": -300},
        "coefficients": {"математика": 2, "физика": 1.5},
        "tz_offset": 3,
    }
    five = money.compute("5", "Математика", settings)
    check(five["amount"] == 600, "пятёрка по математике: 300 × 2 = 600")
    four = money.compute("4", "Физика", settings)
    check(four["amount"] == 225, "четвёрка по физике: 150 × 1.5 = 225")
    two = money.compute("2", "История", settings)
    check(two["amount"] == -300, "двойка по истории: −300 × 1 = −300")
    alias = money.coefficient_for(settings["coefficients"], "Математика (алгебра)")
    check(alias[0] == 2.0, "коэффициент по «математика» работает для «Математика (алгебра)»")
    check(money.coefficient_for(settings["coefficients"], "История")[0] == 1.0,
          "без коэффициента предмет считается ×1")
    zero = money.compute("5", "История литературы", {"rates": {}, "coefficients": {}})
    check(zero["unknown"] is True and zero["amount"] == 0, "нет ставки → 0 и пометка")

    print("\n3) База и баланс")
    user_id = 555
    db.touch_user(user_id, "test", "Иван Тестов")
    check(db.get_settings(user_id)["start_sum"] == config.get("default_start_sum"),
          "новому пользователю выдаются настройки по умолчанию")
    settings = db.save_settings(user_id, start_sum=1000, currency="₽",
                                rates={"5": 300, "4": 150, "3": -100, "2": -300},
                                coefficients={"математика": 2})
    today = utils.today()
    rows = []
    for offset, (grade, subject) in enumerate(
            [("5", "Математика"), ("4", "История"), ("3", "Физика"), ("5", "История")]):
        computed = money.compute(grade, subject, settings)
        rows.append({
            "date": (today - timedelta(days=offset)).isoformat(),
            "subject": computed["subject"],
            "grade": computed["grade"],
            "comment": "контрольная" if offset == 0 else "",
            "coefficient": computed["coefficient"],
            "base": computed["base"],
            "amount": computed["amount"],
        })
    saved = db.add_grades(user_id, rows, source="photo")
    check(len(saved) == 4 and all(item["id"] for item in saved), "оценки записались с id")
    check(db.count_grades(user_id) == 4, "в базе 4 оценки")
    check("Математика" in db.known_subjects(user_id), "предметы подтягиваются в подсказки")

    all_rows = db.list_grades(user_id)
    stats = money.snapshot(settings, all_rows)
    # 5 математика → 600, 4 история → 150, 3 физика → −100, 5 история → 300
    expected_change = 600 + 150 - 100 + 300
    check(stats["change"] == expected_change, f"изменение за период = {expected_change}")
    check(stats["earned"] == 1050, "начислено 1050")
    check(stats["spent"] == 100, "списано 100")
    check(stats["closing"] == 1000 + expected_change, "остаток = стартовая + изменение")
    check(money.average_mark(all_rows) == 4.25, "средний балл = 4.25")

    removed = db.delete_last(user_id)
    check(removed is not None and db.count_grades(user_id) == 3, "последняя запись удаляется")
    db.add_grades(user_id, [rows[-1]])
    check(db.count_grades(user_id) == 4, "запись вернулась на место")

    print("\n4) Отчёт Excel")
    month_from, month_to = money.month_bounds(today)
    period_rows = db.list_grades(user_id, month_from.isoformat(), month_to.isoformat())
    stats = money.snapshot(settings, db.list_grades(user_id), month_from)
    path = os.path.join(TMP, "report.xlsx")
    excel.build_report(path, period_rows, stats, settings, period_title=money.month_title(today),
                       user_label="Иван Тестов", tz_offset=3, ai=db.get_ai(user_id))
    check(os.path.exists(path) and os.path.getsize(path) > 5000, "файл отчёта создан")

    from openpyxl import load_workbook

    workbook = load_workbook(path)
    check(workbook.sheetnames == ["Оценки", "Сводка", "Настройки"],
          "три листа: Оценки, Сводка, Настройки")
    sheet = workbook["Оценки"]
    check(sheet["A4"].value == "Дата" and sheet["B4"].value == "Предмет",
          "шапка начинается с «Дата», «Предмет»")
    check(sheet["C4"].value == "Оценка" and sheet["D4"].value == "Коэффициент",
          "третий и четвёртый столбцы — «Оценка» и «Коэффициент»")
    check(isinstance(sheet["A5"].value, date), "в первой колонке настоящая дата")
    check(sheet.freeze_panes == "A5", "шапка закреплена")
    check(sheet.auto_filter.ref is not None, "включён автофильтр")
    summary = workbook["Сводка"]
    labels = [summary.cell(row=row, column=1).value for row in range(4, 12)]
    check("Остаток на конец периода" in labels, "в сводке есть остаток на конец")
    check(len(summary._charts) == 1, "на листе «Сводка» построена диаграмма")
    check(workbook["Настройки"]["A3"].value == "Стартовая сумма", "лист «Настройки» заполнен")

    print("\n5) Интерфейс бота")
    from aiogram import Dispatcher

    from bot import keyboards as kb, texts, views
    from bot.handlers import ROUTERS
    from bot.middlewares import DbUserMiddleware

    dispatcher = Dispatcher()
    for module in ROUTERS:
        dispatcher.include_router(module.router)
    check(len(ROUTERS) == 6, f"подключено роутеров: {len(ROUTERS)}")
    check(DbUserMiddleware() is not None, "middleware пользователя создаётся")

    previews = views.preview_text(
        [{"date": today.isoformat(), "subject": "Математика", "grade": "5", "comment": "контрольная"},
         {"date": today.isoformat(), "subject": "История", "grade": "3", "comment": ""}],
        settings)
    check("Нашёл 2 оценки" in previews and "600" in previews, "предпросмотр распознанных оценок")
    check("Остаток" in views.balance_text(user_id), "баланс собирается")
    check("Математика" in views.ledger_text(db.list_grades(user_id, newest_first=True), "₽"),
          "список записей собирается")
    check("Отчёт за" in views.report_caption(period_rows, settings, stats, "сентябрь 2026"),
          "подпись к отчёту собирается")
    check("ключ" in texts.KEY_GUIDE.lower() and "openrouter" in texts.KEY_GUIDE.lower(),
          "гайд по ключам на месте")

    boards = [
        kb.main_menu(), kb.cancel_menu(), kb.subjects_menu(["Математика", "Физика"]),
        kb.grades_menu(), kb.date_menu(), kb.confirm_entries(7), kb.after_save_menu(),
        kb.settings_menu(settings), kb.rates_menu(settings["rates"], "₽"),
        kb.coefficients_menu({"математика": 2}), kb.currency_menu("₽"), kb.timezone_menu(3),
        kb.reset_menu(), kb.period_menu(), kb.ai_menu(True), kb.ai_menu(False),
        kb.providers_menu(), kb.retry_menu(True),
        kb.list_entries_menu([{"id": 1, "date": today.isoformat(),
                               "subject": "Математика", "grade": "5"}], 0, 5),
        kb.back_to_menu(),
    ]
    check(all(board is not None for board in boards), f"клавиатуры собираются ({len(boards)} шт.)")

    too_long = []
    for board in boards:
        for row in getattr(board, "inline_keyboard", None) or []:
            for button in row:
                data = getattr(button, "callback_data", None)
                if data and len(str(data).encode("utf-8")) > 64:
                    too_long.append(data)
    check(not too_long, "callback_data везде короче 64 байт")

    print(f"\n🎉 Все проверки прошли: {CHECKS}")
    print(f"📄 Тестовый отчёт: {path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AssertionError as error:
        print(f"\n{error}")
        raise SystemExit(1)
