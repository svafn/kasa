# -*- coding: utf-8 -*-
"""Друковані форми КО-4 (касова книга) і КО-3 (журнал реєстрації).

п. 41 Положення № 148: програма має забезпечувати відображення і
роздрукування «Вкладного аркуша касової книги» та «Звіту касира», які за
формою і змістом відтворюють форму касової книги. Тому на аркуші A4
(альбомна) друкуються дві однакові за змістом половини з лінією відрізу.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4, landscape
from reportlab.pdfgen import canvas as rl_canvas

from app.models import CashOrder
from app.money import ZERO, fmt_money, to_decimal
from app.pdf.base import GREY, Form, date_blank

PAGE = landscape(A4)
LEFT_X, RIGHT_X, CUT_X = 8, 157, 148.5
HALF_W = 132
COLS = [16, 52, 22, 21, 21]          # разом 132 мм
ROW_H = 5.2
ROWS_PER_PAGE = 18


def _entries_of(sheet):
    """Записи аркуша в порядку: спочатку прибуткові, потім видаткові."""
    orders = [o for o in sheet.orders if o.status == CashOrder.POSTED]
    orders.sort(key=lambda o: (0 if o.kind == CashOrder.KIND_IN else 1, o.number))
    rows = []
    for o in orders:
        rows.append({
            "num": o.number_str,
            "who": o.counterparty_text,
            "acc": o.corr_account_code or "",
            "inc": to_decimal(o.amount) if o.kind == CashOrder.KIND_IN else None,
            "out": to_decimal(o.amount) if o.kind == CashOrder.KIND_OUT else None,
        })
    return rows


def _half(f, x, sheet, company, rows, page_no, pages_total, is_report,
          carried=(ZERO, ZERO)):
    """Малює одну половину аркуша: вкладний аркуш або звіт касира."""
    d = sheet.sheet_date
    y = 11
    f.field(x, y, 84, company.name if company else "",
            label="підприємство (установа, організація)", size=8)
    f.field(x + 86, y, 26, company.edrpou if company else "",
            label="Ідентифікаційний код ЄДРПОУ", size=7, align="c")
    f.text(x + HALF_W, y - 4, "Типова форма № КО-4", size=6, align="r")

    y = 22
    f.text(x + HALF_W / 2, y,
           "ЗВІТ КАСИРА" if is_report else "ВКЛАДНИЙ АРКУШ КАСОВОЇ КНИГИ",
           size=10, bold=True, align="c")
    y += 6
    f.text(x, y, f"Каса за {date_blank(d)}", size=9)
    f.text(x + HALF_W, y, f"Аркуш № {sheet.number_str}", size=9,
           bold=True, align="r")
    if pages_total > 1:
        f.text(x + HALF_W, y + 4, f"стор. {page_no} з {pages_total}",
               size=6.5, align="r")

    # --- шапка таблиці
    y += 4
    heights = [11, 4]
    xs, ys = f.grid(x, y, COLS, heights)
    titles = ["Номер документа", "Від кого отримано чи кому видано",
              "Номер кореспондуючого рахунку, субрахунку",
              "Надходження, грн", "Видаток, грн"]
    for i, t in enumerate(titles):
        f.cell(xs, ys, i, 0, t, size=6.0)
    for i in range(5):
        f.cell(xs, ys, i, 1, str(i + 1), size=6)
    y = ys[-1]

    # --- рядки
    body = [None] * ROWS_PER_PAGE
    for i, r in enumerate(rows[:ROWS_PER_PAGE]):
        body[i] = r

    first_page = page_no == 1
    last_page = page_no == pages_total

    extra_top = 1 if first_page else 1        # «Залишок на початок дня» / «Перенесено»
    n_rows = extra_top + ROWS_PER_PAGE
    xs, ys = f.grid(x, y, COLS, [ROW_H] * n_rows)

    if first_page:
        f.cell(xs, ys, 0, 0, "", size=7)
        f.cell(xs, ys, 1, 0, "Залишок на початок дня", size=7, align="l", bold=True)
        f.cell(xs, ys, 2, 0, "", size=7)
        f.cell(xs, ys, 3, 0, fmt_money(sheet.opening_balance), size=7.5,
               align="r", bold=True)
        f.cell(xs, ys, 4, 0, "", size=7)
    else:
        f.cell(xs, ys, 1, 0, "Перенесено з попередньої сторінки", size=7, align="l")
        f.cell(xs, ys, 3, 0, fmt_money(carried[0]), size=7.5, align="r")
        f.cell(xs, ys, 4, 0, fmt_money(carried[1]), size=7.5, align="r")

    for i, r in enumerate(body):
        row = i + extra_top
        if r is None:
            continue
        f.cell(xs, ys, 0, row, r["num"], size=7)
        f.cell(xs, ys, 1, row, r["who"], size=6.5, align="l")
        f.cell(xs, ys, 2, row, r["acc"], size=7)
        f.cell(xs, ys, 3, row, fmt_money(r["inc"]) if r["inc"] is not None else "",
               size=7.5, align="r")
        f.cell(xs, ys, 4, row, fmt_money(r["out"]) if r["out"] is not None else "",
               size=7.5, align="r")
    y = ys[-1]

    # --- підсумки
    if last_page:
        totals = [
            ("Усього за день", fmt_money(sheet.total_in), fmt_money(sheet.total_out), True),
            ("Залишок на кінець дня", fmt_money(sheet.closing_balance), "", True),
            ("у тому числі на заробітну плату, виплати, пов'язані з оплатою "
             "праці, стипендії, пенсії", fmt_money(sheet.salary_balance), "", False),
        ]
        xs, ys = f.grid(x, y, COLS, [ROW_H, ROW_H, 9])
        for i, (title, v_in, v_out, bold) in enumerate(totals):
            f.cell(xs, ys, 1, i, title, size=6.5 if i < 2 else 5.6,
                   align="l", bold=bold)
            f.cell(xs, ys, 3, i, v_in, size=7.5, align="r", bold=bold)
            f.cell(xs, ys, 4, i, v_out, size=7.5, align="r", bold=bold)
        y = ys[-1]
    else:
        page_in = carried[0] + sum((r["inc"] or ZERO) for r in rows[:ROWS_PER_PAGE])
        page_out = carried[1] + sum((r["out"] or ZERO) for r in rows[:ROWS_PER_PAGE])
        xs, ys = f.grid(x, y, COLS, [ROW_H])
        f.cell(xs, ys, 1, 0, "Перенесення на наступну сторінку", size=6.5, align="l")
        f.cell(xs, ys, 3, 0, fmt_money(page_in), size=7.5, align="r")
        f.cell(xs, ys, 4, 0, fmt_money(page_out), size=7.5, align="r")
        y = ys[-1]

    if not last_page:
        return

    # --- підписи
    y += 10
    f.text(x, y - 5, "Касир", size=8)
    f.field(x + 12, y, 40, "", label="підпис")
    f.field(x + 54, y, HALF_W - 54, sheet.cashier_name or "",
            label="прізвище, ім'я, по батькові")

    y += 10
    f.text(x, y, "Записи в касовій книзі перевірив і документи в кількості", size=7)
    w1 = f.text_width("Записи в касовій книзі перевірив і документи в кількості", 7)
    f.field(x + w1 + 1, y + 1, 12, str(sheet.docs_in_count), align="c", size=7.5)
    f.text(x + w1 + 14, y, "прибуткових та", size=7)
    y += 6
    f.field(x, y + 1, 12, str(sheet.docs_out_count), align="c", size=7.5)
    f.text(x + 13, y, "видаткових одержав.", size=7)

    y += 9
    acc_title = "Бухгалтер"
    if company and not company.has_chief_accountant:
        acc_title = company.signatory("accountant")[0] or "Бухгалтер"
    f.text(x, y - 5, acc_title, size=8)
    lw = f.text_width(acc_title, 8) + 3
    f.field(x + lw, y, 34, "", label="підпис")
    f.field(x + lw + 36, y, HALF_W - lw - 36, sheet.accountant_name or "",
            label="прізвище, ім'я, по батькові")

    if sheet.content_hash:
        f.text(x, y + 8, f"Контрольна сума аркуша (SHA-256): "
                         f"{sheet.content_hash[:24]}…", size=5, color=GREY)


def _draft_mark(f, sheet):
    if not sheet.is_closed:
        f.c.saveState()
        f.c.setFont("UA-Bold", 46)
        f.c.setFillGray(0.87)
        f.c.translate(PAGE[0] / 2, PAGE[1] / 2)
        f.c.rotate(28)
        f.c.drawCentredString(0, 0, "ДЕНЬ НЕ ЗАКРИТО")
        f.c.restoreState()


def _sheet_pages(c, sheet, company):
    rows = _entries_of(sheet)
    chunks = [rows[i:i + ROWS_PER_PAGE] for i in range(0, max(len(rows), 1), ROWS_PER_PAGE)] \
        or [[]]
    total = len(chunks)
    carried = [ZERO, ZERO]
    for idx, chunk in enumerate(chunks, start=1):
        f = Form(c, *PAGE)
        cur = tuple(carried)
        _half(f, LEFT_X, sheet, company, chunk, idx, total, False, cur)
        _half(f, RIGHT_X, sheet, company, chunk, idx, total, True, cur)
        carried[0] += sum((r["inc"] or ZERO) for r in chunk)
        carried[1] += sum((r["out"] or ZERO) for r in chunk)
        f.cut_line(CUT_X, 8, 202)
        _draft_mark(f, sheet)
        c.showPage()


def render_sheet(sheet, company) -> bytes:
    """Один аркуш касової книги за день (вкладний аркуш + звіт касира)."""
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=PAGE)
    c.setTitle(f"Касова книга, аркуш № {sheet.number_str} "
               f"за {sheet.sheet_date:%d.%m.%Y}")
    _sheet_pages(c, sheet, company)
    c.save()
    return buf.getvalue()


def render_book(sheets, company, year, title_suffix="") -> bytes:
    """Брошура касової книги за період + засвідчувальний напис.

    п. 40 Положення № 148: загальна кількість аркушів касової книги за рік
    засвідчується підписами керівника і головного бухгалтера.
    """
    buf = BytesIO()
    c = rl_canvas.Canvas(buf, pagesize=PAGE)
    c.setTitle(f"Касова книга за {year} рік {title_suffix}".strip())

    # титульний аркуш
    f = Form(c, *PAGE)
    f.text(PAGE[0] / 2 / 2.8346, 45, "КАСОВА КНИГА", size=22, bold=True, align="c")
    f.text(105, 58, f"за {year} рік {title_suffix}".strip(), size=13, align="c")
    f.text(105, 80, company.name if company else "", size=12, align="c")
    if company:
        f.text(105, 88, f"Ідентифікаційний код ЄДРПОУ: {company.edrpou}",
               size=9, align="c")
        if company.address:
            f.text(105, 95, company.address, size=9, align="c")
    f.text(105, 120, "Ведеться в електронній формі відповідно до пунктів 39–45",
           size=8, align="c")
    f.text(105, 126, "Положення про ведення касових операцій у національній валюті "
                     "в Україні,", size=8, align="c")
    f.text(105, 132, "затвердженого постановою Правління НБУ від 29.12.2017 № 148",
           size=8, align="c")
    c.showPage()

    for s in sheets:
        _sheet_pages(c, s, company)

    # засвідчувальний напис
    f = Form(c, *PAGE)
    y = 40
    f.text(105, y, "ЗАСВІДЧУВАЛЬНИЙ НАПИС", size=13, bold=True, align="c")
    y += 16
    f.text(30, y, "У цій касовій книзі пронумеровано, прошнуровано і скріплено "
                  "печаткою (за наявності)", size=10)
    y += 9
    f.field(30, y, 24, str(len(sheets)), align="c", size=11, bold=True)
    f.text(56, y - 1.2, f"(_____________________________) аркушів за {year} рік.",
           size=10)
    f.text(60, y + 3.5, "кількість словами", size=6)
    y += 25
    f.text(30, y - 5, "Керівник", size=10)
    f.field(52, y, 55, "", label="підпис")
    f.field(112, y, 70, company.director if company else "",
            label="прізвище, ім'я, по батькові")
    y += 16
    f.text(30, y - 5, "Головний бухгалтер", size=10)
    f.field(72, y, 35, "", label="підпис")
    f.field(112, y, 70, company.chief_accountant if company else "",
            label="прізвище, ім'я, по батькові")
    y += 18
    f.text(30, y, "М.П.", size=9)
    c.showPage()
    c.save()
    return buf.getvalue()


# ------------------------------------------------------------------- КО-3

def render_journal(orders, company, date_from, date_to) -> bytes:
    """Журнал реєстрації прибуткових і видаткових касових документів (КО-3)."""
    buf = BytesIO()
    page = A4                                   # книжкова
    c = rl_canvas.Canvas(buf, pagesize=page)
    c.setTitle(f"Журнал реєстрації касових документів "
               f"{date_from:%d.%m.%Y}-{date_to:%d.%m.%Y}")

    ins = sorted([o for o in orders if o.kind == CashOrder.KIND_IN],
                 key=lambda o: (o.doc_date, o.number))
    outs = sorted([o for o in orders if o.kind == CashOrder.KIND_OUT],
                  key=lambda o: (o.doc_date, o.number))
    n = max(len(ins), len(outs), 1)

    cols = [17, 15, 26, 33, 17, 15, 26, 33]     # 182 мм
    rows_per_page = 34
    pages = (n + rows_per_page - 1) // rows_per_page

    for p in range(pages):
        f = Form(c, *page)
        y = 12
        f.field(14, y, 120, company.name if company else "",
                label="підприємство (установа, організація)")
        f.field(138, y, 44, company.edrpou if company else "",
                label="Ідентифікаційний код ЄДРПОУ", align="c")
        f.text(196, y - 4, "Типова форма № КО-3", size=6, align="r")
        y = 24
        f.text(105, y, "ЖУРНАЛ", size=12, bold=True, align="c")
        y += 5
        f.text(105, y, "реєстрації прибуткових і видаткових касових документів",
               size=9, align="c")
        y += 6
        f.text(105, y, f"за період з {date_from:%d.%m.%Y} по {date_to:%d.%m.%Y}",
               size=8.5, align="c")
        if pages > 1:
            f.text(196, y, f"стор. {p + 1} з {pages}", size=7, align="r")

        y += 5
        xs, ys = f.grid(14, y, cols, [6, 9, 4])
        f.cell(xs, ys, 0, 0, "Прибутковий документ", size=8, bold=True, colspan=4)
        f.cell(xs, ys, 4, 0, "Видатковий документ", size=8, bold=True, colspan=4)
        heads = ["дата", "номер", "сума, грн", "примітка"] * 2
        for i, t in enumerate(heads):
            f.cell(xs, ys, i, 1, t, size=6.5)
        for i in range(8):
            f.cell(xs, ys, i, 2, str(i + 1), size=6)
        y = ys[-1]

        xs, ys = f.grid(14, y, cols, [5] * rows_per_page)
        for r in range(rows_per_page):
            idx = p * rows_per_page + r
            if idx < len(ins):
                o = ins[idx]
                f.cell(xs, ys, 0, r, f"{o.doc_date:%d.%m.%Y}", size=6.5)
                f.cell(xs, ys, 1, r, o.number_str, size=6.5)
                f.cell(xs, ys, 2, r, fmt_money(o.amount), size=6.5, align="r")
                f.cell(xs, ys, 3, r, o.cancel_reason if o.status == o.CANCELLED
                       else (o.counterparty_text or ""), size=5.5, align="l")
            if idx < len(outs):
                o = outs[idx]
                f.cell(xs, ys, 4, r, f"{o.doc_date:%d.%m.%Y}", size=6.5)
                f.cell(xs, ys, 5, r, o.number_str, size=6.5)
                f.cell(xs, ys, 6, r, fmt_money(o.amount), size=6.5, align="r")
                f.cell(xs, ys, 7, r, o.cancel_reason if o.status == o.CANCELLED
                       else (o.counterparty_text or ""), size=5.5, align="l")
        y = ys[-1]

        if p == pages - 1:
            total_in = sum((to_decimal(o.amount) for o in ins
                            if o.status == CashOrder.POSTED), ZERO)
            total_out = sum((to_decimal(o.amount) for o in outs
                             if o.status == CashOrder.POSTED), ZERO)
            xs, ys = f.grid(14, y, cols, [6])
            f.cell(xs, ys, 0, 0, "Разом", size=7.5, bold=True, colspan=2)
            f.cell(xs, ys, 2, 0, fmt_money(total_in), size=7.5, align="r", bold=True)
            f.cell(xs, ys, 3, 0, "", size=7)
            f.cell(xs, ys, 4, 0, "Разом", size=7.5, bold=True, colspan=2)
            f.cell(xs, ys, 6, 0, fmt_money(total_out), size=7.5, align="r", bold=True)
            f.cell(xs, ys, 7, 0, "", size=7)
            y = ys[-1] + 14
            f.text(14, y - 5, "Головний бухгалтер", size=9)
            f.field(58, y, 50, "", label="підпис")
            f.field(112, y, 70, company.chief_accountant if company else "",
                    label="прізвище, ім'я, по батькові")
        c.showPage()
    c.save()
    return buf.getvalue()
