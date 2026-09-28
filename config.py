import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-secret")

    _url = os.getenv("DATABASE_URL", "sqlite:///instance/kasa.db")
    # Відносний шлях до SQLite робимо абсолютним відносно кореня проєкту,
    # щоб застосунок не залежав від поточного каталогу запуску.
    if _url.startswith("sqlite:///") and not _url.startswith("sqlite:////"):
        _rel = _url[len("sqlite:///"):]
        if not os.path.isabs(_rel):
            _path = BASE_DIR / _rel
            _path.parent.mkdir(parents=True, exist_ok=True)
            _url = f"sqlite:///{_path}"
    SQLALCHEMY_DATABASE_URI = _url
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Налаштування пулу однакові для SQLite і MySQL; pool_recycle критичний
    # для MySQL (wait_timeout за замовчуванням 8 годин розриває з'єднання).
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
    }

    # Для MySQL додаємо utf8mb4 та STRICT-режим на рівні сесії
    if SQLALCHEMY_DATABASE_URI.startswith("mysql"):
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_ALL_TABLES,NO_ENGINE_SUBSTITUTION'",
        }

    WTF_CSRF_TIME_LIMIT = None
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 8

    BABEL_TZ = os.getenv("TZ", "Europe/Kyiv")
