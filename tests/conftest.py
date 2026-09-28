import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import create_app          # noqa: E402
from app.extensions import db       # noqa: E402
from app.models import Account, Company, User  # noqa: E402


@pytest.fixture
def app():
    app = create_app(SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
                     SQLALCHEMY_ENGINE_OPTIONS={}, TESTING=True,
                     WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        db.session.add(Company(name="ТОВ Тест", edrpou="12345678",
                               cash_limit=10000))
        db.session.add(Account(code="301", name="Готівка"))
        u = User(username="cashier", full_name="Касир К. К.", role="cashier")
        u.set_password("password123")
        db.session.add(u)
        db.session.commit()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def user(app):
    return User.query.first()
