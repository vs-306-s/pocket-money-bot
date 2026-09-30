# -*- coding: utf-8 -*-
"""Все роутеры бота — в порядке обработки."""
from __future__ import annotations

from . import ai_key, base, fallback, grades, report, settings_menu

# base — первым, чтобы «Отмена» и меню работали в любом состоянии,
# fallback — последним: он ловит всё, что не подошло другим.
ROUTERS = [base, settings_menu, ai_key, grades, report, fallback]

__all__ = ["ROUTERS"]
