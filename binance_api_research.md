# Исследование Binance Futures API

## Ключевые находки

### Базовые URL для Binance Futures API:
- Продакшн: https://fapi.binance.com
- Тестнет: https://testnet.binancefuture.com

### Ключевые методы для получения информации о сделках:

1. **Query All Orders** - получение всех заказов аккаунта
   - Endpoint: GET /fapi/v1/allOrders
   - Тип безопасности: USER_DATA (требует API ключ и подпись)

2. **Query Account Trade List** - получение списка сделок аккаунта
   - Endpoint: GET /fapi/v1/userTrades
   - Тип безопасности: USER_DATA (требует API ключ и подпись)

3. **New Order** - создание нового заказа
   - Endpoint: POST /fapi/v1/order
   - Тип безопасности: TRADE (требует API ключ и подпись)

4. **Query Current All Open Orders** - получение всех открытых заказов
   - Endpoint: GET /fapi/v1/openOrders
   - Тип безопасности: USER_DATA

### Аутентификация:
- API ключи передаются через заголовок X-MBX-APIKEY
- Подписанные запросы требуют параметр signature (HMAC SHA256)
- Требуется параметр timestamp
- Опциональный параметр recvWindow (по умолчанию 5000 мс)

### Предоставленные API ключи:

**Реальный аккаунт:**
- API Key: Xtj39d8F667IphoMFI7ZU7lMDa5bL5kS37vSz7rUF1CT3e7xhUUhJmHP0PGnfSoY
- Secret Key: ltBEFMvrNUh91VPyiHMUVlXADoM4VvrlhiAxtEtr7WFZLpqouRiSCQNotCTGksJ6

**Тестовый аккаунт:**
- API Key: NDfpFHXaw2nfZFoh85RKQfCFxD3P1TMb75Yx1MQzg2CU9Ptm7TfZe2bqEb1SGVSW
- Secret Key: FghVxL66PAa5lS5OfSaczDNoeHynmiGZlv5RxYN9Dj2zHCCTEHLvoINaE1JQFHre

### Python SDK:
- Доступен официальный SDK: binance-futures-connector
- Установка: pip install binance-futures-connector



## Детальная информация о ключевых методах:

### 1. Query All Orders (GET /fapi/v1/allOrders)
**Назначение:** Получение всех заказов аккаунта (активных, отмененных или исполненных)

**Параметры:**
- symbol (STRING, обязательный) - торговая пара
- orderId (LONG, опциональный) - ID заказа для фильтрации
- startTime (LONG, опциональный) - начальное время
- endTime (LONG, опциональный) - конечное время
- limit (INT, опциональный) - лимит записей (по умолчанию 500, максимум 1000)
- recvWindow (LONG, опциональный)
- timestamp (LONG, обязательный)

**Ограничения:**
- Период запроса должен быть менее 7 дней
- Заказы старше 90 дней не возвращаются
- Отмененные/истекшие заказы без исполненных сделок удаляются через 3 дня

**Пример ответа:**
```json
[{
  "avgPrice": "0.00000",
  "clientOrderId": "abc",
  "cumQuote": "0",
  "executedQty": "0",
  "orderId": 1917641,
  "origQty": "0.40",
  "origType": "TRAILING_STOP_MARKET",
  "price": "0",
  "reduceOnly": false,
  "side": "BUY",
  "positionSide": "SHORT",
  "status": "NEW",
  "stopPrice": "9300",
  "closePosition": false,
  "symbol": "BTCUSDT",
  "time": 1579276756075,
  "timeInForce": "GTC",
  "type": "TRAILING_STOP_MARKET",
  "updateTime": 1579276756075,
  "workingType": "CONTRACT_PRICE"
}]
```

### 2. Query Account Trade List (GET /fapi/v1/userTrades)
**Назначение:** Получение сделок для конкретного аккаунта и символа

**Параметры:**
- symbol (STRING, обязательный) - торговая пара
- orderId (LONG, опциональный) - ID заказа (только в комбинации с symbol)
- startTime (LONG, опциональный) - начальное время
- endTime (LONG, опциональный) - конечное время
- fromId (LONG, опциональный) - ID сделки для начала выборки
- limit (INT, опциональный) - лимит записей (по умолчанию 500, максимум 1000)
- recvWindow (LONG, опциональный)
- timestamp (LONG, обязательный)

**Ограничения:**
- Если startTime и endTime не указаны, возвращаются данные за последние 7 дней
- Период между startTime и endTime не может быть больше 7 дней
- fromId нельзя использовать с startTime или endTime
- Поддерживается запрос сделок только за последние 6 месяцев

**Пример ответа:**
```json
[{
  "buyer": false,
  "commission": "-0.07819010",
  "commissionAsset": "USDT",
  "id": 698759,
  "maker": false,
  "orderId": 25851813,
  "price": "7819.01",
  "qty": "0.002",
  "quoteQty": "15.63802",
  "realizedPnl": "-0.91539999",
  "side": "SELL",
  "positionSide": "SHORT",
  "symbol": "BTCUSDT",
  "time": 1569514978020
}]
```

### 3. New Order (POST /fapi/v1/order)
**Назначение:** Создание нового заказа

**Основные параметры для копирования сделок:**
- symbol (STRING, обязательный) - торговая пара
- side (ENUM, обязательный) - BUY или SELL
- type (ENUM, обязательный) - тип заказа (MARKET, LIMIT, etc.)
- quantity (DECIMAL) - количество
- price (DECIMAL) - цена (для лимитных заказов)
- timeInForce (ENUM) - время действия заказа
- positionSide (ENUM) - сторона позиции (LONG, SHORT, BOTH)
- timestamp (LONG, обязательный)

## Архитектура решения:

1. **Модуль получения данных с реального аккаунта:**
   - Периодический опрос API для получения новых сделок
   - Сохранение данных в локальную базу данных или файл
   - Фильтрация уже обработанных сделок

2. **Модуль копирования сделок:**
   - Анализ полученных сделок
   - Создание соответствующих заказов в тестовом аккаунте
   - Логирование результатов

3. **Веб-интерфейс Streamlit:**
   - Отображение статистики сделок
   - Мониторинг состояния копирования
   - Управление настройками

4. **Docker контейнер:**
   - Изолированная среда выполнения
   - Автоматический запуск сервисов
   - Управление зависимостями



## Обновленная архитектура (с учетом копирования только новых сделок):

### Логика отслеживания новых сделок:
1. **При запуске скрипта:**
   - Получить текущий timestamp
   - Сохранить его как "точку отсчета"
   - Игнорировать все существующие ордера и сделки

2. **В процессе работы:**
   - Периодически опрашивать API для получения новых сделок
   - Фильтровать сделки по времени (только после точки отсчета)
   - Копировать только новые сделки в тестовый аккаунт

3. **Отслеживание обработанных сделок:**
   - Ведение локального журнала обработанных сделок
   - Предотвращение дублирования копирования

### Ключевые компоненты:
1. **BinanceTradeMonitor** - мониторинг реального аккаунта
2. **BinanceTradeCopier** - копирование в тестовый аккаунт  
3. **TradeDatabase** - локальное хранение данных
4. **StreamlitApp** - веб-интерфейс
5. **DockerContainer** - контейнеризация

