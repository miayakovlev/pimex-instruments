## Установка на Linux-сервер

Исходники лежат в публичном репозитории: **[github.com/miayakovlev/pimex-instruments](https://github.com/miayakovlev/pimex-instruments)** — на сервере достаточно **клонировать** и выполнить шаги ниже. Отдельно переносить файлы через `rsync` не нужно.

Ниже **`/opt/pimex-instruments`** — пример каталога; можно заменить на свой (`$HOME/pimex-instruments`, `/srv/...`, и т.д.).

**Нужно:** Python **3.9+**, доступ в интернет до **HTTPS** `spimex.com`, для почты — исходящий **SMTP**.

---

### 1. Клонирование и окружение

```bash
sudo mkdir -p /opt/pimex-instruments
sudo chown "$USER:$USER" /opt/pimex-instruments
cd /opt/pimex-instruments
git clone https://github.com/miayakovlev/pimex-instruments.git .
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
chmod +x run_spimex_daily.sh install_background.sh
```

По SSH-доступу к GitHub можно клонировать и так:  
`git clone git@github.com:miayakovlev/pimex-instruments.git .`

Проверка: `.venv/bin/python spimex_export.py --help`

*(Редкий запасной вариант: если понадобится рендер страницы в браузере — `pip install playwright` и `playwright install chromium`, флаги `--browser` / `--browser-fallback` в скрипте.)*

---

### 2. Список инструментов

Отредактируйте **`urls.txt`** (в репозитории уже есть пример): по строке на **код** или **полный URL** карточки `detail.php?code=…`. Строки с `#` в начале — комментарии.

Либо в **`.env`** задайте `SPIMEX_URLS_FILE=/путь/к/файлу.txt`.

---

### 3. Конфиг `.env`

```bash
cd /opt/pimex-instruments
cp env.example .env           # или: cp env.rambler.example .env
nano .env
chmod 600 .env
```

Минимум для отправки почты: `SPIMEX_MAIL_TO`, `SPIMEX_MAIL_FROM`, `SPIMEX_SMTP_HOST`, `SPIMEX_SMTP_PORT`, при необходимости `SPIMEX_SMTP_USER`, `SPIMEX_SMTP_PASSWORD`. Для порта **465** обычно добавляют `SPIMEX_SMTP_USE_SSL=1`.

Путь к каталогу в переменных (если нужны): `SPIMEX_OUTPUT_CSV`, `SPIMEX_URLS_FILE`, `SPIMEX_REQUEST_DELAY`. Секреты в git не попадают (см. `.gitignore`).

---

### 4. Пробный запуск

```bash
cd /opt/pimex-instruments
./run_spimex_daily.sh --delay 0
```

Ожидаемо в конце: `Записано строк: N -> ...csv`; при настроенной почте ещё: `Письмо с вложением отправлено`.

Коды выхода: **0** — успех (включая почту при необходимости); **2** — CSV есть, ошибка отправки; **1** — иная ошибка.

---

### 5. Расписание 13:20 МСК (фон)

**systemd (рекомендуется)**

```bash
cd /opt/pimex-instruments
./install_background.sh
systemctl --user list-timers spimex-daily.timer
```

Если таймер должен работать **без залогиненной сессии** (типично для VPS под одним юзером): один раз от root выполните `sudo loginctl enable-linger ВАШ_ЛОГИН`.

Для системного unit под отдельным пользователем:  
`sudo SPIMEX_RUN_USER=deploy ./install_background.sh --system`  
(файлы репозитория и `.env` должны быть доступны этому пользователю.)

Подробнее о таймере см. **`systemd/spimex-daily.timer`** (`Europe/Moscow`, 13:20). Отключить: `systemctl --user disable --now spimex-daily.timer`.

**cron** — пример строки см. **`cron.moscow.example`**.

---

### 6. Обновление и бэкап

```bash
cd /opt/pimex-instruments
git pull
.venv/bin/pip install -r requirements.txt    # если обновился requirements.txt
```

После изменения unit-скриптов перезапуск установки фона: снова **`./install_background.sh`** тем же способом (user/system).

---

### 7. Укороченно про безопасность

- **`.env`**: только `chmod 600`, не коммитить.
- По желанию: `chmod 700` на каталог проекта для одного пользователя.

---

При несовпадении времени расписания с Москвой смотрите **timer**/`CRON_TZ` в **`cron.moscow.example`**.
