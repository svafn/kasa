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
#
# Процес, якого немає, піднімається одразу. А от відсутність відповіді на
# HTTP сама собою не є підставою для перезапуску: застосунок може бути
# зайнятий довгим завданням (формування касової книги за рік), і
# перезапуск саме тоді обірве роботу користувача просто посеред закриття
# дня. Тому перезапуск відбувається лише після кількох невдалих перевірок
# поспіль (HTTP_FAIL_LIMIT).
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PID_FILE="$RUN_DIR/kasa.pid"
FAIL_FILE="$RUN_DIR/kasa-check.fails"
LOG_FILE="$LOG_DIR/kasa-check.log"
CHECK_LOCK="$RUN_DIR/kasa-check.lock"
URL="http://127.0.0.1:$PORT/auth/login"

# Скільки перевірок HTTP поспіль мають провалитися, перш ніж перезапускати
: "${HTTP_FAIL_LIMIT:=3}"
# Скільки секунд чекати на відповідь
: "${HTTP_TIMEOUT:=30}"
# Скільки секунд після запуску не чіпати застосунок (час на старт)
: "${START_GRACE:=60}"

mkdir -p "$RUN_DIR" "$LOG_DIR" || exit 1

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*" >> "$LOG_FILE"
}

# Якщо попередній запуск сторожа ще працює, цей мовчки завершується.
# Без цього два запуски cron поспіль можуть підняти два екземпляри
# й почати писати в одну базу одночасно.
if [ "${KASA_CHECK_LOCKED:-}" != "1" ]; then
    KASA_CHECK_LOCKED=1
    export KASA_CHECK_LOCKED
    exec lockf -s -t 0 "$CHECK_LOCK" "$0" "$@"
fi

read_fails() {
    if [ -f "$FAIL_FILE" ]; then
        cat "$FAIL_FILE" 2>/dev/null || echo 0
    else
        echo 0
    fi
}

reset_fails() {
    rm -f "$FAIL_FILE"
}

process_alive() {
    [ -f "$PID_FILE" ] || return 1
    pid=$(cat "$PID_FILE" 2>/dev/null)
    [ -n "$pid" ] || return 1
    kill -0 "$pid" 2>/dev/null
}

file_mtime() {
    # FreeBSD: stat -f '%m'; GNU/Linux: stat -c '%Y'. Ключ -f у GNU stat
    # означає зовсім інше (дані файлової системи) і завершується успішно,
    # тому результат обов'язково перевіряємо на число.
    m=$(stat -f '%m' "$1" 2>/dev/null)
    case "${m:-x}" in
        ''|*[!0-9]*) m=$(stat -c '%Y' "$1" 2>/dev/null) ;;
    esac
    case "${m:-x}" in
        ''|*[!0-9]*) return 1 ;;
    esac
    echo "$m"
}

just_started() {
    # Щойно запущений застосунок ще міг не встигнути відкрити порт
    [ -f "$PID_FILE" ] || return 1
    started=$(file_mtime "$PID_FILE") || return 1
    now=$(date '+%s')
    [ $((now - started)) -lt "$START_GRACE" ]
}

http_alive() {
    # fetch входить до базової системи FreeBSD, curl може бути не встановлений
    if command -v fetch >/dev/null 2>&1; then
        fetch -qo /dev/null -T "$HTTP_TIMEOUT" "$URL" 2>/dev/null
    elif command -v curl >/dev/null 2>&1; then
        curl -fsS -m "$HTTP_TIMEOUT" -o /dev/null "$URL" 2>/dev/null
    else
        # немає чим перевірити HTTP — покладаємося лише на pid-файл
        return 0
    fi
}

restart() {
    log "$1 — перезапускаю"
    "$SCRIPT_DIR/stopa.sh" >/dev/null 2>&1
    sleep 2
    if "$SCRIPT_DIR/runa.sh"; then
        log "перезапуск виконано"
    else
        log "ПОМИЛКА перезапуску, дивіться $LOG_DIR/kasa.log"
    fi
    reset_fails
}

# --- процес відсутній: піднімаємо негайно, тут двозначності немає
if ! process_alive; then
    restart "процес не знайдено"
    exit 0
fi

# --- процес щойно стартував: даємо йому час відкрити порт
if just_started; then
    exit 0
fi

# --- процес живий; перевіряємо, чи відповідає
if http_alive; then
    [ -f "$FAIL_FILE" ] && log "відповідає знову, лічильник збоїв скинуто"
    reset_fails
    exit 0
fi

fails=$(read_fails)
fails=$((fails + 1))
echo "$fails" > "$FAIL_FILE"

if [ "$fails" -lt "$HTTP_FAIL_LIMIT" ]; then
    # Застосунок може бути зайнятий довгою операцією. Перезапуск зараз
    # обірвав би роботу користувача, тому лише запам'ятовуємо збій.
    log "немає відповіді на $URL (спроба $fails з $HTTP_FAIL_LIMIT), чекаю"
    exit 0
fi

restart "немає відповіді на $URL $fails перевірки поспіль"
exit 0
