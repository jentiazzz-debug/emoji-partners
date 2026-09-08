"""Настройки франшизы: токен, движок, уровни, ссылки.

Emoji Partners — надстройка над готовым ботом-конструктором эмодзи
(StickerEmojiBot). Партнёр приносит токен своего бота, франшиза
поднимает для него отдельную копию движка со своей папкой данных и
своим оформлением, а в кабинете показывает, что этот бот наработал.

Здесь лежит только то, что задаётся один раз при установке. Всё
остальное — партнёры, боты, продажи — живёт в SQLite.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

#: Хостинги отдают под данные отдельный том и сообщают о нём в DATA_DIR.
#: Не слушать его нельзя: база и рабочие папки ботов лягут рядом с кодом
#: и сотрутся на первом же передеплое вместе с токенами партнёров.
DATA_DIR = Path(os.getenv("DATA_DIR") or BASE_DIR / "data")
DATA_DIR.mkdir(parents=True, exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
DB_PATH = Path(os.getenv("DB_PATH") or DATA_DIR / "franchise.sqlite3")

#: Имя сервиса. Меняется одной строкой — в текстах оно везде подставное.
BRAND = os.getenv("BRAND", "Emoji Partners")


def _ints(raw: str | None) -> set[int]:
    if not raw:
        return set()
    return {
        int(chunk.strip())
        for chunk in raw.replace(";", ",").split(",")
        if chunk.strip().lstrip("-").isdigit()
    }


#: Кому доступна админка франшизы: партнёры, боты, статистика, рассылка.
ADMIN_IDS = _ints(os.getenv("ADMIN_IDS"))

# --------------------------------------------------------------------------
# Движок дочерних ботов
# --------------------------------------------------------------------------

#: Папка с кодом бота-конструктора. Франшиза его не правит — только
#: запускает копии с другим токеном и другой папкой данных. Поэтому
#: движок можно обновлять отдельно, не трогая франшизу.
ENGINE_DIR = Path(os.getenv("ENGINE_DIR") or BASE_DIR.parent / "StickerEmojiBot")

#: Файл, который запускается для дочернего бота.
ENGINE_ENTRY = os.getenv("ENGINE_ENTRY", "bot.py")

#: Рабочие папки дочерних ботов: у каждого своя база, свои шрифты,
#: свой кэш превью. Общей базы у ботов партнёров быть не должно —
#: это чужие друг другу магазины.
WORKSPACES = Path(os.getenv("WORKSPACES") or DATA_DIR / "workspaces")
WORKSPACES.mkdir(parents=True, exist_ok=True)

#: Сколько ботов разрешено партнёру без подписки.
FREE_BOTS = int(os.getenv("FREE_BOTS", "1"))

#: Сколько ботов разрешено с подпиской. 0 — без ограничений.
SUB_BOTS = int(os.getenv("SUB_BOTS", "0"))

#: Как часто пересчитывать продажи дочерних ботов, секунды.
STATS_INTERVAL = int(os.getenv("STATS_INTERVAL", "300"))

#: Сколько секунд ждать, пока дочерний бот поднимется, прежде чем
#: считать запуск неудачным. Первый старт дольше остальных: движок
#: пересчитывает превью шаблонов.
START_TIMEOUT = int(os.getenv("START_TIMEOUT", "90"))

# --------------------------------------------------------------------------
# Ссылки
# --------------------------------------------------------------------------

SUPPORT = os.getenv("SUPPORT", "@EmojiPartners_support")
DEMO_BOT = os.getenv("DEMO_BOT", "@emojimakerobot")
CHANNEL = os.getenv("CHANNEL", "")
GUIDE_URL = os.getenv("GUIDE_URL", "https://telegra.ph/")


def link(value: str) -> str:
    """@username или ссылка → всегда ссылка: кнопке нужен URL."""
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        return value
    return "https://t.me/" + value.lstrip("@")


SUPPORT_URL = link(SUPPORT)
CHANNEL_URL = link(CHANNEL)

# --------------------------------------------------------------------------
# Оформление меню
# --------------------------------------------------------------------------

MENU_PHOTO = os.getenv("MENU_PHOTO", "").strip()
MENU_PHOTO_FILE = BASE_DIR / "assets" / "menu.png"
CURRENCY = os.getenv("CURRENCY", "⭐️")

# --------------------------------------------------------------------------
# Уровни и подписка
# --------------------------------------------------------------------------

#: Лестница уровней: (название, значок, комиссия %, продано эмодзи от).
#: Уровень считается от оборота бота партнёра в звёздах — единственной
#: цифры, которую движок считает сам и подделать которую партнёр не
#: может: она берётся из базы его бота, а не с его слов.
LEVELS: tuple[tuple[str, str, float, int], ...] = (
    ("Newbie", "🥉", 15.0, 0),
    ("Maker", "🥈", 12.0, 2_000),
    ("Pro", "🥇", 10.0, 10_000),
    ("Studio", "💎", 8.0, 50_000),
    ("Legend", "👑", 5.0, 250_000),
)

#: На сколько процентов подписка снижает комиссию уровня.
SUB_DISCOUNT = float(os.getenv("SUB_DISCOUNT", "2"))

#: Тарифы подписки: (подпись, цена, приписка). Витрина — приём оплаты
#: подключается вместе с денежной частью.
SUB_PLANS: tuple[tuple[str, str, str], ...] = (
    ("1 месяц", "699", ""),
    ("3 месяца", "1 790", "выгода 15%"),
    ("12 месяцев", "5 490", "выгода 35%"),
)


def check() -> None:
    """Ранние проверки: без них бот падает позже и непонятнее."""
    if not BOT_TOKEN:
        raise SystemExit(
            "Не задан BOT_TOKEN. Скопируй .env.example в .env и впиши токен "
            "от @BotFather."
        )
    entry = ENGINE_DIR / ENGINE_ENTRY
    if not entry.exists():
        raise SystemExit(
            f"Не найден движок дочерних ботов: {entry}\n"
            "Укажи путь к папке бота-конструктора в ENGINE_DIR."
        )
