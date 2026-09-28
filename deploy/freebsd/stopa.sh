#!/bin/sh
#
# Зупинка касової книги.
#   /home/sva/www/kasa/deploy/freebsd/stopa.sh
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PID_FILE="$RUN_DIR/kasa.pid"
SUP_PID_FILE="$RUN_DIR/kasa-supervisor.pid"
LOG_FILE="$LOG_DIR/kasa.log"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') stopa: $*" >> "$LOG_FILE"
}

# Спершу знімаємо наглядача daemon(8): інакше він одразу підніме
# застосунок заново (він запущений з ключем -r).
if [ -f "$SUP_PID_FILE" ]; then
    sup=$(cat "$SUP_PID_FILE" 2>/dev/null)
    if [ -n "$sup" ] && kill -0 "$sup" 2>/dev/null; then
        kill -TERM "$sup" 2>/dev/null
        log "наглядача зупинено (pid $sup)"
    fi
    rm -f "$SUP_PID_FILE"
fi

if [ ! -f "$PID_FILE" ]; then
    log "pid-файл відсутній — застосунок, найімовірніше, не працює"
    exit 0
fi

pid=$(cat "$PID_FILE" 2>/dev/null)
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
    log "процес $pid не знайдено, прибираю несвіжий pid-файл"
    rm -f "$PID_FILE"
    exit 0
fi

# Спочатку чемно: TERM дає waitress закрити активні з'єднання
# і коректно завершити транзакції.
kill -TERM "$pid" 2>/dev/null
i=0
while [ $i -lt 15 ]; do
    kill -0 "$pid" 2>/dev/null || break
    sleep 1
    i=$((i + 1))
done

if kill -0 "$pid" 2>/dev/null; then
    log "процес $pid не завершився за 15 с, надсилаю KILL"
    kill -KILL "$pid" 2>/dev/null
    sleep 1
fi

rm -f "$PID_FILE"
log "зупинено"
exit 0
