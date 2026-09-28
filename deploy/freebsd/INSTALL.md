# Встановлення на FreeBSD 13.5

Застосунок працює на порту **5005** під правами звичайного користувача
(нижче — `sva`), запускається й наглядається через `cron`, так само як інші
сервіси на цьому сервері.

---

## 1. Пакети системи

```sh
# від root
pkg install python311 py311-pip py311-sqlite3 dejavu
```

`py311-sqlite3` **обов'язковий**: у FreeBSD модуль `sqlite3` не входить до
основного пакета Python, і без нього застосунок не запуститься
(`ModuleNotFoundError: No module named '_sqlite3'`). Помилка виникає вже під
час `flask db upgrade`, тому пропустити цей пакет непомітно не вийде.

`dejavu` дає шрифт із кирилицею для PDF. Без нього друковані форми
або не сформуються, або друкуватимуть порожні прямокутники замість тексту.

Якщо надалі переходитимете на MySQL, додайте клієнта:

```sh
pkg install mysql80-client        # для mysqldump у скрипті резервування
```

Драйвер `PyMySQL` — чистий Python, компілятор для нього не потрібен.
Не встановлюйте `mysqlclient`: він потребує складання з вихідних кодів.

---

## 2. Розміщення й віртуальне оточення

```sh
# від користувача sva
mkdir -p /home/sva/www/kasa
cd /home/sva/www/kasa
# розпакуйте сюди архів проєкту

python3.11 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
./venv/bin/pip install waitress
```

**Якщо `reportlab` не збирається** (потребує компілятора й заголовків
freetype), поставте його з пакетів і створіть оточення з доступом до
системних модулів:

```sh
# від root
pkg install py311-reportlab

# від sva, замість звичайного venv
rm -rf venv
python3.11 -m venv --system-site-packages venv
./venv/bin/pip install -r requirements.txt --no-deps
./venv/bin/pip install flask flask-sqlalchemy flask-migrate flask-login \
                       flask-wtf python-dotenv waitress
```

---

## 3. Налаштування застосунку

```sh
cd /home/sva/www/kasa
cp .env.example .env
```

У `.env` вкажіть:

```
SECRET_KEY=<довгий випадковий рядок>
DATABASE_URL=sqlite:///instance/kasa.db
PORT=5005
BIND_HOST=0.0.0.0
SERVER=waitress
TZ=Europe/Kiev
```

Ключ згенеруйте так:

```sh
./venv/bin/python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Створення бази й першого користувача:

```sh
export FLASK_APP=wsgi.py
./venv/bin/flask db upgrade      # структура бази
./venv/bin/flask seed-dicts      # план рахунків
./venv/bin/flask create-admin    # логін, ПІБ, пароль
./venv/bin/flask check-fonts     # має показати шлях до DejaVuSans.ttf
```

---

## 4. Скрипти запуску

```sh
cd /home/sva/www/kasa/deploy/freebsd
chmod +x *.sh
```

Відредагуйте **`kasa.conf`** — це єдине місце, де вказуються шляхи; решта
скриптів читають його. Якщо проєкт лежить не в `/home/sva/www/kasa`,
виправте `APP_DIR` і `VENV_DIR`.

Перевірка вручну:

```sh
./runa.sh          # запуск
./status.sh        # стан: pid, порт, відповідь на HTTP
./stopa.sh         # зупинка
```

Після `runa.sh` відкрийте `http://<адреса-сервера>:5005`.

Призначення скриптів:

| Скрипт | Що робить |
|---|---|
| `runa.sh` | запускає застосунок; повторний виклик другий екземпляр не піднімає |
| `stopa.sh` | зупиняє чемно (TERM), через 15 с — примусово |
| `status.sh` | показує стан: процес і відповідь на HTTP |
| `check_runa.sh` | сторож для cron: піднімає застосунок, якщо той упав або завис |
| `backup.sh` | резервна копія бази з обертанням старих копій |
| `verify.sh` | контроль незмінності закритих аркушів касової книги |
| `kasa.rc` | служба rc.d — запуск під час завантаження сервера |

---

## 5. Завдання cron

```sh
# від користувача sva, НЕ від root
crontab -e
```

Вставте вміст `crontab.example`, виправивши шлях, якщо він інший:

```
SHELL=/bin/sh
PATH=/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
TZ=Europe/Kiev
MAILTO=""

KASA=/home/sva/www/kasa/deploy/freebsd

@reboot            sleep 30 && $KASA/runa.sh
*/5 * * * *        $KASA/check_runa.sh
0 23 * * *         $KASA/backup.sh
30 7 * * 1         $KASA/verify.sh
```

Перевірити: `crontab -l`

Сторож у звичайному стані мовчить — у журнал пише лише перезапуски, тому
`MAILTO=""` не приховає збоїв. Якщо хочете отримувати листи про
перезапуски й порушення цілісності, вкажіть там свою адресу.

---

## 6. Запуск під час завантаження сервера (за бажанням)

Рядок `@reboot` у crontab це вже забезпечує. Але служба rc.d надійніша:
вона піднімає застосунок на потрібному етапі завантаження й дає звичні
команди `service`.

```sh
# від root
cp /home/sva/www/kasa/deploy/freebsd/kasa.rc /usr/local/etc/rc.d/kasa
chmod 555 /usr/local/etc/rc.d/kasa
sysrc kasa_enable=YES
sysrc kasa_user=sva
sysrc kasa_dir=/home/sva/www/kasa

service kasa start
service kasa status
```

Якщо ставите службу rc.d — приберіть рядок `@reboot` з crontab, щоб
застосунок не піднімався двічі.

---

## 7. Журнали

| Файл | Що містить |
|---|---|
| `logs/kasa.log` | вивід застосунку, запуски й зупинки |
| `logs/kasa-check.log` | перезапуски сторожем |
| `logs/kasa-backup.log` | резервні копії |
| `logs/kasa-verify.log` | контроль цілісності |

Журнал застосунку з часом зростає — додайте його до `newsyslog`:

```sh
# /usr/local/etc/newsyslog.conf.d/kasa.conf, від root
/home/sva/www/kasa/logs/kasa.log   sva:sva   644  7  1000  *  CN
```

---

## 8. Nginx попереду (рекомендовано)

Прямий доступ до застосунку на порту 5005 працює, але через nginx краще:
HTTPS, обмеження доступу за адресами, стиснення.

```nginx
server {
    listen 443 ssl;
    server_name kasa.example.com;

    ssl_certificate     /usr/local/etc/letsencrypt/live/kasa.example.com/fullchain.pem;
    ssl_certificate_key /usr/local/etc/letsencrypt/live/kasa.example.com/privkey.pem;

    client_max_body_size 8m;

    location / {
        proxy_pass         http://127.0.0.1:5005;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
```

У цьому разі в `.env` і `kasa.conf` поставте `BIND_HOST=127.0.0.1`, щоб
застосунок не був доступний з мережі напряму, в обхід nginx.

Після переходу на HTTPS увімкніть захищені куки — додайте в `config.py`:

```python
SESSION_COOKIE_SECURE = True
```

---

## 9. Права на файли

База й журнали мають належати користувачеві, під яким працює застосунок:

```sh
chown -R sva:sva /home/sva/www/kasa
chmod 700 /home/sva/www/kasa/instance      # у базі — персональні дані
chmod 600 /home/sva/www/kasa/.env          # у файлі — SECRET_KEY і пароль БД
```

---

## 10. Перевірка після встановлення

```sh
cd /home/sva/www/kasa/deploy/freebsd
./status.sh                       # працює, відповідає на HTTP
./backup.sh && ls -la /home/sva/backup/kasa/
./verify.sh; echo "код: $?"       # 0 — цілісність у нормі
```

Окремо переконайтеся, що **копія бази відновлюється** — копія, яку ніколи
не перевіряли, не є резервною копією:

```sh
cd /tmp
gunzip -k /home/sva/backup/kasa/kasa-*.db.gz
/home/sva/www/kasa/venv/bin/python -c \
  "import sqlite3,sys; print(sqlite3.connect(sys.argv[1]).execute('PRAGMA integrity_check').fetchone()[0])" \
  /home/sva/backup/kasa/kasa-*.db
```

Має вивести `ok`.

І останнє — відкрийте будь-який касовий ордер, натисніть «Друк PDF» і
переконайтеся, що українські літери друкуються, а не замінюються
прямокутниками.

---

## Відмінності від запуску `refills_registr`

Скрипти навмисно відрізняються від ваших наявних у трьох місцях.

**Блокування під час запуску.** `runa.sh` виконується під `lockf -t 0`.
Без цього два виклики cron поспіль (застосунок стартує повільніше, ніж
минає інтервал перевірки) можуть підняти два процеси. Для касової книги
на SQLite два процеси, що пишуть в один файл, — прямий шлях до пошкодження
бази й розбіжності залишків.

**Стан визначається за pid-файлом, а не за `pgrep -f`.** Шаблон
`pgrep -f 'python .*kasa'` збігається не лише із застосунком, а й із самим
скриптом перевірки та будь-якою командою, у чиєму рядку трапилося це слово.
Під час підготовки цих скриптів `pgrep -f` повертав три збіги там, де
процес був один.

**Перевіряється не лише наявність процесу, а й відповідь на HTTP.**
Процес, що завис, залишає pid-файл на місці, і перевірка «чи живий процес»
вважала б такий застосунок справним. Сторож звертається до
`http://127.0.0.1:5005/auth/login` і перезапускає застосунок, якщо
відповіді немає.
