"""Точка входа: бот, команды, поллинг."""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

import config
import handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("starspartners")

COMMANDS = (
    ("start", "Главное меню"),
    ("menu", "Главное меню"),
)


async def main() -> None:
    config.check()

    bot = Bot(
        config.BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(handlers.router)

    me = await bot.get_me()
    log.info("запущен как @%s", me.username)
    await bot.set_my_commands(
        [BotCommand(command=c, description=d) for c, d in COMMANDS]
    )

    # Копим апдейты только с момента запуска: меню — не очередь заявок,
    # разгребать вчерашние нажатия ему незачем.
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
