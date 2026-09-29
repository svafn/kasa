# -*- coding: utf-8 -*-
"""Бізнес-логіка касової книги: нумерація, залишки, закриття дня.

Ключові правила (Положення НБУ № 148):
  * ордер реєструється днем фактичного надходження/видачі готівки (п. 39);
  * нумерація ордерів — наскрізна з початку року, окремо для КО-1 і КО-2;
  * залишок у касі не може бути від'ємним;
  * записи за закритий (роздрукований і зданий) день не змінюються;
  * залишок на початок дня = залишок на кінець попереднього дня з операціями.
"""
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from app.extensions import db
from app.models import CashBookSheet, CashOrder, Company, PosTerminal, utcnow
from app.money import ZERO, to_decimal


class BusinessError(Exception):
    """Порушення облікового правила — показуємо користувачу як flash."""


# Унікальні обмеження бази — остання лінія захисту. Спрацювати вони можуть
# і тоді, коли перевірки в коді пройшли: наприклад, два касири одночасно
# оформили ордер на той самий Z-звіт. Повідомлення бази нечитабельне,
# тому перекладаємо його на мову предметної області.
_CONSTRAINT_MESSAGES = {
    "uq_order_pos_z": (
        "Цей Z-звіт за вказаною касою вже оприбуткований іншим ордером. "
        "Оновіть перелік документів за день."
    ),
    "uq_order_kind_year_number": (
        "Номер ордера щойно зайняв інший документ. "
        "Повторіть проведення — номер буде присвоєно наступний."
    ),
    "uq_sheet_year_number": (
        "Номер аркуша касової книги щойно зайняв інший день. "
        "Повторіть закриття дня."
    ),
}


def friendly_integrity_error(exc) -> str:
    """Читабельне пояснення для порушення обмеження бази."""
    text_of = str(getattr(exc, "orig", exc))
    for name, message in _CONSTRAINT_MESSAGES.items():
        if name in text_of:
            return message
    return ("Не вдалося зберегти документ: база відхилила запис. "
            "Перевірте введені дані й повторіть спробу.")


# ------------------------------------------------------------------ нумерація

def next_number(kind: str, year: int) -> int:
    """Наступний наскрізний номер ордера в межах року.

    На MySQL беремо рядки під блокування (SELECT ... FOR UPDATE), щоб два
    касири одночасно не отримали однаковий номер; на SQLite запис і так
    серіалізований. Додатково номер захищений UNIQUE-обмеженням.
    """
    q = select(func.max(CashOrder.number)).where(
        CashOrder.kind == kind, CashOrder.year == year
    )
    if db.engine.dialect.name == "mysql":
        q = q.with_for_update()
    current = db.session.execute(q).scalar()
    return (current or 0) + 1


def next_sheet_number(year: int) -> int:
    q = select(func.max(CashBookSheet.number)).where(CashBookSheet.year == year)
    if db.engine.dialect.name == "mysql":
        q = q.with_for_update()
    return (db.session.execute(q).scalar() or 0) + 1


# ------------------------------------------------------------------- аркуші

def last_closed_sheet(before: date = None) -> CashBookSheet | None:
    q = CashBookSheet.query.filter(CashBookSheet.status == CashBookSheet.CLOSED)
    if before:
        q = q.filter(CashBookSheet.sheet_date < before)
    return q.order_by(CashBookSheet.sheet_date.desc()).first()


def opening_balance_for(day: date) -> Decimal:
    """Залишок на початок дня — кінцевий залишок останнього закритого аркуша
    до цієї дати плюс рух за незакритими днями між ними."""
    prev = last_closed_sheet(before=day)
    balance = to_decimal(prev.closing_balance) if prev else ZERO
    start = prev.sheet_date if prev else date(day.year - 5, 1, 1)

    orders = CashOrder.query.filter(
        CashOrder.status == CashOrder.POSTED,
        CashOrder.doc_date > start,
        CashOrder.doc_date < day,
    ).all()
    for o in orders:
        balance += o.signed_amount
    return balance


def get_or_create_sheet(day: date) -> CashBookSheet:
    sheet = CashBookSheet.query.filter_by(sheet_date=day).one_or_none()
    if sheet is None:
        sheet = CashBookSheet(
            sheet_date=day,
            year=day.year,
            opening_balance=opening_balance_for(day),
            status=CashBookSheet.OPEN,
        )
        company = Company.current()
        if company:
            sheet.cashier_name = company.cashier
            # За відсутності головбуха записи перевіряє керівник
            # або уповноважена ним особа.
            sheet.accountant_name = company.signatory("accountant")[1]
        db.session.add(sheet)
        db.session.flush()
    return sheet


def recalc_sheet(sheet: CashBookSheet) -> CashBookSheet:
    """Перерахунок підсумків аркуша за проведеними ордерами дня."""
    if sheet.is_closed:
        return sheet
    orders = CashOrder.query.filter(
        CashOrder.doc_date == sheet.sheet_date,
        CashOrder.status == CashOrder.POSTED,
    ).all()

    sheet.opening_balance = opening_balance_for(sheet.sheet_date)
    sheet.total_in = sum((to_decimal(o.amount) for o in orders
                          if o.kind == CashOrder.KIND_IN), ZERO)
    sheet.total_out = sum((to_decimal(o.amount) for o in orders
                           if o.kind == CashOrder.KIND_OUT), ZERO)
    sheet.closing_balance = (to_decimal(sheet.opening_balance)
                             + to_decimal(sheet.total_in)
                             - to_decimal(sheet.total_out))
    sheet.salary_balance = sum((to_decimal(o.amount) for o in orders
                                if o.kind == CashOrder.KIND_OUT and o.is_salary), ZERO)
    sheet.docs_in_count = sum(1 for o in orders if o.kind == CashOrder.KIND_IN)
    sheet.docs_out_count = sum(1 for o in orders if o.kind == CashOrder.KIND_OUT)
    for o in orders:
        o.sheet_id = sheet.id
    return sheet


def current_balance(on_day: date = None) -> Decimal:
    """Залишок готівки в касі на кінець зазначеного дня (за замовчуванням сьогодні)."""
    day = on_day or date.today()
    sheet = CashBookSheet.query.filter_by(sheet_date=day).one_or_none()
    if sheet and sheet.is_closed:
        return to_decimal(sheet.closing_balance)
    balance = opening_balance_for(day)
    todays = CashOrder.query.filter(
        CashOrder.doc_date == day, CashOrder.status == CashOrder.POSTED
    ).all()
    for o in todays:
        balance += o.signed_amount
    return balance


# ---------------------------------------------------------- проведення ордера

def validate_date_open(day: date):
    sheet = CashBookSheet.query.filter_by(sheet_date=day).one_or_none()
    if sheet and sheet.is_closed:
        raise BusinessError(
            f"День {day:%d.%m.%Y} закрито (аркуш № {sheet.number}). "
            "Записи за закритий день не змінюються."
        )
    last = last_closed_sheet()
    if last and day < last.sheet_date:
        raise BusinessError(
            f"Дата раніша за останній закритий аркуш ({last.sheet_date:%d.%m.%Y}). "
            "Проведення заднім числом заборонено."
        )
    if day > date.today():
        raise BusinessError("Касовий ордер не може бути датований майбутнім числом.")


def validate_prro(order: CashOrder):
    """Перевірки для ПКО на оприбуткування виручки ПРРО."""
    if not order.is_prro:
        return
    if order.kind != CashOrder.KIND_IN:
        raise BusinessError("Виручка ПРРО оприбутковується лише прибутковим ордером.")
    if not order.pos_id:
        raise BusinessError("Укажіть касу ПРРО.")
    if not order.z_number or order.z_number <= 0:
        raise BusinessError("Укажіть номер Z-звіту.")
    if not order.z_date:
        raise BusinessError("Укажіть дату Z-звіту.")
    if order.z_date != order.doc_date:
        raise BusinessError(
            "Дата ордера має збігатися з датою Z-звіту: готівка оприбутковується "
            "в день її фактичного одержання (п. 11 Положення № 148)."
        )
    dup = CashOrder.query.filter(
        CashOrder.pos_id == order.pos_id,
        CashOrder.z_number == order.z_number,
        CashOrder.status != CashOrder.CANCELLED,
        CashOrder.id != (order.id or -1),
    ).first()
    if dup:
        raise BusinessError(
            f"Z-звіт № {order.z_number} за цією касою вже оприбуткований "
            f"ордером № {dup.number_str} від {dup.doc_date:%d.%m.%Y}."
        )


def last_z_number(pos_id: int, before_date: date = None) -> int | None:
    """Останній оприбуткований номер Z-звіту за касою."""
    q = CashOrder.query.filter(
        CashOrder.pos_id == pos_id,
        CashOrder.status == CashOrder.POSTED,
        CashOrder.z_number.isnot(None),
    )
    if before_date:
        q = q.filter(CashOrder.doc_date < before_date)
    row = q.order_by(CashOrder.z_number.desc()).first()
    return row.z_number if row else None


# Розрив, більший за цю величину, майже напевно означає не пропущені
# звіти, а зміну схеми нумерації: наприклад, замість порядкового номера
# Z-звіту введено його фіскальний номер. Перелічувати такі «пропуски»
# безглуздо, тому про них повідомляється окремо.
MAX_REASONABLE_GAP = 500

# Скільки номерів показувати переліком, перш ніж згортати в діапазон
MAX_LISTED_NUMBERS = 10


def _describe_gap(low: int, high: int) -> str:
    """Опис проміжку між номерами low і high, не включно.

    Номери НЕ матеріалізуються в список: проміжок може бути в мільйони
    значень, і спроба перелічити їх вичерпує пам'ять сервера.
    """
    count = high - low - 1
    if count <= 0:
        return ""
    if count <= MAX_LISTED_NUMBERS:
        return ", ".join(f"№ {n}" for n in range(low + 1, high))
    return f"№ {low + 1} … № {high - 1} (разом {count})"


def check_z_sequence(day: date) -> list:
    """Розриви в нумерації Z-звітів на дату.

    Кожен Z-звіт обнуляє підсумки реєстратора, тому пропущений номер майже
    завжди означає невідображену в касовій книзі виручку. Перевірка
    попереджувальна: вона не блокує закриття дня, бо розрив може бути
    поясненним (перший день роботи в програмі, анульований ордер).
    """
    problems = []
    for pos in PosTerminal.query.filter_by(is_active=True):
        # Для фіскальних номерів розриви не рахуються: їх присвоює сервер
        # ДПС, і в межах однієї каси вони не йдуть поспіль.
        if not pos.z_sequential:
            continue
        todays = [o.z_number for o in CashOrder.query.filter(
            CashOrder.pos_id == pos.id,
            CashOrder.doc_date == day,
            CashOrder.status == CashOrder.POSTED,
            CashOrder.z_number.isnot(None),
        ).order_by(CashOrder.z_number)]
        if not todays:
            continue

        prev = last_z_number(pos.id, before_date=day)

        # Пари «попередній номер — наступний номер», між якими шукаємо розрив.
        bounds = []
        if prev is not None:
            bounds.append((prev, todays[0]))
        bounds += list(zip(todays, todays[1:]))

        gaps = [(lo, hi) for lo, hi in bounds if hi - lo > 1]
        if not gaps:
            continue

        huge = [(lo, hi) for lo, hi in gaps if hi - lo - 1 > MAX_REASONABLE_GAP]
        if huge:
            lo, hi = huge[0]
            problems.append(
                f"{pos.name}: номер Z-звіту стрибнув з {lo} на {hi}. "
                "Якщо ви вносите фіскальний номер звіту, зніміть позначку "
                "«Номери Z-звітів послідовні» у картці цієї каси — тоді "
                "контроль розривів вимкнеться. Якщо ж номери мають бути "
                "порядковими, перевірте поле «№ Z-звіту» в ордерах."
            )
            continue

        details = "; ".join(t for t in (_describe_gap(lo, hi) for lo, hi in gaps) if t)
        problems.append(
            f"{pos.name}: не оприбутковано Z-звіти {details}. "
            "Перевірте, чи не залишилася виручка за ними поза касовою книгою."
        )
    return problems


def z_summary(day: date) -> list:
    """Скільки Z-звітів оприбутковано за день, за кожною касою."""
    out = []
    for pos in PosTerminal.query.order_by(PosTerminal.name):
        orders = CashOrder.query.filter(
            CashOrder.pos_id == pos.id,
            CashOrder.doc_date == day,
            CashOrder.status == CashOrder.POSTED,
        ).order_by(CashOrder.z_number).all()
        if not orders:
            continue
        out.append({
            "pos": pos,
            "count": len(orders),
            "numbers": [o.z_number for o in orders],
            "cash": sum((to_decimal(o.amount) for o in orders), ZERO),
            "card": sum((to_decimal(o.card_amount) for o in orders), ZERO),
        })
    return out


def post_order(order: CashOrder, user=None) -> CashOrder:
    """Провести ордер: перевірки -> номер -> прив'язка до аркуша дня."""
    if order.status == CashOrder.POSTED:
        raise BusinessError("Документ уже проведено.")
    if order.status == CashOrder.CANCELLED:
        raise BusinessError("Анульований документ провести неможливо.")
    if to_decimal(order.amount) <= ZERO:
        raise BusinessError("Сума має бути більшою за нуль.")

    # Перевірки читають БД; autoflush тут вимкнено, щоб недооформлений
    # документ (ще без номера) не потрапив у таблицю передчасно.
    with db.session.no_autoflush:
        validate_date_open(order.doc_date)
        validate_prro(order)

        if order.kind == CashOrder.KIND_OUT:
            available = current_balance(order.doc_date)
            if to_decimal(order.amount) > available:
                raise BusinessError(
                    f"Недостатньо готівки в касі: доступно {available} грн, "
                    f"потрібно {to_decimal(order.amount)} грн. "
                    "Від'ємний залишок у касовій книзі неможливий."
                )

        order.year = order.doc_date.year
        if not order.number:
            order.number = next_number(order.kind, order.year)
    order.status = CashOrder.POSTED
    order.posted_at = utcnow()
    if user is not None:
        # Присвоюємо об'єкт, а не user.id: у щойно доданого користувача
        # ідентифікатора ще немає, і зв'язок мовчки лишився б порожнім.
        order.posted_by = user

    with db.session.no_autoflush:
        sheet = get_or_create_sheet(order.doc_date)
    order.sheet_id = sheet.id
    db.session.flush()
    recalc_sheet(sheet)
    return order


def cancel_order(order: CashOrder, reason: str, user=None) -> CashOrder:
    if order.status == CashOrder.CANCELLED:
        raise BusinessError("Документ уже анульовано.")
    if order.sheet and order.sheet.is_closed:
        raise BusinessError(
            "Ордер увійшов до закритого аркуша касової книги. "
            "Виправлення оформлюється бухгалтерською довідкою, а не анулюванням."
        )
    if not reason or len(reason.strip()) < 3:
        raise BusinessError("Вкажіть причину анулювання.")

    sheet = order.sheet
    order.status = CashOrder.CANCELLED
    order.cancelled_at = utcnow()
    order.cancel_reason = reason.strip()
    order.sheet_id = None
    db.session.flush()
    if sheet:
        recalc_sheet(sheet)
    return order


# -------------------------------------------------------------- закриття дня

def close_day(sheet: CashBookSheet, user=None, cashier_name=None,
              accountant_name=None) -> CashBookSheet:
    if sheet.is_closed:
        raise BusinessError("День уже закрито.")
    if sheet.sheet_date > date.today():
        raise BusinessError("Неможливо закрити майбутній день.")

    drafts = CashOrder.query.filter(
        CashOrder.doc_date == sheet.sheet_date, CashOrder.status == CashOrder.DRAFT
    ).count()
    if drafts:
        raise BusinessError(
            f"За {sheet.sheet_date:%d.%m.%Y} є непроведених чернеток: {drafts}. "
            "Проведіть або видаліть їх перед закриттям дня."
        )

    recalc_sheet(sheet)
    if sheet.docs_in_count + sheet.docs_out_count == 0:
        raise BusinessError(
            "За цей день немає касових операцій — аркуш не формується "
            "і не роздруковується."
        )
    if to_decimal(sheet.closing_balance) < ZERO:
        raise BusinessError("Від'ємний залишок на кінець дня — перевірте документи.")

    earlier_open = CashBookSheet.query.filter(
        CashBookSheet.status == CashBookSheet.OPEN,
        CashBookSheet.sheet_date < sheet.sheet_date,
    ).order_by(CashBookSheet.sheet_date).first()
    if earlier_open:
        raise BusinessError(
            f"Спочатку закрийте попередній день {earlier_open.sheet_date:%d.%m.%Y}."
        )

    sheet.number = next_sheet_number(sheet.year)
    sheet.status = CashBookSheet.CLOSED
    sheet.closed_at = utcnow()
    if user is not None:
        sheet.closed_by = user
    # Касирів може бути кілька, тому за замовчуванням в аркуші фіксується
    # той, хто фактично закриває день.
    if cashier_name:
        sheet.cashier_name = cashier_name
    elif user is not None and not sheet.cashier_name:
        sheet.cashier_name = user.full_name
    if accountant_name:
        sheet.accountant_name = accountant_name

    prev = last_closed_sheet(before=sheet.sheet_date)
    sheet.prev_hash = prev.content_hash if prev else None
    db.session.flush()
    sheet.content_hash = sheet.compute_hash()
    return sheet


def reopen_day(sheet: CashBookSheet, user=None) -> CashBookSheet:
    """Відкриття дня — лише останнього закритого і лише адміністратором.
    Обов'язково фіксується в журналі аудиту."""
    last = last_closed_sheet()
    if not sheet.is_closed:
        raise BusinessError("День не закрито.")
    if last is None or last.id != sheet.id:
        raise BusinessError("Відкрити можна лише останній закритий аркуш.")
    sheet.status = CashBookSheet.OPEN
    sheet.number = None
    sheet.content_hash = None
    sheet.closed_at = None
    sheet.closed_by_id = None
    return sheet


def verify_chain(year: int) -> list:
    """Перевірка незмінності закритих аркушів за рік."""
    problems = []
    sheets = CashBookSheet.query.filter(
        CashBookSheet.year == year, CashBookSheet.status == CashBookSheet.CLOSED
    ).order_by(CashBookSheet.number).all()
    prev_hash = None
    for s in sheets:
        if s.prev_hash != prev_hash:
            problems.append(f"Аркуш № {s.number} ({s.sheet_date:%d.%m.%Y}): "
                            "розрив ланцюжка контрольних сум.")
        if s.compute_hash() != s.content_hash:
            problems.append(f"Аркуш № {s.number} ({s.sheet_date:%d.%m.%Y}): "
                            "дані змінено після закриття дня.")
        prev_hash = s.content_hash
    return problems


def limit_exceeded(sheet: CashBookSheet) -> bool:
    """Перевірка ліміту залишку готівки на кінець дня.
    Готівка на виплати, пов'язані з оплатою праці, у ліміт не включається
    протягом установленого строку (п. 18 Положення № 148)."""
    company = Company.current()
    if not company or to_decimal(company.cash_limit) <= ZERO:
        return False
    controlled = to_decimal(sheet.closing_balance) - to_decimal(sheet.salary_balance)
    return controlled > to_decimal(company.cash_limit)
