# -*- coding: utf-8 -*-
"""Низькорівневі помічники для друкованих форм (reportlab, мм, кирилиця)."""
import os
from pathlib import Path

from reportlab.lib.colors import black, HexColor
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT = "UA"
FONT_B = "UA-Bold"
GREY = HexColor("#555555")

_FONT_DIR = Path(__file__).parent / "fonts"

# Порядок пошуку: власна тека проєкту -> Linux -> macOS -> Windows
CANDIDATES = [
    # тека проєкту — має найвищий пріоритет
    (_FONT_DIR / "DejaVuSans.ttf", _FONT_DIR / "DejaVuSans-Bold.ttf"),
    # FreeBSD: pkg install dejavu / liberation-fonts-ttf
    ("/usr/local/share/fonts/dejavu/DejaVuSans.ttf",
     "/usr/local/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/local/share/fonts/DejaVu/DejaVuSans.ttf",
     "/usr/local/share/fonts/DejaVu/DejaVuSans-Bold.ttf"),
    ("/usr/local/share/fonts/liberation-fonts-ttf/LiberationSans-Regular.ttf",
     "/usr/local/share/fonts/liberation-fonts-ttf/LiberationSans-Bold.ttf"),
    ("/usr/local/lib/X11/fonts/dejavu/DejaVuSans.ttf",
     "/usr/local/lib/X11/fonts/dejavu/DejaVuSans-Bold.ttf"),
    # Linux
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"),
    ("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
     "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"),
    # macOS / Windows
    ("/Library/Fonts/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf"),
    ("C:/Windows/Fonts/arial.ttf", "C:/Windows/Fonts/arialbd.ttf"),
]

_registered = False


_font_used = None


# Корені, у яких шукаємо шрифт, якщо його немає за відомими шляхами.
# Пакети кладуть файли по-різному (у FreeBSD тека залежить від збірки
# порту), тому фіксований перелік шляхів завжди буде неповним.
FONT_ROOTS = [
    "/usr/local/share/fonts",
    "/usr/local/lib/X11/fonts",
    "/usr/share/fonts",
    "/usr/local/share/texmf-dist/fonts",
    "/opt/local/share/fonts",
    str(Path.home() / ".fonts"),
]

# Пари «звичайний — жирний» у порядку переваги
FONT_PAIRS = [
    ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    ("LiberationSans-Regular.ttf", "LiberationSans-Bold.ttf"),
    ("FreeSans.ttf", "FreeSansBold.ttf"),
    ("NotoSans-Regular.ttf", "NotoSans-Bold.ttf"),
]


class FontsNotFound(RuntimeError):
    """Немає жодного шрифту з кирилицею — PDF сформувати неможливо."""


def _candidates():
    """Шляхи пошуку; KASA_FONT_DIR дає змогу вказати теку зі шрифтами
    в оточенні, не змінюючи код (зручно на сервері)."""
    custom = os.getenv("KASA_FONT_DIR")
    if custom:
        for regular, bold in FONT_PAIRS:
            yield (os.path.join(custom, regular), os.path.join(custom, bold))
    for pair in CANDIDATES:
        yield pair


def _search_roots():
    """Пошук шрифту в теках, де пакети зазвичай їх розміщують.

    Викликається, лише якщо відомі шляхи не спрацювали: обхід дерева
    коштує дорожче за перевірку списку, але виконується один раз
    за час роботи процесу.
    """
    for regular_name, bold_name in FONT_PAIRS:
        for root in FONT_ROOTS:
            if not os.path.isdir(root):
                continue
            for dirpath, _dirnames, filenames in os.walk(root):
                if regular_name in filenames and bold_name in filenames:
                    yield (os.path.join(dirpath, regular_name),
                           os.path.join(dirpath, bold_name))


def _register(regular, bold):
    global _registered, _font_used
    pdfmetrics.registerFont(TTFont(FONT, str(regular)))
    pdfmetrics.registerFont(TTFont(FONT_B, str(bold)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_B)
    _registered = True
    _font_used = str(regular)
    return True


def register_fonts():
    """Реєструє TTF з кирилицею. Без цього PDF друкує кракозябри."""
    if _registered:
        return True

    for regular, bold in _candidates():
        if os.path.exists(regular) and os.path.exists(bold):
            return _register(regular, bold)

    for regular, bold in _search_roots():
        return _register(regular, bold)

    raise FontsNotFound(
        "Не знайдено шрифт із кирилицею — сформувати PDF неможливо.\n\n"
        "Установіть його:\n"
        "    FreeBSD:        pkg install dejavu\n"
        "    Debian/Ubuntu:  apt install fonts-dejavu\n\n"
        "Якщо шрифт уже встановлено, але не знайдено, вкажіть теку з ним:\n"
        "    KASA_FONT_DIR=/шлях/до/теки у файлі .env\n"
        f"або покладіть DejaVuSans.ttf і DejaVuSans-Bold.ttf у {_FONT_DIR}\n\n"
        "Переглянуто теки: " + ", ".join(FONT_ROOTS)
    )


def font_in_use():
    """Шлях до фактично використаного шрифту (для flask check-fonts)."""
    register_fonts()
    return _font_used


MONTHS = ["січня", "лютого", "березня", "квітня", "травня", "червня",
          "липня", "серпня", "вересня", "жовтня", "листопада", "грудня"]
MONTHS_NOM = ["Січень", "Лютий", "Березень", "Квітень", "Травень", "Червень",
              "Липень", "Серпень", "Вересень", "Жовтень", "Листопад", "Грудень"]


def date_words(d):
    """01.03.2026 -> '1 березня 2026 р.'"""
    return f"{d.day} {MONTHS[d.month - 1]} {d.year} р."


def date_blank(d):
    """-> '«01» березня 2026 р.'"""
    return f"«{d.day:02d}» {MONTHS[d.month - 1]} {d.year} р."


class Form:
    """Обгортка над canvas: координати в мм, вісь Y — зверху вниз."""

    def __init__(self, canvas_obj, page_w, page_h):
        register_fonts()
        self.c = canvas_obj
        self.w = page_w
        self.h = page_h

    # --- перетворення координат
    def _x(self, x):
        return x * mm

    def _y(self, y):
        return self.h - y * mm

    # --- примітиви
    def text(self, x, y, s, size=8, bold=False, align="l", color=black):
        if s is None:
            s = ""
        s = str(s)
        self.c.setFont(FONT_B if bold else FONT, size)
        self.c.setFillColor(color)
        if align == "l":
            self.c.drawString(self._x(x), self._y(y), s)
        elif align == "c":
            self.c.drawCentredString(self._x(x), self._y(y), s)
        else:
            self.c.drawRightString(self._x(x), self._y(y), s)
        self.c.setFillColor(black)

    def line(self, x1, y1, x2, y2, width=0.4, dash=None):
        self.c.setLineWidth(width)
        self.c.setDash(dash or ())
        self.c.line(self._x(x1), self._y(y1), self._x(x2), self._y(y2))
        self.c.setDash()

    def rect(self, x, y, w, h, width=0.4, fill=None):
        self.c.setLineWidth(width)
        if fill is not None:
            self.c.setFillColor(fill)
            self.c.rect(self._x(x), self._y(y + h), w * mm, h * mm, stroke=1, fill=1)
            self.c.setFillColor(black)
        else:
            self.c.rect(self._x(x), self._y(y + h), w * mm, h * mm, stroke=1, fill=0)

    def wrap(self, s, width_mm, size=8, bold=False):
        return simpleSplit(str(s or ""), FONT_B if bold else FONT, size, width_mm * mm)

    def text_width(self, s, size=8, bold=False):
        return pdfmetrics.stringWidth(str(s or ""), FONT_B if bold else FONT, size) / mm

    # --- реквізити бланка
    def field(self, x, y, width, value="", label=None, size=8, label_size=5.5,
              bold=False, align="l", underline=True):
        """Значення над лінією, дрібна пояснювальна підказка — під лінією."""
        vx = {"l": x + 1, "c": x + width / 2, "r": x + width - 1}[align]
        self.text(vx, y - 1.2, value, size=size, bold=bold, align=align)
        if underline:
            self.line(x, y, x + width, y, width=0.4)
        if label:
            self.text(x + width / 2, y + 2.8, label, size=label_size,
                      align="c", color=GREY)
        return y + (4.2 if label else 1.5)

    def label_field(self, x, y, label, width_total, value="", size=8,
                    hint=None, bold_value=False):
        """'Підстава: ______' — підпис ліворуч, значення на лінії."""
        self.text(x, y - 1.2, label, size=size)
        lw = self.text_width(label, size) + 1.5
        self.field(x + lw, y, width_total - lw, value, label=hint,
                   size=size, bold=bold_value)
        return y

    def multiline_field(self, x, y, width, value, lines=2, size=8, step=5,
                        label=None):
        """Багаторядковий реквізит ('Підстава', 'Прийнято від')."""
        parts = self.wrap(value, width - 2, size) or [""]
        for i in range(lines):
            txt = parts[i] if i < len(parts) else ""
            if i == lines - 1 and len(parts) > lines:
                txt = parts[i] + "…"
            self.text(x + 1, y - 1.2, txt, size=size)
            self.line(x, y, x + width, y)
            if label and i == lines - 1:
                self.text(x + width / 2, y + 2.8, label, size=5.5,
                          align="c", color=GREY)
            y += step
        return y

    def grid(self, x, y, col_widths, row_heights, width=0.4):
        """Малює сітку таблиці; повертає (x-позиції колонок, y-позиції рядків)."""
        xs = [x]
        for w in col_widths:
            xs.append(xs[-1] + w)
        ys = [y]
        for h in row_heights:
            ys.append(ys[-1] + h)
        self.c.setLineWidth(width)
        for cx in xs:
            self.line(cx, ys[0], cx, ys[-1], width=width)
        for cy in ys:
            self.line(xs[0], cy, xs[-1], cy, width=width)
        return xs, ys

    def cell(self, xs, ys, col, row, value, size=7.5, align="c", bold=False,
             pad=1.2, valign="m", colspan=1):
        x0, x1 = xs[col], xs[col + colspan]
        y0, y1 = ys[row], ys[row + 1]
        h = y1 - y0
        if colspan > 1:
            # прибираємо внутрішні вертикальні лінії об'єднаної клітинки
            self.c.setFillColorRGB(1, 1, 1)
            self.c.rect(self._x(x0) + 0.3, self._y(y1) + 0.3,
                        (x1 - x0) * mm - 0.6, h * mm - 0.6, stroke=0, fill=1)
            self.c.setFillColor(black)
        lines = self.wrap(value, (x1 - x0) - 2 * pad, size, bold) or [""]
        lh = size * 0.42
        total = len(lines) * lh
        if valign == "m":
            ty = y0 + (h - total) / 2 + lh * 0.75
        elif valign == "t":
            ty = y0 + pad + lh * 0.75
        else:
            ty = y1 - pad - total + lh * 0.75
        for ln in lines:
            if align == "l":
                self.text(x0 + pad, ty, ln, size=size, bold=bold, align="l")
            elif align == "r":
                self.text(x1 - pad, ty, ln, size=size, bold=bold, align="r")
            else:
                self.text((x0 + x1) / 2, ty, ln, size=size, bold=bold, align="c")
            ty += lh

    def cut_line(self, x, y1, y2):
        """Лінія відрізу (для квитанції ПКО / звіту касира)."""
        self.line(x, y1, x, y2, width=0.5, dash=[2, 2])
        self.text(x, y1 - 1, "✂", size=7, align="c", color=GREY)

    def form_code(self, x, y, code, width=34):
        """Кутовий штамп 'Типова форма № КО-1'."""
        self.text(x + width, y, "Типова форма № " + code, size=6.5,
                  align="r", color=GREY)
        self.text(x + width, y + 3, "Затверджена наказом Держкомстату України",
                  size=5, align="r", color=GREY)
        self.text(x + width, y + 6, "від 15.12.2011 № 356", size=5,
                  align="r", color=GREY)
