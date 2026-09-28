from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.extensions import db
from app.forms import LoginForm
from app.models import User, utcnow
from app.services.audit import log

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data.strip()).first()
        if user and user.is_enabled and user.check_password(form.password.data):
            login_user(user)
            user.last_login_at = utcnow()
            log("login", "user", user.id)
            db.session.commit()
            return redirect(request.args.get("next") or url_for("dashboard.index"))
        flash("Невірний логін або пароль.", "danger")
        log("login_failed", "user", details=form.username.data)
        db.session.commit()
    return render_template("login.html", form=form)


@bp.route("/logout")
@login_required
def logout():
    log("logout", "user", current_user.id)
    db.session.commit()
    logout_user()
    return redirect(url_for("auth.login"))
