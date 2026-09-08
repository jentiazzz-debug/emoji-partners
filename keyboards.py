"""Клавиатуры. Меню — одно сообщение, которое перерисовывается на месте.

Раскладка главного экрана — это та часть оформления, которую видно
раньше текста. Что здесь важно:

* самые частые действия — кабинет и боты — стоят первым рядом;
* два ряда по две кнопки вместо шести одиночных: столбик одинаковых
  полос читается как список, а не как меню, и занимает весь экран;
* смысловые пары стоят рядом: деньги с деньгами, справка со справкой;
* поддержка — кнопкой-ссылкой: нажатие открывает диалог сразу, без
  промежуточного экрана «вот наш юзернейм».

Схема callback_data:
    m:<экран>          переход на экран
    b:<id>             карточка бота
    bx:<id>:<команда>  действие с ботом
    addbot             подключение нового бота
    adm:<экран>        админка сервиса
"""

from __future__ import annotations

from typing import Mapping, Sequence

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import partners
import texts

BACK = "‹ Назад"


def _kb(
    rows: Sequence[Sequence[InlineKeyboardButton]],
    back: str | None = "m:root",
) -> InlineKeyboardMarkup:
    """Экран: свои кнопки, «Назад» — всегда отдельным рядом снизу.

    «Назад» не переезжает от экрана к экрану: по нему промахиваются
    чаще всего, когда он каждый раз в новом месте.
    """
    keyboard = [list(row) for row in rows if row]
    if back:
        keyboard.append([InlineKeyboardButton(text=BACK, callback_data=back)])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def menu(is_admin: bool = False) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Кабинет", callback_data="m:account")
    kb.button(text="🤖 Мои боты", callback_data="m:bots")
    kb.button(text="💰 Уровни и комиссия", callback_data="m:loyalty")
    kb.button(text="💎 Подписка", callback_data="m:sub")
    kb.button(text="🤝 Рефералы", callback_data="m:ref")
    kb.button(text="ℹ️ Информация", callback_data="m:info")
    kb.button(text="🆕 Обновление", callback_data="m:new")
    kb.button(text="💬 Поддержка", url=config.SUPPORT_URL)
    sizes = [2, 1, 2, 2, 1]
    if is_admin:
        kb.button(text="🛠 Админка", callback_data="adm:root")
        sizes.append(1)
    kb.adjust(*sizes)
    return kb.as_markup()


def account() -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                InlineKeyboardButton(text="🤖 Мои боты", callback_data="m:bots"),
                InlineKeyboardButton(text="🤝 Рефералы", callback_data="m:ref"),
            ],
        ]
    )


def referral() -> InlineKeyboardMarkup:
    return _kb([])


def bots_list(row: Mapping, rows: Sequence[Mapping]) -> InlineKeyboardMarkup:
    """Список ботов: по кнопке на бота, статус — значком в подписи."""
    keyboard = [
        [
            InlineKeyboardButton(
                text=f"{texts.STATE_ICONS.get(item['state'], '')} @{item['username']}",
                callback_data=f"b:{item['id']}",
            )
        ]
        for item in rows
    ]
    if partners.can_add_bot(row, len(rows)):
        keyboard.append(
            [InlineKeyboardButton(text="➕ Подключить бота", callback_data="addbot")]
        )
    else:
        keyboard.append(
            [InlineKeyboardButton(text="💎 Снять лимит", callback_data="m:sub")]
        )
    return _kb(keyboard)


def bot_card(item: Mapping) -> InlineKeyboardMarkup:
    running = item["state"] == "running"
    power = (
        InlineKeyboardButton(text="⏹ Остановить", callback_data=f"bx:{item['id']}:stop")
        if running
        else InlineKeyboardButton(
            text="▶️ Запустить", callback_data=f"bx:{item['id']}:start"
        )
    )
    auto = "🔁 Автозапуск: вкл" if item["autostart"] else "⚪️ Автозапуск: выкл"
    return _kb(
        [
            [
                power,
                InlineKeyboardButton(
                    text="🔄 Перезапустить", callback_data=f"bx:{item['id']}:restart"
                ),
            ],
            [
                InlineKeyboardButton(text=auto, callback_data=f"bx:{item['id']}:auto"),
                InlineKeyboardButton(
                    text="📊 Обновить", callback_data=f"bx:{item['id']}:stats"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🗑 Отключить", callback_data=f"bx:{item['id']}:del"
                ),
            ],
        ],
        back="m:bots",
    )


def confirm_delete(item: Mapping) -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                InlineKeyboardButton(
                    text="🗑 Да, отключить", callback_data=f"bx:{item['id']}:delyes"
                ),
                InlineKeyboardButton(
                    text="‹ Отмена", callback_data=f"b:{item['id']}"
                ),
            ]
        ],
        back=None,
    )


def cancel(to: str = "m:bots") -> InlineKeyboardMarkup:
    return _kb([], back=to)


def subscription() -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text=f"{price} ₽", callback_data=f"buy:{i}")
        for i, (_, price, _) in enumerate(config.SUB_PLANS)
    ]
    return _kb([row])


def loyalty() -> InlineKeyboardMarkup:
    return _kb([])


def info() -> InlineKeyboardMarkup:
    row = [
        InlineKeyboardButton(text="💬 Поддержка", url=config.SUPPORT_URL),
        InlineKeyboardButton(text="📘 Инструкция", url=config.GUIDE_URL),
    ]
    if config.CHANNEL:
        row.append(InlineKeyboardButton(text="📣 Канал", url=config.CHANNEL_URL))
    return _kb([row])


def whatsnew() -> InlineKeyboardMarkup:
    return _kb([])


def admin() -> InlineKeyboardMarkup:
    return _kb(
        [
            [
                InlineKeyboardButton(text="👥 Партнёры", callback_data="adm:partners"),
                InlineKeyboardButton(text="🤖 Боты", callback_data="adm:bots"),
            ],
            [
                InlineKeyboardButton(text="📜 Журнал", callback_data="adm:events"),
                InlineKeyboardButton(
                    text="📊 Пересчитать", callback_data="adm:refresh"
                ),
            ],
        ]
    )


def admin_back() -> InlineKeyboardMarkup:
    return _kb([], back="adm:root")
