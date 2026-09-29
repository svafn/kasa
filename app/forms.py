# -*- coding: utf-8 -*-
from decimal import Decimal, InvalidOperation

from flask_wtf import FlaskForm
from wtforms import (BooleanField, DateField, DecimalField, IntegerField,
                     PasswordField, SelectField, StringField, SubmitField,
                     TextAreaField)
from wtforms.validators import DataRequired, Length, NumberRange, Optional


class LoginForm(FlaskForm):
    username = StringField("Логін", validators=[DataRequired()])
    password = PasswordField("Пароль", validators=[DataRequired()])
    submit = SubmitField("Увійти")


class OrderForm(FlaskForm):
    doc_date = DateField("Дата документа", validators=[DataRequired()])
    amount = DecimalField("Сума, грн", places=2,
                          validators=[DataRequired(),
                                      NumberRange(min=Decimal("0.01"),
                                                  message="Сума має бути > 0")])
    source = SelectField("Джерело надходження", choices=[
        ("general", "Звичайне надходження"),
        ("prro", "Виручка за Z-звітом ПРРО")], default="general")
    pos_id = SelectField("Каса ПРРО", coerce=int, validators=[Optional()])
    z_number = IntegerField("№ Z-звіту", validators=[Optional(),
                                                    NumberRange(min=1)])
    z_date = DateField("Дата Z-звіту", validators=[Optional()])
    card_amount = DecimalField("У т. ч. безготівкові за цим Z, грн (довідково)",
                               places=2, validators=[Optional(),
                                                     NumberRange(min=0)])

    counterparty_id = SelectField("Контрагент з довідника (необов'язково)",
                                  coerce=int, validators=[Optional()])
    # Назва підставляється у вигляді, залежно від виду ордера:
    # «Прийнято від» для КО-1, «Видати» для КО-2 (див. _tune_labels).
    counterparty_text = StringField("Прийнято від",
                                    validators=[DataRequired(), Length(max=255)])
    basis = TextAreaField("Підстава", validators=[Optional(), Length(max=1000)])
    appendix = TextAreaField("Додаток", validators=[Optional(), Length(max=1000)])
    id_document = StringField("Документ, що засвідчує особу",
                              validators=[Optional(), Length(max=255)])
    corr_account_id = SelectField("Кореспондуючий рахунок", coerce=int,
                                  validators=[Optional()])
    analytic_code = StringField("Код аналітичного рахунку",
                                validators=[Optional(), Length(max=20)])
    purpose_code = StringField("Код цільового призначення",
                               validators=[Optional(), Length(max=10)])
    is_salary = BooleanField("Виплати, пов'язані з оплатою праці")
    submit = SubmitField("Зберегти")
    submit_post = SubmitField("Зберегти і провести")


class PosForm(FlaskForm):
    name = StringField("Назва каси", validators=[DataRequired(), Length(max=150)])
    fiscal_number = StringField("Фіскальний номер ПРРО",
                                validators=[DataRequired(), Length(max=20)])
    location = StringField("Господарська одиниця / адреса",
                           validators=[Optional(), Length(max=255)])
    z_sequential = BooleanField(
        "Номери Z-звітів послідовні (порядковий номер зміни)", default=True)
    is_active = BooleanField("Активна", default=True)
    submit = SubmitField("Зберегти")


class CancelForm(FlaskForm):
    reason = StringField("Причина анулювання",
                         validators=[DataRequired(), Length(min=3, max=255)])
    submit = SubmitField("Анулювати")


class CloseDayForm(FlaskForm):
    cashier_name = StringField("Касир", validators=[Optional(), Length(max=150)])
    accountant_name = StringField("Бухгалтер", validators=[Optional(), Length(max=150)])
    submit = SubmitField("Закрити день")


class CompanyForm(FlaskForm):
    name = StringField("Найменування", validators=[DataRequired(), Length(max=255)])
    edrpou = StringField("Код за ЄДРПОУ", validators=[DataRequired(), Length(max=10)])
    address = StringField("Адреса", validators=[Optional(), Length(max=255)])
    subdivision = StringField("Відокремлений підрозділ",
                              validators=[Optional(), Length(max=255)])
    director = StringField("Керівник (ПІБ)", validators=[Optional(), Length(max=150)])
    director_title = StringField("Посада керівника",
                                 validators=[Optional(), Length(max=100)])
    has_chief_accountant = BooleanField(
        "Посада головного бухгалтера передбачена штатним розписом")
    chief_accountant = StringField("Головний бухгалтер (ПІБ)",
                                   validators=[Optional(), Length(max=150)])
    accountant_title = StringField(
        "Посада особи, що підписує замість головного бухгалтера",
        validators=[Optional(), Length(max=100)])
    accountant_name = StringField(
        "ПІБ уповноваженої особи (порожньо — підписує керівник)",
        validators=[Optional(), Length(max=150)])
    authorization_order = StringField(
        "Наказ про уповноваження на підписання касових документів",
        validators=[Optional(), Length(max=255)])
    cashier = StringField("Касир за замовчуванням (ПІБ)",
                          validators=[Optional(), Length(max=150)])
    cashier_order = StringField(
        "Наказ / договір про повну матеріальну відповідальність касира",
        validators=[Optional(), Length(max=255)])
    cash_limit = DecimalField("Ліміт залишку готівки, грн", places=2,
                              validators=[Optional(), NumberRange(min=0)])
    limit_order = StringField("Наказ про встановлення ліміту",
                              validators=[Optional(), Length(max=255)])
    submit = SubmitField("Зберегти")


class CounterpartyForm(FlaskForm):
    name = StringField("Найменування / ПІБ", validators=[DataRequired(), Length(max=255)])
    kind = SelectField("Тип", choices=[("person", "Фізична особа"),
                                       ("company", "Юридична особа")])
    code = StringField("ЄДРПОУ / РНОКПП", validators=[Optional(), Length(max=12)])
    id_document = StringField("Документ, що засвідчує особу",
                              validators=[Optional(), Length(max=255)])
    note = StringField("Примітка", validators=[Optional(), Length(max=255)])
    is_active = BooleanField("Активний", default=True)
    submit = SubmitField("Зберегти")


class AccountForm(FlaskForm):
    code = StringField("Рахунок / субрахунок",
                       validators=[DataRequired(), Length(max=10)])
    name = StringField("Назва", validators=[DataRequired(), Length(max=255)])
    is_active = BooleanField("Активний", default=True)
    submit = SubmitField("Зберегти")


class UserForm(FlaskForm):
    username = StringField("Логін", validators=[DataRequired(), Length(max=64)])
    full_name = StringField("ПІБ", validators=[DataRequired(), Length(max=150)])
    role = SelectField("Роль", choices=[
        ("admin", "Адміністратор — усі права, зокрема користувачі"),
        ("director", "Директор — усі касові операції, довідники, відкриття дня"),
        ("senior_cashier", "Старший касир — касові операції, закриття дня, довідники"),
        ("cashier", "Касир — оформлення й проведення ордерів, закриття дня"),
        ("accountant", "Бухгалтер — ордери, довідники, реквізити"),
        ("viewer", "Перегляд — лише читання і друк")])
    position = StringField("Посада (для друку у формах)",
                           validators=[Optional(), Length(max=100)])
    password = PasswordField("Пароль", validators=[Optional(), Length(min=8)])
    is_enabled = BooleanField("Активний", default=True)
    submit = SubmitField("Зберегти")
