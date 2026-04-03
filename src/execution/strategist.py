"""Execution Strategist -- intelligent order type selection based on volatility and liquidity (EXEC-01/02).

Produces execution_plan.json with per-trade order type recommendations (market, limit, bracket)
based on ATR percentage and volume impact analysis. The Executor reads this plan to dispatch
the appropriate order type.

Decision matrix:
- High volume impact (>= 5% of avg volume) -> limit order (patient fill)
- High ATR (> 3%) -> bracket with wider stops
- Low ATR + low volume impact -> market order (immediate)
- Default -> bracket with standard stops
"""

import json
from datetime import datetime
from pathlib import Path

from src.state_dir import get_state_dir
from src.utils.state_io import save_state_atomic


def select_order_type(trade: dict, market_data: dict) -> dict:
    """Rule-based order type selection per EXEC-01.

    Args:
        trade: Trade dict with symbol, suggested_qty, entry_price, and
               optional technical signals (atr, atr_pct).
        market_data: Market data dict with avg_volume_20d and price info.

    Returns:
        Dict with order_type, urgency, rationale, and type-specific params
        (limit_offset_bps, stop_multiplier).
    """
    # Extract ATR percentage from trade signals or compute from market data
    atr_pct = trade.get("atr_pct", 0)
    if not atr_pct:
        signals = trade.get("signals_summary", {})
        atr = signals.get("atr", 0)
        entry_price = trade.get("entry_price", 0)
        if atr and entry_price and entry_price > 0:
            atr_pct = atr / entry_price

    # Compute volume impact
    avg_volume = market_data.get("avg_volume_20d", 0)
    qty = trade.get("suggested_qty", 0)
    volume_impact = qty / avg_volume if avg_volume and avg_volume > 0 else 1.0

    # Decision matrix
    if volume_impact >= 0.05:
        return {
            "order_type": "limit",
            "limit_offset_bps": 10,
            "urgency": "patient",
            "rationale": (
                f"High volume impact ({volume_impact:.4f} >= 0.05) -- "
                f"limit order to control slippage"
            ),
        }
    elif atr_pct > 0.03:
        return {
            "order_type": "bracket",
            "stop_multiplier": 2.5,
            "urgency": "normal",
            "rationale": (
                f"High volatility (ATR%={atr_pct:.4f} > 0.03) -- "
                f"bracket with wider stops (2.5x)"
            ),
        }
    elif atr_pct < 0.01 and volume_impact < 0.001:
        return {
            "order_type": "market",
            "urgency": "immediate",
            "rationale": (
                f"Low vol (ATR%={atr_pct:.4f}) + very liquid "
                f"(vol_impact={volume_impact:.6f}) -- market order fine"
            ),
        }
    else:
        return {
            "order_type": "bracket",
            "stop_multiplier": 2.0,
            "urgency": "normal",
            "rationale": (
                f"Default conditions (ATR%={atr_pct:.4f}, "
                f"vol_impact={volume_impact:.6f}) -- bracket with standard stops"
            ),
        }


def task_execution_strategist(assessed: list[dict]) -> list[dict]:
    """Produce execution_plan.json with order type recommendations (EXEC-01/02).

    Loads market_overview.json and technical_signals.json for volume/ATR data,
    runs select_order_type for each approved trade, and saves the plan to
    {STATE_DIR}/execution_plan.json.

    Args:
        assessed: List of trade dicts from risk manager / portfolio strategist.

    Returns:
        The assessed list unchanged (pass-through).
    """
    try:
        state_dir = get_state_dir()
        plans = []

        # Load market data for volume info
        mkt_path = state_dir / "market_overview.json"
        market_data = {}
        if mkt_path.exists():
            with open(mkt_path, "r", encoding="utf-8") as f:
                market_data = json.load(f)

        # Load technical signals for ATR data
        tech_path = state_dir / "technical_signals.json"
        tech_data = {}
        if tech_path.exists():
            with open(tech_path, "r", encoding="utf-8") as f:
                tech_data = json.load(f)

        for trade in assessed:
            if not trade.get("approved"):
                continue

            symbol = trade["symbol"]

            # Merge ATR from technical signals into trade if not present
            tech_signals = tech_data.get("signals", {}).get(symbol, {})
            if not trade.get("atr_pct") and tech_signals.get("atr"):
                entry_price = trade.get("entry_price", 0)
                if entry_price and entry_price > 0:
                    trade["atr_pct"] = tech_signals["atr"] / entry_price

            # Get stock-level market data
            stock_data = market_data.get("stocks", {}).get(symbol, {})

            plan = select_order_type(trade, stock_data)
            plan["symbol"] = symbol
            plan["side"] = trade["side"]
            plan["qty"] = trade.get("suggested_qty")
            plan["entry_price"] = trade.get("entry_price")

            # For limit orders, compute limit price with offset
            if plan["order_type"] == "limit":
                offset_bps = plan.get("limit_offset_bps", 10)
                entry = trade.get("entry_price", 0)
                if entry and entry > 0:
                    if trade["side"] == "buy":
                        plan["limit_price"] = round(
                            entry * (1 - offset_bps / 10000), 2
                        )
                    else:
                        plan["limit_price"] = round(
                            entry * (1 + offset_bps / 10000), 2
                        )

            plans.append(plan)

        result = {
            "timestamp": datetime.now().isoformat(),
            "plans": plans,
            "total_assessed": len(assessed),
            "total_planned": len(plans),
        }
        save_state_atomic(state_dir / "execution_plan.json", result)

        print(
            f"\U0001f4ca [Execution Strategist] "
            f"\u2705 Plan for {len(plans)} trades"
        )
        # Summary of order types
        type_counts = {}
        for p in plans:
            otype = p["order_type"]
            type_counts[otype] = type_counts.get(otype, 0) + 1
        if type_counts:
            summary = ", ".join(f"{k}={v}" for k, v in type_counts.items())
            print(f"  Order types: {summary}")

    except Exception as e:
        print(
            f"  \u26a0\ufe0f  Execution Strategist failed "
            f"(using default orders): {e}"
        )

    return assessed
