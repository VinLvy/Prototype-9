"""
utils/market_discovery.py
--------------------------
CLI utility to browse and discover active Polymarket binary markets.
Handles ephemeral 5M/15M markets which open/close on rolling windows.

KEY INSIGHT: 5-minute and 15-minute markets are time-ephemeral.
They exist for their duration then immediately close. The standard
`active=true&closed=false` query misses them if queried between windows.

Strategy for ephemeral markets:
  - Query without closed filter, sort by endDate, narrow to a ±35 min window
  - OR use --watch mode to poll every 30s and catch the next window open

Usage:
    # One-shot: find any active markets (standard)
    python utils/market_discovery.py --keyword bitcoin

    # Find 5M/15M markets specifically (includes current + upcoming window)
    python utils/market_discovery.py --timeframe 5m
    python utils/market_discovery.py --timeframe 15m

    # Watch mode: poll every 30s, prints new windows as they open
    python utils/market_discovery.py --timeframe 5m --watch

    # Show all short-window markets
    python utils/market_discovery.py --timeframe all --limit 50
"""

import argparse
import asyncio
import json
from datetime import datetime, timezone, timedelta

import aiohttp
from rich.console import Console
from rich.table import Table
from rich import box

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
console = Console()

# Slug prefixes used by Polymarket for each timeframe
TIMEFRAME_SLUG_MAP = {
    "5m":  ["btc-updown-5m", "eth-updown-5m", "sol-updown-5m", "xrp-updown-5m", "doge-updown-5m"],
    "15m": ["btc-updown-15m", "eth-updown-15m", "sol-updown-15m", "xrp-updown-15m"],
    "1h":  ["btc-updown-1h", "eth-updown-1h", "sol-updown-1h"],
    "4h":  ["btc-updown-4h", "eth-updown-4h", "sol-updown-4h"],
    "all": ["btc-updown", "eth-updown", "sol-updown", "xrp-updown", "doge-updown"],
}


async def fetch_markets_open(keyword: str = "", limit: int = 20) -> list:
    """Standard fetch: only truly open markets."""
    params = {
        "active":    "true",
        "closed":    "false",
        "limit":     limit * 4,
        "order":     "endDate",
        "ascending": "true",
    }
    return await _fetch(params, keyword, limit)


async def fetch_markets_ephemeral(timeframe: str, limit: int = 30) -> list:
    """
    Fetch for short-window markets. Includes recently closed (last 5 min)
    and open markets in the current/upcoming window (next 35 min).

    These markets have endDate within a tight window. We cast a wider net
    by querying without the closed filter and sorting by endDate ascending.
    """
    now          = datetime.now(timezone.utc)
    window_start = (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    window_end   = (now + timedelta(minutes=35)).strftime("%Y-%m-%dT%H:%M:%SZ")

    prefixes    = TIMEFRAME_SLUG_MAP.get(timeframe, TIMEFRAME_SLUG_MAP["all"])
    all_markets = []

    async with aiohttp.ClientSession() as session:
        for prefix in prefixes:
            params = {
                "active":       "true",
                "limit":        10,
                "order":        "endDate",
                "ascending":    "true",
                "end_date_min": window_start,
                "end_date_max": window_end,
            }
            try:
                async with session.get(
                    f"{GAMMA_API_BASE}/markets",
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=15)
                ) as resp:
                    if resp.status == 200:
                        markets = await resp.json()
                        filtered = [
                            m for m in markets
                            if (m.get("slug") or "").startswith(prefix)
                            and m.get("clobTokenIds")
                        ]
                        all_markets.extend(filtered)
            except Exception as e:
                console.print(f"[dim red]Warning: fetch failed for {prefix}: {e}[/dim red]")

    # Deduplicate by conditionId
    seen, unique = set(), []
    for m in all_markets:
        cid = m.get("conditionId")
        if cid not in seen:
            seen.add(cid)
            unique.append(m)

    unique.sort(key=lambda m: m.get("endDateIso") or m.get("endDate") or "")
    return unique[:limit]


async def _fetch(params: dict, keyword: str, limit: int) -> list:
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{GAMMA_API_BASE}/markets",
            params=params,
            timeout=aiohttp.ClientTimeout(total=15)
        ) as resp:
            if resp.status != 200:
                console.print(f"[red]API error {resp.status}: {await resp.text()}[/red]")
                return []
            markets = await resp.json()

    markets = [m for m in markets if m.get("clobTokenIds") and m.get("enableOrderBook")]

    if keyword:
        kw = keyword.lower()
        markets = [
            m for m in markets
            if kw in (m.get("question") or "").lower()
            or kw in (m.get("slug") or "").lower()
        ]

    return markets[:limit]


def display_markets(markets: list, title: str = "Active Polymarket CLOB Markets"):
    if not markets:
        console.print("[yellow]No markets found in this window.[/yellow]")
        console.print("[dim]5M/15M markets are ephemeral — they open at fixed intervals.[/dim]")
        console.print("[dim]Try: --watch to poll every 30s, or wait for the next window to open.[/dim]")
        return

    table = Table(title=title, box=box.ROUNDED, show_header=True, header_style="bold cyan")
    table.add_column("#",                 width=3)
    table.add_column("Question",          min_width=38)
    table.add_column("Slug",              style="dim", min_width=22)
    table.add_column("End (UTC)",         width=19)
    table.add_column("Status",            width=10)
    table.add_column("Vol 24h",           justify="right", style="green", width=10)
    table.add_column("YES token_id (22)", style="yellow",  width=25)
    table.add_column("NO token_id (22)",  style="red",     width=25)

    now = datetime.now(timezone.utc)

    for i, m in enumerate(markets, 1):
        try:
            token_ids = json.loads(m.get("clobTokenIds", "[]"))
            yes_id    = token_ids[0][:22] + "…" if len(token_ids) > 0 else "N/A"
            no_id     = token_ids[1][:22] + "…" if len(token_ids) > 1 else "N/A"
        except Exception:
            yes_id = no_id = "parse error"

        vol     = m.get("volume24hr") or 0
        end_raw = m.get("endDateIso") or m.get("endDate") or ""
        end_str = end_raw[:19].replace("T", " ") if end_raw else "—"

        # Compute live status
        status = "[green]LIVE[/green]"
        try:
            end_dt = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
            delta  = (end_dt - now).total_seconds()
            if delta < 0:
                status = "[dim]CLOSED[/dim]"
            elif delta < 60:
                status = f"[bold red]{int(delta)}s left[/bold red]"
            elif delta < 300:
                status = f"[yellow]{int(delta // 60)}m {int(delta % 60)}s[/yellow]"
        except Exception:
            pass

        table.add_row(
            str(i),
            (m.get("question") or "")[:55],
            (m.get("slug") or "")[:28],
            end_str,
            status,
            f"${float(vol):,.0f}" if vol else "—",
            yes_id,
            no_id,
        )

    console.print(table)
    console.print(
        f"\n[dim]Shown: {len(markets)} | "
        f"Time: {now.strftime('%H:%M:%S UTC')}[/dim]"
    )
    console.print(
        "[dim]Get full token IDs via: "
        "curl 'https://gamma-api.polymarket.com/markets?slug=<slug>'[/dim]"
    )


async def watch_mode(timeframe: str, poll_interval: int = 30):
    """Poll continuously and refresh table when new windows open."""
    console.print(
        f"[bold cyan]Watch mode[/bold cyan] — polling every {poll_interval}s "
        f"for [{timeframe.upper()}] markets. Ctrl+C to stop.\n"
    )
    seen_slugs: set = set()
    while True:
        markets     = await fetch_markets_ephemeral(timeframe)
        new_markets = [m for m in markets if m.get("slug") not in seen_slugs]

        if new_markets:
            for m in new_markets:
                seen_slugs.add(m.get("slug"))
            display_markets(
                markets,
                title=f"[{timeframe.upper()}] — {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
            )
        else:
            now = datetime.now(timezone.utc)
            console.print(
                f"[dim]{now.strftime('%H:%M:%S')} — "
                f"no new windows. Next check in {poll_interval}s...[/dim]"
            )

        await asyncio.sleep(poll_interval)


async def main(args):
    if args.watch:
        await watch_mode(args.timeframe or "5m", poll_interval=args.poll)
        return

    if args.timeframe:
        console.print(
            f"[bold cyan]Fetching [{args.timeframe.upper()}] markets[/bold cyan] "
            f"(current + upcoming window)..."
        )
        markets = await fetch_markets_ephemeral(args.timeframe, limit=args.limit)
        display_markets(markets, title=f"[{args.timeframe.upper()}] Polymarket CLOB Markets")
    else:
        console.print(
            f"[bold cyan]Fetching markets[/bold cyan] "
            f"(keyword={args.keyword!r}, limit={args.limit})..."
        )
        markets = await fetch_markets_open(keyword=args.keyword, limit=args.limit)
        display_markets(markets)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Browse active Polymarket CLOB markets",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python utils/market_discovery.py --keyword bitcoin
  python utils/market_discovery.py --timeframe 5m
  python utils/market_discovery.py --timeframe 15m --watch
  python utils/market_discovery.py --timeframe all --limit 50
        """
    )
    parser.add_argument("--keyword",   "-k", default="",    help="Filter keyword (without --timeframe)")
    parser.add_argument("--timeframe", "-t", default="",    help="Ephemeral window: 5m | 15m | 1h | 4h | all")
    parser.add_argument("--limit",     "-l", type=int, default=20, help="Max results (default: 20)")
    parser.add_argument("--watch",     "-w", action="store_true",  help="Poll continuously for new windows")
    parser.add_argument("--poll",      "-p", type=int, default=30, help="Watch poll interval seconds (default: 30)")
    args = parser.parse_args()
    try:
        asyncio.run(main(args))
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")