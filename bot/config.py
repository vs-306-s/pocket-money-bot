# -*- coding: utf-8 -*-
"""
Настройки бота.

Порядок приоритета:
    1) переменная окружения (удобно на хостинге),
    2) файл config.json (удобно на своём компьютере),
    3) значение по умолчанию.

Важно: личные настройки (стартовая сумма, ставки за оценки, коэффициенты по
предметам) здесь НЕ хранятся — они у каждого пользователя свои и лежат в базе.
В config.json живут только токен, прокси и значения «по умолчанию для новых».
"""
from __future__ import annotations

import json
import os
import threading

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
DATA_DIR = os.environ.get("DATA_DIR") or os.path.join(BASE_DIR, "data")
REPORTS_DIR = os.path.join(DATA_DIR, "reports")

DEFAULTS: dict = {
    # --- подключение ---
    "bot_token": "",
    "owner_ids": [],                 # id владельцев (служебные команды /admin)
    "proxy": None,                   # напр. "http://127.0.0.1:10809" или "socks5://..."
    "secret": "pocket-money-bot-secret",

    # --- «заводские» настройки для новых пользователей ---
    "default_start_sum": 0,          # стартовая сумма карманных денег
    "default_currency": "₽",
    "default_rates": {"5": 300, "4": 150, "3": -100, "2": -300},
    "default_coefficients": {"математика": 2, "физика": 1.5, "русский язык": 1.5},

    # --- прочее ---
    "tz_offset": 3,                  # часовой пояс (МСК = 3) — по нему считаются месяцы
    "max_photos": 8,                 # сколько фото принимаем за один раз
    "ai": {"temperature": 0.2, "max_tokens": 4000, "timeout": 180},
    "log_level": "INFO",
}

ENV_MAP = {
    "bot_token": "BOT_TOKEN",
    "owner_ids": "OWNER_IDS",
    "proxy": "PROXY",
    "secret": "BOT_SECRET",
    "tz_offset": "TZ_OFFSET",
}


def _cast(value: str, like):
    """Приводит строку из переменной окружения к типу значения по умолчанию."""
    try:
        if isinstance(like, bool):
            return value.strip().lower() in ("1", "true", "yes", "on", "да")
        if isinstance(like, int):
            return int(float(value))
        if isinstance(like, float):
            return float(value)
        if isinstance(like, list):
            return [x.strip() for x in value.split(",") if x.strip()]
    except (TypeError, ValueError):
        return value
    return value


class _Config:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self.data: dict = dict(DEFAULTS)
        self.reload()

    # ------------------------------------------------------------------ чтение
    def reload(self) -> dict:
        with self._lock:
            data = dict(DEFAULTS)
            if os.path.exists(CONFIG_PATH):
                try:
                    with open(CONFIG_PATH, encoding="utf-8") as handle:
                        from_file = json.load(handle)
                    if isinstance(from_file, dict):
                        for key, value in from_file.items():
                            if value is None and key in DEFAULTS:
                                continue
                            data[key] = value
                except (OSError, ValueError):
                    pass
            for key, env_name in ENV_MAP.items():
                raw = os.environ.get(env_name)
                if raw:
                    data[key] = _cast(raw, DEFAULTS.get(key))
            self.data = data
            return data

    def get(self, key: str, default=None):
        with self._lock:
            value = self.data.get(key, DEFAULTS.get(key, default))
            return DEFAULTS.get(key, default) if value is None and key in DEFAULTS else value

    # ------------------------------------------------------------------ запись
    def set(self, key: str, value, save: bool = True) -> None:
        with self._lock:
            self.data[key] = value
        if save:
            self.save()

    def save(self) -> None:
        """Пишется только то, что отличается от значений по умолчанию."""
        with self._lock:
            payload = {k: v for k, v in self.data.items() if DEFAULTS.get(k, object()) != v
                       or k in ("bot_token", "owner_ids", "proxy")}
            try:
                os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
                temp_path = CONFIG_PATH + ".tmp"
                with open(temp_path, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                os.replace(temp_path, CONFIG_PATH)
            except OSError:
                pass

    # --------------------------------------------------------------- свойства
    @property
    def token(self) -> str:
        return str(self.data.get("bot_token") or "").strip()

    @property
    def proxy(self) -> str | None:
        value = str(self.data.get("proxy") or "").strip()
        return value or None

    @property
    def owner_ids(self) -> list[int]:
        raw = self.data.get("owner_ids") or []
        result: list[int] = []
        for item in raw if isinstance(raw, list) else [raw]:
            try:
                result.append(int(item))
            except (TypeError, ValueError):
                continue
        return result

    def is_owner(self, user_id: int) -> bool:
        owners = self.owner_ids
        return not owners or user_id in owners


cfg = _Config()


def get(key: str, default=None):
    return cfg.get(key, default)


def set(key: str, value, save: bool = True) -> None:  # noqa: A001 — читается как config.set
    cfg.set(key, value, save=save)


def ensure_dirs() -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(REPORTS_DIR, exist_ok=True)
