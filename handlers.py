"""Меню: один экран, который перерисовывается на месте.

Правило, из-за которого меню выглядит опрятно: бот не шлёт новое
сообщение на каждое нажатие, а правит то же самое. Иначе после пяти
нажатий в переписке лежит пять почти одинаковых карточек, и человек
листает вверх, чтобы понять, где он.

Отсюда же — обязательный ответ на каждый callback: либо перерисовка,
либо всплывашка. Молча оставленный callback крутит часики у нажавшего
до самого таймаута.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    Message,
)

import config
import keyboards
import partners
import texts

log = logging.getLogger("starspartners.menu")
router = Router(name="menu")

#: Ограничение Telegram на подпись к фото. Карточки в него укладываются,
#: но тексты правятся руками — поэтому не «надеемся», а проверяем.
CAPTION_LIMIT = 1024

#: Заглушки под свою логику: показать всплывашку и не молчать. Меняя
#: этот файл под себя, разводите «a:*» по нормальным экранам.
ACTIONS = {
    "a:payout": (
        f"Вывод от {config.MIN_PAYOUT} {config.CURRENCY}. "
        "Заявка обрабатывается в течение суток."
    ),
    "a:history": "История операций пока пуста.",
    "a:ref": "Реферальная ссылка появится здесь после подключения базы.",
    "a:addbot": "Пришлите токен от @BotFather, чтобы подключить бота.",
    "a:mybots": "Список ботов появится здесь после подключения базы.",
}


def _photo() -> str | FSInputFile | None:
    """Баннер меню: file_id/URL из настроек или файл из assets."""
    if config.MENU_PHOTO:
        return config.MENU_PHOTO
    if config.MENU_PHOTO_FILE.exists():
        return FSInputFile(config.MENU_PHOTO_FILE)
    return None


def _partner(user) -> partners.Partner:
    name = (user.first_name or "").strip() or user.username or "партнёр"
    return partners.get(user.id, name)


async def open_menu(message: Message, text: str, kb: InlineKeyboardMarkup):
    """Первая отрисовка меню: с баннером, если он есть."""
    photo = _photo()
    if photo is not None and len(text) <= CAPTION_LIMIT:
        return await message.answer_photo(photo, caption=text, reply_markup=kb)
    return await message.answer(
        text, reply_markup=kb, disable_web_page_preview=True
    )


async def render(message: Message, text: str, kb: InlineKeyboardMarkup):
    """Перерисовать открытый экран на месте.

    У сообщения с фото правится подпись, у обычного — текст: подменить
    одно другим Telegram не даёт. Если карточка переросла лимит подписи
    (её же правят руками), меню переезжает в обычное сообщение — лучше
    без баннера, чем ошибка отправки.
    """
    try:
        if message.photo:
            if len(text) <= CAPTION_LIMIT:
                return await message.edit_caption(caption=text, reply_markup=kb)
            await message.delete()
            return await message.answer(
                text, reply_markup=kb, disable_web_page_preview=True
            )
        return await message.edit_text(
            text, reply_markup=kb, disable_web_page_preview=True
        )
    except TelegramBadRequest as err:
        # «message is not modified» — человек нажал ту же кнопку дважды.
        # Это не ошибка, крутилку просто снимет answer() у вызывающего.
        if "not modified" not in str(err):
            raise
        return message


@router.message(CommandStart())
@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    p = _partner(message.from_user)
    await open_menu(message, texts.menu(p), keyboards.menu())


@router.callback_query(F.data == "m:root")
async def back_to_menu(call: CallbackQuery) -> None:
    p = _partner(call.from_user)
    await render(call.message, texts.menu(p), keyboards.menu())
    await call.answer()


@router.callback_query(F.data.startswith("m:"))
async def open_screen(call: CallbackQuery) -> None:
    screen = keyboards.SCREENS.get(call.data.split(":", 1)[1])
    if not screen:
        await call.answer("Раздел недоступен", show_alert=True)
        return
    card, kb = screen
    p = _partner(call.from_user)
    await render(call.message, card(p), kb())
    await call.answer()


@router.callback_query(F.data.startswith("a:"))
async def action(call: CallbackQuery) -> None:
    # Тарифы приходят как «a:buy:<номер>» — их разбираем отдельно.
    if call.data.startswith("a:buy:"):
        idx = int(call.data.rsplit(":", 1)[1])
        name, price, _ = config.SUB_PLANS[idx]
        await call.answer(
            f"{name} — {price} {config.CURRENCY}.\n"
            "Оплата подключается отдельно.",
            show_alert=True,
        )
        return
    await call.answer(ACTIONS.get(call.data, "Скоро"), show_alert=True)


@router.message(F.text)
async def anything(message: Message) -> None:
    """Любое сообщение возвращает в меню.

    Человек, который пишет боту текст, обычно потерял кнопки — показать
    меню полезнее, чем ответить «не понимаю».
    """
    p = _partner(message.from_user)
    await open_menu(message, texts.menu(p), keyboards.menu())
