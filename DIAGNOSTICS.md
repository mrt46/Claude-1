# 🔍 Trade Yapılmaması - Diagnostik Rehberi

## ❓ Neden Trade Yapılmıyor?

Bot çalışıyor ama trade yapmıyorsa, şu kontrolleri yapın:

### 1. Dashboard'da Score'ları Kontrol Edin

**Bot Activity** panelinde:
- **Last Scores:** BUY ve SELL score'ları görünüyor mu?
- **min:** Minimum threshold nedir? (örn: 7.0)
- **Result:** "✗ No Signal" mi görünüyor?

**Eğer score'lar threshold'un altındaysa:**
- Örnek: BUY: 3.2/10.0, min: 7.0 → Sinyal üretilmez
- **Çözüm:** Threshold'u düşürün veya weight'leri ayarlayın

### 2. Log Dosyalarını Kontrol Edin

Terminal'de şu mesajları arayın:

#### A. Score Mesajları
```
Final Scores: BUY=3.2/10.0, SELL=2.1/10.0
No signal: scores below threshold (7.0)
```
**Anlamı:** Score'lar threshold'un altında

#### B. Microstructure Reddi
```
Poor microstructure (spread=poor, liquidity=poor), skipping trade
```
**Anlamı:** Piyasa koşulları kötü, sinyal üretilmiyor

#### C. Risk Yönetimi Reddi
```
Trade rejected: [reason]
```
**Anlamı:** Sinyal üretildi ama risk yönetimi reddetti

### 3. Olası Nedenler ve Çözümler

#### ❌ Problem 1: Score Threshold Çok Yüksek

**Belirtiler:**
- Dashboard'da score'lar sürekli 3-5 arası
- "No signal: scores below threshold" mesajı

**Çözüm:**
`.env` dosyasında threshold'u düşürün:
```env
# Önceki
STRATEGY_MIN_SCORE=7.0

# Yeni (daha fazla sinyal için)
STRATEGY_MIN_SCORE=5.0
```

**Test:**
- Bot'u yeniden başlatın
- Dashboard'da score'ları izleyin
- 5.0'a ulaşan score'lar sinyal üretecek

#### ❌ Problem 2: Microstructure Filtresi Çok Sıkı

**Belirtiler:**
- Log'larda "Poor microstructure" mesajları
- Order book spread'i yüksek

**Çözüm:**
`src/strategies/institutional.py` içinde:
```python
# Mevcut kod (çok sıkı)
if micro['spread_quality'] == 'poor' or micro['liquidity_quality'] == 'poor':
    return None

# Daha esnek (sadece çok kötü durumlarda reddet)
if micro['spread_quality'] == 'poor' and micro['liquidity_quality'] == 'poor':
    return None
```

#### ❌ Problem 3: Risk Yönetimi Reddediyor

**Belirtiler:**
- "Trade rejected" mesajları
- Dashboard'da "Rejected" sayısı artıyor

**Olası nedenler:**
1. **Slippage çok yüksek**
   - Çözüm: `MAX_SLIPPAGE_PERCENT` artırın (örn: 0.5 → 1.0)

2. **Likitlik yetersiz**
   - Çözüm: `MIN_LIQUIDITY_USDT` düşürün (örn: 50000 → 20000)

3. **Günlük kayıp limiti**
   - Çözüm: `MAX_DAILY_LOSS_PERCENT` kontrol edin

#### ❌ Problem 4: Market Koşulları Uygun Değil

**Belirtiler:**
- Score'lar düşük ama analiz çalışıyor
- Hiçbir faktör aktif değil

**Açıklama:**
- Volume Profile: Price VAL/VAH arasında (nötr)
- Order Book: Denge (nötr)
- CVD: Divergence yok
- Supply/Demand: Zone'da değil
- HVN: Yakın değil

**Çözüm:**
- Bekleyin (market koşulları değişecek)
- Veya threshold'u düşürün (daha fazla sinyal)

### 4. Hızlı Test: Threshold'u Düşürün

**En hızlı çözüm:**

1. `.env` dosyasını açın
2. Şunu değiştirin:
```env
# Önceki
STRATEGY_MIN_SCORE=7.0

# Test için
STRATEGY_MIN_SCORE=4.0
```

3. Bot'u yeniden başlatın
4. Dashboard'da score'ları izleyin
5. 4.0'a ulaşan score'lar sinyal üretecek

**⚠️ Dikkat:** Düşük threshold = daha fazla sinyal ama daha fazla risk!

### 5. Detaylı Loglama Ekleyin

Daha fazla bilgi için log seviyesini artırın:

```python
# src/core/logger.py veya .env
LOG_LEVEL=DEBUG
```

Bu şunları gösterir:
- Her faktörün score katkısı
- Neden sinyal üretilmediği
- Risk yönetimi detayları

### 6. Dashboard'da Kontrol Listesi

**Bot Activity** panelinde kontrol edin:

- ✅ **Status:** "🟢 Running" mi?
- ✅ **Last Analysis:** Ne zaman analiz yapıldı?
- ✅ **Total Analyses:** Analiz sayısı artıyor mu?
- ✅ **Last Scores:** Score'lar görünüyor mu?
- ✅ **Result:** "✗ No Signal" mi yoksa "✓ Signal Generated" mi?

**Performance** panelinde:

- ✅ **Total Signals:** Sinyal sayısı artıyor mu?
- ✅ **Approved:** Onaylanan trade var mı?
- ✅ **Rejected:** Reddedilen trade var mı?

### 7. Manuel Test: Score'ları Kontrol Edin

Terminal'de şu mesajları arayın:

```
Analyzing BTCUSDT at 43250.00
  ✓ Price below VAL (+2.0)
  ✓ Strong buy pressure (+2.0)
Final Scores: BUY=4.0/10.0, SELL=1.0/10.0
No signal: scores below threshold (7.0)
```

**Bu örnekte:**
- BUY score: 4.0
- Threshold: 7.0
- **Sonuç:** Sinyal üretilmedi (4.0 < 7.0)

**Çözüm:** Threshold'u 4.0'a düşürün veya weight'leri artırın

### 8. Weight Optimizasyonu

Eğer score'lar sürekli düşükse, weight'leri ayarlayın:

```env
# Daha agresif (daha fazla puan)
WEIGHT_VOLUME_PROFILE=3.0
WEIGHT_ORDERBOOK=3.0
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=1.5
WEIGHT_HVN=0.5
WEIGHT_TIME_OF_DAY=0.0
```

**Toplam:** 10.0 olmalı!

### 9. Test Senaryosu

**Adım 1:** Threshold'u çok düşük yapın (test için)
```env
STRATEGY_MIN_SCORE=2.0
```

**Adım 2:** Bot'u çalıştırın

**Adım 3:** Sinyal üretiliyor mu kontrol edin

**Adım 4:** Eğer sinyal üretiliyorsa, threshold'u yavaşça artırın

**Adım 5:** Optimal threshold'u bulun

### 10. Yaygın Senaryolar

#### Senaryo 1: Hiç Sinyal Yok
- **Neden:** Threshold çok yüksek (7.0)
- **Çözüm:** 5.0'a düşürün

#### Senaryo 2: Sinyal Var Ama Trade Yok
- **Neden:** Risk yönetimi reddediyor
- **Çözüm:** Risk parametrelerini kontrol edin

#### Senaryo 3: Sinyal Var, Trade Approved Ama Pozisyon Yok
- **Neden:** Order execution hatası
- **Çözüm:** Log'larda execution hatalarını kontrol edin

---

## 🎯 Hızlı Çözüm Özeti

1. **Dashboard'da score'ları kontrol edin**
2. **Threshold'u düşürün** (test için 4.0-5.0)
3. **Log'ları kontrol edin** ("No signal" veya "Trade rejected" mesajları)
4. **Risk parametrelerini kontrol edin**
5. **Bot'u yeniden başlatın**

## 📊 Beklenen Davranış

**Normal durum:**
- Her 60 saniyede bir analiz
- Score'lar 0-10 arası
- Threshold'a ulaşan score'lar sinyal üretir
- Risk yönetimi onaylarsa trade yapılır

**Eğer hiç trade yoksa:**
- Score'lar threshold'un altında (en yaygın)
- Veya risk yönetimi reddediyor
- Veya market koşulları uygun değil
