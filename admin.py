"""Админка сервиса: партнёры, боты, журнал, рассылка.

Роутер подключается первым и фильтруется по ADMIN_IDS целиком — так
чужой callback вида «adm:...» до обработчиков просто не доходит, и
проверять права в каждом из них не нужно.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

import config
import db
import engine_stats
import handlers
import keyboards
import texts

log = logging.getLogger("partners.admin")
router = Router(name="admin")
router.message.filter(F.from_user.id.in_(config.ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(config.ADMIN_IDS))


class Cast(StatesGroup):
    text = State()


@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    await state.clear()
    sums = await db.service_totals()
    await message.answer(texts.admin_root(sums), reply_markup=keyboards.admin())


@router.callback_query(F.data.startswith("adm:"))
async def screen(call: CallbackQuery, state: FSMContext):
    what = call.data.split(":", 1)[1]

    if what == "root":
        await state.clear()
        sums = await db.service_totals()
        await handlers.render(call.message, texts.admin_root(sums), keyboards.admin())
    elif what == "partners":
        rows = await db.partners_page(limit=25)
        await handlers.render(
            call.message, texts.admin_partners(rows), keyboards.admin_back()
        )
    elif what == "bots":
        rows = await db.all_bots()
        await handlers.render(
            call.message, texts.admin_bots(rows), keyboards.admin_back()
        )
    elif what == "events":
        rows = await db.events(limit=25)
        await handlers.render(
            call.message, texts.admin_events(rows), keyboards.admin_back()
        )
    elif what == "refresh":
        await call.answer("Считаю…")
        done = await engine_stats.refresh_all()
        sums = await db.service_totals()
        await handlers.render(
            call.message,
            texts.admin_root(sums) + f"\n\n<i>Пересчитано ботов: {done}</i>",
            keyboards.admin(),
        )
        return
    else:
        await call.answer("Раздел недоступен", show_alert=True)
        return

    await call.answer()


# --------------------------------------------------------------------------
# Рассылка
# --------------------------------------------------------------------------


@router.message(Command("cast"))
async def cast_start(message: Message, state: FSMContext):
    await state.set_state(Cast.text)
    await message.answer(
        "✉️ <b>Рассылка</b>\n\nПришлите сообщение — оно уйдёт всем партнёрам "
        "как есть. Отмена — /menu."
    )


@router.message(Cast.text)
async def cast_send(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    ids = await db.all_partner_ids()
    sent = gone = 0
    for uid in ids:
        try:
            await message.send_copy(uid)
            sent += 1
        except TelegramRetryAfter as err:
            # Telegram сам говорит, сколько ждать. Спорить бессмысленно:
            # без паузы дальше пойдут отказы подряд.
            await asyncio.sleep(err.retry_after)
            try:
                await message.send_copy(uid)
                sent += 1
            except Exception:  # noqa: BLE001
                gone += 1
        except TelegramForbiddenError:
            gone += 1  # заблокировал бота
        except Exception as err:  # noqa: BLE001
            log.warning("рассылка %s: %s", uid, err)
            gone += 1
        # ~20 сообщений в секунду — предел, после которого Telegram
        # начинает отвечать RetryAfter на каждое второе.
        await asyncio.sleep(0.05)

    await db.log(message.from_user.id, "cast", f"отправлено {sent}")
    await message.answer(
        f"✅ Рассылка закончена.\n\nДоставлено: <b>{sent}</b>\n"
        f"Не доставлено: <b>{gone}</b>"
    )
