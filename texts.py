"""Карточки экранов. Разметка — HTML, включена по умолчанию в main.py.

О вёрстке, раз уж просили «дизайн получше». Telegram даёт ровно четыре
инструмента: жирный, моноширинный, цитата и пустая строка. Отсюда
правила, по которым собраны все карточки:

* шапка отделена от тела пустой строкой, а не линией из «━━━» —
  такие линии в мобильной ленте читаются как мусор;
* уровень, тарифы и лестница ступеней завёрнуты в <blockquote>: клиент
  рисует их отдельным блоком с полосой слева, и глазу есть за что
  зацепиться;
* полоса прогресса — в <code>: моноширинный шрифт держит ширину ячеек,
  иначе полоса «пляшет» на разных значениях;
* справочные ссылки — в раскрывающейся цитате: свёрнутыми они не
  занимают пол-экрана, но и не потеряны.

Всё, что приходит от людей (имя партнёра), проходит через esc(): «&»
или «<» в имени иначе роняют отправку целиком.
"""

from __future__ import annotations

import html
from typing import Any

import config
from partners import LEVELS, Partner

NL = "\n"


def esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=False)


#: Неразрывный пробел. В разрядах суммы и перед знаком валюты он
#: обязателен: обычный пробел клиент переносит на новую строку, и
#: «1 240.00 ₽» разваливается ровно посередине.
NBSP = "\u00a0"


def money(value: float) -> str:
    """Деньги: «1 240.00 ₽», разряды — неразрывным пробелом."""
    return f"{value:,.2f}".replace(",", NBSP) + NBSP + config.CURRENCY


def short_money(value: float) -> str:
    """То же, но без копеек — для лестницы уровней."""
    return f"{value:,.0f}".replace(",", NBSP) + NBSP + config.CURRENCY


def plural(n: int, one: str, few: str, many: str) -> str:
    """«1 бот, 2 бота, 5 ботов» — без этого карточка выдаёт робота."""
    n = abs(int(n))
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def bar(share: float, cells: int = 10) -> str:
    """Полоса прогресса из закрашенных и пустых ячеек.

    Первая ячейка закрашивается при любом ненулевом прогрессе: пустая
    полоса у партнёра, который уже что-то заработал, читается как
    «ничего не засчитано».
    """
    share = min(1.0, max(0.0, share))
    full = int(share * cells)
    if share > 0 and full == 0:
        full = 1
    return "▰" * full + "▱" * (cells - full)


def percent(share: float) -> int:
    """Процент прогресса, округлённый вниз.

    Именно вниз: округление к ближайшему рисует «100%» тому, кому до
    уровня осталась копейка, и человек идёт в поддержку выяснять,
    почему уровень не поднялся.
    """
    share = min(1.0, max(0.0, share))
    return 100 if share >= 1 else int(share * 100)


def fee(value: float) -> str:
    """Комиссия: «8%», без хвоста «.0» у целых."""
    return f"{value:g}%"


# --------------------------------------------------------------------------
# Главное меню
# --------------------------------------------------------------------------


def menu(p: Partner) -> str:
    lvl = p.level
    nxt = p.next_level

    if nxt:
        goal = (
            f"<code>{bar(p.progress)}</code>  {percent(p.progress)}%\n"
            f"До уровня <b>{esc(nxt.name)}</b> — <b>{money(p.left)}</b>"
        )
    else:
        goal = (
            f"<code>{bar(1)}</code>  100%\n"
            "Максимальный уровень — комиссия минимальная."
        )

    stats = (
        f"💰 <b>{money(p.balance)}</b> к выводу   •   "
        f"🤖 <b>{p.bots}</b> {plural(p.bots, 'бот', 'бота', 'ботов')}   •   "
        f"👥 <b>{p.refs}</b> {plural(p.refs, 'реферал', 'реферала', 'рефералов')}"
    )

    links = (
        f"🤖 Пример бота-франшизы — {esc(config.DEMO_BOT)}\n"
        f'📋 Как собрать своего — <a href="{config.GUIDE_URL}">инструкция</a>\n'
        f"💬 Поддержка партнёров — {esc(config.SUPPORT)}\n"
        f"🛡 Свой VPN в один клик — {esc(config.VPN_BOT)}"
    )

    return (
        f"✦ <b>{esc(config.BRAND)}</b> ✦\n"
        f"\n"
        f"Привет, <b>{esc(p.name)}</b>! Рады видеть.\n"
        f"\n"
        f"<blockquote>{lvl.icon} <b>{esc(lvl.name)}</b>  ·  "
        f"комиссия сервиса <b>{fee(lvl.fee)}</b>\n"
        f"{goal}</blockquote>\n"
        f"\n"
        f"{stats}\n"
        f"\n"
        f"<blockquote expandable>{links}</blockquote>\n"
        f"\n"
        f"Выберите раздел ниже 👇"
    )


# --------------------------------------------------------------------------
# Разделы
# --------------------------------------------------------------------------


def account(p: Partner) -> str:
    lvl = p.level
    return (
        f"👤 <b>Личный кабинет</b>\n"
        f"\n"
        f"<blockquote>ID · <code>{p.uid}</code>\n"
        f"Уровень · {lvl.icon} <b>{esc(lvl.name)}</b>\n"
        f"Комиссия · <b>{fee(lvl.fee)}</b></blockquote>\n"
        f"\n"
        f"💰 Доступно к выводу — <b>{money(p.balance)}</b>\n"
        f"📈 Заработано всего — <b>{money(p.earned)}</b>\n"
        f"🤖 Ботов подключено — <b>{p.bots}</b>\n"
        f"👥 Рефералов — <b>{p.refs}</b>\n"
        f"\n"
        f"Вывод — от {esc(config.MIN_PAYOUT)}{NBSP}{config.CURRENCY}, "
        f"заявки обрабатываются в течение суток."
    )


def subscription(p: Partner) -> str:
    status = (
        f"активна до <b>{esc(p.sub_until)}</b>"
        if p.sub_until
        else "<b>не подключена</b>"
    )
    plans = NL.join(
        f"{name} — <b>{price}{NBSP}{config.CURRENCY}</b>"
        + (f"  ·  {note}" if note else "")
        for name, price, note in config.SUB_PLANS
    )
    return (
        f"💎 <b>Подписка</b>\n"
        f"\n"
        f"Статус · {status}\n"
        f"\n"
        f"Что даёт:\n"
        f"• комиссия сервиса ниже на <b>2%</b>\n"
        f"• без лимита на количество ботов\n"
        f"• приоритетная очередь в поддержке\n"
        f"• расширенная статистика и выгрузки\n"
        f"\n"
        f"<blockquote>{plans}</blockquote>\n"
        f"\n"
        f"Продление — вручную: списаний без вашего ведома не будет."
    )


def bots(p: Partner) -> str:
    if p.bots:
        head = (
            f"Подключено <b>{p.bots}</b> "
            f"{plural(p.bots, 'бот', 'бота', 'ботов')}. "
            f"Открывайте любого кнопкой ниже."
        )
    else:
        head = "Пока ни одного бота — самое время создать первого."
    return (
        f"🤖 <b>Управление ботами</b>\n"
        f"\n"
        f"{head}\n"
        f"\n"
        f"<blockquote>Как это работает:\n"
        f"1. Берёте токен у @BotFather\n"
        f"2. Добавляете его кнопкой ниже\n"
        f"3. Настраиваете витрину и цены\n"
        f"4. Получаете выплату с каждой продажи</blockquote>\n"
        f"\n"
        f'Подробности — <a href="{config.GUIDE_URL}">в инструкции</a>. '
        f"Готовый пример: {esc(config.DEMO_BOT)}"
    )


def loyalty(p: Partner) -> str:
    """Лестница уровней. Текущая ступень помечена и выделена жирным."""
    current = p.level
    rows = []
    for lvl in LEVELS:
        line = (
            f"{lvl.icon} {lvl.name}  ·  {fee(lvl.fee)}  ·  "
            f"от {short_money(lvl.need)}"
        )
        rows.append(f"▸ <b>{line}</b>" if lvl is current else f"   {line}")
    tail = (
        f"До <b>{esc(p.next_level.name)}</b> осталось заработать "
        f"<b>{money(p.left)}</b>."
        if p.next_level
        else "Вы на вершине лестницы — комиссия минимальная."
    )
    return (
        f"💰 <b>Программа лояльности</b>\n"
        f"\n"
        f"Чем больше заработано, тем меньше берёт сервис. "
        f"Уровень считается от общего заработка и не сгорает.\n"
        f"\n"
        f"<blockquote>{NL.join(rows)}</blockquote>\n"
        f"\n"
        f"<code>{bar(p.progress)}</code>  {percent(p.progress)}%\n"
        f"{tail}"
    )


def info() -> str:
    return (
        f"ℹ️ <b>Информация</b>\n"
        f"\n"
        f"{esc(config.BRAND)} — партнёрская программа: вы запускаете своего "
        f"бота на нашем движке, мы берём на себя платежи, доставку и "
        f"техчасть, вы получаете процент с каждой продажи.\n"
        f"\n"
        f"<blockquote>💬 Поддержка — {esc(config.SUPPORT)}\n"
        f"🤖 Пример бота — {esc(config.DEMO_BOT)}\n"
        f"🛡 VPN в один клик — {esc(config.VPN_BOT)}\n"
        f'📋 Инструкция — <a href="{config.GUIDE_URL}">открыть</a>'
        f"</blockquote>\n"
        f"\n"
        f"Поддержка отвечает с 10:00 до 22:00 МСК. В нерабочее время "
        f"заявка не теряется — ответим утром."
    )


#: Что нового. Верхняя запись — самая свежая; её дата подставляется в
#: подпись кнопки в меню, поэтому лежит рядом с текстом.
CHANGELOG: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "08.09.2026",
        (
            "Новое главное меню: уровень, прогресс и баланс видно сразу",
            "Раздел «Подписка» вместо субпартнёрки",
            "Лестница уровней с подсветкой текущей ступени",
        ),
    ),
    (
        "21.08.2026",
        (
            "Ускорили выплаты — заявки уходят в течение суток",
            "Починили статистику по рефералам второго уровня",
        ),
    ),
)


def whatsnew() -> str:
    blocks = []
    for date, items in CHANGELOG:
        lines = NL.join(f"• {item}" for item in items)
        blocks.append(f"<b>{date}</b>\n{lines}")
    return (
        "🆕 <b>Что нового</b>\n"
        "\n"
        + "\n\n".join(blocks)
        + f"\n\nВопрос по обновлению — {esc(config.SUPPORT)}"
    )
