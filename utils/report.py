"""
utils/report.py
----------------
Performance analytics report generator for Prototype-9.

Usage:
    python utils/report.py --period 7d
    python utils/report.py --period 30d --export trades_report.csv

Reads from the SQLite trades database and outputs:
  - Total P&L
  - Win rate
  - Average profit/loss per trade
  - Gas costs breakdown (simulated)
  - Best/worst performing markets
  - Capital velocity (trades per day)
"""

import argparse
import sqlite3
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich import box
    HAS_RICH = True
except ImportError:
    HAS_RICH = False


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DEFAULT_DB_PATH = os.getenv("DB_PATH", "./data/trades.db")
PERIOD_MAP = {
    "1d": 1,
    "7d": 7,
    "30d": 30,
    "all": None,
}


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------

def load_trades(db_path: str, days: Optional[int]) -> list:
    """Load trades from SQLite, optionally filtered to the last N days."""
    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    if days is not None:
        since = datetime.now() - timedelta(days=days)
        cursor.execute(
            "SELECT * FROM trades WHERE timestamp >= ? ORDER BY timestamp DESC",
            (since.strftime("%Y-%m-%d %H:%M:%S"),),
        )
    else:
        cursor.execute("SELECT * FROM trades ORDER BY timestamp DESC")

    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return rows


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

def compute_stats(trades: list) -> dict:
    if not trades:
        return {}

    profits = [t["estimated_profit"] for t in trades]
    wins = [p for p in profits if p > 0]
    losses = [p for p in profits if p <= 0]

    total_pnl = sum(profits)
    win_count = len(wins)
    loss_count = len(losses)
    total_trades = len(trades)
    win_rate = (win_count / total_trades * 100) if total_trades else 0.0

    avg_win = (sum(wins) / win_count) if wins else 0.0
    avg_loss = (sum(losses) / loss_count) if losses else 0.0
    avg_trade = total_pnl / total_trades if total_trades else 0.0

    # Market breakdown
    market_pnl: dict = {}
    for t in trades:
        mid = t["market_id"]
        market_pnl[mid] = market_pnl.get(mid, 0.0) + t["estimated_profit"]

    best_market = max(market_pnl, key=market_pnl.get) if market_pnl else "N/A"
    worst_market = min(market_pnl, key=market_pnl.get) if market_pnl else "N/A"

    # Capital velocity
    if total_trades >= 2:
        dt_first = datetime.strptime(trades[-1]["timestamp"], "%Y-%m-%d %H:%M:%S")
        dt_last = datetime.strptime(trades[0]["timestamp"], "%Y-%m-%d %H:%M:%S")
        days_span = max((dt_last - dt_first).days, 1)
        velocity = total_trades / days_span
    else:
        velocity = float(total_trades)

    return {
        "total_trades": total_trades,
        "total_pnl": total_pnl,
        "win_count": win_count,
        "loss_count": loss_count,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "avg_trade": avg_trade,
        "best_market": best_market,
        "worst_market": worst_market,
        "capital_velocity": velocity,
        "market_pnl": market_pnl,
    }


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def print_rich_report(stats: dict, period_label: str):
    console = Console()

    pnl = stats["total_pnl"]
    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
    pnl_color = "green" if pnl >= 0 else "red"

    # Summary table
    summary = Table(title=f"Prototype-9 Performance Report — {period_label}", box=box.DOUBLE_EDGE)
    summary.add_column("Metric", style="cyan", min_width=28)
    summary.add_column("Value", justify="right", style="white")

    summary.add_row("Total Trades", str(stats["total_trades"]))
    summary.add_row("Total P&L", f"[{pnl_color}]{pnl_str}[/{pnl_color}]")
    summary.add_row("Win Rate", f"{stats['win_rate']:.1f}%")
    summary.add_row("Wins / Losses", f"{stats['win_count']} / {stats['loss_count']}")
    summary.add_row("Avg Profit (wins)", f"+${stats['avg_win']:.4f}")
    summary.add_row("Avg Loss (losses)", f"-${abs(stats['avg_loss']):.4f}")
    summary.add_row("Avg P&L per Trade", f"${stats['avg_trade']:.4f}")
    summary.add_row("Capital Velocity", f"{stats['capital_velocity']:.1f} trades/day")
    summary.add_row("Best Market", stats["best_market"])
    summary.add_row("Worst Market", stats["worst_market"])

    console.print()
    console.print(summary)

    # Market breakdown
    if stats.get("market_pnl"):
        mkt_table = Table(title="P&L by Market", box=box.SIMPLE_HEAVY)
        mkt_table.add_column("Market", style="white")
        mkt_table.add_column("P&L", justify="right")
        for mkt, mp in sorted(stats["market_pnl"].items(), key=lambda x: -x[1]):
            color = "green" if mp >= 0 else "red"
            mkt_table.add_row(mkt, f"[{color}]+${mp:.4f}[/{color}]" if mp >= 0 else f"[{color}]-${abs(mp):.4f}[/{color}]")
        console.print(mkt_table)


def print_plain_report(stats: dict, period_label: str):
    print(f"\n=== Prototype-9 Report ({period_label}) ===")
    for k, v in stats.items():
        if k == "market_pnl":
            continue
        print(f"  {k:28s}: {v}")


def export_csv(trades: list, path: str):
    if not HAS_PANDAS:
        print("[WARN] pandas not installed. Cannot export CSV.")
        return
    df = pd.DataFrame(trades)
    df.to_csv(path, index=False)
    print(f"[OK] Exported {len(df)} trades to {path}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Prototype-9 Performance Report Generator")
    parser.add_argument(
        "--period",
        choices=list(PERIOD_MAP.keys()),
        default="7d",
        help="Time window for the report (default: 7d)",
    )
    parser.add_argument(
        "--db",
        default=DEFAULT_DB_PATH,
        help=f"Path to SQLite trades database (default: {DEFAULT_DB_PATH})",
    )
    parser.add_argument(
        "--export",
        metavar="FILE.csv",
        default=None,
        help="Export trade history to CSV file",
    )
    args = parser.parse_args()

    days = PERIOD_MAP[args.period]
    period_label = args.period.upper()

    trades = load_trades(args.db, days)

    if args.export:
        export_csv(trades, args.export)

    if not trades:
        print(f"No trades found in the last {period_label}.")
        return

    stats = compute_stats(trades)

    if HAS_RICH:
        print_rich_report(stats, period_label)
    else:
        print_plain_report(stats, period_label)


if __name__ == "__main__":
    main()
