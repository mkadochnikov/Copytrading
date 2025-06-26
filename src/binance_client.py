"""
Binance Futures API Client
Модуль для работы с Binance Futures API
"""

import os
import time
import hmac
import hashlib
import requests
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

class BinanceFuturesClient:
    """Базовый клиент для работы с Binance Futures API"""
    
    def __init__(self, api_key: str, secret_key: str, base_url: str, testnet: bool = False):
        self.api_key = api_key
        self.secret_key = secret_key
        self.base_url = base_url
        self.testnet = testnet
        self.session = requests.Session()
        self.session.headers.update({
            'X-MBX-APIKEY': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded'
        })
        
        # Настройка логирования
        self.logger = logging.getLogger(f"BinanceClient_{'testnet' if testnet else 'real'}")
        
    def _generate_signature(self, params: Dict[str, Any]) -> str:
        """Генерация подписи для запроса"""
        query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
        return hmac.new(
            self.secret_key.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
    
    def _get_timestamp(self) -> int:
        """Получение текущего timestamp в миллисекундах"""
        return int(time.time() * 1000)
    
    def _make_request(self, method: str, endpoint: str, params: Dict[str, Any] = None, signed: bool = False) -> Dict[str, Any]:
        """Выполнение HTTP запроса к API"""
        if params is None:
            params = {}
            
        url = f"{self.base_url}{endpoint}"
        
        if signed:
            params['timestamp'] = self._get_timestamp()
            params['signature'] = self._generate_signature(params)
        
        try:
            if method.upper() == 'GET':
                response = self.session.get(url, params=params, timeout=30)
            elif method.upper() == 'POST':
                response = self.session.post(url, data=params, timeout=30)
            elif method.upper() == 'DELETE':
                response = self.session.delete(url, params=params, timeout=30)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Request failed: {e}")
            raise
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to decode JSON response: {e}")
            raise
    
    def get_server_time(self) -> Dict[str, Any]:
        """Получение времени сервера"""
        return self._make_request('GET', '/fapi/v1/time')
    
    def get_exchange_info(self) -> Dict[str, Any]:
        """Получение информации о бирже"""
        return self._make_request('GET', '/fapi/v1/exchangeInfo')
    
    def get_account_info(self) -> Dict[str, Any]:
        """Получение информации об аккаунте"""
        return self._make_request('GET', '/fapi/v2/account', signed=True)
    
    def get_all_orders(self, symbol: str, start_time: Optional[int] = None, 
                      end_time: Optional[int] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Получение всех заказов"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
            
        return self._make_request('GET', '/fapi/v1/allOrders', params=params, signed=True)
    
    def get_user_trades(self, symbol: str, start_time: Optional[int] = None,
                       end_time: Optional[int] = None, limit: int = 500) -> List[Dict[str, Any]]:
        """Получение сделок пользователя"""
        params = {
            'symbol': symbol,
            'limit': limit
        }
        
        if start_time:
            params['startTime'] = start_time
        if end_time:
            params['endTime'] = end_time
            
        return self._make_request('GET', '/fapi/v1/userTrades', params=params, signed=True)
    
    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Получение открытых заказов"""
        params = {}
        if symbol:
            params['symbol'] = symbol
            
        return self._make_request('GET', '/fapi/v1/openOrders', params=params, signed=True)
    
    def create_order(self, symbol: str, side: str, order_type: str, quantity: float,
                    price: Optional[float] = None, time_in_force: str = 'GTC',
                    position_side: str = 'BOTH') -> Dict[str, Any]:
        """Создание нового заказа"""
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'quantity': quantity,
            'timeInForce': time_in_force,
            'positionSide': position_side
        }
        
        if price and order_type in ['LIMIT', 'STOP', 'TAKE_PROFIT']:
            params['price'] = price
            
        return self._make_request('POST', '/fapi/v1/order', params=params, signed=True)


class BinanceRealAccount(BinanceFuturesClient):
    """Клиент для работы с реальным аккаунтом"""
    
    def __init__(self):
        api_key = os.getenv('REAL_API_KEY')
        secret_key = os.getenv('REAL_SECRET_KEY')
        base_url = os.getenv('REAL_BASE_URL', 'https://fapi.binance.com')
        
        if not api_key or not secret_key:
            raise ValueError("Real account API credentials not found in environment variables")
            
        super().__init__(api_key, secret_key, base_url, testnet=False)


class BinanceTestAccount(BinanceFuturesClient):
    """Клиент для работы с тестовым аккаунтом"""
    
    def __init__(self):
        api_key = os.getenv('TEST_API_KEY')
        secret_key = os.getenv('TEST_SECRET_KEY')
        base_url = os.getenv('TEST_BASE_URL', 'https://testnet.binancefuture.com')
        
        if not api_key or not secret_key:
            raise ValueError("Test account API credentials not found in environment variables")
            
        super().__init__(api_key, secret_key, base_url, testnet=True)


def test_connection():
    """Тестирование подключения к API"""
    print("Testing Binance API connections...")
    
    try:
        # Тест реального аккаунта
        real_client = BinanceRealAccount()
        real_time = real_client.get_server_time()
        print(f"✓ Real account connection successful. Server time: {real_time['serverTime']}")
        
        # Тест тестового аккаунта
        test_client = BinanceTestAccount()
        test_time = test_client.get_server_time()
        print(f"✓ Test account connection successful. Server time: {test_time['serverTime']}")
        
        return True
        
    except Exception as e:
        print(f"✗ Connection test failed: {e}")
        return False


if __name__ == "__main__":
    # Настройка логирования
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Тест подключения
    test_connection()

