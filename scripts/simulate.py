# -*- coding: utf-8 -*-
"""
Оффлайн-прогон апдейтов через настоящий Dispatcher: проверяю маршрутизацию,
FSM-состояния, меню «Нейросеть» и остальные сценарии.

Сеть не используется: все исходящие вызовы Bot перехватываются.
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

TMP = tempfile.mkdtemp(prefix="pmb-sim-")
os.environ["DATA_DIR"] = TMP

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, Chat, Message, Update, User

from bot import config, db
from bot.handlers import ROUTERS
from bot.middlewares import DbUserMiddleware

USER_ID = 777
CHAT_ID = 777
NEXT_ID = [1000]
ERRORS: list[str] = []
FAILED: list[str] = []


class SilentBot(Bot):
    """Перехватывает все исходящие вызовы Bot — никакой сети."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.sent: list = []

    async def __call__(self, method, request_timeout=None):  # type: ignore[override]
        self.sent.append(method)
        return None

    def texts(self) -> list[str]:
        return [
            (getattr(item, "text", None) or getattr(item, "caption", None)
             or f"<{type(item).__name__}>")
            for item in self.sent
        ]

    def clear(self) -> None:
        self.sent = []


def make_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.message.middleware(DbUserMiddleware())
    dispatcher.callback_query.middleware(DbUserMiddleware())
    for module in ROUTERS:
        dispatcher.include_router(module.router)

    @dispatcher.errors()
    async def on_error(event):
        message = f"{type(event.exception).__name__}: {event.exception}"
        ERRORS.append(message)
        print(f"    ⛔ ОШИБКА: {message}")
        return True

    return dispatcher


def user() -> User:
    return User(id=USER_ID, is_bot=False, first_name="Иван")


def message_update(text: str | None = None) -> Update:
    NEXT_ID[0] += 1
    return Update(
        update_id=NEXT_ID[0],
        message=Message(
            message_id=NEXT_ID[0], date=datetime.now(),
            chat=Chat(id=CHAT_ID, type="private"), from_user=user(), text=text,
        ),
    )


def callback_update(data: str) -> Update:
    NEXT_ID[0] += 1
    return Update(
        update_id=NEXT_ID[0],
        callback_query=CallbackQuery(
            id=str(NEXT_ID[0]), from_user=user(), chat_instance="sim", data=data,
            message=Message(
                message_id=NEXT_ID[0], date=datetime.now(),
                chat=Chat(id=CHAT_ID, type="private"), from_user=user(),
                text="предыдущее сообщение бота",
            ),
        ),
    )


async def step(bot: SilentBot, dispatcher: Dispatcher, update: Update, title: str,
               expect: str | None = None) -> list[str]:
    bot.clear()
    await dispatcher.feed_update(bot, update)
    texts = bot.texts()
    print(f"\n▶️  {title}")
    if not texts:
        print("    (бот ничего не ответил)")
    for text in texts:
        print(f"    ➡️ {text.replace(chr(10), ' ')[:105]}")
    if expect is not None:
        joined = " ".join(texts)
        if expect.lower() not in joined.lower():
            FAILED.append(f"{title}: не нашёл «{expect}»")
            print(f"    ❌ ОЖИДАЛ: «{expect}»")
        else:
            print(f"    ✅ есть «{expect}»")
    return texts


async def main() -> int:
    config.ensure_dirs()
    db.init()
    bot = SilentBot(token="111:TEST", default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = make_dispatcher()

    print("=" * 70)
    print("СЦЕНАРИИ")
    print("=" * 70)

    await step(bot, dispatcher, message_update("/start"), "1. /start", expect="Привет")

    await step(bot, dispatcher, message_update("🤖 Нейросеть"),
               "2. кнопка «🤖 Нейросеть» (нижнее меню)", expect="Нейросеть")

    await step(bot, dispatcher, callback_update("ai:key"),
               "3. «🔑 Ввести ключ» без провайдера", expect="Пришли API-ключ")

    await step(bot, dispatcher, message_update("sk-simulated-key-1234567890"),
               "4. прислал ключ после запроса", expect="ключ")

    await step(bot, dispatcher, callback_update("prov:custom"),
               "5. выбрал провайдера «Свой сервер»", expect="Свой сервер")

    await step(bot, dispatcher, message_update("sk-another-key-0987654321"),
               "6. прислал ключ после выбора провайдера", expect="ключ")

    await step(bot, dispatcher, message_update("1122334455:AAHqqqzzzVVVbbbNNNmmm123456789012"),
               "7. прислал ТОКЕН Telegram-бота (частая путаница)", expect="токен Telegram-бота")

    await step(bot, dispatcher, message_update("просто случайный текст"),
               "8. просто текст", expect="Не понял")

    await step(bot, dispatcher, message_update("gsk_abcdefghijklmnopqrstuvwxyz0123"),
               "9. ключ без запроса — должен приняться", expect="ключ")

    await step(bot, dispatcher, message_update("/settings"), "10. /settings", expect="Настройки")
    await step(bot, dispatcher, callback_update("st:rates"), "11. «📈 Ставки»", expect="Ставки")
    await step(bot, dispatcher, callback_update("st:rate:5"), "12. выбрать пятёрку", expect="Ставка")
    await step(bot, dispatcher, message_update("400"), "13. новая ставка 400", expect="400")
    await step(bot, dispatcher, callback_update("st:coef_add"), "14. «➕ Добавить предмет»",
               expect="предмет")
    await step(bot, dispatcher, message_update("Физика"), "15. предмет «Физика»", expect="Физика")
    await step(bot, dispatcher, message_update("1.5"), "16. коэффициент 1.5", expect="1.5")
    await step(bot, dispatcher, callback_update("st:main"), "17. назад в настройки",
               expect="Настройки")

    await step(bot, dispatcher, message_update("/add 5 математика 15.09"),
               "18. /add с аргументами", expect="Записал")
    await step(bot, dispatcher, message_update("/add"), "19. /add без аргументов",
               expect="Какая оценка")
    await step(bot, dispatcher, callback_update("gr:new:4"), "20. оценка «4»", expect="предмету")
    await step(bot, dispatcher, message_update("История"), "21. предмет «История»", expect="Когда")
    await step(bot, dispatcher, callback_update("gr:date:today"), "22. дата «сегодня»",
               expect="Записал")

    await step(bot, dispatcher, message_update("/balance"), "23. /balance", expect="Остаток")
    await step(bot, dispatcher, message_update("/list"), "24. /list", expect="Последние оценки")
    await step(bot, dispatcher, callback_update("lg:page:0"), "25. пагинация списка")

    await step(bot, dispatcher, message_update("/report"), "26. /report", expect="Отчёт")
    await step(bot, dispatcher, callback_update("rp:month"), "27. отчёт за этот месяц",
               expect="Отчёт за")
    await step(bot, dispatcher, callback_update("rp:all"), "28. отчёт за всё время",
               expect="Отчёт за")

    await step(bot, dispatcher, message_update("/help"), "29. /help", expect="Справка")
    await step(bot, dispatcher, message_update("/guide"), "30. /guide", expect="OpenRouter")

    print("\n" + "=" * 70)
    print(f"Ошибок в хендлерах: {len(ERRORS)}")
    for error in ERRORS:
        print("  ⛔", error)
    print(f"Не выполнено ожиданий: {len(FAILED)}")
    for failure in FAILED:
        print("  ❌", failure)
    print("ИТОГ:", "✅ всё чисто" if not ERRORS and not FAILED else "❌ есть проблемы")
    return 0 if not ERRORS and not FAILED else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
