"""Настройки бота. Всё, что зависит от окружения, читается из .env."""

from __future__ import annotations

import os
from typing import Dict, List, Set

from dotenv import load_dotenv

#: Версия сборки. Печатается в лог при старте и видна в админ-панели —
#: по ней сразу понятно, обновился хостинг или крутит старый код.
VERSION = "2.2.0"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

load_dotenv(os.path.join(BASE_DIR, ".env"))

# --------------------------------------------------------------------------
# Токен и контакты
# --------------------------------------------------------------------------

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "").strip()

#: Куда ведёт кнопка «Поддержка». Можно указать @username или ссылку.
SUPPORT_CONTACT: str = os.getenv("SUPPORT_CONTACT", "@support").strip()

#: Необязательный канал/чат проекта — показывается в разделе поддержки.
SUPPORT_CHAT: str = os.getenv("SUPPORT_CHAT", "").strip()


def _support_url(value: str) -> str:
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        return value
    return "https://t.me/" + value.lstrip("@")


SUPPORT_URL: str = _support_url(SUPPORT_CONTACT)
SUPPORT_CHAT_URL: str = _support_url(SUPPORT_CHAT)

#: Канал обязательной подписки на первый запуск. Дальше список каналов
#: живёт в базе и правится в админке — это значение переносится туда
#: один раз, чтобы старые установки не потеряли настройку.
REQUIRED_CHANNEL: str = os.getenv("REQUIRED_CHANNEL", "@emojieditor_news").strip()

ADMIN_IDS: Set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(";", ",").split(",") if x.strip().isdigit()
}

REQUIRED_CHANNEL_URL: str = _support_url(REQUIRED_CHANNEL)

# --------------------------------------------------------------------------
# Пути
# --------------------------------------------------------------------------

TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
FONTS_DIR = os.path.join(BASE_DIR, "fonts")

#: Где хранить всё, что бот создаёт сам. Хостинги (Bothost, Railway и
#: подобные) отдают под постоянный том отдельную папку и сообщают её в
#: DATA_DIR — иначе база и загруженные шрифты жили бы внутри контейнера
#: и исчезали при каждом передеплое.
DATA_DIR = os.getenv("DATA_DIR", "").strip() or os.path.join(BASE_DIR, "data")

USER_FONTS_DIR = os.path.join(DATA_DIR, "user_fonts")
DB_PATH = os.path.join(DATA_DIR, "bot.sqlite3")

#: Кэш превью тоже кладём в постоянную папку: пересчитать его для 250
#: шаблонов — это полминуты работы на старте, и повторять их при каждом
#: рестарте незачем.
PREVIEWS_DIR = os.path.join(DATA_DIR, "previews")

for _path in (DATA_DIR, PREVIEWS_DIR, USER_FONTS_DIR):
    os.makedirs(_path, exist_ok=True)

# --------------------------------------------------------------------------
# Наборы шаблонов
# --------------------------------------------------------------------------

#: Наборы, которые видит пользователь. Пока он один, но экран выбора
#: набора отдельный — второй пак добавляется одной строкой здесь.
PACKS: Dict[str, Dict[str, object]] = {
    "main": {
        "title": "Основной",
        "emoji": "📦",
        "range": (1, 250),
    },
}

#: Сколько шаблонов встроено в бота (файлы templates/001.tgs … 250.tgs).
TEMPLATE_COUNT = 250

#: Сколько шаблонов показываем на одной странице ручного выбора.
PAGE_SIZE = 12

#: Максимальная длина надписи внутри эмодзи.
MAX_TEXT_LENGTH = 20

#: Ограничения на пользовательский SVG-логотип.
MAX_LOGO_BYTES = 256 * 1024

#: Ограничения на пользовательский шрифт.
MAX_FONT_BYTES = 5 * 1024 * 1024
FONT_EXTENSIONS = (".ttf", ".otf")

# --------------------------------------------------------------------------
# Оформление
# --------------------------------------------------------------------------

#: Встроенные шрифты: id → (подпись на кнопке, файл в fonts/).
FONTS: Dict[str, tuple] = {
    "evolve": ("Evolve Sans", "evolve.otf"),
    "stolzl": ("Stolzl", "stolzl.otf"),
    "unisans": ("Uni Sans", "unisans.otf"),
    "gotham": ("Gotham", "gotham.otf"),
    "proxima": ("Proxima Nova", "proxima.ttf"),
    "junegull": ("Junegull", "junegull.ttf"),
}

DEFAULT_FONT = "stolzl"

#: Эмодзи, которое присваивается каждому созданному кастом-эмодзи.
DEFAULT_EMOJI = "✨"

#: Название набора, который бот создаёт пользователю.
PACK_TITLE_SUFFIX = os.getenv("PACK_TITLE", "emoji pack").strip()

# --------------------------------------------------------------------------
# Случайный подбор и оплата
# --------------------------------------------------------------------------

#: Варианты количества на кнопках. Своё число тоже можно прислать текстом.
QUANTITY_PRESETS: List[int] = [5, 10, 15, 20, 30, 50]

#: Минимум и максимум эмодзи в одном заказе.
#:
#: Telegram пропускает 8 стикеров за 4 минуты — считая сами стикеры, а
#: не запросы. Поэтому цена любого заказа во времени линейна: 8 штук —
#: минута, 50 — около получаса. Потолок в 50 держим как разумный
#: максимум ожидания; кому нужно больше, делает второй заказ.
MIN_ORDER = 1
MAX_ORDER = 50

#: Цена в звёздах Telegram за одно эмодзи.
PRICE_PER_EMOJI = int(os.getenv("PRICE_PER_EMOJI", "1"))

#: Валюта Telegram Stars.
CURRENCY = "XTR"

#: Максимум эмодзи в одном наборе Telegram.
PACK_LIMIT = 200

#: Сколько стикеров уходит в createNewStickerSet первым вызовом.
#:
#: Telegram считает лимит «8 за 4 минуты» по стикерам, а не по запросам,
#: поэтому пачка больше восьми упирается во флуд-контроль сразу и
#: навсегда. Если Telegram ослабит правило, поднимайте это число: API
#: сам по себе принимает до 50 штук за вызов.
CREATE_BATCH = 8

#: Что собираем: премиум-эмодзи или обычный стикерпак. Значения — то,
#: что уходит в sticker_type у createNewStickerSet, и префикс ссылки.
KINDS = {
    "emoji": {
        "title": "Премиум-эмодзи",
        "short": "эмодзи",
        "icon": "💎",
        "sticker_type": "custom_emoji",
        "link": "addemoji",
        "note": "вставляются в текст, нужен Telegram Premium",
    },
    "sticker": {
        "title": "Обычные стикеры",
        "short": "стикеры",
        "icon": "🖼",
        "sticker_type": "regular",
        "link": "addstickers",
        "note": "работают у всех, без Premium",
    },
}

DEFAULT_KIND = "emoji"


def pack_url(kind: str, name: str) -> str:
    """Ссылка на набор. У эмодзи и стикеров разные точки входа."""
    prefix = KINDS.get(kind, KINDS[DEFAULT_KIND])["link"]
    return f"https://t.me/{prefix}/{name}"


#: Суммы пополнения баланса на кнопках, в звёздах.
TOPUP_PRESETS = [50, 100, 250, 500, 1000]

#: Границы разового пополнения — верхняя совпадает с лимитом Telegram.
MIN_TOPUP, MAX_TOPUP = 1, 2500

# --------------------------------------------------------------------------
# Оплата криптой (Crypto Pay: @CryptoBot и @send)
# --------------------------------------------------------------------------

#: Токен приложения из @CryptoBot → Crypto Pay → Create App.
#: Пустой токен просто выключает способ оплаты, бот работает как раньше.
CRYPTO_TOKEN: str = os.getenv("CRYPTO_TOKEN", "").strip()

#: Адрес API. Для тестовой сети — https://testnet-pay.crypt.bot/api
CRYPTO_API: str = os.getenv("CRYPTO_API", "https://pay.crypt.bot/api").strip()

#: В какой монете выставляем счета.
CRYPTO_ASSET: str = os.getenv("CRYPTO_ASSET", "USDT").strip()

#: Сколько монеты стоит одна звезда. По умолчанию 1 USDT = 100 звёзд.
CRYPTO_RATE: float = float(os.getenv("CRYPTO_RATE", "0.01"))

#: Сколько секунд живёт неоплаченный счёт.
CRYPTO_INVOICE_TTL: int = int(os.getenv("CRYPTO_INVOICE_TTL", "1800"))

#: Как часто опрашиваем неоплаченные счета.
CRYPTO_POLL_TICK: float = 15.0

FONT_IDS: List[str] = list(FONTS.keys())
