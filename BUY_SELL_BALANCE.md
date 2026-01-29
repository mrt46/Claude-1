# ⚖️ BUY/SELL Dengesi Rehberi

## 🔍 Sorun: Sadece SELL Sinyalleri Üretiliyor

Eğer dashboard'da sadece SELL sinyalleri görüyorsanız, bunun nedeni:

### Neden BUY Sinyali Yok?

1. **BUY score'ları threshold'un altında kalıyor**
   - BUY faktörleri aktif değil
   - Market koşulları bearish (düşüş eğilimli)

2. **SELL score'ları BUY'ı geçiyor**
   - SELL score'u threshold'a ulaşıyor
   - BUY score'u SELL'den düşük kalıyor

3. **Market koşulları**
   - Price VAH'ın üstünde (bearish)
   - Order book'ta sell pressure var
   - CVD bearish divergence gösteriyor

## ✅ Çözüm: Ayrı BUY/SELL Threshold'ları

Artık BUY ve SELL için ayrı threshold'lar kullanabilirsiniz!

### .env Dosyasında Ayarlama

```env
# Genel threshold (varsayılan)
STRATEGY_MIN_SCORE=5.0

# BUY için özel threshold (daha düşük = daha fazla BUY sinyali)
STRATEGY_MIN_BUY_SCORE=4.0

# SELL için özel threshold
STRATEGY_MIN_SELL_SCORE=5.0
```

### Örnek Senaryolar

#### Senaryo 1: Daha Fazla BUY Sinyali İstiyorsanız

```env
STRATEGY_MIN_SCORE=5.0
STRATEGY_MIN_BUY_SCORE=3.0    # BUY için daha düşük
STRATEGY_MIN_SELL_SCORE=5.0   # SELL için normal
```

**Sonuç:** BUY sinyalleri daha kolay üretilir, SELL sinyalleri aynı kalır.

#### Senaryo 2: Daha Az SELL Sinyali İstiyorsanız

```env
STRATEGY_MIN_SCORE=5.0
STRATEGY_MIN_BUY_SCORE=5.0    # BUY için normal
STRATEGY_MIN_SELL_SCORE=7.0   # SELL için daha yüksek
```

**Sonuç:** SELL sinyalleri daha az üretilir, BUY sinyalleri aynı kalır.

#### Senaryo 3: Dengeli Yaklaşım

```env
STRATEGY_MIN_SCORE=5.0
STRATEGY_MIN_BUY_SCORE=4.5    # BUY için biraz düşük
STRATEGY_MIN_SELL_SCORE=5.5   # SELL için biraz yüksek
```

**Sonuç:** BUY ve SELL sinyalleri daha dengeli olur.

## 🎯 Hızlı Test

### Adım 1: BUY Threshold'unu Düşürün

```env
STRATEGY_MIN_BUY_SCORE=3.0
```

### Adım 2: Bot'u Yeniden Başlatın

```bash
python run.py
```

### Adım 3: Dashboard'da Kontrol Edin

- **Bot Activity** → **Last Scores**
- BUY score'ları 3.0'a ulaşıyor mu?
- SELL score'larından yüksek mi?

### Adım 4: Sinyalleri İzleyin

- **Recent Signals** panelinde BUY sinyalleri görünüyor mu?
- Eğer görünüyorsa, threshold'u yavaşça artırın
- Optimal dengeyi bulun

## 📊 Weight Optimizasyonu

Eğer threshold değiştirmek yeterli değilse, weight'leri ayarlayın:

### BUY Faktörlerini Güçlendirin

```env
# BUY faktörlerine daha fazla ağırlık
WEIGHT_VOLUME_PROFILE=2.5    # Price below VAL → BUY
WEIGHT_ORDERBOOK=2.5         # Buy pressure → BUY
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=2.0     # Demand zone → BUY
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=0.0
```

**Toplam:** 10.0 olmalı!

### SELL Faktörlerini Zayıflatın

```env
# SELL faktörlerine daha az ağırlık
WEIGHT_VOLUME_PROFILE=1.5    # Price above VAH → SELL
WEIGHT_ORDERBOOK=1.5         # Sell pressure → SELL
WEIGHT_CVD=2.0
WEIGHT_SUPPLY_DEMAND=2.0     # Supply zone → SELL
WEIGHT_HVN=1.0
WEIGHT_TIME_OF_DAY=2.0
```

## 🔍 Dashboard'da Kontrol

**Bot Activity** panelinde:

```
Last Scores:
  BUY: 3.5/10.0 (min: 4.0)  ← Sarı (threshold altında)
  SELL: 5.2/10.0 (min: 5.0) ← Yeşil (threshold üstünde)
  Result: ✗ No Signal       ← SELL threshold'a ulaştı ama BUY'dan düşük
```

**Çözüm:** `STRATEGY_MIN_BUY_SCORE=3.0` yapın

## ⚠️ Dikkat

1. **Çok düşük BUY threshold:**
   - Çok fazla BUY sinyali
   - Daha fazla risk
   - Zayıf sinyaller

2. **Çok yüksek SELL threshold:**
   - Çok az SELL sinyali
   - Fırsat kaçırma
   - Bearish market'te dezavantaj

3. **Denge önemli:**
   - Her iki yönde de sinyal üretilmeli
   - Market koşullarına göre ayarlayın

## 📈 Önerilen Başlangıç Ayarları

### Konservatif (Güvenli)

```env
STRATEGY_MIN_SCORE=5.0
STRATEGY_MIN_BUY_SCORE=5.0
STRATEGY_MIN_SELL_SCORE=5.0
```

### Dengeli (Önerilen)

```env
STRATEGY_MIN_SCORE=5.0
STRATEGY_MIN_BUY_SCORE=4.5
STRATEGY_MIN_SELL_SCORE=5.5
```

### Agresif (Daha Fazla Sinyal)

```env
STRATEGY_MIN_SCORE=5.0
STRATEGY_MIN_BUY_SCORE=3.5
STRATEGY_MIN_SELL_SCORE=4.5
```

## 🎯 Sonuç

Artık BUY ve SELL için ayrı threshold'lar kullanabilirsiniz!

**Hızlı test:**
1. `.env` dosyasına ekleyin: `STRATEGY_MIN_BUY_SCORE=3.0`
2. Bot'u yeniden başlatın
3. Dashboard'da BUY sinyallerini izleyin
