# -*- coding: utf-8 -*-
"""Перенесення даних SQLite -> MySQL без втрат.

Порядок переходу на другому етапі:
  1. Створити базу:
       CREATE DATABASE kasa CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
       CREATE USER 'kasa_user'@'%' IDENTIFIED BY '...';
       GRANT ALL PRIVILEGES ON kasa.* TO 'kasa_user'@'%';
  2. У .env вказати DATABASE_URL=mysql+pymysql://...
  3. flask db upgrade            # структура таблиць у MySQL
  4. python tools/sqlite_to_mysql.py \
         --source sqlite:///instance/kasa.db \
         --target mysql+pymysql://kasa_user:pass@127.0.0.1/kasa?charset=utf8mb4

Оскільки всі суми зберігаються цілими копійками (BigInteger), перенесення
відбувається без округлень і без різниці у типах між СУБД.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import create_engine, text  # noqa: E402

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402

# Порядок важливий через зовнішні ключі
ORDER = ["company", "users", "counterparty", "account",
         "cash_book_sheet", "cash_order", "audit_log"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", required=True)
    ap.add_argument("--target", required=True)
    ap.add_argument("--batch", type=int, default=500)
    args = ap.parse_args()

    src = create_engine(args.source)
    dst = create_engine(args.target)

    app = create_app()
    with app.app_context():
        meta = db.metadata

    with dst.begin() as dconn:
        dconn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for name in reversed(ORDER):
            dconn.execute(text(f"DELETE FROM `{name}`"))

        total = 0
        with src.connect() as sconn:
            for name in ORDER:
                table = meta.tables.get(name)
                if table is None:
                    continue
                rows = [dict(r._mapping) for r in sconn.execute(table.select())]
                if not rows:
                    print(f"{name}: порожня")
                    continue
                for i in range(0, len(rows), args.batch):
                    dconn.execute(table.insert(), rows[i:i + args.batch])
                total += len(rows)
                print(f"{name}: перенесено {len(rows)} рядків")
        dconn.execute(text("SET FOREIGN_KEY_CHECKS=1"))

    # синхронізація AUTO_INCREMENT
    with dst.begin() as dconn:
        for name in ORDER:
            mx = dconn.execute(text(f"SELECT COALESCE(MAX(id),0)+1 FROM `{name}`")).scalar()
            dconn.execute(text(f"ALTER TABLE `{name}` AUTO_INCREMENT = {mx}"))

    print(f"\nГотово. Усього перенесено рядків: {total}")
    print("Перевірте контроль цілісності: у застосунку — «Перевірити цілісність» "
          "за кожен рік.")


if __name__ == "__main__":
    main()
