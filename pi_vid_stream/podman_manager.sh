#!/bin/bash

show_menu() {
    echo "================================================"
    echo "     Redpanda Video Stream - Podman Manager"
    echo "================================================"
    echo "1. Start (build + up)"
    echo "2. Stop"
    echo "3. Restart"
    echo "4. Status"
    echo "5. Logs (all services)"
    echo "6. Logs (stream)"
    echo "7. Rebuild streamer"
    echo "8. Clean (down + remove image)"
    echo "9. Shell into streamer"
    echo "0. Exit"
    echo "================================================"
}

start() {
    podman-compose up --build -d
}

stop() {
    podman-compose stop
}

restart() {
    podman-compose stop
    podman-compose up --build -d
}

status() {
    podman ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
}

logs_all() {
    podman-compose logs -f
}
logs_stream() {
    podman logs -f vid-stream
}

rebuild_stream() {
    podman-compose stop
    podman rm -f server 2>/dev/null
    podman rmi localhost/vid-stream 2>/dev/null
    podman-compose up --build -d
}

clean() {
    podman-compose down --remove-orphans
    podman rmi localhost/vid-stream 2>/dev/null
    echo "Done."
}

shell_stream() {
    podman exec -it vid-stream sh
}

prune() {
    podman image prune -f
}

if [ -n "$1" ]; then
    case $1 in
        start)  start ;;
        stop)  stop ;;
        restart)  restart ;;
        status)  status ;;
        logs_all)  logs_all ;;
        logs_stream)  logs_stream ;;
        rebuild_stream) rebuild_stream ;;
        clean) clean ;;
        shell_stream) shell_stream ;;
        *) echo "Usage: $0 {start|stop|restart|status|logs_all|logs_postgres|logs_adminer|logs_server|rebuild_server|clean|shell_server}" ;;
    esac
    exit 0
fi

while true; do
    show_menu
    read -p "Choice: " choice
    case $choice in
        1)  start ;;
        2)  stop ;;
        3)  restart ;;
        4)  status ;;
        5)  logs_all ;;
        6)  logs_stream ;;
        7)  rebuild_stream ;;
        8)  clean ;;
        9)  shell_stream ;;
        0)  exit 0 ;;
        *)  echo "Error: choose a number between 0 and 12" ;;
    esac
    echo
done
