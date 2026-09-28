from datetime import date, timedelta

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import CompanyForm
from app.models import AuditLog, CashBookSheet, CashOrder, Company
from app.money import to_decimal
from app.services import cashbook as cb
from app.services.audit import log

bp = Blueprint("dashboard", __name__)


@bp.route("/")
@login_required
def index():
    company = Company.current()
    today = date.today()
    balance = cb.current_balance(today)
    sheet = CashBookSheet.query.filter_by(sheet_date=today).one_or_none()
    recent = (CashOrder.query.order_by(CashOrder.doc_date.desc(),
                                       CashOrder.created_at.desc())
              .limit(10).all())
    open_days = (CashBookSheet.query
                 .filter(CashBookSheet.status == CashBookSheet.OPEN)
                 .order_by(CashBookSheet.sheet_date).all())
    drafts = CashOrder.query.filter_by(status=CashOrder.DRAFT).count()

    over_limit = False
    if company and to_decimal(company.cash_limit) > 0 and sheet:
        over_limit = cb.limit_exceeded(sheet)

    return render_template("dashboard.html", company=company, balance=balance,
                           sheet=sheet, recent=recent, open_days=open_days,
                           drafts=drafts, over_limit=over_limit, today=today)


@bp.route("/company", methods=["GET", "POST"])
@login_required
def company():
    if not current_user.has("company"):
        flash("Недостатньо прав.", "danger")
        return redirect(url_for("dashboard.index"))
    obj = Company.current()
    form = CompanyForm(obj=obj)
    if form.validate_on_submit():
        if obj is None:
            obj = Company()
            db.session.add(obj)
        form.populate_obj(obj)
        log("company_update", "company", obj.id)
        db.session.commit()
        flash("Реквізити підприємства збережено.", "success")
        return redirect(url_for("dashboard.company"))
    return render_template("company.html", form=form, company=obj)


@bp.route("/audit")
@login_required
def audit():
    if not current_user.has("audit"):
        flash("Недостатньо прав.", "danger")
        return redirect(url_for("dashboard.index"))
    rows = AuditLog.query.order_by(AuditLog.ts.desc()).limit(300).all()
    return render_template("audit.html", rows=rows)


@bp.route("/verify/<int:year>")
@login_required
def verify(year):
    problems = cb.verify_chain(year)
    if problems:
        for p in problems:
            flash(p, "danger")
    else:
        flash(f"Контроль цілісності за {year} рік пройдено: "
              "закриті аркуші не змінювалися.", "success")
    return redirect(url_for("book.index", year=year))
