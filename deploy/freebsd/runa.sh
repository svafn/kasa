#!/bin/sh
#
# Запуск касової книги на FreeBSD під правами звичайного користувача.
#   /home/sva/www/kasa/deploy/freebsd/runa.sh
#
# Скрипт безпечно викликати повторно: якщо застосунок уже працює,
# другий екземпляр не запускається.
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PID_FILE="$RUN_DIR/kasa.pid"
SUP_PID_FILE="$RUN_DIR/kasa-supervisor.pid"
LOCK_FILE="$RUN_DIR/kasa.lock"
LOG_FILE="$LOG_DIR/kasa.log"
PYTHON="$VENV_DIR/bin/python"

mkdir -p "$RUN_DIR" "$LOG_DIR" || exit 1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') runa: $*" >> "$LOG_FILE"
}

# --- чи вже працює
is_running() {
    [ -f "$PID_FILE" ] || return 1
    pid=$(cat "$PID_FILE" 2>/dev/null)
    [ -n "$pid" ] || return 1
    # kill -0 лише перевіряє існування процесу, нічого не надсилаючи
    kill -0 "$pid" 2>/dev/null
}

if is_running; then
    log "уже працює (pid $(cat "$PID_FILE")), повторний запуск не потрібен"
    exit 0
fi

# Несвіжий pid-файл після аварійного завершення прибираємо самі,
# інакше daemon(8) відмовиться стартувати.
[ -f "$PID_FILE" ] && rm -f "$PID_FILE"

if [ ! -x "$PYTHON" ]; then
    log "ПОМИЛКА: не знайдено інтерпретатор $PYTHON"
    exit 1
fi
if [ ! -f "$APP_DIR/run_server.py" ]; then
    log "ПОМИЛКА: не знайдено $APP_DIR/run_server.py"
    exit 1
fi

export PORT BIND_HOST SERVER THREADS TZ
export PYTHONUNBUFFERED=1

cd "$APP_DIR" || exit 1

# lockf -s -t 0 — захист від одночасного запуску: якщо цей самий скрипт
# уже виконується (наприклад, його щойно викликав cron), другий екземпляр
# завершується одразу, а не чекає і не піднімає другий процес.
#
# daemon(8) — з базової системи FreeBSD:
#   -f       від'єднатися від термінала
#   -r       перезапускати застосунок, якщо він аварійно завершиться
#   -P/-p    pid-файли наглядача і самого процесу
#   -o       файл журналу (stdout і stderr застосунку)
#   -t       підпис процесу у виводі ps
lockf -s -t 0 "$LOCK_FILE" \
    daemon -f -r \
        -P "$SUP_PID_FILE" \
        -p "$PID_FILE" \
        -o "$LOG_FILE" \
        -t "kasa:$PORT" \
        "$PYTHON" "$APP_DIR/run_server.py"

rc=$?
if [ $rc -ne 0 ]; then
    log "не вдалося запустити (код $rc); можливо, запуск уже виконується"
    exit $rc
fi

# Даємо процесу піднятися і переконуємося, що він не впав одразу
# (типова причина — зайнятий порт або помилка в .env).
sleep 2
if is_running; then
    log "запущено, pid $(cat "$PID_FILE"), порт $PORT"
    exit 0
fi

log "ПОМИЛКА: процес завершився одразу після запуску, дивіться $LOG_FILE"
exit 1
