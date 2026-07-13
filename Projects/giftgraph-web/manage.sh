#!/bin/bash
# GiftGraph Web — утилита управления
# Использование: ./manage.sh {start|stop|restart|status|logs}

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
PIDFILE="$DIR/server.pid"
LOGFILE="$DIR/server.log"
PORT="${GIFTGRAPH_WEB_PORT:-5100}"

start_server() {
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "⚠️  Сервер уже запущен (PID $pid)"
            return 1
        fi
        rm -f "$PIDFILE"
    fi

    cd "$DIR"
    echo "🚀 Запуск GiftGraph Web на порту $PORT..."
    nohup python3 server.py > "$LOGFILE" 2>&1 &
    echo $! > "$PIDFILE"
    sleep 1
    if kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
        echo "✅ Сервер запущен (PID $(cat "$PIDFILE"))"
    else
        echo "❌ Сервер не запустился. Логи:"
        tail -20 "$LOGFILE"
        rm -f "$PIDFILE"
        return 1
    fi
}

stop_server() {
    if [ ! -f "$PIDFILE" ]; then
        echo "⚠️  Сервер не запущен (нет PID-файла)"
        return 1
    fi
    pid=$(cat "$PIDFILE")
    if kill -0 "$pid" 2>/dev/null; then
        echo "🛑 Остановка сервера (PID $pid)..."
        kill "$pid"
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid"
        fi
        echo "✅ Сервер остановлен"
    else
        echo "⚠️  Процесс $pid не найден"
    fi
    rm -f "$PIDFILE"
}

echo_status() {
    if [ -f "$PIDFILE" ]; then
        pid=$(cat "$PIDFILE")
        if kill -0 "$pid" 2>/dev/null; then
            echo "✅ Сервер запущен (PID $pid) на порту $PORT"
            return 0
        fi
    fi
    echo "⭕ Сервер не запущен"
    return 1
}

echo_logs() {
    if [ -f "$LOGFILE" ]; then
        tail -f "$LOGFILE"
    else
        echo "⚠️  Лог-файл не найден"
    fi
}

case "${1:-}" in
    start)   start_server ;;
    stop)    stop_server ;;
    restart) stop_server 2>/dev/null; sleep 1; start_server ;;
    status)  echo_status ;;
    logs)    echo_logs ;;
    *)
        echo "Использование: $0 {start|stop|restart|status|logs}"
        exit 1
        ;;
esac
