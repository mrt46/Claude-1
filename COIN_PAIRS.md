# 💰 Coin Çiftleri Listesi

## 📋 Binance Trading Pairs

### 🔥 Popüler Major Pairs (USDT)

```env
# Major coins (En likit, en popüler)
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT
```

### 📊 Kategorize Edilmiş Listeler

#### Tier 1 - En Likit (Önerilen)
```env
# Top 10 en likit coin'ler
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT
```

#### Tier 2 - Orta Likit
```env
# İyi likidite, popüler coin'ler
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT,MATICUSDT,LINKUSDT,LTCUSDT,UNIUSDT,ATOMUSDT
```

#### Tier 3 - Geniş Portföy
```env
# Çok çeşitli coin'ler
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT,MATICUSDT,LINKUSDT,LTCUSDT,UNIUSDT,ATOMUSDT,ETCUSDT,XLMUSDT,ALGOUSDT,VETUSDT,ICPUSDT
```

### 🎯 Strateji Bazlı Öneriler

#### Konservatif (Sadece Major)
```env
# Sadece en güvenilir, en likit coin'ler
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT
```

#### Dengeli (Önerilen)
```env
# İyi likidite, çeşitli coin'ler
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT
```

#### Agresif (Geniş Portföy)
```env
# Çok sayıda coin, daha fazla fırsat
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT,MATICUSDT,LINKUSDT,LTCUSDT,UNIUSDT,ATOMUSDT,ETCUSDT,XLMUSDT,ALGOUSDT,VETUSDT,ICPUSDT,FILUSDT,TRXUSDT,EOSUSDT,AAVEUSDT
```

### 📈 Coin Kategorileri

#### Layer 1 Blockchains
```env
# Blockchain platformları
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,AVAXUSDT,ADAUSDT,DOTUSDT,ATOMUSDT,ICPUSDT,ALGOUSDT
```

#### DeFi Tokens
```env
# DeFi protokolleri
TRADING_SYMBOLS=UNIUSDT,AAVEUSDT,LINKUSDT,CAKEUSDT,SUSHIUSDT,CRVUSDT,COMPUSDT,MKRUSDT
```

#### Meme Coins
```env
# Popüler meme coin'ler
TRADING_SYMBOLS=DOGEUSDT,SHIBUSDT,FLOKIUSDT,PEPEUSDT
```

#### Gaming & Metaverse
```env
# Oyun ve metaverse coin'leri
TRADING_SYMBOLS=AXSUSDT,SANDUSDT,MANAUSDT,ENJUSDT,GALAUSDT
```

### 🌍 Bölgesel Popüler Coin'ler

#### Türkiye Popüler
```env
# Türkiye'de popüler coin'ler
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,AVAXUSDT,ADAUSDT,SOLUSDT,XRPUSDT,DOGEUSDT
```

#### Global Top 20
```env
# Market cap'e göre top 20
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,USDCUSDT,STETHUSDT,ADAUSDT,AVAXUSDT,DOGEUSDT,TRXUSDT,LINKUSDT,DOTUSDT,MATICUSDT,SHIBUSDT,DAIUSDT,LTCUSDT,BCHUSDT,UNIUSDT,ATOMUSDT
```

### ⚡ Hızlı Başlangıç Önerileri

#### Minimal (Test için)
```env
# Sadece 2 coin ile test
TRADING_SYMBOLS=BTCUSDT,ETHUSDT
```

#### Standart (Önerilen)
```env
# 5-8 coin, dengeli portföy
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT
```

#### Maksimum (Deneyimli)
```env
# 15+ coin, geniş portföy
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT,MATICUSDT,LINKUSDT,LTCUSDT,UNIUSDT,ATOMUSDT,ETCUSDT,XLMUSDT,ALGOUSDT,VETUSDT,ICPUSDT
```

### 📝 Kullanım Notları

1. **Likitlik Önemli:**
   - Daha likit coin'ler = Daha iyi fiyatlar
   - Daha az slippage
   - Daha hızlı execution

2. **Coin Sayısı:**
   - Az coin (2-5): Daha iyi odaklanma, daha az kaynak kullanımı
   - Orta (5-10): Dengeli, önerilen
   - Çok (10+): Daha fazla fırsat ama daha fazla kaynak

3. **Volatilite:**
   - Major coin'ler (BTC, ETH): Daha stabil
   - Altcoin'ler: Daha volatil, daha fazla fırsat/risk

4. **Testnet:**
   - Testnet'te tüm coin'ler mevcut olmayabilir
   - Önce testnet'te test edin

### 🔄 Coin Listesi Güncelleme

Yeni coin eklemek için:
```env
# Mevcut listeye ekleyin
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,YENICOINUSDT
```

Coin çıkarmak için:
```env
# Listeden kaldırın
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT
```

### ⚠️ Önemli Uyarılar

1. **Coin Formatı:**
   - Doğru format: `SYMBOLUSDT` (örn: BTCUSDT)
   - Yanlış: `BTC-USDT`, `BTC/USDT`, `btcusdt` (küçük harf)

2. **Mevcut Coin'ler:**
   - Binance'de mevcut olmayan coin'ler hata verir
   - Testnet'te bazı coin'ler olmayabilir

3. **Likitlik Kontrolü:**
   - Düşük likit coin'lerde slippage yüksek olabilir
   - Risk yönetimi ayarlarını kontrol edin

### 📊 Örnek .env Dosyası

```env
# Binance API
BINANCE_API_KEY=your_api_key
BINANCE_API_SECRET=your_api_secret
BINANCE_TESTNET=true

# Trading Symbols (Önerilen: 5-8 coin)
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT

# Strategy
STRATEGY_MIN_SCORE=7.0

# Risk Management
MAX_POSITIONS=5
RISK_PER_TRADE_PERCENT=2.0
```

### 🎯 Hızlı Seçim Rehberi

**Yeni başlıyorsanız:**
```env
TRADING_SYMBOLS=BTCUSDT,ETHUSDT
```

**Dengeli portföy:**
```env
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT
```

**Geniş portföy:**
```env
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,XRPUSDT,ADAUSDT,DOGEUSDT,AVAXUSDT,SHIBUSDT,DOTUSDT,MATICUSDT,LINKUSDT,LTCUSDT,UNIUSDT,ATOMUSDT
```
