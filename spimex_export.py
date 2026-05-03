#!/usr/bin/env python3
"""
Собирает с карточек инструментов SPIMEX (нефтепродукты):
- наименование из поля «Биржевой товар»;
- текст из поля «Базис поставки»;
- значение «Последняя» для самой поздней даты в таблице
  «Результаты последних 10 торговых сессий».

Выход: CSV (UTF-8 с BOM для Excel).

Использование данных сайта биржи — на условиях пользовательского соглашения SPIMEX;
при массовой автоматизации и коммерческом распространении сверьтесь с правилами и,
при необходимости, с официальными каналами предоставления информации.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import smtplib
import ssl
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

SESSION = requests.Session()
SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
    }
)

DATE_RE = re.compile(r"^\d{1,2}\.\d{1,2}\.\d{4}$")
BIRZHEVOI_Tovar_RE = re.compile(r"биржев(ой|ый)\s+товар", re.IGNORECASE)
BAZIS_POSTAVKI_RE = re.compile(r"базис\s+поставки", re.IGNORECASE)
SESSIONS_SECTION_RE = re.compile(
    r"Результаты последних\s+10\s+торговых\s+сессий", re.IGNORECASE
)
DETAIL_URL = (
    "https://spimex.com/markets/oil_products/instruments/list/detail.php?code="
)


def normalize_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("\xa0", " ")).strip()


def instrument_code(url_or_code: str) -> str:
    s = url_or_code.strip()
    if "://" in s or s.startswith("//"):
        q = urlparse(s).query
        parts = parse_qs(q).get("code")
        if parts and parts[0]:
            return parts[0].strip()
        raise ValueError(f"В URL не найден параметр code: {s}")
    return s.strip()


def fetch_html(code: str) -> str:
    url = DETAIL_URL + requests.utils.quote(code, safe="")
    r = SESSION.get(url, timeout=45)
    r.raise_for_status()
    # Частые кракозябры без указания кодировки
    if r.encoding is None or r.encoding.lower() == "iso-8859-1":
        r.encoding = r.apparent_encoding or "utf-8"
    return r.text


def fetch_html_playwright(code: str) -> str:
    """Страница может подставлять таблицы через JS — тогда нужен браузер."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise RuntimeError(
            "Нужен Playwright: pip install playwright && playwright install chromium"
        ) from e

    url = DETAIL_URL + requests.utils.quote(code, safe="")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=90_000)
            page.wait_for_timeout(4000)
            return page.content()
        finally:
            browser.close()


def cell_text(cell) -> str:
    return cell.get_text(" ", strip=True)


def rows_cells(table):
    """Списки текста ячеек по каждой строке (без вложенных таблиц в ячейке — редкость)."""
    out = []
    for tr in table.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        out.append([cell_text(c) for c in cells])
    return out


def extract_product_desc_cell(soup: BeautifulSoup, label_re: re.Pattern[str]) -> str | None:
    """Строка таблицы описания инструмента: первая ячейка — подпись, дальше код/ссылка и полное имя."""
    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"], recursive=False)
        if not cells:
            continue
        first = normalize_ws(cell_text(cells[0]))
        if not label_re.search(first):
            continue
        rest = [normalize_ws(cell_text(c)) for c in cells[1:] if normalize_ws(cell_text(c))]
        if not rest:
            return None
        return rest[-1]
    return None


def extract_birzhevoi_tovar(soup: BeautifulSoup) -> str | None:
    return extract_product_desc_cell(soup, BIRZHEVOI_Tovar_RE)


def extract_bazis_postavki(soup: BeautifulSoup) -> str | None:
    return extract_product_desc_cell(soup, BAZIS_POSTAVKI_RE)


def find_sessions_table(soup: BeautifulSoup):
    """
    Таблица последних торгов имеет thead с «Дата торгов», «Последняя», а не текст заголовка
    раздела (он обычно снаружи). Нельзя брать просто «следующую table» после заголовка —
    часто между ними идёт product_desc или другая разметка.
    """
    for table in soup.find_all("table"):
        tn = normalize_ws(table.get_text(" ", strip=True)).lower()
        if "последняя" not in tn or "дата торгов" not in tn:
            continue
        rows = rows_cells(table)
        if any(r for r in rows if r and DATE_RE.match(r[0].strip())):
            return table

    # Дополнительно: класс с вёрстки SPIMEX
    for table in soup.select("table.results_table"):
        tn = normalize_ws(table.get_text(" ", strip=True)).lower()
        if "последняя" in tn and rows_cells(table):
            rows = rows_cells(table)
            if any(r for r in rows if r and DATE_RE.match(r[0].strip())):
                return table

    marker_sub = "последних 10 торговых сессий"
    marker_full = "Результаты последних 10 торговых сессий"
    for tag in soup.find_all(["h2", "h3", "h4", "div", "p", "strong", "td", "th"]):
        head = normalize_ws(tag.get_text(" ", strip=True))
        if marker_full.lower() not in head.lower() and marker_sub.lower() not in head.lower():
            continue
        for table in tag.find_all_next("table", limit=8):
            tn = normalize_ws(table.get_text(" ", strip=True)).lower()
            if "последняя" in tn and "дата торгов" in tn:
                rows = rows_cells(table)
                if any(r for r in rows if r and DATE_RE.match(r[0].strip())):
                    return table
    return None


def column_index_poslednyaya(header_rows: list[list[str]]) -> int | None:
    """
    Индекс колонки «Последняя» в строках данных (td).

    У SPIMEX первая строка thead: «Дата торгов» (rowspan=2) + «Цена, руб.» (colspan=3) + объёмы;
    вторая — только «Рыночная | Первая | Последняя» без ячейки даты. Тогда индекс в подстроке цен
    нужно сдвинуть на +1 относительно второй строки заголовка.
    """
    price_head = {"рыночная", "первая", "последняя"}
    for row in header_rows:
        if not row:
            continue
        lowered = [normalize_ws(h).lower() for h in row]
        if "последняя" not in lowered:
            continue
        idx = lowered.index("последняя")
        if len(row) == 3 and all(h in price_head for h in lowered):
            return idx + 1
        return idx
    return None


def parse_sessions_last_price(table) -> tuple[str | None, str | None]:
    """
    Возвращает (дата DD.MM.YYYY, значение «Последняя») для самой поздней даты в таблице.
    """
    rows = rows_cells(table)
    if not rows:
        return None, None

    # Заголовок: 1–2 верхние строки, пока не встретим строку с датой в первом столбце.
    header_rows: list[list[str]] = []
    data_start = 0
    for i, row in enumerate(rows):
        if row and DATE_RE.match(row[0].strip()):
            data_start = i
            break
        header_rows.append(row)
        data_start = i + 1

    last_idx = column_index_poslednyaya(header_rows)
    if last_idx is None:
        # Типичная вёрстка SPIMEX: дата + три цены + объёмы (см. пример на сайте).
        last_idx = 3

    best_date: datetime | None = None
    best_last: str | None = None
    best_date_s: str | None = None

    for row in rows[data_start:]:
        if not row:
            continue
        d0 = row[0].strip()
        if not DATE_RE.match(d0):
            continue
        if last_idx >= len(row):
            continue
        try:
            d = datetime.strptime(d0, "%d.%m.%Y")
        except ValueError:
            continue
        val = row[last_idx].strip()
        if best_date is None or d > best_date:
            best_date = d
            best_last = val
            best_date_s = d0

    return best_date_s, best_last


@dataclass
class Row:
    code: str
    url: str
    birzhevoi_tovar: str | None
    bazis_postavki: str | None
    data_posledney_sessii: str | None
    tsena_poslednyaya: str | None


def extract_one(code: str, *, use_browser: bool) -> Row:
    url = DETAIL_URL + requests.utils.quote(code, safe="")
    if use_browser:
        html = fetch_html_playwright(code)
    else:
        html = fetch_html(code)
    soup = BeautifulSoup(html, "html.parser")
    commodity = extract_birzhevoi_tovar(soup)
    bazis = extract_bazis_postavki(soup)
    sess_table = find_sessions_table(soup)
    sess_date = sess_last = None
    if sess_table:
        sess_date, sess_last = parse_sessions_last_price(sess_table)

    # Пустая разметка в requests-трафике: один раз пробуем через браузер, если включено авто.
    return Row(
        code=code,
        url=url,
        birzhevoi_tovar=commodity,
        bazis_postavki=bazis,
        data_posledney_sessii=sess_date,
        tsena_poslednyaya=sess_last,
    )


def _env_bool(key: str, default: bool = False) -> bool:
    v = os.environ.get(key, "").strip().lower()
    if not v:
        return default
    return v in ("1", "true", "yes", "on")


def _mail_recipients_from_env() -> list[str]:
    raw = os.environ.get("SPIMEX_MAIL_TO", "")
    return [x.strip() for x in raw.split(",") if x.strip()]


def send_csv_email(
    csv_path: Path,
    recipients: list[str],
    *,
    subject: str | None,
) -> None:
    host = os.environ.get("SPIMEX_SMTP_HOST", "").strip()
    mail_from = os.environ.get("SPIMEX_MAIL_FROM", "").strip()
    port = int(os.environ.get("SPIMEX_SMTP_PORT", "587") or "587")
    user = os.environ.get("SPIMEX_SMTP_USER", "").strip() or None
    password = os.environ.get("SPIMEX_SMTP_PASSWORD", "").strip() or None
    use_ssl = _env_bool("SPIMEX_SMTP_USE_SSL", port == 465)

    if not host:
        raise ValueError("Для отправки почты задайте SPIMEX_SMTP_HOST")
    if not mail_from:
        raise ValueError("Задайте SPIMEX_MAIL_FROM (адрес отправителя)")
    if not recipients:
        raise ValueError("Нет получателей письма")

    msk_now = datetime.now(ZoneInfo("Europe/Moscow"))
    subj = subject or f"SPIMEX: выгрузка инструментов {msk_now:%Y-%m-%d %H:%M} МСК"

    msg = EmailMessage()
    msg["Subject"] = subj
    msg["From"] = mail_from
    msg["To"] = ", ".join(recipients)
    msg.set_content(
        f"Выгрузка SPIMEX: файл {csv_path.name} во вложении (перезаписан на сервере).\n"
        f"Отправлено {msk_now:%Y-%m-%d %H:%M:%S} МСК.\n"
    )
    data = csv_path.read_bytes()
    msg.add_attachment(
        data,
        maintype="text",
        subtype="csv",
        filename=csv_path.name,
    )

    ctx = ssl.create_default_context()
    if use_ssl:
        with smtplib.SMTP_SSL(host, port, timeout=90, context=ctx) as smtp:
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=90) as smtp:
            smtp.starttls(context=ctx)
            if user and password:
                smtp.login(user, password)
            smtp.send_message(msg)


def extract_one_smart(code: str, *, browser: bool, browser_fallback: bool) -> Row:
    if browser:
        return extract_one(code, use_browser=True)
    row = extract_one(code, use_browser=False)
    if browser_fallback and (row.birzhevoi_tovar is None or row.tsena_poslednyaya is None):
        return extract_one(code, use_browser=True)
    return row


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description="Выгрузка полей карточки инструмента SPIMEX в CSV.")
    p.add_argument(
        "items",
        nargs="*",
        help="Код инструмента или полный URL detail.php?code=...",
    )
    p.add_argument(
        "-f",
        "--file",
        metavar="PATH",
        help="Файл: по одному коду или URL в строке; пустые и # игнорируются.",
    )
    p.add_argument(
        "-o",
        "--output",
        default="spimex_instruments.csv",
        help="Путь CSV (UTF-8 с BOM). По умолчанию spimex_instruments.csv",
    )
    p.add_argument(
        "--delay",
        type=float,
        default=0.75,
        help="Пауза между запросами, сек. (умеренная нагрузка на сайт).",
    )
    p.add_argument(
        "--browser",
        action="store_true",
        help="Загружать страницу через Chromium (Playwright); нужен pip install playwright && playwright install chromium.",
    )
    p.add_argument(
        "--browser-fallback",
        action="store_true",
        help="Если после обычного запроса не найдены товар и/или «Последняя», повторить через браузер.",
    )
    p.add_argument(
        "--dump-html",
        metavar="PATH",
        help="Сохранить HTML первого инструмента для отладки и выйти (коды из аргументов/-f).",
    )
    p.add_argument(
        "--mail-to",
        action="append",
        default=[],
        metavar="EMAIL",
        help="Получатель копии CSV (можно несколько раз). Если не задано — SPIMEX_MAIL_TO в окружении.",
    )
    p.add_argument(
        "--mail-subject",
        default=None,
        help="Тема письма (иначе автоматически с датой по Москве).",
    )
    args = p.parse_args(argv)

    codes: list[str] = []
    if args.file:
        with open(args.file, encoding="utf-8") as fp:
            for line in fp:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                codes.append(instrument_code(line))
    for x in args.items:
        codes.append(instrument_code(x))

    if not codes:
        p.error("Укажите коды или URL в аргументах или через --file.")

    if args.dump_html:
        c0 = codes[0]
        try:
            html = fetch_html_playwright(c0) if args.browser else fetch_html(c0)
        except requests.RequestException as e:
            print(f"Ошибка загрузки: {e}", file=sys.stderr)
            return 1
        with open(args.dump_html, "w", encoding="utf-8") as fp:
            fp.write(html)
        print(f"HTML сохранён: {args.dump_html} (код {c0})")
        return 0

    rows_out: list[Row] = []
    for i, c in enumerate(codes):
        if i and args.delay:
            time.sleep(args.delay)
        try:
            rows_out.append(
                extract_one_smart(
                    c,
                    browser=args.browser,
                    browser_fallback=args.browser_fallback,
                ),
            )
        except requests.RequestException as e:
            rows_out.append(
                Row(
                    code=c,
                    url=DETAIL_URL + requests.utils.quote(c, safe=""),
                    birzhevoi_tovar=f"REQUEST_ERROR: {e}",
                    bazis_postavki=None,
                    data_posledney_sessii=None,
                    tsena_poslednyaya=None,
                ),
            )
        except RuntimeError as e:
            print(f"{c}: {e}", file=sys.stderr)
            rows_out.append(
                Row(
                    code=c,
                    url=DETAIL_URL + requests.utils.quote(c, safe=""),
                    birzhevoi_tovar=f"RUNTIME_ERROR: {e}",
                    bazis_postavki=None,
                    data_posledney_sessii=None,
                    tsena_poslednyaya=None,
                ),
            )

    fieldnames = [
        "code",
        "url",
        "birzhevoi_tovar",
        "bazis_postavki",
        "data_posledney_sessii",
        "tsena_poslednyaya_rub_posledniaia",
    ]
    out_path = Path(args.output)
    with open(out_path, "w", encoding="utf-8-sig", newline="") as fp:
        w = csv.DictWriter(fp, fieldnames=fieldnames)
        w.writeheader()
        for r in rows_out:
            w.writerow(
                {
                    "code": r.code,
                    "url": r.url,
                    "birzhevoi_tovar": r.birzhevoi_tovar or "",
                    "bazis_postavki": r.bazis_postavki or "",
                    "data_posledney_sessii": r.data_posledney_sessii or "",
                    "tsena_poslednyaya_rub_posledniaia": r.tsena_poslednyaya or "",
                },
            )

    print(f"Записано строк: {len(rows_out)} -> {out_path}")

    recipients = list(args.mail_to) if args.mail_to else _mail_recipients_from_env()
    if recipients:
        try:
            send_csv_email(out_path, recipients, subject=args.mail_subject)
        except (OSError, ValueError, smtplib.SMTPException) as e:
            print(f"CSV записан, но отправка почты не удалась: {e}", file=sys.stderr)
            return 2
        print(f"Письмо с вложением отправлено: {', '.join(recipients)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
