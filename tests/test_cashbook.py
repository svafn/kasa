from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import CashBookSheet, CashOrder
from app.services import cashbook as cb


def mk(kind, amount, day=None, **kw):
    day = day or date.today()
    o = CashOrder(kind=kind, doc_date=day, year=day.year,
                  amount=Decimal(str(amount)),
                  counterparty_text=kw.pop("who", "Контрагент"),
                  basis=kw.pop("basis", "Підстава"), **kw)
    db.session.add(o)
    return o


def test_numbering_is_sequential_per_kind(app):
    a, b = mk("in", 100), mk("in", 200)
    cb.post_order(a); cb.post_order(b)
    c = mk("out", 50)
    cb.post_order(c)
    db.session.commit()
    assert (a.number, b.number, c.number) == (1, 2, 1)


def test_draft_has_no_number(app):
    o = mk("in", 100)
    db.session.commit()
    assert o.number is None and o.number_str == "б/н"


def test_balance_and_day_totals(app):
    cb.post_order(mk("in", "1000.00"))
    cb.post_order(mk("out", "250.50"))
    db.session.commit()
    assert cb.current_balance() == Decimal("749.50")
    sheet = cb.get_or_create_sheet(date.today())
    assert sheet.total_in == Decimal("1000.00")
    assert sheet.closing_balance == Decimal("749.50")


def test_cannot_go_negative(app):
    cb.post_order(mk("in", "100.00"))
    db.session.commit()
    with pytest.raises(cb.BusinessError, match="Недостатньо готівки"):
        cb.post_order(mk("out", "100.01"))


def test_closed_day_is_locked(app):
    yesterday = date.today() - timedelta(days=1)
    cb.post_order(mk("in", "500.00", yesterday))
    db.session.commit()
    sheet = cb.get_or_create_sheet(yesterday)
    cb.close_day(sheet)
    db.session.commit()
    assert sheet.number == 1 and sheet.is_closed
    with pytest.raises(cb.BusinessError, match="закрито"):
        cb.post_order(mk("in", "10.00", yesterday))


def test_opening_balance_carries_over(app):
    d1 = date.today() - timedelta(days=2)
    cb.post_order(mk("in", "800.00", d1))
    db.session.commit()
    cb.close_day(cb.get_or_create_sheet(d1))
    db.session.commit()

    d2 = date.today()
    cb.post_order(mk("in", "200.00", d2))
    db.session.commit()
    s2 = cb.get_or_create_sheet(d2)
    cb.recalc_sheet(s2)
    assert s2.opening_balance == Decimal("800.00")
    assert s2.closing_balance == Decimal("1000.00")


def test_empty_day_not_closable(app):
    sheet = cb.get_or_create_sheet(date.today())
    with pytest.raises(cb.BusinessError, match="немає касових операцій"):
        cb.close_day(sheet)


def test_cancelled_order_keeps_number_and_drops_from_totals(app):
    o = mk("in", "300.00")
    cb.post_order(o)
    db.session.commit()
    num = o.number
    cb.cancel_order(o, "Помилково оформлено")
    db.session.commit()
    assert o.number == num and o.status == CashOrder.CANCELLED
    assert cb.current_balance() == Decimal("0.00")


def test_hash_chain_detects_tampering(app):
    d = date.today() - timedelta(days=1)
    cb.post_order(mk("in", "700.00", d))
    db.session.commit()
    sheet = cb.get_or_create_sheet(d)
    cb.close_day(sheet)
    db.session.commit()
    assert cb.verify_chain(d.year) == []

    sheet.closing_balance = Decimal("999.00")   # імітація втручання в БД
    db.session.commit()
    assert cb.verify_chain(d.year) != []


def test_limit_control(app):
    cb.post_order(mk("in", "15000.00"))
    db.session.commit()
    sheet = cb.get_or_create_sheet(date.today())
    cb.recalc_sheet(sheet)
    assert cb.limit_exceeded(sheet) is True


def test_money_roundtrip_is_exact(app):
    o = mk("in", "0.10")
    cb.post_order(o)
    db.session.commit()
    db.session.expire_all()
    assert db.session.get(CashOrder, o.id).amount == Decimal("0.10")
