"""Карточки экранов. Разметка — HTML, включена по умолчанию в main.py.

О вёрстке. Telegram даёт ровно четыре инструмента: жирный,
моноширинный, цитата и пустая строка. Отсюда правила, по которым
собраны все карточки:

* шапка отделена от тела пустой строкой, а не линией из «━━━» —
  такие линии в мобильной ленте читаются как мусор;
* уровень, тарифы и лестница ступеней завёрнуты в <blockquote>: клиент
  рисует их отдельным блоком с полосой слева, и глазу есть за что
  зацепиться;
* полоса прогресса — в <code>: моноширинный шрифт держит ширину ячеек,
  иначе полоса «пляшет» на разных значениях;
* справочные ссылки — в раскрывающейся цитате: свёрнутыми они не
  занимают пол-экрана, но и не потеряны.

Всё, что приходит от людей (имя партнёра, юзернейм его бота, текст
ошибки движка), проходит через esc(): «&» или «<» в любом из них
роняют отправку карточки целиком.
"""

from __future__ import annotations

import html
import time
from datetime import datetime
from typing import Any, Mapping, Sequence

import config
import partners

NL = "\n"

#: Неразрывный пробел. В разрядах числа он обязателен: обычный пробел
#: клиент переносит на новую строку, и «12 400» рвётся пополам.
NBSP = " "

#: Значок состояния отдельно от подписи: на кнопке места на слова нет,
#: а цветной кружок читается и там, и в списке.
STATE_ICONS = {"running": "🟢", "stopped": "⚪️", "error": "🔴"}

#: Состояния бота: как хранится → как показывается.
STATES = {
    "running": "🟢 работает",
    "stopped": "⚪️ остановлен",
    "error": "🔴 ошибка",
}


def esc(text: Any) -> str:
    return html.escape(str(text or ""), quote=False)


def num(value: int) -> str:
    return f"{int(value):,}".replace(",", NBSP)


def stars(value: int) -> str:
    return f"{num(value)}{NBSP}{config.CURRENCY}"


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
    полоса у партнёра, который уже что-то продал, читается как
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
    уровня осталась пара звёзд, и человек идёт в поддержку выяснять,
    почему уровень не поднялся.
    """
    share = min(1.0, max(0.0, share))
    return 100 if share >= 1 else int(share * 100)


def fee(value: float) -> str:
    return f"{value:g}%"


def when(ts: int) -> str:
    return datetime.fromtimestamp(int(ts)).strftime("%d.%m.%Y") if ts else "—"


def ago(ts: int) -> str:
    """«5 минут назад» — для отметки о свежести статистики."""
    if not ts:
        return "ещё не считалась"
    gap = max(0, int(time.time()) - int(ts))
    if gap < 90:
        return "только что"
    if gap < 3600:
        n = gap // 60
        return f"{n} {plural(n, 'минуту', 'минуты', 'минут')} назад"
    if gap < 86400:
        n = gap // 3600
        return f"{n} {plural(n, 'час', 'часа', 'часов')} назад"
    n = gap // 86400
    return f"{n} {plural(n, 'день', 'дня', 'дней')} назад"


# --------------------------------------------------------------------------
# Главное меню
# --------------------------------------------------------------------------


def menu(row: Mapping, sums: Mapping, refs: int) -> str:
    revenue = int(sums["revenue"])
    lvl = partners.level_of(revenue)
    nxt = partners.next_of(revenue)
    fee_now = partners.fee_of(row, revenue)

    head = f"{lvl.icon} <b>{esc(lvl.name)}</b>  ·  комиссия <b>{fee(fee_now)}</b>"
    if partners.has_sub(row):
        head += " <i>(с подпиской)</i>"

    if nxt:
        goal = (
            f"<code>{bar(partners.progress(revenue))}</code>  "
            f"{percent(partners.progress(revenue))}%\n"
            f"До уровня <b>{esc(nxt.name)}</b> — "
            f"<b>{stars(partners.left(revenue))}</b> оборота"
        )
    else:
        goal = (
            f"<code>{bar(1)}</code>  100%\n"
            "Максимальный уровень — комиссия минимальная."
        )

    bots = int(sums["bots"])
    if bots:
        line = (
            f"🤖 <b>{bots}</b> {plural(bots, 'бот', 'бота', 'ботов')}"
            f" ({int(sums['running'])} в работе)   •   "
            f"🎨 <b>{num(sums['orders'])}</b> "
            f"{plural(int(sums['orders']), 'заказ', 'заказа', 'заказов')}"
            f"   •   ⭐️ <b>{num(revenue)}</b>"
        )
    else:
        line = "🤖 Ботов пока нет — первый подключается за пару минут."

    links = (
        f"🎨 Как выглядит бот — {esc(config.DEMO_BOT)}\n"
        f'📘 Как запустить свой — <a href="{config.GUIDE_URL}">инструкция</a>\n'
        f"💬 Поддержка партнёров — {esc(config.SUPPORT)}\n"
        f"👥 Рефералов приведено — {refs}"
    )

    return (
        f"✦ <b>{esc(config.BRAND)}</b> ✦\n"
        f"\n"
        f"Привет, <b>{esc(row['name'])}</b>! "
        f"Ваш бот собирает анимированные эмодзи, вы получаете долю с продаж.\n"
        f"\n"
        f"<blockquote>{head}\n{goal}</blockquote>\n"
        f"\n"
        f"{line}\n"
        f"\n"
        f"<blockquote expandable>{links}</blockquote>\n"
        f"\n"
        f"Выберите раздел ниже 👇"
    )


# --------------------------------------------------------------------------
# Кабинет
# --------------------------------------------------------------------------


def account(row: Mapping, sums: Mapping, refs: int) -> str:
    revenue = int(sums["revenue"])
    lvl = partners.level_of(revenue)
    sub = (
        f"активна до <b>{when(row['sub_until'])}</b>"
        if partners.has_sub(row)
        else "нет"
    )
    limit = partners.bot_limit(row)
    return (
        f"👤 <b>Личный кабинет</b>\n"
        f"\n"
        f"<blockquote>ID · <code>{row['uid']}</code>\n"
        f"Уровень · {lvl.icon} <b>{esc(lvl.name)}</b>\n"
        f"Комиссия · <b>{fee(partners.fee_of(row, revenue))}</b>\n"
        f"Подписка · {sub}\n"
        f"С нами с · {when(row['joined_at'])}</blockquote>\n"
        f"\n"
        f"🤖 Ботов — <b>{sums['bots']}</b>, в работе <b>{sums['running']}</b>"
        f"{'' if limit == 0 else f', лимит {limit}'}\n"
        f"👥 Клиентов в ботах — <b>{num(sums['clients'])}</b>\n"
        f"🎨 Заказов собрано — <b>{num(sums['orders'])}</b>\n"
        f"⭐️ Оборот — <b>{num(revenue)}</b>\n"
        f"🤝 Рефералов — <b>{refs}</b>\n"
        f"\n"
        f"<blockquote expandable>Оборот считается по оплаченным заказам "
        f"в ваших ботах и пересчитывается автоматически. Выплаты и "
        f"списание комиссии подключаются отдельно — до тех пор звёзды "
        f"остаются на счёте вашего бота.</blockquote>"
    )


def referral(row: Mapping, refs: int, link: str) -> str:
    return (
        f"🤝 <b>Реферальная программа</b>\n"
        f"\n"
        f"Приводите тех, кто хочет свой бот-конструктор эмодзи. "
        f"Каждый, кто пришёл по вашей ссылке, закрепляется за вами "
        f"навсегда — переоткрыть чужую ссылку и «сменить» пригласившего "
        f"нельзя.\n"
        f"\n"
        f"<blockquote>Приведено: <b>{refs}</b> "
        f"{plural(refs, 'партнёр', 'партнёра', 'партнёров')}</blockquote>\n"
        f"\n"
        f"Ваша ссылка:\n<code>{esc(link)}</code>\n"
        f"\n"
        f"Начисления за рефералов включатся вместе с денежной частью — "
        f"счётчик уже работает, ничего не потеряется."
    )


# --------------------------------------------------------------------------
# Боты
# --------------------------------------------------------------------------


def bots_list(row: Mapping, rows: Sequence[Mapping]) -> str:
    limit = partners.bot_limit(row)
    if not rows:
        return (
            f"🤖 <b>Мои боты</b>\n"
            f"\n"
            f"Пока ни одного. Свой бот запускается за пару минут: берёте "
            f"токен у @BotFather, присылаете его сюда — дальше всё делаем "
            f"мы.\n"
            f"\n"
            f"<blockquote>Что получит ваш бот:\n"
            f"• 250 анимированных шаблонов и 6 шрифтов\n"
            f"• сборку наборов премиум-эмодзи и стикеров\n"
            f"• приём оплаты звёздами\n"
            f"• свою админку: цены, рассылка, статистика</blockquote>\n"
            f"\n"
            f"Посмотреть, как это выглядит у клиента: {esc(config.DEMO_BOT)}"
        )

    lines = []
    for item in rows:
        mark = STATES.get(item["state"], item["state"])
        lines.append(
            f"{mark}  @{esc(item['username'])}\n"
            f"    🎨 {num(item['orders'])}  ·  ⭐️ {num(item['revenue'])}  ·  "
            f"👥 {num(item['clients'])}"
        )
    tail = (
        "Лимит ботов исчерпан — снимается подпиской."
        if not partners.can_add_bot(row, len(rows))
        else f"Можно подключить ещё "
        f"<b>{'сколько угодно' if limit == 0 else limit - len(rows)}</b>."
    )
    return (
        f"🤖 <b>Мои боты</b>\n"
        f"\n"
        f"<blockquote>{NL.join(lines)}</blockquote>\n"
        f"\n"
        f"Статистика обновляется автоматически. {tail}"
    )


def bot_card(item: Mapping) -> str:
    mark = STATES.get(item["state"], item["state"])
    card = (
        f"🤖 <b>@{esc(item['username'])}</b>\n"
        f"\n"
        f"<blockquote>Статус · {mark}\n"
        f"Автозапуск · {'включён' if item['autostart'] else 'выключен'}\n"
        f"Подключён · {when(item['created_at'])}</blockquote>\n"
        f"\n"
        f"👥 Клиентов — <b>{num(item['clients'])}</b>\n"
        f"🎨 Заказов — <b>{num(item['orders'])}</b>\n"
        f"⭐️ Оборот — <b>{num(item['revenue'])}</b>\n"
        f"\n"
        f"<i>Данные обновлены {ago(item['stats_at'])}.</i>"
    )
    if item["state"] == "error" and item["last_error"]:
        card += (
            f"\n\n<blockquote expandable>Последняя ошибка:\n"
            f"<code>{esc(item['last_error'])[:900]}</code></blockquote>"
        )
    return card


def add_bot_howto() -> str:
    return (
        f"➕ <b>Подключение бота</b>\n"
        f"\n"
        f"<blockquote>1. Откройте @BotFather → <code>/newbot</code>\n"
        f"2. Придумайте имя и юзернейм (должен кончаться на <code>bot</code>)\n"
        f"3. Скопируйте токен — длинную строку вида\n"
        f"<code>1234567890:AAG...</code>\n"
        f"4. Пришлите его следующим сообщением</blockquote>\n"
        f"\n"
        f"Токен нужен, чтобы запустить движок от имени вашего бота. "
        f"Храните его как пароль: у кого токен — тот и управляет ботом. "
        f"Если случайно отправили его в чужой чат, отзовите в @BotFather "
        f"командой <code>/revoke</code> и пришлите новый.\n"
        f"\n"
        f"Отменить — кнопкой ниже."
    )


def token_bad(reason: str) -> str:
    return (
        f"❌ <b>Токен не подошёл</b>\n"
        f"\n"
        f"{esc(reason)}\n"
        f"\n"
        f"Пришлите другой токен или вернитесь в меню."
    )


def bot_added(username: str, started: bool, note: str) -> str:
    head = (
        f"✅ <b>Бот @{esc(username)} подключён</b>"
        if started
        else f"⚠️ <b>Бот @{esc(username)} подключён, но не запустился</b>"
    )
    return (
        f"{head}\n"
        f"\n"
        f"{esc(note)}\n"
        f"\n"
        f"Загляните в бота и нажмите <code>/start</code> — вы его админ: "
        f"цена, оформление и рассылка настраиваются командой "
        f"<code>/admin</code> внутри самого бота."
    )


# --------------------------------------------------------------------------
# Подписка и лояльность
# --------------------------------------------------------------------------


def subscription(row: Mapping, sums: Mapping) -> str:
    revenue = int(sums["revenue"])
    status = (
        f"активна до <b>{when(row['sub_until'])}</b>"
        if partners.has_sub(row)
        else "<b>не подключена</b>"
    )
    plans = NL.join(
        f"{name} — <b>{price}{NBSP}₽</b>" + (f"  ·  {note}" if note else "")
        for name, price, note in config.SUB_PLANS
    )
    base = partners.level_of(revenue).fee
    return (
        f"💎 <b>Подписка</b>\n"
        f"\n"
        f"Статус · {status}\n"
        f"\n"
        f"Что даёт:\n"
        f"• комиссия ниже на <b>{fee(config.SUB_DISCOUNT)}</b> — "
        f"на вашем уровне это {fee(base)} → "
        f"<b>{fee(max(0.0, base - config.SUB_DISCOUNT))}</b>\n"
        f"• без лимита на количество ботов\n"
        f"• приоритетная очередь в поддержке\n"
        f"• ранний доступ к новым шаблонам\n"
        f"\n"
        f"<blockquote>{plans}</blockquote>\n"
        f"\n"
        f"Оплата подключается вместе с денежной частью сервиса. "
        f"Нужна подписка сейчас — напишите в {esc(config.SUPPORT)}."
    )


def loyalty(row: Mapping, sums: Mapping) -> str:
    revenue = int(sums["revenue"])
    current = partners.level_of(revenue)
    rows = []
    for lvl in partners.LEVELS:
        line = f"{lvl.icon} {lvl.name}  ·  {fee(lvl.fee)}  ·  от {num(lvl.need)} ⭐️"
        rows.append(f"▸ <b>{line}</b>" if lvl is current else f"   {line}")
    nxt = partners.next_of(revenue)
    tail = (
        f"До <b>{esc(nxt.name)}</b> осталось наработать "
        f"<b>{stars(partners.left(revenue))}</b> оборота."
        if nxt
        else "Вы на вершине лестницы — комиссия минимальная."
    )
    return (
        f"💰 <b>Программа лояльности</b>\n"
        f"\n"
        f"Чем больше продают ваши боты, тем меньше берёт сервис. "
        f"Уровень считается по общему обороту и не сгорает.\n"
        f"\n"
        f"<blockquote>{NL.join(rows)}</blockquote>\n"
        f"\n"
        f"<code>{bar(partners.progress(revenue))}</code>  "
        f"{percent(partners.progress(revenue))}%\n"
        f"{tail}"
    )


def info() -> str:
    channel = (
        f'\n📣 Канал — <a href="{config.CHANNEL_URL}">{esc(config.CHANNEL)}</a>'
        if config.CHANNEL
        else ""
    )
    return (
        f"ℹ️ <b>Информация</b>\n"
        f"\n"
        f"{esc(config.BRAND)} — франшиза бота-конструктора анимированных "
        f"эмодзи. Вы приводите аудиторию и держите свой бренд, мы держим "
        f"движок: 250 TGS-шаблонов, шрифты, сборку наборов, приём оплаты "
        f"звёздами и сервер.\n"
        f"\n"
        f"<blockquote>🎨 Пример бота — {esc(config.DEMO_BOT)}\n"
        f"💬 Поддержка — {esc(config.SUPPORT)}\n"
        f'📘 Инструкция — <a href="{config.GUIDE_URL}">открыть</a>{channel}'
        f"</blockquote>\n"
        f"\n"
        f"Бот партнёра работает на нашем сервере и переживает "
        f"перезапуски: если процесс упал, он поднимается сам."
    )


#: Что нового. Верхняя запись — самая свежая.
CHANGELOG: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "08.09.2026",
        (
            "Запуск Emoji Partners: подключение своего бота по токену",
            "Кабинет с уровнем, оборотом и статистикой по каждому боту",
            "Автоматический перезапуск упавших ботов",
        ),
    ),
)


def whatsnew() -> str:
    blocks = []
    for date, items in CHANGELOG:
        lines = NL.join(f"• {item}" for item in items)
        blocks.append(f"<b>{date}</b>\n{lines}")
    return (
        "🆕 <b>Что нового</b>\n\n"
        + "\n\n".join(blocks)
        + f"\n\nВопрос по обновлению — {esc(config.SUPPORT)}"
    )


# --------------------------------------------------------------------------
# Админка сервиса
# --------------------------------------------------------------------------


def admin_root(sums: Mapping) -> str:
    return (
        f"🛠 <b>Админка {esc(config.BRAND)}</b>\n"
        f"\n"
        f"<blockquote>Партнёров · <b>{num(sums.get('partners', 0))}</b>\n"
        f"Ботов · <b>{num(sums.get('bots', 0))}</b>, "
        f"в работе <b>{num(sums.get('running', 0))}</b>\n"
        f"Клиентов · <b>{num(sums.get('clients', 0))}</b>\n"
        f"Заказов · <b>{num(sums.get('orders', 0))}</b>\n"
        f"Оборот · <b>{stars(sums.get('revenue', 0))}</b></blockquote>\n"
        f"\n"
        f"Оборот — сумма по базам всех дочерних ботов."
    )


def admin_bots(rows: Sequence[Mapping]) -> str:
    if not rows:
        return "🤖 <b>Боты</b>\n\nНи одного бота ещё не подключено."
    lines = [
        f"{STATES.get(r['state'], r['state'])}  @{esc(r['username'])}  ·  "
        f"id владельца <code>{r['owner']}</code>  ·  ⭐️ {num(r['revenue'])}"
        for r in rows
    ]
    return f"🤖 <b>Боты</b>\n\n<blockquote>{NL.join(lines)}</blockquote>"


def admin_partners(rows: Sequence[Mapping]) -> str:
    if not rows:
        return "👥 <b>Партнёры</b>\n\nПока никого."
    lines = []
    for r in rows:
        who = f"@{esc(r['username'])}" if r["username"] else esc(r["name"])
        flag = " 🚫" if r["banned"] else ""
        lines.append(f"{who} · <code>{r['uid']}</code> · {when(r['joined_at'])}{flag}")
    return f"👥 <b>Партнёры</b>\n\n<blockquote>{NL.join(lines)}</blockquote>"


def admin_events(rows: Sequence[Mapping]) -> str:
    if not rows:
        return "📜 <b>Журнал</b>\n\nПусто."
    lines = [
        f"{datetime.fromtimestamp(r['ts']).strftime('%d.%m %H:%M')} · "
        f"{esc(r['kind'])} · {esc(r['text'])}"
        for r in rows
    ]
    return f"📜 <b>Журнал</b>\n\n<blockquote expandable>{NL.join(lines)}</blockquote>"
