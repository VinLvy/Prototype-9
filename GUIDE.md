# Prototype-9 — Operational Guide

> Panduan lengkap mulai dari setup environment hingga menjalankan bot secara paper & live.

---

## Daftar Isi

1. [Prasyarat](#1-prasyarat)
2. [Instalasi](#2-instalasi)
3. [Konfigurasi Environment](#3-konfigurasi-environment)
4. [Menjalankan dalam Paper Mode](#4-menjalankan-dalam-paper-mode)
5. [Memahami Dashboard TUI](#5-memahami-dashboard-tui)
6. [Menjalankan Tests](#6-menjalankan-tests)
7. [Melihat Laporan Performa](#7-melihat-laporan-performa)
8. [Menjalankan dalam Live Mode](#8-menjalankan-dalam-live-mode)
9. [Penjelasan Komponen Inti](#9-penjelasan-komponen-inti)
10. [Troubleshooting](#10-troubleshooting)
11. [Pre-Live Checklist](#11-pre-live-checklist)

---

## 1. Prasyarat

Pastikan semua tools berikut sudah terinstall sebelum mulai:

| Tool | Versi Minimum | Cek Versi |
|---|---|---|
| Python | 3.12+ | `python --version` |
| pip | terbaru | `pip --version` |
| Git | any | `git --version` |

> **Windows:** Gunakan **PowerShell** atau **Command Prompt** sebagai Administrator untuk menghindari permission error saat membuat virtual environment.

---

## 2. Instalasi

### Langkah 1 — Clone repository

```bash
git clone https://github.com/yourname/prototype-9.git
cd prototype-9
```

### Langkah 2 — Buat virtual environment

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

Setelah aktif, prompt terminal akan menampilkan `(venv)` di awal baris.

### Langkah 3 — Install dependencies

```bash
pip install -r requirements.txt
```

Proses ini menginstall semua library yang dibutuhkan:

| Package | Fungsi |
|---|---|
| `py-clob-client` | Polymarket CLOB API client |
| `web3` | Interaksi dengan Polygon blockchain |
| `aiohttp` + `websockets` | Streaming harga real-time |
| `pandas` | Analitik data trading |
| `python-dotenv` | Load konfigurasi dari `.env` |
| `rich` | Terminal dashboard TUI |
| `SQLAlchemy` | ORM database (upgrade dari sqlite3) |
| `pytest` | Framework testing |

### Langkah 4 — Buat direktori data

```bash
# Windows
mkdir data

# macOS / Linux
mkdir -p data
```

> Direktori `data/` akan menyimpan `trades.db` — database SQLite untuk semua riwayat transaksi.

---

## 3. Konfigurasi Environment

### Langkah 1 — Salin file contoh

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

### Langkah 2 — Edit file `.env`

Buka `.env` dengan text editor favorit dan isi sesuai kebutuhan:

```env
# ── Polymarket CLOB API ─────────────────────────────
POLY_API_KEY=your_api_key_here
POLY_API_SECRET=your_api_secret_here
POLY_PASSPHRASE=your_passphrase_here

# ── Wallet Polygon ──────────────────────────────────
WALLET_PRIVATE_KEY=your_private_key_here
WALLET_ADDRESS=0xYourWalletAddress

# ── Parameter Trading ───────────────────────────────
MIN_SPREAD=0.020          # Spread minimum 2.0% agar trade terpicu
MAX_POSITION_USD=50       # Ukuran posisi maksimal per trade ($)
DAILY_LOSS_LIMIT=30       # Bot berhenti otomatis jika rugi > $30/hari
MAX_OPEN_POSITIONS=3      # Maksimal posisi terbuka bersamaan

# ── Mode ─────────────────────────────────────────────
TRADING_MODE=paper        # Gunakan 'paper' dulu, 'live' hanya saat siap

# ── Gas Polygon ──────────────────────────────────────
MAX_GAS_GWEI=100
GAS_PRICE_BUFFER=1.2      # Buffer keamanan estimasi gas

# ── Logging & Database ───────────────────────────────
LOG_LEVEL=INFO
DB_PATH=./data/trades.db
```

> **⚠️ PENTING:** Jangan pernah commit file `.env` ke Git. File ini sudah terdaftar di `.gitignore`.

### Penjelasan Parameter Kritis

| Parameter | Deskripsi | Rekomendasi Awal |
|---|---|---|
| `MIN_SPREAD` | Spread minimum yang diperlukan agar arb dianggap valid (setelah gas) | `0.020` (2%) |
| `MAX_POSITION_USD` | Batas keras ukuran posisi per trade | `$25–50` |
| `DAILY_LOSS_LIMIT` | Circuit breaker harian — bot auto-halt | Maks 5% modal |
| `MAX_OPEN_POSITIONS` | Batas eksposur simultan | `2–3` |

---

## 4. Menjalankan dalam Paper Mode

Paper mode adalah **mode wajib sebelum live**. Semua logika deteksi, sizing, dan logging berjalan penuh — hanya eksekusi order ke blockchain yang di-skip.

### Run dasar

```bash
python main.py --mode paper
```

### Dengan parameter tambahan

```bash
# Spread minimum lebih ketat (2.5%)
python main.py --mode paper --min-spread 0.025

# Batasi ukuran posisi ke $20
python main.py --mode paper --max-pos 20

# Log lebih detail untuk debugging
python main.py --mode paper --log-level DEBUG

# Fokus ke market tertentu saja
python main.py --mode paper --market BTC-UP-DOWN-15M
```

### Referensi semua flag CLI

| Flag | Default | Deskripsi |
|---|---|---|
| `--mode` | `paper` | Mode trading: `paper` atau `live` |
| `--min-spread` | `0.020` | Threshold spread minimum |
| `--max-pos` | `50.0` | Ukuran posisi maks per trade (USD) |
| `--log-level` | `INFO` | Verbositas log: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--market` | semua | Fokus ke satu market spesifik |

### Menghentikan bot

Tekan `Ctrl + C` untuk shutdown bersih. Bot akan menutup koneksi database dan task async sebelum exit.

---

## 5. Memahami Dashboard TUI

Saat bot berjalan, terminal akan menampilkan dashboard real-time:

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

### Penjelasan setiap panel

**Panel Atas — Statistik Harian:**
- **P&L Today** — Total profit/loss hari ini (hijau = profit, merah = loss)
- **Win Rate** — Persentase trade yang menguntungkan
- **Open Opps** — Jumlah peluang arb aktif saat ini
- **Bankroll** — Saldo modal yang sedang dilacak bot

**Panel Tengah — Live Opportunities:**
- Market dengan peluang arb yang terdeteksi, diurutkan terbaru di atas
- Hanya menampilkan opps yang melewati threshold `MIN_SPREAD`

**Panel Bawah — Execution Log:**
- Riwayat 10 trade terakhir dengan timestamp, status, spread, dan P&L
- **WIN** = trade profitable, **LOSS** = trade rugi

---

## 6. Menjalankan Tests

Jalankan semua test sekaligus:

```bash
pytest tests/ -v
```

Jalankan test per modul:

```bash
# Test ArbitrageDetector
pytest tests/test_detector.py -v

# Test RiskManager
pytest tests/test_risk_manager.py -v

# Test Kelly Criterion
pytest tests/test_kelly.py -v
```

Jalankan dengan laporan coverage:

```bash
pip install pytest-cov
pytest tests/ --cov=core --cov=utils --cov-report=term-missing
```

### Hasil yang diharapkan

```
tests/test_detector.py::TestCalculateSpread::test_valid_opportunity_detected    PASSED
tests/test_detector.py::TestCalculateSpread::test_no_opportunity_below_threshold PASSED
...
tests/test_kelly.py::TestKellyCompute::test_positive_edge_returns_nonzero_size  PASSED
...
========================= 28 passed in 0.42s =========================
```

> Semua 28 test harus hijau sebelum melanjutkan ke live mode.

---

## 7. Melihat Laporan Performa

Setelah bot berjalan dan mengumpulkan data di `data/trades.db`:

```bash
# Laporan 7 hari terakhir (default)
python utils/report.py --period 7d

# Laporan 30 hari
python utils/report.py --period 30d

# Laporan semua waktu
python utils/report.py --period all

# Export ke CSV
python utils/report.py --period 30d --export hasil_trading.csv

# Gunakan database di path custom
python utils/report.py --period 7d --db ./data/custom_trades.db
```

### Contoh output laporan

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

## 8. Menjalankan dalam Live Mode

> **⚠️ PERINGATAN:** Hanya lakukan ini setelah menyelesaikan semua item di [Pre-Live Checklist](#11-pre-live-checklist).

### Langkah 1 — Update `.env`

```env
TRADING_MODE=live
MAX_POSITION_USD=10    # Mulai kecil, maks $10/trade untuk minggu pertama
DAILY_LOSS_LIMIT=15    # Ketat di awal
MAX_OPEN_POSITIONS=2   # Batasi eksposur
```

### Langkah 2 — Validasi konfigurasi

```bash
python -c "from config.settings import validate; validate()"
```

Jika output `Settings validation passed for LIVE mode.` → siap lanjut.

### Langkah 3 — Jalankan live mode

```bash
python main.py --mode live
```

### Langkah 4 — Monitor ketat

Di minggu pertama live:
- Pantau dashboard setiap 30 menit
- Periksa laporan harian: `python utils/report.py --period 1d`
- Siapkan jari di `Ctrl+C` jika ada anomali

---

## 9. Penjelasan Komponen Inti

```
main.py
  │
  ├── core/price_monitor.py     → WebSocket: stream harga YES/NO
  │       ↓
  ├── core/arb_detector.py      → Hitung spread: YES + NO > 1.00 + fee + threshold?
  │       ↓ (jika ada sinyal)
  ├── core/execution_engine.py  → Paper: log saja | Live: POST order ke CLOB
  │       ↑
  ├── core/risk_manager.py      → Gate keeper: posisi maks? loss limit? Kelly size?
  │       ↓
  ├── core/data_logger.py       → Simpan hasil trade ke SQLite
  │       ↓
  └── core/dashboard.py         → Tampilkan TUI real-time di terminal
```

### Alur sinyal (detail)

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

### File konfigurasi

| File | Fungsi |
|---|---|
| `.env` | Credentials & parameter (jangan di-commit!) |
| `config/settings.py` | Loader dari `.env` — semua modul import dari sini |

### File utility

| File | Fungsi |
|---|---|
| `utils/kelly.py` | Hitung ukuran posisi optimal (Half-Kelly) |
| `utils/gas.py` | Estimasi biaya gas Polygon dalam USD |
| `utils/helpers.py` | Format angka, timestamp, validasi |
| `utils/report.py` | CLI tool laporan performa |

---

## 10. Troubleshooting

### `ModuleNotFoundError: No module named 'rich'`

Virtual environment belum aktif atau dependencies belum terinstall.

```bash
# Aktifkan venv dulu
venv\Scripts\Activate.ps1   # Windows
source venv/bin/activate     # macOS/Linux

# Install ulang
pip install -r requirements.txt
```

### `EnvironmentError: Live mode requires these env vars to be set`

File `.env` belum diisi lengkap untuk live mode. Periksa:

```bash
python -c "from config.settings import validate; validate()"
```

Isi env var yang masih kosong.

### Bot berjalan tapi tidak ada trade yang terpicu

1. Spread pasar sedang terlalu kecil — ini normal. Coba turunkan sementara:
   ```bash
   python main.py --mode paper --min-spread 0.010
   ```
2. Pastikan koneksi internet stabil (WebSocket putus = tidak ada data).
3. Cek log dengan `--log-level DEBUG` untuk detail.

### Dashboard tidak muncul / tampilan rusak

Terminal tidak mendukung warna ANSI. Gunakan:
- Windows: **Windows Terminal** (bukan CMD lama)
- macOS/Linux: Terminal standar sudah mendukung

```bash
# Fallback: jalankan tanpa TUI, output ke log file
python main.py --mode paper --log-level INFO 2>&1 | tee run.log
```

### Database error: `unable to open database file`

Direktori `data/` belum ada:

```bash
mkdir data
```

### `pytest` tidak menemukan modul

Jalankan dari root direktori project (bukan dari dalam `tests/`):

```bash
# Benar
cd prototype-9
pytest tests/ -v

# Salah — jangan masuk ke folder tests
cd tests && pytest  # ini akan gagal
```

---

## 11. Pre-Live Checklist

Selesaikan **semua item** sebelum switch ke live mode:

### Paper Trading Validation

- [ ] Minimum **50 paper trades** selesai
- [ ] **Win rate ≥ 65%** selama minimal 2 minggu (pantau dengan `report.py`)
- [ ] Average net profit per trade **positif** setelah biaya gas simulasi
- [ ] Tidak ada unhandled exception di log selama 48 jam berjalan terus
- [ ] Circuit breaker harian sudah diuji: set `DAILY_LOSS_LIMIT=0.01`, verifikasi bot berhenti

### Wallet & API

- [ ] Wallet Polygon diisi USDC (mulai dari $100–200)
- [ ] Polymarket API keys ditest berhasil via panggilan GET market
- [ ] Gas estimator dikalibrasi — bandingkan estimasi bot vs [PolygonScan](https://polygonscan.com)
- [ ] File `.env` tidak mengandung test keys di konfigurasi production

### System Stability

- [ ] Bot berjalan **48 jam non-stop** tanpa crash di paper mode
- [ ] Auto-reconnect WebSocket diuji (putuskan koneksi, konfirmasi recovery)
- [ ] Laptop sleep/hibernate **dinonaktifkan** selama jam trading
- [ ] Kill switch `Ctrl+C` diuji — konfirmasi database terkunci dengan benar

### Risk Parameters (Minggu Pertama Live)

- [ ] `MAX_POSITION_USD=10` (maks $10 per trade)
- [ ] `DAILY_LOSS_LIMIT` ≤ 5% dari total modal
- [ ] `MAX_OPEN_POSITIONS=2`
- [ ] Review setiap hari selama 7 hari pertama sebelum naikkan limits

---

## Referensi Cepat

```bash
# Jalankan paper mode
python main.py --mode paper

# Jalankan dengan debug penuh
python main.py --mode paper --log-level DEBUG

# Cek semua test
pytest tests/ -v

# Laporan 7 hari
python utils/report.py --period 7d

# Validasi settings untuk live
python -c "from config.settings import validate; validate()"

# Jalankan live mode
python main.py --mode live
```

---

*Prototype-9 — Alpha v0.1 | Paper trading only. Trade at your own risk.*
