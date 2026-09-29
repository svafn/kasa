#!/bin/sh
#
# Запуск касової книги в режимі налагодження — у передньому плані,
# з повним трасуванням помилок на екран і в браузер.
#
#   /home/sva/www/kasa/deploy/freebsd/debug.sh
#
# Використовується лише для пошуку причини збою. Скрипт:
#   * зупиняє фоновий застосунок, щоб звільнити порт;
#   * попереджає, якщо сторож у crontab може втрутитися;
#   * запускає вбудований сервер Flask, який показує трасування.
#
# Зупинити — Ctrl+C. Після цього поверніть звичайний режим:
#   ./runa.sh
#
set -u

SCRIPT_DIR=$(dirname "$0")
. "$SCRIPT_DIR/kasa.conf"

PYTHON="$VENV_DIR/bin/python"
FLASK="$VENV_DIR/bin/flask"

echo "=========================================================="
echo " РЕЖИМ НАЛАГОДЖЕННЯ — не для повсякденної роботи"
echo "=========================================================="
echo

# --- чи не заважатиме сторож
if crontab -l 2>/dev/null | grep -q '[c]heck_runa.sh'; then
    if crontab -l 2>/dev/null | grep '[c]heck_runa.sh' | grep -qv '^#'; then
        echo "УВАГА: у crontab увімкнено сторож check_runa.sh."
        echo "Поки ви шукаєте причину, він може підняти другий екземпляр"
        echo "і зайняти порт. Тимчасово вимкніть його:"
        echo
        echo "    crontab -l > ~/crontab.backup"
        echo "    crontab -l | sed 's|^\\*/5.*check_runa|#&|' | crontab -"
        echo
        echo "Повернути потім:  crontab ~/crontab.backup"
        echo
        printf "Продовжити попри це? [y/N] "
        read answer
        case "$answer" in
            y|Y|т|Т) : ;;
            *) echo "Скасовано."; exit 1 ;;
        esac
        echo
    fi
fi

# --- зупиняємо фоновий застосунок
echo "Зупиняю фоновий застосунок…"
"$SCRIPT_DIR/stopa.sh" >/dev/null 2>&1

# --- чи не лишилося зайвих екземплярів
leftovers=$(ps ax -o pid=,command= | grep '[r]un_server.py' | wc -l | tr -d ' ')
if [ "$leftovers" -gt 0 ]; then
    echo
    echo "УВАГА: лишилося процесів застосунку: $leftovers"
    ps ax -o pid=,command= | grep '[r]un_server.py'
    echo
    echo "Кілька екземплярів на одній базі SQLite блокують одне одного —"
    echo "це саме собою може бути причиною збоїв. Зупиніть зайві:"
    echo "    kill <pid>"
    echo
fi

cd "$APP_DIR" || exit 1
export FLASK_APP=wsgi.py
export TZ
export PYTHONUNBUFFERED=1

echo "Застосунок:  $APP_DIR"
echo "Python:      $PYTHON"
echo "Адреса:      http://$(hostname):$PORT  (і http://127.0.0.1:$PORT)"
echo
"$PYTHON" -c "import sys; print('версія Python:', sys.version.split()[0])"
"$FLASK" check-fonts 2>&1 | head -2
echo
echo "----------------------------------------------------------"
echo " Відтворіть дію, що дає збій. Трасування з'явиться нижче"
echo " і в самому браузері. Зупинити — Ctrl+C."
echo "----------------------------------------------------------"
echo

# --debug вмикає перезавантаження коду й сторінку з трасуванням.
# Вбудований сервер Flask не призначений для роботи під навантаженням,
# тому після діагностики поверніться до ./runa.sh
exec "$FLASK" run --host=0.0.0.0 --port="$PORT" --debug
