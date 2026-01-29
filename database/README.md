# Database Kurulum Rehberi

Bu klasörde database kurulum scriptleri bulunur.

## 🚀 Hızlı Kurulum

### Windows
```powershell
.\database\setup.ps1
```

### Linux/Mac
```bash
chmod +x database/setup.sh
./database/setup.sh
```

## 📋 Gereksinimler

- Docker Desktop (Windows/Mac) veya Docker (Linux)
- Docker Compose

## 🔧 Manuel Kurulum

### Docker Compose ile

1. **Proje kök dizininde:**
```bash
docker-compose up -d
```

2. **Kontroller:**
```bash
# TimescaleDB durumu
docker exec trading_bot_timescaledb pg_isready -U postgres

# Redis durumu
docker exec trading_bot_redis redis-cli ping
```

3. **Logları görüntüle:**
```bash
docker-compose logs -f
```

## 📊 Database Yapısı

### TimescaleDB Tabloları

**Hypertables (Time-series):**
- `ohlcv` - OHLCV verileri
- `orderbook_snapshots` - Order book anlık görüntüleri
- `trades` - Trade/ticks verileri

**PostgreSQL Tabloları:**
- `bot_orders` - Bot emirleri
- `bot_positions` - Açık pozisyonlar
- `bot_trades` - Kapatılmış pozisyonlar

**Materialized Views:**
- `ohlcv_1h` - 1 saatlik OHLCV aggregate
- `strategy_performance` - Strateji performans özeti

### Redis

- Order book cache (1 saniye TTL)
- Volume profile cache (5 dakika TTL)
- State management

## ⚙️ Yapılandırma

Kurulumdan sonra `.env` dosyanızı güncelleyin:

```env
TIMESCALEDB_HOST=localhost
TIMESCALEDB_PORT=5432
TIMESCALEDB_DATABASE=trading_bot
TIMESCALEDB_USER=postgres
TIMESCALEDB_PASSWORD=postgres

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
```

## 🛑 Durdurma

```bash
docker-compose down
```

## 🗑️ Verileri Silme

```bash
# Dikkat: Tüm veriler silinir!
docker-compose down -v
```

## 🔍 Troubleshooting

### Port zaten kullanılıyor
```bash
# Port'u değiştir veya kullanan servisi durdur
# docker-compose.yml dosyasında port'ları değiştirebilirsiniz
```

### Container başlamıyor
```bash
# Logları kontrol et
docker-compose logs timescaledb
docker-compose logs redis

# Container'ı yeniden başlat
docker-compose restart
```

### Database bağlantı hatası
1. Container'ların çalıştığını kontrol edin: `docker ps`
2. Port'ların açık olduğunu kontrol edin
3. `.env` dosyasındaki bilgileri kontrol edin

## 📈 Veri Yönetimi

### Backup
```bash
# TimescaleDB backup
docker exec trading_bot_timescaledb pg_dump -U postgres trading_bot > backup.sql

# Redis backup
docker exec trading_bot_redis redis-cli SAVE
docker cp trading_bot_redis:/data/dump.rdb ./redis_backup.rdb
```

### Restore
```bash
# TimescaleDB restore
docker exec -i trading_bot_timescaledb psql -U postgres trading_bot < backup.sql
```

## 🔄 Güncelleme

```bash
docker-compose pull
docker-compose up -d
```

## 📝 Notlar

- Database olmadan da bot çalışır (sadece veri kaydetmez)
- İlk kurulumda `init.sql` otomatik çalışır
- Retention policy'ler otomatik eski verileri siler
- Continuous aggregates otomatik güncellenir
