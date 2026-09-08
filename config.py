"""Настройки меню: токен, ссылки в шапке, картинка-баннер.

Всё, что в меню упоминается текстом — юзернеймы поддержки, ссылка на
инструкцию, пример бота — вынесено сюда: эти строчки меняются чаще
всего, и лазить за ними в разметку карточки не нужно.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()

#: Имя сервиса в шапке меню.
BRAND = os.getenv("BRAND", "STARS PARTNERS")

# --------------------------------------------------------------------------
# Ссылки в карточке меню
# --------------------------------------------------------------------------

DEMO_BOT = os.getenv("DEMO_BOT", "@HStars_Robot")
SUPPORT = os.getenv("SUPPORT", "@StarsPartners_support")
VPN_BOT = os.getenv("VPN_BOT", "@VPNPartners_Robot")
GUIDE_URL = os.getenv("GUIDE_URL", "https://telegra.ph/")

#: Ссылка на поддержку для кнопки. Юзернейм из SUPPORT сам по себе
#: кнопкой быть не может — Telegram нужен полный URL.
SUPPORT_URL = os.getenv("SUPPORT_URL", "").strip() or (
    "https://t.me/" + SUPPORT.lstrip("@")
)

# --------------------------------------------------------------------------
# Баннер
# --------------------------------------------------------------------------

#: Картинка над меню. Можно положить файл в assets/menu.png, можно
#: указать URL или file_id уже загруженной картинки в MENU_PHOTO.
#:
#: file_id выгоднее всего: Telegram не перезаливает файл на каждое
#: открытие меню, а меню открывают часто.
MENU_PHOTO = os.getenv("MENU_PHOTO", "").strip()
MENU_PHOTO_FILE = BASE_DIR / "assets" / "menu.png"

#: Валюта в карточках. Только для показа — на расчёты не влияет.
CURRENCY = os.getenv("CURRENCY", "₽")

# --------------------------------------------------------------------------
# Подписка и выплаты
# --------------------------------------------------------------------------

#: Тарифы для экрана «Подписка»: (подпись, цена, приписка справа).
#: Это витрина — приём оплаты подключается отдельно.
SUB_PLANS: tuple[tuple[str, str, str], ...] = (
    ("1 месяц", "399", ""),
    ("3 месяца", "999", "выгода 17%"),
    ("12 месяцев", "2 990", "выгода 38%"),
)

#: Минимальная сумма вывода.
MIN_PAYOUT = os.getenv("MIN_PAYOUT", "500")


def check() -> None:
    """Ранняя проверка: без токена стартовать бессмысленно."""
    if not BOT_TOKEN:
        raise SystemExit(
            "Не задан BOT_TOKEN. Скопируй .env.example в .env и впиши токен "
            "от @BotFather."
        )
