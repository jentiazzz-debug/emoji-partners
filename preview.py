"""Показать карточки в терминале, не поднимая бота.

Правка текста — это цикл «поменял строчку → посмотрел, как легло».
Гонять ради него Telegram незачем: скрипт собирает те же карточки на
выдуманных данных и печатает их так, как их увидит партнёр — с
отступами цитат и без тегов.

    python preview.py

Заодно это проверка разметки: незакрытый <b> здесь видно сразу, а в
боте он оборачивается отказом отправки на весь текст.
"""

from __future__ import annotations

import html
import re
import sys
import time

import keyboards
import texts

TAG = re.compile(r"<[^>]+>")

# Консоль Windows по умолчанию в cp1251, а в карточках эмодзи и «▰».
# Без этого скрипт падает на первой же строке.
if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

NOW = int(time.time())

PARTNER = {
    "uid": 123_456_789,
    "username": "ivan",
    "name": "Иван",
    "joined_at": NOW - 86_400 * 40,
    "ref_by": None,
    "sub_until": 0,
    "banned": 0,
}

SUMS = {"bots": 2, "running": 1, "orders": 340, "revenue": 12_400, "clients": 128}

BOTS = [
    {
        "id": 1,
        "owner": PARTNER["uid"],
        "bot_id": 111,
        "username": "my_emoji_bot",
        "title": "My Emoji",
        "state": "running",
        "autostart": 1,
        "last_error": None,
        "created_at": NOW - 86_400 * 12,
        "orders": 302,
        "revenue": 11_100,
        "clients": 118,
        "stats_at": NOW - 300,
    },
    {
        "id": 2,
        "owner": PARTNER["uid"],
        "bot_id": 222,
        "username": "second_bot",
        "title": "Second",
        "state": "error",
        "autostart": 1,
        "last_error": "TelegramUnauthorizedError: token is invalid",
        "created_at": NOW - 86_400 * 2,
        "orders": 38,
        "revenue": 1_300,
        "clients": 10,
        "stats_at": NOW - 86_400,
    },
]


def plain(card: str) -> str:
    """Убрать теги так, как их «убирает» клиент: цитаты — с полосой."""
    out = []
    for chunk in re.split(r"<blockquote(?: expandable)?>|</blockquote>", card):
        out.append(html.unescape(TAG.sub("", chunk)).strip("\n"))
    blocks = []
    for i, chunk in enumerate(out):
        if not chunk:
            continue
        if i % 2:
            blocks.append("\n".join("│ " + s for s in chunk.split("\n")))
        else:
            blocks.append(chunk)
    return "\n\n".join(blocks)


def check(card: str) -> None:
    """Грубая проверка парности тегов — то, на чём падает Telegram."""
    for tag in ("b", "i", "code", "a", "blockquote"):
        opened = len(re.findall(rf"<{tag}(?: [^>]*)?>", card))
        closed = card.count(f"</{tag}>")
        if opened != closed:
            raise SystemExit(f"непарный <{tag}>: {opened} открыт, {closed} закрыт")


def show(title: str, card: str, kb=None) -> None:
    check(card)
    print("=" * 52)
    print(f"[{title}]")
    print("=" * 52)
    print(plain(card))
    if kb is not None:
        print("-" * 52)
        for row in kb.inline_keyboard:
            print("  " + "   ".join(f"[ {b.text} ]" for b in row))
    print()


def main() -> None:
    link = "https://t.me/EmojiPartners_bot?start=r123456789"
    empty = dict(PARTNER)
    no_bots = {"bots": 0, "running": 0, "orders": 0, "revenue": 0, "clients": 0}

    show("Главное меню", texts.menu(PARTNER, SUMS, 7), keyboards.menu(True))
    show("Меню — новый партнёр", texts.menu(empty, no_bots, 0), keyboards.menu())
    show("Кабинет", texts.account(PARTNER, SUMS, 7), keyboards.account())
    show(
        "Мои боты",
        texts.bots_list(PARTNER, BOTS),
        keyboards.bots_list(PARTNER, BOTS),
    )
    show(
        "Мои боты — пусто",
        texts.bots_list(PARTNER, []),
        keyboards.bots_list(PARTNER, []),
    )
    show("Карточка бота", texts.bot_card(BOTS[0]), keyboards.bot_card(BOTS[0]))
    show("Карточка бота — ошибка", texts.bot_card(BOTS[1]))
    show("Подключение бота", texts.add_bot_howto(), keyboards.cancel())
    show("Рефералы", texts.referral(PARTNER, 7, link), keyboards.referral())
    show("Подписка", texts.subscription(PARTNER, SUMS), keyboards.subscription())
    show("Лояльность", texts.loyalty(PARTNER, SUMS), keyboards.loyalty())
    show("Информация", texts.info(), keyboards.info())
    show("Что нового", texts.whatsnew(), keyboards.whatsnew())
    show(
        "Админка",
        texts.admin_root(
            {
                "partners": 42,
                "bots": 17,
                "running": 15,
                "orders": 4_120,
                "revenue": 138_400,
                "clients": 2_310,
            }
        ),
        keyboards.admin(),
    )
    show("Админка — боты", texts.admin_bots(BOTS), keyboards.admin_back())


if __name__ == "__main__":
    main()
