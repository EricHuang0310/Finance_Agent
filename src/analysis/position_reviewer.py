"""
Position Exit Review Module
Evaluates existing positions to determine if they should be closed
based on momentum/trend signals AND professional hard stop rules.

Hard stops (breakeven, profit lock, give-back) execute unconditionally.
Soft scoring (trend, momentum, ATR, market, time, events) accumulates
to a threshold. Hard stops are checked FIRST and override soft scoring.
"""

from dataclasses import dataclass, asdict, field
from typing import Optional, Callable

import pandas as pd

from src.analysis.technical import TechnicalAnalyzer, TechnicalSignal


@dataclass
class ExitSignal:
    """Result of exit evaluation for a single position."""
    symbol: str
    side: str               # "long" or "short" (from position)
    exit_action: str         # "close" or "hold"
    exit_reason: str
    exit_score: float        # 0.0 (strong hold) to 1.0 (urgent exit)
    current_price: float
    avg_entry_price: float
    qty: float
    unrealized_pl: float
    unrealized_plpc: float   # as decimal, e.g. 0.05 = 5%
    tech_score: float
    trend: str
    rsi: float
    atr: float
    exit_urgency: str = "normal"  # "high" if exit_score >= 0.7
    holding_days: int = 0
    exit_score_breakdown: dict = field(default_factory=dict)
    hard_stop_type: Optional[str] = None  # "breakeven", "profit_lock", "giveback", or None
    partial_close_pct: Optional[float] = None  # e.g. 0.50 means close 50% of position

    def to_dict(self) -> dict:
        return asdict(self)


class PositionReviewer:
    """Evaluates existing positions for exit signals using momentum/trend criteria
    plus professional hard stop rules."""

    def __init__(self, config: dict):
        exit_cfg = config.get("position_exit", {})
        self.exit_threshold = exit_cfg.get("exit_threshold", 0.5)
        self.atr_multiplier = exit_cfg.get("atr_multiplier", 2.0)
        self.trailing_lookback_bars = exit_cfg.get("trailing_lookback_bars", 10)
        self.max_positions = config.get("risk", {}).get("max_positions", 8)

        # Hard stop rules (professional desk practices)
        self.breakeven_atr_trigger = exit_cfg.get("breakeven_atr_trigger", 1.0)
        self.profit_lock_atr_trigger = exit_cfg.get("profit_lock_atr_trigger", 2.0)
        self.profit_lock_trail_atr = exit_cfg.get("profit_lock_trail_atr", 1.5)
        self.giveback_threshold = exit_cfg.get("giveback_threshold", 0.50)
        self.giveback_min_peak_pct = exit_cfg.get("giveback_min_peak_pct", 0.03)
        self.time_stop_days = exit_cfg.get("time_stop_days", 5)
        self.time_stop_flat_atr = exit_cfg.get("time_stop_flat_atr", 0.5)

        # ATR Gradient Trailing Stop tiers (sorted ascending by trigger)
        raw_gradient = exit_cfg.get("atr_gradient", [
            {"trigger": 2.0, "lock": 0.75},
            {"trigger": 3.0, "lock": 1.5},
            {"trigger": 5.0, "lock": 3.0},
            {"trigger": 10.0, "lock": 7.0},
            {"trigger": 15.0, "lock": 12.0},
        ])
        self.atr_gradient = sorted(
            [(float(t["trigger"]), float(t["lock"])) for t in raw_gradient],
            key=lambda x: x[0],
        )

        # Partial close settings
        self.partial_close_enabled = exit_cfg.get("partial_close_enabled", True)
        self.partial_close_high_vol_atr = exit_cfg.get("partial_close_high_vol_atr", 2.0)
        self.partial_close_high_vol_pct = exit_cfg.get("partial_close_high_vol_pct", 0.50)
        self.partial_close_standard_atr = exit_cfg.get("partial_close_standard_atr", 4.0)
        self.partial_close_standard_pct = exit_cfg.get("partial_close_standard_pct", 0.25)
        self.partial_close_bank_atr = exit_cfg.get("partial_close_bank_atr", 2.0)
        self.partial_close_bank_pct = exit_cfg.get("partial_close_bank_pct", 0.50)

        self.tech_analyzer = TechnicalAnalyzer()

    # ──────────────────────────────────────────────────────────
    # Hard Stop Rules — trigger = immediate exit, no averaging
    # ──────────────────────────────────────────────────────────

    def _check_hard_stops(
        self,
        position: dict,
        tech_signal: TechnicalSignal,
        bars: Optional[pd.DataFrame],
    ) -> Optional[tuple[float, str, dict, str]]:
        """Check rule-based hard stops.

        Returns (score, reason, breakdown, hard_stop_type) or None.
        Hard stops override the soft scoring system entirely.
        """
        entry_price = position["avg_entry_price"]
        current_price = position["current_price"]
        atr = tech_signal.atr
        is_long = position["side"] == "long"

        if atr <= 0 or entry_price <= 0:
            return None

        # PnL in ATR units
        if is_long:
            pnl_atr = (current_price - entry_price) / atr
        else:
            pnl_atr = (entry_price - current_price) / atr

        # Compute high water mark from bars
        high_water_price = current_price
        low_water_price = current_price
        if bars is not None and len(bars) > 0:
            if is_long:
                high_water_price = float(bars["high"].astype(float).max())
            else:
                low_water_price = float(bars["low"].astype(float).min())

        # Peak and current PnL as percentage
        if is_long:
            peak_pnl_pct = (high_water_price - entry_price) / entry_price
            current_pnl_pct = (current_price - entry_price) / entry_price
            peak_pnl_atr = (high_water_price - entry_price) / atr
        else:
            peak_pnl_pct = (entry_price - low_water_price) / entry_price
            current_pnl_pct = (entry_price - current_price) / entry_price
            peak_pnl_atr = (entry_price - low_water_price) / atr

        breakdown = {}

        # ── 1. Breakeven Stop ──
        # Position WAS in profit by >= breakeven_atr_trigger ATRs,
        # but has retraced back to entry or worse.
        if peak_pnl_atr >= self.breakeven_atr_trigger and pnl_atr <= 0:
            reason = (
                f"HARD STOP breakeven: was up {peak_pnl_pct*100:.1f}% "
                f"({peak_pnl_atr:.1f} ATR), retraced to entry"
            )
            breakdown["hard_stop"] = "breakeven"
            breakdown["peak_pnl_pct"] = round(peak_pnl_pct * 100, 2)
            breakdown["peak_pnl_atr"] = round(peak_pnl_atr, 2)
            return (1.0, reason, breakdown, "breakeven")

        # ── 2. ATR Gradient Trailing Profit Lock ──
        # Use the highest matching tier from the gradient table.
        # Each tier: if peak_pnl_atr >= trigger, lock profit at entry + lock * ATR.
        # If current PnL has retraced below the lock level, trigger hard stop.
        lock_atr = None
        matched_trigger = None
        for trigger, lock in self.atr_gradient:
            if peak_pnl_atr >= trigger:
                lock_atr = lock
                matched_trigger = trigger
        if lock_atr is not None:
            if is_long:
                lock_price = entry_price + lock_atr * atr
                if current_price < lock_price:
                    reason = (
                        f"HARD STOP profit lock (gradient): price ${current_price:.2f} < "
                        f"lock ${lock_price:.2f} "
                        f"(entry ${entry_price:.2f} + {lock_atr}×ATR, "
                        f"tier +{matched_trigger} ATR)"
                    )
                    breakdown["hard_stop"] = "profit_lock"
                    breakdown["high_water"] = round(high_water_price, 2)
                    breakdown["lock_price"] = round(lock_price, 2)
                    breakdown["gradient_tier"] = matched_trigger
                    breakdown["lock_atr"] = lock_atr
                    return (1.0, reason, breakdown, "profit_lock")
            else:
                lock_price = entry_price - lock_atr * atr
                if current_price > lock_price:
                    reason = (
                        f"HARD STOP profit lock (gradient): price ${current_price:.2f} > "
                        f"lock ${lock_price:.2f} "
                        f"(entry ${entry_price:.2f} - {lock_atr}×ATR, "
                        f"tier +{matched_trigger} ATR)"
                    )
                    breakdown["hard_stop"] = "profit_lock"
                    breakdown["low_water"] = round(low_water_price, 2)
                    breakdown["lock_price"] = round(lock_price, 2)
                    breakdown["gradient_tier"] = matched_trigger
                    breakdown["lock_atr"] = lock_atr
                    return (1.0, reason, breakdown, "profit_lock")

        # ── 3. Profit Give-back ──
        # Peak PnL was >= giveback_min_peak_pct, but we've given back >= giveback_threshold.
        if peak_pnl_pct >= self.giveback_min_peak_pct and peak_pnl_pct > 0:
            if current_pnl_pct <= 0:
                giveback_ratio = 1.0
            else:
                giveback_ratio = 1.0 - (current_pnl_pct / peak_pnl_pct)

            if giveback_ratio >= self.giveback_threshold:
                reason = (
                    f"HARD STOP give-back: peak {peak_pnl_pct*100:.1f}% → "
                    f"now {current_pnl_pct*100:.1f}% "
                    f"(gave back {giveback_ratio*100:.0f}%)"
                )
                breakdown["hard_stop"] = "giveback"
                breakdown["peak_pnl_pct"] = round(peak_pnl_pct * 100, 2)
                breakdown["current_pnl_pct"] = round(current_pnl_pct * 100, 2)
                breakdown["giveback_ratio"] = round(giveback_ratio * 100, 1)
                return (0.85, reason, breakdown, "giveback")

        return None

    # ──────────────────────────────────────────────────────────
    # Partial Close — suggest closing a fraction of the position
    # ──────────────────────────────────────────────────────────

    def _check_partial_close(
        self,
        position: dict,
        tech_signal: TechnicalSignal,
        bars: Optional[pd.DataFrame],
    ) -> Optional[tuple[float, str]]:
        """Check if a partial close is warranted.

        Returns (partial_close_pct, reason) or None.
        """
        if not self.partial_close_enabled:
            return None

        entry_price = position["avg_entry_price"]
        current_price = position["current_price"]
        atr = tech_signal.atr
        is_long = position["side"] == "long"

        if atr <= 0 or entry_price <= 0:
            return None

        if is_long:
            pnl_atr = (current_price - entry_price) / atr
        else:
            pnl_atr = (entry_price - current_price) / atr

        if pnl_atr <= 0:
            return None

        atr_pct = atr / entry_price if entry_price > 0 else 0

        # Bank sector check
        sector = position.get("sector", "unknown")
        is_bank = any(
            kw in sector.lower()
            for kw in ("financial", "bank")
        ) if sector else False

        # Priority: bank rule, then high-vol rule, then standard rule
        if is_bank and pnl_atr >= self.partial_close_bank_atr:
            return (
                self.partial_close_bank_pct,
                f"Partial close (bank sector): +{pnl_atr:.1f} ATR >= {self.partial_close_bank_atr} ATR threshold",
            )

        if atr_pct > 0.05 and pnl_atr >= self.partial_close_high_vol_atr:
            return (
                self.partial_close_high_vol_pct,
                f"Partial close (high vol ATR/P={atr_pct*100:.1f}%): +{pnl_atr:.1f} ATR >= {self.partial_close_high_vol_atr} ATR threshold",
            )

        if pnl_atr >= self.partial_close_standard_atr:
            return (
                self.partial_close_standard_pct,
                f"Partial close (standard): +{pnl_atr:.1f} ATR >= {self.partial_close_standard_atr} ATR threshold",
            )

        return None

    # ──────────────────────────────────────────────────────────
    # Main review — hard stops first, then soft scoring
    # ──────────────────────────────────────────────────────────

    def review_position(
        self,
        position: dict,
        tech_signal: TechnicalSignal,
        market_score: float,
        bars: pd.DataFrame,
        sentiment_data: dict = None,
    ) -> ExitSignal:
        """Evaluate a single position for exit.

        1. Check hard stops (breakeven, profit lock, give-back) — immediate exit.
        2. If no hard stop, run soft scoring:
           Weights: trend 0.25, momentum 0.20, ATR trailing 0.20,
                    market 0.10, time_stop 0.15, event_risk 0.10
        """
        is_long = position["side"] == "long"

        # Compute holding days
        holding_days = self._compute_holding_days(position)

        # ── Hard Stops (checked first, override everything) ──
        hard_stop = self._check_hard_stops(position, tech_signal, bars)
        if hard_stop is not None:
            score, reason, breakdown, stop_type = hard_stop
            return ExitSignal(
                symbol=position["symbol"],
                side=position["side"],
                exit_action="close",
                exit_reason=reason,
                exit_score=score,
                current_price=position["current_price"],
                avg_entry_price=position["avg_entry_price"],
                qty=position["qty"],
                unrealized_pl=position["unrealized_pl"],
                unrealized_plpc=position["unrealized_plpc"],
                tech_score=tech_signal.score,
                trend=tech_signal.trend,
                rsi=tech_signal.rsi,
                atr=tech_signal.atr,
                exit_urgency="high",
                holding_days=holding_days,
                exit_score_breakdown=breakdown,
                hard_stop_type=stop_type,
            )

        # ── Partial Close (after hard stops, before soft scoring) ──
        partial = self._check_partial_close(position, tech_signal, bars)
        if partial is not None:
            partial_pct, partial_reason = partial
            return ExitSignal(
                symbol=position["symbol"],
                side=position["side"],
                exit_action="partial_close",
                exit_reason=partial_reason,
                exit_score=0.6,
                current_price=position["current_price"],
                avg_entry_price=position["avg_entry_price"],
                qty=position["qty"],
                unrealized_pl=position["unrealized_pl"],
                unrealized_plpc=position["unrealized_plpc"],
                tech_score=tech_signal.score,
                trend=tech_signal.trend,
                rsi=tech_signal.rsi,
                atr=tech_signal.atr,
                exit_urgency="normal",
                holding_days=holding_days,
                exit_score_breakdown={"partial_close": partial_reason},
                hard_stop_type=None,
                partial_close_pct=partial_pct,
            )

        # ── Soft Scoring (6 factors) ──
        exit_score = 0.0
        reasons = []
        breakdown = {}

        # PnL in ATR units (for enhanced time stop)
        atr = tech_signal.atr
        entry_price = position["avg_entry_price"]
        current_price = position["current_price"]
        if atr > 0 and entry_price > 0:
            if is_long:
                pnl_atr = (current_price - entry_price) / atr
            else:
                pnl_atr = (entry_price - current_price) / atr
        else:
            pnl_atr = 0.0

        # ── 1. Trend Reversal (weight: 0.25) ──
        trend_contribution = 0.0
        if is_long and tech_signal.score < 0:
            trend_contribution = 0.25 * min(1.0, abs(tech_signal.score))
            reasons.append(f"trend reversed (score={tech_signal.score:.2f})")
        elif not is_long and tech_signal.score > 0:
            trend_contribution = 0.25 * min(1.0, abs(tech_signal.score))
            reasons.append(f"trend reversed (score={tech_signal.score:.2f})")
        exit_score += trend_contribution
        breakdown["trend_reversal"] = round(trend_contribution, 4)

        # ── 2. Momentum Weakening (weight: 0.20) ──
        momentum_contribution = 0.0
        if is_long:
            if tech_signal.rsi < 50:
                rsi_component = min(1.0, (50 - tech_signal.rsi) / 20)
                momentum_contribution += 0.10 * rsi_component
                reasons.append(f"RSI weakened ({tech_signal.rsi:.1f})")
            if tech_signal.trend != "bullish":
                momentum_contribution += 0.10
                reasons.append(f"EMA alignment broken (trend={tech_signal.trend})")
        else:
            if tech_signal.rsi > 50:
                rsi_component = min(1.0, (tech_signal.rsi - 50) / 20)
                momentum_contribution += 0.10 * rsi_component
                reasons.append(f"RSI weakened ({tech_signal.rsi:.1f})")
            if tech_signal.trend != "bearish":
                momentum_contribution += 0.10
                reasons.append(f"EMA alignment broken (trend={tech_signal.trend})")
        exit_score += momentum_contribution
        breakdown["momentum_weakening"] = round(momentum_contribution, 4)

        # ── 3. Trailing Stop via ATR (weight: 0.20) ──
        trailing_contribution = 0.0
        if bars is not None and len(bars) >= self.trailing_lookback_bars:
            closes = bars["close"].astype(float)
            recent = closes.tail(self.trailing_lookback_bars)

            if is_long:
                recent_high = float(recent.max())
                trailing_stop = recent_high - self.atr_multiplier * tech_signal.atr
                if current_price < trailing_stop:
                    breach_pct = (trailing_stop - current_price) / max(trailing_stop, 0.01)
                    trailing_contribution = 0.20 * min(1.0, breach_pct * 10 + 0.5)
                    reasons.append(f"trailing stop breached (${trailing_stop:.2f})")
            else:
                recent_low = float(recent.min())
                trailing_stop = recent_low + self.atr_multiplier * tech_signal.atr
                if current_price > trailing_stop:
                    breach_pct = (current_price - trailing_stop) / max(trailing_stop, 0.01)
                    trailing_contribution = 0.20 * min(1.0, breach_pct * 10 + 0.5)
                    reasons.append(f"trailing stop breached (${trailing_stop:.2f})")
        exit_score += trailing_contribution
        breakdown["atr_trailing_stop"] = round(trailing_contribution, 4)

        # ── 4. Market Context Deterioration (weight: 0.10) ──
        market_contribution = 0.0
        if is_long and market_score < -0.2:
            market_contribution = 0.10 * min(1.0, abs(market_score))
            reasons.append(f"market context bearish ({market_score:.2f})")
        elif not is_long and market_score > 0.2:
            market_contribution = 0.10 * min(1.0, abs(market_score))
            reasons.append(f"market context bullish ({market_score:.2f})")
        exit_score += market_contribution
        breakdown["market_context"] = round(market_contribution, 4)

        # ── 5. Enhanced Time Stop (weight: 0.15) ──
        time_contribution = 0.0
        if holding_days >= self.time_stop_days and pnl_atr < self.time_stop_flat_atr:
            # Position held N+ days but hasn't moved favorably by even 0.5 ATR
            time_contribution = 0.15
            reasons.append(
                f"time stop: {holding_days}d held, only {pnl_atr:.1f} ATR gain "
                f"(need {self.time_stop_flat_atr})"
            )
        elif holding_days > 20:
            time_contribution = 0.10
            reasons.append(f"time decay ({holding_days}d held)")
        elif holding_days > 10:
            time_contribution = 0.06
            reasons.append(f"time decay ({holding_days}d held)")
        elif holding_days > 5:
            time_contribution = 0.03
            reasons.append(f"time decay ({holding_days}d held)")
        exit_score += time_contribution
        breakdown["time_stop"] = round(time_contribution, 4)

        # ── 6. Event Risk (weight: 0.10) ──
        event_contribution = 0.0
        if sentiment_data:
            sym_sent = sentiment_data.get("symbols", {}).get(position["symbol"], {})
            if sym_sent.get("upcoming_earnings"):
                event_contribution = 0.07
                reasons.append("upcoming earnings")
            if sym_sent.get("binary_event"):
                event_contribution = 0.10
                reasons.append("binary event risk")
        exit_score += event_contribution
        breakdown["event_risk"] = round(event_contribution, 4)

        exit_score = min(1.0, exit_score)
        exit_action = "close" if exit_score >= self.exit_threshold else "hold"
        exit_reason = "; ".join(reasons) if reasons else "holding - trend intact"
        exit_urgency = "high" if exit_score >= 0.7 else "normal"

        return ExitSignal(
            symbol=position["symbol"],
            side=position["side"],
            exit_action=exit_action,
            exit_reason=exit_reason,
            exit_score=round(exit_score, 4),
            current_price=position["current_price"],
            avg_entry_price=position["avg_entry_price"],
            qty=position["qty"],
            unrealized_pl=position["unrealized_pl"],
            unrealized_plpc=position["unrealized_plpc"],
            tech_score=tech_signal.score,
            trend=tech_signal.trend,
            rsi=tech_signal.rsi,
            atr=tech_signal.atr,
            exit_urgency=exit_urgency,
            holding_days=holding_days,
            exit_score_breakdown=breakdown,
            hard_stop_type=None,
        )

    # ──────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────

    @staticmethod
    def _compute_holding_days(position: dict) -> int:
        """Compute holding days from position created_at if available."""
        holding_days = 0
        if position.get("created_at"):
            try:
                from datetime import datetime, timezone
                created = position["created_at"]
                if isinstance(created, str):
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                now = datetime.now(timezone.utc)
                holding_days = (now - created).days
            except Exception:
                pass
        return holding_days

    def review_all(
        self,
        positions: list[dict],
        tech_signals: dict,
        market_data: dict,
        bars_getter: Callable,
        sentiment_data: dict = None,
    ) -> list[ExitSignal]:
        """Review all positions for exit signals."""
        results = []

        for pos in positions:
            symbol = pos["symbol"]

            # Get or compute technical signal
            tech_signal = self._get_tech_signal(symbol, symbol, "stock", tech_signals, bars_getter)
            if tech_signal is None:
                print(f"  ⚠️  {symbol}: cannot analyze, skipping exit review")
                continue

            # Get market score
            market_score = self._get_market_score(symbol, "stock", market_data)

            # Get bars for trailing stop
            bars = bars_getter(symbol, "stock")

            signal = self.review_position(pos, tech_signal, market_score, bars, sentiment_data)
            results.append(signal)

        return results

    def _get_tech_signal(
        self,
        position_symbol: str,
        bars_symbol: str,
        asset_type: str,
        tech_signals: dict,
        bars_getter: Callable,
    ) -> Optional[TechnicalSignal]:
        """Get tech signal from cache or compute on-demand."""
        category = "stocks"
        cached = tech_signals.get(category, {})

        # Try exact match first (position symbol or bars symbol)
        for try_sym in [position_symbol, bars_symbol]:
            if try_sym in cached:
                data = cached[try_sym]
                return TechnicalSignal(**data) if isinstance(data, dict) else data

        # Not in cache — compute on demand
        bars = bars_getter(bars_symbol, asset_type)
        if bars is not None and len(bars) >= 50:
            return self.tech_analyzer.analyze(bars, position_symbol, "1Day")

        return None

    def _get_market_score(self, symbol: str, asset_type: str, market_data: dict) -> float:
        """Get market score for a symbol, defaulting to 0."""
        return market_data.get("stocks", {}).get(symbol, {}).get("market_score", 0.0)
