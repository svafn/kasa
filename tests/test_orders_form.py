"""Поведінка форми касового ордера: назви граф і підстановка реквізитів."""
from datetime import date

import pytest

from app.extensions import db
from app.models import CashOrder, Counterparty, User


@pytest.fixture
def client(app):
    app.config["WTF_CSRF_ENABLED"] = False
    u = User(username="t", full_name="Тест Т. Т.", role="admin")
    u.set_password("password123")
    db.session.add(u)
    db.session.add(Counterparty(
        name="Іваненко Іван Іванович", kind="person",
        id_document="паспорт СН 123456, виданий 12.05.2010"))
    db.session.commit()
    c = app.test_client()
    c.post("/auth/login", data={"username": "t", "password": "password123"})
    return c


def test_field_labels_match_the_form(client):
    assert "Прийнято від" in client.get("/orders/new/in").get_data(as_text=True)
    out = client.get("/orders/new/out").get_data(as_text=True)
    assert "Видати" in out
    assert "Прийнято від / Видати" not in out


def test_id_document_map_is_rendered_for_outgoing(client):
    out = client.get("/orders/new/out").get_data(as_text=True)
    assert "const CP_DOCS" in out
    assert "паспорт СН 123456" in out


def test_id_document_is_filled_from_counterparty_card(client, app):
    cp = Counterparty.query.first()
    client.post("/orders/new/in", data={
        "doc_date": date.today().isoformat(), "amount": "1000",
        "source": "general", "counterparty_id": "0",
        "counterparty_text": "Каса", "basis": "Поповнення",
        "corr_account_id": "0", "submit_post": "x"}, follow_redirects=True)
    client.post("/orders/new/out", data={
        "doc_date": date.today().isoformat(), "amount": "100",
        "counterparty_id": str(cp.id), "counterparty_text": cp.name,
        "basis": "Під звіт", "id_document": "",
        "corr_account_id": "0", "submit_post": "x"}, follow_redirects=True)

    order = CashOrder.query.filter_by(kind="out").first()
    assert order.id_document == cp.id_document


def test_manual_id_document_is_not_overwritten(client, app):
    cp = Counterparty.query.first()
    client.post("/orders/new/in", data={
        "doc_date": date.today().isoformat(), "amount": "1000",
        "source": "general", "counterparty_id": "0",
        "counterparty_text": "Каса", "basis": "Поповнення",
        "corr_account_id": "0", "submit_post": "x"}, follow_redirects=True)
    client.post("/orders/new/out", data={
        "doc_date": date.today().isoformat(), "amount": "100",
        "counterparty_id": str(cp.id), "counterparty_text": cp.name,
        "basis": "Під звіт", "id_document": "посвідчення водія ABC 111",
        "corr_account_id": "0", "submit_post": "x"}, follow_redirects=True)

    order = CashOrder.query.filter_by(kind="out").first()
    assert order.id_document == "посвідчення водія ABC 111"


def test_order_card_opens_without_csrf(client):
    """Регресія: картка чернетки раніше падала при вимкненому CSRF."""
    client.post("/orders/new/in", data={
        "doc_date": date.today().isoformat(), "amount": "50",
        "source": "general", "counterparty_id": "0",
        "counterparty_text": "Каса", "basis": "Тест",
        "corr_account_id": "0", "submit": "x"}, follow_redirects=True)
    order = CashOrder.query.first()
    assert client.get(f"/orders/{order.id}").status_code == 200
