#!/bin/bash

# Скрипт управления сервисом копирования сделок Binance
# Использование: ./service_manager.sh [start|stop|restart|status|install|uninstall|logs]

SERVICE_NAME="binance-copy-trading"
SERVICE_FILE="binance-copy-trading.service"
WORK_DIR="/home/ubuntu/Copytrading"
PYTHON_SCRIPT="src/background_service.py"
DASHBOARD_SCRIPT="src/dashboard_app.py"

# Цвета для вывода
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Функция для вывода цветного текста
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

# Проверка прав root для системных операций
check_root() {
    if [[ $EUID -eq 0 ]]; then
        return 0
    else
        return 1
    fi
}

# Установка сервиса
install_service() {
    print_info "Установка системного сервиса..."
    
    if check_root; then
        # Копируем файл сервиса
        cp "$SERVICE_FILE" "/etc/systemd/system/"
        
        # Перезагружаем systemd
        systemctl daemon-reload
        
        # Включаем автозапуск
        systemctl enable "$SERVICE_NAME"
        
        print_status "Сервис успешно установлен и настроен на автозапуск"
        print_info "Используйте: sudo systemctl start $SERVICE_NAME для запуска"
    else
        print_error "Для установки сервиса требуются права root"
        print_info "Запустите: sudo $0 install"
        exit 1
    fi
}

# Удаление сервиса
uninstall_service() {
    print_info "Удаление системного сервиса..."
    
    if check_root; then
        # Останавливаем сервис
        systemctl stop "$SERVICE_NAME" 2>/dev/null
        
        # Отключаем автозапуск
        systemctl disable "$SERVICE_NAME" 2>/dev/null
        
        # Удаляем файл сервиса
        rm -f "/etc/systemd/system/$SERVICE_FILE"
        
        # Перезагружаем systemd
        systemctl daemon-reload
        
        print_status "Сервис успешно удален"
    else
        print_error "Для удаления сервиса требуются права root"
        print_info "Запустите: sudo $0 uninstall"
        exit 1
    fi
}

# Запуск сервиса
start_service() {
    print_info "Запуск сервиса копирования сделок..."
    
    # Проверяем, установлен ли системный сервис
    if systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
        if check_root; then
            systemctl start "$SERVICE_NAME"
            print_status "Системный сервис запущен"
        else
            print_error "Для управления системным сервисом требуются права root"
            print_info "Запустите: sudo systemctl start $SERVICE_NAME"
            exit 1
        fi
    else
        # Запускаем в фоновом режиме
        print_info "Системный сервис не установлен, запускаем в фоновом режиме..."
        
        # Создаем необходимые директории
        mkdir -p "$WORK_DIR/data" "$WORK_DIR/logs"
        
        # Проверяем, не запущен ли уже процесс
        if pgrep -f "$PYTHON_SCRIPT" > /dev/null; then
            print_warning "Сервис уже запущен"
            return 0
        fi
        
        # Запускаем в фоне
        cd "$WORK_DIR"
        nohup python3 "$PYTHON_SCRIPT" > logs/service.log 2>&1 &
        
        sleep 2
        
        if pgrep -f "$PYTHON_SCRIPT" > /dev/null; then
            print_status "Сервис запущен в фоновом режиме"
            print_info "Логи: $WORK_DIR/logs/service.log"
        else
            print_error "Не удалось запустить сервис"
            exit 1
        fi
    fi
}

# Остановка сервиса
stop_service() {
    print_info "Остановка сервиса копирования сделок..."
    
    # Проверяем, установлен ли системный сервис
    if systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
        if check_root; then
            systemctl stop "$SERVICE_NAME"
            print_status "Системный сервис остановлен"
        else
            print_error "Для управления системным сервисом требуются права root"
            print_info "Запустите: sudo systemctl stop $SERVICE_NAME"
            exit 1
        fi
    else
        # Останавливаем процесс
        if pgrep -f "$PYTHON_SCRIPT" > /dev/null; then
            pkill -f "$PYTHON_SCRIPT"
            sleep 2
            
            if ! pgrep -f "$PYTHON_SCRIPT" > /dev/null; then
                print_status "Сервис остановлен"
            else
                print_warning "Принудительная остановка..."
                pkill -9 -f "$PYTHON_SCRIPT"
                print_status "Сервис принудительно остановлен"
            fi
        else
            print_warning "Сервис не запущен"
        fi
    fi
}

# Перезапуск сервиса
restart_service() {
    print_info "Перезапуск сервиса..."
    stop_service
    sleep 3
    start_service
}

# Статус сервиса
status_service() {
    print_info "Проверка статуса сервиса..."
    
    # Проверяем системный сервис
    if systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
        print_info "Статус системного сервиса:"
        systemctl status "$SERVICE_NAME" --no-pager -l
    else
        print_info "Системный сервис не установлен"
    fi
    
    # Проверяем процесс
    if pgrep -f "$PYTHON_SCRIPT" > /dev/null; then
        PID=$(pgrep -f "$PYTHON_SCRIPT")
        print_status "Сервис запущен (PID: $PID)"
        
        # Показываем информацию о процессе
        ps aux | grep "$PYTHON_SCRIPT" | grep -v grep
    else
        print_warning "Сервис не запущен"
    fi
    
    # Проверяем файлы
    echo
    print_info "Проверка файлов:"
    
    files_to_check=(
        "$WORK_DIR/.env"
        "$WORK_DIR/data/trading.db"
        "$WORK_DIR/logs/background_service.log"
    )
    
    for file in "${files_to_check[@]}"; do
        if [[ -f "$file" ]]; then
            size=$(du -h "$file" | cut -f1)
            print_status "✓ $file ($size)"
        else
            print_warning "✗ $file (отсутствует)"
        fi
    done
}

# Просмотр логов
show_logs() {
    print_info "Просмотр логов сервиса..."
    
    # Логи системного сервиса
    if systemctl list-unit-files | grep -q "$SERVICE_NAME"; then
        print_info "Логи системного сервиса (последние 50 строк):"
        journalctl -u "$SERVICE_NAME" -n 50 --no-pager
        echo
    fi
    
    # Логи файла
    if [[ -f "$WORK_DIR/logs/background_service.log" ]]; then
        print_info "Логи из файла (последние 50 строк):"
        tail -n 50 "$WORK_DIR/logs/background_service.log"
    else
        print_warning "Файл логов не найден: $WORK_DIR/logs/background_service.log"
    fi
    
    # Логи сервиса (если запущен вручную)
    if [[ -f "$WORK_DIR/logs/service.log" ]]; then
        print_info "Логи ручного запуска (последние 20 строк):"
        tail -n 20 "$WORK_DIR/logs/service.log"
    fi
}

# Запуск dashboard
start_dashboard() {
    print_info "Запуск веб-интерфейса dashboard..."
    
    cd "$WORK_DIR"
    
    # Проверяем, не запущен ли уже dashboard
    if pgrep -f "$DASHBOARD_SCRIPT" > /dev/null; then
        print_warning "Dashboard уже запущен"
        print_info "Откройте http://localhost:8501 в браузере"
        return 0
    fi
    
    # Запускаем dashboard
    print_info "Запуск Streamlit dashboard..."
    streamlit run "$DASHBOARD_SCRIPT" --server.port 8501 --server.address 0.0.0.0
}

# Показать помощь
show_help() {
    echo "Управление сервисом копирования сделок Binance"
    echo
    echo "Использование: $0 [команда]"
    echo
    echo "Команды:"
    echo "  start      - Запустить сервис"
    echo "  stop       - Остановить сервис"
    echo "  restart    - Перезапустить сервис"
    echo "  status     - Показать статус сервиса"
    echo "  logs       - Показать логи сервиса"
    echo "  install    - Установить как системный сервис (требует sudo)"
    echo "  uninstall  - Удалить системный сервис (требует sudo)"
    echo "  dashboard  - Запустить веб-интерфейс"
    echo "  help       - Показать эту справку"
    echo
    echo "Примеры:"
    echo "  $0 start                    # Запустить сервис"
    echo "  sudo $0 install             # Установить системный сервис"
    echo "  $0 dashboard                # Запустить веб-интерфейс"
    echo "  $0 status                   # Проверить статус"
    echo
}

# Основная логика
case "$1" in
    start)
        start_service
        ;;
    stop)
        stop_service
        ;;
    restart)
        restart_service
        ;;
    status)
        status_service
        ;;
    logs)
        show_logs
        ;;
    install)
        install_service
        ;;
    uninstall)
        uninstall_service
        ;;
    dashboard)
        start_dashboard
        ;;
    help|--help|-h)
        show_help
        ;;
    *)
        print_error "Неизвестная команда: $1"
        echo
        show_help
        exit 1
        ;;
esac

