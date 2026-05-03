#!/usr/bin/env bash
# Однократная установка: после enable --now таймер крутит выгрузку в фоне по расписанию.
#
# По умолчанию — systemd user timer (работает после входа; для VPS без входа см. ниже linger).
#   ./install_background.sh
#
# Для машины доступной только через SSH без графической сессии включите lingering:
#   sudo loginctl enable-linger "$USER"
# тогда user-timer будет срабатывать и когда вы не залогинены.
#
# Системная установка (от root, служба от имени пользователя):
#   sudo SPIMEX_RUN_USER=deploy ./install_background.sh --system

set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_TIMER="spimex-daily.timer"
UNIT_SERVICE="spimex-daily.service"

MODE=user
EXTRA_LINES="# (user instance — без директив User/Group)"
RUN_USER=""

usage() {
  echo "Использование: $0 [--user|--system]" >&2
  echo "  --user (по умолчанию): ~/.config/systemd/user/" >&2
  echo "  --system:              /etc/systemd/system/, нужен root" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user) MODE=user; shift ;;
    --system) MODE=system; shift ;;
    -h|--help) usage; exit 0 ;;
    *)
      echo "Неизвестный аргумент: $1" >&2
      usage
      exit 1
      ;;
  esac
done

RUN_USER="${SPIMEX_RUN_USER:-}"
if [[ "$MODE" == system ]]; then
  if [[ $EUID -ne 0 ]]; then
    echo "Режим --system: запустите через sudo или от root." >&2
    exit 1
  fi
  RUN_USER="${RUN_USER:-${SUDO_USER:-}}"
  if [[ -z "${RUN_USER}" || "${RUN_USER}" == root ]]; then
    echo "Укажите непривилегированного пользователя, например: sudo SPIMEX_RUN_USER=deploy $0 --system" >&2
    exit 1
  fi
fi

TIMER_SRC="$DIR/systemd/$UNIT_TIMER"
SERVICE_TMPL="$DIR/systemd/spimex-daily.service.template"
if [[ ! -f "$TIMER_SRC" ]] || [[ ! -f "$SERVICE_TMPL" ]]; then
  echo "Не найдены unit-файлы в $DIR/systemd/" >&2
  exit 1
fi

DEST_DIR=""
SYSTEMCTL_CMD=()
case "$MODE" in
  user)
    DEST_DIR="${HOME}/.config/systemd/user"
    SYSTEMCTL_CMD=(systemctl --user)
    ;;
  system)
    DEST_DIR="/etc/systemd/system"
    SYSTEMCTL_CMD=(systemctl)
    ;;
esac

mkdir -p "$DEST_DIR"

awk -v install_root="$DIR" -v mode="$MODE" -v run_user="$RUN_USER" '
  {
    gsub(/@INSTALL_ROOT@/, install_root)
    if ($0 ~ /__EXTRA_SERVICE_LINES__/) {
      if (mode == "system") {
        print "User=" run_user
        print "Group=" run_user
      }
      next
    }
    print
  }
' "$SERVICE_TMPL" >"$DEST_DIR/$UNIT_SERVICE"
cp "$TIMER_SRC" "$DEST_DIR/$UNIT_TIMER"

"${SYSTEMCTL_CMD[@]}" daemon-reload
"${SYSTEMCTL_CMD[@]}" enable --now "$UNIT_TIMER"

echo ""
echo "Установлено: $DEST_DIR/$UNIT_SERVICE + $DEST_DIR/$UNIT_TIMER"
echo "Ближайший запуск:"
"${SYSTEMCTL_CMD[@]}" list-timers "${UNIT_TIMER}" --no-pager || true

if [[ "$MODE" == user ]]; then
  echo ""
  echo "Если нужен запуск когда вы не авторизованы на сервере (только SSH), выполните один раз:"
  echo "  sudo loginctl enable-linger \"$USER\""
fi
