"""Показать карточки в терминале, не поднимая бота.

Правка текста меню — это цикл «поменял строчку → посмотрел, как легло».
Гонять ради него Telegram незачем: скрипт собирает те же карточки и
печатает их так, как их увидит человек — с отступами цитат и без тегов.

    python preview.py

Заодно это проверка разметки: незакрытый <b> здесь видно сразу, а в
боте он оборачивается отказом отправки на весь текст.
"""

from __future__ import annotations

import html
import re
import sys

import keyboards
import partners
import texts

TAG = re.compile(r"<[^>]+>")

# Консоль Windows по умолчанию в cp1251, а в карточках эмодзи и «▰».
# Без этого скрипт падает на первой же строке — вместо предпросмотра
# человек получает UnicodeEncodeError.
if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def plain(card: str) -> str:
    """Убрать теги так, как их «убирает» клиент: цитаты — с полосой."""
    out = []
    for chunk in re.split(r"<blockquote(?: expandable)?>|</blockquote>", card):
        text = html.unescape(TAG.sub("", chunk)).strip("\n")
        out.append(text)
    # Нечётные куски — это то, что было внутри цитаты. Блоки разделены
    # пустой строкой: клиент тоже отбивает цитату от соседнего текста,
    # и без этого предпросмотр врёт про плотность карточки.
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
    """Грубая проверка парности тегов — ровно то, на чём падает Telegram."""
    for tag in ("b", "code", "a", "blockquote"):
        opened = len(re.findall(rf"<{tag}(?: [^>]*)?>", card))
        closed = card.count(f"</{tag}>")
        if opened != closed:
            raise SystemExit(f"непарный <{tag}>: {opened} открыт, {closed} закрыт")


def main() -> None:
    p = partners.get(123_456_789, "Иван")
    screens = [("Главное меню", texts.menu(p), keyboards.menu())]
    for key, (card, kb) in keyboards.SCREENS.items():
        screens.append((key, card(p), kb()))

    for title, card, kb in screens:
        check(card)
        print("=" * 46)
        print(f"[{title}]")
        print("=" * 46)
        print(plain(card))
        print("-" * 46)
        for row in kb.inline_keyboard:
            print("  " + "   ".join(f"[ {b.text} ]" for b in row))
        print()


if __name__ == "__main__":
    main()
