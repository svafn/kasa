"""Оприбуткування виручки ПРРО та контроль Z-звітів."""
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.extensions import db
from app.models import CashOrder, PosTerminal
from app.services import cashbook as cb


@pytest.fixture
def pos(app):
    p = PosTerminal(name="Каса магазину", fiscal_number="4000123456")
    db.session.add(p)
    db.session.commit()
    return p


def z_order(pos, day, z, amount="1000.00", card=None):
    o = CashOrder(kind="in", doc_date=day, year=day.year, amount=Decimal(amount),
                  counterparty_text="Мельник О. В.", source="prro",
                  pos_id=pos.id, z_number=z, z_date=day,
                  card_amount=Decimal(card) if card else None)
    o.basis = o.build_basis()
    db.session.add(o)
    return o


def test_basis_is_generated_with_fiscal_number(app, pos):
    o = z_order(pos, date.today(), 101)
    assert "Z-звітом) № 101" in o.basis
    assert "ПРРО фіскальний № 4000123456" in o.basis


def test_same_z_cannot_be_posted_twice(app, pos):
    cb.post_order(z_order(pos, date.today(), 101))
    db.session.commit()
    with pytest.raises(cb.BusinessError, match="вже оприбуткований"):
        cb.post_order(z_order(pos, date.today(), 101))


def test_order_date_must_match_z_date(app, pos):
    o = z_order(pos, date.today(), 101)
    o.z_date = date.today() - timedelta(days=1)
    with pytest.raises(cb.BusinessError, match="збігатися з датою Z-звіту"):
        cb.post_order(o)


def test_prro_requires_pos_and_number(app, pos):
    o = z_order(pos, date.today(), 101)
    o.pos_id = None
    with pytest.raises(cb.BusinessError, match="касу ПРРО"):
        cb.post_order(o)

    o2 = z_order(pos, date.today(), None)
    with pytest.raises(cb.BusinessError, match="номер Z-звіту"):
        cb.post_order(o2)


def test_prro_only_for_incoming_orders(app, pos):
    o = z_order(pos, date.today(), 101)
    o.kind = CashOrder.KIND_OUT
    with pytest.raises(cb.BusinessError, match="прибутковим ордером"):
        cb.post_order(o)


def test_gap_in_z_numbering_is_detected(app, pos):
    d1 = date.today() - timedelta(days=2)
    cb.post_order(z_order(pos, d1, 101))
    db.session.commit()
    cb.close_day(cb.get_or_create_sheet(d1))
    db.session.commit()

    d2 = date.today() - timedelta(days=1)
    cb.post_order(z_order(pos, d2, 104))
    cb.post_order(z_order(pos, d2, 106))
    db.session.commit()

    problems = cb.check_z_sequence(d2)
    assert len(problems) == 1
    assert "№ 102" in problems[0] and "№ 103" in problems[0] and "№ 105" in problems[0]


def test_no_gap_when_sequence_continues(app, pos):
    d1 = date.today() - timedelta(days=1)
    cb.post_order(z_order(pos, d1, 101))
    cb.post_order(z_order(pos, d1, 102))
    db.session.commit()
    assert cb.check_z_sequence(d1) == []


def test_z_summary_counts_and_totals(app, pos):
    d = date.today()
    cb.post_order(z_order(pos, d, 101, "1000.00", "500.00"))
    cb.post_order(z_order(pos, d, 102, "2000.00", "300.00"))
    db.session.commit()
    rows = cb.z_summary(d)
    assert len(rows) == 1
    assert rows[0]["count"] == 2
    assert rows[0]["numbers"] == [101, 102]
    assert rows[0]["cash"] == Decimal("3000.00")
    # Безготівкові в касову книгу не входять, лише довідково
    assert rows[0]["card"] == Decimal("800.00")


def test_separate_terminals_have_independent_numbering(app, pos):
    second = PosTerminal(name="Каса складу", fiscal_number="4000999999")
    db.session.add(second)
    db.session.commit()
    d = date.today()
    cb.post_order(z_order(pos, d, 101))
    cb.post_order(z_order(second, d, 55))
    db.session.commit()
    assert cb.check_z_sequence(d) == []
    assert len(cb.z_summary(d)) == 2


# --- регресія: дубль Z-звіту через вебформу ---------------------------------
# Раніше перевірка виконувалася після db.session.add(), і autoflush встигав
# вставити неперевірений документ. Користувач бачив помилку унікального
# обмеження від СУБД замість зрозумілого повідомлення. На MySQL/MariaDB це
# призводило до сторінки помилки.

def _web(app):
    from app.models import User
    app.config["WTF_CSRF_ENABLED"] = False
    u = User(username="w", full_name="Веб Тест", role="admin")
    u.set_password("password123")
    db.session.add(u)
    db.session.commit()
    c = app.test_client()
    c.post("/auth/login", data={"username": "w", "password": "password123"})
    return c


def _post_z(client, pos, znum, amount="1000.00", submit="submit_post"):
    return client.post("/orders/new/in", data={
        "doc_date": date.today().isoformat(), "amount": amount,
        "source": "prro", "pos_id": str(pos.id), "z_number": str(znum),
        "z_date": date.today().isoformat(), "counterparty_id": "0",
        "counterparty_text": "Мельник О. В.", "basis": "",
        "corr_account_id": "0", submit: "x"}, follow_redirects=True)


def test_web_form_rejects_duplicate_z(app, pos):
    client = _web(app)
    r = _post_z(client, pos, 201)
    assert "проведено" in r.get_data(as_text=True)

    r = _post_z(client, pos, 201)
    text = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "вже оприбуткований" in text


def test_web_form_rejects_duplicate_z_as_draft(app, pos):
    client = _web(app)
    _post_z(client, pos, 202)
    r = _post_z(client, pos, 202, submit="submit")
    assert "вже оприбуткований" in r.get_data(as_text=True)


def test_web_form_fills_basis_and_terminal(app, pos):
    client = _web(app)
    _post_z(client, pos, 203, amount="1234.56")
    order = CashOrder.query.filter_by(z_number=203).one()
    assert order.pos_id == pos.id
    assert "Z-звітом) № 203" in order.basis
    assert pos.fiscal_number in order.basis
