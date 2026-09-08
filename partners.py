"""Партнёр и лестница уровней.

Здесь только витрина меню: уровни, комиссия и то, что показывается в
карточке. Данные лежат в памяти и при перезапуске обнуляются — это
заглушка под настоящую базу. Меняя её на свою, оставьте сигнатуру
get(): всё остальное ходит за данными только через неё.

Уровень не хранится в записи партнёра, а считается от суммы заработка:
одно число — один источник правды, и уровень невозможно рассинхронить
с деньгами при ручной правке.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Level:
    """Ступень лестницы: с какого заработка и под какую комиссию."""

    name: str
    icon: str
    fee: float  # комиссия сервиса, %
    need: float  # заработок, с которого ступень открыта


#: Лестница снизу вверх. Первая ступень обязана начинаться с нуля —
#: с неё стартует любой новый партнёр.
LEVELS: tuple[Level, ...] = (
    Level("Newbie", "🥉", 8.0, 0),
    Level("Rising Star", "🥈", 7.0, 5_000),
    Level("Star", "🥇", 6.0, 25_000),
    Level("Super Star", "💎", 5.0, 100_000),
    Level("Legend", "👑", 4.0, 500_000),
)


@dataclass
class Partner:
    """Запись партнёра в том объёме, в каком её показывает меню."""

    uid: int
    name: str = "партнёр"
    earned: float = 0.0  # заработано всего — от него считается уровень
    balance: float = 0.0  # доступно к выводу
    bots: int = 0
    refs: int = 0
    sub_until: str = ""  # пусто — подписки нет
    extra: dict = field(default_factory=dict)

    # ---- уровень ---------------------------------------------------

    @property
    def level(self) -> Level:
        current = LEVELS[0]
        for lvl in LEVELS:
            if self.earned >= lvl.need:
                current = lvl
        return current

    @property
    def next_level(self) -> Level | None:
        """Следующая ступень или None, если партнёр на вершине."""
        for lvl in LEVELS:
            if lvl.need > self.earned:
                return lvl
        return None

    @property
    def left(self) -> float:
        """Сколько осталось заработать до следующей ступени."""
        nxt = self.next_level
        return max(0.0, nxt.need - self.earned) if nxt else 0.0

    @property
    def progress(self) -> float:
        """Доля пути до следующей ступени, 0..1.

        Считается от начала текущей ступени, а не от нуля: иначе на
        старших уровнях полоса всегда была бы почти полной.
        """
        nxt = self.next_level
        if not nxt:
            return 1.0
        base = self.level.need
        span = nxt.need - base
        return min(1.0, max(0.0, (self.earned - base) / span)) if span else 1.0


_people: dict[int, Partner] = {}

#: Демо-данные для первого запуска: ровно те цифры, что видно на
#: скриншоте исходного бота, чтобы карточку было на чём посмотреть.
DEMO = dict(earned=4_032.53, balance=1_240.00, bots=2, refs=7)


def get(uid: int, name: str = "партнёр") -> Partner:
    """Партнёр по id. Незнакомого заводит на лету."""
    p = _people.get(uid)
    if p is None:
        p = Partner(uid=uid, name=name, **DEMO)
        _people[uid] = p
    elif name and name != p.name:
        p.name = name  # человек сменил имя в Telegram
    return p
