# -*- coding: utf-8 -*-
"""Модель даних касової книги.

Нормативна база:
  Положення про ведення касових операцій у національній валюті в Україні,
  затверджене постановою Правління НБУ від 29.12.2017 № 148 (зі змінами).
  Форми: КО-1 (ПКО), КО-2 (ВКО), КО-3 (журнал реєстрації), КО-4 (касова книга).
"""
import hashlib
from datetime import date, datetime, timezone
from decimal import Decimal

from flask_login import UserMixin
from sqlalchemy import UniqueConstraint, CheckConstraint, Index
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.money import Money, ZERO, to_decimal


def utcnow():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- довідники

class Company(db.Model):
    """Підприємство (юридична особа) — «шапка» всіх форм."""
    __tablename__ = "company"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    edrpou = db.Column(db.String(10), nullable=False)          # код за ЄДРПОУ
    address = db.Column(db.String(255))
    subdivision = db.Column(db.String(255))                     # відокремлений підрозділ
    director = db.Column(db.String(150))                        # керівник
    director_title = db.Column(db.String(100), default="Директор")

    # Посада головного бухгалтера може бути не передбачена штатним розписом.
    # Тоді касові документи підписує керівник або інша уповноважена ним особа
    # (п. 26, 45 Положення № 148).
    has_chief_accountant = db.Column(db.Boolean, nullable=False, default=True)
    chief_accountant = db.Column(db.String(150))                # головний бухгалтер
    accountant_title = db.Column(db.String(100), default="Директор")
    accountant_name = db.Column(db.String(150))                 # уповноважена особа
    authorization_order = db.Column(db.String(255))             # наказ про уповноваження

    cashier = db.Column(db.String(150))                         # касир за замовчуванням
    cashier_order = db.Column(db.String(255))   # наказ / договір про матвідповідальність
    cash_limit = db.Column(Money, nullable=False, default=ZERO)  # ліміт залишку готівки
    limit_order = db.Column(db.String(255))                     # реквізити наказу про ліміт
    book_started_at = db.Column(db.Date)                        # дата початку ведення книги
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    @staticmethod
    def current():
        return Company.query.order_by(Company.id).first()

    # --- підписанти друкованих форм
    def signatory(self, kind: str):
        """Повертає (посада, ПІБ) для підпису у формах КО-1…КО-4."""
        if kind == "director":
            return (self.director_title or "Керівник", self.director or "")
        if kind == "accountant":
            if self.has_chief_accountant:
                return ("Головний бухгалтер", self.chief_accountant or "")
            # обов'язки виконує керівник або уповноважена ним особа
            return (self.accountant_title or "Директор",
                    self.accountant_name or self.director or "")
        if kind == "cashier":
            return ("Касир", self.cashier or "")
        return ("", "")

    @property
    def accountant_is_director(self) -> bool:
        """Головбуха немає і його обов'язки виконує сам керівник."""
        return not self.has_chief_accountant and not self.accountant_name

    @property
    def signature_note(self) -> str:
        """Пояснювальний напис для форм, коли головбуха немає за штатом."""
        if self.has_chief_accountant:
            return ""
        text = ("Посаду головного бухгалтера штатним розписом не передбачено; "
                "касові документи підписує особа, уповноважена керівником")
        return f"{text} ({self.authorization_order})." if self.authorization_order \
            else text + "."


class User(UserMixin, db.Model):
    """Користувач із розмежуванням прав (п. 42 Положення — захист від
    несанкціонованого доступу до електронної касової книги)."""
    __tablename__ = "users"

    ROLES = {
        "admin": "Адміністратор",
        "director": "Директор",
        "senior_cashier": "Старший касир",
        "cashier": "Касир",
        "accountant": "Бухгалтер",
        "viewer": "Перегляд",
    }

    # Права: orders — оформлення ордерів, post — проведення, close — закриття дня,
    # reopen — відкриття останнього закритого дня, dicts — довідники,
    # company — реквізити підприємства, users — користувачі, audit — журнал аудиту.
    PERMISSIONS = {
        "admin":         {"orders", "post", "close", "reopen", "dicts",
                          "company", "users", "audit"},
        "director":      {"orders", "post", "close", "reopen", "dicts",
                          "company", "audit"},
        "senior_cashier": {"orders", "post", "close", "dicts", "audit"},
        "cashier":       {"orders", "post", "close"},
        "accountant":    {"orders", "post", "dicts", "company", "audit"},
        "viewer":        set(),
    }

    # Ролі, чий носій має право підписувати касові документи як керівник
    # або як уповноважена ним особа.
    SIGNS_AS_DIRECTOR = {"director"}

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="cashier")
    position = db.Column(db.String(100))          # посада для друку у формах
    is_enabled = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    last_login_at = db.Column(db.DateTime)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_active(self):          # Flask-Login
        return self.is_enabled

    def has(self, *permissions) -> bool:
        """Перевірка прав за роллю."""
        granted = self.PERMISSIONS.get(self.role, set())
        return any(p in granted for p in permissions)

    # Сумісність зі старим кодом
    def can(self, *roles):
        return self.role == "admin" or self.role in roles

    @property
    def signs_as_director(self) -> bool:
        return self.role in self.SIGNS_AS_DIRECTOR

    @property
    def role_title(self):
        return self.ROLES.get(self.role, self.role)


class Counterparty(db.Model):
    """Контрагент / підзвітна особа ('Прийнято від', 'Видати')."""
    __tablename__ = "counterparty"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    kind = db.Column(db.String(20), nullable=False, default="person")  # person|company
    code = db.Column(db.String(12))                                    # ЄДРПОУ / РНОКПП
    id_document = db.Column(db.String(255))   # паспорт тощо — реквізит ВКО
    note = db.Column(db.String(255))
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (Index("ix_counterparty_name", "name"),)


class PosTerminal(db.Model):
    """Каса ПРРО (місце проведення розрахунків).

    Потрібна, щоб нумерація Z-звітів контролювалася окремо за кожним
    реєстратором: два ПРРО мають незалежні послідовності номерів.
    """
    __tablename__ = "pos_terminal"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    fiscal_number = db.Column(db.String(20), unique=True, nullable=False)
    location = db.Column(db.String(255))        # господарська одиниця / адреса

    # Чи послідовні номери Z-звітів у цій касі.
    # Порядковий номер зміни зростає на одиницю, тому пропуск означає
    # невідображену виручку — його варто ловити. Фіскальний номер
    # присвоює сервер ДПС, він не послідовний у межах каси, і контроль
    # розривів для нього не має сенсу.
    z_sequential = db.Column(db.Boolean, nullable=False, default=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True)

    def __str__(self):
        return f"{self.name} (фіск. № {self.fiscal_number})"


class Account(db.Model):
    """Рахунок/субрахунок Плану рахунків — графа «кореспондуючий рахунок»."""
    __tablename__ = "account"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(10), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, nullable=False, default=True)


# ---------------------------------------------------------------- документи

class CashOrder(db.Model):
    """Касовий ордер: KIND_IN = КО-1 (прибутковий), KIND_OUT = КО-2 (видатковий).

    Виправлення в касових ордерах заборонені (п. 26 Положення), тому
    проведений документ не редагується — лише анулюється з причиною,
    номер при цьому не перевикористовується.
    """
    __tablename__ = "cash_order"

    KIND_IN, KIND_OUT = "in", "out"
    DRAFT, POSTED, CANCELLED = "draft", "posted", "cancelled"
    STATUS_TITLES = {DRAFT: "Чернетка", POSTED: "Проведено", CANCELLED: "Анульовано"}

    id = db.Column(db.Integer, primary_key=True)
    kind = db.Column(db.String(3), nullable=False)
    year = db.Column(db.Integer, nullable=False)
    # Номер присвоюється в момент проведення: чернетка номера не має,
    # а номер проведеного (навіть анульованого) ордера не перевикористовується.
    number = db.Column(db.Integer)                          # наскрізна нумерація з початку року
    doc_date = db.Column(db.Date, nullable=False)
    amount = db.Column(Money, nullable=False)

    counterparty_id = db.Column(db.Integer, db.ForeignKey("counterparty.id"))
    counterparty_text = db.Column(db.String(255), nullable=False)  # друкується у формі
    basis = db.Column(db.Text, nullable=False)              # «Підстава»
    appendix = db.Column(db.Text)                           # «Додаток»
    id_document = db.Column(db.String(255))                 # ВКО: «за ... (документ особи)»

    corr_account_id = db.Column(db.Integer, db.ForeignKey("account.id"))
    corr_account_code = db.Column(db.String(10))            # кореспондуючий рахунок, субрахунок
    analytic_code = db.Column(db.String(20))                # код аналітичного рахунку
    purpose_code = db.Column(db.String(10))                 # код цільового призначення
    is_salary = db.Column(db.Boolean, nullable=False, default=False)  # рядок «у т.ч. на з/п»

    # --- оприбуткування виручки ПРРО
    # source: general — звичайне надходження, prro — виручка за Z-звітом
    source = db.Column(db.String(10), nullable=False, default="general")
    pos_id = db.Column(db.Integer, db.ForeignKey("pos_terminal.id"))
    z_number = db.Column(db.Integer)            # порядковий номер Z-звіту
    z_date = db.Column(db.Date)                 # дата фіскального звітного чека
    card_amount = db.Column(Money)              # безготівкові за цим Z, довідково

    status = db.Column(db.String(10), nullable=False, default=DRAFT)
    sheet_id = db.Column(db.Integer, db.ForeignKey("cash_book_sheet.id"))

    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    posted_at = db.Column(db.DateTime)
    posted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    cancelled_at = db.Column(db.DateTime)
    cancel_reason = db.Column(db.String(255))

    counterparty = db.relationship("Counterparty")
    corr_account = db.relationship("Account")
    pos = db.relationship("PosTerminal")
    created_by = db.relationship("User", foreign_keys=[created_by_id])
    posted_by = db.relationship("User", foreign_keys=[posted_by_id])
    sheet = db.relationship("CashBookSheet", back_populates="orders")

    __table_args__ = (
        UniqueConstraint("kind", "year", "number", name="uq_order_kind_year_number"),
        # Один і той самий Z-звіт не може бути оприбуткований двічі.
        UniqueConstraint("pos_id", "z_number", name="uq_order_pos_z"),
        CheckConstraint("amount > 0", name="ck_order_amount_positive"),
        Index("ix_order_date", "doc_date"),
    )

    # --- зручні властивості
    SOURCE_TITLES = {"general": "Звичайне надходження",
                     "prro": "Виручка за Z-звітом ПРРО"}

    @property
    def is_prro(self):
        return self.source == "prro"

    @property
    def z_label(self):
        if not self.is_prro:
            return ""
        pos = f", ПРРО фіскальний № {self.pos.fiscal_number}" if self.pos else ""
        return f"Z-звіт № {self.z_number} від {self.z_date:%d.%m.%Y}{pos}"



    def build_basis(self) -> str:
        """Стандартне формулювання підстави для виручки ПРРО."""
        terminal = self.pos
        if terminal is None and self.pos_id:
            terminal = db.session.get(PosTerminal, self.pos_id)
        pos = f", ПРРО фіскальний № {terminal.fiscal_number}" if terminal else ""
        return ("Оприбуткування готівкової виручки за фіскальним звітним чеком "
                f"(Z-звітом) № {self.z_number} від {self.z_date:%d.%m.%Y}{pos}")

    @property
    def form_code(self):
        return "КО-1" if self.kind == self.KIND_IN else "КО-2"

    @property
    def title(self):
        return ("Прибутковий касовий ордер" if self.kind == self.KIND_IN
                else "Видатковий касовий ордер")

    @property
    def number_str(self):
        return str(self.number) if self.number else "б/н"

    @property
    def status_title(self):
        return self.STATUS_TITLES.get(self.status, self.status)

    @property
    def is_editable(self):
        return self.status == self.DRAFT

    @property
    def signed_amount(self) -> Decimal:
        a = to_decimal(self.amount)
        return a if self.kind == self.KIND_IN else -a


# ------------------------------------------------- касова книга (форма КО-4)

class CashBookSheet(db.Model):
    """Аркуш касової книги за один день.

    п. 39-45 Положення № 148:
      * записи ведуться за кожним ордером у день надходження/видачі готівки;
      * наприкінці дня виводяться підсумки та залишок на кінець дня;
      * аркуші нумеруються автоматично в порядку зростання з початку року;
      * роздруковуються «Вкладний аркуш касової книги» і «Звіт касира»
        у двох примірниках (дні без операцій не роздруковуються).
    """
    __tablename__ = "cash_book_sheet"

    OPEN, CLOSED = "open", "closed"

    id = db.Column(db.Integer, primary_key=True)
    sheet_date = db.Column(db.Date, nullable=False, unique=True)
    year = db.Column(db.Integer, nullable=False)
    number = db.Column(db.Integer)                 # № аркуша, присвоюється при закритті дня

    opening_balance = db.Column(Money, nullable=False, default=ZERO)
    total_in = db.Column(Money, nullable=False, default=ZERO)
    total_out = db.Column(Money, nullable=False, default=ZERO)
    closing_balance = db.Column(Money, nullable=False, default=ZERO)
    salary_balance = db.Column(Money, nullable=False, default=ZERO)  # у т.ч. на з/п

    docs_in_count = db.Column(db.Integer, nullable=False, default=0)
    docs_out_count = db.Column(db.Integer, nullable=False, default=0)

    status = db.Column(db.String(10), nullable=False, default=OPEN)
    cashier_name = db.Column(db.String(150))
    accountant_name = db.Column(db.String(150))
    closed_at = db.Column(db.DateTime)
    closed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    printed_count = db.Column(db.Integer, nullable=False, default=0)

    # ланцюжок хешів — контроль незмінності закритих аркушів
    prev_hash = db.Column(db.String(64))
    content_hash = db.Column(db.String(64))

    closed_by = db.relationship("User")
    orders = db.relationship(
        "CashOrder", back_populates="sheet",
        order_by="CashOrder.kind.desc(), CashOrder.number",
    )

    __table_args__ = (
        UniqueConstraint("year", "number", name="uq_sheet_year_number"),
        Index("ix_sheet_date", "sheet_date"),
    )

    @property
    def is_closed(self):
        return self.status == self.CLOSED

    @property
    def number_str(self):
        return str(self.number) if self.number else "—"

    def compute_hash(self) -> str:
        parts = [
            self.prev_hash or "",
            self.sheet_date.isoformat(),
            str(self.number),
            f"{to_decimal(self.opening_balance)}",
            f"{to_decimal(self.total_in)}",
            f"{to_decimal(self.total_out)}",
            f"{to_decimal(self.closing_balance)}",
        ]
        for o in sorted(self.orders, key=lambda x: (x.kind, x.number)):
            parts.append(f"{o.kind}:{o.number}:{to_decimal(o.amount)}:{o.status}")
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


class AuditLog(db.Model):
    """Журнал дій користувачів — вимога щодо захисту електронної касової книги."""
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    ts = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    username = db.Column(db.String(64))
    action = db.Column(db.String(50), nullable=False)
    entity = db.Column(db.String(50))
    entity_id = db.Column(db.Integer)
    details = db.Column(db.Text)
    ip = db.Column(db.String(45))

    user = db.relationship("User")
