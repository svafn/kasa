from datetime import date

from flask import Flask, render_template

from app.extensions import csrf, db, login_manager, migrate
from app.money import fmt_money
from app.services.words import amount_to_words


def create_app(config_object="config.Config", **overrides):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object)
    # Перевизначення застосовуємо ДО init_app: Flask-SQLAlchemy створює
    # engine саме там, і пізніша зміна URI вже не подіє.
    app.config.update(overrides)

    # Кирилиця в JSON-даних для шаблонів має лишатися читабельною,
    # а не перетворюватися на \uXXXX.
    app.json.ensure_ascii = False

    db.init_app(app)
    migrate.init_app(app, db, render_as_batch=True)   # batch -> ALTER TABLE у SQLite
    login_manager.init_app(app)
    csrf.init_app(app)

    from app import models  # noqa: F401  (реєстрація моделей)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(models.User, int(user_id))

    from app.blueprints.auth import bp as auth_bp
    from app.blueprints.dashboard import bp as dash_bp
    from app.blueprints.orders import bp as orders_bp
    from app.blueprints.book import bp as book_bp
    from app.blueprints.dicts import bp as dicts_bp

    for bp in (auth_bp, dash_bp, orders_bp, book_bp, dicts_bp):
        app.register_blueprint(bp)

    from app.cli import register_cli
    register_cli(app)

    # --- фільтри шаблонів
    app.jinja_env.filters["money"] = fmt_money
    app.jinja_env.filters["words"] = amount_to_words
    app.jinja_env.filters["d"] = lambda v: v.strftime("%d.%m.%Y") if v else ""
    app.jinja_env.filters["dt"] = lambda v: v.strftime("%d.%m.%Y %H:%M") if v else ""

    @app.context_processor
    def inject_globals():
        return {"today": date.today(), "Company": models.Company}

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404,
                               msg="Сторінку не знайдено"), 404

    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403,
                               msg="Недостатньо прав"), 403

    # Відсутній шрифт — не збій програми, а незавершене налаштування
    # сервера. Показуємо, що саме встановити, замість голої сторінки 500.
    from app.pdf.base import FontsNotFound

    @app.errorhandler(FontsNotFound)
    def fonts_missing(e):
        app.logger.error("PDF не сформовано: %s", e)
        return render_template("error.html", code=500,
                               title="Не налаштовано шрифт для PDF",
                               msg=str(e)), 500

    @app.errorhandler(500)
    @app.errorhandler(Exception)
    def internal_error(e):
        # Наскрізні винятки HTTP (404, 403 тощо) обробляються вище
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e
        db.session.rollback()
        app.logger.exception("Необроблена помилка")
        # Під час налагодження й у тестах виняток має долітати незмінним:
        # інакше справжня вада виглядає як звичайна сторінка помилки
        # і залишається непоміченою.
        if app.testing or app.debug:
            raise e
        return render_template(
            "error.html", code=500,
            title="Внутрішня помилка",
            msg="Дію не виконано. Подробиці записано в журнал сервера "
                "(logs/kasa.log). Якщо помилка повторюється — надішліть "
                "останні рядки журналу розробнику."), 500

    return app
