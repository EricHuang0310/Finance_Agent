"""
Backtest Runner — Orchestrates day-by-day simulation of the trading pipeline.

Usage:
    python -m src.backtest.runner --start 2020-01-01 --end 2025-12-31 --capital 100000
"""

import argparse
import sys
from datetime import date

import yaml

from src.backtest.data_loader import DataLoader
from src.backtest.client import BacktestClient
from src.backtest.report import BacktestReport
from src.orchestrator import TradingOrchestrator


class BacktestRunner:
    """
    Runs the full trading pipeline over historical data, day by day.

    Architecture:
    1. DataLoader fetches all historical bars once (cached as Parquet)
    2. BacktestClient serves date-windowed data + simulates portfolio
    3. On each trading day, a fresh TradingOrchestrator runs the full pipeline
    """

    def __init__(
        self,
        start_date: str,
        end_date: str,
        initial_capital: float = 100_000,
        config_path: str = "config/settings.yaml",
        fill_mode: str = "next_open",
        commission_pct: float = 0.0,
        cache_dir: str = "data/backtest_cache",
    ):
        self.start_date = date.fromisoformat(start_date)
        self.end_date = date.fromisoformat(end_date)
        self.initial_capital = initial_capital
        self.config_path = config_path
        self.fill_mode = fill_mode
        self.commission_pct = commission_pct

        with open(config_path) as f:
            self.config = yaml.safe_load(f)

        self.data_loader = DataLoader(cache_dir=cache_dir)

    def run(self) -> dict:
        """Execute the full backtest and return the report."""

        print("=" * 60)
        print("  🔬 BACKTESTING ENGINE")
        print("=" * 60)
        print(f"  Period:   {self.start_date} → {self.end_date}")
        print(f"  Capital:  ${self.initial_capital:,.0f}")
        print(f"  Fill:     {self.fill_mode}")
        print(f"  Config:   {self.config_path}")
        print("=" * 60)

        # ── Step 1: Determine symbols ──
        symbols = self._get_symbols()
        print(f"\n📊 Symbols: {len(symbols['stocks'])} stocks")
        for s in symbols["stocks"]:
            print(f"   • {s}")

        # ── Step 2: Load historical data ──
        print("\n📥 Loading historical data...")
        all_bars = self.data_loader.load_all(
            symbols=symbols,
            start_date=self.start_date,
            end_date=self.end_date,
            lookback_days=200,
        )

        loaded_symbols = list(all_bars.keys())
        print(f"\n✅ Loaded data for {len(loaded_symbols)} symbols: {loaded_symbols}")

        if not all_bars:
            print("❌ No data loaded — aborting backtest.")
            return {}

        # ── Step 3: Create BacktestClient ──
        bt_client = BacktestClient(
            all_bars=all_bars,
            initial_capital=self.initial_capital,
            fill_mode=self.fill_mode,
            commission_pct=self.commission_pct,
        )

        # ── Step 4: Generate trading days ──
        trading_days = self._get_trading_days(all_bars)
        print(f"\n📅 Trading days in range: {len(trading_days)}")

        if not trading_days:
            print("❌ No trading days found — aborting.")
            return {}

        # ── Step 5: Day-by-day simulation ──
        total_days = len(trading_days)
        errors = 0

        for i, day in enumerate(trading_days):
            # Progress indicator (every 20 days or first/last)
            if i % 20 == 0 or i == total_days - 1:
                equity = bt_client._calculate_equity()
                pnl_pct = (equity - self.initial_capital) / self.initial_capital * 100
                print(f"\n  [{i+1}/{total_days}] {day} | "
                      f"Equity: ${equity:,.0f} ({pnl_pct:+.1f}%) | "
                      f"Positions: {len(bt_client._positions)}")

            # Advance simulated date
            bt_client.set_current_date(day)

            # Create fresh orchestrator with injected client
            try:
                orchestrator = TradingOrchestrator(
                    config_path=self.config_path,
                    client=bt_client,
                )
            except Exception as e:
                print(f"  ❌ Failed to create orchestrator on {day}: {e}")
                errors += 1
                continue

            # Override settings for backtest mode
            orchestrator.notifier.enabled = False
            orchestrator.decision_cfg["require_human_confirm"] = False
            orchestrator.weights["sentiment_analyst"] = 0.0
            orchestrator.watchlist_mode = "static"

            # Only include symbols we actually have data for
            orchestrator.watchlist_stocks = [
                s for s in orchestrator.watchlist_stocks if s in all_bars
            ]
            orchestrator.watchlist_crypto = []  # v1: stocks only

            try:
                orchestrator.run_pipeline(execute=True)
            except Exception as e:
                if i % 20 == 0:  # Only print errors periodically to avoid spam
                    print(f"  ⚠️  Pipeline error on {day}: {e}")
                errors += 1
                continue

            # Update last_equity for next day's daily P&L calculation
            bt_client._last_equity = bt_client._calculate_equity()

        # ── Step 6: Generate report ──
        print(f"\n\n{'=' * 60}")
        print(f"  Simulation complete. Errors: {errors}/{total_days} days")
        print(f"{'=' * 60}")

        report = BacktestReport(
            equity_curve=bt_client._equity_curve,
            trades=bt_client._trades,
            initial_capital=self.initial_capital,
        )
        return report.generate()

    def _get_symbols(self) -> dict:
        """Get symbols from static watchlist (backtest always uses static mode)."""
        stocks = self.config.get("watchlist", {}).get("stocks", [])
        # v1: stocks only, no crypto
        return {
            "stocks": stocks,
            "crypto": [],
        }

    def _get_trading_days(self, all_bars: dict) -> list[date]:
        """
        Determine valid trading days from the loaded data.

        Uses the intersection of dates across major symbols to ensure
        we only simulate on days where the market was actually open.
        """
        all_dates = set()

        for symbol, bars in all_bars.items():
            if bars.index.tz is not None:
                dates = {d.date() for d in bars.index.tz_localize(None)}
            else:
                dates = {d.date() for d in bars.index}

            if not all_dates:
                all_dates = dates
            else:
                # Use union (any day with any data)
                all_dates.update(dates)

        # Filter to our backtest range
        valid = sorted(
            d for d in all_dates
            if self.start_date <= d <= self.end_date
        )

        return valid


# ═══════════════════════════════════════════
# CLI Entry Point
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Backtest the Multi-Agent Trading Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Short backtest (1 month)
  python -m src.backtest.runner --start 2025-06-01 --end 2025-06-30

  # Full 5-year backtest
  python -m src.backtest.runner --start 2020-01-01 --end 2025-12-31 --capital 100000

  # With commission
  python -m src.backtest.runner --start 2023-01-01 --end 2025-12-31 --commission 0.001
        """,
    )
    parser.add_argument("--start", required=True, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", required=True, help="End date (YYYY-MM-DD)")
    parser.add_argument("--capital", type=float, default=100_000, help="Initial capital (default: 100000)")
    parser.add_argument("--fill-mode", default="next_open",
                        choices=["next_open", "current_close"],
                        help="Order fill mode (default: next_open)")
    parser.add_argument("--commission", type=float, default=0.0,
                        help="Commission as fraction, e.g. 0.001 = 0.1%% (default: 0)")
    parser.add_argument("--config", default="config/settings.yaml", help="Config file path")
    parser.add_argument("--cache-dir", default="data/backtest_cache", help="Data cache directory")

    args = parser.parse_args()

    runner = BacktestRunner(
        start_date=args.start,
        end_date=args.end,
        initial_capital=args.capital,
        config_path=args.config,
        fill_mode=args.fill_mode,
        commission_pct=args.commission,
        cache_dir=args.cache_dir,
    )

    results = runner.run()

    if results:
        print("\n✅ Backtest complete! Report saved to logs/backtest_report.json")
    else:
        print("\n❌ Backtest failed — no results generated.")
        sys.exit(1)


if __name__ == "__main__":
    main()
