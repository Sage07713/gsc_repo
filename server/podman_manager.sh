#!/bin/bash

show_menu() {
    echo "================================================"
    echo "       Redpanda Server - Podman Manager"
    echo "================================================"
    echo "1. Start (build + up)"
    echo "2. Stop"
    echo "3. Restart"
    echo "4. Status"
    echo "5. Logs (all services)"
    echo "6. Logs (postgres)"
    echo "7. Logs (adminer)"
    echo "8. Logs (server)"
    echo "9. Rebuild server"
    echo "10. Clean (down + remove image)"
    echo "11. Shell into server"
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

logs_postgres() {
    podman logs -f postgres
}

logs_adminer() {
    podman logs -f adminer
}

logs_server() {
    podman logs -f server
}

rebuild_server() {
    podman-compose stop
    podman rm -f server 2>/dev/null
    podman rmi localhost/redpanda_server 2>/dev/null
    podman-compose up --build -d
}

clean() {
    podman-compose down --remove-orphans
    podman rmi localhost/redpanda_server 2>/dev/null
    echo "Done."
}

shell_server() {
    podman exec -it server sh
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
        logs_postgres)  logs_postgres ;;
        logs_adminer)  logs_adminer ;;
        logs_server)  logs_server ;;
        rebuild_server) rebuild_server ;;
        clean) clean ;;
        shell_server) shell_server ;;
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
        6)  logs_postgres ;;
        7)  logs_adminer ;;
        8)  logs_server ;;
        9)  rebuild_server ;;
        10) clean ;;
        11) shell_ingestion ;;
        0)  exit 0 ;;
        *)  echo "Error: choose a number between 0 and 12" ;;
    esac
    echo
done
