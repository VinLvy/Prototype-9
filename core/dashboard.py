"""
core/dashboard.py
------------------
Live Rich TUI dashboard for Prototype-9.
Renders P&L, open opportunities, and execution log in the terminal.

Matches the layout described in README § Dashboard.
"""

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich import box


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data models for dashboard state
# ---------------------------------------------------------------------------

@dataclass
class Opportunity:
    market_id: str
    spread_pct: float       # e.g. 0.024 → 2.4%
    estimated_profit: float # in USD per position
    yes_price: float
    no_price: float


@dataclass
class ExecutionRecord:
    timestamp: datetime
    market_id: str
    spread_pct: float
    pnl: float              # positive = win, negative = loss
    status: str             # "WIN" | "LOSS" | "FILLED" | "REJECTED"


@dataclass
class DashboardState:
    mode: str = "PAPER"
    pnl_today: float = 0.0
    bankroll: float = 1000.0
    win_count: int = 0
    loss_count: int = 0
    opportunities: List[Opportunity] = field(default_factory=list)
    log: deque = field(default_factory=lambda: deque(maxlen=10))

    @property
    def win_rate(self) -> float:
        total = self.win_count + self.loss_count
        return (self.win_count / total * 100) if total > 0 else 0.0

    @property
    def open_opps(self) -> int:
        return len(self.opportunities)


# ---------------------------------------------------------------------------
# Dashboard renderer
# ---------------------------------------------------------------------------

class Dashboard:
    """
    Renders a live terminal UI using the Rich library.
    Provides P&L stats, live opportunities table, and scrolling execution log.
    """

    REFRESH_RATE: float = 1.0  # seconds between redraws

    def __init__(self):
        self.console = Console()
        self.state = DashboardState()
        self._live: Optional[Live] = None

    # ------------------------------------------------------------------
    # Public state update methods (called by other modules)
    # ------------------------------------------------------------------

    def set_mode(self, mode: str):
        self.state.mode = mode.upper()

    def update_market_data(self, tick: dict):
        """Called by PriceMonitor to refresh opportunity list with latest prices."""
        # Simple pass-through; ArbitrageDetector signals are richer
        pass

    def record_opportunity(self, signal: dict):
        """Add or update an opportunity in the header table."""
        opp = Opportunity(
            market_id=signal.get("market_id", "UNKNOWN"),
            spread_pct=signal.get("spread", 0.0),
            estimated_profit=signal.get("estimated_profit_per_share", 0.0),
            yes_price=signal.get("yes_price", 0.0),
            no_price=signal.get("no_price", 0.0),
        )
        # Replace if same market already listed, otherwise append
        self.state.opportunities = [
            o for o in self.state.opportunities if o.market_id != opp.market_id
        ]
        self.state.opportunities.insert(0, opp)

    def record_execution(self, trade: dict):
        """Add an entry to the execution log and update P&L counters."""
        pnl = trade.get("estimated_profit", 0.0)
        status = trade.get("status", "FILLED")

        rec = ExecutionRecord(
            timestamp=datetime.now(),
            market_id=trade.get("market_id", "UNKNOWN"),
            spread_pct=trade.get("spread", 0.0),
            pnl=pnl,
            status=status,
        )

        self.state.log.appendleft(rec)
        self.state.pnl_today += pnl
        self.state.bankroll += pnl

        if status == "WIN":
            self.state.win_count += 1
        elif status == "LOSS":
            self.state.loss_count += 1

        # Jika sudah WIN atau LOSS (posisi closed/resolved), 
        # maka bersihkan dari tabel Live Opportunities.
        if status in ["WIN", "LOSS", "REJECTED"]:
            self.state.opportunities = [
                o for o in self.state.opportunities if o.market_id != trade.get("market_id")
            ]

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _build_header_panel(self) -> Panel:
        """Top stats bar: P&L, win rate, open opps, bankroll."""
        s = self.state
        pnl_sign = "+" if s.pnl_today >= 0 else ""
        pnl_color = "green" if s.pnl_today >= 0 else "red"

        table = Table.grid(padding=(0, 4))
        table.add_column(justify="center")
        table.add_column(justify="center")
        table.add_column(justify="center")
        table.add_column(justify="center")

        table.add_row(
            Text("P&L Today", style="bold cyan"),
            Text("Win Rate", style="bold cyan"),
            Text("Open Opps", style="bold cyan"),
            Text("Bankroll", style="bold cyan"),
        )
        table.add_row(
            Text(f"{pnl_sign}${s.pnl_today:.2f}", style=f"bold {pnl_color}"),
            Text(f"{s.win_rate:.0f}%", style="bold white"),
            Text(str(s.open_opps), style="bold yellow"),
            Text(f"${s.bankroll:.2f}", style="bold white"),
        )

        return Panel(
            table,
            title=f"[bold white]PROTOTYPE-9[/]   [dim]{s.mode} MODE[/]",
            border_style="bright_cyan",
            box=box.DOUBLE_EDGE,
        )

    def _build_opportunities_panel(self) -> Panel:
        """Live opportunities table."""
        table = Table(
            show_header=True,
            header_style="bold magenta",
            box=box.SIMPLE_HEAVY,
            expand=True,
        )
        table.add_column("Market", style="white", min_width=20)
        table.add_column("Spread", justify="right", style="green")
        table.add_column("Est. Profit", justify="right", style="bright_green")
        table.add_column("YES", justify="right", style="dim")
        table.add_column("NO", justify="right", style="dim")

        opps = self.state.opportunities
        if not opps:
            table.add_row("[dim]Scanning…[/]", "", "", "", "")
        else:
            for opp in opps[:5]:  # show at most 5
                table.add_row(
                    opp.market_id,
                    f"{opp.spread_pct * 100:.1f}%",
                    f"+${opp.estimated_profit:.4f}",
                    f"{opp.yes_price:.3f}",
                    f"{opp.no_price:.3f}",
                )

        return Panel(
            table,
            title="[bold]LIVE OPPORTUNITIES[/]",
            border_style="green",
            box=box.ROUNDED,
        )

    def _build_log_panel(self) -> Panel:
        """Scrolling execution log."""
        table = Table(
            show_header=False,
            box=None,
            expand=True,
            padding=(0, 1),
        )
        table.add_column("Time", style="dim", width=10)
        table.add_column("Status", width=6)
        table.add_column("Market", style="white")
        table.add_column("Spread", justify="right", style="cyan")
        table.add_column("P&L", justify="right")

        if not self.state.log:
            table.add_row("", "[dim]No trades yet[/]", "", "", "")
        else:
            for rec in self.state.log:
                status_color = "green" if rec.status == "WIN" else "red" if rec.status == "LOSS" else "yellow"
                pnl_str = f"+${rec.pnl:.2f}" if rec.pnl >= 0 else f"-${abs(rec.pnl):.2f}"
                pnl_color = "green" if rec.pnl >= 0 else "red"
                table.add_row(
                    rec.timestamp.strftime("%H:%M:%S"),
                    f"[{status_color}]{rec.status}[/{status_color}]",
                    rec.market_id,
                    f"{rec.spread_pct * 100:.1f}%",
                    f"[{pnl_color}]{pnl_str}[/{pnl_color}]",
                )

        return Panel(
            table,
            title="[bold]EXECUTION LOG[/]",
            border_style="yellow",
            box=box.ROUNDED,
        )

    def _build_footer(self) -> Text:
        return Text(
            "  [Q] Quit   [P] Pause   [K] Kill all positions",
            style="dim",
            justify="center",
        )

    def _render(self) -> Layout:
        layout = Layout()
        layout.split_column(
            Layout(self._build_header_panel(), name="header", size=6),
            Layout(self._build_opportunities_panel(), name="opps", size=10),
            Layout(self._build_log_panel(), name="log"),
            Layout(self._build_footer(), name="footer", size=1),
        )
        return layout

    # ------------------------------------------------------------------
    # Async render loop
    # ------------------------------------------------------------------

    async def render_loop(self):
        """
        Long-running async task that redraws the dashboard every REFRESH_RATE seconds.
        Wraps Rich Live context manager in a non-blocking asyncio loop.
        """
        try:
            with Live(
                self._render(),
                console=self.console,
                refresh_per_second=int(1 / self.REFRESH_RATE),
                screen=True,
            ) as live:
                self._live = live
                while True:
                    live.update(self._render())
                    await asyncio.sleep(self.REFRESH_RATE)
        except asyncio.CancelledError:
            pass
        finally:
            self._live = None
            logger.info("Dashboard stopped.")
