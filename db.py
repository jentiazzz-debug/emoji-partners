"""База франшизы: партнёры, их боты, журнал событий.

Одна база на весь сервис, но в ней нет ни одной продажи: продажи живут
в базах дочерних ботов, каждая у своего бота. Сюда попадает только
пересчитанная сводка — сколько заказов и на сколько звёзд. Так у
франшизы нет соблазна лезть в чужие данные глубже, чем нужно для
статистики, а движок остаётся независимым: его можно обновлять и
чинить, не трогая эту базу.

Токены дочерних ботов лежат здесь же и в открытом виде — иначе их
нечем запускать. Файл базы — самое ценное, что есть у сервиса:
держите его в DATA_DIR на постоянном томе и не кладите в репозиторий.
"""

from __future__ import annotations

import time
from typing import Any, Iterable, Mapping, Sequence

import aiosqlite

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS partners (
    uid        INTEGER PRIMARY KEY,
    username   TEXT,
    name       TEXT,
    joined_at  INTEGER NOT NULL,
    ref_by     INTEGER,
    sub_until  INTEGER NOT NULL DEFAULT 0,
    banned     INTEGER NOT NULL DEFAULT 0,
    seen_at    INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_partners_ref ON partners(ref_by);

CREATE TABLE IF NOT EXISTS bots (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    owner      INTEGER NOT NULL,
    bot_id     INTEGER NOT NULL UNIQUE,
    token      TEXT NOT NULL UNIQUE,
    username   TEXT,
    title      TEXT,
    workspace  TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'stopped',
    autostart  INTEGER NOT NULL DEFAULT 1,
    last_error TEXT,
    created_at INTEGER NOT NULL,
    orders     INTEGER NOT NULL DEFAULT 0,
    revenue    INTEGER NOT NULL DEFAULT 0,
    clients    INTEGER NOT NULL DEFAULT 0,
    stats_at   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_bots_owner ON bots(owner);

CREATE TABLE IF NOT EXISTS events (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    uid  INTEGER,
    kind TEXT NOT NULL,
    text TEXT,
    ts   INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def now() -> int:
    return int(time.time())


async def init() -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.executescript(_SCHEMA)
        await conn.commit()


async def _rows(sql: str, args: Sequence[Any] = ()) -> list[dict]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(sql, args) as cur:
            return [dict(row) for row in await cur.fetchall()]


async def _row(sql: str, args: Sequence[Any] = ()) -> dict | None:
    rows = await _rows(sql, args)
    return rows[0] if rows else None


async def _run(sql: str, args: Sequence[Any] = ()) -> int:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute(sql, args)
        await conn.commit()
        return cur.lastrowid or cur.rowcount


# --------------------------------------------------------------------------
# Партнёры
# --------------------------------------------------------------------------


async def partner(uid: int) -> dict | None:
    return await _row("SELECT * FROM partners WHERE uid = ?", (uid,))


async def touch(
    uid: int, username: str | None, name: str, ref_by: int | None = None
) -> dict:
    """Найти партнёра или завести нового.

    Пригласивший записывается только при первом появлении: иначе
    достаточно переоткрыть чужую ссылку, чтобы сменить «родителя» и
    увести реферала у того, кто его привёл.
    """
    row = await partner(uid)
    if row is None:
        if ref_by == uid:
            ref_by = None  # ссылка на самого себя
        await _run(
            "INSERT INTO partners (uid, username, name, joined_at, ref_by, "
            "seen_at) VALUES (?, ?, ?, ?, ?, ?)",
            (uid, username, name, now(), ref_by, now()),
        )
        await log(uid, "join", f"пришёл{' по ссылке' if ref_by else ''}")
        return await partner(uid)  # type: ignore[return-value]

    if row["username"] != username or row["name"] != name:
        await _run(
            "UPDATE partners SET username = ?, name = ?, seen_at = ? WHERE uid = ?",
            (username, name, now(), uid),
        )
    else:
        await _run("UPDATE partners SET seen_at = ? WHERE uid = ?", (now(), uid))
    return await partner(uid)  # type: ignore[return-value]


async def set_sub(uid: int, until: int) -> None:
    await _run("UPDATE partners SET sub_until = ? WHERE uid = ?", (until, uid))


async def set_banned(uid: int, banned: bool) -> None:
    await _run(
        "UPDATE partners SET banned = ? WHERE uid = ?", (1 if banned else 0, uid)
    )


async def referrals(uid: int) -> int:
    row = await _row("SELECT COUNT(*) AS n FROM partners WHERE ref_by = ?", (uid,))
    return int(row["n"]) if row else 0


async def partners_page(
    limit: int = 20, offset: int = 0, query: str = ""
) -> list[dict]:
    """Список партнёров для админки: свежие сверху, с поиском."""
    if query:
        like = f"%{query.lstrip('@').lower()}%"
        return await _rows(
            "SELECT * FROM partners WHERE lower(username) LIKE ? "
            "OR lower(name) LIKE ? OR CAST(uid AS TEXT) LIKE ? "
            "ORDER BY joined_at DESC LIMIT ? OFFSET ?",
            (like, like, like, limit, offset),
        )
    return await _rows(
        "SELECT * FROM partners ORDER BY joined_at DESC LIMIT ? OFFSET ?",
        (limit, offset),
    )


async def all_partner_ids() -> list[int]:
    rows = await _rows("SELECT uid FROM partners WHERE banned = 0")
    return [int(r["uid"]) for r in rows]


# --------------------------------------------------------------------------
# Боты
# --------------------------------------------------------------------------


async def bots_of(uid: int) -> list[dict]:
    return await _rows(
        "SELECT * FROM bots WHERE owner = ? ORDER BY created_at", (uid,)
    )


async def bot(row_id: int) -> dict | None:
    return await _row("SELECT * FROM bots WHERE id = ?", (row_id,))


async def bot_by_tg(bot_id: int) -> dict | None:
    return await _row("SELECT * FROM bots WHERE bot_id = ?", (bot_id,))


async def all_bots(state: str = "") -> list[dict]:
    if state:
        return await _rows("SELECT * FROM bots WHERE state = ? ORDER BY id", (state,))
    return await _rows("SELECT * FROM bots ORDER BY id")


async def add_bot(
    owner: int, bot_id: int, token: str, username: str, title: str, workspace: str
) -> int:
    return await _run(
        "INSERT INTO bots (owner, bot_id, token, username, title, workspace, "
        "created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (owner, bot_id, token, username, title, workspace, now()),
    )


async def drop_bot(row_id: int) -> None:
    await _run("DELETE FROM bots WHERE id = ?", (row_id,))


async def set_state(row_id: int, state: str, error: str | None = None) -> None:
    await _run(
        "UPDATE bots SET state = ?, last_error = ? WHERE id = ?",
        (state, error, row_id),
    )


async def set_autostart(row_id: int, on: bool) -> None:
    await _run(
        "UPDATE bots SET autostart = ? WHERE id = ?", (1 if on else 0, row_id)
    )


async def save_stats(row_id: int, orders: int, revenue: int, clients: int) -> None:
    await _run(
        "UPDATE bots SET orders = ?, revenue = ?, clients = ?, stats_at = ? "
        "WHERE id = ?",
        (orders, revenue, clients, now(), row_id),
    )


async def totals(uid: int) -> dict:
    """Сводка по всем ботам партнёра — то, что видно в кабинете."""
    row = await _row(
        "SELECT COUNT(*) AS bots, "
        "COALESCE(SUM(orders), 0) AS orders, "
        "COALESCE(SUM(revenue), 0) AS revenue, "
        "COALESCE(SUM(clients), 0) AS clients, "
        "COALESCE(SUM(state = 'running'), 0) AS running "
        "FROM bots WHERE owner = ?",
        (uid,),
    )
    return row or {"bots": 0, "orders": 0, "revenue": 0, "clients": 0, "running": 0}


async def service_totals() -> dict:
    """То же самое по всему сервису — для админки."""
    row = await _row(
        "SELECT (SELECT COUNT(*) FROM partners) AS partners, "
        "(SELECT COUNT(*) FROM bots) AS bots, "
        "(SELECT COALESCE(SUM(state = 'running'), 0) FROM bots) AS running, "
        "(SELECT COALESCE(SUM(orders), 0) FROM bots) AS orders, "
        "(SELECT COALESCE(SUM(revenue), 0) FROM bots) AS revenue, "
        "(SELECT COALESCE(SUM(clients), 0) FROM bots) AS clients"
    )
    return row or {}


# --------------------------------------------------------------------------
# Журнал
# --------------------------------------------------------------------------


async def log(uid: int | None, kind: str, text: str = "") -> None:
    """Событие в журнал.

    Журнал — единственный способ потом ответить на «почему бот
    остановился ночью»: состояние в таблице ботов перезаписывается, а
    здесь остаётся история.
    """
    await _run(
        "INSERT INTO events (uid, kind, text, ts) VALUES (?, ?, ?, ?)",
        (uid, kind, text, now()),
    )


async def events(uid: int | None = None, limit: int = 20) -> list[dict]:
    if uid is None:
        return await _rows("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,))
    return await _rows(
        "SELECT * FROM events WHERE uid = ? ORDER BY id DESC LIMIT ?", (uid, limit)
    )


# --------------------------------------------------------------------------
# Настройки сервиса
# --------------------------------------------------------------------------


async def get(key: str, default: str = "") -> str:
    row = await _row("SELECT value FROM settings WHERE key = ?", (key,))
    return row["value"] if row else default


async def put(key: str, value: str) -> None:
    await _run(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
