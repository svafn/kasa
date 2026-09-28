# -*- coding: utf-8 -*-
from datetime import date

from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import CloseDayForm
from app.models import CashBookSheet, CashOrder, Company
from app.pdf.book import render_book, render_sheet
from app.pdf.response import pdf_response
from app.services import cashbook as cb
from app.services.audit import log

bp = Blueprint("book", __name__, url_prefix="/book")


@bp.route("/")
@login_required
def index():
    year = request.args.get("year", date.today().year, type=int)
    sheets = (CashBookSheet.query.filter(CashBookSheet.year == year)
              .order_by(CashBookSheet.sheet_date.desc()).all())
    years = [y[0] for y in db.session.query(CashBookSheet.year)
             .distinct().order_by(CashBookSheet.year.desc())]
    return render_template("book_list.html", sheets=sheets, year=year,
                           years=years or [date.today().year])


@bp.route("/<iso_date>")
@login_required
def day(iso_date):
    try:
        d = date.fromisoformat(iso_date)
    except ValueError:
        abort(404)
    sheet = CashBookSheet.query.filter_by(sheet_date=d).one_or_none()
    if sheet is None:
        sheet = cb.get_or_create_sheet(d)
        cb.recalc_sheet(sheet)
        db.session.commit()
    elif not sheet.is_closed:
        cb.recalc_sheet(sheet)
        db.session.commit()

    orders = CashOrder.query.filter(
        CashOrder.doc_date == d, CashOrder.status != CashOrder.DRAFT
    ).order_by(CashOrder.kind.desc(), CashOrder.number).all()

    return render_template("book_day.html", sheet=sheet, orders=orders,
                           form=CloseDayForm(obj=sheet),
                           over_limit=cb.limit_exceeded(sheet),
                           z_rows=cb.z_summary(d),
                           z_problems=cb.check_z_sequence(d),
                           company=Company.current())


@bp.route("/<iso_date>/close", methods=["POST"])
@login_required
def close(iso_date):
    if not current_user.has("close"):
        abort(403)
    d = date.fromisoformat(iso_date)
    sheet = CashBookSheet.query.filter_by(sheet_date=d).one_or_none() or abort(404)
    form = CloseDayForm()
    try:
        z_problems = cb.check_z_sequence(d)
        cb.close_day(sheet, current_user, form.cashier_name.data,
                     form.accountant_name.data)
        log("day_close", "cash_book_sheet", sheet.id,
            f"аркуш № {sheet.number}, залишок {sheet.closing_balance}")
        db.session.commit()
        flash(f"День закрито. Сформовано аркуш № {sheet.number}. "
              "Роздрукуйте його у двох примірниках.", "success")
        for msg in z_problems:
            flash(msg, "warning")
    except cb.BusinessError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("book.day", iso_date=iso_date))


@bp.route("/<iso_date>/reopen", methods=["POST"])
@login_required
def reopen(iso_date):
    if not current_user.has("reopen"):
        abort(403)
    d = date.fromisoformat(iso_date)
    sheet = CashBookSheet.query.filter_by(sheet_date=d).one_or_none() or abort(404)
    try:
        num = sheet.number
        cb.reopen_day(sheet, current_user)
        log("day_reopen", "cash_book_sheet", sheet.id, f"скасовано аркуш № {num}")
        db.session.commit()
        flash("День відкрито. Дію зафіксовано в журналі аудиту.", "warning")
    except cb.BusinessError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("book.day", iso_date=iso_date))


@bp.route("/<iso_date>/pdf")
@login_required
def sheet_pdf(iso_date):
    d = date.fromisoformat(iso_date)
    sheet = CashBookSheet.query.filter_by(sheet_date=d).one_or_none() or abort(404)
    if sheet.is_closed:
        sheet.printed_count = (sheet.printed_count or 0) + 1
        log("sheet_print", "cash_book_sheet", sheet.id,
            f"друк № {sheet.printed_count}")
        db.session.commit()
    data = render_sheet(sheet, Company.current())
    return pdf_response(
        data, f"КО-4_{d:%Y-%m-%d}_аркуш-{sheet.number_str}.pdf")


@bp.route("/year/<int:year>.pdf")
@login_required
def year_pdf(year):
    """Брошура касової книги за рік із засвідчувальним написом."""
    sheets = (CashBookSheet.query
              .filter(CashBookSheet.year == year,
                      CashBookSheet.status == CashBookSheet.CLOSED)
              .order_by(CashBookSheet.number).all())
    if not sheets:
        flash("За цей рік немає закритих аркушів.", "warning")
        return redirect(url_for("book.index", year=year))
    log("book_print", "year", year, f"аркушів: {len(sheets)}")
    db.session.commit()
    data = render_book(sheets, Company.current(), year)
    return pdf_response(data, f"Касова-книга-{year}.pdf")
