# -*- coding: utf-8 -*-
"""Друковані форми КО-1 (прибутковий) і КО-2 (видатковий касовий ордер).

Формат — A4 альбомна: ліва половина — ордер, права — квитанція (для КО-1)
або відривна частина. Між ними лінія відрізу.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas

from app.money import fmt_money, to_decimal
from app.pdf.base import GREY, Form, date_blank


def _sig(company, kind):
    """(посада, ПІБ) підписанта з урахуванням відсутності головного бухгалтера."""
    return company.signatory(kind) if company else ("", "")


def _cashier(order, company):
    """Підпис касира — той працівник, який фактично провів документ."""
    if order.posted_by is not None:
        return order.posted_by.full_name
    if order.created_by is not None:
        return order.created_by.full_name
    return company.cashier if company else ""


def _sig_block(f, x, y, width, title, name, sign_w=34):
    """Рядок підпису: посада — підпис — ПІБ."""
    f.text(x, y - 5, title, size=8)
    lw = f.text_width(title, 8) + 3
    f.field(x + lw, y, sign_w, "", label="підпис")
    f.field(x + lw + sign_w + 2, y, width - lw - sign_w - 2, name,
            label="прізвище, ім'я, по батькові")


def _note(f, x, y, company, width):
    """Виноска про те, що головбуха немає за штатом."""
    if company and company.signature_note:
        for i, line in enumerate(f.wrap(company.signature_note, width, 5.5)):
            f.text(x, y + i * 3, line, size=5.5, color=GREY)
from app.services.words import amount_to_words

PAGE = landscape(A4)          # 297 x 210 мм
LEFT_X = 8
HALF_W = 132
CUT_X = 148.5
RIGHT_X = 157


def _company_header(f, x, y, company, form_code):
    f.field(x, y, 78, company.name if company else "",
            label="підприємство (установа, організація)", size=8)
    f.field(x + 80, y, 30, company.edrpou if company else "",
            label="Ідентифікаційний код ЄДРПОУ", size=8, align="c")
    f.form_code(x + HALF_W - 34, y - 8, form_code)
    return y + 6


def _amount_table(f, x, y, order, width):
    """Таблиця реквізитів: кор. рахунок / аналітика / сума / цільове призначення."""
    cw = [width * 0.28, width * 0.22, width * 0.26, width * 0.24]
    xs, ys = f.grid(x, y, cw, [9, 6])
    for i, title in enumerate([
        "Кореспондуючий рахунок, субрахунок",
        "Код аналітичного рахунку",
        "Сума, грн",
        "Код цільового призначення",
    ]):
        f.cell(xs, ys, i, 0, title, size=6.2)
    f.cell(xs, ys, 0, 1, order.corr_account_code or "", size=8)
    f.cell(xs, ys, 1, 1, order.analytic_code or "", size=8)
    f.cell(xs, ys, 2, 1, fmt_money(order.amount), size=9, bold=True)
    f.cell(xs, ys, 3, 1, order.purpose_code or "", size=8)
    return ys[-1] + 5


def _watermark(f, order):
    if order.status == order.CANCELLED:
        f.c.saveState()
        f.c.setFont("UA-Bold", 60)
        f.c.setFillGray(0.85)
        f.c.translate(PAGE[0] / 2, PAGE[1] / 2)
        f.c.rotate(30)
        f.c.drawCentredString(0, 0, "АНУЛЬОВАНО")
        f.c.restoreState()
    elif order.status == order.DRAFT:
        f.c.saveState()
        f.c.setFont("UA-Bold", 50)
        f.c.setFillGray(0.88)
        f.c.translate(PAGE[0] / 2, PAGE[1] / 2)
        f.c.rotate(30)
        f.c.drawCentredString(0, 0, "ЧЕРНЕТКА — не є документом")
        f.c.restoreState()


# ------------------------------------------------------------------- КО-1

def _ko1_order(f, x, order, company):
    y = 14
    y = _company_header(f, x, y, company, "КО-1")
    y += 6
    f.text(x + HALF_W / 2, y, "ПРИБУТКОВИЙ КАСОВИЙ ОРДЕР", size=11,
           bold=True, align="c")
    y += 6
    f.text(x, y, f"№ {order.number_str}", size=9, bold=True)
    f.text(x + HALF_W, y, f"від {date_blank(order.doc_date)}", size=9, align="r")
    y += 4

    y = _amount_table(f, x, y, order, HALF_W)

    y += 4
    f.text(x, y - 1.2, "Прийнято від", size=8)
    lw = f.text_width("Прийнято від", 8) + 2
    y = f.multiline_field(x + lw, y, HALF_W - lw, order.counterparty_text,
                          lines=1, size=8, step=7,
                          label="прізвище, ім'я, по батькові / найменування")
    y += 5
    f.text(x, y - 1.2, "Підстава:", size=8)
    lw = f.text_width("Підстава:", 8) + 2
    y = f.multiline_field(x + lw, y, HALF_W - lw, order.basis, lines=2,
                          size=8, step=7)
    y += 4

    f.text(x, y - 1.2, "Сума", size=8)
    lw = f.text_width("Сума", 8) + 2
    y = f.multiline_field(x + lw, y, HALF_W - lw,
                          amount_to_words(order.amount), lines=2, size=8,
                          step=7, label="словами")
    y += 4
    f.text(x, y - 1.2, "Додаток:", size=8)
    lw = f.text_width("Додаток:", 8) + 2
    f.multiline_field(x + lw, y, HALF_W - lw, order.appendix or "",
                      lines=1, size=8, step=7)

    # підписи — на фіксованій висоті, як на друкованому бланку
    title, name = _sig(company, "accountant")
    _sig_block(f, x, 150, HALF_W, title, name)
    _sig_block(f, x, 168, HALF_W, "Одержав касир", _cashier(order, company))
    _note(f, x, 178, company, HALF_W)


def _ko1_receipt(f, x, order, company):
    """Квитанція до прибуткового касового ордера."""
    w = HALF_W
    y = 20
    f.text(x + w / 2, y, "КВИТАНЦІЯ", size=10, bold=True, align="c")
    y += 5
    f.text(x + w / 2, y,
           f"до прибуткового касового ордера № {order.number_str} "
           f"від {date_blank(order.doc_date)}", size=8, align="c")
    y += 8

    f.field(x, y, w, company.name if company else "",
            label="підприємство (установа, організація)")
    y += 11
    f.text(x, y - 1.2, "Прийнято від", size=8)
    lw = f.text_width("Прийнято від", 8) + 2
    y = f.multiline_field(x + lw, y, w - lw, order.counterparty_text,
                          lines=1, step=7)
    y += 5
    f.text(x, y - 1.2, "Підстава:", size=8)
    lw = f.text_width("Підстава:", 8) + 2
    y = f.multiline_field(x + lw, y, w - lw, order.basis, lines=2, step=7)
    y += 4
    f.text(x, y - 1.2, "Сума", size=8)
    lw = f.text_width("Сума", 8) + 2
    y = f.multiline_field(x + lw, y, w - lw, amount_to_words(order.amount),
                          lines=2, step=7, label="словами")
    y += 8
    f.text(x, y, date_blank(order.doc_date), size=8)

    title, name = _sig(company, "accountant")
    f.text(x, 150 - 5, "М.П.", size=8)
    _sig_block(f, x + 16, 150, w - 16, title, name)
    _sig_block(f, x, 168, w, "Касир", _cashier(order, company))
    _note(f, x, 178, company, w)


# ------------------------------------------------------------------- КО-2

def _ko2_order(f, x, order, company):
    y = 14
    y = _company_header(f, x, y, company, "КО-2")
    y += 6
    f.text(x + HALF_W / 2, y, "ВИДАТКОВИЙ КАСОВИЙ ОРДЕР", size=11,
           bold=True, align="c")
    y += 6
    f.text(x, y, f"№ {order.number_str}", size=9, bold=True)
    f.text(x + HALF_W, y, f"від {date_blank(order.doc_date)}", size=9, align="r")
    y += 4

    y = _amount_table(f, x, y, order, HALF_W)

    y += 4
    f.text(x, y - 1.2, "Видати", size=8)
    lw = f.text_width("Видати", 8) + 2
    y = f.multiline_field(x + lw, y, HALF_W - lw, order.counterparty_text,
                          lines=1, step=7, label="прізвище, ім'я, по батькові")
    y += 5
    f.text(x, y - 1.2, "Підстава:", size=8)
    lw = f.text_width("Підстава:", 8) + 2
    y = f.multiline_field(x + lw, y, HALF_W - lw, order.basis, lines=2, step=7)
    y += 4
    f.text(x, y - 1.2, "Сума", size=8)
    lw = f.text_width("Сума", 8) + 2
    y = f.multiline_field(x + lw, y, HALF_W - lw, amount_to_words(order.amount),
                          lines=2, step=7, label="словами")
    y += 4
    f.text(x, y - 1.2, "Додаток:", size=8)
    lw = f.text_width("Додаток:", 8) + 2
    f.multiline_field(x + lw, y, HALF_W - lw, order.appendix or "",
                      lines=1, step=7)

    d_title, d_name = _sig(company, "director")
    a_title, a_name = _sig(company, "accountant")

    if company and company.accountant_is_director:
        # Головбуха немає за штатом: обидва підписи ставить керівник, тому
        # друкується один рядок підпису і пояснювальна виноска.
        _sig_block(f, x, 150, HALF_W, d_title, d_name)
        _note(f, x, 160, company, HALF_W)
    else:
        _sig_block(f, x, 150, HALF_W, d_title, d_name)
        _sig_block(f, x, 168, HALF_W, a_title, a_name)
        _note(f, x, 178, company, HALF_W)


def _ko2_receipt(f, x, order, company):
    """Права частина ВКО: розписка одержувача та відмітка касира."""
    w = HALF_W
    y = 22
    f.text(x + w / 2, y, "РОЗПИСКА ОДЕРЖУВАЧА", size=10, bold=True, align="c")
    y += 5
    f.text(x + w / 2, y,
           f"до видаткового касового ордера № {order.number_str} "
           f"від {date_blank(order.doc_date)}", size=8, align="c")
    y += 10

    hrn, kop = divmod(int(to_decimal(order.amount) * 100), 100)
    f.text(x, y - 1.2, "Одержав", size=8)
    f.field(x + 16, y, 30, str(hrn), align="c")
    f.text(x + 47, y - 1.2, "грн", size=8)
    f.field(x + 56, y, 16, f"{kop:02d}", align="c")
    f.text(x + 73, y - 1.2, "коп.", size=8)
    y += 11
    y = f.multiline_field(x, y, w, amount_to_words(order.amount), lines=2, step=7,
                          label="сума словами, вписується одержувачем власноруч")
    y += 9
    f.text(x, y, date_blank(order.doc_date), size=8)
    f.field(x + 60, y, w - 60, "", label="підпис одержувача")
    y += 16

    f.text(x, y - 1.2, "За", size=8)
    f.multiline_field(
        x + 6, y, w - 6, order.id_document or "", lines=2, step=7,
        label="назва, номер, дата та місце видачі документа, що засвідчує особу одержувача")

    _sig_block(f, x, 168, w, "Видав касир", _cashier(order, company))


# ---------------------------------------------------------------- публічне API

def render_order(order, company) -> bytes:
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=PAGE)
    c.setTitle(f"{order.form_code} № {order.number_str} від {order.doc_date:%d.%m.%Y}")
    f = Form(c, *PAGE)

    if order.kind == order.KIND_IN:
        _ko1_order(f, LEFT_X, order, company)
        _ko1_receipt(f, RIGHT_X, order, company)
    else:
        _ko2_order(f, LEFT_X, order, company)
        _ko2_receipt(f, RIGHT_X, order, company)

    f.cut_line(CUT_X, 8, 202)
    _watermark(f, order)
    c.showPage()
    c.save()
    return buf.getvalue()


def render_orders_batch(orders, company) -> bytes:
    """Пакетний друк кількох ордерів в один PDF."""
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=PAGE)
    c.setTitle("Касові ордери")
    for order in orders:
        f = Form(c, *PAGE)
        if order.kind == order.KIND_IN:
            _ko1_order(f, LEFT_X, order, company)
            _ko1_receipt(f, RIGHT_X, order, company)
        else:
            _ko2_order(f, LEFT_X, order, company)
            _ko2_receipt(f, RIGHT_X, order, company)
        f.cut_line(CUT_X, 8, 202)
        _watermark(f, order)
        c.showPage()
    c.save()
    return buf.getvalue()
