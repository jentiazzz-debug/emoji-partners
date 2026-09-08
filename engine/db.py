"""Хранилище бота. SQLite через aiosqlite — без внешних сервисов.

В базе лежит то, что должно пережить перезапуск: профили, наборы и
заказы. Заказ сохраняется до выставления счёта — иначе оплата, дошедшая
после рестарта, не нашла бы, что именно человек купил.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

import aiosqlite

import config

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id       INTEGER PRIMARY KEY,
    username      TEXT,
    first_name    TEXT,
    created_at    INTEGER NOT NULL,
    last_seen_at  INTEGER NOT NULL,
    emoji_created INTEGER NOT NULL DEFAULT 0,
    stars_spent   INTEGER NOT NULL DEFAULT 0,
    balance       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS packs (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    name       TEXT NOT NULL UNIQUE,
    title      TEXT NOT NULL,
    count      INTEGER NOT NULL DEFAULT 0,
    kind       TEXT NOT NULL DEFAULT 'emoji',
    created_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_packs_user ON packs(user_id);

CREATE TABLE IF NOT EXISTS orders (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL,
    pack_id    TEXT NOT NULL,
    font_id    TEXT NOT NULL,
    font_path  TEXT,
    text       TEXT NOT NULL DEFAULT '',
    logo       BLOB,
    numbers    TEXT NOT NULL,
    amount     INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'new',
    charge_id   TEXT,
    target_pack TEXT,
    paid_from   TEXT,
    created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS crypto_invoices (
    invoice_id INTEGER PRIMARY KEY,
    user_id    INTEGER NOT NULL,
    chat_id    INTEGER NOT NULL,
    stars      INTEGER NOT NULL,
    amount     REAL NOT NULL,
    asset      TEXT NOT NULL,
    status     TEXT NOT NULL DEFAULT 'active',
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS blocked (
    user_id    INTEGER PRIMARY KEY,
    reason     TEXT,
    created_at INTEGER NOT NULL
);
"""


#: Колонки, добавленные после первого релиза. CREATE TABLE IF NOT EXISTS
#: их в уже созданную базу не принесёт, поэтому досыпаем вручную.
_MIGRATIONS = (
    ("users", "balance", "INTEGER NOT NULL DEFAULT 0"),
    ("packs", "kind", "TEXT NOT NULL DEFAULT 'emoji'"),
    ("orders", "kind", "TEXT NOT NULL DEFAULT 'emoji'"),
    ("orders", "target_pack", "TEXT"),
    ("orders", "paid_from", "TEXT"),
    # Очередь выдачи: чтобы оплаченный заказ пережил перезапуск бота.
    ("orders", "chat_id", "INTEGER"),
    ("orders", "attempts", "INTEGER NOT NULL DEFAULT 0"),
    ("orders", "next_try_at", "INTEGER NOT NULL DEFAULT 0"),
    ("orders", "paid_at", "INTEGER NOT NULL DEFAULT 0"),
)


async def init() -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.executescript(_SCHEMA)
        for table, column, decl in _MIGRATIONS:
            async with conn.execute(f"PRAGMA table_info({table})") as cur:
                columns = {row[1] for row in await cur.fetchall()}
            if column not in columns:
                await conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
        await conn.commit()


# --------------------------------------------------------------------------
# Пользователи
# --------------------------------------------------------------------------

async def ensure_user(user_id: int, username: Optional[str], first_name: Optional[str]) -> None:
    """Заводит профиль при первом /start и обновляет ник при каждом входе.

    Ник в Telegram меняется, а в профиле он показывается — иначе бот
    рисовал бы устаревшее имя месяцами.
    """
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            """
            INSERT INTO users (user_id, username, first_name, created_at, last_seen_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                last_seen_at = excluded.last_seen_at
            """,
            (user_id, username, first_name, now, now),
        )
        await conn.commit()


async def get_user(user_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def add_emoji_counter(user_id: int, count: int, stars: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET emoji_created = emoji_created + ?, stars_spent = stars_spent + ? "
            "WHERE user_id = ?",
            (count, stars, user_id),
        )
        await conn.commit()


# --------------------------------------------------------------------------
# Наборы
# --------------------------------------------------------------------------

async def add_pack(user_id: int, name: str, title: str, kind: str = "emoji") -> None:
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO packs (user_id, name, title, count, kind, created_at) "
            "VALUES (?, ?, ?, 0, ?, ?)",
            (user_id, name, title, kind, now),
        )
        await conn.commit()


async def bump_pack(name: str, count: int = 1) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("UPDATE packs SET count = count + ? WHERE name = ?", (count, name))
        await conn.commit()


async def get_packs(user_id: int) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM packs WHERE user_id = ? ORDER BY id",
            (user_id,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_last_pack(user_id: int) -> Optional[Dict[str, Any]]:
    """Последний набор пользователя — в него доклеиваются новые эмодзи."""
    packs = await get_packs(user_id)
    return packs[-1] if packs else None


# --------------------------------------------------------------------------
# Заказы
# --------------------------------------------------------------------------

async def create_order(
    user_id: int,
    pack_id: str,
    font_id: str,
    font_path: Optional[str],
    text: str,
    logo: Optional[bytes],
    numbers: List[int],
    amount: int,
    kind: str = "emoji",
) -> int:
    """Сохраняет заказ перед счётом и возвращает его id.

    Id уходит в payload счёта: по нему оплата находит свой заказ даже
    после перезапуска бота, когда FSM-сессия уже потеряна.
    """
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute(
            """
            INSERT INTO orders (user_id, pack_id, font_id, font_path, text, logo,
                                numbers, amount, kind, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?)
            """,
            (
                user_id, pack_id, font_id, font_path, text, logo,
                ",".join(str(n) for n in numbers), amount, kind, now,
            ),
        )
        await conn.commit()
        return int(cur.lastrowid)


async def get_order(order_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)) as cur:
            row = await cur.fetchone()
    if not row:
        return None
    order = dict(row)
    order["numbers"] = [int(x) for x in order["numbers"].split(",") if x]
    return order


async def set_order_status(order_id: int, status: str, charge_id: Optional[str] = None) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET status = ?, charge_id = COALESCE(?, charge_id) WHERE id = ?",
            (status, charge_id, order_id),
        )
        await conn.commit()


async def last_paid_order(user_id: int) -> Optional[Dict[str, Any]]:
    """Последняя оплата пользователя — по ней админ делает возврат."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM orders WHERE user_id = ? AND charge_id IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def stats() -> Dict[str, int]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(emoji_created), 0), COALESCE(SUM(stars_spent), 0) FROM users"
        ) as cur:
            users, emoji, stars = await cur.fetchone()
        async with conn.execute("SELECT COUNT(*) FROM packs") as cur:
            (packs,) = await cur.fetchone()
        async with conn.execute("SELECT COUNT(*) FROM orders WHERE status = 'done'") as cur:
            (orders,) = await cur.fetchone()
    return {
        "users": int(users),
        "emoji": int(emoji),
        "stars": int(stars),
        "packs": int(packs),
        "orders": int(orders),
    }


# --------------------------------------------------------------------------
# Настройки, меняемые из админки
# --------------------------------------------------------------------------

async def get_settings() -> Dict[str, str]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute("SELECT key, value FROM settings") as cur:
            rows = await cur.fetchall()
    return {str(k): str(v) for k, v in rows}


async def set_setting(key: str, value: str) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await conn.commit()


# --------------------------------------------------------------------------
# Блокировки
# --------------------------------------------------------------------------

async def block_user(user_id: int, reason: str = "") -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO blocked (user_id, reason, created_at) VALUES (?, ?, ?)",
            (user_id, reason, int(time.time())),
        )
        await conn.commit()


async def unblock_user(user_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute("DELETE FROM blocked WHERE user_id = ?", (user_id,))
        await conn.commit()


async def is_blocked(user_id: int) -> bool:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute("SELECT 1 FROM blocked WHERE user_id = ?", (user_id,)) as cur:
            return await cur.fetchone() is not None


async def blocked_ids() -> List[int]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute("SELECT user_id FROM blocked") as cur:
            return [int(r[0]) for r in await cur.fetchall()]


# --------------------------------------------------------------------------
# Выборки для админки
# --------------------------------------------------------------------------

async def list_users(limit: int, offset: int) -> List[Dict[str, Any]]:
    """Пользователи от новых к старым — так админ видит свежий приток."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM users ORDER BY created_at DESC, user_id DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def count_users() -> int:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute("SELECT COUNT(*) FROM users") as cur:
            (count,) = await cur.fetchone()
    return int(count)


async def find_users(query: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Поиск по id или части ника — то, чем пользуются в поддержке."""
    query = query.strip().lstrip("@")
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        if query.isdigit():
            sql = "SELECT * FROM users WHERE user_id = ? LIMIT ?"
            args: tuple = (int(query), limit)
        else:
            sql = ("SELECT * FROM users WHERE username LIKE ? OR first_name LIKE ? "
                   "ORDER BY created_at DESC LIMIT ?")
            args = (f"%{query}%", f"%{query}%", limit)
        async with conn.execute(sql, args) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def list_orders(limit: int, offset: int, status: Optional[str] = None) -> List[Dict[str, Any]]:
    where = "WHERE status = ?" if status else ""
    args: tuple = (status, limit, offset) if status else (limit, offset)
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            f"SELECT id, user_id, font_id, text, numbers, amount, status, charge_id, created_at "
            f"FROM orders {where} ORDER BY id DESC LIMIT ? OFFSET ?",
            args,
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for row in rows:
        order = dict(row)
        order["numbers"] = [int(x) for x in order["numbers"].split(",") if x]
        result.append(order)
    return result


async def count_orders(status: Optional[str] = None) -> int:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        if status:
            sql, args = "SELECT COUNT(*) FROM orders WHERE status = ?", (status,)
        else:
            sql, args = "SELECT COUNT(*) FROM orders", ()
        async with conn.execute(sql, args) as cur:
            (count,) = await cur.fetchone()
    return int(count)


async def orders_of_user(user_id: int, limit: int = 10) -> List[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT id, amount, status, charge_id, numbers, created_at FROM orders "
            "WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for row in rows:
        order = dict(row)
        order["numbers"] = [int(x) for x in order["numbers"].split(",") if x]
        result.append(order)
    return result


async def period_stats(since: int) -> Dict[str, int]:
    """Срез за период: новые люди, оплаченные заказы и звёзды с них."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute(
            "SELECT COUNT(*) FROM users WHERE created_at >= ?", (since,),
        ) as cur:
            (users,) = await cur.fetchone()
        async with conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM orders "
            "WHERE status = 'done' AND created_at >= ?",
            (since,),
        ) as cur:
            orders, stars = await cur.fetchone()
    return {"users": int(users), "orders": int(orders), "stars": int(stars)}


async def all_user_ids() -> List[int]:
    """Адресаты рассылки: все, кроме заблокированных."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        async with conn.execute(
            "SELECT user_id FROM users WHERE user_id NOT IN (SELECT user_id FROM blocked)"
        ) as cur:
            return [int(r[0]) for r in await cur.fetchall()]


# --------------------------------------------------------------------------
# Баланс
# --------------------------------------------------------------------------

async def add_balance(user_id: int, amount: int) -> int:
    """Меняет баланс и возвращает новое значение.

    Сумма может быть отрицательной — админ снимает выданное по ошибке.
    В минус баланс при этом не уходит: MAX(0, …) считается в самом SQL,
    иначе между чтением и записью успел бы влезть заказ.
    """
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE users SET balance = MAX(0, balance + ?) WHERE user_id = ?",
            (amount, user_id),
        )
        await conn.commit()
        async with conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cur:
            row = await cur.fetchone()
    return int(row[0]) if row else 0


async def spend_balance(user_id: int, amount: int) -> bool:
    """Списывает с баланса, если хватает. False — денег не хватило.

    Проверка и списание идут одним UPDATE с условием: между отдельными
    SELECT и UPDATE пользователь успел бы нажать «оплатить» дважды и
    увести баланс в минус.
    """
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
            (amount, user_id, amount),
        )
        await conn.commit()
        return cur.rowcount > 0


async def get_balance(user_id: int) -> int:
    user = await get_user(user_id)
    return int(user.get("balance", 0)) if user else 0


# --------------------------------------------------------------------------
# Куда складывать эмодзи
# --------------------------------------------------------------------------

async def set_order_target(order_id: int, target_pack: Optional[str]) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET target_pack = ? WHERE id = ?", (target_pack, order_id),
        )
        await conn.commit()


async def mark_order_paid(order_id: int, source: str, charge_id: Optional[str] = None) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET status = 'paid', paid_from = ?, "
            "charge_id = COALESCE(?, charge_id) WHERE id = ?",
            (source, charge_id, order_id),
        )
        await conn.commit()


async def packs_with_room(user_id: int, limit: int, kind: str) -> List[Dict[str, Any]]:
    """Наборы нужного типа, куда ещё влезет ``limit`` штук.

    Тип обязателен: дописать эмодзи в стикерпак Telegram не даёт, и такой
    набор в списке был бы кнопкой, ведущей в ошибку.
    """
    packs = await get_packs(user_id)
    return [
        p for p in packs
        if p.get("kind", "emoji") == kind and int(p["count"]) + limit <= config.PACK_LIMIT
    ]


async def get_pack(name: str) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT * FROM packs WHERE name = ?", (name,)) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------
# Очередь выдачи
# --------------------------------------------------------------------------

async def mark_paid_for_delivery(order_id: int, source: str, chat_id: int,
                                 charge_id: Optional[str] = None) -> None:
    """Ставит заказ в очередь выдачи.

    chat_id запоминаем здесь: выдача может случиться через час и после
    перезапуска бота, когда исходного сообщения уже нет, а написать
    человеку всё равно нужно.
    """
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET status = 'paid', paid_from = ?, chat_id = ?, "
            "paid_at = ?, next_try_at = 0, attempts = 0, "
            "charge_id = COALESCE(?, charge_id) WHERE id = ?",
            (source, chat_id, now, charge_id, order_id),
        )
        await conn.commit()


async def due_orders(limit: int = 5) -> List[Dict[str, Any]]:
    """Оплаченные заказы, которым пора попробовать выдаться."""
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM orders WHERE status = 'paid' AND next_try_at <= ? "
            "ORDER BY paid_at, id LIMIT ?",
            (now, limit),
        ) as cur:
            rows = await cur.fetchall()
    result = []
    for row in rows:
        order = dict(row)
        order["numbers"] = [int(x) for x in order["numbers"].split(",") if x]
        result.append(order)
    return result


async def postpone_order(order_id: int, seconds: int) -> None:
    """Откладывает следующую попытку выдачи и считает их количество."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET next_try_at = ?, attempts = attempts + 1 WHERE id = ?",
            (int(time.time()) + max(0, seconds), order_id),
        )
        await conn.commit()


async def retry_order_now(order_id: int) -> None:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "UPDATE orders SET next_try_at = 0 WHERE id = ? AND status = 'paid'",
            (order_id,),
        )
        await conn.commit()


async def pending_orders(limit: int = 20) -> List[Dict[str, Any]]:
    """Всё, что оплачено и ещё не выдано — для админ-панели."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT id, user_id, amount, attempts, next_try_at, paid_at, numbers "
            "FROM orders WHERE status = 'paid' ORDER BY paid_at LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


# --------------------------------------------------------------------------
# Счета на пополнение криптой
# --------------------------------------------------------------------------

async def add_invoice(invoice_id: int, user_id: int, chat_id: int,
                      stars: int, amount: float, asset: str) -> None:
    now = int(time.time())
    async with aiosqlite.connect(config.DB_PATH) as conn:
        await conn.execute(
            "INSERT OR REPLACE INTO crypto_invoices "
            "(invoice_id, user_id, chat_id, stars, amount, asset, status, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 'active', ?)",
            (invoice_id, user_id, chat_id, stars, amount, asset, now),
        )
        await conn.commit()


async def open_invoices(limit: int = 50) -> List[Dict[str, Any]]:
    """Счета, по которым ещё ждём оплату."""
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM crypto_invoices WHERE status = 'active' "
            "ORDER BY created_at LIMIT ?",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_invoice(invoice_id: int) -> Optional[Dict[str, Any]]:
    async with aiosqlite.connect(config.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute(
            "SELECT * FROM crypto_invoices WHERE invoice_id = ?", (invoice_id,),
        ) as cur:
            row = await cur.fetchone()
    return dict(row) if row else None


async def close_invoice(invoice_id: int, status: str) -> bool:
    """Закрывает счёт. False — его уже закрыли раньше.

    Проверка «был активен» тут не для красоты: опрос и кнопка «я
    оплатил» могут сойтись на одном счёте, и без неё звёзды начислились
    бы дважды.
    """
    async with aiosqlite.connect(config.DB_PATH) as conn:
        cur = await conn.execute(
            "UPDATE crypto_invoices SET status = ? WHERE invoice_id = ? AND status = 'active'",
            (status, invoice_id),
        )
        await conn.commit()
        return cur.rowcount > 0
