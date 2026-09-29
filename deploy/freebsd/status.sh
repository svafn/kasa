#!/bin/sh
#
# Стан касової книги.
#   /home/sva/www/kasa/deploy/freebsd/status.sh
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PID_FILE="$RUN_DIR/kasa.pid"
FAIL_FILE="$RUN_DIR/kasa-check.fails"
URL="http://127.0.0.1:$PORT/auth/login"
rc=0

# --- процес
if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null)
else
    pid=""
fi

if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "kasa: працює, pid $pid, порт $PORT"
    ps -o pid,start,time,rss,command -p "$pid" 2>/dev/null | tail -n +2
else
    echo "kasa: НЕ ПРАЦЮЄ"
    rc=1
fi

# --- узгодженість порту
# Найпідступніша помилка налаштування: у kasa.conf один порт, у .env інший.
# Тоді сторож стукає не туди, вважає застосунок непрацездатним і
# перезапускає його — користувач бачить «сервер відхилив з'єднання»
# просто посеред роботи.
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
    env_port=$(grep -E '^[[:space:]]*PORT=' "$ENV_FILE" 2>/dev/null \
               | tail -1 | sed 's/^[[:space:]]*PORT=//' | tr -d '"'"'"' ' | tr -d '\r')
    if [ -n "${env_port:-}" ] && [ "$env_port" != "$PORT" ]; then
        echo
        echo "УВАГА: розбіжність портів."
        echo "  kasa.conf: PORT=$PORT"
        echo "  .env:      PORT=$env_port"
        echo "  Запуск через runa.sh використає $PORT, а сторож перевірятиме $PORT."
        echo "  Якщо застосунок фактично доступний на $env_port, він запущений"
        echo "  повз runa.sh — тоді сторож перезапускатиме його кожні 5 хвилин."
        echo "  Приведіть обидва файли до одного значення."
        rc=1
    fi
fi

# --- лічильник невдалих перевірок сторожа
if [ -f "$FAIL_FILE" ]; then
    echo
    echo "Сторож нарахував невдалих перевірок поспіль: $(cat "$FAIL_FILE")"
fi

# --- HTTP
if command -v fetch >/dev/null 2>&1; then
    probe="fetch -qo /dev/null -T 15"
elif command -v curl >/dev/null 2>&1; then
    probe="curl -fsS -m 15 -o /dev/null"
else
    probe=""
fi

if [ -n "$probe" ]; then
    echo
    if $probe "$URL" 2>/dev/null; then
        echo "HTTP: відповідає на $URL"
    else
        echo "HTTP: НЕ відповідає на $URL"
        rc=1
    fi
fi

exit $rc
