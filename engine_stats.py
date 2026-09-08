"""Сводка продаж из баз дочерних ботов.

Франшиза читает базы ботов **только на чтение** и только четыре числа:
сколько заказов оплачено, на сколько звёзд, сколько людей пришло. Ни
надписей клиентов, ни их логотипов, ни переписки здесь не появляется —
это чужие данные, они нужны боту, а не сервису.

Оборот считается по заказам, а не по платежам: движок журналирует
заказ с ценой и статусом, а пополнения баланса отдельной таблицей не
пишет. По заказам цифра честнее — она не задваивает «пополнил на 500,
потратил 300». Когда дойдём до денежной части, в движок стоит добавить
таблицу платежей: без неё не отличить оплату звёздами от списания с
баланса, а комиссию считать нужно именно с первого.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from pathlib import Path

import config
import db
import supervisor

log = logging.getLogger("partners.stats")

#: Статусы оплаченных заказов в движке: 'paid' — деньги приняты,
#: 'done' — набор уже собран и отдан.
PAID = ("paid", "done")


def _read(path: Path) -> tuple[int, int, int] | None:
    """(заказы, звёзды, клиенты) из базы бота. None — базы ещё нет."""
    if not path.exists():
        return None
    try:
        # mode=ro: бот в этот момент работает и пишет в свою базу.
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=5)
    except sqlite3.Error:
        return None
    try:
        marks = ",".join("?" * len(PAID))
        row = conn.execute(
            f"SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM orders "
            f"WHERE status IN ({marks})",
            PAID,
        ).fetchone()
        clients = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        return int(row[0]), int(row[1]), int(clients)
    except sqlite3.Error as err:
        # Заблокированная или ещё не созданная база — не повод шуметь:
        # пересчёт повторится через STATS_INTERVAL.
        log.debug("база %s недоступна: %s", path, err)
        return None
    finally:
        conn.close()


async def refresh(row: dict) -> tuple[int, int, int] | None:
    """Пересчитать сводку одного бота и сохранить её во франшизе."""
    path = supervisor.workspace(int(row["bot_id"])) / "data" / "bot.sqlite3"
    stats = await asyncio.to_thread(_read, path)
    if stats is None:
        return None
    orders, revenue, clients = stats
    await db.save_stats(int(row["id"]), orders, revenue, clients)
    return stats


async def refresh_all() -> int:
    rows = await db.all_bots()
    done = 0
    for row in rows:
        if await refresh(row) is not None:
            done += 1
    return done


async def worker() -> None:
    """Фоновый пересчёт. Ошибки не должны ронять задачу."""
    while True:
        try:
            done = await refresh_all()
            log.debug("сводка обновлена по %s ботам", done)
        except Exception as err:  # noqa: BLE001 — фоновой задаче нельзя падать
            log.warning("пересчёт сводки не удался: %s", err)
        await asyncio.sleep(config.STATS_INTERVAL)
