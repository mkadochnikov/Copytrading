"""
Streamlit веб-интерфейс для мониторинга и управления копированием сделок
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import sqlite3
import os
import sys
import threading
import time
import json

# Добавляем путь к модулям
sys.path.append(os.path.join(os.path.dirname(__file__)))

from trade_monitor import BinanceTradeMonitor, BinanceTradeCopier, TradeDatabase
from main import TradeCopierService

# Настройка страницы
st.set_page_config(
    page_title="Binance Trade Copier",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Глобальные переменные для сервиса
if 'service' not in st.session_state:
    st.session_state.service = None
if 'service_thread' not in st.session_state:
    st.session_state.service_thread = None
if 'service_running' not in st.session_state:
    st.session_state.service_running = False

class StreamlitTradeCopierService(TradeCopierService):
    """Расширенный сервис для работы с Streamlit"""
    
    def __init__(self):
        # Отключаем обработчики сигналов для Streamlit
        super().__init__(setup_signals=False)
        self.status_placeholder = None
    
    def start_background(self):
        """Запуск сервиса в фоновом режиме"""
        def run():
            self.start()
        
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return thread

def load_trades_data():
    """Загрузка данных о сделках из базы данных"""
    db = TradeDatabase()
    
    try:
        with sqlite3.connect(db.db_path) as conn:
            query = """
                SELECT trade_id, symbol, side, quantity, price, timestamp, copied, created_at
                FROM processed_trades
                ORDER BY timestamp DESC
                LIMIT 1000
            """
            df = pd.read_sql_query(query, conn)
            
            if not df.empty:
                # Преобразование timestamp в datetime
                df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
                df['created_at'] = pd.to_datetime(df['created_at'])
                
                # Вычисление значения сделки
                df['value'] = df['quantity'] * df['price']
                
            return df
    except Exception as e:
        st.error(f"Ошибка загрузки данных: {e}")
        return pd.DataFrame()

def get_service_stats():
    """Получение статистики сервиса"""
    if st.session_state.service:
        return st.session_state.service.get_stats()
    return {}

def main():
    """Основная функция веб-интерфейса"""
    
    # Заголовок
    st.title("📈 Binance Futures Trade Copier")
    st.markdown("---")
    
    # Боковая панель управления
    with st.sidebar:
        st.header("🎛️ Управление")
        
        # Статус сервиса
        if st.session_state.service_running:
            st.success("🟢 Сервис запущен")
            if st.button("⏹️ Остановить сервис", type="secondary"):
                if st.session_state.service:
                    st.session_state.service.stop()
                st.session_state.service_running = False
                st.session_state.service = None
                st.rerun()
        else:
            st.error("🔴 Сервис остановлен")
            if st.button("▶️ Запустить сервис", type="primary"):
                try:
                    service = StreamlitTradeCopierService()
                    st.session_state.service = service
                    st.session_state.service_thread = service.start_background()
                    st.session_state.service_running = True
                    st.success("Сервис запущен!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Ошибка запуска: {e}")
        
        st.markdown("---")
        
        # Настройки
        st.header("⚙️ Настройки")
        
        polling_interval = st.slider(
            "Интервал опроса (сек)",
            min_value=5,
            max_value=60,
            value=10,
            step=5
        )
        
        auto_refresh = st.checkbox("Автообновление", value=True)
        
        if auto_refresh:
            refresh_interval = st.slider(
                "Интервал обновления (сек)",
                min_value=5,
                max_value=30,
                value=10,
                step=5
            )
        
        st.markdown("---")
        
        # Тестирование подключения
        st.header("🔗 Тестирование")
        
        if st.button("Тест подключения"):
            with st.spinner("Тестирование..."):
                try:
                    monitor = BinanceTradeMonitor()
                    copier = BinanceTradeCopier()
                    
                    monitor_ok = monitor.test_connection()
                    copier_ok = copier.test_connection()
                    
                    if monitor_ok and copier_ok:
                        st.success("✅ Все подключения работают")
                    else:
                        st.error("❌ Ошибка подключения")
                        
                except Exception as e:
                    st.error(f"Ошибка тестирования: {e}")
    
    # Основная область
    col1, col2, col3, col4 = st.columns(4)
    
    # Статистика
    stats = get_service_stats()
    
    with col1:
        st.metric(
            "Найдено сделок",
            stats.get('total_trades_found', 0),
            delta=None
        )
    
    with col2:
        st.metric(
            "Скопировано сделок",
            stats.get('total_trades_copied', 0),
            delta=None
        )
    
    with col3:
        st.metric(
            "Ошибки",
            stats.get('errors', 0),
            delta=None
        )
    
    with col4:
        if stats.get('last_check'):
            last_check = stats['last_check']
            if isinstance(last_check, str):
                last_check = datetime.fromisoformat(last_check.replace('Z', '+00:00'))
            st.metric(
                "Последняя проверка",
                last_check.strftime("%H:%M:%S") if last_check else "Никогда",
                delta=None
            )
        else:
            st.metric("Последняя проверка", "Никогда", delta=None)
    
    st.markdown("---")
    
    # Вкладки
    tab1, tab2, tab3, tab4 = st.tabs(["📊 Обзор", "📋 Сделки", "📈 Аналитика", "📝 Логи"])
    
    with tab1:
        st.header("Обзор системы")
        
        # Загрузка данных
        df = load_trades_data()
        
        if not df.empty:
            # Последние сделки
            st.subheader("🕒 Последние сделки")
            recent_trades = df.head(10)
            
            for _, trade in recent_trades.iterrows():
                col1, col2, col3, col4, col5 = st.columns([2, 1, 1, 1, 1])
                
                with col1:
                    st.write(f"**{trade['symbol']}**")
                
                with col2:
                    color = "🟢" if trade['side'] == 'BUY' else "🔴"
                    st.write(f"{color} {trade['side']}")
                
                with col3:
                    st.write(f"{trade['quantity']:.4f}")
                
                with col4:
                    st.write(f"${trade['price']:.2f}")
                
                with col5:
                    status = "✅" if trade['copied'] else "⏳"
                    st.write(status)
            
            # Статистика по символам
            st.subheader("📊 Статистика по символам")
            
            symbol_stats = df.groupby('symbol').agg({
                'trade_id': 'count',
                'value': 'sum',
                'copied': 'sum'
            }).round(2)
            symbol_stats.columns = ['Всего сделок', 'Общий объем', 'Скопировано']
            
            st.dataframe(symbol_stats, use_container_width=True)
            
        else:
            st.info("Данные о сделках отсутствуют")
    
    with tab2:
        st.header("Список всех сделок")
        
        df = load_trades_data()
        
        if not df.empty:
            # Фильтры
            col1, col2, col3 = st.columns(3)
            
            with col1:
                symbols = ['Все'] + list(df['symbol'].unique())
                selected_symbol = st.selectbox("Символ", symbols)
            
            with col2:
                sides = ['Все', 'BUY', 'SELL']
                selected_side = st.selectbox("Сторона", sides)
            
            with col3:
                statuses = ['Все', 'Скопировано', 'Не скопировано']
                selected_status = st.selectbox("Статус", statuses)
            
            # Применение фильтров
            filtered_df = df.copy()
            
            if selected_symbol != 'Все':
                filtered_df = filtered_df[filtered_df['symbol'] == selected_symbol]
            
            if selected_side != 'Все':
                filtered_df = filtered_df[filtered_df['side'] == selected_side]
            
            if selected_status == 'Скопировано':
                filtered_df = filtered_df[filtered_df['copied'] == True]
            elif selected_status == 'Не скопировано':
                filtered_df = filtered_df[filtered_df['copied'] == False]
            
            # Отображение таблицы
            display_df = filtered_df[['datetime', 'symbol', 'side', 'quantity', 'price', 'value', 'copied']].copy()
            display_df['copied'] = display_df['copied'].map({True: '✅', False: '⏳'})
            
            st.dataframe(
                display_df,
                use_container_width=True,
                column_config={
                    "datetime": st.column_config.DatetimeColumn("Время"),
                    "symbol": st.column_config.TextColumn("Символ"),
                    "side": st.column_config.TextColumn("Сторона"),
                    "quantity": st.column_config.NumberColumn("Количество", format="%.4f"),
                    "price": st.column_config.NumberColumn("Цена", format="$%.2f"),
                    "value": st.column_config.NumberColumn("Объем", format="$%.2f"),
                    "copied": st.column_config.TextColumn("Статус")
                }
            )
            
        else:
            st.info("Данные о сделках отсутствуют")
    
    with tab3:
        st.header("Аналитика")
        
        df = load_trades_data()
        
        if not df.empty:
            # График объемов по времени
            st.subheader("📈 Объемы сделок по времени")
            
            # Группировка по часам
            df['hour'] = df['datetime'].dt.floor('H')
            hourly_volume = df.groupby('hour')['value'].sum().reset_index()
            
            fig_volume = px.line(
                hourly_volume,
                x='hour',
                y='value',
                title='Объем сделок по часам',
                labels={'hour': 'Время', 'value': 'Объем ($)'}
            )
            st.plotly_chart(fig_volume, use_container_width=True)
            
            # Распределение по символам
            st.subheader("🥧 Распределение по символам")
            
            symbol_volume = df.groupby('symbol')['value'].sum().reset_index()
            
            fig_pie = px.pie(
                symbol_volume,
                values='value',
                names='symbol',
                title='Распределение объема по символам'
            )
            st.plotly_chart(fig_pie, use_container_width=True)
            
            # Статистика BUY/SELL
            st.subheader("⚖️ Соотношение BUY/SELL")
            
            side_stats = df.groupby('side').agg({
                'trade_id': 'count',
                'value': 'sum'
            }).reset_index()
            
            col1, col2 = st.columns(2)
            
            with col1:
                fig_count = px.bar(
                    side_stats,
                    x='side',
                    y='trade_id',
                    title='Количество сделок',
                    color='side',
                    color_discrete_map={'BUY': 'green', 'SELL': 'red'}
                )
                st.plotly_chart(fig_count, use_container_width=True)
            
            with col2:
                fig_value = px.bar(
                    side_stats,
                    x='side',
                    y='value',
                    title='Объем сделок',
                    color='side',
                    color_discrete_map={'BUY': 'green', 'SELL': 'red'}
                )
                st.plotly_chart(fig_value, use_container_width=True)
            
        else:
            st.info("Недостаточно данных для аналитики")
    
    with tab4:
        st.header("Системные логи")
        
        # Чтение логов
        log_file = "logs/trade_copier.log"
        
        if os.path.exists(log_file):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    logs = f.readlines()
                
                # Показываем последние 100 строк
                recent_logs = logs[-100:] if len(logs) > 100 else logs
                
                # Фильтр по уровню логов
                log_level = st.selectbox(
                    "Уровень логов",
                    ["Все", "ERROR", "WARNING", "INFO", "DEBUG"]
                )
                
                filtered_logs = []
                for log in recent_logs:
                    if log_level == "Все" or log_level in log:
                        filtered_logs.append(log)
                
                # Отображение логов
                log_text = "".join(filtered_logs)
                st.text_area(
                    "Логи",
                    value=log_text,
                    height=400,
                    disabled=True
                )
                
                # Кнопка очистки логов
                if st.button("🗑️ Очистить логи"):
                    try:
                        open(log_file, 'w').close()
                        st.success("Логи очищены")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ошибка очистки логов: {e}")
                        
            except Exception as e:
                st.error(f"Ошибка чтения логов: {e}")
        else:
            st.info("Файл логов не найден")
    
    # Автообновление
    if auto_refresh and st.session_state.service_running:
        time.sleep(refresh_interval)
        st.rerun()

if __name__ == "__main__":
    main()

