# SPIMEX Instruments Export

Небольшой набор скриптов для **автоматической выгрузки данных** с публичных карточек инструментов **рынка нефтепродуктов** Санкт-Петербургской международной товарно-сырьевой биржи ([spimex.com](https://spimex.com/)): по списку кодов или полных ссылок вида `detail.php?code=...` обновляются файлы на диске, при необходимости **отчёт отправляется по SMTP**. На сервере Linux расписание задаётся через **systemd timer** (раз в сутки в **13:20 по Москве**) или через **cron**.

**Репозиторий:** [github.com/miayakovlev/pimex-instruments](https://github.com/miayakovlev/pimex-instruments) — установка: `git clone` и настройка `.env`; пошагово в **[INSTALL.md](INSTALL.md)**. Подготовка чистой ВМ: **[OC.md](OC.md)**.

## Задача

Вручную из карточки инструмента собирали бы:

- полное наименование по полю **«Биржевой товар»**;
- текст по полю **«Базис поставки»**;
- для таблицы **«Результаты последних 10 торговых сессий»** — значение колонки **«Последняя»** по **самой поздней дате** торгов.

Скрипт повторяет это для каждой строки списка и пишет результат в файлы (см. ниже). При ошибках HTTP/парсинга в CSV попадает строка с префиксом `REQUEST_ERROR:` / `RUNTIME_ERROR:` в поле товара; детали — в stderr.

## Выходные данные

| Файл (по умолчанию) | Описание |
|---------------------|----------|
| `spimex_instruments.csv` | **Wide-CSV**, UTF-8 с BOM: базовые столбцы + колонки дат запуска (**МСК**) с ценой «Последняя» (или fallback из последних сессий, если за текущую дату в таблице нет строки) |
| `spimex_price_history.csv` | Накопленная история дат и цен |
| `spimex_prices_hist.png` | Гистограмма (нужен **matplotlib** из `requirements.txt`) |
| `spimex_report.xlsx` | Excel с таблицей и графиками (нужен **openpyxl**) |

Базовые столбцы wide-CSV: `code`, `url`, `birzhevoi_tovar`, `bazis_postavki`, далее колонки вида **`ДД.MM.ГГГГ`**. Имя основного CSV по умолчанию: `spimex_instruments.csv`.

## Состав проекта

| Файл / каталог | Назначение |
|----------------|------------|
| `spimex_export.py` | HTTP, парсинг HTML, запись CSV/истории, PNG, XLSX, опционально SMTP |
| `requirements.txt` | `requests`, `beautifulsoup4`, `matplotlib`, `openpyxl` |
| `urls.txt` | Список URL или кодов (пример; правьте под себя) |
| `run_spimex_daily.sh` | Подхватывает `.env`, вызывает `spimex_export.py` |
| `install_background.sh` | Установка **systemd timer** (13:20 МСК) |
| `systemd/` | Шаблоны unit-файлов |
| `env.example`, `env.rambler.example` | Примеры `.env` |
| `cron.moscow.example` | Пример cron, если не systemd |

`.env` и `.venv/` не коммитятся — см. `.gitignore`.

## Быстрый ручной запуск

```bash
.venv/bin/python spimex_export.py -f urls.txt -o spimex_instruments.csv
```

С почтой (SMTP из `.env`, получатель из аргумента или `SPIMEX_MAIL_TO`):

```bash
set -a && source .env && set +a
.venv/bin/python spimex_export.py -f urls.txt -o spimex_instruments.csv --mail-to получатель@example.com
```

Гистограмма и Excel формируются автоматически при установленных зависимостях; пути: `--histogram-output`, `--report-output`, `--history-output`. Полный список ключей: `spimex_export.py --help` (в т.ч. `--delay`, `--browser`, `--browser-fallback`, `--dump-html`).

Переменные `.env` для путей и задержки: `SPIMEX_URLS_FILE`, `SPIMEX_OUTPUT_CSV`, `SPIMEX_REQUEST_DELAY`, `SPIMEX_PYTHON` — см. `env.example` и **`run_spimex_daily.sh`**.

## Почта

Если заданы получатели и SMTP, скрипт отправляет письмо с **вложением Excel** — файл **`--report-output`** (по умолчанию `spimex_report.xlsx`), а не CSV. Порт **587** обычно с STARTTLS; для **465** задайте `SPIMEX_SMTP_USE_SSL=1` (пример в `env.rambler.example`).

**Коды выхода:** **0** — успех; **1** — выгрузка с ошибками по части кодов; **2** — файлы записаны, но отправка почты не удалась.

## Расписание на сервере

Раз в сутки в **13:20 МСК** — **`run_spimex_daily.sh`**; установка: **`install_background.sh`**, подробности в **[INSTALL.md](INSTALL.md)**. Без systemd — **`cron.moscow.example`**.

## Ограничения и юридическая сторона

Использование данных сайта биржи (в т.ч. автоматическое скачивание) может регулироваться соглашениями SPIMEX. Проект рассчитан на внутренний офисный сценарий.

## Если что-то ломается

- Сайт или вёрстка изменились — попробуйте **`--browser-fallback`** и **Playwright** (`pip install playwright`, `playwright install chromium`), см. **[OC.md](OC.md)**.
- Отладка HTML: **`--dump-html путь`** для первого инструмента из списка.
