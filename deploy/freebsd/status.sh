#!/bin/sh
#
# Стан касової книги.
#   /home/sva/www/kasa/deploy/freebsd/status.sh
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PID_FILE="$RUN_DIR/kasa.pid"
URL="http://127.0.0.1:$PORT/auth/login"

if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null)
else
    pid=""
fi

if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "kasa: працює, pid $pid, порт $PORT"
    ps -o pid,start,time,rss,command -p "$pid" 2>/dev/null | tail -n +2
else
    echo "kasa: не працює"
    exit 1
fi

if command -v fetch >/dev/null 2>&1; then
    probe="fetch -qo /dev/null -T 10"
elif command -v curl >/dev/null 2>&1; then
    probe="curl -fsS -m 10 -o /dev/null"
else
    probe=""
fi

if [ -n "$probe" ]; then
    if $probe "$URL" 2>/dev/null; then
        echo "HTTP: відповідає на $URL"
    else
        echo "HTTP: НЕ відповідає на $URL"
        exit 1
    fi
fi

exit 0
