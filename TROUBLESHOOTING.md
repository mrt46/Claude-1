# Troubleshooting Guide

## 🔧 Quick Diagnostic

**Problem: Bot not trading or showing errors**

### Step 1: Run Debug Tool
```bash
python debug_bot.py
```

This will automatically check:
- ✅ Environment configuration
- ✅ Database connections
- ✅ Exchange API access
- ✅ Symbol validity
- ✅ Strategy configuration

### Step 2: Fix Issues Based on Results

---

## 🐛 Common Problems

### 1. Database Password Authentication Failed

**Error:** `password authentication failed for user "postgres"`

**Quick Fix (Windows):**
```cmd
fix_database.bat
```

**Quick Fix (Linux/Mac):**
```bash
chmod +x fix_database.sh
./fix_database.sh
```

**Manual Fix:**
1. Check your `.env` file:
   ```
   TIMESCALEDB_PASSWORD=postgres
   ```

2. Reset password in Docker:
   ```bash
   docker exec -it timescaledb psql -U postgres
   ALTER USER postgres PASSWORD 'postgres';
   \q
   ```

3. Update `.env` to match the new password

---

### 2. Bot Starts But No Trades

**This is NORMAL!** The InstitutionalStrategy is very selective.

**Why No Trades?**
- Strategy requires **7/10 minimum score**
- All 5 factors must align (Volume Profile, Order Book, CVD, Supply/Demand, HVN)
- Market conditions may not meet criteria for hours or days

**Check if Bot is Working:**

1. **Look at Dashboard** (full-screen terminal UI):
   - "Bot Activity" panel shows last analysis
   - BUY/SELL scores are displayed
   - Example: `BUY: 5.5/10.0 (min: 7.0)` = No signal (score too low)

2. **Bot is working if you see:**
   ```
   Analysis Cycle #1, #2, #3...
   Analyzing BTCUSDT at $42,531.20
   Final Scores: BUY=5.5/10, SELL=4.0/10
   ```

3. **Expected Behavior:**
   - Bot analyzes every 60 seconds
   - Most analysis cycles produce NO signal
   - This is intentional - quality over quantity

**If You Want More Trades:**

Edit `.env`:
```bash
MIN_SCORE=6.5  # Lower threshold (default is 7.0)
```

⚠️ **Warning:** Lower threshold = more trades but lower quality

---

### 3. Dashboard Hides Log Messages

**Problem:** After starting bot, you see the dashboard but no log messages

**This is EXPECTED!**

The dashboard runs in full-screen mode (`screen=True`) which takes over the terminal.

**Solution: Logs are still being written**

1. **View logs in file** (if logging to file):
   ```bash
   tail -f bot.log
   ```

2. **Run without dashboard** (temporary):
   Edit `main.py`:
   ```python
   self.dashboard_enabled = False  # Disable dashboard
   ```

3. **Dashboard shows all info:**
   - Bot Activity panel = last analysis results
   - System Status = connection status
   - Performance = PnL and trades
   - No need to see raw logs

---

### 4. No Valid Symbols (Testnet)

**Error:** `❌ SOLUSDT: Invalid symbol` (or similar)

**Problem:** Not all symbols are available on Binance Testnet

**Fix:** Update `.env` with testnet-compatible symbols:
```bash
TRADING_SYMBOLS=BTCUSDT,ETHUSDT,BNBUSDT
```

**Check which symbols work:**
```bash
python debug_bot.py
```
The script will test each symbol and show which are valid.

---

### 5. API Keys Not Working

**Error:** `API key/secret invalid` or `Signature verification failed`

**Common Causes:**
1. **Testnet vs Mainnet mismatch**
   - Testnet keys only work on testnet
   - Mainnet keys only work on mainnet

   Check `.env`:
   ```bash
   TESTNET=true  # Use testnet
   ```

2. **IP restriction** (on Binance)
   - Go to Binance API settings
   - Remove IP restrictions OR add your current IP

3. **API permissions**
   - Enable "Spot & Margin Trading"
   - Enable "Reading" permission

**Test API Keys:**
```bash
python debug_bot.py
```
It will show "✅ USDT Balance: X.XX" if keys work.

---

### 6. Docker Not Running

**Error:** `Cannot connect to the Docker daemon`

**Windows:**
1. Open Docker Desktop
2. Wait for it to fully start (whale icon in taskbar)
3. Run `docker ps` to verify

**Linux:**
```bash
sudo systemctl start docker
sudo systemctl enable docker
```

**Mac:**
1. Open Docker Desktop from Applications
2. Wait for status "Docker Desktop is running"

---

### 7. Bot Crashes on Startup

**Check logs for error:**
```bash
python main.py 2>&1 | tee bot_error.log
```

**Common Errors:**

1. **Module not found:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Port already in use (Dashboard):**
   - Another instance of bot is running
   - Close it first or change dashboard port

3. **Permission denied:**
   ```bash
   # Linux/Mac
   chmod +x fix_database.sh

   # Windows: Run as Administrator
   ```

---

## 📊 Understanding Dashboard

When you run `python main.py`, the dashboard appears full-screen:

```
┌──────────────────────────────────────────────────────────────┐
│         INSTITUTIONAL TRADING BOT - LIVE DASHBOARD           │
├──────────────┬───────────────────────────────────────────────┤
│ Performance  │  📊 Recent Trades (last 10)                   │
│ Wallet       │  🎯 Optimization Insights                    │
│ Daily Stats  │  Active Positions                             │
│              │  System Status                                │
│              │  Bot Activity ← SHOWS IF BOT IS WORKING      │
└──────────────┴───────────────────────────────────────────────┘
```

**Key Panels:**

1. **Bot Activity:**
   - Status: Running/Stopped
   - Last Analysis: "2m ago"
   - Last Scores: BUY=5.5/10, SELL=4.0/10
   - **If scores are updating, bot is working!**

2. **Performance:**
   - Balance, Daily PnL
   - Total signals generated
   - Approved vs Rejected trades

3. **Recent Trades:**
   - Only appears after trades are executed
   - Shows PnL, fees, closure reason

4. **Optimization Insights:**
   - Runs every 24h automatically
   - Suggests parameter improvements
   - Requires minimum 10 trades

---

## 🚀 Full Startup Checklist

### Before First Run:

1. **Start Docker:**
   ```bash
   docker-compose up -d
   ```

2. **Wait 5 seconds for database:**
   ```bash
   sleep 5  # Linux/Mac
   timeout 5  # Windows CMD
   ```

3. **Run diagnostic:**
   ```bash
   python debug_bot.py
   ```

4. **If all tests pass:**
   ```bash
   python main.py
   ```

### Expected Startup Sequence:

```
✅ Database connections
✅ Exchange initialized
✅ Account balance loaded
✅ Dashboard started
✅ WebSocket streams connected
✅ Position monitor started
✅ Optimization agent started (if database connected)
✅ Trading bot STARTED - Entering main loop
```

### If Something Goes Wrong:

1. **Stop bot:** `Ctrl+C`
2. **Check error:** Look at dashboard or last log message
3. **Fix issue:** Use `debug_bot.py` or `fix_database.bat`
4. **Restart:** `python main.py`

---

## 📞 Still Having Issues?

### Collect Diagnostic Info:

```bash
# Run full diagnostic
python debug_bot.py > diagnostic_output.txt 2>&1

# Check database
docker logs timescaledb > db_logs.txt

# Check bot startup
python main.py 2>&1 | head -50 > startup_logs.txt
```

### Post Issue on GitHub:

Include:
1. Output from `debug_bot.py`
2. Error messages (if any)
3. OS and Python version
4. Whether using testnet or mainnet

---

## 💡 Pro Tips

### 1. Test Mode First
Always test on **testnet** before using real money:
```bash
TESTNET=true
```

### 2. Monitor Dashboard
The dashboard shows everything you need:
- Is bot running? → Bot Activity panel
- Any trades? → Recent Trades panel
- Is strategy finding opportunities? → Bot Activity scores

### 3. Be Patient
- Strategy is selective (7/10 threshold)
- May take hours/days to find good setups
- Check "Last Analysis" timestamp - should update every ~60s
- If timestamp is updating, bot is working!

### 4. Understand Scores
```
BUY: 5.5/10.0 (min: 7.0)  ← No signal (below threshold)
BUY: 7.5/10.0 (min: 7.0)  ← Signal generated! ✅
```

Each factor contributes:
- Volume Profile: 2.0 points
- Order Book: 2.0 points
- CVD: 2.0 points
- Supply/Demand: 2.0 points
- HVN Support: 1.0 point
- Time/Volume: 1.0 point

**Total: 10.0 points max**

---

## 🔄 Quick Reset (if everything fails)

**Nuclear option - deletes all data:**

```bash
# Stop everything
docker-compose down -v

# Remove containers
docker rm -f timescaledb redis

# Recreate
docker-compose up -d

# Wait and reinitialize
sleep 5
python debug_bot.py
```

Then update `.env` with password: `postgres`

---

## ✅ Success Indicators

**Bot is working correctly when:**

1. ✅ Dashboard updates every second
2. ✅ "Last Analysis" timestamp updates every ~60 seconds
3. ✅ Bot Activity shows scores (even if below threshold)
4. ✅ System Status shows WebSocket connected
5. ✅ No error messages in System Status

**You DON'T need:**
- ❌ Trades within first hour (normal to have none)
- ❌ Signals every cycle (strategy is selective)
- ❌ Constant log messages (dashboard shows everything)
