"""
Основной скрипт для мониторинга и копирования сделок Binance Futures
"""

import os
import time
import signal
import sys
import threading
import logging
from datetime import datetime
from typing import Dict, List
from dotenv import load_dotenv

from trade_monitor import BinanceTradeMonitor, BinanceTradeCopier, TradeDatabase

# Загрузка переменных окружения
load_dotenv()

class TradeCopierService:
    """Основной сервис для копирования сделок"""
    
    def __init__(self, setup_signals=True):
        self.monitor = BinanceTradeMonitor()
        self.copier = BinanceTradeCopier()
        self.db = TradeDatabase()
        self.logger = logging.getLogger("TradeCopierService")
        
        self.running = False
        self.polling_interval = int(os.getenv('POLLING_INTERVAL', 10))
        
        # Статистика
        self.stats = {
            'total_trades_found': 0,
            'total_trades_copied': 0,
            'errors': 0,
            'start_time': None,
            'last_check': None
        }
        
        # Настройка обработчика сигналов только если это основной поток
        if setup_signals and threading.current_thread() is threading.main_thread():
            try:
                signal.signal(signal.SIGINT, self._signal_handler)
                signal.signal(signal.SIGTERM, self._signal_handler)
            except ValueError:
                # Игнорируем ошибку если не в основном потоке
                pass
    
    def _signal_handler(self, signum, frame):
        """Обработчик сигналов для корректного завершения"""
        self.logger.info(f"Received signal {signum}, shutting down...")
        self.stop()
    
    def start(self):
        """Запуск сервиса"""
        self.logger.info("Starting Binance Trade Copier Service...")
        
        # Проверка подключений
        if not self._test_connections():
            self.logger.error("Connection tests failed, exiting...")
            return False
        
        self.running = True
        self.stats['start_time'] = datetime.now()
        
        self.logger.info(f"Service started successfully. Polling interval: {self.polling_interval}s")
        
        # Основной цикл мониторинга
        try:
            while self.running:
                self._monitoring_cycle()
                time.sleep(self.polling_interval)
        except Exception as e:
            self.logger.error(f"Unexpected error in main loop: {e}")
            self.stats['errors'] += 1
        finally:
            self.logger.info("Service stopped")
        
        return True
    
    def stop(self):
        """Остановка сервиса"""
        self.running = False
        self._print_stats()
    
    def _test_connections(self) -> bool:
        """Тестирование подключений к API"""
        self.logger.info("Testing API connections...")
        
        monitor_ok = self.monitor.test_connection()
        copier_ok = self.copier.test_connection()
        
        if monitor_ok and copier_ok:
            self.logger.info("✓ All connections successful")
            return True
        else:
            self.logger.error("✗ Connection tests failed")
            return False
    
    def _monitoring_cycle(self):
        """Один цикл мониторинга"""
        try:
            self.stats['last_check'] = datetime.now()
            
            # Получение новых сделок
            new_trades = self.monitor.get_all_symbols_trades()
            
            if new_trades:
                self.logger.info(f"Found {len(new_trades)} new trades")
                self.stats['total_trades_found'] += len(new_trades)
                
                # Копирование сделок
                copied_count = self.copier.copy_trades(new_trades)
                self.stats['total_trades_copied'] += copied_count
                
                self.logger.info(f"Copied {copied_count}/{len(new_trades)} trades")
                
                # Логирование деталей сделок
                for trade in new_trades:
                    self.logger.info(
                        f"Trade: {trade['symbol']} {trade['side']} "
                        f"{trade['qty']} @ {trade['price']} "
                        f"(ID: {trade['id']})"
                    )
            else:
                self.logger.debug("No new trades found")
                
        except Exception as e:
            self.logger.error(f"Error in monitoring cycle: {e}")
            self.stats['errors'] += 1
    
    def _print_stats(self):
        """Вывод статистики"""
        if self.stats['start_time']:
            runtime = datetime.now() - self.stats['start_time']
            
            print("\n" + "="*50)
            print("TRADE COPIER STATISTICS")
            print("="*50)
            print(f"Runtime: {runtime}")
            print(f"Total trades found: {self.stats['total_trades_found']}")
            print(f"Total trades copied: {self.stats['total_trades_copied']}")
            print(f"Errors: {self.stats['errors']}")
            print(f"Last check: {self.stats['last_check']}")
            print("="*50)
    
    def get_stats(self) -> Dict:
        """Получение статистики для веб-интерфейса"""
        stats = self.stats.copy()
        if stats['start_time']:
            stats['runtime'] = str(datetime.now() - stats['start_time'])
        return stats


def setup_logging():
    """Настройка логирования"""
    # Создание директорий
    os.makedirs('logs', exist_ok=True)
    
    # Настройка логирования
    log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
    log_file = os.getenv('LOG_FILE', 'logs/trade_copier.log')
    
    logging.basicConfig(
        level=getattr(logging, log_level),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )


def main():
    """Основная функция"""
    print("Binance Futures Trade Copier")
    print("============================")
    
    # Настройка логирования
    setup_logging()
    
    # Создание и запуск сервиса
    service = TradeCopierService()
    
    try:
        service.start()
    except KeyboardInterrupt:
        print("\nShutdown requested by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        logging.error(f"Fatal error: {e}")
    finally:
        service.stop()


if __name__ == "__main__":
    main()

