import pytest

from app.services.words import amount_to_words, plural


@pytest.mark.parametrize("value,expected", [
    ("0", "Нуль гривень 00 копійок"),
    ("1", "Одна гривня 00 копійок"),
    ("2.05", "Дві гривні 05 копійок"),
    ("11", "Одинадцять гривень 00 копійок"),
    ("21", "Двадцять одна гривня 00 копійок"),
    ("1000", "Одна тисяча гривень 00 копійок"),
    ("1234.56", "Одна тисяча двісті тридцять чотири гривні 56 копійок"),
    ("1000000", "Один мільйон гривень 00 копійок"),
    ("2000000.01", "Два мільйони гривень 01 копійка"),
    ("112", "Сто дванадцять гривень 00 копійок"),
])
def test_amount_to_words(value, expected):
    assert amount_to_words(value) == expected


def test_plural_rules():
    forms = ("гривня", "гривні", "гривень")
    assert plural(1, forms) == "гривня"
    assert plural(3, forms) == "гривні"
    assert plural(11, forms) == "гривень"
    assert plural(101, forms) == "гривня"
    assert plural(114, forms) == "гривень"
