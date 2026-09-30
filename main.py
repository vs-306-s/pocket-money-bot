# -*- coding: utf-8 -*-
"""
Точка входа. Запуск:  python main.py

Бот работает на длинном опросе (long polling): ни вебхук, ни белый IP не нужны.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, ErrorEvent

from bot import config, db
from bot.handlers import ROUTERS
from bot.middlewares import DbUserMiddleware

# Русская консоль часто в cp1251 — без этого print с эмодзи падает
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

log = logging.getLogger("pocket-money-bot")

COMMANDS = [
    BotCommand(command="photos", description="📸 Как присылать фото"),
    BotCommand(command="add", description="➕ Добавить оценку вручную"),
    BotCommand(command="list", description="📋 Последние оценки"),
    BotCommand(command="balance", description="💰 Баланс карманных"),
    BotCommand(command="report", description="📊 Отчёт в Excel"),
    BotCommand(command="settings", description="⚙️ Ставки и коэффициенты"),
    BotCommand(command="key", description="🤖 Ключ нейросети"),
    BotCommand(command="guide", description="📖 Где взять ключ"),
    BotCommand(command="help", description="❓ Справка"),
    BotCommand(command="cancel", description="✖️ Отменить ввод"),
]


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, str(config.get("log_level", "INFO")).upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    config.ensure_dirs()
    db.init()

    token = config.cfg.token
    if not token or ":" not in token:
        print("❌ В config.json не заполнен bot_token.\n"
              "   1) Создай бота у @BotFather → /newbot → скопируй токен.\n"
              "   2) Впиши его в config.json в поле \"bot_token\" "
              "(или задай переменную окружения BOT_TOKEN).")
        return

    proxy = config.cfg.proxy
    try:
        session = AiohttpSession(proxy=proxy) if proxy else AiohttpSession()
    except Exception as error:  # noqa: BLE001 — покажем понятный текст вместо трейсбека
        print(f"❌ Не смог настроить прокси из config.json: {error}\n"
              "   Для socks/http прокси нужен пакет aiohttp-socks (pip install aiohttp-socks).")
        return

    bot = Bot(token=token, session=session,
              default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher(storage=MemoryStorage())

    dispatcher.message.middleware(DbUserMiddleware())
    dispatcher.callback_query.middleware(DbUserMiddleware())

    for module in ROUTERS:
        dispatcher.include_router(module.router)

    @dispatcher.errors()
    async def on_error(event: ErrorEvent) -> bool:
        log.error("ошибка при обработке апдейта: %s", event.exception, exc_info=event.exception)
        return True

    try:
        me = await bot.get_me()
        await bot.set_my_commands(COMMANDS)
        await bot.delete_webhook(drop_pending_updates=True)
    except Exception as error:  # noqa: BLE001
        print(f"❌ Не смог подключиться к Telegram: {error}\n"
              "   • проверь токен в config.json (вид 123456:AA...);\n"
              "   • если Telegram заблокирован провайдером — включи VPN или укажи "
              "\"proxy\" в config.json.")
        await bot.session.close()
        return

    ai_ready = bool(config.get("default_rates"))
    print("=" * 60)
    print(f"  ✅ Бот @{me.username} запущен")
    print(f"  База:      {db.DB_PATH}")
    print(f"  Прокси:    {proxy or 'не используется'}")
    print(f"  Ставки по умолчанию: {config.get('default_rates')}")
    print(f"  Коэффициенты: {config.get('default_coefficients')}")
    print(f"  Ключи нейросети подключает каждый пользователь сам (/key)")
    print("=" * 60)
    if not ai_ready:
        print("  ⚠️  В config.json не заданы default_rates — оценки будут считаться по нулям.")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("\nОстановлено.")
