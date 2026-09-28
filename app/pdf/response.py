# -*- coding: utf-8 -*-
"""Віддача PDF браузеру.

Заголовки HTTP передаються в кодуванні latin-1, тому кирилиця в імені
файла («КО-1», «—») обриває відповідь помилкою UnicodeEncodeError уже на
рівні WSGI-сервера: користувач бачить «Internal Server Error», а причина
не має нічого спільного ні з даними, ні з формуванням PDF.

За RFC 6266 передаємо два імені: ASCII-варіант для сумісності і
UTF-8-варіант (`filename*`), який використовують сучасні браузери.
"""
from urllib.parse import quote

from flask import Response

# Транслітерація для ASCII-варіанта імені файла
TRANSLIT = {
    "а": "a", "б": "b", "в": "v", "г": "h", "ґ": "g", "д": "d", "е": "e",
    "є": "ie", "ж": "zh", "з": "z", "и": "y", "і": "i", "ї": "i", "й": "i",
    "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r",
    "с": "s", "т": "t", "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch",
    "ш": "sh", "щ": "shch", "ь": "", "ю": "iu", "я": "ia",
}


def ascii_filename(name: str) -> str:
    """Ім'я файла, придатне для заголовка HTTP.

    Кирилиця транслітерується, решта неприпустимих символів замінюється
    на дефіс. Порожній результат замінюється на «document.pdf».
    """
    out = []
    for ch in name:
        low = ch.lower()
        if low in TRANSLIT:
            repl = TRANSLIT[low]
            out.append(repl.upper() if ch.isupper() and repl else repl)
        elif ch.isascii() and (ch.isalnum() or ch in "._- "):
            out.append(ch)
        else:
            out.append("-")
    cleaned = "".join(out).strip("- ")
    while "--" in cleaned:
        cleaned = cleaned.replace("--", "-")
    return cleaned or "document.pdf"


def pdf_response(data: bytes, filename: str, inline: bool = True) -> Response:
    """Відповідь із PDF і коректно закодованим іменем файла."""
    disposition = "inline" if inline else "attachment"
    fallback = ascii_filename(filename)
    encoded = quote(filename, safe="")
    header = (f"{disposition}; filename=\"{fallback}\"; "
              f"filename*=UTF-8''{encoded}")
    # Остання перевірка: заголовок мусить кодуватися в latin-1, інакше
    # WSGI-сервер обірве відповідь.
    header.encode("latin-1")
    return Response(data, mimetype="application/pdf",
                    headers={"Content-Disposition": header})
