import sqlite3
import argparse
from rich.console import Console
from rich.table import Table

def main(db_path, limit):
    console = Console()
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Cek ketersediaan tabel
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trades'")
        if not cursor.fetchone():
            console.print("[yellow]Tabel 'trades' belum ada. Belum ada trade yang dicatat.[/yellow]")
            return

        cursor.execute(f"SELECT timestamp, market_id, mode, size_usd, spread, estimated_profit, status FROM trades ORDER BY id DESC LIMIT {limit}")
        rows = cursor.fetchall()
        
        if not rows:
            console.print("[dim]Database trades.db masih kosong.[/dim]")
            return
            
        table = Table(title="History Eksekusi Trade (trades.db)", show_lines=True)
        table.add_column("Waktu (UTC)", style="dim")
        table.add_column("Market", min_width=30)
        table.add_column("Mode", justify="center")
        table.add_column("Size ($)", justify="right")
        table.add_column("Spread", justify="right", style="cyan")
        table.add_column("Est. Profit", justify="right", style="bold green")
        table.add_column("Status", justify="center")
        
        for row in rows:
            timestamp, market_id, mode, size_usd, spread, profit, status = row
            market_str = market_id[:40] + "..." if len(market_id) > 40 else market_id
            color = "green" if status == "WIN" else "yellow" if status == "FILLED" else "red"
            
            table.add_row(
                timestamp, 
                market_str, 
                mode.upper(), 
                f"${size_usd:.2f}", 
                f"{spread*100:.1f}%", 
                f"${profit:.4f}" if profit >= 0 else f"-${abs(profit):.4f}", 
                f"[{color}]{status}[/{color}]"
            )
            
        console.print(table)
        
    except sqlite3.Error as e:
        console.print(f"[red]Error saat membaca database: {e}[/red]")
    finally:
        if 'conn' in locals():
            conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="./data/trades.db", help="Lokasi database")
    parser.add_argument("--limit", type=int, default=50, help="Batas history yang ditampilkan")
    args = parser.parse_args()
    main(args.db, args.limit)
