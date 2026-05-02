# Prototype-9
### Polymarket Automated Trading & Arbitrage System


---

## Overview

Prototype-9 is an automated trading bot designed for Polymarket's binary prediction markets. It supports two distinct operational strategies:

**1. Arbitrage Strategy (`arb`)**
Exploits pricing inefficiencies in short-window markets where the combined YES + NO price deviates above $1.00, locking in a near-guaranteed spread after gas fees.

**Core mechanic:**
```
YES_price + NO_price > 1.00 + gas_fee + min_threshold
→ Buy both sides simultaneously
→ Collect spread at market resolution
```

**2. BoneReaper Strategy (`bonereaper`)**
A directional-to-hedge strategy that enters positions when implied probability is low, holds for a brief window, and attempts to hedge the opposite side if the market moves favorably to lock in a guaranteed spread before resolution.

**Target performance (paper trading baseline):**
- Win rate: ~70–80% (spread arb, not directional)
- Avg net profit per trade: ~$0.02–0.05 per $1 deployed
- Monthly infra cost: ~$25 (AI subscription + VPS optional)

---

## System Architecture

```
┌─────────────────────────────────────────────────┐
│                  Prototype-9                    │
│                                                 │
│  ┌─────────────┐     ┌─────────────────────┐    │
│  │Price Monitor│────▶│  Arbitrage Detector │    │
│  │ WebSocket   │     │  Spread calculator  │    │
│  └─────────────┘     └──────────┬──────────┘    │
│                                 │ Signal        │
│  ┌─────────────┐     ┌──────────▼──────────┐    │
│  │Risk Manager │◀────│  Execution Engine   │    │
│  │Circuit break│     │  Dual-side orders   │    │
│  └─────────────┘     └──────────┬──────────┘    │
│                                 │               │
│  ┌─────────────┐     ┌──────────▼──────────┐    │
│  │  Dashboard  │◀────│    Data Logger      │    │
│  │  Live TUI   │     │    SQLite journal   │    │
│  └─────────────┘     └─────────────────────┘    │
└─────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.12+
- Polygon wallet with USDC balance (for live mode)
- Polymarket account with CLOB API access
- OS: Windows 10/11, macOS, or Linux
- RAM: 2GB minimum
- Network: Stable broadband (latency matters)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/yourname/prototype-9.git
cd prototype-9
```

### 2. Create virtual environment

```bash
# Windows
python -m venv venv
venv\Scripts\activate

# macOS / Linux
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

**requirements.txt:**
```
polymarket-py==0.3.0
web3==6.15.0
aiohttp==3.9.5
websockets==12.0
pandas==2.2.2
python-dotenv==1.0.1
rich==13.7.1
SQLAlchemy==2.0.30
pytest==8.2.0
```

### 4. Configure environment

Copy the example env file and fill in your credentials:

```bash
cp .env.example .env
```

Edit `.env`:

```env
# Polymarket CLOB API
POLY_API_KEY=your_api_key_here
POLY_API_SECRET=your_api_secret_here
POLY_PASSPHRASE=your_passphrase_here

# Wallet (Polygon)
WALLET_PRIVATE_KEY=your_private_key_here
WALLET_ADDRESS=0xYourWalletAddress

# Trading Parameters
MIN_SPREAD=0.020              # Minimum spread to trigger (2.0%)
MAX_POSITION_USD=50           # Max position size per trade
DAILY_LOSS_LIMIT=30           # Auto-halt if daily loss exceeds this ($)
MAX_OPEN_POSITIONS=3          # Max simultaneous positions

# BoneReaper Strategy Parameters
STRATEGY=bonereaper           # arb | bonereaper 
ENTRY_PRICE_THRESHOLD=0.35    # Implied probability threshold to enter
HEDGE_TRIGGER_SECONDS=120     # Seconds to hold before seeking a hedge
MAX_COMBINED_COST=0.97        # Max combined cost of YES + NO (locks 3% spread)

# Mode: paper | live
TRADING_MODE=paper

# Gas Settings (Polygon)
MAX_GAS_GWEI=100
GAS_PRICE_BUFFER=1.2          # Multiply estimate by this factor

# Logging
LOG_LEVEL=INFO
DB_PATH=./data/trades.db
```

> **Security warning:** Never commit your `.env` file. The `.gitignore` already excludes it. Keep your private key offline when not running the bot.

---

## Project Structure

```
prototype-9/
├── README.md
├── requirements.txt
├── .env.example
├── .gitignore
├── main.py                    # Entry point
│
├── core/
│   ├── __init__.py
│   ├── price_monitor.py       # WebSocket market feed
│   ├── arb_detector.py        # Spread detection logic
│   ├── bonereaper_detector.py # BoneReaper strategy logic
│   ├── execution_engine.py    # Order placement
│   ├── risk_manager.py        # Safety controls
│   ├── bankroll_guard.py      # Bankroll protection logic
│   ├── data_logger.py         # SQLite trade journal
│   └── dashboard.py           # Rich TUI interface
│
├── utils/
│   ├── __init__.py
│   ├── kelly.py               # Kelly Criterion calculator
│   ├── gas.py                 # Polygon gas estimator
│   └── helpers.py             # Shared utilities
│
├── config/
│   └── settings.py            # Config loader from .env
│
├── data/
│   └── trades.db              # Auto-created on first run
│
└── tests/
    ├── test_detector.py
    ├── test_risk_manager.py
    └── test_kelly.py
```

---

## Running Prototype-9

### Paper mode (recommended first)

```bash
python main.py --mode paper
```

Paper mode simulates all execution logic without placing real orders. Runs the full detection and sizing pipeline against live market data.

### Live mode

```bash
python main.py --mode live
```

> Only run live mode after completing the [pre-live checklist](#pre-live-checklist).

### Additional flags

```bash
# Set the strategy to run (arb or bonereaper)
python main.py --mode paper --strategy bonereaper

# Set minimum spread threshold (overrides .env)
python main.py --mode paper --min-spread 0.025

# Limit max position size
python main.py --mode live --max-pos 25

# Verbose logging
python main.py --mode paper --log-level DEBUG

# Run against specific market only
python main.py --mode paper --market BTC-UP-DOWN-15M
```

---

## Dashboard

When running, Prototype-9 displays a live terminal dashboard:

```
┌─ PROTOTYPE-9 ──────────────────────── PAPER MODE ──┐
│ P&L Today    Win Rate   Open Opps   Bankroll       │
│ +$12.40      74%        3           $812.40        │
├────────────────────────────────────────────────────┤
│ LIVE OPPORTUNITIES                                 │
│ BTC Up/Down 15m #3   2.4% spread   +$1.20 est.     │
│ BTC Up/Down 30m #1   1.9% spread   +$0.95 est.     │
├────────────────────────────────────────────────────┤
│ EXECUTION LOG                                      │
│ [14:32:01] WIN  BTC 15m #2  2.1% spread  +$1.05    │
│ [14:31:44] WIN  BTC 15m #1  1.8% spread  +$0.90    │
│ [14:30:22] LOSS BTC 30m #3  1.7% spread  -$0.42    │
└────────────────────────────────────────────────────┘
  [Q] Quit   [P] Pause   [K] Kill all positions
```

---

## Pre-Live Checklist

Complete every item before switching to live mode:

**Paper trading validation:**
- [ ] Minimum 50 paper trades completed
- [ ] Win rate sustained above 65% over 2+ weeks
- [ ] Average net profit per trade positive after simulated gas
- [ ] No execution errors or unhandled exceptions in logs
- [ ] Daily loss circuit breaker tested and confirmed working

**Wallet & API:**
- [ ] Polygon wallet funded with USDC (start: $100–200)
- [ ] Polymarket API keys confirmed working via test call
- [ ] Gas estimator calibrated against current Polygon network fees
- [ ] `.env` double-checked — no test keys in production config

**System stability:**
- [ ] Bot ran continuously for 48 hours without crash
- [ ] Auto-reconnect tested (manually disconnect network, confirm recovery)
- [ ] Laptop sleep/hibernate disabled during trading hours
- [ ] Emergency kill switch (`K` key) tested successfully

**Risk parameters:**
- [ ] `MAX_POSITION_USD` set to $10 or less for first live week
- [ ] `DAILY_LOSS_LIMIT` set to no more than 5% of total capital
- [ ] `MAX_OPEN_POSITIONS` set to 2 for first live week

---

## Risk Management

Prototype-9 includes multiple safety layers:

| Layer | Mechanism | Default |
|---|---|---|
| Position sizing | Half-Kelly Criterion | Dynamic |
| Per-trade cap | `MAX_POSITION_USD` | $50 |
| Daily loss halt | `DAILY_LOSS_LIMIT` | $30 |
| Gas floor | Skip if fee > 30% of spread | Auto |
| Max exposure | `MAX_OPEN_POSITIONS` | 3 |
| Market window | Skip markets resolving < 5 min | Auto |

The bot will auto-halt and log a warning if any circuit breaker trips. Restart with `python main.py` after reviewing the logs.

---

## Performance Analytics

Trade history is stored in `data/trades.db` (for `arb` strategy) or `data/bonereaper_trades.db` (for `bonereaper` strategy). To generate a performance report:

```bash
python utils/report.py --period 7d
python utils/report.py --period 30d --export trades_report.csv
```

Output includes: total P&L, win rate, avg profit/loss per trade, gas costs breakdown, best/worst markets, capital velocity.

---

## Known Limitations

- **Latency:** Laptop execution is 50–200ms slower than data-center bots. Focus on wider spreads (>2%) to compensate.
- **API rate limits:** Polymarket CLOB throttles at high request volume. Built-in backoff handles this but reduces scan frequency under load.
- **Market resolution risk:** Binary markets can resolve while a position is open. The 5-minute window filter reduces but does not eliminate this.
- **Capital scale:** Below $500 deployed capital, gas costs materially reduce net returns. Scale gradually.

---

## Roadmap

- **v0.2** — Cross-market arbitrage (Polymarket vs Kalshi)
- **v0.3** — Liquidity provision mode with hedging
- **v0.4** — VPS deployment scripts + systemd service
- **v1.0** — Multi-asset support (ETH, SOL prediction markets)

---

## License

MIT License. Use at your own risk. This software is for educational and research purposes. Trading prediction markets involves financial risk. Past paper trading performance does not guarantee live trading results.

