"""Сквозная проверка на временной базе — без Telegram и без токенов.

Что проверяется:

1. база заводится, партнёр и бот в неё ложатся, сводка считается;
2. карточки собираются на реальных данных из базы и не роняют разметку;
3. окружение дочернего бота собрано верно и не тащит токен франшизы;
4. движок реально запускается отдельным процессом — с заведомо
   негодным токеном он обязан упасть и оставить внятный след в логе;
5. сводка продаж читается из базы бота того же вида, что делает движок.

    python selfcheck.py

Ничего из настоящих данных скрипт не трогает: DATA_DIR подменяется на
временную папку до импорта config.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

if (sys.stdout.encoding or "").lower().replace("-", "") != "utf8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Подмена окружения обязана случиться до импорта config: он читает всё
# на импорте и создаёт папки.
TMP = Path(tempfile.mkdtemp(prefix="emoji-partners-check-"))
os.environ["DATA_DIR"] = str(TMP)
os.environ["BOT_TOKEN"] = "0:selfcheck"
os.environ["ADMIN_IDS"] = "1"

import config  # noqa: E402
import db  # noqa: E402
import engine_stats  # noqa: E402
import keyboards  # noqa: E402
import preview  # noqa: E402
import supervisor  # noqa: E402
import texts  # noqa: E402

OK = "✅"
NO = "❌"
failed: list[str] = []


def check(ok: bool, title: str, detail: str = "") -> None:
    print(f"{OK if ok else NO} {title}" + (f" — {detail}" if detail else ""))
    if not ok:
        failed.append(title)


def fake_engine_db(path: Path) -> None:
    """База того же вида, что заводит движок: заказы и пользователи."""
    path.parent.mkdir(parents=True, exist_ok=True)
    # Движок, успевший подняться на шаге 4, уже завёл тут свою базу —
    # подменяем её целиком, иначе схема наложится на схему.
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (user_id INTEGER PRIMARY KEY, balance INTEGER);
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER, amount INTEGER, status TEXT, created_at INTEGER
        );
        INSERT INTO users VALUES (1, 0), (2, 40);
        INSERT INTO orders (user_id, amount, status, created_at)
        VALUES (1, 30, 'done', 0), (2, 12, 'paid', 0), (2, 99, 'new', 0);
        """
    )
    conn.commit()
    conn.close()


async def main() -> None:
    print(f"Временная папка: {TMP}\n")

    # 1. База и данные ---------------------------------------------------
    await db.init()
    row = await db.touch(777, "ivan", "Иван")
    check(row is not None and row["uid"] == 777, "партнёр заводится")

    ref = await db.touch(888, "petya", "Петя", ref_by=777)
    await db.touch(888, "petya", "Петя", ref_by=999)  # попытка сменить «родителя»
    ref = await db.partner(888)
    check(ref["ref_by"] == 777, "пригласивший не переписывается чужой ссылкой")

    self_ref = await db.touch(555, None, "Сам", ref_by=555)
    check(self_ref["ref_by"] is None, "ссылка на самого себя не засчитывается")

    bot_id = 424242
    ws = supervisor.workspace(bot_id)
    row_id = await db.add_bot(777, bot_id, "424242:BAD-TOKEN", "test_bot", "T", str(ws))
    await db.save_stats(row_id, orders=2, revenue=42, clients=2)
    sums = await db.totals(777)
    check(
        sums["bots"] == 1 and sums["revenue"] == 42,
        "сводка по ботам партнёра считается",
        f"{dict(sums)}",
    )

    # 2. Карточки на реальных данных -------------------------------------
    item = await db.bot(row_id)
    refs = await db.referrals(777)
    cards = {
        "меню": texts.menu(row, sums, refs),
        "кабинет": texts.account(row, sums, refs),
        "боты": texts.bots_list(row, [item]),
        "карточка бота": texts.bot_card(item),
        "подписка": texts.subscription(row, sums),
        "лояльность": texts.loyalty(row, sums),
        "админка": texts.admin_root(await db.service_totals()),
    }
    bad = []
    for name, card in cards.items():
        try:
            preview.check(card)
        except SystemExit as err:
            bad.append(f"{name}: {err}")
    check(not bad, "разметка карточек парная", "; ".join(bad))
    check(
        len(cards["меню"]) <= 1024,
        "меню влезает в подпись к фото",
        f"{len(cards['меню'])} символов",
    )
    keyboards.bots_list(row, [item])
    keyboards.bot_card(item)
    check(True, "клавиатуры собираются")

    # 3. Окружение дочернего бота ----------------------------------------
    env = supervisor._env(item)
    check(env["BOT_TOKEN"] == item["token"], "дочернему боту уходит его токен")
    check(
        env["BOT_TOKEN"] != config.BOT_TOKEN and "franchise" not in env["DATA_DIR"],
        "токен и база франшизы не протекают в дочерний бот",
    )
    check(
        env["DATA_DIR"] == str(ws / "data"),
        "у бота своя папка данных",
        env["DATA_DIR"],
    )
    check("1" in env["ADMIN_IDS"] and "777" in env["ADMIN_IDS"],
          "админы бота: владелец и сервис", env["ADMIN_IDS"])
    check(env["REQUIRED_CHANNEL"] == "", "чужой канал подписки не навязывается")

    # 4. Запуск движка отдельным процессом --------------------------------
    if not (config.ENGINE_DIR / config.ENGINE_ENTRY).exists():
        check(False, "движок найден", f"нет {config.ENGINE_DIR / config.ENGINE_ENTRY}")
    else:
        ok, note = await supervisor.start(item)
        check(
            not ok and bool(note),
            "негодный токен честно валит запуск",
            note.splitlines()[-1] if note else "",
        )
        fresh = await db.bot(row_id)
        check(fresh["state"] == "error", "состояние записано в базу", fresh["state"])
        check(bool(supervisor.tail(item)), "лог бота пишется в его папку")
        await supervisor.stop(item)

    # 5. Чтение продаж из базы бота ---------------------------------------
    fake_engine_db(ws / "data" / "bot.sqlite3")
    got = await engine_stats.refresh(item)
    check(got == (2, 42, 2), "продажи читаются из базы бота", str(got))

    empty = await db.add_bot(777, 4343, "4343:X", "empty_bot", "E", str(ws / "none"))
    check(
        await engine_stats.refresh(await db.bot(empty)) is None,
        "бот без базы не роняет пересчёт",
    )

    print()
    if failed:
        print(f"{NO} провалено: {len(failed)} — " + "; ".join(failed))
        raise SystemExit(1)
    print(f"{OK} всё сошлось")


if __name__ == "__main__":
    asyncio.run(main())
