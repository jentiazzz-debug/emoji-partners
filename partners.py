"""Уровни, подписка и лимиты — правила, а не данные.

Уровень нигде не хранится: он считается от оборота ботов партнёра.
Одно число — один источник правды, и уровень невозможно рассинхронить
с продажами ручной правкой базы.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Mapping

import config


@dataclass(frozen=True)
class Level:
    """Ступень: название, значок, комиссия сервиса и порог оборота."""

    name: str
    icon: str
    fee: float
    need: int


LEVELS: tuple[Level, ...] = tuple(Level(*item) for item in config.LEVELS)


def level_of(revenue: int) -> Level:
    current = LEVELS[0]
    for lvl in LEVELS:
        if revenue >= lvl.need:
            current = lvl
    return current


def next_of(revenue: int) -> Level | None:
    for lvl in LEVELS:
        if lvl.need > revenue:
            return lvl
    return None


def left(revenue: int) -> int:
    nxt = next_of(revenue)
    return max(0, nxt.need - revenue) if nxt else 0


def progress(revenue: int) -> float:
    """Доля пути до следующей ступени, 0..1.

    Считается от начала текущей ступени, а не от нуля: иначе на
    старших уровнях полоса всегда была бы почти полной.
    """
    nxt = next_of(revenue)
    if not nxt:
        return 1.0
    base = level_of(revenue).need
    span = nxt.need - base
    return min(1.0, max(0.0, (revenue - base) / span)) if span else 1.0


def fee_of(row: Mapping, revenue: int) -> float:
    """Комиссия партнёра: уровень минус скидка за подписку."""
    fee = level_of(revenue).fee
    if has_sub(row):
        fee = max(0.0, fee - config.SUB_DISCOUNT)
    return fee


def has_sub(row: Mapping) -> bool:
    return int(row.get("sub_until") or 0) > int(time.time())


def bot_limit(row: Mapping) -> int:
    """Сколько ботов разрешено партнёру. 0 — без ограничений."""
    return config.SUB_BOTS if has_sub(row) else config.FREE_BOTS


def can_add_bot(row: Mapping, have: int) -> bool:
    limit = bot_limit(row)
    return limit == 0 or have < limit
