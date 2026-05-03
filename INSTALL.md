## Установка на Linux-сервер

Инструкция рассчитана на **обычный сервер или VPS с Linux** (Debian, Ubuntu, Rocky, Alma и аналоги), доступ по SSH и права на установку **systemd** (для таймера) или **cron**. Каталог проекта далее обозначен как `/opt/spimex-instruments` — при необходимости замените на свой путь.

---

### 1. Что понадобится

- **Python 3.9+** (в комплекте: `venv`, модуль `zoneinfo`).
- **`bash`**, утилиты `curl` или браузер не обязательны для базового режима.
- Сеть **IPv4**, исходящий доступ к **HTTPS** на `spimex.com`.
- Если нужна **почта**: исходящий доступ к вашему **SMTP** (хост и порт без блокировки фаерволом).

Примечание по Python: если в системе только `python3`, команды ниже выполнять с **`python3`** вместо `python`.

---

### 2. Перенести файлы проекта на сервер

Вариант A — **git**:

```bash
sudo mkdir -p /opt/spimex-instruments
sudo chown "$USER:$USER" /opt/spimex-instruments
cd /opt/spimex-instruments
git clone <URL_вашего_репозитория> .
```

Вариант B — **scp/rsync** с рабочей машины:

```bash
rsync -avz ./spimex-instruments/ user@server:/opt/spimex-instruments/
```

В каталоге должны быть как минимум: `spimex_export.py`, `requirements.txt`, `run_spimex_daily.sh`, `install_background.sh`, каталог `systemd/`, примеры `env.example`, файлы можно скопировать `urls.txt` и отредактировать.

Не копируйте на боевой сервер чужую папку **`.venv`** с другой машины — лучше создать её заново (следующий шаг).

---

### 3. Виртуальное окружение Python

```bash
cd /opt/spimex-instruments
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
chmod +x run_spimex_daily.sh install_background.sh
```

Проверка:

```bash
.venv/bin/python spimex_export.py --help
```

Дополнительно (только если понадобится обход проблем JS на сайте):

```bash
.venv/bin/pip install playwright
.venv/bin/playwright install chromium
```

---

### 4. Список инструментов: `urls.txt`

Отредактируйте файл **`urls.txt`**: каждая непустая строка без ведущего `#` — это либо **код инструмента** (например `PC36KOB062F`), либо **полная ссылка**:

`https://spimex.com/markets/oil_products/instruments/list/detail.php?code=XXXX`

Строки, начинающиеся с `#`, игнорируются.

Альтернатива через переменные в `.env` (следующий шаг):

```text
SPIMEX_URLS_FILE=/opt/spimex-instruments/conf/moi_instrumenty.txt
```

---

### 5. Конфигурация почты и путей: `.env`

1. В корне проекта создайте файл **`.env`** (именно такое имя, с точкой в начале):

   ```bash
   cd /opt/spimex-instruments
   cp env.example .env
   # или для Рамблера начните с:
   # cp env.rambler.example .env
   nano .env   # или vim
   chmod 600 .env
   ```

2. Заполните как минимум:

   | Переменная | Назначение |
   |------------|------------|
   | `SPIMEX_MAIL_TO` | Получатель(и) CSV через запятую |
   | `SPIMEX_MAIL_FROM` | Адрес в поле «От» |
   | `SPIMEX_SMTP_HOST` | Сервер SMTP |
   | `SPIMEX_SMTP_PORT` | Обычно `587` (STARTTLS) или `465` (SSL) |
   | `SPIMEX_SMTP_USER` | Часто полный адрес почты для авторизации на SMTP |
   | `SPIMEX_SMTP_PASSWORD` | Пароль или пароль приложения |

   Если используете порт **465** и прямое SSL-соединение:

   ```text
   SPIMEX_SMTP_USE_SSL=1
   ```

3. По желанию:

   ```text
   SPIMEX_OUTPUT_CSV=/opt/spimex-instruments/data/spimex_instruments.csv
   SPIMEX_REQUEST_DELAY=0.75
   SPIMEX_PYTHON=/opt/spimex-instruments/.venv/bin/python
   ```

`run_spimex_daily.sh` при старте делает **`set -a; source .env; set +a`**, поэтому переменные автоматически попадают в окружение дочернего процесса `spimex_export.py`.

Файл **`.gitignore`** уже исключает `.env`; не включайте `.env` с паролями в репозиторий.

---

### 6. Первый пробный запуск вручную

```bash
cd /opt/spimex-instruments
./run_spimex_daily.sh --delay 0
```

Либо явно через Python:

```bash
set -a && source .env && set +a
.venv/bin/python spimex_export.py -f urls.txt -o spimex_instruments.csv --delay 0
```

Успешные признаки:

- в конце строка вида `Записано строк: N -> ...csv`;
- при настроенных получателях и SMTP — строка **`Письмо с вложением отправлено: ...`**.

Коды выхода:

- **`0`** — всё успешно, в том числе почта если она включена;
- **`2`** — CSV записан, **ошибка отправки почты** (смотреть текст в stderr);
- **`1`** — другие ошибки (например нет файла списка URL).

При ошибках SMTP сохраните **только сообщение ошибки без пароля** для разбора политики сервера (TLS, авторизация, «разрешить почтовые клиенты» в веб-интерфейсе почты).

---

### 7. Фон по расписанию: systemd (рекомендуется)

Один запуск установщика в каталоге проекта:

```bash
cd /opt/spimex-instruments
./install_background.sh
```

По умолчанию ставится **пользовательский** таймер (файлы в `~/.config/systemd/user/` того пользователя, от которого вы запускали установку). Проверка:

```bash
systemctl --user list-timers spimex-daily.timer
journalctl --user -u spimex-daily.service -n 50 --no-pager
```

Чтобы пользовательские таймеры **работали после перезагрузки без активного входа**, для этого пользователя на сервере один раз выполните (от root):

```bash
sudo loginctl enable-linger имя_пользователя
```

#### Системная установка от root

Если хотите systemd **на уровне системы**, от имени сервисного пользователя без интерактивного входа:

```bash
cd /opt/spimex-instruments
sudo SPIMEX_RUN_USER=deploy ./install_background.sh --system
```

Где **`deploy`** — непривилегированный пользователь Linux, которому должны принадлежать `/opt/spimex-instruments` и права на чтение `.env`, запись в каталог CSV.

Управление и лог:

```bash
sudo systemctl list-timers spimex-daily.timer
sudo journalctl -u spimex-daily.service -n 50 --no-pager
```

Время триггера задано в **`systemd/spimex-daily.timer`**: каждый день **13:20** в часовой зоне **Europe/Moscow**.

Отключить:

```bash
systemctl --user disable --now spimex-daily.timer
# или: sudo systemctl disable --now spimex-daily.timer
```

---

### 8. Альтернатива: cron

Если systemd по политике недоступен, см. файл **`cron.moscow.example`** — скопируйте строку в `crontab -e`. Убедитесь, что в окружении cron либо прописан полный путь к `run_spimex_daily.sh`, либо cron-задача содержит `cd /opt/spimex-instruments` перед запуском, чтобы находились **`urls.txt`** и **`.env`**.

---

### 9. Обновление и бэкап

- Обновление кода: `git pull` (или заново скопировать файлы), затем при изменении **`requirements.txt`**: `.venv/bin/pip install -r requirements.txt`.
- После изменения **`install_background.sh`** или шаблонов в **`systemd/`** переустановите таймер: снова запустите **`./install_background.sh`** тем же режимом (user/system).
- При необходимости архивируйте сам **`spimex_instruments.csv`** или подключайте ротацию в отдельный каталог после копирования.

---

### 10. Безопасность

- Права **`chmod 700`** на каталог проекта допустимы, если нужен ограниченный доступ только владельцу.
- **`.env`** — **`chmod 600`**, только владелец и сервисный пользователь systemd.
- Не храните пароли в параметрах systemd `ExecStart` в открытом виде — используйте только **`EnvironmentFile=-.../.env`** (так уже сделано в шаблоне сервиса).

---

При сомнениях в часовых поясах сервера ориентируйтесь на **`Europe/Moscow`** в unit timer или переменную **`CRON_TZ`** в cron — см. **`cron.moscow.example`**.
