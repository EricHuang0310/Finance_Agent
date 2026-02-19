"""
Backtest Performance Report.

Computes standard backtesting metrics from the equity curve and trade log,
outputs a formatted console summary and saves detailed JSON report.
"""

import json
from datetime import datetime
from pathlib import Path


class BacktestReport:
    """Compute and format backtest performance metrics."""

    def __init__(
        self,
        equity_curve: list[dict],
        trades: list[dict],
        initial_capital: float,
    ):
        self.equity_curve = equity_curve
        self.trades = trades
        self.initial_capital = initial_capital

    def generate(self) -> dict:
        """Generate the complete backtest report."""
        metrics = self._compute_metrics()
        trade_analysis = self._analyze_trades()

        report = {
            "summary": metrics,
            "trade_analysis": trade_analysis,
            "equity_curve": self.equity_curve,
            "trades": self.trades,
            "generated_at": datetime.now().isoformat(),
        }

        # Save to file
        output_dir = Path("logs")
        output_dir.mkdir(exist_ok=True)
        output_path = output_dir / "backtest_report.json"
        with open(output_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        self._print_report(metrics, trade_analysis)
        return report

    def _compute_metrics(self) -> dict:
        """Compute portfolio-level performance metrics."""
        if not self.equity_curve:
            return {"error": "No equity data"}

        equities = [e["equity"] for e in self.equity_curve]
        dates = [e["date"] for e in self.equity_curve]

        final_equity = equities[-1]
        total_return = (final_equity - self.initial_capital) / self.initial_capital

        # ── Annualized Return ──
        n_days = len(equities)
        trading_days_per_year = 252
        if n_days > 1 and total_return > -1:
            annualized_return = (1 + total_return) ** (trading_days_per_year / n_days) - 1
        else:
            annualized_return = 0.0

        # ── Daily Returns ──
        daily_returns = []
        for i in range(1, len(equities)):
            if equities[i - 1] != 0:
                dr = (equities[i] - equities[i - 1]) / equities[i - 1]
            else:
                dr = 0.0
            daily_returns.append(dr)

        # ── Sharpe Ratio ──
        if daily_returns:
            avg_daily = sum(daily_returns) / len(daily_returns)
            variance = sum((r - avg_daily) ** 2 for r in daily_returns) / len(daily_returns)
            std_daily = variance ** 0.5
            sharpe = (avg_daily / std_daily) * (252 ** 0.5) if std_daily > 0 else 0.0
        else:
            avg_daily = 0.0
            sharpe = 0.0

        # ── Sortino Ratio ──
        negative_returns = [r for r in daily_returns if r < 0]
        if negative_returns:
            downside_variance = sum(r ** 2 for r in negative_returns) / len(negative_returns)
            downside_std = downside_variance ** 0.5
            sortino = (avg_daily / downside_std) * (252 ** 0.5) if downside_std > 0 else 0.0
        else:
            sortino = float("inf") if avg_daily > 0 else 0.0

        # ── Max Drawdown ──
        peak = equities[0]
        max_dd = 0.0
        max_dd_start = dates[0]
        max_dd_end = dates[0]
        dd_start = dates[0]

        for i, eq in enumerate(equities):
            if eq > peak:
                peak = eq
                dd_start = dates[i]
            if peak > 0:
                dd = (peak - eq) / peak
                if dd > max_dd:
                    max_dd = dd
                    max_dd_start = dd_start
                    max_dd_end = dates[i]

        # ── Calmar Ratio ──
        calmar = annualized_return / max_dd if max_dd > 0 else 0.0

        # ── Win/Loss Streaks ──
        max_win_streak, max_loss_streak = self._compute_streaks()

        return {
            "initial_capital": self.initial_capital,
            "final_equity": round(final_equity, 2),
            "total_return_pct": round(total_return * 100, 2),
            "annualized_return_pct": round(annualized_return * 100, 2),
            "sharpe_ratio": round(sharpe, 3),
            "sortino_ratio": round(sortino, 3) if sortino != float("inf") else "inf",
            "calmar_ratio": round(calmar, 3),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "max_drawdown_period": f"{max_dd_start} → {max_dd_end}",
            "max_win_streak": max_win_streak,
            "max_loss_streak": max_loss_streak,
            "trading_days": n_days,
            "start_date": dates[0],
            "end_date": dates[-1],
        }

    def _analyze_trades(self) -> dict:
        """Compute trade-level statistics."""
        # Filter to closed trades (those with realized P&L)
        closed = [t for t in self.trades if t.get("realized_pnl") is not None]

        if not closed:
            return {
                "total_trades": len(self.trades),
                "closed_trades": 0,
                "note": "No closed trades to analyze",
            }

        wins = [t for t in closed if t["realized_pnl"] > 0]
        losses = [t for t in closed if t["realized_pnl"] < 0]
        breakeven = [t for t in closed if t["realized_pnl"] == 0]

        total_wins = sum(t["realized_pnl"] for t in wins)
        total_losses = abs(sum(t["realized_pnl"] for t in losses))

        win_rate = len(wins) / len(closed) if closed else 0.0
        avg_win = total_wins / len(wins) if wins else 0.0
        avg_loss = total_losses / len(losses) if losses else 0.0
        profit_factor = total_wins / total_losses if total_losses > 0 else float("inf")

        total_pnl = sum(t["realized_pnl"] for t in closed)
        expectancy = total_pnl / len(closed)

        # Unique symbols traded
        symbols_traded = list(set(t["symbol"] for t in self.trades))

        # P&L by symbol
        pnl_by_symbol = {}
        for t in closed:
            sym = t["symbol"]
            pnl_by_symbol[sym] = pnl_by_symbol.get(sym, 0) + t["realized_pnl"]
        pnl_by_symbol = {k: round(v, 2) for k, v in sorted(pnl_by_symbol.items(), key=lambda x: x[1], reverse=True)}

        return {
            "total_trades": len(self.trades),
            "closed_trades": len(closed),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "breakeven_trades": len(breakeven),
            "win_rate_pct": round(win_rate * 100, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "largest_win": round(max((t["realized_pnl"] for t in wins), default=0), 2),
            "largest_loss": round(min((t["realized_pnl"] for t in losses), default=0), 2),
            "profit_factor": round(profit_factor, 3) if profit_factor != float("inf") else "inf",
            "expectancy_per_trade": round(expectancy, 2),
            "total_pnl": round(total_pnl, 2),
            "symbols_traded": symbols_traded,
            "pnl_by_symbol": pnl_by_symbol,
        }

    def _compute_streaks(self) -> tuple[int, int]:
        """Compute max consecutive winning and losing trade streaks."""
        closed = [t for t in self.trades if t.get("realized_pnl") is not None]

        max_win = 0
        max_loss = 0
        current_win = 0
        current_loss = 0

        for t in closed:
            if t["realized_pnl"] > 0:
                current_win += 1
                current_loss = 0
                max_win = max(max_win, current_win)
            elif t["realized_pnl"] < 0:
                current_loss += 1
                current_win = 0
                max_loss = max(max_loss, current_loss)
            else:
                current_win = 0
                current_loss = 0

        return max_win, max_loss

    def _print_report(self, metrics: dict, trade_analysis: dict):
        """Print formatted summary to console."""
        print("\n" + "═" * 60)
        print("  📊 BACKTEST RESULTS")
        print("═" * 60)
        print(f"  Period:             {metrics.get('start_date')} → {metrics.get('end_date')}")
        print(f"  Trading Days:       {metrics.get('trading_days')}")
        print()
        print(f"  {'─' * 40}")
        print(f"  💰 PORTFOLIO PERFORMANCE")
        print(f"  {'─' * 40}")
        print(f"  Initial Capital:    ${metrics.get('initial_capital', 0):>12,.2f}")
        print(f"  Final Equity:       ${metrics.get('final_equity', 0):>12,.2f}")
        print(f"  Total Return:       {metrics.get('total_return_pct', 0):>11.2f}%")
        print(f"  Annualized Return:  {metrics.get('annualized_return_pct', 0):>11.2f}%")
        print()
        print(f"  {'─' * 40}")
        print(f"  📈 RISK-ADJUSTED METRICS")
        print(f"  {'─' * 40}")
        print(f"  Sharpe Ratio:       {metrics.get('sharpe_ratio', 0):>11.3f}")
        print(f"  Sortino Ratio:      {str(metrics.get('sortino_ratio', 0)):>11s}")
        print(f"  Calmar Ratio:       {metrics.get('calmar_ratio', 0):>11.3f}")
        print(f"  Max Drawdown:       {metrics.get('max_drawdown_pct', 0):>11.2f}%")
        print(f"  Max DD Period:      {metrics.get('max_drawdown_period', 'N/A')}")
        print()
        print(f"  {'─' * 40}")
        print(f"  🎯 TRADE ANALYSIS")
        print(f"  {'─' * 40}")
        print(f"  Total Trades:       {trade_analysis.get('total_trades', 0):>8}")
        print(f"  Closed Trades:      {trade_analysis.get('closed_trades', 0):>8}")
        print(f"  Win Rate:           {trade_analysis.get('win_rate_pct', 0):>7.1f}%")
        print(f"  Profit Factor:      {str(trade_analysis.get('profit_factor', 0)):>7s}")
        print(f"  Avg Win:            ${trade_analysis.get('avg_win', 0):>10,.2f}")
        print(f"  Avg Loss:           ${trade_analysis.get('avg_loss', 0):>10,.2f}")
        print(f"  Largest Win:        ${trade_analysis.get('largest_win', 0):>10,.2f}")
        print(f"  Largest Loss:       ${trade_analysis.get('largest_loss', 0):>10,.2f}")
        print(f"  Expectancy/Trade:   ${trade_analysis.get('expectancy_per_trade', 0):>10,.2f}")
        print(f"  Total P&L:          ${trade_analysis.get('total_pnl', 0):>10,.2f}")

        # Streaks
        print(f"  Max Win Streak:     {metrics.get('max_win_streak', 0):>8}")
        print(f"  Max Loss Streak:    {metrics.get('max_loss_streak', 0):>8}")

        # P&L by symbol (top 5)
        pnl_by_sym = trade_analysis.get("pnl_by_symbol", {})
        if pnl_by_sym:
            print()
            print(f"  {'─' * 40}")
            print(f"  📋 P&L BY SYMBOL (Top 10)")
            print(f"  {'─' * 40}")
            for i, (sym, pnl) in enumerate(pnl_by_sym.items()):
                if i >= 10:
                    break
                marker = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
                print(f"  {marker} {sym:8s}  ${pnl:>10,.2f}")

        print()
        print(f"═" * 60)
        print(f"  📁 Full report: logs/backtest_report.json")
        print(f"═" * 60)
