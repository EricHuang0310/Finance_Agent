"""
Risk Manager Module
Validates trades against portfolio constraints and sizes positions.
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class RiskAssessment:
    """Result of risk assessment for a trade candidate."""
    symbol: str
    approved: bool
    reason: str
    suggested_qty: int
    risk_reward_ratio: float
    position_size_pct: float

    def to_dict(self) -> dict:
        return asdict(self)


class RiskManager:
    """Enforces risk constraints and sizes positions."""

    def __init__(self, config: dict):
        risk_cfg = config.get("risk", {})
        self.max_position_pct = risk_cfg.get("max_position_pct", 10.0) / 100
        self.max_exposure_pct = risk_cfg.get("max_exposure_pct", 60.0) / 100
        self.max_positions = risk_cfg.get("max_positions", 8)
        self.daily_loss_limit_pct = risk_cfg.get("daily_loss_limit_pct", 2.0) / 100
        self.kill_switch_pct = risk_cfg.get("kill_switch_pct", 3.0) / 100
        self.max_drawdown_pct = risk_cfg.get("max_drawdown_pct", 10.0) / 100
        self.min_risk_reward = risk_cfg.get("min_risk_reward", 1.5)

        self.equity = 0.0
        self.cash = 0.0
        self.positions = []
        self.daily_pnl = 0.0
        self.daily_pnl_pct = 0.0
        self.peak_equity = 0.0
        self.drawdown_from_peak_pct = 0.0
        self.kill_switch_active = False

    def update_portfolio(self, account: dict, positions: list[dict]):
        """Update current portfolio state from Alpaca."""
        self.equity = float(account.get("equity", account.get("portfolio_value", 0)))
        self.cash = float(account.get("cash", 0))
        self.positions = positions

        last_equity = float(account.get("last_equity", self.equity))
        self.daily_pnl = self.equity - last_equity
        self.daily_pnl_pct = (self.daily_pnl / last_equity) if last_equity > 0 else 0

        # Track peak equity for drawdown calculation
        # In a one-shot system, use the higher of last_equity and current equity
        self.peak_equity = max(last_equity, self.equity)
        if self.peak_equity > 0:
            self.drawdown_from_peak_pct = (self.peak_equity - self.equity) / self.peak_equity
        else:
            self.drawdown_from_peak_pct = 0.0

        # Check kill switch
        if self.daily_pnl_pct <= -self.kill_switch_pct:
            self.kill_switch_active = True

        # Check max drawdown
        if self.drawdown_from_peak_pct >= self.max_drawdown_pct:
            self.kill_switch_active = True

    def assess_trade(
        self,
        symbol: str,
        side: str,
        entry_price: float,
        stop_loss_price: Optional[float] = None,
        take_profit_price: Optional[float] = None,
        signal_score: float = 0,
    ) -> RiskAssessment:
        """Assess whether a trade meets risk constraints."""

        # Kill switch check
        if self.kill_switch_active:
            return RiskAssessment(
                symbol=symbol, approved=False, reason="Kill switch active",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
            )

        # Daily loss limit
        if self.daily_pnl_pct <= -self.daily_loss_limit_pct:
            return RiskAssessment(
                symbol=symbol, approved=False, reason="Daily loss limit reached",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
            )

        # Look up existing position in same symbol (used in multiple checks below)
        existing_position = next((p for p in self.positions if p["symbol"] == symbol), None)
        existing_value = abs(float(existing_position.get("market_value", 0))) if existing_position else 0.0
        existing_exposure_pct = (existing_value / self.equity) if self.equity > 0 else 0.0

        # Max positions (only reject if this is a NEW symbol)
        if len(self.positions) >= self.max_positions:
            if existing_position is None:
                return RiskAssessment(
                    symbol=symbol, approved=False,
                    reason=f"Max positions ({self.max_positions}) reached",
                    suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
                )

        # Reject if already at max single-position exposure for this symbol
        if existing_exposure_pct >= self.max_position_pct:
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason=f"Already at max position for {symbol} ({existing_exposure_pct*100:.1f}%)",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
            )

        # Total exposure check
        total_exposure = sum(abs(float(p.get("market_value", 0))) for p in self.positions)
        current_exposure_pct = total_exposure / self.equity if self.equity > 0 else 0

        if current_exposure_pct >= self.max_exposure_pct:
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason=f"Max exposure ({self.max_exposure_pct*100:.0f}%) reached",
                suggested_qty=0, risk_reward_ratio=0, position_size_pct=0,
            )

        # Risk-reward ratio
        risk_reward = 0.0
        if stop_loss_price and take_profit_price and entry_price:
            risk = abs(entry_price - stop_loss_price)
            reward = abs(take_profit_price - entry_price)
            risk_reward = reward / risk if risk > 0 else 0

            if risk_reward < self.min_risk_reward:
                return RiskAssessment(
                    symbol=symbol, approved=False,
                    reason=f"R:R {risk_reward:.2f} < min {self.min_risk_reward}",
                    suggested_qty=0, risk_reward_ratio=risk_reward, position_size_pct=0,
                )

        # Position sizing — account for existing holdings in the same symbol
        max_position_value = self.equity * self.max_position_pct
        remaining_room = max(0, max_position_value - existing_value)
        suggested_qty = int(remaining_room / entry_price) if entry_price > 0 else 0
        position_size_pct = (suggested_qty * entry_price / self.equity * 100) if self.equity > 0 else 0

        if suggested_qty <= 0:
            return RiskAssessment(
                symbol=symbol, approved=False,
                reason=f"Insufficient room (existing {symbol} exposure: {existing_exposure_pct*100:.1f}%)",
                suggested_qty=0, risk_reward_ratio=risk_reward, position_size_pct=0,
            )

        side_label = "shares" if side == "buy" else "shares (short)"
        return RiskAssessment(
            symbol=symbol,
            approved=True,
            reason=f"Approved: {suggested_qty} {side_label}, R:R={risk_reward:.2f}",
            suggested_qty=suggested_qty,
            risk_reward_ratio=round(risk_reward, 2),
            position_size_pct=round(position_size_pct, 2),
        )

    def get_risk_summary(self) -> dict:
        """Get current risk status summary."""
        total_exposure = sum(abs(float(p.get("market_value", 0))) for p in self.positions)
        exposure_pct = (total_exposure / self.equity * 100) if self.equity > 0 else 0

        return {
            "equity": self.equity,
            "cash": self.cash,
            "current_exposure_pct": round(exposure_pct, 2),
            "max_exposure_pct": self.max_exposure_pct * 100,
            "daily_pnl_pct": round(self.daily_pnl_pct * 100, 2),
            "drawdown_from_peak_pct": round(self.drawdown_from_peak_pct * 100, 2),
            "max_drawdown_pct": self.max_drawdown_pct * 100,
            "position_count": len(self.positions),
            "max_positions": self.max_positions,
            "kill_switch_active": self.kill_switch_active,
            "daily_limit_hit": self.daily_pnl_pct <= -self.daily_loss_limit_pct,
        }
