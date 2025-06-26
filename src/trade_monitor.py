"""
Binance Futures Trade Monitor and Copier
Использует официальный binance-futures-connector SDK
"""

import os
import time
import json
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv
from binance.um_futures import UMFutures

# Загрузка переменных окружения
load_dotenv()

class TradeDatabase:
    """Класс для работы с локальной базой данных сделок"""
    
    def __init__(self, db_path: str = "data/trades.db"):
        self.db_path = db_path
        self.init_database()
        
    def init_database(self):
        """Инициализация базы данных"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица для отслеживания обработанных сделок
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_trades (
                    id INTEGER PRIMARY KEY,
                    trade_id INTEGER UNIQUE,
                    symbol TEXT,
                    side TEXT,
                    quantity REAL,
                    price REAL,
                    timestamp INTEGER,
                    copied BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица для хранения настроек
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def save_trade(self, trade_data: Dict[str, Any]) -> bool:
        """Сохранение сделки в базу данных"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('''
                    INSERT OR IGNORE INTO processed_trades 
                    (trade_id, symbol, side, quantity, price, timestamp)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    trade_data['id'],
                    trade_data['symbol'],
                    trade_data['side'],
                    float(trade_data['qty']),
                    float(trade_data['price']),
                    trade_data['time']
                ))
                conn.commit()
                return cursor.rowcount > 0
        except Exception as e:
            logging.error(f"Error saving trade: {e}")
            return False
    
    def is_trade_processed(self, trade_id: int) -> bool:
        """Проверка, была ли сделка уже обработана"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT 1 FROM processed_trades WHERE trade_id = ?', (trade_id,))
            return cursor.fetchone() is not None
    
    def mark_trade_copied(self, trade_id: int):
        """Отметка сделки как скопированной"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(
                'UPDATE processed_trades SET copied = TRUE WHERE trade_id = ?',
                (trade_id,)
            )
            conn.commit()
    
    def get_setting(self, key: str) -> Optional[str]:
        """Получение настройки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            result = cursor.fetchone()
            return result[0] if result else None
    
    def set_setting(self, key: str, value: str):
        """Установка настройки"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            ''', (key, value))
            conn.commit()


class BinanceTradeMonitor:
    """Мониторинг сделок на реальном аккаунте"""
    
    def __init__(self):
        self.api_key = os.getenv('REAL_API_KEY')
        self.secret_key = os.getenv('REAL_SECRET_KEY')
        
        if not self.api_key or not self.secret_key:
            raise ValueError("Real account API credentials not found")
        
        # Используем testnet для безопасности тестирования
        self.client = UMFutures(
            key=self.api_key,
            secret=self.secret_key,
            base_url="https://testnet.binancefuture.com"  # Временно используем testnet
        )
        
        self.db = TradeDatabase()
        self.logger = logging.getLogger("TradeMonitor")
        
        # Установка начального времени мониторинга
        self.start_time = self._get_start_time()
        
    def _get_start_time(self) -> int:
        """Получение времени начала мониторинга"""
        saved_time = self.db.get_setting('monitor_start_time')
        if saved_time:
            return int(saved_time)
        else:
            # Устанавливаем текущее время как начальное
            current_time = int(time.time() * 1000)
            self.db.set_setting('monitor_start_time', str(current_time))
            self.logger.info(f"Set monitor start time: {datetime.fromtimestamp(current_time/1000)}")
            return current_time
    
    def test_connection(self) -> bool:
        """Тестирование подключения"""
        try:
            server_time = self.client.time()
            self.logger.info(f"Connection successful. Server time: {server_time['serverTime']}")
            return True
        except Exception as e:
            self.logger.error(f"Connection failed: {e}")
            return False
    
    def get_account_info(self) -> Dict[str, Any]:
        """Получение информации об аккаунте"""
        try:
            return self.client.account()
        except Exception as e:
            self.logger.error(f"Failed to get account info: {e}")
            return {}
    
    def get_new_trades(self, symbol: str = "BTCUSDT") -> List[Dict[str, Any]]:
        """Получение новых сделок с момента запуска мониторинга"""
        try:
            # Получаем сделки с момента начала мониторинга
            trades = self.client.get_account_trades(
                symbol=symbol,
                startTime=self.start_time,
                limit=1000
            )
            
            # Фильтруем только новые сделки
            new_trades = []
            for trade in trades:
                if not self.db.is_trade_processed(trade['id']):
                    new_trades.append(trade)
                    self.db.save_trade(trade)
            
            if new_trades:
                self.logger.info(f"Found {len(new_trades)} new trades for {symbol}")
            
            return new_trades
            
        except Exception as e:
            self.logger.error(f"Failed to get trades for {symbol}: {e}")
            return []
    
    def get_all_symbols_trades(self) -> List[Dict[str, Any]]:
        """Получение новых сделок по всем символам"""
        all_trades = []
        
        # Список популярных символов для мониторинга
        symbols = ["BTCUSDT", "ETHUSDT", "ADAUSDT", "BNBUSDT", "XRPUSDT"]
        
        for symbol in symbols:
            trades = self.get_new_trades(symbol)
            all_trades.extend(trades)
            time.sleep(0.1)  # Небольшая задержка между запросами
        
        return all_trades


class BinanceTradeCopier:
    """Копирование сделок в тестовый аккаунт"""
    
    def __init__(self):
        self.api_key = os.getenv('TEST_API_KEY')
        self.secret_key = os.getenv('TEST_SECRET_KEY')
        
        if not self.api_key or not self.secret_key:
            raise ValueError("Test account API credentials not found")
        
        self.client = UMFutures(
            key=self.api_key,
            secret=self.secret_key,
            base_url="https://testnet.binancefuture.com"
        )
        
        self.db = TradeDatabase()
        self.logger = logging.getLogger("TradeCopier")
    
    def test_connection(self) -> bool:
        """Тестирование подключения"""
        try:
            server_time = self.client.time()
            self.logger.info(f"Test account connection successful. Server time: {server_time['serverTime']}")
            return True
        except Exception as e:
            self.logger.error(f"Test account connection failed: {e}")
            return False
    
    def copy_trade(self, trade_data: Dict[str, Any]) -> bool:
        """Копирование сделки"""
        try:
            # Создаем рыночный ордер на основе сделки
            order_params = {
                'symbol': trade_data['symbol'],
                'side': trade_data['side'],
                'type': 'MARKET',
                'quantity': float(trade_data['qty'])
            }
            
            self.logger.info(f"Copying trade: {order_params}")
            
            # Создаем ордер в тестовом аккаунте
            result = self.client.new_order(**order_params)
            
            # Отмечаем сделку как скопированную
            self.db.mark_trade_copied(trade_data['id'])
            
            self.logger.info(f"Trade copied successfully: {result['orderId']}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to copy trade: {e}")
            return False
    
    def copy_trades(self, trades: List[Dict[str, Any]]) -> int:
        """Копирование списка сделок"""
        copied_count = 0
        
        for trade in trades:
            if self.copy_trade(trade):
                copied_count += 1
                time.sleep(0.5)  # Задержка между ордерами
        
        return copied_count


def main():
    """Основная функция для тестирования"""
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/trade_copier.log'),
            logging.StreamHandler()
        ]
    )
    
    # Создание директории для логов
    os.makedirs('logs', exist_ok=True)
    
    print("=== Binance Trade Copier Test ===")
    
    # Тестирование мониторинга
    print("\n1. Testing trade monitor...")
    monitor = BinanceTradeMonitor()
    if monitor.test_connection():
        print("✓ Trade monitor connection successful")
        
        # Получение информации об аккаунте
        account_info = monitor.get_account_info()
        if account_info:
            print(f"✓ Account balance: {account_info.get('totalWalletBalance', 'N/A')} USDT")
    else:
        print("✗ Trade monitor connection failed")
    
    # Тестирование копировщика
    print("\n2. Testing trade copier...")
    copier = BinanceTradeCopier()
    if copier.test_connection():
        print("✓ Trade copier connection successful")
    else:
        print("✗ Trade copier connection failed")
    
    print("\n=== Test completed ===")


if __name__ == "__main__":
    main()

