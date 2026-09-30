# -*- coding: utf-8 -*-
"""Состояния диалогов (FSM)."""
from __future__ import annotations

from aiogram.fsm.state import State, StatesGroup


class Flow(StatesGroup):
    # настройки
    start_sum = State()
    rate_value = State()
    coefficient_subject = State()
    coefficient_value = State()
    currency = State()
    timezone = State()

    # нейросеть
    ai_key = State()
    ai_model = State()
    ai_base_url = State()

    # добавление оценок вручную
    add_grade = State()
    add_subject = State()
    add_date = State()

    # свой период для отчёта
    period_from = State()
    period_to = State()
