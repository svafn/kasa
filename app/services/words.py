# -*- coding: utf-8 -*-
"""Сума прописом українською (для КО-1, КО-2, видаткових відомостей).

Положення НБУ №148: у касовому ордері сума зазначається словами,
копійки — цифрами (додатки 2, 3).
"""
from decimal import Decimal

from app.money import to_decimal

ONES = {
    "m": ["", "один", "два", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"],
    "f": ["", "одна", "дві", "три", "чотири", "п'ять", "шість", "сім", "вісім", "дев'ять"],
}
TEENS = ["десять", "одинадцять", "дванадцять", "тринадцять", "чотирнадцять",
         "п'ятнадцять", "шістнадцять", "сімнадцять", "вісімнадцять", "дев'ятнадцять"]
TENS = ["", "", "двадцять", "тридцять", "сорок", "п'ятдесят", "шістдесят",
        "сімдесят", "вісімдесят", "дев'яносто"]
HUNDREDS = ["", "сто", "двісті", "триста", "чотириста", "п'ятсот", "шістсот",
            "сімсот", "вісімсот", "дев'ятсот"]

SCALES = [
    (("тисяча", "тисячі", "тисяч"), "f"),
    (("мільйон", "мільйони", "мільйонів"), "m"),
    (("мільярд", "мільярди", "мільярдів"), "m"),
    (("трильйон", "трильйони", "трильйонів"), "m"),
]
UAH = ("гривня", "гривні", "гривень")
KOP = ("копійка", "копійки", "копійок")


def plural(n: int, forms) -> str:
    n = abs(int(n))
    if n % 100 in (11, 12, 13, 14):
        return forms[2]
    last = n % 10
    if last == 1:
        return forms[0]
    if last in (2, 3, 4):
        return forms[1]
    return forms[2]


def _triple(n: int, gender: str) -> list:
    out = []
    h, rest = divmod(n, 100)
    if h:
        out.append(HUNDREDS[h])
    if 10 <= rest <= 19:
        out.append(TEENS[rest - 10])
    else:
        t, u = divmod(rest, 10)
        if t:
            out.append(TENS[t])
        if u:
            out.append(ONES[gender][u])
    return out


def int_to_words(n: int, gender: str = "m") -> str:
    n = int(n)
    if n == 0:
        return "нуль"
    groups = []
    while n > 0:
        n, r = divmod(n, 1000)
        groups.append(r)

    words = []
    for idx in range(len(groups) - 1, -1, -1):
        g = groups[idx]
        if g == 0:
            continue
        if idx == 0:
            words += _triple(g, gender)
        else:
            forms, gnd = SCALES[idx - 1]
            words += _triple(g, gnd)
            words.append(plural(g, forms))
    return " ".join(words)


def amount_to_words(value, digits_kop: bool = True, capitalize: bool = True) -> str:
    """1234.56 -> 'Одна тисяча двісті тридцять чотири гривні 56 копійок'."""
    d: Decimal = to_decimal(value)
    total_kop = int(d * 100)
    hrn, kop = divmod(abs(total_kop), 100)

    text = f"{int_to_words(hrn, 'f')} {plural(hrn, UAH)}"
    if digits_kop:
        text += f" {kop:02d} {plural(kop, KOP)}"
    else:
        text += f" {int_to_words(kop, 'f') if kop else 'нуль'} {plural(kop, KOP)}"
    if total_kop < 0:
        text = "мінус " + text
    return text[0].upper() + text[1:] if capitalize else text
