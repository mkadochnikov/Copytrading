#!/bin/bash

# Скрипт для сборки Docker образа Binance Trade Copier

echo "Building Binance Trade Copier Docker image..."

# Переход в директорию проекта
cd "$(dirname "$0")"

# Сборка образа
docker build -t binance-trade-copier:latest .

if [ $? -eq 0 ]; then
    echo "✅ Docker image built successfully!"
    echo "Image: binance-trade-copier:latest"
    
    # Показать размер образа
    echo "Image size:"
    docker images binance-trade-copier:latest
else
    echo "❌ Failed to build Docker image"
    exit 1
fi

