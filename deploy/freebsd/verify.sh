#!/bin/sh
#
# Щотижневий контроль цілісності закритих аркушів касової книги.
#   30 7 * * 1  /home/sva/www/kasa/deploy/freebsd/verify.sh
#
# Перевіряє ланцюжок контрольних сум: чи не змінювалися дані закритих
# днів в обхід програми (правкою в базі, відновленням старої копії тощо).
# У звичайному стані скрипт мовчить; за наявності проблем виводить їх,
# і cron надішле листа, якщо в crontab указано MAILTO.
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

LOG_FILE="$LOG_DIR/kasa-verify.log"
YEAR=$(date '+%Y')

mkdir -p "$LOG_DIR" || exit 1

cd "$APP_DIR" || exit 1
export FLASK_APP=wsgi.py
export TZ

out=$("$VENV_DIR/bin/flask" verify-chain --year "$YEAR" 2>&1)
rc=$?

echo "$(date '+%Y-%m-%d %H:%M:%S') $out" >> "$LOG_FILE"

if [ $rc -ne 0 ]; then
    # Вивід у stdout потрапить у лист від cron
    echo "Касова книга, контроль цілісності за $YEAR рік:"
    echo "$out"
    exit 1
fi

exit 0
