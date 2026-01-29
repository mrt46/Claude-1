# 🚀 Kurulum ve Çalıştırma Rehberi

## 📋 Ön Gereksinimler

### 1. Python Kurulumu
- Python 3.10 veya üzeri
- pip paket yöneticisi

### 2. Veritabanları (Opsiyonel)
Bot veritabanı olmadan da çalışabilir, ancak tam özellikler için:

**TimescaleDB (PostgreSQL):**
```bash
# Windows (Chocolatey)
choco install postgresql

# veya Docker
docker run -d --name timescaledb -p 5432:5432 -e POSTGRES_PASSWORD=yourpassword timescale/timescaledb:latest-pg14

# Linux
sudo apt-get install postgresql postgresql-contrib
sudo apt-get install timescaledb-2-postgresql-14
```

**Redis:**
```bash
# Windows (Chocolatey)
choco install redis-64

# veya Docker
docker run -d --name redis -p 6379:6379 redis:latest

# Linux
sudo apt-get install redis-server
```

## 🔧 Kurulum Adımları

### 1. Projeyi İndirin
```bash
git clone <repository-url>
cd trading-bot
```

### 2. Python Paketlerini Yükleyin
```bash
pip install -r requirements.txt
```

### 3. Ortam Değişkenlerini Ayarlayın

`.env` dosyası oluşturun:
```bash
# Windows
copy .env.example .env

# Linux/Mac
cp .env.example .env
```

`.env` dosyasını düzenleyin:
```env
# Binance API (ZORUNLU)
BINANCE_API_KEY=your_api_key_here
BINANCE_API_SECRET=your_api_secret_here
BINANCE_TESTNET=true  # İlk testler için true yapın!

# Veritabanları (Opsiyonel - boş bırakılabilir)
TIMESCALEDB_HOST=localhost
TIMESCALEDB_PORT=5432
TIMESCALEDB_DATABASE=trading_bot
TIMESCALEDB_USER=postgres
TIMESCALEDB_PASSWORD=your_password

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0

# Trading Ayarları
# Coin çiftleri listesi için COIN_PAIRS.md dosyasına bakın
TRADING_SYMBOLS=BTCUSDT,ETHUSDT
BASE_CURRENCY=USDT

# Strateji Ayarları
STRATEGY_MIN_SCORE=7.0
WEIGHT_VOLUME_PROFILE=2.0
WEIGHT_ORDERBOOK=2.0
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=2.0
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=1.0

# Risk Yönetimi
MAX_POSITIONS=5
MAX_DAILY_LOSS_PERCENT=5.0
MAX_DRAWDOWN_PERCENT=15.0
RISK_PER_TRADE_PERCENT=2.0
MAX_SLIPPAGE_PERCENT=0.5
MIN_LIQUIDITY_USDT=50000.0
```

### 4. Binance API Anahtarları

**Testnet için:**
1. https://testnet.binance.vision/ adresine gidin
2. API Key oluşturun
3. `.env` dosyasına ekleyin

**Gerçek API için:**
1. https://www.binance.com/en/my/settings/api-management
2. API Key oluşturun
3. **ÖNEMLİ:** Sadece "Enable Trading" iznini verin
4. IP Whitelist ekleyin (önerilir)
5. Withdrawal'ı KAPALI tutun

## ▶️ Çalıştırma

### Basit Çalıştırma
```bash
python run.py
```

veya

```bash
python main.py
```

### Test Modunda Çalıştırma
`.env` dosyasında:
```env
BINANCE_TESTNET=true
```

### Production Modunda
`.env` dosyasında:
```env
BINANCE_TESTNET=false
```

## 🧪 Test Etme

### 1. Unit Testler
```bash
pytest
```

### 2. Testnet'te Test
1. `.env` dosyasında `BINANCE_TESTNET=true` yapın
2. Testnet API key'lerini ekleyin
3. Bot'u çalıştırın
4. Logları kontrol edin

## 📊 Loglar

Loglar konsola yazılır. Dosyaya kaydetmek için `src/core/logger.py` dosyasını düzenleyin.

## ⚠️ Önemli Notlar

1. **İlk Kullanım:** Mutlaka testnet'te test edin!
2. **Risk Yönetimi:** `RISK_PER_TRADE_PERCENT` değerini düşük tutun (1-2%)
3. **Monitoring:** Bot'u sürekli izleyin
4. **API Güvenliği:** API key'lerinizi asla paylaşmayın
5. **Backup:** Önemli ayarları yedekleyin

## 🐛 Sorun Giderme

### "BINANCE_API_KEY must be set" Hatası
- `.env` dosyasının proje kök dizininde olduğundan emin olun
- API key'lerin doğru girildiğini kontrol edin

### Veritabanı Bağlantı Hatası
- Veritabanlarının çalıştığından emin olun
- `.env` dosyasındaki bilgileri kontrol edin
- Bot veritabanı olmadan da çalışabilir (sadece veri kaydedilmez)

### "ModuleNotFoundError" Hatası
```bash
pip install -r requirements.txt
```

### WebSocket Bağlantı Hatası
- İnternet bağlantınızı kontrol edin
- Firewall ayarlarını kontrol edin
- Bot otomatik olarak yeniden bağlanmaya çalışır

## 📈 Performans İzleme

Bot çalışırken:
- Logları izleyin
- Sinyal üretimini kontrol edin
- Risk limitlerini takip edin
- Pozisyonları monitör edin

## 🔄 Güncelleme

```bash
git pull
pip install -r requirements.txt --upgrade
```

## 💡 İpuçları

1. **Küçük Başlayın:** İlk başta küçük pozisyonlarla test edin
2. **Paper Trading:** Gerçek para kullanmadan önce testnet'te uzun süre test edin
3. **Monitoring:** Bot'u 7/24 izleyin (özellikle ilk haftalar)
4. **Backtesting:** Gelecekte backtesting özelliği eklenecek
5. **Optimizasyon:** Strateji ağırlıklarını piyasaya göre ayarlayın

## 📞 Destek

Sorun yaşarsanız:
1. Log dosyalarını kontrol edin
2. Testleri çalıştırın: `pytest`
3. `.env` dosyasını kontrol edin
4. GitHub Issues'da arayın
