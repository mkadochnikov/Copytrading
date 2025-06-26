#!/bin/bash

# Скрипт для остановки Binance Trade Copier

echo "Stopping Binance Trade Copier..."

# Переход в директорию проекта
cd "$(dirname "$0")"

# Остановка контейнеров
docker-compose down

if [ $? -eq 0 ]; then
    echo "✅ Binance Trade Copier stopped successfully!"
else
    echo "❌ Failed to stop Binance Trade Copier"
    exit 1
fi

# Показать статус
echo ""
echo "Container status:"
docker-compose ps

