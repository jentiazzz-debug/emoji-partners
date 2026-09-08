"""Кабинет партнёра: навигация, подключение ботов, управление ими.

Меню — одно сообщение, которое перерисовывается на месте. Иначе после
пяти нажатий в переписке лежит пять почти одинаковых карточек, и
человек листает вверх, чтобы понять, где он.

Отсюда же правило: на каждый callback либо перерисовка, либо
всплывашка, но обязательно что-то — молча оставленный callback крутит
часики у нажавшего до самого таймаута.
"""

from __future__ import annotations

import logging
import re

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramUnauthorizedError
from aiogram.filters import Command, CommandObject, CommandStart, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardMarkup,
    Message,
)

import config
import db
import engine_stats
import keyboards
import partners
import supervisor
import texts

log = logging.getLogger("partners.cabinet")
router = Router(name="cabinet")

#: Ограничение Telegram на подпись к фото.
CAPTION_LIMIT = 1024

#: Токен от BotFather: <id бота>:<секрет>. Проверка формы нужна не для
#: строгости, а чтобы не дёргать Telegram на каждое случайное сообщение.
TOKEN_RE = re.compile(r"^\d{6,12}:[A-Za-z0-9_-]{30,}$")


class Form(StatesGroup):
    token = State()


# --------------------------------------------------------------------------
# Отрисовка
# --------------------------------------------------------------------------


def _photo() -> str | FSInputFile | None:
    if config.MENU_PHOTO:
        return config.MENU_PHOTO
    if config.MENU_PHOTO_FILE.exists():
        return FSInputFile(config.MENU_PHOTO_FILE)
    return None


async def open_menu(message: Message, text: str, kb: InlineKeyboardMarkup):
    """Первая отрисовка: с баннером, если он есть."""
    photo = _photo()
    if photo is not None and len(text) <= CAPTION_LIMIT:
        return await message.answer_photo(photo, caption=text, reply_markup=kb)
    return await message.answer(text, reply_markup=kb, disable_web_page_preview=True)


async def render(message: Message, text: str, kb: InlineKeyboardMarkup):
    """Перерисовать открытый экран на месте.

    У сообщения с фото правится подпись, у обычного — текст: подменить
    одно другим Telegram не даёт. Если карточка переросла лимит подписи
    (в неё попадает и хвост лога с ошибкой движка), меню переезжает в
    обычное сообщение — лучше без баннера, чем ошибка отправки.
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
        # «message is not modified» — нажали ту же кнопку дважды.
        if "not modified" not in str(err):
            raise
        return message


async def who(user) -> dict:
    name = (user.first_name or "").strip() or user.username or "партнёр"
    return await db.touch(user.id, user.username, name)


async def menu_card(row: dict) -> tuple[str, InlineKeyboardMarkup]:
    sums = await db.totals(row["uid"])
    refs = await db.referrals(row["uid"])
    is_admin = row["uid"] in config.ADMIN_IDS
    return texts.menu(row, sums, refs), keyboards.menu(is_admin)


# --------------------------------------------------------------------------
# Вход
# --------------------------------------------------------------------------


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    await state.clear()
    # Реферальная ссылка: t.me/<bot>?start=r123456789
    ref = None
    if command.args and command.args.startswith("r"):
        tail = command.args[1:]
        if tail.isdigit():
            ref = int(tail)
    user = message.from_user
    name = (user.first_name or "").strip() or user.username or "партнёр"
    row = await db.touch(user.id, user.username, name, ref)
    text, kb = await menu_card(row)
    await open_menu(message, text, kb)


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    text, kb = await menu_card(await who(message.from_user))
    await open_menu(message, text, kb)


@router.callback_query(F.data == "m:root")
async def back_to_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text, kb = await menu_card(await who(call.from_user))
    await render(call.message, text, kb)
    await call.answer()


# --------------------------------------------------------------------------
# Разделы
# --------------------------------------------------------------------------


@router.callback_query(F.data.startswith("m:"))
async def open_screen(call: CallbackQuery, state: FSMContext):
    await state.clear()
    screen = call.data.split(":", 1)[1]
    row = await who(call.from_user)
    sums = await db.totals(row["uid"])

    if screen == "account":
        refs = await db.referrals(row["uid"])
        card, kb = texts.account(row, sums, refs), keyboards.account()
    elif screen == "bots":
        rows = await db.bots_of(row["uid"])
        card, kb = texts.bots_list(row, rows), keyboards.bots_list(row, rows)
    elif screen == "loyalty":
        card, kb = texts.loyalty(row, sums), keyboards.loyalty()
    elif screen == "sub":
        card, kb = texts.subscription(row, sums), keyboards.subscription()
    elif screen == "ref":
        me = await call.bot.me()
        link = f"https://t.me/{me.username}?start=r{row['uid']}"
        refs = await db.referrals(row["uid"])
        card, kb = texts.referral(row, refs, link), keyboards.referral()
    elif screen == "info":
        card, kb = texts.info(), keyboards.info()
    elif screen == "new":
        card, kb = texts.whatsnew(), keyboards.whatsnew()
    else:
        await call.answer("Раздел недоступен", show_alert=True)
        return

    await render(call.message, card, kb)
    await call.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_plan(call: CallbackQuery):
    idx = int(call.data.split(":", 1)[1])
    name, price, _ = config.SUB_PLANS[idx]
    await call.answer(
        f"{name} — {price} ₽.\nОплата подключается вместе с денежной частью: "
        f"напишите в {config.SUPPORT}.",
        show_alert=True,
    )


# --------------------------------------------------------------------------
# Подключение бота
# --------------------------------------------------------------------------


@router.callback_query(F.data == "addbot")
async def add_bot_start(call: CallbackQuery, state: FSMContext):
    row = await who(call.from_user)
    have = len(await db.bots_of(row["uid"]))
    if not partners.can_add_bot(row, have):
        await call.answer(
            "Лимит ботов исчерпан. Снимается подпиской.", show_alert=True
        )
        return
    await state.set_state(Form.token)
    await render(call.message, texts.add_bot_howto(), keyboards.cancel())
    await call.answer()


async def _check_token(token: str) -> tuple[dict | None, str]:
    """Спросить Telegram, чей это токен. Возвращает (данные, ошибка)."""
    probe = Bot(token)
    try:
        me = await probe.get_me()
        return (
            {"id": me.id, "username": me.username or "", "title": me.full_name},
            "",
        )
    except TelegramUnauthorizedError:
        return None, "Telegram не принял токен — он отозван или введён с опечаткой."
    except Exception as err:  # noqa: BLE001 — сеть, таймаут, что угодно
        return None, f"Не удалось проверить токен: {err}"
    finally:
        await probe.session.close()


@router.message(Form.token, F.text)
async def add_bot_token(message: Message, state: FSMContext):
    token = (message.text or "").strip()

    # Токен — это пароль от бота. В переписке ему не место, поэтому
    # сообщение с ним стирается сразу, ещё до всех проверок.
    try:
        await message.delete()
    except TelegramBadRequest:
        pass

    if not TOKEN_RE.match(token):
        await message.answer(
            texts.token_bad(
                "Это не похоже на токен. Он выглядит так: "
                "1234567890:AAG... — цифры, двоеточие, длинный хвост."
            ),
            reply_markup=keyboards.cancel(),
        )
        return

    info, err = await _check_token(token)
    if info is None:
        await message.answer(
            texts.token_bad(err), reply_markup=keyboards.cancel()
        )
        return

    if await db.bot_by_tg(info["id"]):
        await message.answer(
            texts.token_bad("Этот бот уже подключён к сервису."),
            reply_markup=keyboards.cancel(),
        )
        return

    row = await who(message.from_user)
    have = len(await db.bots_of(row["uid"]))
    if not partners.can_add_bot(row, have):
        await state.clear()
        await message.answer(
            texts.token_bad("Лимит ботов исчерпан."),
            reply_markup=keyboards.cancel(),
        )
        return

    ws = supervisor.workspace(info["id"])
    row_id = await db.add_bot(
        row["uid"], info["id"], token, info["username"], info["title"], str(ws)
    )
    await db.log(row["uid"], "bot_add", f"@{info['username']}")
    await state.clear()

    item = await db.bot(row_id)
    ok, note = await supervisor.start(item)
    item = await db.bot(row_id)
    await message.answer(
        texts.bot_added(info["username"], ok, note),
        reply_markup=keyboards.bot_card(item),
    )


# --------------------------------------------------------------------------
# Карточка бота
# --------------------------------------------------------------------------


async def _owned(call: CallbackQuery, row_id: int) -> dict | None:
    """Бот по id — только свой. Чужой callback подделать несложно."""
    item = await db.bot(row_id)
    if not item or (
        int(item["owner"]) != call.from_user.id
        and call.from_user.id not in config.ADMIN_IDS
    ):
        await call.answer("Бот не найден", show_alert=True)
        return None
    return item


@router.callback_query(F.data.startswith("b:"))
async def bot_card(call: CallbackQuery):
    item = await _owned(call, int(call.data.split(":", 1)[1]))
    if not item:
        return
    await render(call.message, texts.bot_card(item), keyboards.bot_card(item))
    await call.answer()


@router.callback_query(F.data.startswith("bx:"))
async def bot_action(call: CallbackQuery):
    _, raw_id, action = call.data.split(":", 2)
    item = await _owned(call, int(raw_id))
    if not item:
        return

    note = ""
    if action == "start":
        await call.answer("Запускаю…")
        ok, note = await supervisor.start(item)
    elif action == "stop":
        await call.answer("Останавливаю…")
        note = await supervisor.stop(item)
    elif action == "restart":
        await call.answer("Перезапускаю…")
        ok, note = await supervisor.restart(item)
    elif action == "auto":
        await db.set_autostart(int(item["id"]), not item["autostart"])
        await call.answer(
            "Автозапуск выключен" if item["autostart"] else "Автозапуск включён"
        )
    elif action == "stats":
        got = await engine_stats.refresh(item)
        await call.answer(
            "Обновлено" if got else "База бота ещё пуста — он не запускался"
        )
    elif action == "del":
        await render(
            call.message,
            f"🗑 <b>Отключить @{texts.esc(item['username'])}?</b>\n\n"
            f"Бот остановится и пропадёт из вашего списка. Его база с "
            f"клиентами и заказами останется на сервере — если передумаете, "
            f"поддержка вернёт бота с той же статистикой.",
            keyboards.confirm_delete(item),
        )
        await call.answer()
        return
    elif action == "delyes":
        await supervisor.stop(item)
        await db.drop_bot(int(item["id"]))
        await db.log(item["owner"], "bot_del", f"@{item['username']}")
        row = await who(call.from_user)
        rows = await db.bots_of(row["uid"])
        await render(
            call.message, texts.bots_list(row, rows), keyboards.bots_list(row, rows)
        )
        await call.answer("Бот отключён")
        return
    else:
        await call.answer("Неизвестная команда", show_alert=True)
        return

    item = await db.bot(int(raw_id))
    card = texts.bot_card(item)
    if note and note not in card:
        card += f"\n\n<i>{texts.esc(note)}</i>"
    await render(call.message, card, keyboards.bot_card(item))


# --------------------------------------------------------------------------
# Всё остальное
# --------------------------------------------------------------------------


@router.message(StateFilter(None), F.text)
async def anything(message: Message):
    """Любое сообщение возвращает в меню.

    Человек, который пишет боту текст, обычно потерял кнопки — показать
    меню полезнее, чем ответить «не понимаю».
    """
    text, kb = await menu_card(await who(message.from_user))
    await open_menu(message, text, kb)
