"""
Backtest Client — Drop-in replacement for AlpacaClient during backtesting.

Serves date-windowed historical data (no look-ahead bias) and simulates
portfolio state including cash, positions, order fills, and SL/TP tracking.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional
from uuid import uuid4

import pandas as pd


# ─────────────────────────────────────────────
# Supporting Data Structures
# ─────────────────────────────────────────────

@dataclass
class PositionState:
    """Internal simulated position state."""
    symbol: str
    qty: float
    avg_entry_price: float
    side: str  # "long" or "short"
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


@dataclass
class PendingOrder:
    """Order waiting to be filled at next day's open."""
    symbol: str
    qty: float
    side: str  # "buy" or "sell"
    order_type: str  # "market" or "bracket"
    order_id: str = ""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


# ─────────────────────────────────────────────
# BacktestClient
# ─────────────────────────────────────────────

class BacktestClient:
    """
    Simulated AlpacaClient for backtesting.

    Implements the same interface as AlpacaClient so it can be injected
    into TradingOrchestrator via dependency injection.
    """

    def __init__(
        self,
        all_bars: dict[str, pd.DataFrame],
        initial_capital: float = 100_000,
        fill_mode: str = "next_open",
        commission_pct: float = 0.0,
    ):
        """
        Args:
            all_bars: {symbol: DataFrame} with full historical OHLCV data
            initial_capital: Starting cash amount
            fill_mode: "next_open" (realistic) or "current_close" (simpler)
            commission_pct: Commission as fraction (0.001 = 0.1%)
        """
        self.is_paper = True  # Satisfy attribute check in orchestrator

        self._all_bars = all_bars
        self._current_date: Optional[date] = None
        self._fill_mode = fill_mode
        self._commission_pct = commission_pct

        # Portfolio state
        self._initial_capital = initial_capital
        self._cash = initial_capital
        self._positions: dict[str, PositionState] = {}
        self._pending_orders: list[PendingOrder] = []
        self._last_equity = initial_capital

        # Records for reporting
        self._trades: list[dict] = []
        self._equity_curve: list[dict] = []

    # ═══════════════════════════════════════════
    # Date Control (called by BacktestRunner)
    # ═══════════════════════════════════════════

    def set_current_date(self, d: date):
        """
        Advance simulation to date d.

        Order of operations:
        1. Fill any pending orders from the previous day (at today's open)
        2. Set current date
        3. Check SL/TP triggers at today's prices
        4. Record equity snapshot
        """
        # Fill pending orders at today's open price
        self._fill_pending_orders(d)

        self._current_date = d

        # Mark-to-market: check SL/TP triggers
        self._check_sl_tp()

        # Record daily snapshot
        self._record_equity_snapshot()

    # ═══════════════════════════════════════════
    # Market Data (date-windowed, no look-ahead)
    # ═══════════════════════════════════════════

    def get_stock_bars(self, symbol: str, timeframe: str = "1Day", lookback_days: int = 90):
        """Return stock bars up to and including current_date."""
        return self._get_bars_windowed(symbol, lookback_days)

    def get_crypto_bars(self, symbol: str, timeframe: str = "1Day", lookback_days: int = 90):
        """Return None — v1 backtest does not support crypto."""
        return None

    def _get_bars_windowed(self, symbol: str, lookback_days: int) -> Optional[pd.DataFrame]:
        """
        Core date-windowing logic.

        Returns the last `lookback_days` bars where date <= current_date.
        This prevents any look-ahead bias.
        """
        full = self._all_bars.get(symbol)
        if full is None:
            return None

        if self._current_date is None:
            return None

        # Filter: only rows where date <= current_date
        # Handle both timezone-aware and naive indices
        if full.index.tz is not None:
            mask = full.index.tz_localize(None).date <= self._current_date
        else:
            mask = full.index.date <= self._current_date

        windowed = full[mask]

        if windowed.empty:
            return None

        # Return last N rows
        return windowed.tail(lookback_days)

    # ═══════════════════════════════════════════
    # News (stub for v1)
    # ═══════════════════════════════════════════

    def get_news(self, symbol: str, days: int = 3, limit: int = 50) -> list:
        """Return empty list — sentiment analysis is skipped in v1 backtest."""
        return []

    # ═══════════════════════════════════════════
    # Market Hours
    # ═══════════════════════════════════════════

    def is_market_open(self) -> dict:
        """Always return open during backtest."""
        return {"is_open": True, "next_open": None, "next_close": None}

    # ═══════════════════════════════════════════
    # Account
    # ═══════════════════════════════════════════

    def get_account(self) -> dict:
        """Return simulated account state in Alpaca format."""
        equity = self._calculate_equity()
        return {
            "equity": equity,
            "cash": self._cash,
            "portfolio_value": equity,
            "last_equity": self._last_equity,
            "buying_power": self._cash,
            "daytrade_count": 0,
        }

    # ═══════════════════════════════════════════
    # Positions
    # ═══════════════════════════════════════════

    def get_positions(self) -> list[dict]:
        """Return current positions in Alpaca format."""
        result = []
        for symbol, pos in self._positions.items():
            current_price = self._get_current_price(symbol)
            if current_price == 0:
                continue

            market_value = abs(pos.qty * current_price)

            if pos.side == "long":
                unrealized_pl = (current_price - pos.avg_entry_price) * pos.qty
            else:
                unrealized_pl = (pos.avg_entry_price - current_price) * pos.qty

            cost_basis = pos.avg_entry_price * pos.qty
            unrealized_plpc = unrealized_pl / cost_basis if cost_basis != 0 else 0.0

            result.append({
                "symbol": symbol,
                "qty": pos.qty,
                "avg_entry_price": pos.avg_entry_price,
                "current_price": current_price,
                "market_value": market_value,
                "unrealized_pl": unrealized_pl,
                "unrealized_plpc": unrealized_plpc,
                "side": pos.side,
            })
        return result

    # ═══════════════════════════════════════════
    # Order Placement
    # ═══════════════════════════════════════════

    def place_market_order(self, symbol: str, qty: float, side: str = "buy") -> dict:
        """Place a simulated market order."""
        order_id = str(uuid4())[:8]

        if self._fill_mode == "current_close":
            fill_price = self._get_current_price(symbol)
            if fill_price > 0:
                self._execute_fill(symbol, qty, side, fill_price, order_id)
        else:
            # Queue for next-open fill
            self._pending_orders.append(PendingOrder(
                symbol=symbol, qty=qty, side=side,
                order_type="market", order_id=order_id,
            ))

        return {"id": order_id, "status": "accepted"}

    def place_bracket_order(
        self,
        symbol: str,
        qty: float,
        side: str = "buy",
        stop_loss_price: float = 0,
        take_profit_price: float = 0,
    ) -> dict:
        """Place a simulated bracket order with SL/TP."""
        order_id = str(uuid4())[:8]

        if self._fill_mode == "current_close":
            fill_price = self._get_current_price(symbol)
            if fill_price > 0:
                self._execute_fill(symbol, qty, side, fill_price, order_id)
                # Register SL/TP on the position
                if symbol in self._positions:
                    self._positions[symbol].stop_loss = stop_loss_price if stop_loss_price else None
                    self._positions[symbol].take_profit = take_profit_price if take_profit_price else None
        else:
            self._pending_orders.append(PendingOrder(
                symbol=symbol, qty=qty, side=side,
                order_type="bracket", order_id=order_id,
                stop_loss=stop_loss_price if stop_loss_price else None,
                take_profit=take_profit_price if take_profit_price else None,
            ))

        return {"id": order_id, "status": "accepted"}

    # ═══════════════════════════════════════════
    # Internal: Order Fill Logic
    # ═══════════════════════════════════════════

    def _fill_pending_orders(self, fill_date: date):
        """Fill pending orders using the open price on fill_date."""
        if not self._pending_orders:
            return

        for order in self._pending_orders:
            fill_price = self._get_price_on_date(order.symbol, fill_date, "open")
            if fill_price is None or fill_price <= 0:
                # No data for this date — skip (order cancelled)
                continue

            self._execute_fill(
                order.symbol, order.qty, order.side,
                fill_price, order.order_id,
            )

            # Register SL/TP for bracket orders
            if order.order_type == "bracket" and order.symbol in self._positions:
                if order.stop_loss:
                    self._positions[order.symbol].stop_loss = order.stop_loss
                if order.take_profit:
                    self._positions[order.symbol].take_profit = order.take_profit

        self._pending_orders.clear()

    def _execute_fill(self, symbol: str, qty: float, side: str, fill_price: float, order_id: str):
        """
        Execute an order fill, updating cash and positions.

        Handles:
        - Opening new long/short positions
        - Closing existing positions (partial or full)
        - Commission deduction
        """
        # Cap qty to prevent unrealistic position sizes in backtesting
        MAX_SHARES_PER_ORDER = 10_000
        MAX_ORDER_VALUE = 100_000  # $100k max per order
        qty = min(qty, MAX_SHARES_PER_ORDER)
        qty = min(qty, int(MAX_ORDER_VALUE / fill_price)) if fill_price > 0 else qty
        if qty <= 0:
            return

        cost = qty * fill_price
        commission = cost * self._commission_pct

        if side == "buy":
            if symbol in self._positions and self._positions[symbol].side == "short":
                # Closing a short position
                pos = self._positions[symbol]
                close_qty = min(qty, pos.qty)
                pnl = (pos.avg_entry_price - fill_price) * close_qty
                # Return the collateral + P&L
                self._cash += (pos.avg_entry_price * close_qty) + pnl - commission
                pos.qty -= close_qty
                if pos.qty <= 0:
                    del self._positions[symbol]
                self._record_trade(symbol, "buy", close_qty, fill_price, order_id, pnl)
            else:
                # Opening/adding to a long position
                self._cash -= (cost + commission)
                if symbol in self._positions:
                    pos = self._positions[symbol]
                    total_cost = pos.avg_entry_price * pos.qty + fill_price * qty
                    pos.qty += qty
                    pos.avg_entry_price = total_cost / pos.qty
                else:
                    self._positions[symbol] = PositionState(
                        symbol=symbol, qty=qty, avg_entry_price=fill_price,
                        side="long",
                    )
                self._record_trade(symbol, "buy", qty, fill_price, order_id, None)

        elif side == "sell":
            if symbol in self._positions and self._positions[symbol].side == "long":
                # Closing a long position
                pos = self._positions[symbol]
                close_qty = min(qty, pos.qty)
                pnl = (fill_price - pos.avg_entry_price) * close_qty
                self._cash += (fill_price * close_qty) - commission
                pos.qty -= close_qty
                if pos.qty <= 0:
                    del self._positions[symbol]
                self._record_trade(symbol, "sell", close_qty, fill_price, order_id, pnl)
            else:
                # Opening/adding to a short position
                # Short sale: receive cash from selling borrowed shares
                self._cash += (cost - commission)
                if symbol in self._positions:
                    pos = self._positions[symbol]
                    total_cost = pos.avg_entry_price * pos.qty + fill_price * qty
                    pos.qty += qty
                    pos.avg_entry_price = total_cost / pos.qty
                else:
                    self._positions[symbol] = PositionState(
                        symbol=symbol, qty=qty, avg_entry_price=fill_price,
                        side="short",
                    )
                self._record_trade(symbol, "sell", qty, fill_price, order_id, None)

    # ═══════════════════════════════════════════
    # Internal: SL/TP Checking
    # ═══════════════════════════════════════════

    def _check_sl_tp(self):
        """Check stop-loss and take-profit triggers for all positions."""
        to_close = []

        for symbol, pos in self._positions.items():
            current_price = self._get_current_price(symbol)
            if current_price <= 0:
                continue

            if pos.side == "long":
                if pos.stop_loss and current_price <= pos.stop_loss:
                    to_close.append((symbol, "sell", pos.qty, pos.stop_loss, "stop_loss"))
                elif pos.take_profit and current_price >= pos.take_profit:
                    to_close.append((symbol, "sell", pos.qty, pos.take_profit, "take_profit"))
            elif pos.side == "short":
                if pos.stop_loss and current_price >= pos.stop_loss:
                    to_close.append((symbol, "buy", pos.qty, pos.stop_loss, "stop_loss"))
                elif pos.take_profit and current_price <= pos.take_profit:
                    to_close.append((symbol, "buy", pos.qty, pos.take_profit, "take_profit"))

        for symbol, side, qty, price, reason in to_close:
            order_id = f"sl_tp_{reason}_{symbol}"
            self._execute_fill(symbol, qty, side, price, order_id)

    # ═══════════════════════════════════════════
    # Internal: Price Lookups
    # ═══════════════════════════════════════════

    def _get_current_price(self, symbol: str) -> float:
        """Get the close price on the current simulated date."""
        if self._current_date is None:
            return 0.0
        return self._get_price_on_date(symbol, self._current_date, "close") or 0.0

    def _get_price_on_date(self, symbol: str, d: date, price_col: str = "close") -> Optional[float]:
        """Get a specific price (open/close/high/low) for a symbol on a date."""
        bars = self._all_bars.get(symbol)
        if bars is None:
            return None

        # Handle timezone-aware index
        if bars.index.tz is not None:
            idx_dates = bars.index.tz_localize(None).date
        else:
            idx_dates = bars.index.date

        mask = idx_dates == d
        day_bars = bars[mask]

        if not day_bars.empty:
            return float(day_bars[price_col].iloc[-1])

        # Fallback: last available price before this date
        if price_col == "close":
            mask_before = idx_dates <= d
            filtered = bars[mask_before]
            if not filtered.empty:
                return float(filtered["close"].iloc[-1])

        return None

    # ═══════════════════════════════════════════
    # Internal: Portfolio Calculations
    # ═══════════════════════════════════════════

    def _calculate_equity(self) -> float:
        """Total equity = cash + sum of position market values."""
        positions_value = 0.0
        for symbol, pos in self._positions.items():
            price = self._get_current_price(symbol)
            if pos.side == "long":
                positions_value += pos.qty * price
            else:
                # Short position value: collateral locked - current value
                # (already counted cash when opened; equity = cash + unrealized P&L)
                positions_value += pos.qty * (pos.avg_entry_price - price)
        return self._cash + positions_value

    def _record_equity_snapshot(self):
        """Record daily equity for the equity curve."""
        equity = self._calculate_equity()
        self._equity_curve.append({
            "date": str(self._current_date),
            "equity": round(equity, 2),
            "cash": round(self._cash, 2),
            "positions_value": round(equity - self._cash, 2),
            "position_count": len(self._positions),
        })

    def _record_trade(self, symbol: str, side: str, qty: float,
                      fill_price: float, order_id: str, realized_pnl: Optional[float]):
        """Record a trade fill for reporting."""
        self._trades.append({
            "date": str(self._current_date),
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "fill_price": round(fill_price, 4),
            "order_id": order_id,
            "realized_pnl": round(realized_pnl, 2) if realized_pnl is not None else None,
        })
