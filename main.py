"""Точка входа: база, бот франшизы, дочерние боты, поллинг.

Порядок важен. Сначала база — на неё опирается всё остальное. Потом
поднимаются боты партнёров: они зарабатывают деньги и не должны ждать,
пока франшиза договорится с Telegram. И только потом поллинг кабинета.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

import admin
import config
import db
import engine_stats
import handlers
import supervisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("partners")

COMMANDS = (
    ("start", "Главное меню"),
    ("menu", "Главное меню"),
)


async def main() -> None:
    config.check()
    await db.init()

    bot = Bot(
        config.BOT_TOKEN,
        default=DefaultBotProperties(
            parse_mode=ParseMode.HTML, link_preview_is_disabled=True
        ),
    )
    dp = Dispatcher(storage=MemoryStorage())
    # Админский роутер первым: его фильтр пропускает только ADMIN_IDS,
    # остальное проваливается дальше в кабинет партнёра.
    dp.include_router(admin.router)
    dp.include_router(handlers.router)

    me = await bot.get_me()
    log.info("франшиза запущена как @%s", me.username)
    if not config.ADMIN_IDS:
        log.warning("ADMIN_IDS пуст — админка недоступна никому")
    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in COMMANDS]
    )

    await supervisor.start_all()
    watchdog = asyncio.create_task(supervisor.watchdog())
    stats = asyncio.create_task(engine_stats.worker())

    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        # Боты партнёров живут своими процессами: если франшиза
        # выключается, гасим и их — иначе при следующем старте два
        # процесса на один токен подерутся за апдейты.
        watchdog.cancel()
        stats.cancel()
        await supervisor.stop_all()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
