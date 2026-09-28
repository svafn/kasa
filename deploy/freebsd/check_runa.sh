#!/bin/sh
#
# Сторож касової книги: перевіряє, чи застосунок живий, і піднімає його,
# якщо ні. Викликається з crontab користувача кожні кілька хвилин.
#
#   */5 * * * * /home/sva/www/kasa/deploy/freebsd/check_runa.sh
#
# Перевіряються дві речі:
#   1) чи існує процес із pid-файла;
#   2) чи відповідає він на HTTP.
# Друга перевірка важлива: процес, що завис, залишає pid-файл на місці,
# і перевірка «чи є процес» вважала б такий застосунок справним.
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PID_FILE="$RUN_DIR/kasa.pid"
LOG_FILE="$LOG_DIR/kasa-check.log"
CHECK_LOCK="$RUN_DIR/kasa-check.lock"
URL="http://127.0.0.1:$PORT/auth/login"

mkdir -p "$RUN_DIR" "$LOG_DIR" || exit 1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"
}

# Якщо попередній запуск сторожа ще працює (застосунок довго стартує),
# цей мовчки завершується. Без цього два запуски cron поспіль можуть
# підняти два екземпляри й почати писати в одну базу одночасно.
if [ "${KASA_CHECK_LOCKED:-}" != "1" ]; then
    KASA_CHECK_LOCKED=1
    export KASA_CHECK_LOCKED
    exec lockf -s -t 0 "$CHECK_LOCK" "$0" "$@"
fi

process_alive() {
    [ -f "$PID_FILE" ] || return 1
    pid=$(cat "$PID_FILE" 2>/dev/null)
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null
}

http_alive() {
    # fetch входить до базової системи FreeBSD, curl може бути не встановлений
    if command -v fetch >/dev/null 2>&1; then
        fetch -qo /dev/null -T 10 "$URL" 2>/dev/null
    elif command -v curl >/dev/null 2>&1; then
        curl -fsS -m 10 -o /dev/null "$URL" 2>/dev/null
    else
        # немає чим перевірити HTTP — покладаємося лише на pid-файл
        return 0
    fi
}

restart() {
    log "$1 — перезапускаю"
    "$SCRIPT_DIR/stopa.sh" >/dev/null 2>&1
    sleep 2
    "$SCRIPT_DIR/runa.sh"
    if [ $? -eq 0 ]; then
        log "перезапуск виконано"
    else
        log "ПОМИЛКА перезапуску, дивіться $LOG_DIR/kasa.log"
    fi
}

if ! process_alive; then
    restart "процес не знайдено"
    exit 0
fi

if ! http_alive; then
    restart "процес живий, але не відповідає на $URL"
    exit 0
fi

# У звичайному стані сторож мовчить: інакше cron щоп'ять хвилин
# надсилатиме листа, а журнал розросте без користі.
exit 0
