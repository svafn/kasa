#!/bin/sh
#
# Резервне копіювання бази касової книги.
#   0 23 * * *  /home/sva/www/kasa/deploy/freebsd/backup.sh
#
# Копія знімається «гарячим» способом, без зупинки застосунку:
# для SQLite — через штатний механізм резервування (.backup), який
# дочекається завершення поточних транзакцій; просте копіювання файла
# під час запису дало б пошкоджену копію.
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

LOG_FILE="$LOG_DIR/kasa-backup.log"
STAMP=$(date '+%Y-%m-%d_%H%M')
PYTHON="$VENV_DIR/bin/python"

mkdir -p "$BACKUP_DIR" "$LOG_DIR" || exit 1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"
}

# Рядок підключення читаємо з .env застосунку
DB_URL=$(grep -E '^[[:space:]]*DATABASE_URL=' "$APP_DIR/.env" 2>/dev/null \
         | tail -1 | sed 's/^[[:space:]]*DATABASE_URL=//' | tr -d '"'"'"'')

if [ -z "${DB_URL:-}" ]; then
    DB_URL="sqlite:///instance/kasa.db"
fi

case "$DB_URL" in
    sqlite*)
        DB_PATH=$(echo "$DB_URL" | sed 's|^sqlite:////|/|; s|^sqlite:///||')
        case "$DB_PATH" in
            /*) : ;;
            *) DB_PATH="$APP_DIR/$DB_PATH" ;;
        esac

        if [ ! -f "$DB_PATH" ]; then
            log "ПОМИЛКА: не знайдено файл бази $DB_PATH"
            exit 1
        fi

        OUT="$BACKUP_DIR/kasa-$STAMP.db"
        "$PYTHON" - "$DB_PATH" "$OUT" <<'PYEOF'
import sqlite3
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True, timeout=30)
dst = sqlite3.connect(dst_path)
with dst:
    src.backup(dst)          # узгоджена копія без зупинки застосунку
dst.close()
src.close()
PYEOF
        if [ $? -ne 0 ]; then
            log "ПОМИЛКА копіювання бази $DB_PATH"
            exit 1
        fi
        ;;

    mysql*)
        # mysql+pymysql://user:pass@host:port/dbname?charset=utf8mb4
        creds=$(echo "$DB_URL" | sed 's|^[^/]*//||; s|/.*$||')
        DB_USER=$(echo "$creds" | sed 's|:.*$||')
        DB_PASS=$(echo "$creds" | sed 's|^[^:]*:||; s|@.*$||')
        DB_HOST=$(echo "$creds" | sed 's|^.*@||; s|:.*$||')
        DB_PORT=$(echo "$creds" | sed 's|^.*@[^:]*||; s|^:||')
        [ -z "$DB_PORT" ] && DB_PORT=3306
        DB_NAME=$(echo "$DB_URL" | sed 's|^[^/]*//[^/]*/||; s|?.*$||')

        OUT="$BACKUP_DIR/kasa-$STAMP.sql"
        mysqldump --single-transaction --quick --default-character-set=utf8mb4 \
            -h "$DB_HOST" -P "$DB_PORT" -u "$DB_USER" -p"$DB_PASS" \
            "$DB_NAME" > "$OUT" 2>> "$LOG_FILE"
        if [ $? -ne 0 ]; then
            log "ПОМИЛКА mysqldump для бази $DB_NAME"
            rm -f "$OUT"
            exit 1
        fi
        ;;

    *)
        log "ПОМИЛКА: невідомий тип бази в DATABASE_URL"
        exit 1
        ;;
esac

gzip -f "$OUT" 2>/dev/null && OUT="$OUT.gz"
SIZE=$(ls -lh "$OUT" 2>/dev/null | awk '{print $5}')
log "копію створено: $OUT ($SIZE)"

# Прибирання старих копій
find "$BACKUP_DIR" -name 'kasa-*' -type f -mtime "+$BACKUP_KEEP_DAYS" -delete 2>/dev/null

exit 0
