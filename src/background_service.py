#!/usr/bin/env python3
"""
Фоновый сервис для копирования сделок с Binance Futures
Работает независимо от веб-интерфейса, сохраняет данные в БД
"""

import os
import sys
import time
import json
import sqlite3
import logging
import threading
import signal
from datetime import datetime
from typing import Dict, List, Optional
import websocket
import requests
from binance.client import Client
from binance.exceptions import BinanceAPIException
import schedule

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/background_service.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class DatabaseManager:
    """Менеджер базы данных для хранения данных о сделках и позициях"""
    
    def __init__(self, db_path: str = "data/trading.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица для сделок
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                source_account TEXT NOT NULL,
                target_account TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                quantity REAL NOT NULL,
                price REAL,
                order_id TEXT,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                source_order_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица для позиций
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS positions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_type TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                size REAL NOT NULL,
                entry_price REAL,
                mark_price REAL,
                pnl REAL,
                percentage REAL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(account_type, symbol)
            )
        ''')
        
        # Таблица для статистики
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date DATE DEFAULT CURRENT_DATE,
                total_trades INTEGER DEFAULT 0,
                successful_trades INTEGER DEFAULT 0,
                failed_trades INTEGER DEFAULT 0,
                total_volume REAL DEFAULT 0,
                total_pnl REAL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(date)
            )
        ''')
        
        conn.commit()
        conn.close()
        logger.info("База данных инициализирована")
    
    def save_trade(self, trade_data: Dict):
        """Сохранение информации о сделке"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO trades (source_account, target_account, symbol, side, quantity, 
                              price, order_id, status, error_message, source_order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            trade_data.get('source_account'),
            trade_data.get('target_account'),
            trade_data.get('symbol'),
            trade_data.get('side'),
            trade_data.get('quantity'),
            trade_data.get('price'),
            trade_data.get('order_id'),
            trade_data.get('status', 'pending'),
            trade_data.get('error_message'),
            trade_data.get('source_order_id')
        ))
        
        conn.commit()
        conn.close()
    
    def update_positions(self, account_type: str, positions: List[Dict]):
        """Обновление позиций в базе данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Очищаем старые позиции для этого аккаунта
        cursor.execute('DELETE FROM positions WHERE account_type = ?', (account_type,))
        
        # Добавляем новые позиции
        for pos in positions:
            if float(pos.get('positionAmt', 0)) != 0:  # Только открытые позиции
                cursor.execute('''
                    INSERT OR REPLACE INTO positions 
                    (account_type, symbol, side, size, entry_price, mark_price, pnl, percentage)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    account_type,
                    pos.get('symbol'),
                    'LONG' if float(pos.get('positionAmt', 0)) > 0 else 'SHORT',
                    abs(float(pos.get('positionAmt', 0))),
                    float(pos.get('entryPrice', 0)),
                    float(pos.get('markPrice', 0)),
                    float(pos.get('unRealizedProfit', 0)),
                    float(pos.get('percentage', 0))
                ))
        
        conn.commit()
        conn.close()
    
    def get_recent_trades(self, limit: int = 100) -> List[Dict]:
        """Получение последних сделок"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM trades 
            ORDER BY created_at DESC 
            LIMIT ?
        ''', (limit,))
        
        columns = [description[0] for description in cursor.description]
        trades = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return trades
    
    def get_positions(self, account_type: Optional[str] = None) -> List[Dict]:
        """Получение позиций"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        if account_type:
            cursor.execute('SELECT * FROM positions WHERE account_type = ?', (account_type,))
        else:
            cursor.execute('SELECT * FROM positions')
        
        columns = [description[0] for description in cursor.description]
        positions = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        conn.close()
        return positions


class BinanceWebSocketManager:
    """Менеджер WebSocket подключений к Binance"""
    
    def __init__(self, api_key: str, api_secret: str, callback=None):
        self.api_key = api_key
        self.api_secret = api_secret
        self.callback = callback
        self.ws = None
        self.listen_key = None
        self.running = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 10
        
        # Создаем клиент для получения listen key
        self.client = Client(
            api_key, 
            api_secret, 
            testnet=False,
            requests_params={'timeout': 60}
        )
    
    def get_listen_key(self):
        """Получение listen key для user data stream"""
        try:
            response = self.client.futures_stream_get_listen_key()
            return response['listenKey']
        except Exception as e:
            logger.error(f"Ошибка получения listen key: {e}")
            return None
    
    def start_user_data_stream(self):
        """Запуск user data stream"""
        self.listen_key = self.get_listen_key()
        if not self.listen_key:
            logger.error("Не удалось получить listen key")
            return False
        
        ws_url = f"wss://fstream.binance.com/ws/{self.listen_key}"
        
        try:
            self.ws = websocket.WebSocketApp(
                ws_url,
                on_message=self.on_message,
                on_error=self.on_error,
                on_close=self.on_close,
                on_open=self.on_open
            )
            
            self.running = True
            self.ws.run_forever()
            
        except Exception as e:
            logger.error(f"Ошибка WebSocket: {e}")
            return False
    
    def on_open(self, ws):
        """Обработчик открытия соединения"""
        logger.info("WebSocket соединение установлено")
        self.reconnect_attempts = 0
    
    def on_message(self, ws, message):
        """Обработчик входящих сообщений"""
        try:
            data = json.loads(message)
            
            # Обрабатываем события ордеров
            if data.get('e') == 'ORDER_TRADE_UPDATE':
                self.handle_order_update(data)
            
            # Обрабатываем события позиций
            elif data.get('e') == 'ACCOUNT_UPDATE':
                self.handle_account_update(data)
                
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
    
    def handle_order_update(self, data):
        """Обработка обновлений ордеров"""
        order_data = data.get('o', {})
        
        # Проверяем, что это новый заполненный ордер
        if order_data.get('X') == 'FILLED' and order_data.get('x') == 'TRADE':
            trade_info = {
                'symbol': order_data.get('s'),
                'side': order_data.get('S'),
                'quantity': float(order_data.get('q', 0)),
                'price': float(order_data.get('ap', 0)),  # Average price
                'order_id': order_data.get('i'),
                'timestamp': datetime.fromtimestamp(data.get('E', 0) / 1000)
            }
            
            logger.info(f"Новая сделка: {trade_info}")
            
            if self.callback:
                self.callback(trade_info)
    
    def handle_account_update(self, data):
        """Обработка обновлений аккаунта"""
        # Обновления позиций будут обрабатываться отдельно через REST API
        pass
    
    def on_error(self, ws, error):
        """Обработчик ошибок"""
        logger.error(f"WebSocket ошибка: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Обработчик закрытия соединения"""
        logger.warning(f"WebSocket соединение закрыто: {close_status_code} - {close_msg}")
        
        if self.running and self.reconnect_attempts < self.max_reconnect_attempts:
            self.reconnect_attempts += 1
            logger.info(f"Попытка переподключения #{self.reconnect_attempts}")
            time.sleep(5)
            self.start_user_data_stream()
    
    def stop(self):
        """Остановка WebSocket"""
        self.running = False
        if self.ws:
            self.ws.close()


class TradeCopyService:
    """Основной сервис копирования сделок"""
    
    def __init__(self):
        # Загрузка конфигурации
        self.load_config()
        
        # Инициализация компонентов
        self.db = DatabaseManager()
        self.running = False
        
        # Клиенты Binance с увеличенным recvWindow
        self.source_client = Client(
            self.source_api_key, 
            self.source_secret, 
            testnet=False,
            requests_params={'timeout': 60}
        )
        self.target_client = Client(
            self.target_api_key, 
            self.target_secret, 
            testnet=True,
            requests_params={'timeout': 60}
        )
        
        # WebSocket менеджер
        self.ws_manager = BinanceWebSocketManager(
            self.source_api_key, 
            self.source_secret,
            callback=self.handle_new_trade
        )
        
        # Отслеживание обработанных ордеров
        self.processed_orders = set()
        
        # Настройка обработчиков сигналов
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def load_config(self):
        """Загрузка конфигурации из .env файла"""
        from dotenv import load_dotenv
        load_dotenv()
        
        self.source_api_key = os.getenv('SOURCE_API_KEY')
        self.source_secret = os.getenv('SOURCE_SECRET_KEY')
        self.target_api_key = os.getenv('TARGET_API_KEY')
        self.target_secret = os.getenv('TARGET_SECRET_KEY')
        
        if not all([self.source_api_key, self.source_secret, self.target_api_key, self.target_secret]):
            raise ValueError("Не все API ключи настроены в .env файле")
    
    def handle_new_trade(self, trade_info: Dict):
        """Обработка новой сделки"""
        try:
            # Проверяем, не обрабатывали ли мы уже этот ордер
            order_id = trade_info.get('order_id')
            if order_id in self.processed_orders:
                return
            
            self.processed_orders.add(order_id)
            
            # Копируем сделку на тестовый аккаунт
            result = self.copy_trade(trade_info)
            
            # Сохраняем в базу данных
            trade_data = {
                'source_account': 'real',
                'target_account': 'testnet',
                'symbol': trade_info['symbol'],
                'side': trade_info['side'],
                'quantity': trade_info['quantity'],
                'price': trade_info['price'],
                'source_order_id': order_id,
                'status': 'success' if result['success'] else 'failed',
                'order_id': result.get('order_id'),
                'error_message': result.get('error')
            }
            
            self.db.save_trade(trade_data)
            
            if result['success']:
                logger.info(f"Сделка успешно скопирована: {trade_info['symbol']} {trade_info['side']} {trade_info['quantity']}")
            else:
                logger.error(f"Ошибка копирования сделки: {result.get('error')}")
                
        except Exception as e:
            logger.error(f"Ошибка обработки новой сделки: {e}")
    
    def copy_trade(self, trade_info: Dict) -> Dict:
        """Копирование сделки на тестовый аккаунт"""
        try:
            # Размещаем рыночный ордер на тестовом аккаунте
            order = self.target_client.futures_create_order(
                symbol=trade_info['symbol'],
                side=trade_info['side'],
                type='MARKET',
                quantity=trade_info['quantity'],
                recvWindow=60000
            )
            
            return {
                'success': True,
                'order_id': order['orderId']
            }
            
        except BinanceAPIException as e:
            return {
                'success': False,
                'error': f"Binance API Error: {e.message}"
            }
        except Exception as e:
            return {
                'success': False,
                'error': f"Unexpected error: {str(e)}"
            }
    
    def update_positions(self):
        """Обновление позиций в базе данных"""
        try:
            # Получаем позиции с реального аккаунта
            real_positions = self.source_client.futures_position_information(recvWindow=60000)
            self.db.update_positions('real', real_positions)
            
            # Получаем позиции с тестового аккаунта
            test_positions = self.target_client.futures_position_information(recvWindow=60000)
            self.db.update_positions('testnet', test_positions)
            
            logger.info("Позиции обновлены в базе данных")
            
        except Exception as e:
            logger.error(f"Ошибка обновления позиций: {e}")
    
    def start(self):
        """Запуск сервиса"""
        logger.info("Запуск сервиса копирования сделок...")
        
        # Проверяем подключение к API
        try:
            self.source_client.futures_account(recvWindow=60000)
            self.target_client.futures_account(recvWindow=60000)
            logger.info("Подключение к Binance API успешно")
        except Exception as e:
            logger.error(f"Ошибка подключения к API: {e}")
            return False
        
        # Получаем начальные позиции
        self.update_positions()
        
        # Настраиваем периодическое обновление позиций
        schedule.every(30).seconds.do(self.update_positions)
        
        # Запускаем WebSocket в отдельном потоке
        ws_thread = threading.Thread(target=self.ws_manager.start_user_data_stream)
        ws_thread.daemon = True
        ws_thread.start()
        
        self.running = True
        logger.info("Сервис запущен и готов к работе")
        
        # Основной цикл
        try:
            while self.running:
                schedule.run_pending()
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()
        
        return True
    
    def stop(self):
        """Остановка сервиса"""
        logger.info("Остановка сервиса...")
        self.running = False
        self.ws_manager.stop()
        logger.info("Сервис остановлен")
    
    def signal_handler(self, signum, frame):
        """Обработчик системных сигналов"""
        logger.info(f"Получен сигнал {signum}, остановка сервиса...")
        self.stop()
        sys.exit(0)


def main():
    """Главная функция"""
    # Создаем необходимые директории
    os.makedirs('logs', exist_ok=True)
    os.makedirs('data', exist_ok=True)
    
    try:
        service = TradeCopyService()
        service.start()
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

