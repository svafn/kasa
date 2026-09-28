# -*- coding: utf-8 -*-
"""CLI-команди: flask init-db, flask create-admin, flask demo-data, flask check-fonts."""
import random
from datetime import date, timedelta
from decimal import Decimal

import click
from flask.cli import with_appcontext

from app.extensions import db
from app.models import Account, CashOrder, Company, Counterparty, User

PLAN = [
    ("301", "Готівка в національній валюті"),
    ("311", "Поточні рахунки в національній валюті"),
    ("333", "Грошові кошти в дорозі в національній валюті"),
    ("361", "Розрахунки з вітчизняними покупцями"),
    ("372", "Розрахунки з підзвітними особами"),
    ("377", "Розрахунки з іншими дебіторами"),
    ("631", "Розрахунки з вітчизняними постачальниками"),
    ("661", "Розрахунки за заробітною платою"),
    ("685", "Розрахунки з іншими кредиторами"),
    ("701", "Дохід від реалізації готової продукції"),
    ("702", "Дохід від реалізації товарів"),
    ("703", "Дохід від реалізації робіт і послуг"),
    ("719", "Інші доходи від операційної діяльності"),
]


def register_cli(app):

    @app.cli.command("seed-dicts")
    @with_appcontext
    def seed_dicts():
        """Наповнити план рахунків типовими рахунками.

        Команда безпечна для повторного запуску: наявні рахунки не змінюються,
        додаються лише відсутні.
        """
        added = 0
        for code, name in PLAN:
            if not Account.query.filter_by(code=code).first():
                db.session.add(Account(code=code, name=name))
                added += 1
        db.session.commit()
        if added:
            click.echo(f"План рахунків поповнено: додано рахунків — {added}.")
        else:
            click.echo("План рахунків уже містить усі типові рахунки.")

    @app.cli.command("init-db")
    @with_appcontext
    def init_db():
        """Створити схему без Alembic (альтернатива flask db upgrade).

        Потрібна лише для швидкого разового запуску. Після створення таблиць
        схема позначається поточною версією міграцій, інакше наступний
        `flask db upgrade` спробує створити вже наявні таблиці.
        """
        from flask_migrate import stamp

        db.create_all()
        for code, name in PLAN:
            if not Account.query.filter_by(code=code).first():
                db.session.add(Account(code=code, name=name))
        db.session.commit()
        stamp()          # позначаємо схему як актуальну для Alembic
        click.echo("Базу створено, план рахунків заповнено, "
                   "схему позначено поточною версією міграцій.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--full-name", prompt="ПІБ")
    @click.option("--password", prompt=True, hide_input=True,
                  confirmation_prompt=True)
    @with_appcontext
    def create_admin(username, full_name, password):
        """Створити адміністратора."""
        if User.query.filter_by(username=username).first():
            click.echo("Такий користувач уже існує."), exit(1)
        u = User(username=username, full_name=full_name, role="admin")
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        click.echo(f"Адміністратора {username} створено.")

    @app.cli.command("check-fonts")
    def check_fonts():
        """Перевірити наявність шрифту з кирилицею для PDF.

        Код виходу 1, якщо шрифт не знайдено, — щоб команду можна було
        використовувати в перевірках після встановлення.
        """
        from app.pdf.base import FontsNotFound, font_in_use

        try:
            click.echo(f"Використовується шрифт: {font_in_use()}")
            click.echo("Кирилиця в PDF друкуватиметься коректно.")
        except FontsNotFound as e:
            click.echo(str(e), err=True)
            raise SystemExit(1)

    @app.cli.command("verify-chain")
    @click.option("--year", type=int, default=None,
                  help="Рік перевірки; за замовчуванням поточний.")
    @with_appcontext
    def verify_chain(year):
        """Перевірити незмінність закритих аркушів касової книги.

        Код виходу 1, якщо виявлено зміни: це дає змогу викликати команду
        з cron і отримувати повідомлення лише за наявності проблем.
        """
        from app.services.cashbook import verify_chain as check

        year = year or date.today().year
        problems = check(year)
        if problems:
            click.echo(f"УВАГА: виявлено порушення цілісності за {year} рік:")
            for p in problems:
                click.echo(f"  - {p}")
            raise SystemExit(1)
        click.echo(f"Контроль цілісності за {year} рік пройдено: "
                   "закриті аркуші не змінювалися.")

    @app.cli.command("demo-data")
    @with_appcontext
    def demo_data():
        """Наповнити демонстраційними даними (тільки для тестів)."""
        from app.services import cashbook as cb

        if not Company.current():
            db.session.add(Company(
                name='ТОВ "Приклад"', edrpou="12345678",
                address="м. Київ, вул. Хрещатик, 1",
                director="Шевченко Т. Г.", chief_accountant="Коваленко І. П.",
                cashier="Мельник О. В.", cash_limit=Decimal("10000.00"),
                limit_order="Наказ від 03.01.2026 № 2"))
        for name, kind, code in [
            ("Петренко Петро Петрович", "person", "1234567890"),
            ("Іваненко Іван Іванович", "person", "2345678901"),
            ('ТОВ "Постачальник"', "company", "87654321"),
            ('ФОП Сидоренко С. С.', "company", "3456789012"),
        ]:
            if not Counterparty.query.filter_by(name=name).first():
                db.session.add(Counterparty(name=name, kind=kind, code=code,
                                            id_document="паспорт СН 123456"))
        db.session.commit()

        admin = User.query.filter_by(role="admin").first()
        start = date.today() - timedelta(days=6)
        for i in range(6):
            d = start + timedelta(days=i)
            cps = Counterparty.query.all()
            acc_in = Account.query.filter_by(code="361").first()
            acc_out = Account.query.filter_by(code="372").first()
            for _ in range(random.randint(1, 3)):
                o = CashOrder(kind=CashOrder.KIND_IN, doc_date=d, year=d.year,
                              amount=Decimal(random.randrange(50000, 500000)) / 100,
                              counterparty_text=random.choice(cps).name,
                              basis="Оплата за товар згідно з накладною",
                              corr_account_id=acc_in.id, corr_account_code="361",
                              created_by_id=admin.id if admin else None)
                db.session.add(o)
                cb.post_order(o, admin)
            for _ in range(random.randint(0, 2)):
                o = CashOrder(kind=CashOrder.KIND_OUT, doc_date=d, year=d.year,
                              amount=Decimal(random.randrange(10000, 150000)) / 100,
                              counterparty_text=random.choice(cps).name,
                              basis="Видача під звіт на господарські потреби",
                              id_document="паспорт СН 123456",
                              corr_account_id=acc_out.id, corr_account_code="372",
                              created_by_id=admin.id if admin else None)
                db.session.add(o)
                try:
                    cb.post_order(o, admin)
                except cb.BusinessError:
                    db.session.expunge(o)
            db.session.commit()
            if i < 5:
                sheet = cb.get_or_create_sheet(d)
                try:
                    cb.close_day(sheet, admin)
                    db.session.commit()
                except cb.BusinessError as e:
                    db.session.rollback()
                    click.echo(f"{d}: {e}")
        click.echo("Демонстраційні дані створено.")
