#!/bin/bash

# Скрипт для запуска Binance Trade Copier в Docker

echo "Starting Binance Trade Copier..."

# Переход в директорию проекта
cd "$(dirname "$0")"

# Проверка наличия .env файла
if [ ! -f .env ]; then
    echo "❌ .env file not found!"
    echo "Please create .env file with your API credentials"
    exit 1
fi

# Создание необходимых директорий
mkdir -p data logs

# Запуск с помощью docker-compose
echo "Starting with docker-compose..."
docker-compose up -d

if [ $? -eq 0 ]; then
    echo "✅ Binance Trade Copier started successfully!"
    echo ""
    echo "🌐 Web interface: http://localhost:8501"
    echo "📊 Monitor logs: docker-compose logs -f"
    echo "⏹️  Stop service: docker-compose down"
    echo ""
    echo "Container status:"
    docker-compose ps
else
    echo "❌ Failed to start Binance Trade Copier"
    exit 1
fi

