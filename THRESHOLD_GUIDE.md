# 🎯 Threshold Ayarları Rehberi

## 📊 Strategy Threshold Ayarları

Threshold ayarları `.env` dosyasında yapılır. Bot, sinyal üretmek için minimum bir score threshold'una ihtiyaç duyar.

### 🔧 Temel Ayarlar

#### 1. Minimum Score Threshold
```env
STRATEGY_MIN_SCORE=7.0
```

**Açıklama:**
- Bot'un sinyal üretmesi için gereken minimum score
- **Varsayılan:** `7.0` (10 üzerinden)
- **Önerilen aralık:** `5.0` - `8.0`
  - `5.0` = Daha fazla sinyal (daha riskli)
  - `7.0` = Dengeli (önerilen)
  - `8.0` = Daha az sinyal (daha güvenli)

**Nasıl çalışır:**
- Her analiz sonrası BUY ve SELL için ayrı score hesaplanır
- Toplam max score = 10.0 (tüm weight'lerin toplamı)
- Sinyal üretmek için: `score >= STRATEGY_MIN_SCORE` ve `score > karşı taraf score`

**Örnek:**
```
BUY Score: 7.5/10.0
SELL Score: 3.2/10.0
STRATEGY_MIN_SCORE: 7.0

Sonuç: ✅ BUY sinyali üretilir (7.5 >= 7.0 ve 7.5 > 3.2)
```

#### 2. Weight Ayarları (Faktör Ağırlıkları)

Her analiz faktörünün ne kadar önemli olduğunu belirler:

```env
# Volume Profile (Fiyatın volume profildeki konumu)
WEIGHT_VOLUME_PROFILE=2.0

# Order Book (Alış/satış dengesi)
WEIGHT_ORDERBOOK=2.0

# CVD (Cumulative Volume Delta - Alıcı/satıcı gücü)
WEIGHT_CVD=2.0

# Supply/Demand Zones (Arz/talep bölgeleri)
WEIGHT_SUPPLY_DEMAND=2.0

# HVN Support/Resistance (Yüksek volume seviyeleri)
WEIGHT_HVN=1.0

# Time of Day + Volume (Zaman ve volume patlamaları)
WEIGHT_TIME_OF_DAY=1.0
```

**Toplam:** 2.0 + 2.0 + 2.0 + 2.0 + 1.0 + 1.0 = **10.0** (max score)

### 📈 Threshold Stratejileri

#### Konservatif (Güvenli)
```env
STRATEGY_MIN_SCORE=8.0
```
- ✅ Çok güçlü sinyaller
- ❌ Az sinyal
- 🎯 Uzun vadeli, düşük risk

#### Dengeli (Önerilen)
```env
STRATEGY_MIN_SCORE=7.0
```
- ✅ İyi kalite sinyaller
- ✅ Makul sinyal sayısı
- 🎯 Genel kullanım

#### Agresif (Daha Fazla Sinyal)
```env
STRATEGY_MIN_SCORE=5.0
```
- ✅ Çok sinyal
- ⚠️ Daha fazla risk
- 🎯 Aktif trading

### 🎛️ Weight Özelleştirme

Belirli faktörlere daha fazla önem vermek isterseniz:

#### Volume Profile Odaklı
```env
WEIGHT_VOLUME_PROFILE=3.0
WEIGHT_ORDERBOOK=2.0
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=1.5
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=0.5
# Toplam: 10.0
```

#### Order Book Odaklı
```env
WEIGHT_VOLUME_PROFILE=1.5
WEIGHT_ORDERBOOK=3.0
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=2.0
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=0.5
# Toplam: 10.0
```

#### CVD Odaklı
```env
WEIGHT_VOLUME_PROFILE=1.5
WEIGHT_ORDERBOOK=1.5
WEIGHT_CVD=3.0
WEIGHT_SUPPLY_DEMAND=2.0
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=1.0
# Toplam: 10.0
```

**⚠️ Dikkat:** Weight'lerin toplamı 10.0 olmalı, yoksa threshold oranları değişir!

### 📝 Örnek .env Dosyası

```env
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

# Database (Opsiyonel)
TIMESCALEDB_HOST=localhost
TIMESCALEDB_PORT=5432
TIMESCALEDB_DATABASE=trading_bot
TIMESCALEDB_USER=postgres
TIMESCALEDB_PASSWORD=postgres

REDIS_HOST=localhost
REDIS_PORT=6379

# Trading
TRADING_SYMBOLS=BTCUSDT,ETHUSDT

# Strategy Thresholds
STRATEGY_MIN_SCORE=7.0

# Strategy Weights
WEIGHT_VOLUME_PROFILE=2.0
WEIGHT_ORDERBOOK=2.0
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=2.0
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=1.0

# Risk Management
MAX_POSITIONS=5
MAX_DAILY_LOSS_PERCENT=5.0
RISK_PER_TRADE_PERCENT=2.0
MAX_SLIPPAGE_PERCENT=0.5
```

### 🔍 Dashboard'da Threshold Kontrolü

Dashboard'da "Bot Activity" panelinde:
- **Last Scores:** Son analiz score'ları
- **min:** Minimum threshold (STRATEGY_MIN_SCORE)
- **Result:** Sinyal üretildi mi?

**Örnek:**
```
Last Scores:
  BUY: 3.2/10.0 (min: 7.0)  ← Sarı (threshold altında)
  SELL: 2.1/10.0            ← Sarı (threshold altında)
  Result: ✗ No Signal       ← Threshold'a ulaşamadı
```

### 🎯 Threshold Optimizasyonu

1. **Başlangıç:** Varsayılan `7.0` ile başlayın
2. **Gözlem:** Dashboard'da score'ları izleyin
3. **Ayarlama:**
   - Çok az sinyal → `6.0` veya `6.5` dene
   - Çok fazla sinyal → `7.5` veya `8.0` dene
4. **Test:** Testnet'te farklı threshold'ları test edin
5. **Optimize:** Backtest sonuçlarına göre ayarlayın

### ⚠️ Önemli Notlar

1. **Threshold çok düşükse:**
   - Çok fazla sinyal → Daha fazla risk
   - Zayıf sinyaller → Daha fazla kayıp

2. **Threshold çok yüksekse:**
   - Çok az sinyal → Fırsat kaçırma
   - Sadece çok güçlü sinyaller → Daha güvenli ama az kazanç

3. **Weight'lerin toplamı:**
   - Her zaman 10.0 olmalı
   - Toplam değişirse, threshold oranları değişir

4. **Market koşulları:**
   - Volatil piyasada threshold'u artırın
   - Sakin piyasada threshold'u düşürün

### 📊 Score Hesaplama Örneği

```
Faktör 1: Volume Profile
  - Price below VAL → +2.0 (BUY)
  
Faktör 2: Order Book
  - Strong buy pressure → +2.0 (BUY)
  
Faktör 3: CVD
  - No divergence → +0.0
  
Faktör 4: Supply/Demand
  - In fresh demand zone → +2.0 (BUY)
  
Faktör 5: HVN
  - Near HVN support → +1.0 (BUY)
  
Faktör 6: Time/Volume
  - High volume + buy bias → +1.0 (BUY)

Toplam BUY Score: 8.0/10.0
Toplam SELL Score: 0.0/10.0
STRATEGY_MIN_SCORE: 7.0

Sonuç: ✅ BUY sinyali üretilir!
```

### 🔄 Değişiklikleri Uygulama

1. `.env` dosyasını düzenleyin
2. Bot'u yeniden başlatın
3. Dashboard'da yeni threshold'u göreceksiniz
4. Log'larda yeni ayarlar görünecek

```bash
# Bot'u durdurun (Ctrl+C)
# .env dosyasını düzenleyin
# Bot'u tekrar başlatın
python run.py
```
