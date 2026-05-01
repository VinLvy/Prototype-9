# Prototype-9 — Operational Guide

> Complete guide from environment setup to running the bot in paper & live mode.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Installation](#2-installation)
3. [Environment Configuration](#3-environment-configuration)
4. [Running in Paper Mode](#4-running-in-paper-mode)
5. [Understanding the TUI Dashboard](#5-understanding-the-tui-dashboard)
6. [Running Tests](#6-running-tests)
7. [Viewing Performance Reports](#7-viewing-performance-reports)
8. [Running in Live Mode](#8-running-in-live-mode)
9. [Core Components Explanation](#9-core-components-explanation)
10. [Troubleshooting](#10-troubleshooting)
11. [Pre-Live Checklist](#11-pre-live-checklist)

---

## 1. Prerequisites

Ensure all the following tools are installed before starting:

| Tool | Minimum Version | Check Version |
|---|---|---|
| Python | 3.12+ | `python --version` |
| pip | latest | `pip --version` |
| Git | any | `git --version` |

> **Windows:** Use **PowerShell** or **Command Prompt** as Administrator to avoid permission errors when creating the virtual environment.

---

## 2. Installation

### Step 1 — Clone the repository

```bash
git clone https://github.com/yourname/prototype-9.git
cd prototype-9
```

### Step 2 — Create a virtual environment

**Windows (PowerShell):**
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
```

**Windows (Command Prompt):**
```cmd
python -m venv venv
venv\Scripts\activate.bat
```

**macOS / Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Once active, the terminal prompt will show `(venv)` at the beginning of the line.

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

This process installs all required libraries:

| Package | Function |
|---|---|
| `py-clob-client` | Polymarket CLOB API client |
| `web3` | Interaction with Polygon blockchain |
| `aiohttp` + `websockets` | Real-time price streaming |
| `pandas` | Trading data analytics |
| `python-dotenv` | Load configurations from `.env` |
| `rich` | Terminal TUI dashboard |
| `SQLAlchemy` | Database ORM (upgrade from sqlite3) |
| `pytest` | Testing framework |

### Step 4 — Create data directory

```bash
# Windows
mkdir data

# macOS / Linux
mkdir -p data
```

> The `data/` directory will store `trades.db` — the SQLite database for all transaction history.

---

## 3. Environment Configuration

### Step 1 — Copy the example file

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

### Step 2 — Edit the .env file

Open `.env` with your favorite text editor and fill it out as needed:

```env
# ── Polymarket CLOB API ─────────────────────────────
POLY_API_KEY=your_api_key_here
POLY_API_SECRET=your_api_secret_here
POLY_PASSPHRASE=your_passphrase_here

# ── Polygon Wallet ──────────────────────────────────
WALLET_PRIVATE_KEY=your_private_key_here
WALLET_ADDRESS=0xYourWalletAddress

# ── Trading Parameters ──────────────────────────────
MIN_SPREAD=0.020          # Minimum spread 2.0% to trigger trade
MAX_POSITION_USD=50       # Max position size per trade ($)
DAILY_LOSS_LIMIT=30       # Auto-halt bot if daily loss > $30
MAX_OPEN_POSITIONS=3      # Max simultaneous open positions

# ── BoneReaper Strategy ─────────────────────────────
STRATEGY=bonereaper           # arb | bonereaper
ENTRY_PRICE_THRESHOLD=0.42    # Maximum implied prob threshold for entry
HEDGE_TRIGGER_SECONDS=45      # Hold time limit before forcing hedge position
MAX_COMBINED_COST=0.96        # Maximum combined price for YES+NO (4% spread)

# ── Mode ─────────────────────────────────────────────
TRADING_MODE=paper        # Use 'paper' first, 'live' only when ready

# ── Polygon Gas ──────────────────────────────────────
MAX_GAS_GWEI=100
GAS_PRICE_BUFFER=1.2      # Safety buffer for gas estimation

# ── Logging & Database ───────────────────────────────
LOG_LEVEL=INFO
DB_PATH=./data/trades.db
```

> **⚠️ IMPORTANT:** Never commit the `.env` file to Git. This file is already registered in `.gitignore`.

### Critical Parameters Explanation

| Parameter | Description | Initial Recommendation |
|---|---|---|
| `MIN_SPREAD` | Minimum spread required for an arb to be considered valid (after gas) | `0.020` (2%) |
| `MAX_POSITION_USD` | Hard limit for maximum position size per trade | `$25–50` |
| `DAILY_LOSS_LIMIT` | Daily circuit breaker — auto-halt bot | Max 5% of capital |
| `MAX_OPEN_POSITIONS` | Maximum simultaneous open positions | `2–3` |
| `STRATEGY` | Bot trading strategy (`arb` or `bonereaper`) | `bonereaper` |
| `ENTRY_PRICE_THRESHOLD` | Entry threshold specifically for `bonereaper` on cheap prices | `0.42` |
| `HEDGE_TRIGGER_SECONDS` | Cut-loss timer specifically for `bonereaper` | `45` |
| `MAX_COMBINED_COST` | Maximum net price for hedge in `bonereaper` | `0.96` |

---

## 4. Running in Paper Mode

Paper mode is **mandatory before going live**. All detection, sizing, and logging logic runs fully — only order execution to the blockchain is skipped.

### Basic Run

Activate the venv first
```bash
venv\Scripts\python main.py --mode paper
```

### Viewing Trade Execution History (Database)
All successful order logs will be recorded in `/data/trades.db`. 
Use the following reader script to display them in the terminal:
```bash
venv\Scripts\python utils/view_trades.py
```

### Support Script (Market Discovery)

Helps find active markets that can be paired with the bot.
```bash
# Monitor current active window timeframe 5m
python utils/market_discovery.py --timeframe 5m

# Auto-refresh every 30s (suitable to be left running in a separate terminal)
python utils/market_discovery.py --timeframe 5m --watch

# View all short-window markets across timeframes
python utils/market_discovery.py --timeframe all --limit 50
```

### With additional parameters

```bash
# Tighter minimum spread (2.5%)
python main.py --mode paper --min-spread 0.025

# Limit position size to $20
python main.py --mode paper --max-pos 20

# More detailed logs for debugging
python main.py --mode paper --log-level DEBUG

# Focus only on a specific market
python main.py --mode paper --market BTC-UP-DOWN-15M
```

### CLI flags reference

| Flag | Default | Description |
|---|---|---|
| `--mode` | `paper` | Trading mode: `paper` or `live` |
| `--strategy` | `arb` | Strategy: `arb`, `bonereaper` |
| `--min-spread` | `0.020` | Minimum spread threshold |
| `--max-pos` | `50.0` | Max position size per trade (USD) |
| `--log-level` | `INFO` | Log verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--market` | all | Focus on one specific market |

### Stopping the bot

Press `Ctrl + C` for a clean shutdown. The bot will close database connections and async tasks before exiting.

---

## 5. Understanding the TUI Dashboard

While the bot is running, the terminal will display a real-time dashboard:

```
╔═ PROTOTYPE-9 ════════════════════════════ PAPER MODE ═╗
║  P&L Today     Win Rate    Open Opps    Bankroll       ║
║  +$12.40       74%         3            $812.40        ║
╚══════════════════════════════════════════════════════════╝

╭── LIVE OPPORTUNITIES ────────────────────────────────────╮
│  Market              Spread    Est. Profit   YES    NO   │
│  BTC-UP-DOWN-15M     2.4%      +$0.0195     0.540  0.500 │
│  BTC-UP-DOWN-30M     1.9%      +$0.0145     0.520  0.470 │
╰──────────────────────────────────────────────────────────╯

╭── EXECUTION LOG ─────────────────────────────────────────╮
│  14:32:01  WIN   BTC-UP-DOWN-15M   2.1%   +$1.05         │
│  14:31:44  WIN   BTC-UP-DOWN-15M   1.8%   +$0.90         │
│  14:30:22  LOSS  BTC-UP-DOWN-30M   1.7%   -$0.42         │
╰──────────────────────────────────────────────────────────╯
  [Q] Quit   [P] Pause   [K] Kill all positions
```

### Explanation of each panel

**Top Panel — Daily Statistics:**
- **P&L Today** — Total profit/loss for today (green = profit, red = loss)
- **Win Rate** — Percentage of profitable trades
- **Open Opps** — Number of currently active arb opportunities
- **Bankroll** — Bankroll balance currently tracked by the bot

**Middle Panel — Live Opportunities:**
- Markets with detected arb opportunities, sorted newest at the top
- Only displays opps that pass the `MIN_SPREAD` threshold

**Bottom Panel — Execution Log:**
- History of the last 10 trades with timestamp, status, spread, and P&L
- **WIN** = profitable trade, **LOSS** = losing trade

---

## 6. Running Tests

Run all tests at once:

```bash
pytest tests/ -v
```

Run tests per module:

```bash
# Test ArbitrageDetector
pytest tests/test_detector.py -v

# Test RiskManager
pytest tests/test_risk_manager.py -v

# Test Kelly Criterion
pytest tests/test_kelly.py -v
```

Run with coverage report:

```bash
pip install pytest-cov
pytest tests/ --cov=core --cov=utils --cov-report=term-missing
```

### Expected results

```
tests/test_detector.py::TestCalculateSpread::test_valid_opportunity_detected    PASSED
tests/test_detector.py::TestCalculateSpread::test_no_opportunity_below_threshold PASSED
...
tests/test_kelly.py::TestKellyCompute::test_positive_edge_returns_nonzero_size  PASSED
...
========================= 28 passed in 0.42s =========================
```

> All 28 tests must be green before proceeding to live mode.

---

## 7. Viewing Performance Reports

After the bot runs and collects data in `data/trades.db`:

```bash
# Report for the last 7 days (default)
python utils/report.py --period 7d

# Report for 30 days
python utils/report.py --period 30d

# All-time report
python utils/report.py --period all

# Export to CSV
python utils/report.py --period 30d --export hasil_trading.csv

# Use database in a custom path
python utils/report.py --period 7d --db ./data/custom_trades.db
```

### Example report output

```
                Prototype-9 Performance Report — 7D
╔══════════════════════════════════════╦══════════════════╗
║ Metric                               ║ Value            ║
╠══════════════════════════════════════╬══════════════════╣
║ Total Trades                         ║ 142              ║
║ Total P&L                            ║ +$28.40          ║
║ Win Rate                             ║ 73.2%            ║
║ Wins / Losses                        ║ 104 / 38         ║
║ Avg Profit (wins)                    ║ +$0.4120         ║
║ Avg Loss (losses)                    ║ -$0.2840         ║
║ Avg P&L per Trade                    ║ $0.2000          ║
║ Capital Velocity                     ║ 20.3 trades/day  ║
║ Best Market                          ║ BTC-UP-DOWN-15M  ║
║ Worst Market                         ║ BTC-UP-DOWN-30M  ║
╚══════════════════════════════════════╩══════════════════╝
```

---

## 8. Running in Live Mode

> **⚠️ WARNING:** Only do this after completing all items in the [Pre-Live Checklist](#11-pre-live-checklist).

### Step 1 — Update .env

```env
TRADING_MODE=live
MAX_POSITION_USD=10    # Start small, max $10/trade for the first week
DAILY_LOSS_LIMIT=15    # Strict at the beginning
MAX_OPEN_POSITIONS=2   # Limit exposure
```

### Step 2 — Validate configuration

```bash
python -c "from config.settings import validate; validate()"
```

If the output is `Settings validation passed for LIVE mode.` → ready to proceed.

### Step 3 — Run live mode

```bash
python main.py --mode live
```

### Step 4 — Monitor strictly

During the first week of live:
- Monitor the dashboard every 30 minutes
- Check daily reports: `python utils/report.py --period 1d`
- Keep your fingers on `Ctrl+C` in case of anomalies

---

## 9. Core Components Explanation

```
main.py
  │
  ├── [arb / bonereaper]
  │   ├── core/price_monitor.py       → WebSocket: stream YES/NO prices in real-time
  │   ├── core/arb_detector.py        → Calculate spread for arb strategy
  │   └── core/bonereaper_detector.py → Dual-entry logic for BoneReaper
  │
  ├── core/bankroll_guard.py      → Tracker for deployed/available capital
  ├── core/execution_engine.py    → Paper: log only | Live: POST orders to CLOB
  ├── core/risk_manager.py        → Gatekeeper: max position? loss limit? Kelly size?
  ├── core/data_logger.py         → Save trade results to SQLite
  └── core/dashboard.py           → Display real-time TUI in the terminal
```

### Signal flow (detail)

```
PriceMonitor            ArbitrageDetector        ExecutionEngine
     │                        │                        │
     │─── price_tick ────────▶│                        │
     │                        │── spread OK? ──▶ YES   │
     │                        │─── signal ────────────▶│
     │                        │                        │── RiskManager.evaluate()
     │                        │                        │── CLOB API (live) / skip (paper)
     │                        │                        │── DataLogger.log_trade()
     │                        │                        │── Dashboard.record_execution()
```

### Configuration files

| File | Function |
|---|---|
| `.env` | Credentials & parameters (do not commit!) |
| `config/settings.py` | Loader from `.env` — all modules import from here |

### Utility files

| File | Function |
|---|---|
| `utils/kelly.py` | Calculate optimal position size (Half-Kelly) |
| `utils/gas.py` | Polygon gas cost estimation in USD |
| `utils/helpers.py` | Number formatting, timestamps, validation |
| `utils/report.py` | CLI tool for performance reports |

---

## 10. Troubleshooting

### `ModuleNotFoundError: No module named 'rich'`

Virtual environment is not active or dependencies are not installed.

```bash
# Activate venv first
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate     # macOS/Linux

# Reinstall
pip install -r requirements.txt
```

### `EnvironmentError: Live mode requires these env vars to be set`

The `.env` file is not fully configured for live mode. Check:

```bash
python -c "from config.settings import validate; validate()"
```

Fill in any empty environment variables.

### Bot is running but no trades are triggered

1. Market spread is too small — this is normal. Try lowering it temporarily:
   ```bash
   python main.py --mode paper --min-spread 0.010
   ```
2. Ensure a stable internet connection (WebSocket disconnected = no data).
3. Check logs with `--log-level DEBUG` for details.

### Dashboard does not appear / display is broken

Terminal does not support ANSI colors. Use:
- Windows: **Windows Terminal** (not the legacy CMD)
- macOS/Linux: Standard terminals already support it

```bash
# Fallback: run without TUI, output to log file
python main.py --mode paper --log-level INFO 2>&1 | tee run.log
```

### Database error: `unable to open database file`

The `data/` directory does not exist:

```bash
mkdir data
```

### `pytest` does not find module

Run from the project root directory (not from inside `tests/`):

```bash
# Correct
cd prototype-9
pytest tests/ -v

# Wrong — do not enter the tests folder
cd tests && pytest  # this will fail
```

---

## 11. Pre-Live Checklist

Complete **all items** before switching to live mode:

### Paper Trading Validation

- [ ] Minimum **50 paper trades** completed
- [ ] **Win rate ≥ 65%** for at least 2 weeks (monitor with `report.py`)
- [ ] Average net profit per trade is **positive** after simulated gas costs
- [ ] No unhandled exceptions in logs during 48 hours of continuous running
- [ ] Daily circuit breaker tested: set `DAILY_LOSS_LIMIT=0.01`, verify the bot halts

### Wallet & API

- [ ] Polygon Wallet funded with USDC (starting from $100–200)
- [ ] Polymarket API keys successfully tested via GET market calls
- [ ] Gas estimator calibrated — compare bot's estimation vs [PolygonScan](https://polygonscan.com)
- [ ] `.env` file does not contain test keys in production configuration

### System Stability

- [ ] Bot runs for **48 hours non-stop** without crashing in paper mode
- [ ] WebSocket auto-reconnect tested (disconnect network, confirm recovery)
- [ ] Laptop sleep/hibernation **disabled** during trading hours
- [ ] Kill switch `Ctrl+C` tested — confirm database locks correctly

### Risk Parameters (First Week Live)

- [ ] `MAX_POSITION_USD=10` (max $10 per trade)
- [ ] `DAILY_LOSS_LIMIT` ≤ 5% of total capital
- [ ] `MAX_OPEN_POSITIONS=2`
- [ ] Review daily for the first 7 days before raising limits

---

## Quick Reference

```bash
# Paper mode — BoneReaper (algorithmic dual-entry)
venv\Scripts\python main.py --mode paper --strategy bonereaper

# Run all tests
pytest tests/ -v

# BoneReaper performance report
venv\Scripts\python utils/report.py --period 7d --db ./data/bonereaper_trades.db

# Validate settings for live
python -c "from config.settings import validate; validate()"

# Run live mode
venv\Scripts\python main.py --mode live --strategy bonereaper
```

---

*Prototype-9 — Alpha v0.1 | Paper trading only. Trade at your own risk.*
