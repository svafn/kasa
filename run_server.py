# -*- coding: utf-8 -*-
"""Промисловий запуск касової книги (FreeBSD / Linux).

    python run_server.py

Параметри беруться з оточення або з файла .env:

    PORT        порт, за замовчуванням 5005
    BIND_HOST   інтерфейс: 127.0.0.1 (за nginx) або 0.0.0.0 (прямий доступ)
    SERVER      waitress | gevent | auto   (за замовчуванням auto)
    THREADS     робочих потоків waitress, за замовчуванням 8

Чому waitress за замовчуванням: це чистий Python, він не потребує
компілятора під час встановлення на FreeBSD і коректно обробляє
блокуючі звернення до SQLite/MySQL у окремих потоках. Gevent
підтримується для однорідності з іншими сервісами на цьому сервері,
але потребує складання з вихідних кодів.
"""
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

# .env читаємо до всього іншого: він задає і SERVER, і PORT.
try:
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:
    pass

_WANTED = os.getenv("SERVER", "auto").lower()

# Монкі-патч gevent має виконуватися до імпорту сокетів і драйвера БД,
# інакше вони залишаться блокуючими і сенс gevent втрачається.
if _WANTED == "gevent":
    from gevent import monkey

    monkey.patch_all()

from app import create_app  # noqa: E402

app = create_app()

HOST = os.getenv("BIND_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5005"))
THREADS = int(os.getenv("THREADS", "8"))


def _log(msg):
    print(f"[kasa] {msg}", flush=True)


def serve():
    if _WANTED in ("auto", "waitress"):
        try:
            from waitress import serve as waitress_serve
        except ImportError:
            if _WANTED == "waitress":
                sys.exit("[kasa] не встановлено waitress: pip install waitress")
        else:
            _log(f"waitress on {HOST}:{PORT}, threads={THREADS}")
            waitress_serve(app, host=HOST, port=PORT, threads=THREADS,
                           ident="kasa", clear_untrusted_proxy_headers=True)
            return

    if _WANTED in ("auto", "gevent"):
        try:
            from gevent.pywsgi import WSGIServer
        except ImportError:
            if _WANTED == "gevent":
                sys.exit("[kasa] не встановлено gevent: pip install gevent")
        else:
            _log(f"gevent on {HOST}:{PORT}")
            WSGIServer((HOST, PORT), app).serve_forever()
            return

    sys.exit("[kasa] не знайдено ні waitress, ні gevent. "
             "Установіть один із них: pip install waitress")


if __name__ == "__main__":
    serve()
