# -*- coding: utf-8 -*-
"""
Сборка красивого отчёта в Excel (openpyxl).

Три листа:
  * «Оценки»   — таблица: дата · предмет · оценка · коэффициент · ставка · сумма · комментарий;
  * «Сводка»   — деньги, итоги по предметам и оценкам, диаграмма;
  * «Настройки»— с какими ставками и коэффициентами считался отчёт.

openpyxl импортируется внутри функции: если пакет не установлен, бот всё равно
запустится и просто скажет, что нужно доустановить.
"""
from __future__ import annotations

import os
from datetime import date, datetime

from . import money, utils

DARK = "12324F"
ACCENT = "1F6FB2"
LIGHT = "EEF4FA"
BAND = "F7FAFD"
GREEN_FONT = "146C39"
GREEN_FILL = "E3F5E9"
RED_FONT = "B3261E"
RED_FILL = "FDE8E6"
GREY = "7A8089"
GRADE_COLORS = {"5": "1B7A3D", "4": "1F6FB2", "3": "B26A00", "2": "B3261E"}

SHEET_GRADES = "Оценки"
SHEET_SUMMARY = "Сводка"
SHEET_SETTINGS = "Настройки"


def _need_openpyxl():
    try:
        __import__("openpyxl")
    except ImportError as error:  # pragma: no cover
        raise RuntimeError(
            "Для отчётов нужен пакет openpyxl.\n"
            "Установи его командой:  pip install openpyxl"
        ) from error


def _money_format(currency: str) -> str:
    symbol = (currency or "₽").replace('"', "")
    return f'#,##0" {symbol}";-#,##0" {symbol}"'


def _subject_groups(rows: list[dict]) -> dict:
    groups: dict[str, dict] = {}
    for row in rows:
        subject = str(row.get("subject") or "—")
        group = groups.setdefault(subject, {
            "count": 0, "sum": 0.0, "earned": 0.0, "spent": 0.0,
            "coefficient": float(row.get("coefficient") or 1), "marks": [],
        })
        amount = float(row.get("amount") or 0)
        group["count"] += 1
        group["sum"] += amount
        if amount >= 0:
            group["earned"] += amount
        else:
            group["spent"] += -amount
        key = money.grade_key(row.get("grade"))
        if key:
            group["marks"].append(int(key))
    return groups


def _grade_groups(rows: list[dict]) -> dict:
    groups: dict[str, dict] = {}
    for row in rows:
        key = money.grade_key(row.get("grade")) or str(row.get("grade") or "—")
        group = groups.setdefault(key, {"count": 0, "sum": 0.0, "rate": float(row.get("base") or 0)})
        group["count"] += 1
        group["sum"] += float(row.get("amount") or 0)
    order = {key: index for index, key in enumerate(money.GRADES)}
    return dict(sorted(groups.items(), key=lambda item: order.get(item[0], 99)))


# ------------------------------------------------------------------ лист №1
def _build_grades_sheet(ws, rows, stats, currency, period_title, user_label):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.formatting.rule import CellIsRule
    from openpyxl.worksheet.properties import PageSetupProperties

    thin = Side(style="thin", color="D7DEE6")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    money_fmt = _money_format(currency)

    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = ACCENT
    ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0

    widths = {"A": 13, "B": 28, "C": 10, "D": 13, "E": 13, "F": 16, "G": 34}
    for column, width in widths.items():
        ws.column_dimensions[column].width = width

    # заголовок
    ws.merge_cells("A1:G1")
    title = ws["A1"]
    title.value = f"Карманные деньги — отчёт за {period_title}"
    title.font = Font(bold=True, size=15, color="FFFFFF")
    title.fill = PatternFill("solid", fgColor=DARK)
    title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:G2")
    subtitle = ws["A2"]
    parts = []
    if user_label:
        parts.append(user_label)
    parts.append(f"выгружено {utils.local_now().strftime('%d.%m.%Y в %H:%M')}")
    if not rows:
        parts.append("оценок за период нет")
    subtitle.value = "  ·  ".join(parts)
    subtitle.font = Font(italic=True, size=10, color=GREY)
    subtitle.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 8

    headers = ["Дата", "Предмет", "Оценка", "Коэффициент", "Ставка", "Сумма", "Комментарий"]
    header_row = 4
    for index, text in enumerate(headers, start=1):
        cell = ws.cell(row=header_row, column=index, value=text)
        cell.font = Font(bold=True, size=11, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=ACCENT)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = box
    ws.row_dimensions[header_row].height = 30

    row_index = header_row
    for position, entry in enumerate(rows):
        row_index += 1
        band = position % 2 == 1
        fill = PatternFill("solid", fgColor=BAND) if band else None

        parsed = money.parse_date(entry.get("date"))
        cell = ws.cell(row=row_index, column=1,
                       value=parsed or str(entry.get("date") or ""))
        if isinstance(cell.value, date):
            cell.number_format = "DD.MM.YYYY"
        cell.alignment = Alignment(horizontal="center", vertical="center")

        subject_cell = ws.cell(row=row_index, column=2, value=str(entry.get("subject") or "—"))
        subject_cell.font = Font(bold=True, size=11)
        subject_cell.alignment = Alignment(vertical="center")

        grade = money.clean_grade(entry.get("grade"))
        grade_cell = ws.cell(row=row_index, column=3, value=grade)
        key = money.grade_key(grade)
        grade_cell.font = Font(bold=True, size=11, color=GRADE_COLORS.get(key or "", "333333"))
        grade_cell.alignment = Alignment(horizontal="center", vertical="center")

        coefficient = float(entry.get("coefficient") or 1)
        coefficient_cell = ws.cell(row=row_index, column=4, value=coefficient)
        coefficient_cell.number_format = '0.###"×"'
        coefficient_cell.alignment = Alignment(horizontal="center", vertical="center")

        base = float(entry.get("base") or 0)
        base_cell = ws.cell(row=row_index, column=5, value=base if base else "—")
        if isinstance(base_cell.value, (int, float)):
            base_cell.number_format = money_fmt
        base_cell.alignment = Alignment(horizontal="center", vertical="center")

        amount = float(entry.get("amount") or 0)
        amount_cell = ws.cell(row=row_index, column=6, value=amount)
        amount_cell.number_format = money_fmt
        amount_cell.font = Font(bold=True, size=11,
                                color=GREEN_FONT if amount >= 0 else RED_FONT)
        amount_cell.alignment = Alignment(horizontal="right", vertical="center")

        comment_cell = ws.cell(row=row_index, column=7, value=str(entry.get("comment") or ""))
        comment_cell.font = Font(size=9, color=GREY)
        comment_cell.alignment = Alignment(vertical="center", wrap_text=True)

        for column in range(1, 8):
            target = ws.cell(row=row_index, column=column)
            target.border = box
            if fill is not None:
                target.fill = fill

    last_data_row = row_index
    if not rows:
        row_index += 1
        ws.merge_cells(start_row=row_index, start_column=1, end_row=row_index, end_column=7)
        empty = ws.cell(row=row_index, column=1,
                        value="За этот период оценок нет — пришли фото дневника боту.")
        empty.font = Font(italic=True, color=GREY)
        empty.alignment = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[row_index].height = 22

    # итоги
    row_index += 1
    ws.merge_cells(start_row=row_index, start_column=1, end_row=row_index, end_column=5)
    label = ws.cell(row=row_index, column=1,
                    value=f"ИТОГО за период  ({utils.marks(len(rows))})")
    label.font = Font(bold=True, size=11, color="FFFFFF")
    label.fill = PatternFill("solid", fgColor=DARK)
    label.alignment = Alignment(horizontal="right", vertical="center")

    total_cell = ws.cell(row=row_index, column=6)
    if rows:
        total_cell.value = f"=SUM(F{header_row + 1}:F{last_data_row})"
    else:
        total_cell.value = 0
    total_cell.number_format = money_fmt
    total_cell.font = Font(bold=True, size=12, color="FFFFFF")
    total_cell.fill = PatternFill("solid", fgColor=DARK)
    total_cell.alignment = Alignment(horizontal="right", vertical="center")

    tail = ws.cell(row=row_index, column=7)
    tail.fill = PatternFill("solid", fgColor=DARK)
    ws.row_dimensions[row_index].height = 24

    if rows:
        _add_negative_note(ws, row_index + 2, stats, currency)

    ws.freeze_panes = f"A{header_row + 1}"
    if rows:
        ws.auto_filter.ref = f"A{header_row}:G{last_data_row}"

    first = header_row + 1
    if rows:
        for operator, value, color, back in (
            ("greaterThan", "0", GREEN_FONT, GREEN_FILL),
            ("lessThan", "0", RED_FONT, RED_FILL),
        ):
            ws.conditional_formatting.add(
                f"F{first}:F{last_data_row}",
                CellIsRule(operator=operator, formula=[value],
                           font=Font(bold=True, color=color),
                           fill=PatternFill("solid", bgColor=back)),
            )
    return ws


def _add_negative_note(ws, row: int, stats: dict, currency: str) -> None:
    from openpyxl.styles import Alignment, Font

    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=7)
    cell = ws.cell(row=row, column=1)
    cell.value = (
        f"Как считалось: сумма = ставка за оценку × коэффициент предмета.  "
        f"Начислено: {utils.money_text(stats['earned'], currency)}   ·   "
        f"Списано: −{utils.money_text(stats['spent'], currency)}   ·   "
        f"Итог за период: {utils.money_text(stats['change'], currency, sign=True)}"
    )
    cell.font = Font(size=9, italic=True, color=GREY)
    cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[row].height = 18


# ------------------------------------------------------------------ лист №2
def _build_summary_sheet(ws, rows, stats, settings, currency, period_title, user_label):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.chart import BarChart, Reference

    thin = Side(style="thin", color="D7DEE6")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    money_fmt = _money_format(currency)

    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = "3FA45B"
    for column, width in {"A": 30, "B": 18, "C": 12, "D": 14, "E": 16,
                          "F": 16, "G": 16, "H": 3, "I": 3}.items():
        ws.column_dimensions[column].width = width

    ws.merge_cells("A1:G1")
    title = ws["A1"]
    title.value = f"Сводка за {period_title}"
    title.font = Font(bold=True, size=15, color="FFFFFF")
    title.fill = PatternFill("solid", fgColor=DARK)
    title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:G2")
    subtitle = ws["A2"]
    subtitle.value = (f"{user_label + '  ·  ' if user_label else ''}"
                      f"сформировано {utils.local_now().strftime('%d.%m.%Y в %H:%M')}")
    subtitle.font = Font(italic=True, size=10, color=GREY)
    subtitle.alignment = Alignment(horizontal="center", vertical="center")

    average = money.average_mark(rows)
    cards = [
        ("Стартовая сумма (из настроек)", stats["start_sum"], False),
        ("На начало периода", stats["opening"], False),
        ("Начислено за период", stats["earned"], False),
        ("Списано за период", -stats["spent"], False),
        ("Изменение за период", stats["change"], True),
        ("Остаток на конец периода", stats["closing"], True),
    ]
    row = 4
    for label, value, highlight in cards:
        name_cell = ws.cell(row=row, column=1, value=label)
        name_cell.font = Font(bold=highlight, size=11)
        name_cell.alignment = Alignment(vertical="center")
        name_cell.fill = PatternFill("solid", fgColor=LIGHT)
        name_cell.border = box

        value_cell = ws.cell(row=row, column=2, value=float(value))
        value_cell.number_format = money_fmt
        value_cell.alignment = Alignment(horizontal="right", vertical="center")
        value_cell.border = box
        if highlight:
            color = GREEN_FONT if value >= 0 else RED_FONT
            value_cell.font = Font(bold=True, size=12, color=color)
            value_cell.fill = PatternFill("solid", fgColor=GREEN_FILL if value >= 0 else RED_FILL)
        ws.row_dimensions[row].height = 22
        row += 1

    ws.cell(row=row, column=1, value="Средний балл за период").font = Font(size=11)
    average_cell = ws.cell(row=row, column=2,
                           value=round(average, 2) if average is not None else "—")
    if average is not None:
        average_cell.number_format = "0.00"
    average_cell.alignment = Alignment(horizontal="right")
    average_cell.border = box
    ws.row_dimensions[row].height = 22
    row += 2

    # ------------------------------------------------------- по предметам
    groups = _subject_groups(rows)
    ws.cell(row=row, column=1, value="По предметам").font = Font(bold=True, size=12, color=DARK)
    row += 1
    subject_header = row
    for index, text in enumerate(["Предмет", "Коэффициент", "Оценок", "Средний балл",
                                  "Начислено", "Списано", "Итого"], start=1):
        cell = ws.cell(row=row, column=index, value=text)
        cell.font = Font(bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=ACCENT)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = box
    ws.row_dimensions[row].height = 26
    row += 1

    ordered = sorted(groups.items(), key=lambda item: (-item[1]["sum"], item[0]))
    for position, (subject, group) in enumerate(ordered):
        band = PatternFill("solid", fgColor=BAND) if position % 2 else None
        mark_average = (sum(group["marks"]) / len(group["marks"])) if group["marks"] else None
        values = [
            subject,
            float(group["coefficient"]),
            int(group["count"]),
            round(mark_average, 2) if mark_average is not None else "—",
            float(group["earned"]),
            -float(group["spent"]),
            float(group["sum"]),
        ]
        for column, value in enumerate(values, start=1):
            cell = ws.cell(row=row, column=column, value=value)
            cell.border = box
            if band is not None:
                cell.fill = band
            if column == 1:
                cell.font = Font(bold=True, size=10)
            elif column in (2, 3, 4):
                cell.alignment = Alignment(horizontal="center")
                cell.number_format = '0.###"×"' if column == 2 else (
                    "0.00" if column == 4 else "0")
            else:
                cell.number_format = money_fmt
                cell.alignment = Alignment(horizontal="right")
                cell.font = Font(size=10, color=GREEN_FONT if value >= 0 else RED_FONT)
            if column == 7:
                cell.font = Font(bold=True, size=10,
                                 color=GREEN_FONT if value >= 0 else RED_FONT)
        row += 1

    if not rows:
        ws.cell(row=row, column=1, value="нет данных").font = Font(italic=True, color=GREY)
        row += 1
    subject_last = row - 1

    # --------------------------------------------------------- по оценкам
    row += 1
    ws.cell(row=row, column=1, value="По оценкам").font = Font(bold=True, size=12, color=DARK)
    row += 1
    for index, text in enumerate(["Оценка", "Ставка", "Сколько раз", "Всего"], start=1):
        cell = ws.cell(row=row, column=index, value=text)
        cell.font = Font(bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=ACCENT)
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = box
    row += 1
    grade_rows = _grade_groups(rows)
    for grade, group in grade_rows.items():
        label = money.GRADE_TITLES.get(grade, grade)
        cells = [
            (1, label, None),
            (2, float(group["rate"]), money_fmt),
            (3, int(group["count"]), "0"),
            (4, float(group["sum"]), money_fmt),
        ]
        for column, value, number_format in cells:
            cell = ws.cell(row=row, column=column, value=value)
            cell.border = box
            if number_format:
                cell.number_format = number_format
            if column == 1:
                cell.font = Font(bold=True, size=10, color=GRADE_COLORS.get(grade, "333333"))
            else:
                cell.alignment = Alignment(horizontal="right" if column == 4 else "center")
            if column == 4:
                cell.font = Font(bold=True, size=10,
                                 color=GREEN_FONT if value >= 0 else RED_FONT)
        row += 1

    # ------------------------------------------------------------ диаграмма
    if ordered:
        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = f"Итого по предметам за {period_title}"
        chart.y_axis.title = currency
        chart.x_axis.title = None
        data = Reference(ws, min_col=7, min_row=subject_header, max_row=subject_last)
        categories = Reference(ws, min_col=1, min_row=subject_header + 1, max_row=subject_last)
        chart.add_data(data, titles_from_data=True)
        chart.set_categories(categories)
        chart.height = 8.5
        chart.width = 17
        chart.legend = None
        ws.add_chart(chart, "I4")

    return ws


# ------------------------------------------------------------------ лист №3
def _build_settings_sheet(ws, settings, ai, currency, tz_offset):
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

    thin = Side(style="thin", color="D7DEE6")
    box = Border(left=thin, right=thin, top=thin, bottom=thin)
    money_fmt = _money_format(currency)

    ws.sheet_view.showGridLines = False
    ws.sheet_properties.tabColor = GREY
    for column, width in {"A": 32, "B": 22, "C": 16, "D": 16, "E": 16}.items():
        ws.column_dimensions[column].width = width

    ws.merge_cells("A1:E1")
    title = ws["A1"]
    title.value = "С какими настройками считался отчёт"
    title.font = Font(bold=True, size=14, color="FFFFFF")
    title.fill = PatternFill("solid", fgColor=DARK)
    title.alignment = Alignment(horizontal="center", vertical="center")
    ws.row_dimensions[1].height = 30

    row = 3
    basics = [
        ("Стартовая сумма", float(settings.get("start_sum") or 0), money_fmt),
        ("Валюта", currency, None),
        ("Часовой пояс (сдвиг от UTC)", f"+{int(tz_offset)}", None),
        ("Нейросеть", f"{ai.get('provider') or '—'} · {ai.get('model') or '—'}", None),
    ]
    for label, value, number_format in basics:
        name_cell = ws.cell(row=row, column=1, value=label)
        name_cell.font = Font(bold=True, size=10)
        name_cell.fill = PatternFill("solid", fgColor=LIGHT)
        name_cell.border = box
        value_cell = ws.cell(row=row, column=2, value=value)
        value_cell.border = box
        if number_format:
            value_cell.number_format = number_format
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Ставки за оценки").font = Font(bold=True, size=11, color=DARK)
    row += 1
    for index, text in enumerate(["Оценка", "Ставка"], start=1):
        cell = ws.cell(row=row, column=index, value=text)
        cell.font = Font(bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=ACCENT)
        cell.alignment = Alignment(horizontal="center")
        cell.border = box
    row += 1
    rates = settings.get("rates") or {}
    if not rates:
        ws.cell(row=row, column=1, value="не заданы").font = Font(italic=True, color=GREY)
        row += 1
    for grade, rate in money.sorted_rates(rates):
        label_cell = ws.cell(row=row, column=1, value=money.GRADE_TITLES.get(grade, grade))
        label_cell.font = Font(bold=True, size=10, color=GRADE_COLORS.get(grade, "333333"))
        label_cell.border = box
        rate_cell = ws.cell(row=row, column=2, value=float(rate))
        rate_cell.number_format = money_fmt
        rate_cell.border = box
        rate_cell.font = Font(size=10, color=GREEN_FONT if rate >= 0 else RED_FONT)
        row += 1

    row += 1
    ws.cell(row=row, column=1, value="Коэффициенты по предметам").font = Font(bold=True, size=11, color=DARK)
    row += 1
    for index, text in enumerate(["Предмет", "Коэффициент", "Что значит"], start=1):
        cell = ws.cell(row=row, column=index, value=text)
        cell.font = Font(bold=True, size=10, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=ACCENT)
        cell.alignment = Alignment(horizontal="center")
        cell.border = box
    row += 1
    coefficients = settings.get("coefficients") or {}
    if not coefficients:
        ws.cell(row=row, column=1, value="не заданы — у всех предметов ×1").font = Font(italic=True, color=GREY)
        row += 1
    for subject, coefficient in sorted(coefficients.items()):
        name_cell = ws.cell(row=row, column=1, value=money.pretty_subject(subject))
        name_cell.font = Font(bold=True, size=10)
        name_cell.border = box
        value_cell = ws.cell(row=row, column=2, value=float(coefficient))
        value_cell.number_format = '0.###"×"'
        value_cell.alignment = Alignment(horizontal="center")
        value_cell.border = box
        note_cell = ws.cell(row=row, column=3,
                            value=f"деньги по предмету умножаются на {utils.coefficient_text(coefficient)[1:]}")
        note_cell.font = Font(size=9, color=GREY)
        note_cell.border = box
        row += 1

    row += 1
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=5)
    note = ws.cell(row=row, column=1,
                   value="Сумма = ставка за оценку × коэффициент предмета. "
                         "Ключ нейросети в отчёт не попадает.")
    note.font = Font(italic=True, size=9, color=GREY)
    return ws


# -------------------------------------------------------------------- сборка
def build_report(path: str, rows: list[dict], stats: dict, settings: dict, *,
                 period_title: str, user_label: str = "", tz_offset: float = 3,
                 ai: dict | None = None) -> str:
    """Собирает книгу Excel и сохраняет её по пути `path`."""
    _need_openpyxl()
    from openpyxl import Workbook

    currency = settings.get("currency") or "₽"
    workbook = Workbook()

    grades_sheet = workbook.active
    grades_sheet.title = SHEET_GRADES
    _build_grades_sheet(grades_sheet, rows, stats, currency, period_title, user_label)

    summary_sheet = workbook.create_sheet(SHEET_SUMMARY)
    _build_summary_sheet(summary_sheet, rows, stats, settings, currency, period_title, user_label)

    settings_sheet = workbook.create_sheet(SHEET_SETTINGS)
    _build_settings_sheet(settings_sheet, settings, ai or {}, currency, tz_offset)

    workbook.properties.title = f"Карманные деньги — {period_title}"
    workbook.properties.creator = "pocket-money-bot"
    workbook.properties.description = "Отчёт по оценкам: дата, предмет, оценка, коэффициент, сумма"

    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    workbook.save(path)
    return path


def default_report_name(user_id: int, period_title: str, stamp: datetime | None = None) -> str:
    moment = stamp or utils.local_now()
    safe = "".join(ch for ch in period_title if ch.isalnum() or ch in " -_").strip()
    safe = safe.replace(" ", "-")
    return f"ocenki-{safe or 'report'}-{moment.strftime('%Y%m%d-%H%M')}-{user_id}.xlsx"
