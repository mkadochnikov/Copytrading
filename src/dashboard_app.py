#!/usr/bin/env python3
"""
Dashboard для отображения данных копирования сделок
Читает данные из базы данных, созданной фоновым сервисом
"""

import streamlit as st
import pandas as pd
import sqlite3
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from datetime import datetime, timedelta
import os
import time
import json

# Настройка страницы
st.set_page_config(
    page_title="Binance Trade Copier Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

class DatabaseReader:
    """Класс для чтения данных из базы данных"""
    
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
    
    def get_connection(self):
        """Получение подключения к базе данных"""
        if not os.path.exists(self.db_path):
            st.error("База данных не найдена. Убедитесь, что фоновый сервис запущен.")
            return None
        return sqlite3.connect(self.db_path)
    
    def get_trades(self, limit: int = 100) -> pd.DataFrame:
        """Получение сделок"""
        conn = self.get_connection()
        if conn is None:
            return pd.DataFrame()
        
        query = """
            SELECT * FROM trades 
            ORDER BY created_at DESC 
            LIMIT ?
        """
        df = pd.read_sql_query(query, conn, params=(limit,))
        conn.close()
        
        if not df.empty:
            df['created_at'] = pd.to_datetime(df['created_at'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        return df
    
    def get_positions(self, account_type: str = None) -> pd.DataFrame:
        """Получение позиций"""
        conn = self.get_connection()
        if conn is None:
            return pd.DataFrame()
        
        if account_type:
            query = "SELECT * FROM positions WHERE account_type = ?"
            df = pd.read_sql_query(query, conn, params=(account_type,))
        else:
            query = "SELECT * FROM positions"
            df = pd.read_sql_query(query, conn)
        
        conn.close()
        
        if not df.empty:
            df['updated_at'] = pd.to_datetime(df['updated_at'])
        
        return df
    
    def get_statistics(self) -> pd.DataFrame:
        """Получение статистики"""
        conn = self.get_connection()
        if conn is None:
            return pd.DataFrame()
        
        query = "SELECT * FROM statistics ORDER BY date DESC"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['updated_at'] = pd.to_datetime(df['updated_at'])
        
        return df
    
    def get_trade_summary(self) -> dict:
        """Получение сводной информации о сделках"""
        conn = self.get_connection()
        if conn is None:
            return {}
        
        cursor = conn.cursor()
        
        # Общее количество сделок
        cursor.execute("SELECT COUNT(*) FROM trades")
        total_trades = cursor.fetchone()[0]
        
        # Успешные сделки
        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'success'")
        successful_trades = cursor.fetchone()[0]
        
        # Неудачные сделки
        cursor.execute("SELECT COUNT(*) FROM trades WHERE status = 'failed'")
        failed_trades = cursor.fetchone()[0]
        
        # Сделки за последние 24 часа
        cursor.execute("""
            SELECT COUNT(*) FROM trades 
            WHERE created_at >= datetime('now', '-1 day')
        """)
        trades_24h = cursor.fetchone()[0]
        
        # Общий объем
        cursor.execute("SELECT SUM(quantity * price) FROM trades WHERE status = 'success'")
        total_volume = cursor.fetchone()[0] or 0
        
        conn.close()
        
        return {
            'total_trades': total_trades,
            'successful_trades': successful_trades,
            'failed_trades': failed_trades,
            'trades_24h': trades_24h,
            'total_volume': total_volume,
            'success_rate': (successful_trades / total_trades * 100) if total_trades > 0 else 0
        }

def create_trades_chart(df: pd.DataFrame):
    """Создание графика сделок по времени"""
    if df.empty:
        return None
    
    # Группируем сделки по часам
    df_hourly = df.set_index('created_at').resample('H').size().reset_index()
    df_hourly.columns = ['hour', 'count']
    
    fig = px.line(
        df_hourly, 
        x='hour', 
        y='count',
        title='Количество сделок по времени',
        labels={'hour': 'Время', 'count': 'Количество сделок'}
    )
    
    fig.update_layout(
        xaxis_title="Время",
        yaxis_title="Количество сделок",
        hovermode='x unified'
    )
    
    return fig

def create_positions_comparison_chart(real_positions: pd.DataFrame, test_positions: pd.DataFrame):
    """Создание графика сравнения позиций"""
    if real_positions.empty and test_positions.empty:
        return None
    
    # Подготавливаем данные для сравнения
    real_symbols = set(real_positions['symbol'].tolist()) if not real_positions.empty else set()
    test_symbols = set(test_positions['symbol'].tolist()) if not test_positions.empty else set()
    all_symbols = real_symbols.union(test_symbols)
    
    comparison_data = []
    for symbol in all_symbols:
        real_size = 0
        test_size = 0
        
        if not real_positions.empty:
            real_pos = real_positions[real_positions['symbol'] == symbol]
            if not real_pos.empty:
                real_size = real_pos.iloc[0]['size']
        
        if not test_positions.empty:
            test_pos = test_positions[test_positions['symbol'] == symbol]
            if not test_pos.empty:
                test_size = test_pos.iloc[0]['size']
        
        comparison_data.append({
            'symbol': symbol,
            'real_size': real_size,
            'test_size': test_size,
            'difference': abs(real_size - test_size)
        })
    
    df_comparison = pd.DataFrame(comparison_data)
    
    fig = go.Figure()
    
    fig.add_trace(go.Bar(
        name='Реальный аккаунт',
        x=df_comparison['symbol'],
        y=df_comparison['real_size'],
        marker_color='blue'
    ))
    
    fig.add_trace(go.Bar(
        name='Тестовый аккаунт',
        x=df_comparison['symbol'],
        y=df_comparison['test_size'],
        marker_color='orange'
    ))
    
    fig.update_layout(
        title='Сравнение размеров позиций',
        xaxis_title='Символ',
        yaxis_title='Размер позиции',
        barmode='group'
    )
    
    return fig

def create_pnl_chart(positions: pd.DataFrame):
    """Создание графика PnL"""
    if positions.empty:
        return None
    
    # Фильтруем позиции с PnL
    positions_with_pnl = positions[positions['pnl'] != 0].copy()
    
    if positions_with_pnl.empty:
        return None
    
    fig = px.bar(
        positions_with_pnl,
        x='symbol',
        y='pnl',
        color='pnl',
        color_continuous_scale=['red', 'yellow', 'green'],
        title='PnL по позициям',
        labels={'symbol': 'Символ', 'pnl': 'PnL (USDT)'}
    )
    
    fig.update_layout(
        xaxis_title="Символ",
        yaxis_title="PnL (USDT)",
        showlegend=False
    )
    
    return fig

def main():
    """Главная функция dashboard"""
    
    # Заголовок
    st.title("📊 Binance Trade Copier Dashboard")
    st.markdown("---")
    
    # Инициализация базы данных
    db = DatabaseReader()
    
    # Боковая панель с настройками
    st.sidebar.header("⚙️ Настройки")
    
    # Автообновление
    auto_refresh = st.sidebar.checkbox("Автообновление (30 сек)", value=True)
    if auto_refresh:
        time.sleep(30)
        st.rerun()
    
    # Количество сделок для отображения
    trades_limit = st.sidebar.slider("Количество сделок", 10, 500, 100)
    
    # Получение данных
    trades_df = db.get_trades(trades_limit)
    real_positions_df = db.get_positions('real')
    test_positions_df = db.get_positions('testnet')
    summary = db.get_trade_summary()
    
    # Проверка наличия данных
    if not os.path.exists("data/trading.db"):
        st.error("❌ База данных не найдена!")
        st.info("Убедитесь, что фоновый сервис запущен: `python src/background_service.py`")
        return
    
    # Основные метрики
    st.header("📈 Основные метрики")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            label="Всего сделок",
            value=summary.get('total_trades', 0)
        )
    
    with col2:
        st.metric(
            label="Успешных сделок",
            value=summary.get('successful_trades', 0),
            delta=f"{summary.get('success_rate', 0):.1f}% успешность"
        )
    
    with col3:
        st.metric(
            label="За 24 часа",
            value=summary.get('trades_24h', 0)
        )
    
    with col4:
        st.metric(
            label="Общий объем",
            value=f"${summary.get('total_volume', 0):,.2f}"
        )
    
    st.markdown("---")
    
    # Вкладки
    tab1, tab2, tab3, tab4 = st.tabs(["📋 Сделки", "📊 Позиции", "📈 Аналитика", "⚙️ Статус"])
    
    with tab1:
        st.header("📋 История сделок")
        
        if not trades_df.empty:
            # Фильтры
            col1, col2, col3 = st.columns(3)
            
            with col1:
                status_filter = st.selectbox(
                    "Статус", 
                    ['Все'] + list(trades_df['status'].unique())
                )
            
            with col2:
                symbol_filter = st.selectbox(
                    "Символ",
                    ['Все'] + list(trades_df['symbol'].unique())
                )
            
            with col3:
                side_filter = st.selectbox(
                    "Сторона",
                    ['Все'] + list(trades_df['side'].unique())
                )
            
            # Применяем фильтры
            filtered_df = trades_df.copy()
            
            if status_filter != 'Все':
                filtered_df = filtered_df[filtered_df['status'] == status_filter]
            
            if symbol_filter != 'Все':
                filtered_df = filtered_df[filtered_df['symbol'] == symbol_filter]
            
            if side_filter != 'Все':
                filtered_df = filtered_df[filtered_df['side'] == side_filter]
            
            # Отображаем таблицу
            st.dataframe(
                filtered_df[['created_at', 'symbol', 'side', 'quantity', 'price', 'status']],
                use_container_width=True
            )
            
            # График сделок по времени
            trades_chart = create_trades_chart(filtered_df)
            if trades_chart:
                st.plotly_chart(trades_chart, use_container_width=True)
        else:
            st.info("Сделки не найдены")
    
    with tab2:
        st.header("📊 Текущие позиции")
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🔴 Реальный аккаунт")
            if not real_positions_df.empty:
                st.dataframe(
                    real_positions_df[['symbol', 'side', 'size', 'entry_price', 'pnl']],
                    use_container_width=True
                )
            else:
                st.info("Позиции не найдены")
        
        with col2:
            st.subheader("🟡 Тестовый аккаунт")
            if not test_positions_df.empty:
                st.dataframe(
                    test_positions_df[['symbol', 'side', 'size', 'entry_price', 'pnl']],
                    use_container_width=True
                )
            else:
                st.info("Позиции не найдены")
        
        # Сравнение позиций
        if not real_positions_df.empty or not test_positions_df.empty:
            st.subheader("🔄 Сравнение позиций")
            comparison_chart = create_positions_comparison_chart(real_positions_df, test_positions_df)
            if comparison_chart:
                st.plotly_chart(comparison_chart, use_container_width=True)
    
    with tab3:
        st.header("📈 Аналитика")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # PnL график для реального аккаунта
            if not real_positions_df.empty:
                st.subheader("💰 PnL - Реальный аккаунт")
                pnl_chart_real = create_pnl_chart(real_positions_df)
                if pnl_chart_real:
                    st.plotly_chart(pnl_chart_real, use_container_width=True)
        
        with col2:
            # PnL график для тестового аккаунта
            if not test_positions_df.empty:
                st.subheader("💰 PnL - Тестовый аккаунт")
                pnl_chart_test = create_pnl_chart(test_positions_df)
                if pnl_chart_test:
                    st.plotly_chart(pnl_chart_test, use_container_width=True)
        
        # Распределение сделок по символам
        if not trades_df.empty:
            st.subheader("📊 Распределение сделок по символам")
            symbol_counts = trades_df['symbol'].value_counts().head(10)
            
            fig_pie = px.pie(
                values=symbol_counts.values,
                names=symbol_counts.index,
                title="Топ-10 символов по количеству сделок"
            )
            st.plotly_chart(fig_pie, use_container_width=True)
    
    with tab4:
        st.header("⚙️ Статус системы")
        
        # Проверка статуса базы данных
        if os.path.exists("data/trading.db"):
            st.success("✅ База данных доступна")
            
            # Информация о последнем обновлении
            if not trades_df.empty:
                last_trade = trades_df.iloc[0]['created_at']
                st.info(f"🕒 Последняя сделка: {last_trade}")
            
            if not real_positions_df.empty:
                last_update_real = real_positions_df['updated_at'].max()
                st.info(f"🔄 Последнее обновление позиций (реальный): {last_update_real}")
            
            if not test_positions_df.empty:
                last_update_test = test_positions_df['updated_at'].max()
                st.info(f"🔄 Последнее обновление позиций (тестовый): {last_update_test}")
        else:
            st.error("❌ База данных недоступна")
        
        # Инструкции по запуску
        st.subheader("🚀 Управление сервисом")
        
        st.code("""
# Запуск фонового сервиса
python src/background_service.py

# Запуск dashboard
streamlit run src/dashboard_app.py

# Остановка сервиса
Ctrl+C или kill процесс
        """)
        
        # Информация о файлах
        st.subheader("📁 Файлы системы")
        
        files_status = []
        files_to_check = [
            "src/background_service.py",
            "src/dashboard_app.py", 
            "data/trading.db",
            "logs/background_service.log",
            ".env"
        ]
        
        for file_path in files_to_check:
            exists = os.path.exists(file_path)
            size = os.path.getsize(file_path) if exists else 0
            files_status.append({
                'Файл': file_path,
                'Статус': '✅ Существует' if exists else '❌ Отсутствует',
                'Размер': f"{size} байт" if exists else "N/A"
            })
        
        st.dataframe(pd.DataFrame(files_status), use_container_width=True)
    
    # Футер
    st.markdown("---")
    st.markdown(
        "🤖 **Binance Trade Copier Dashboard** | "
        f"Последнее обновление: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    )

if __name__ == "__main__":
    main()

