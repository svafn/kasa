# -*- coding: utf-8 -*-
from flask import (Blueprint, abort, flash, redirect, render_template, url_for)
from flask_login import current_user, login_required

from app.extensions import db
from app.forms import AccountForm, CounterpartyForm, PosForm, UserForm
from app.models import Account, Counterparty, PosTerminal, User
from app.services.audit import log

bp = Blueprint("dicts", __name__, url_prefix="/dicts")


@bp.route("/counterparties")
@login_required
def counterparties():
    items = Counterparty.query.order_by(Counterparty.name).all()
    return render_template("dict_counterparties.html", items=items)


@bp.route("/counterparties/new", methods=["GET", "POST"])
@bp.route("/counterparties/<int:item_id>", methods=["GET", "POST"])
@login_required
def counterparty_edit(item_id=None):
    if not current_user.has("dicts"):
        abort(403)
    item = db.get_or_404(Counterparty, item_id) if item_id else None
    form = CounterpartyForm(obj=item)
    if form.validate_on_submit():
        if item is None:
            item = Counterparty()
            db.session.add(item)
        form.populate_obj(item)
        log("counterparty_save", "counterparty", item.id, item.name)
        db.session.commit()
        flash("Збережено.", "success")
        return redirect(url_for("dicts.counterparties"))
    return render_template("dict_form.html", form=form,
                           title="Контрагент / підзвітна особа")


@bp.route("/accounts")
@login_required
def accounts():
    items = Account.query.order_by(Account.code).all()
    return render_template("dict_accounts.html", items=items)


@bp.route("/accounts/new", methods=["GET", "POST"])
@bp.route("/accounts/<int:item_id>", methods=["GET", "POST"])
@login_required
def account_edit(item_id=None):
    if not current_user.has("dicts"):
        abort(403)
    item = db.get_or_404(Account, item_id) if item_id else None
    form = AccountForm(obj=item)
    if form.validate_on_submit():
        if item is None:
            item = Account()
            db.session.add(item)
        form.populate_obj(item)
        log("account_save", "account", item.id, item.code)
        db.session.commit()
        flash("Збережено.", "success")
        return redirect(url_for("dicts.accounts"))
    return render_template("dict_form.html", form=form, title="Рахунок")


@bp.route("/pos")
@login_required
def pos_list():
    items = PosTerminal.query.order_by(PosTerminal.name).all()
    return render_template("dict_pos.html", items=items)


@bp.route("/pos/new", methods=["GET", "POST"])
@bp.route("/pos/<int:item_id>", methods=["GET", "POST"])
@login_required
def pos_edit(item_id=None):
    if not current_user.has("dicts"):
        abort(403)
    item = db.get_or_404(PosTerminal, item_id) if item_id else None
    form = PosForm(obj=item)
    if form.validate_on_submit():
        if item is None:
            item = PosTerminal()
            db.session.add(item)
        form.populate_obj(item)
        log("pos_save", "pos_terminal", item.id, item.fiscal_number)
        db.session.commit()
        flash("Збережено.", "success")
        return redirect(url_for("dicts.pos_list"))
    return render_template("dict_form.html", form=form, title="Каса ПРРО")


@bp.route("/users")
@login_required
def users():
    if not current_user.has("users"):
        abort(403)
    return render_template("dict_users.html", items=User.query.order_by(User.username))


@bp.route("/users/new", methods=["GET", "POST"])
@bp.route("/users/<int:item_id>", methods=["GET", "POST"])
@login_required
def user_edit(item_id=None):
    if not current_user.has("users"):
        abort(403)
    item = db.get_or_404(User, item_id) if item_id else None
    form = UserForm(obj=item)
    if form.validate_on_submit():
        if item is None:
            item = User()
            db.session.add(item)
            if not form.password.data:
                flash("Для нового користувача потрібен пароль (мін. 8 символів).",
                      "danger")
                return render_template("dict_form.html", form=form,
                                       title="Користувач")
        item.username = form.username.data.strip()
        item.full_name = form.full_name.data.strip()
        item.role = form.role.data
        item.position = (form.position.data or '').strip()
        item.is_enabled = form.is_enabled.data
        if form.password.data:
            item.set_password(form.password.data)
        log("user_save", "user", item.id, item.username)
        db.session.commit()
        flash("Збережено.", "success")
        return redirect(url_for("dicts.users"))
    return render_template("dict_form.html", form=form, title="Користувач")
