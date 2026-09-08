"""Клавиатуры. Меню — одно сообщение, которое перерисовывается на месте.

Раскладка главного экрана — это и есть та часть «дизайна», которую
видно раньше текста. Что здесь важно:

* самое частое действие — «Личный кабинет» — стоит первым и слева:
  большой палец добирается туда без перехвата телефона;
* два ряда по две кнопки вместо шести одиночных: столбик из шести
  одинаковых полос читается как список, а не как меню, и занимает
  весь экран;
* смысловые пары стоят рядом — деньги с деньгами, справка со справкой;
* поддержка — кнопкой-ссылкой: нажатие открывает диалог сразу, без
  промежуточного экрана «вот наш юзернейм».

Схема callback_data:
    m:<экран>   переход на экран
    a:<что>     действие внутри экрана (заглушки под свою логику)
"""

from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

import config
import texts

BACK = "‹ Назад"


def menu() -> InlineKeyboardMarkup:
    """Главное меню."""
    kb = InlineKeyboardBuilder()
    kb.button(text="👤 Личный кабинет", callback_data="m:account")
    kb.button(text="💎 Подписка", callback_data="m:sub")
    kb.button(text="🤖 Управление ботами", callback_data="m:bots")
    kb.button(text="💰 Программа лояльности", callback_data="m:loyalty")
    kb.button(text="ℹ️ Информация", callback_data="m:info")
    kb.button(text="🆕 Обновление", callback_data="m:new")
    kb.button(text="💬 Поддержка", url=config.SUPPORT_URL)
    kb.adjust(2, 1, 1, 2, 1)
    return kb.as_markup()


def _back(*rows: tuple[InlineKeyboardButton, ...]) -> InlineKeyboardMarkup:
    """Экран раздела: свои кнопки сверху, «Назад» — отдельным рядом снизу.

    «Назад» всегда одна и на своём месте: по нему промахиваются чаще
    всего, если он переезжает от экрана к экрану.
    """
    keyboard = [list(row) for row in rows if row]
    keyboard.append([InlineKeyboardButton(text=BACK, callback_data="m:root")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def account() -> InlineKeyboardMarkup:
    return _back(
        (
            InlineKeyboardButton(text="💸 Вывести", callback_data="a:payout"),
            InlineKeyboardButton(text="🧾 История", callback_data="a:history"),
        ),
        (
            InlineKeyboardButton(
                text="👥 Реферальная ссылка", callback_data="a:ref"
            ),
        ),
    )


def subscription() -> InlineKeyboardMarkup:
    """Тарифы — кнопками: цена на кнопке короче любого «выбрать тариф»."""
    row = tuple(
        InlineKeyboardButton(
            text=f"{price} {config.CURRENCY}", callback_data=f"a:buy:{i}"
        )
        for i, (_, price, _) in enumerate(config.SUB_PLANS)
    )
    return _back(row)


def bots() -> InlineKeyboardMarkup:
    return _back(
        (
            InlineKeyboardButton(
                text="➕ Добавить бота", callback_data="a:addbot"
            ),
        ),
        (
            InlineKeyboardButton(text="📋 Мои боты", callback_data="a:mybots"),
            InlineKeyboardButton(text="📘 Инструкция", url=config.GUIDE_URL),
        ),
    )


def loyalty() -> InlineKeyboardMarkup:
    return _back()


def info() -> InlineKeyboardMarkup:
    return _back(
        (
            InlineKeyboardButton(text="💬 Поддержка", url=config.SUPPORT_URL),
            InlineKeyboardButton(text="📘 Инструкция", url=config.GUIDE_URL),
        ),
    )


def whatsnew() -> InlineKeyboardMarkup:
    return _back()


#: Экраны раздела: текст и клавиатура в одном месте, чтобы добавить
#: новый пункт меню можно было одной строкой здесь и одной кнопкой выше.
SCREENS = {
    "account": (texts.account, account),
    "sub": (texts.subscription, subscription),
    "bots": (texts.bots, bots),
    "loyalty": (texts.loyalty, loyalty),
    "info": (lambda _p: texts.info(), info),
    "new": (lambda _p: texts.whatsnew(), whatsnew),
}
