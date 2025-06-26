#!/bin/bash

# Скрипт запуска Streamlit приложения для Binance Trade Copier

echo "Starting Binance Trade Copier Web Interface..."

# Переход в директорию проекта
cd "$(dirname "$0")"

# Создание необходимых директорий
mkdir -p data logs

# Запуск Streamlit приложения
streamlit run src/streamlit_app.py \
    --server.port 8501 \
    --server.address 0.0.0.0 \
    --server.headless true \
    --server.enableCORS false \
    --server.enableXsrfProtection false

