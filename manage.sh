#!/usr/bin/env bash
# Быстрое управление GiftGraph Bot для тестов.
#
#   ./manage.sh start     — запустить бота в фоне
#   ./manage.sh stop      — остановить бота
#   ./manage.sh restart   — перезапустить
#   ./manage.sh status    — статус (запущен/остановлен + PID)
#   ./manage.sh logs      — последние логи (live, Ctrl+C для выхода)
#   ./manage.sh version   — показать build-tag текущего кода
#
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

PYTHON="${PYTHON:-"$DIR/.venv/bin/python"}"
PID_FILE="$DIR/bot.pid"
LOG_FILE="$DIR/bot.out.log"

is_running() {
  [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null
}

cleanup_stale_pid() {
  if [[ -f "$PID_FILE" ]] && ! kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    rm -f "$PID_FILE"
  fi
}

start() {
  cleanup_stale_pid
  if is_running; then
    echo "✅ Бот уже запущен (PID $(cat "$PID_FILE"))."
    return 0
  fi
  echo "▶️  Запускаю бота..."
  rm -f "$PID_FILE"
  nohup "$PYTHON" main.py >"$LOG_FILE" 2>&1 &
  echo $! >"$PID_FILE"
  for _ in $(seq 1 15); do
    if is_running; then
      break
    fi
    sleep 1
  done
  if is_running; then
    echo "✅ Запущен (PID $(cat "$PID_FILE")). Логи: ./manage.sh logs"
    return 0
  fi
  echo "❌ Не удалось запустить. Последние строки лога:"
  tail -n 20 "$LOG_FILE" || true
  rm -f "$PID_FILE"
  return 1
}

stop() {
  if is_running; then
    PID="$(cat "$PID_FILE")"
    echo "⏹  Останавливаю (PID $PID)..."
    kill "$PID" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "$PID" 2>/dev/null || break
      sleep 0.5
    done
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
    echo "✅ Остановлен."
  else
    echo "ℹ️  Бот не запущен."
    rm -f "$PID_FILE"
  fi
}

status() {
  cleanup_stale_pid
  if is_running; then
    echo "✅ Запущен (PID $(cat "$PID_FILE"))."
  else
    echo "⏹  Остановлен."
  fi
}

version() {
  python3 - <<'PY'
from pathlib import Path
import re
text = Path('main.py').read_text(encoding='utf-8')
m = re.search(r'BUILD_TAG\s*=\s*"([^"]+)"', text)
print(m.group(1) if m else 'unknown')
PY
}

logs() {
  touch "$LOG_FILE"
  tail -n 40 -f "$LOG_FILE"
}

case "${1:-}" in
  start)   start ;;
  stop)    stop ;;
  restart) stop; start ;;
  status)  status ;;
  logs)    logs ;;
  version) version ;;
  *) echo "Использование: ./manage.sh {start|stop|restart|status|logs|version}"; exit 1 ;;
esac
