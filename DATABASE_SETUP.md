# 🗄️ Database Kurulum Rehberi

## 🚀 Hızlı Başlangıç (Windows)

1. **Docker Desktop'ı başlatın**

2. **Kurulum scriptini çalıştırın:**
```powershell
.\database\setup.ps1
```

3. **`.env` dosyasını kontrol edin** (zaten doğru değerlerle gelir)

4. **Bot'u çalıştırın:**
```bash
python run.py
```

## 🚀 Hızlı Başlangıç (Linux/Mac)

1. **Docker'ı başlatın**

2. **Kurulum scriptini çalıştırın:**
```bash
chmod +x database/setup.sh
./database/setup.sh
```

3. **`.env` dosyasını kontrol edin**

4. **Bot'u çalıştırın:**
```bash
python run.py
```

## 📋 Gereksinimler

- **Docker Desktop** (Windows/Mac) veya **Docker** (Linux)
- En az 2GB boş disk alanı
- En az 1GB RAM (database'ler için)

## 🔧 Manuel Kurulum

Eğer script çalışmazsa:

```bash
# Proje kök dizininde
docker-compose up -d

# Durumu kontrol et
docker ps

# Logları görüntüle
docker-compose logs -f
```

## ✅ Kurulum Kontrolü

### TimescaleDB Kontrolü
```bash
docker exec trading_bot_timescaledb pg_isready -U postgres
```

Çıktı: `trading_bot_timescaledb:5432 - accepting connections`

### Redis Kontrolü
```bash
docker exec trading_bot_redis redis-cli ping
```

Çıktı: `PONG`

### Database Bağlantı Testi
```bash
# Python ile test
python -c "import asyncio; from src.data.database import TimescaleDBClient; async def test(): c = TimescaleDBClient('localhost', 5432, 'trading_bot', 'postgres', 'postgres'); await c.connect(); print('✅ Connected'); await c.close(); asyncio.run(test())"
```

## 📊 Oluşturulan Tablolar

Kurulum sonrası otomatik oluşturulur:

**TimescaleDB Hypertables:**
- ✅ `ohlcv` - OHLCV verileri
- ✅ `orderbook_snapshots` - Order book anlık görüntüleri  
- ✅ `trades` - Trade verileri

**PostgreSQL Tabloları:**
- ✅ `bot_orders` - Bot emirleri
- ✅ `bot_positions` - Açık pozisyonlar
- ✅ `bot_trades` - Kapatılmış pozisyonlar

**Materialized Views:**
- ✅ `ohlcv_1h` - 1 saatlik aggregate
- ✅ `strategy_performance` - Performans özeti

## 🛑 Durdurma

```bash
docker-compose down
```

## 🗑️ Tamamen Silme

```bash
# Dikkat: Tüm veriler silinir!
docker-compose down -v
```

## 🔄 Yeniden Başlatma

```bash
docker-compose restart
```

## 📈 Veri Yönetimi

### Backup
```bash
# TimescaleDB
docker exec trading_bot_timescaledb pg_dump -U postgres trading_bot > backup_$(date +%Y%m%d).sql

# Redis
docker exec trading_bot_redis redis-cli SAVE
docker cp trading_bot_redis:/data/dump.rdb ./redis_backup_$(date +%Y%m%d).rdb
```

### Restore
```bash
# TimescaleDB
docker exec -i trading_bot_timescaledb psql -U postgres trading_bot < backup_20250127.sql
```

## 🐛 Sorun Giderme

### Port 5432 zaten kullanılıyor
```yaml
# docker-compose.yml dosyasında port'u değiştirin:
ports:
  - "5433:5432"  # 5433 kullan
```

Sonra `.env` dosyasında:
```env
TIMESCALEDB_PORT=5433
```

### Container başlamıyor
```bash
# Logları kontrol et
docker-compose logs timescaledb
docker-compose logs redis

# Container'ı yeniden oluştur
docker-compose down
docker-compose up -d
```

### Database bağlantı hatası
1. Container'ların çalıştığını kontrol edin:
   ```bash
   docker ps
   ```

2. Port'ların açık olduğunu kontrol edin:
   ```bash
   netstat -an | findstr 5432  # Windows
   netstat -an | grep 5432     # Linux/Mac
   ```

3. `.env` dosyasındaki bilgileri kontrol edin

### Windows'ta "executable file not found"
Docker Desktop'ın çalıştığından emin olun ve WSL2 backend kullanın.

## 📝 Notlar

- ✅ Database olmadan da bot çalışır (sadece veri kaydetmez)
- ✅ İlk kurulumda tüm tablolar otomatik oluşturulur
- ✅ Retention policy'ler otomatik eski verileri siler (90 gün OHLCV, 7 gün OB, 30 gün trades)
- ✅ Continuous aggregates otomatik güncellenir (her saat)

## 🔗 Faydalı Komutlar

```bash
# Container durumu
docker ps

# Database'e bağlan
docker exec -it trading_bot_timescaledb psql -U postgres -d trading_bot

# Redis'e bağlan
docker exec -it trading_bot_redis redis-cli

# Logları takip et
docker-compose logs -f timescaledb
docker-compose logs -f redis

# Container'ları durdur
docker-compose stop

# Container'ları başlat
docker-compose start
```
