"""Грошовий тип, однаковий для SQLite і MySQL.

Зберігаємо суму цілим числом копійок (BigInteger). Це:
  * виключає похибки float (у SQLite немає справжнього DECIMAL);
  * дає коректні SUM/ORDER BY/порівняння в обох СУБД;
  * робить міграцію SQLite -> MySQL тривіальною.
На рівні Python працюємо тільки з Decimal.
"""
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import BigInteger
from sqlalchemy.types import TypeDecorator

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def to_decimal(value) -> Decimal:
    if value is None:
        return ZERO
    if isinstance(value, Decimal):
        d = value
    else:
        d = Decimal(str(value).replace(" ", "").replace("\u00a0", "").replace(",", "."))
    return d.quantize(CENT, rounding=ROUND_HALF_UP)


class Money(TypeDecorator):
    impl = BigInteger
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return int(to_decimal(value) * 100)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return (Decimal(int(value)) / 100).quantize(CENT)


def fmt_money(value, thousands=True) -> str:
    """1234.5 -> '1 234,50' (український формат)."""
    d = to_decimal(value)
    neg = d < 0
    s = f"{abs(d):,.2f}".replace(",", "\u00a0") if thousands else f"{abs(d):.2f}"
    s = s.replace(".", ",")
    return ("-" + s) if neg else s
