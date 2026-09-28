"""Підписанти й права доступу за відсутності головного бухгалтера."""
from datetime import date, timedelta
from decimal import Decimal

from app.extensions import db
from app.models import CashOrder, Company, User
from app.services import cashbook as cb


def setup_no_accountant(app):
    c = Company.current()
    c.director = "Шевченко Т. Г."
    c.director_title = "Директор"
    c.has_chief_accountant = False
    c.chief_accountant = None
    c.accountant_title = "Директор"
    c.authorization_order = "наказ від 03.01.2026 № 1"
    db.session.commit()
    return c


def test_director_signs_instead_of_chief_accountant(app):
    c = setup_no_accountant(app)
    assert c.signatory("accountant") == ("Директор", "Шевченко Т. Г.")
    assert c.signatory("director") == ("Директор", "Шевченко Т. Г.")
    assert c.accountant_is_director is True
    assert "наказ від 03.01.2026 № 1" in c.signature_note


def test_authorized_person_other_than_director(app):
    c = setup_no_accountant(app)
    c.accountant_title = "Бухгалтер"
    c.accountant_name = "Коваленко І. П."
    db.session.commit()
    assert c.signatory("accountant") == ("Бухгалтер", "Коваленко І. П.")
    # підписує не сам керівник -> у ВКО лишаються два рядки підписів
    assert c.accountant_is_director is False


def test_chief_accountant_present(app):
    c = Company.current()
    c.has_chief_accountant = True
    c.chief_accountant = "Коваленко І. П."
    db.session.commit()
    assert c.signatory("accountant") == ("Головний бухгалтер", "Коваленко І. П.")
    assert c.signature_note == ""


def test_role_permissions(app):
    def role(name):
        u = User(username=name, full_name=name, role=name)
        return u

    assert role("senior_cashier").has("close") is True
    assert role("senior_cashier").has("dicts") is True
    assert role("senior_cashier").has("users") is False
    assert role("senior_cashier").has("reopen") is False

    assert role("director").has("reopen") is True
    assert role("director").has("company") is True
    assert role("director").has("users") is False

    assert role("cashier").has("orders", "post", "close") is True
    assert role("cashier").has("dicts") is False
    assert role("cashier").has("audit") is False

    assert role("viewer").has("orders") is False
    assert role("admin").has("users", "reopen") is True


def test_sheet_records_actual_cashier(app):
    """Касирів двоє: в аркуші фіксується той, хто закрив день."""
    d = date.today() - timedelta(days=1)
    director = User(username="dir", full_name="Шевченко Т. Г.", role="senior_cashier")
    director.set_password("password123")
    db.session.add(director)
    o = CashOrder(kind="in", doc_date=d, year=d.year, amount=Decimal("500.00"),
                  counterparty_text="Контрагент", basis="Підстава")
    db.session.add(o)
    cb.post_order(o, director)
    db.session.commit()

    sheet = cb.get_or_create_sheet(d)
    sheet.cashier_name = None
    cb.close_day(sheet, director)
    db.session.commit()
    assert sheet.cashier_name == "Шевченко Т. Г."


def test_order_signature_uses_posting_user(app):
    """Підпис касира в ордері — від того, хто фактично провів документ."""
    from app.pdf.orders import _cashier

    u = User(username="k", full_name="Мельник О. В.", role="cashier")
    u.set_password("password123")
    db.session.add(u)
    o = CashOrder(kind="in", doc_date=date.today(), year=date.today().year,
                  amount=Decimal("100.00"), counterparty_text="К", basis="П")
    db.session.add(o)
    cb.post_order(o, u)
    db.session.commit()
    assert _cashier(o, Company.current()) == "Мельник О. В."
