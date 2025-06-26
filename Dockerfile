# Dockerfile для Binance Trade Copier
FROM python:3.11-slim

# Создание рабочей директории
WORKDIR /app

# Копирование файлов требований
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование исходного кода
COPY src/ ./src/
COPY .env .
COPY run_streamlit.sh .

# Создание необходимых директорий
RUN mkdir -p data logs

# Установка прав на выполнение скрипта
RUN chmod +x run_streamlit.sh

# Открытие портов
EXPOSE 8501

# Переменные окружения
ENV PYTHONPATH=/app/src
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ADDRESS=0.0.0.0
ENV STREAMLIT_SERVER_HEADLESS=true

# Команда по умолчанию
CMD ["streamlit", "run", "src/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]

