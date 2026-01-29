# 🏛️ Institutional-Grade Crypto Trading Bot

Professional-grade cryptocurrency trading bot built with Python, focusing on institutional trading strategies rather than simple retail indicators.

## 🎯 Features

- **Volume Profile Analysis**: POC, VAH/VAL, HVN/LVN detection
- **Order Book Analysis**: Imbalance, walls, liquidity depth
- **CVD (Cumulative Volume Delta)**: Buy/sell pressure tracking and divergence detection
- **Supply/Demand Zones**: Fresh vs tested zone identification
- **Market Microstructure**: Spread, slippage, execution quality analysis
- **Multi-Factor Scoring**: Weighted scoring system (minimum 7/10 threshold)
- **Risk Management**: Pre-trade validation, dynamic position sizing, zone-based stop-loss
- **Smart Order Routing**: Optimal execution strategy based on order size and liquidity

## 🏗️ Architecture

```
src/
├── core/           # Configuration and logging
├── data/           # Data acquisition and normalization
├── analysis/       # Feature engineering (VP, OB, CVD, S/D, Microstructure)
├── strategies/     # Trading strategies (Multi-factor institutional)
├── risk/           # Risk management (Validation, sizing, portfolio limits)
└── execution/      # Order execution (Router, lifecycle)
```

## 📋 Prerequisites

- Python 3.10+
- Docker Desktop (for database setup) - **Recommended**
- PostgreSQL with TimescaleDB extension (optional - can run without DB)
- Redis (optional - can run without Redis)
- Binance API credentials

## 🚀 Quick Start

### Hızlı Başlangıç (Türkçe)
Detaylı kurulum için `SETUP.md` dosyasına bakın.

```bash
# 1. Paketleri yükleyin
pip install -r requirements.txt

# 2. .env dosyası oluşturun ve API key'lerinizi ekleyin
copy .env.example .env  # Windows
# veya
cp .env.example .env    # Linux/Mac

# 3. .env dosyasını düzenleyin (BINANCE_API_KEY ve BINANCE_API_SECRET)

# 4. Testnet'te çalıştırın
python run.py
```

## 🚀 Installation (Detailed)

1. **Clone the repository**
```bash
git clone <repository-url>
cd trading-bot
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Set up databases (Optional)**

   **TimescaleDB:**
   ```sql
   CREATE DATABASE trading_bot;
   \c trading_bot;
   CREATE EXTENSION IF NOT EXISTS timescaledb;
   
   -- Create OHLCV hypertable
   CREATE TABLE ohlcv (
       time TIMESTAMPTZ NOT NULL,
       symbol TEXT NOT NULL,
       open NUMERIC NOT NULL,
       high NUMERIC NOT NULL,
       low NUMERIC NOT NULL,
       close NUMERIC NOT NULL,
       volume NUMERIC NOT NULL,
       trades INTEGER
   );
   
   SELECT create_hypertable('ohlcv', 'time');
   CREATE INDEX ON ohlcv (symbol, time DESC);
   ```

   **Redis:**
   ```bash
   # Install and start Redis
   redis-server
   ```

4. **Configure environment**

   Copy `.env.example` to `.env` and fill in your credentials:
   ```bash
   cp .env.example .env
   ```

   Edit `.env` with your settings:
   ```env
   BINANCE_API_KEY=your_api_key
   BINANCE_API_SECRET=your_api_secret
   BINANCE_TESTNET=false
   
   TIMESCALEDB_HOST=localhost
   TIMESCALEDB_PORT=5432
   TIMESCALEDB_DATABASE=trading_bot
   TIMESCALEDB_USER=postgres
   TIMESCALEDB_PASSWORD=your_password
   
   REDIS_HOST=localhost
   REDIS_PORT=6379
   REDIS_PASSWORD=
   REDIS_DB=0
   
   TRADING_SYMBOLS=BTCUSDT,ETHUSDT
   ```

5. **Run the bot**
```bash
python run.py
```

veya

```bash
python main.py
```

**Not:** İlk kullanımda mutlaka testnet'te test edin! `.env` dosyasında `BINANCE_TESTNET=true` yapın.

## ⚙️ Configuration

### Strategy Configuration

Edit strategy weights in `.env`:
```env
STRATEGY_MIN_SCORE=7.0
WEIGHT_VOLUME_PROFILE=2.0
WEIGHT_ORDERBOOK=2.0
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=2.0
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=1.0
```

### Risk Management

Configure risk parameters:
```env
MAX_POSITIONS=5
MAX_DAILY_LOSS_PERCENT=5.0
MAX_DRAWDOWN_PERCENT=15.0
MAX_SYMBOL_EXPOSURE_PERCENT=20.0
RISK_PER_TRADE_PERCENT=2.0
MAX_SLIPPAGE_PERCENT=0.5
MIN_LIQUIDITY_USDT=50000.0
```

## 📊 How It Works

### Multi-Factor Scoring System

The bot uses a weighted scoring system (0-10 points):

1. **Volume Profile Position** (Weight: 2.0)
   - Price below VAL → +2 (buy)
   - Price above VAH → +2 (sell)

2. **Order Book Imbalance** (Weight: 2.0)
   - Strong buy/sell pressure → +2
   - Moderate pressure → +1

3. **CVD Divergence** (Weight: 2.0)
   - Bullish/bearish divergence → +2

4. **Supply/Demand Zones** (Weight: 2.0)
   - In fresh zone → +2

5. **HVN Support/Resistance** (Weight: 1.0)
   - Near HVN level → +1

6. **Time & Volume** (Weight: 1.0)
   - High activity + volume surge → +1

**Minimum score for trade: 7.0/10**

### Risk Management Flow

1. **Pre-Trade Validation**
   - Microstructure quality check (spread, liquidity)
   - Slippage estimation
   - Portfolio limits check
   - Position size calculation

2. **Post-Trade Management**
   - Zone-based stop-loss
   - Trailing stop (optional)
   - Position monitoring

## 🔒 Security

- API keys stored in environment variables (never in code)
- Binance API settings:
  - Withdrawal: DISABLED
  - IP Whitelist: ENABLED (recommended)
  - Permissions: Trading only

## 📈 Performance Targets

- Signal generation: < 200ms
- Feature calculation: < 100ms
- Risk validation: < 50ms
- Total: Signal → Position < 2.5 seconds

## 🧪 Testing

### Running Unit Tests

1. **Install test dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Run all tests**
   ```bash
   pytest
   ```

3. **Run with coverage**
   ```bash
   pytest --cov=src --cov-report=html
   ```

4. **Run specific test file**
   ```bash
   pytest tests/test_analysis_volume_profile.py
   ```

5. **Run with verbose output**
   ```bash
   pytest -v
   ```

### Test Coverage

The test suite covers:
- ✅ Data normalization
- ✅ Volume profile analysis
- ✅ Order book analysis
- ✅ CVD calculation
- ✅ Position sizing
- ✅ Risk validation
- ✅ Order routing
- ✅ Order lifecycle
- ✅ Strategy base class
- ✅ Logger

### Before Live Trading

1. **Test on Binance Testnet**
   ```env
   BINANCE_TESTNET=true
   ```

2. **Paper trading mode** (implement in main.py)

3. **Backtesting** (future feature)

## 📝 Development

### Adding a New Strategy

1. Create a new file in `src/strategies/`
2. Inherit from `BaseStrategy`
3. Implement `generate_signal()` method
4. Return `Signal` object or `None`

Example:
```python
from src.strategies.base import BaseStrategy, Signal

class MyStrategy(BaseStrategy):
    async def generate_signal(self, df, **kwargs):
        # Your logic here
        return Signal(...)
```

## 🐛 Troubleshooting

### Database Connection Issues
- Verify PostgreSQL/TimescaleDB is running
- Check credentials in `.env`
- Ensure TimescaleDB extension is installed

### WebSocket Disconnections
- The bot automatically reconnects with exponential backoff
- Check network connectivity
- Verify Binance API status

### No Signals Generated
- Check minimum score threshold (default: 7.0)
- Verify market data is being received
- Review logs for analysis errors

## 📚 Documentation

- `SETUP.md` - Detailed setup guide
- `DATABASE_SETUP.md` - Database installation guide
- `THRESHOLD_GUIDE.md` - Strategy threshold and weight configuration guide
- `COIN_PAIRS.md` - Trading pairs list and recommendations
- `STRATEGY_DEVELOPMENT.md` - Strategy development and AI integration guide
- `# 🏛️ SYSTEM ARCHITECTURE.md` - Complete system architecture

## ⚠️ Disclaimer

This bot is for educational purposes. Trading cryptocurrencies involves substantial risk. Always:
- Test thoroughly on testnet first
- Start with small positions
- Monitor closely
- Never risk more than you can afford to lose

## 📄 License

[Your License Here]

## 🤝 Contributing

Contributions welcome! Please follow the coding standards:
- Type hints on all functions
- Google-style docstrings
- Async/await for I/O operations
- Comprehensive error handling
