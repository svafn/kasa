"""Формування друкованих форм: пошук шрифту й стійкість до неповних даних."""
from datetime import date
from decimal import Decimal

import pytest

import app.pdf.base as base
from app.extensions import db
from app.models import CashOrder, Company, PosTerminal, User
from app.pdf.orders import render_order
from app.services import cashbook as cb


@pytest.fixture(autouse=True)
def _reset_fonts():
    """Кожен тест починає з чистим станом реєстрації шрифтів."""
    saved = (base.CANDIDATES, base.FONT_ROOTS, base._registered)
    yield
    base.CANDIDATES, base.FONT_ROOTS, base._registered = saved


def mk(kind="in", **kw):
    data = dict(kind=kind, doc_date=date.today(), year=date.today().year,
                amount=Decimal("150.00"), counterparty_text="Ковтун Д. П.",
                basis="Оприбуткування виручки")
    data.update(kw)
    order = CashOrder(**data)
    db.session.add(order)
    db.session.flush()
    return order


def test_pdf_without_company_details(app):
    """Реквізити підприємства ще не заповнені — форма все одно друкується."""
    Company.query.delete()
    db.session.commit()
    assert Company.current() is None
    assert len(render_order(mk(), None)) > 1000


def test_pdf_for_draft_without_number(app):
    order = mk()
    assert order.number is None
    assert len(render_order(order, Company.current())) > 1000


@pytest.mark.parametrize("field,value", [
    ("basis", "Оплата за послуги " * 40),
    ("counterparty_text", 'ТОВ "' + "Дуже довга назва " * 12 + '"'),
    ("counterparty_text", "Ку'зьма «Сергій» \"Іванович\""),
    ("appendix", None),
    ("amount", Decimal("0.01")),
    ("amount", Decimal("9999999.99")),
])
def test_pdf_survives_edge_values(app, field, value):
    order = mk(**{field: value})
    assert len(render_order(order, Company.current())) > 1000


def test_pdf_for_prro_order(app):
    pos = PosTerminal(name="Каса магазину", fiscal_number="4000123456")
    db.session.add(pos)
    db.session.commit()
    order = mk(source="prro", pos_id=pos.id, z_number=1, z_date=date.today())
    order.basis = order.build_basis()
    assert len(render_order(order, Company.current())) > 1000


# --- пошук шрифту -----------------------------------------------------------

def test_font_found_by_search_when_path_unknown(app, tmp_path):
    """Пакет поклав шрифт у теку, якої немає в переліку відомих шляхів.

    Так буває на FreeBSD: тека залежить від збірки порту. Шрифт має
    знайтися обходом кореневих тек.
    """
    real = base.font_in_use()          # шрифт цієї системи
    bold = real.replace("DejaVuSans.ttf", "DejaVuSans-Bold.ttf")
    if not (real.endswith("DejaVuSans.ttf") and __import__("os").path.exists(bold)):
        pytest.skip("на цій системі немає пари DejaVuSans/Bold")

    nest = tmp_path / "share" / "fonts" / "dejavu-fonts-ttf-2.37"
    nest.mkdir(parents=True)
    for src, name in ((real, "DejaVuSans.ttf"), (bold, "DejaVuSans-Bold.ttf")):
        (nest / name).write_bytes(open(src, "rb").read())

    base.CANDIDATES = [("/nonexistent/a.ttf", "/nonexistent/b.ttf")]
    base.FONT_ROOTS = [str(tmp_path / "share" / "fonts")]
    base._registered = False

    assert base.font_in_use().startswith(str(nest))


def test_missing_font_gives_actionable_error(app):
    base.CANDIDATES = [("/nonexistent/a.ttf", "/nonexistent/b.ttf")]
    base.FONT_ROOTS = ["/nonexistent-root"]
    base._registered = False

    with pytest.raises(base.FontsNotFound) as exc:
        render_order(mk(), Company.current())

    text = str(exc.value)
    assert "pkg install dejavu" in text
    assert "KASA_FONT_DIR" in text


def test_missing_font_shows_readable_page_not_bare_500(app):
    """Регресія: раніше користувач бачив голий 'Internal Server Error'."""
    app.config["WTF_CSRF_ENABLED"] = False
    u = User(username="p", full_name="Друк Тест", role="admin")
    u.set_password("password123")
    db.session.add(u)
    order = mk()
    cb.post_order(order, u)
    db.session.commit()

    client = app.test_client()
    client.post("/auth/login", data={"username": "p", "password": "password123"})

    base.CANDIDATES = [("/nonexistent/a.ttf", "/nonexistent/b.ttf")]
    base.FONT_ROOTS = ["/nonexistent-root"]
    base._registered = False

    r = client.get(f"/orders/{order.id}/pdf")
    page = r.get_data(as_text=True)
    assert r.status_code == 500
    assert "Не налаштовано шрифт для PDF" in page
    assert "pkg install dejavu" in page


# --- заголовки відповіді ----------------------------------------------------
# Регресія: ім'я файла з кирилицею («КО-1», «—») обривало відповідь на рівні
# WSGI-сервера з UnicodeEncodeError, бо заголовки HTTP передаються в latin-1.
# Тестовий клієнт Flask заголовки не кодує, тому такі вади проходять повз
# звичайні перевірки — цей тест кодує їх явно.

def test_ascii_filename_transliterates_cyrillic():
    from app.pdf.response import ascii_filename

    assert ascii_filename("КО-1_15_2026-09-25.pdf") == "KO-1_15_2026-09-25.pdf"
    assert ascii_filename("КО-4_аркуш-—.pdf").isascii()
    assert ascii_filename("———").isascii()
    assert ascii_filename("") == "document.pdf"


def test_pdf_response_header_is_latin1_encodable():
    from app.pdf.response import pdf_response

    for name in ["КО-1_1_2026-09-25.pdf", "КО-4_2026-09-25_аркуш-—.pdf",
                 "Касова-книга-2026.pdf", "звіт «касира».pdf"]:
        header = pdf_response(b"%PDF-1.4", name).headers["Content-Disposition"]
        header.encode("latin-1")          # не має викидати UnicodeEncodeError
        assert "filename*=UTF-8''" in header


def test_all_pdf_routes_send_encodable_headers(app):
    """Кожен маршрут із PDF має віддавати заголовок, придатний для latin-1."""
    from datetime import date as _date

    app.config["WTF_CSRF_ENABLED"] = False
    u = User(username="h", full_name="Заголовок Тест", role="admin")
    u.set_password("password123")
    db.session.add(u)
    order = mk()
    cb.post_order(order, u)
    db.session.commit()
    day = _date.today().isoformat()

    client = app.test_client()
    client.post("/auth/login", data={"username": "h", "password": "password123"})

    for url in (f"/orders/{order.id}/pdf", "/orders/journal.pdf",
                f"/book/{day}/pdf"):
        r = client.get(url)
        assert r.status_code == 200, url
        assert r.mimetype == "application/pdf", url
        # Саме ця операція падала на справжньому сервері
        r.headers["Content-Disposition"].encode("latin-1")
