# -*- coding: utf-8 -*-
from datetime import date

from flask import (Blueprint, Response, abort, flash, redirect,
                   render_template, request, url_for)
from flask_login import current_user, login_required
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.forms import CancelForm, OrderForm
from app.models import Account, CashOrder, Company, Counterparty, PosTerminal
from app.pdf.orders import render_order, render_orders_batch
from app.pdf.response import pdf_response
from app.pdf.book import render_journal
from app.services import cashbook as cb
from app.services.audit import log

bp = Blueprint("orders", __name__, url_prefix="/orders")

KINDS = {"in": ("Прибуткові касові ордери (КО-1)", CashOrder.KIND_IN),
         "out": ("Видаткові касові ордери (КО-2)", CashOrder.KIND_OUT)}


def _fill_choices(form):
    counterparties = (Counterparty.query.filter_by(is_active=True)
                      .order_by(Counterparty.name).all())
    form.counterparty_id.choices = [(0, "— вручну —")] + [
        (c.id, f"{c.name}" + (f" ({c.code})" if c.code else ""))
        for c in counterparties
    ]
    form.pos_id.choices = [(0, "—")] + [
        (p.id, str(p)) for p in PosTerminal.query.filter_by(is_active=True)
        .order_by(PosTerminal.name)
    ]
    form.corr_account_id.choices = [(0, "—")] + [
        (a.id, f"{a.code} — {a.name}")
        for a in Account.query.filter_by(is_active=True).order_by(Account.code)
    ]
    # Документи, що засвідчують особу, — для підстановки у формі без перезавантаження
    return {str(c.id): (c.id_document or "") for c in counterparties}


def _tune_labels(form, kind):
    """Назви реквізитів мають збігатися з графами бланка КО-1 / КО-2."""
    is_in = kind == "in"
    form.counterparty_text.label.text = "Прийнято від" if is_in else "Видати"
    form.basis.label.text = "Підстава"
    form.amount.label.text = "Сума, грн"
    if not is_in:
        form.counterparty_id.label.text = "Одержувач з довідника (необов'язково)"


def _require(*roles):
    if not current_user.has(*roles):
        abort(403)


@bp.route("/")
@login_required
def index():
    kind = request.args.get("kind")
    status = request.args.get("status")
    df = request.args.get("from")
    dt = request.args.get("to")

    q = CashOrder.query
    if kind in ("in", "out"):
        q = q.filter(CashOrder.kind == kind)
    if status:
        q = q.filter(CashOrder.status == status)
    if df:
        q = q.filter(CashOrder.doc_date >= date.fromisoformat(df))
    if dt:
        q = q.filter(CashOrder.doc_date <= date.fromisoformat(dt))

    page = request.args.get("page", 1, type=int)
    pagination = q.order_by(CashOrder.doc_date.desc(), CashOrder.kind,
                            CashOrder.number.desc()).paginate(page=page, per_page=50)
    return render_template("orders_list.html", pagination=pagination,
                           kind=kind, status=status, df=df, dt=dt)


@bp.route("/new/<kind>", methods=["GET", "POST"])
@login_required
def create(kind):
    _require("orders")
    if kind not in KINDS:
        abort(404)
    title, kind_code = KINDS[kind]

    form = OrderForm()
    cp_docs = _fill_choices(form)
    _tune_labels(form, kind)
    if request.method == "GET":
        form.doc_date.data = date.today()

    if form.validate_on_submit():
        order = CashOrder(kind=kind_code, year=form.doc_date.data.year,
                          created_by_id=current_user.id)
        _apply(form, order)
        db.session.add(order)
        try:
            # Перевірки читають базу, а отже викликають autoflush. Без цієї
            # обгортки ще не перевірений документ потрапив би в таблицю, і
            # замість зрозумілого повідомлення користувач побачив би
            # помилку унікального обмеження від СУБД.
            with db.session.no_autoflush:
                if not order.basis:
                    raise cb.BusinessError("Заповніть підставу.")
                cb.validate_date_open(order.doc_date)
                cb.validate_prro(order)
            if form.submit_post.data:
                cb.post_order(order, current_user)
                log("order_post", "cash_order", order.id,
                    f"{order.form_code} № {order.number} на {order.amount}")
                flash(f"{order.form_code} № {order.number} проведено.", "success")
            else:
                log("order_create", "cash_order", order.id)
                flash("Чернетку збережено.", "info")
            db.session.commit()
            return redirect(url_for("orders.view", order_id=order.id))
        except cb.BusinessError as e:
            db.session.rollback()
            flash(str(e), "danger")
        except IntegrityError as e:
            db.session.rollback()
            flash(cb.friendly_integrity_error(e), "danger")

    return render_template("order_form.html", form=form, kind=kind,
                           title=title, order=None, cp_docs=cp_docs)


@bp.route("/<int:order_id>/edit", methods=["GET", "POST"])
@login_required
def edit(order_id):
    _require("orders")
    order = db.get_or_404(CashOrder, order_id)
    if not order.is_editable:
        flash("Виправлення в проведених касових ордерах не допускаються "
              "(п. 26 Положення № 148).", "warning")
        return redirect(url_for("orders.view", order_id=order.id))

    kind = "in" if order.kind == CashOrder.KIND_IN else "out"
    form = OrderForm(obj=order)
    cp_docs = _fill_choices(form)
    _tune_labels(form, kind)
    if form.validate_on_submit():
        _apply(form, order)
        try:
            with db.session.no_autoflush:
                if not order.basis:
                    raise cb.BusinessError("Заповніть підставу.")
                cb.validate_prro(order)
            if form.submit_post.data:
                cb.post_order(order, current_user)
                log("order_post", "cash_order", order.id)
                flash(f"{order.form_code} № {order.number} проведено.", "success")
            else:
                log("order_update", "cash_order", order.id)
                flash("Збережено.", "info")
            db.session.commit()
            return redirect(url_for("orders.view", order_id=order.id))
        except cb.BusinessError as e:
            db.session.rollback()
            flash(str(e), "danger")
        except IntegrityError as e:
            db.session.rollback()
            flash(cb.friendly_integrity_error(e), "danger")

    return render_template("order_form.html", form=form, kind=kind,
                           title=order.title, order=order, cp_docs=cp_docs)


def _apply(form, order):
    order.doc_date = form.doc_date.data
    order.year = form.doc_date.data.year
    order.amount = form.amount.data
    order.counterparty_id = form.counterparty_id.data or None
    order.counterparty_text = form.counterparty_text.data.strip()
    order.basis = form.basis.data.strip()
    order.appendix = (form.appendix.data or "").strip()
    order.id_document = (form.id_document.data or "").strip()
    order.corr_account_id = form.corr_account_id.data or None
    if order.corr_account_id:
        acc = db.session.get(Account, order.corr_account_id)
        order.corr_account_code = acc.code if acc else None
    else:
        order.corr_account_code = None
    order.analytic_code = (form.analytic_code.data or "").strip()
    order.purpose_code = (form.purpose_code.data or "").strip()
    order.is_salary = bool(form.is_salary.data)

    # --- виручка ПРРО
    order.source = form.source.data if order.kind == CashOrder.KIND_IN else "general"
    if order.is_prro:
        # Заповнюємо і зв'язок, і зовнішній ключ. Об'єкт потрібен, щоб у
        # згенерованій підставі був фіскальний номер ПРРО; ключ — щоб
        # перевірки бачили касу ще до запису в базу (вони виконуються
        # з вимкненим autoflush, а зв'язок синхронізує ключ лише під час
        # запису).
        terminal = (db.session.get(PosTerminal, form.pos_id.data)
                    if form.pos_id.data else None)
        order.pos = terminal
        order.pos_id = terminal.id if terminal else None
        order.z_number = form.z_number.data
        order.z_date = form.z_date.data or form.doc_date.data
        order.card_amount = form.card_amount.data
        if not order.basis and order.z_number and order.z_date:
            # Стандартне формулювання підстави підставляється автоматично,
            # але залишається доступним для редагування.
            order.basis = order.build_basis()
    else:
        order.pos = None
        order.pos_id = None
        order.z_number = None
        order.z_date = None
        order.card_amount = None

    # Документ, що засвідчує особу, підтягуємо з картки контрагента:
    # у ВКО це обов'язковий реквізит, на якому найчастіше помиляються.
    if not order.id_document and order.counterparty_id:
        cp = db.session.get(Counterparty, order.counterparty_id)
        if cp and cp.id_document:
            order.id_document = cp.id_document


@bp.route("/<int:order_id>")
@login_required
def view(order_id):
    order = db.get_or_404(CashOrder, order_id)
    return render_template("order_view.html", order=order,
                           cancel_form=CancelForm())


@bp.route("/<int:order_id>/post", methods=["POST"])
@login_required
def post(order_id):
    _require("orders")
    order = db.get_or_404(CashOrder, order_id)
    try:
        cb.post_order(order, current_user)
        log("order_post", "cash_order", order.id)
        db.session.commit()
        flash(f"{order.form_code} № {order.number} проведено.", "success")
    except cb.BusinessError as e:
        db.session.rollback()
        flash(str(e), "danger")
    return redirect(url_for("orders.view", order_id=order_id))


@bp.route("/<int:order_id>/cancel", methods=["POST"])
@login_required
def cancel(order_id):
    _require("orders")
    order = db.get_or_404(CashOrder, order_id)
    form = CancelForm()
    if form.validate_on_submit():
        try:
            cb.cancel_order(order, form.reason.data, current_user)
            log("order_cancel", "cash_order", order.id, form.reason.data)
            db.session.commit()
            flash("Документ анульовано. Номер зберігається за ним.", "warning")
        except cb.BusinessError as e:
            db.session.rollback()
            flash(str(e), "danger")
    return redirect(url_for("orders.view", order_id=order_id))


@bp.route("/<int:order_id>/delete", methods=["POST"])
@login_required
def delete(order_id):
    _require("orders")
    order = db.get_or_404(CashOrder, order_id)
    if order.status != CashOrder.DRAFT:
        flash("Видаляти можна лише непроведені чернетки.", "danger")
        return redirect(url_for("orders.view", order_id=order_id))
    log("order_delete", "cash_order", order.id, f"{order.counterparty_text}")
    db.session.delete(order)
    db.session.commit()
    flash("Чернетку видалено.", "info")
    return redirect(url_for("orders.index"))


@bp.route("/<int:order_id>/pdf")
@login_required
def pdf(order_id):
    order = db.get_or_404(CashOrder, order_id)
    data = render_order(order, Company.current())
    return pdf_response(
        data,
        f"{order.form_code}_{order.number_str}_{order.doc_date:%Y-%m-%d}.pdf")


@bp.route("/journal.pdf")
@login_required
def journal_pdf():
    """Журнал реєстрації прибуткових і видаткових касових документів (КО-3)."""
    df = date.fromisoformat(request.args.get("from", date.today().replace(
        month=1, day=1).isoformat()))
    dt = date.fromisoformat(request.args.get("to", date.today().isoformat()))
    orders = CashOrder.query.filter(
        CashOrder.doc_date >= df, CashOrder.doc_date <= dt,
        CashOrder.status != CashOrder.DRAFT,
    ).all()
    data = render_journal(orders, Company.current(), df, dt)
    return pdf_response(data, f"КО-3_{df}_{dt}.pdf")
