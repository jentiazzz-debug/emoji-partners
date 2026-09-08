"""Запуск и присмотр за ботами партнёров.

Каждый бот партнёра — отдельный процесс с кодом движка, но со своим
токеном и своей папкой данных. Отдельный процесс, а не второй
Dispatcher в общем: движок написан как самостоятельное приложение с
глобальным config, и двум токенам в одном процессе там не разойтись.
Заодно падение одного бота не роняет остальные и не роняет франшизу.

Движок настраивается переменными окружения, и это важно: свой .env он
читает через load_dotenv, который **не** перетирает уже заданные
переменные. Значит, переданное здесь окружение сильнее файла — код
движка править не нужно вообще.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import sys
from pathlib import Path

import config
import db

log = logging.getLogger("partners.supervisor")

#: Живые процессы: id строки бота → процесс. Переживает только сессию,
#: поэтому при старте франшизы боты поднимаются заново (start_all).
_procs: dict[int, subprocess.Popen] = {}

#: На Windows дочерний процесс иначе открывает пустое консольное окно
#: на каждого бота — на сервере это никого не смущает, а на рабочей
#: машине через десять ботов работать невозможно.
_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

#: Переменные франшизы, которые не должны протечь в дочерний бот: у
#: него свои токен, база и админы.
_STRIP = ("BOT_TOKEN", "DATA_DIR", "DB_PATH", "ENGINE_DIR", "WORKSPACES", "BRAND")

#: Строка, по которой видно, что бот представился Telegram и работает.
#: Движок пишет её в лог сразу после getMe — раньше этого «запущен»
#: означает только «процесс не упал», а это разные вещи.
READY_MARK = os.getenv("READY_MARK", "Запущен как")


def workspace(bot_id: int) -> Path:
    """Рабочая папка бота. Имя — telegram-id: он не меняется никогда."""
    path = config.WORKSPACES / str(bot_id)
    (path / "data").mkdir(parents=True, exist_ok=True)
    return path


def _env(row: dict) -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _STRIP}
    ws = workspace(int(row["bot_id"]))
    #: Партнёр — админ своего бота: цены, рассылка, статистика. Админы
    #: сервиса добавлены следом, чтобы разбирать жалобы, не выпрашивая
    #: доступ у партнёра.
    admins = {int(row["owner"])} | config.ADMIN_IDS
    env.update(
        BOT_TOKEN=row["token"],
        DATA_DIR=str(ws / "data"),
        ADMIN_IDS=",".join(str(i) for i in sorted(admins)),
        SUPPORT_CONTACT=config.SUPPORT,
        #: Обязательную подписку на чужой канал дочерним ботам не
        #: навязываем: у движка в дефолте стоит канал автора, и без
        #: этой строки все боты франшизы гнали бы аудиторию туда.
        REQUIRED_CHANNEL="",
        PYTHONIOENCODING="utf-8",
        PYTHONUNBUFFERED="1",
    )
    return env


def alive(row_id: int) -> bool:
    proc = _procs.get(row_id)
    return bool(proc and proc.poll() is None)


def tail(row: dict, lines: int = 12) -> str:
    """Хвост лога бота — то, что показывается партнёру при ошибке."""
    path = workspace(int(row["bot_id"])) / "bot.log"
    if not path.exists():
        return ""
    try:
        text = path.read_text("utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(text[-lines:])


#: Последняя строка трейсбека: «полное.имя.КлассОшибки: сообщение».
#: Именно она объясняет падение — всё, что выше, это стек, а всё, что
#: ниже, обычно уборка aiohttp.
_EXC = re.compile(r"^[\w.]*(?:Error|Exception)\s*:\s*\S")

#: Слова для запасного поиска, если трейсбека в логе нет.
_ERR_WORDS = ("error", "critical", "ошибк")

#: Шум, который выглядит как ошибка, но ею не является: aiohttp ругается
#: на незакрытую сессию уже после настоящего падения, и без этого
#: фильтра партнёр увидел бы «Unclosed connector» вместо «токен отозван».
_NOISE = ("unclosed", "connector:", "client_session:", "connections:")


def reason(row: dict) -> str:
    """Короткая причина падения из лога — то, что покажется партнёру."""
    lines = [s.strip() for s in tail(row, 80).splitlines() if s.strip()]
    clean = [s for s in lines if not any(n in s.lower() for n in _NOISE)]

    for line in reversed(clean):
        if _EXC.match(line):
            return line[:400]
    for line in reversed(clean):
        if any(w in line.lower() for w in _ERR_WORDS):
            return line[:400]
    return "\n".join(clean[-4:])[:400]


async def start(row: dict) -> tuple[bool, str]:
    """Поднять бота. Возвращает (получилось, что сказать партнёру)."""
    row_id = int(row["id"])
    if alive(row_id):
        return True, "Бот уже запущен."

    ws = workspace(int(row["bot_id"]))
    logfile = open(ws / "bot.log", "a", encoding="utf-8", errors="replace")
    try:
        proc = subprocess.Popen(
            [sys.executable, config.ENGINE_ENTRY],
            cwd=str(config.ENGINE_DIR),
            env=_env(row),
            stdout=logfile,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=_FLAGS,
        )
    except OSError as err:
        logfile.close()
        await db.set_state(row_id, "error", str(err))
        await db.log(row["owner"], "bot_error", f"@{row['username']}: {err}")
        return False, f"Не удалось запустить: {err}"

    _procs[row_id] = proc

    # Живой процесс — ещё не работающий бот. Отозванный токен движок
    # обнаруживает не сразу: сначала импорты, потом первый запрос к
    # Telegram, и только тогда падение. Поэтому ждём не по таймеру, а
    # до одного из двух исходов: процесс умер или в логе появилась
    # строка о том, что бот представился Telegram.
    deadline = asyncio.get_running_loop().time() + config.START_TIMEOUT
    while asyncio.get_running_loop().time() < deadline:
        if proc.poll() is not None:
            err = reason(row) or f"процесс завершился с кодом {proc.returncode}"
            await db.set_state(row_id, "error", err)
            await db.log(row["owner"], "bot_error", f"@{row['username']}")
            _procs.pop(row_id, None)
            return False, "Бот не поднялся. Что в логе:\n\n" + err
        if READY_MARK in tail(row, 40):
            await db.set_state(row_id, "running", None)
            await db.log(row["owner"], "bot_start", f"@{row['username']}")
            return True, "Бот запущен."
        await asyncio.sleep(0.5)

    # Процесс жив, но о себе не сообщил. Обычно это первый запуск:
    # движок пересчитывает превью 250 шаблонов и до Telegram доходит
    # позже. Гасить такого нельзя — досмотрит watchdog.
    await db.set_state(row_id, "running", None)
    await db.log(row["owner"], "bot_start", f"@{row['username']} (медленный старт)")
    return True, (
        "Бот запущен, но поднимается дольше обычного — так бывает при "
        "первом старте. Проверьте статус через минуту."
    )


async def stop(row: dict) -> str:
    """Остановить бота. Сначала вежливо, через пять секунд — жёстко."""
    row_id = int(row["id"])
    proc = _procs.pop(row_id, None)
    if proc and proc.poll() is None:
        proc.terminate()
        for _ in range(50):
            if proc.poll() is not None:
                break
            await asyncio.sleep(0.1)
        else:
            proc.kill()
    await db.set_state(row_id, "stopped", None)
    await db.log(row["owner"], "bot_stop", f"@{row['username']}")
    return "Бот остановлен."


async def restart(row: dict) -> tuple[bool, str]:
    await stop(row)
    return await start(row)


async def start_all() -> None:
    """Поднять при старте франшизы всё, что должно работать."""
    rows = [r for r in await db.all_bots() if r["autostart"]]
    for row in rows:
        ok, _ = await start(row)
        log.info("бот @%s: %s", row["username"], "поднят" if ok else "не поднялся")
        # Пауза между запусками: десяток ботов, одновременно считающих
        # превью шаблонов, кладут диск и растягивают старт всем.
        await asyncio.sleep(1.0)


async def stop_all() -> None:
    for row_id, proc in list(_procs.items()):
        if proc.poll() is None:
            proc.terminate()
        _procs.pop(row_id, None)


async def watchdog() -> None:
    """Присматривать за процессами и поднимать упавшие.

    Бот партнёра — это его деньги: упавший ночью и замеченный утром
    процесс стоит дороже, чем перезапуск вслепую. Поэтому упавший
    поднимается сам, но не бесконечно — после трёх подряд падений
    остаётся лежать с пометкой, иначе бот с отозванным токеном будет
    перезапускаться вечно.
    """
    fails: dict[int, int] = {}
    while True:
        await asyncio.sleep(20)
        for row in await db.all_bots("running"):
            row_id = int(row["id"])
            if alive(row_id):
                fails.pop(row_id, None)
                continue
            fails[row_id] = fails.get(row_id, 0) + 1
            if fails[row_id] > 3:
                await db.set_state(row_id, "error", reason(row) or "процесс упал")
                await db.log(row["owner"], "bot_down", f"@{row['username']}")
                log.warning("бот @%s не поднимается, оставлен", row["username"])
                continue
            log.warning("бот @%s упал, поднимаю", row["username"])
            await start(row)
