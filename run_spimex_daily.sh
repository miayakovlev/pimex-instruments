#!/usr/bin/env bash
# Ежедневный запуск: обновляет CSV и отправляет его на почту (настройки в .env или окружении).
# Фон и расписание 13:20 МСК без ручного crontab: ./install_background.sh
# Альтернатива: см. cron.moscow.example .
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if [[ -f "$DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$DIR/.env"
  set +a
fi

PYTHON="${SPIMEX_PYTHON:-$DIR/.venv/bin/python}"
URLS="${SPIMEX_URLS_FILE:-$DIR/urls.txt}"
OUT="${SPIMEX_OUTPUT_CSV:-$DIR/spimex_instruments.csv}"
DELAY="${SPIMEX_REQUEST_DELAY:-0.75}"

if [[ ! -f "$URLS" ]]; then
  echo "Нет файла со списком ссылок: $URLS" >&2
  exit 1
fi

exec "$PYTHON" "$DIR/spimex_export.py" -f "$URLS" -o "$OUT" --delay "$DELAY" "$@"
