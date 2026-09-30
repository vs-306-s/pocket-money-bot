# -*- coding: utf-8 -*-
"""
Мини-база (SQLite) в файле data/bot.db.

Таблицы:
  * users    — кто пользуется ботом;
  * settings — личные настройки: стартовая сумма, ставки, коэффициенты, валюта;
  * ai       — ключ и модель нейросети этого пользователя;
  * grades   — сами оценки: дата, предмет, оценка, коэффициент, сумма.

Соединение открывается на один запрос и сразу закрывается — так не бывает
«зависших» блокировок и не нужно думать о потоках.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime

from bot import config

DB_PATH = os.path.join(config.DATA_DIR, "bot.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id    INTEGER PRIMARY KEY,
    username   TEXT,
    full_name  TEXT,
    created    TEXT DEFAULT (datetime('now')),
    last_seen  TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS settings (
    user_id      INTEGER PRIMARY KEY,
    start_sum    REAL DEFAULT 0,
    currency     TEXT DEFAULT '₽',
    rates        TEXT DEFAULT '{}',
    coefficients TEXT DEFAULT '{}',
    tz_offset    REAL DEFAULT 3,
    updated      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai (
    user_id      INTEGER PRIMARY KEY,
    provider     TEXT,
    base_url     TEXT,
    model        TEXT,
    api_key      TEXT,
    updated      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS grades (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    date        TEXT NOT NULL,          -- ГГГГ-ММ-ДД
    subject     TEXT NOT NULL,
    grade       TEXT NOT NULL,
    coefficient REAL DEFAULT 1,
    base        REAL DEFAULT 0,         -- ставка за оценку до коэффициента
    amount      REAL DEFAULT 0,         -- итоговая сумма (может быть отрицательной)
    comment     TEXT DEFAULT '',
    source      TEXT DEFAULT 'manual',  -- photo | manual
    created     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_grades_user_date ON grades(user_id, date DESC);
"""


def _connect() -> sqlite3.Connection:
    os.makedirs(config.DATA_DIR, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=20)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA journal_mode=WAL")
    except sqlite3.Error:
        pass
    return connection


@contextmanager
def _cursor():
    connection = _connect()
    try:
        with connection:                 # commit при успехе, rollback при ошибке
            yield connection
    finally:
        connection.close()


def init() -> None:
    config.ensure_dirs()
    with _cursor() as connection:
        connection.executescript(SCHEMA)


# --------------------------------------------------------------------- users
def touch_user(user_id: int, username: str | None = None, full_name: str | None = None) -> dict:
    with _cursor() as connection:
        connection.execute(
            "INSERT INTO users(user_id, username, full_name) VALUES(?,?,?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "username=excluded.username, full_name=excluded.full_name, last_seen=datetime('now')",
            (user_id, username or "", full_name or ""),
        )
    return get_user(user_id)


def get_user(user_id: int) -> dict:
    with _cursor() as connection:
        row = connection.execute("SELECT * FROM users WHERE user_id=?", (user_id,)).fetchone()
    return dict(row) if row else {"user_id": user_id, "username": "", "full_name": ""}


# ------------------------------------------------------------------ settings
def default_settings() -> dict:
    return {
        "start_sum": float(config.get("default_start_sum") or 0),
        "currency": str(config.get("default_currency") or "₽"),
        "rates": {str(k): float(v) for k, v in (config.get("default_rates") or {}).items()},
        "coefficients": {str(k): float(v) for k, v in (config.get("default_coefficients") or {}).items()},
        "tz_offset": float(config.get("tz_offset", 3) or 0),
    }


def _decode_settings(row: sqlite3.Row) -> dict:
    def _json(value) -> dict:
        try:
            data = json.loads(value or "{}")
        except (TypeError, ValueError):
            return {}
        if not isinstance(data, dict):
            return {}
        result: dict[str, float] = {}
        for key, item in data.items():
            try:
                result[str(key)] = float(item)
            except (TypeError, ValueError):
                continue
        return result

    return {
        "start_sum": float(row["start_sum"] or 0),
        "currency": str(row["currency"] or "₽"),
        "rates": _json(row["rates"]),
        "coefficients": _json(row["coefficients"]),
        "tz_offset": float(row["tz_offset"] if row["tz_offset"] is not None else 3),
    }


def get_settings(user_id: int) -> dict:
    with _cursor() as connection:
        row = connection.execute("SELECT * FROM settings WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        values = default_settings()
        _write_settings(user_id, values)
        return values
    return _decode_settings(row)


def _write_settings(user_id: int, settings: dict) -> None:
    with _cursor() as connection:
        connection.execute(
            "INSERT INTO settings(user_id, start_sum, currency, rates, coefficients, "
            "tz_offset, updated) VALUES(?,?,?,?,?,?,datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "start_sum=excluded.start_sum, currency=excluded.currency, "
            "rates=excluded.rates, coefficients=excluded.coefficients, "
            "tz_offset=excluded.tz_offset, updated=datetime('now')",
            (
                user_id,
                float(settings.get("start_sum") or 0),
                str(settings.get("currency") or "₽"),
                json.dumps(settings.get("rates") or {}, ensure_ascii=False),
                json.dumps(settings.get("coefficients") or {}, ensure_ascii=False),
                float(settings.get("tz_offset") if settings.get("tz_offset") is not None else 3),
            ),
        )


def save_settings(user_id: int, **changes) -> dict:
    settings = get_settings(user_id)
    for key, value in changes.items():
        if value is not None:
            settings[key] = value
    _write_settings(user_id, settings)
    return settings


def reset_settings(user_id: int) -> dict:
    values = default_settings()
    _write_settings(user_id, values)
    return values


# ------------------------------------------------------------------------ ai
def get_ai(user_id: int) -> dict:
    with _cursor() as connection:
        row = connection.execute("SELECT * FROM ai WHERE user_id=?", (user_id,)).fetchone()
    if row is None:
        return {"provider": "", "base_url": "", "model": "", "api_key": ""}
    return {
        "provider": row["provider"] or "",
        "base_url": row["base_url"] or "",
        "model": row["model"] or "",
        "api_key": row["api_key"] or "",
    }


def set_ai(user_id: int, **changes) -> dict:
    current = get_ai(user_id)
    current.update({k: v for k, v in changes.items() if v is not None})
    with _cursor() as connection:
        connection.execute(
            "INSERT INTO ai(user_id, provider, base_url, model, api_key, updated) "
            "VALUES(?,?,?,?,?,datetime('now')) "
            "ON CONFLICT(user_id) DO UPDATE SET provider=excluded.provider, "
            "base_url=excluded.base_url, model=excluded.model, api_key=excluded.api_key, "
            "updated=datetime('now')",
            (user_id, current.get("provider", ""), current.get("base_url", ""),
             current.get("model", ""), current.get("api_key", "")),
        )
    return get_ai(user_id)


def clear_ai_key(user_id: int) -> None:
    with _cursor() as connection:
        connection.execute("UPDATE ai SET api_key='' WHERE user_id=?", (user_id,))


# -------------------------------------------------------------------- grades
def add_grades(user_id: int, entries: list[dict], source: str = "manual") -> list[dict]:
    """Сохраняет оценки. В каждой записи должны быть date, subject, grade,
    coefficient, base, amount, comment."""
    saved: list[dict] = []
    with _cursor() as connection:
        for entry in entries:
            cursor = connection.execute(
                "INSERT INTO grades(user_id, date, subject, grade, coefficient, base, amount, "
                "comment, source) VALUES(?,?,?,?,?,?,?,?,?)",
                (
                    user_id,
                    str(entry.get("date")),
                    str(entry.get("subject") or "").strip(),
                    str(entry.get("grade") or "").strip(),
                    float(entry.get("coefficient") or 1),
                    float(entry.get("base") or 0),
                    float(entry.get("amount") or 0),
                    str(entry.get("comment") or "").strip(),
                    source,
                ),
            )
            entry_id = int(cursor.lastrowid)
            saved.append({**entry, "id": entry_id})
    return saved


def list_grades(user_id: int, date_from: str | None = None, date_to: str | None = None,
                limit: int | None = None, newest_first: bool = False) -> list[dict]:
    query = "SELECT * FROM grades WHERE user_id=?"
    params: list = [user_id]
    if date_from:
        query += " AND date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND date <= ?"
        params.append(date_to)
    query += " ORDER BY date DESC, id DESC" if newest_first else " ORDER BY date ASC, id ASC"
    if limit:
        query += " LIMIT ?"
        params.append(int(limit))
    with _cursor() as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def get_grade(grade_id: int, user_id: int) -> dict | None:
    with _cursor() as connection:
        row = connection.execute("SELECT * FROM grades WHERE id=? AND user_id=?",
                                 (grade_id, user_id)).fetchone()
    return dict(row) if row else None


def delete_grade(grade_id: int, user_id: int) -> dict | None:
    found = get_grade(grade_id, user_id)
    if not found:
        return None
    with _cursor() as connection:
        connection.execute("DELETE FROM grades WHERE id=? AND user_id=?", (grade_id, user_id))
    return found


def delete_last(user_id: int) -> dict | None:
    """Убирает последнюю ДОБАВЛЕННУЮ запись (её может не быть самой поздней по дате)."""
    with _cursor() as connection:
        row = connection.execute(
            "SELECT * FROM grades WHERE user_id=? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
    if row is None:
        return None
    return delete_grade(int(row["id"]), user_id)


def clear_grades(user_id: int) -> int:
    with _cursor() as connection:
        cursor = connection.execute("DELETE FROM grades WHERE user_id=?", (user_id,))
    return int(cursor.rowcount or 0)


def count_grades(user_id: int) -> int:
    with _cursor() as connection:
        row = connection.execute("SELECT COUNT(*) AS n FROM grades WHERE user_id=?",
                                 (user_id,)).fetchone()
    return int(row["n"] if row else 0)


def known_subjects(user_id: int, limit: int = 40) -> list[str]:
    """Предметы, которые уже встречались у пользователя (для подсказок)."""
    with _cursor() as connection:
        rows = connection.execute(
            "SELECT subject, COUNT(*) AS n FROM grades WHERE user_id=? "
            "GROUP BY subject ORDER BY n DESC, subject ASC LIMIT ?",
            (user_id, int(limit)),
        ).fetchall()
    return [str(row["subject"]) for row in rows]


def stats(user_id: int) -> dict:
    with _cursor() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(amount),0) AS total, "
            "MIN(date) AS first_date, MAX(date) AS last_date FROM grades WHERE user_id=?",
            (user_id,),
        ).fetchone()
    return {
        "count": int(row["n"] or 0),
        "total": float(row["total"] or 0),
        "first_date": row["first_date"],
        "last_date": row["last_date"],
    }


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def totals() -> dict:
    """Общая статистика по базе (для служебной команды /admin)."""
    with _cursor() as connection:
        users = connection.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        grades = connection.execute("SELECT COUNT(*) AS n FROM grades").fetchone()["n"]
        keys = connection.execute("SELECT COUNT(*) AS n FROM ai WHERE api_key <> ''").fetchone()["n"]
    return {"users": int(users or 0), "grades": int(grades or 0), "keys": int(keys or 0)}
