"""
Claude Code Agent Teams Launcher
Provides commands for orchestrating multi-agent trading analysis via Claude Code.

Usage with Claude Code Agent Teams:
    1. export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true
    2. cd alpaca-multi-agent-trading
    3. claude
    4. Paste the launch prompt below

This file also supports standalone execution for testing.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from src.utils.state_io import save_state_atomic
from src.analysis.technical import TechnicalAnalyzer

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.state_dir import get_state_dir
from src.alpaca_client import AlpacaClient
from src.orchestrator import TradingOrchestrator
from src.notifications.telegram import TelegramNotifier
from src.debate.helpers import (
    _fetch_sector_intelligence,
    task_prepare_debate_context,
    task_merge_debate_results,
)
from src.memory.reflection import (
    get_unreflected_trades,
    task_prepare_reflection_context,
    task_save_reflections,
)


# ══════════════════════════════════════════════
# Shared Orchestrator (singleton for pipeline mode)
# In Agent Teams mode (separate processes), each
# process gets its own instance naturally.
# ══════════════════════════════════════════════

_orchestrator_instance = None


def get_orchestrator() -> TradingOrchestrator:
    """Lazy singleton orchestrator to avoid redundant initialization."""
    global _orchestrator_instance
    if _orchestrator_instance is None:
        _orchestrator_instance = TradingOrchestrator()
    return _orchestrator_instance


# ══════════════════════════════════════════════
# Agent Task Functions
# Each function is designed to be called by a
# separate Claude Code teammate/agent
# ══════════════════════════════════════════════

def task_macro_strategist() -> dict:
    """Fetch cross-asset data and produce macro_outlook.json.

    Uses code-fetched real-time data only (MACRO-02). Never LLM memory.
    Called by Macro Strategist teammate or standalone pipeline.
    """
    orch = get_orchestrator()
    state_dir = get_state_dir()
    cfg = orch.config.get("macro", {})

    print("\n" + "=" * 60)
    print("  Macro Strategist - Cross-Asset Analysis")
    print("=" * 60)

    cross_asset = {}
    data_freshness = {}

    # 1. VIX via yfinance
    vix_ticker = cfg.get("vix_ticker", "^VIX")
    try:
        vix_data = yf.Ticker(vix_ticker).history(period="1mo")
        if vix_data is not None and len(vix_data) > 0:
            vix_close = float(vix_data["Close"].iloc[-1])
            sma5 = float(vix_data["Close"].tail(5).mean())
            sma20 = float(vix_data["Close"].tail(20).mean())
            cross_asset["vix"] = {
                "value": round(vix_close, 2),
                "trend": "declining" if sma5 < sma20 else "rising",
                "sma5_vs_sma20": "below" if sma5 < sma20 else "above",
            }
            data_freshness["vix_source"] = "yfinance"
            print(f"  VIX: {vix_close:.2f} (SMA5 {'<' if sma5 < sma20 else '>'} SMA20)")
    except Exception as e:
        print(f"  WARNING: VIX data unavailable: {e}")
        cross_asset["vix"] = {"value": None, "trend": "unknown", "error": str(e)}
        data_freshness["vix_source"] = "unavailable"

    # 2. TLT (bonds) via Alpaca
    tlt_ticker = cfg.get("tlt_ticker", "TLT")
    try:
        client = AlpacaClient()
        tlt_bars = client.get_bars(tlt_ticker, "1Day", lookback_days=cfg.get("trend_lookback_days", 20))
        if tlt_bars is not None and len(tlt_bars) > 0:
            tlt_close = float(tlt_bars["close"].iloc[-1])
            tlt_sma = float(tlt_bars["close"].mean())
            trend = "rising" if tlt_close > tlt_sma else "declining"
            interp = "yields_falling_risk_off" if trend == "rising" else "yields_rising_risk_on"
            cross_asset["tlt"] = {
                "price": round(tlt_close, 2),
                "trend": trend,
                "interpretation": interp,
            }
            data_freshness["tlt_source"] = "alpaca"
            print(f"  TLT: ${tlt_close:.2f} ({trend}) -> {interp}")
    except Exception as e:
        print(f"  WARNING: TLT data unavailable: {e}")
        cross_asset["tlt"] = {"price": None, "trend": "unknown", "error": str(e)}
        data_freshness["tlt_source"] = "unavailable"

    # 3. UUP (dollar) via Alpaca
    uup_ticker = cfg.get("uup_ticker", "UUP")
    try:
        client = AlpacaClient()
        uup_bars = client.get_bars(uup_ticker, "1Day", lookback_days=cfg.get("trend_lookback_days", 20))
        if uup_bars is not None and len(uup_bars) > 0:
            uup_close = float(uup_bars["close"].iloc[-1])
            uup_sma = float(uup_bars["close"].mean())
            trend = "rising" if uup_close > uup_sma else "flat" if abs(uup_close - uup_sma) / uup_sma < 0.005 else "declining"
            interp = "dollar_strong" if trend == "rising" else "dollar_neutral" if trend == "flat" else "dollar_weak"
            cross_asset["uup"] = {
                "price": round(uup_close, 2),
                "trend": trend,
                "interpretation": interp,
            }
            data_freshness["uup_source"] = "alpaca"
            print(f"  UUP: ${uup_close:.2f} ({trend}) -> {interp}")
    except Exception as e:
        print(f"  WARNING: UUP data unavailable: {e}")
        cross_asset["uup"] = {"price": None, "trend": "unknown", "error": str(e)}
        data_freshness["uup_source"] = "unavailable"

    # 4. Yield curve via yfinance
    yield_10y = cfg.get("yield_10y_ticker", "^TNX")
    yield_3m = cfg.get("yield_3m_ticker", "^IRX")
    try:
        tnx = yf.Ticker(yield_10y).history(period="5d")
        irx = yf.Ticker(yield_3m).history(period="5d")
        if tnx is not None and len(tnx) > 0 and irx is not None and len(irx) > 0:
            tnx_val = float(tnx["Close"].iloc[-1])
            irx_val = float(irx["Close"].iloc[-1])
            spread = round(tnx_val - irx_val, 3)
            cross_asset["yield_curve"] = {
                "spread_10y_3m": spread,
                "inverted": spread < 0,
                "ten_year": round(tnx_val, 3),
                "three_month": round(irx_val, 3),
            }
            data_freshness["yield_curve_source"] = "yfinance"
            print(f"  Yield Curve: 10Y={tnx_val:.3f}% 3M={irx_val:.3f}% spread={spread:.3f}{'  INVERTED' if spread < 0 else ''}")
    except Exception as e:
        print(f"  WARNING: Yield curve data unavailable: {e}")
        cross_asset["yield_curve"] = {"spread_10y_3m": None, "inverted": None, "error": str(e)}
        data_freshness["yield_curve_source"] = "unavailable"

    # Determine macro regime suggestion
    vix_val = cross_asset.get("vix", {}).get("value")
    tlt_trend = cross_asset.get("tlt", {}).get("trend")
    yield_inverted = cross_asset.get("yield_curve", {}).get("inverted")

    if vix_val and vix_val > 30:
        regime_suggestion = "risk_off"
    elif vix_val and vix_val < 18 and tlt_trend == "declining":
        regime_suggestion = "risk_on"
    elif yield_inverted:
        regime_suggestion = "risk_off"
    else:
        regime_suggestion = "neutral"

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "cross_asset_signals": cross_asset,
        "macro_regime_suggestion": regime_suggestion,
        "key_events": [],  # Populated by LLM teammate reasoning, empty in code path
        "data_freshness": data_freshness,
    }

    output_path = Path(state_dir) / "macro_outlook.json"
    save_state_atomic(output_path, result)
    print(f"\n  Wrote macro_outlook.json -> regime suggestion: {regime_suggestion}")

    return result


def get_recent_eod_insights(max_days: int = 3) -> list[dict]:
    """Load recent EOD reviews with confidence decay.

    Yesterday=1.0, 2 days ago=0.5, 3 days ago=0.25.
    Used by CIO to inform stance decisions (EOD-03 / MEM-05).
    """
    orch = get_orchestrator()
    decay_cfg = orch.config.get("eod_review", {}).get("decay_weights", {1: 1.0, 2: 0.5, 3: 0.25})
    state_base = Path(get_state_dir()).parent  # parent of YYYY-MM-DD dir
    results = []
    today = datetime.now().date()

    for days_ago in range(1, max_days + 1):
        target_date = today - timedelta(days=days_ago)
        eod_path = state_base / target_date.isoformat() / "eod_review.json"
        if eod_path.exists():
            try:
                with open(eod_path) as f:
                    eod_data = json.load(f)
                weight = decay_cfg.get(days_ago, decay_cfg.get(str(days_ago), 0.0))
                results.append({
                    "date": target_date.isoformat(),
                    "weight": weight,
                    "observations": eod_data.get("observations", []),
                    "thesis_drift_alerts": eod_data.get("thesis_drift_alerts", []),
                    "portfolio_summary": eod_data.get("portfolio_summary", {}),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return results


def task_cio_directive() -> dict:
    """Produce daily_directive.json with trading stance and risk budget.

    CIO scope is narrow per D-04: sets stance + multiplier only.
    Does NOT veto individual trades (Risk Manager's job).
    Goes live from day 1 per D-06.
    """
    orch = get_orchestrator()
    state_dir = get_state_dir()
    cio_cfg = orch.config.get("cio", {})

    print("\n" + "=" * 60)
    print("  CIO - Daily Trading Directive")
    print("=" * 60)

    # Read inputs per D-05
    inputs_used = {
        "macro_outlook_available": False,
        "yesterday_eod_available": False,
        "market_regime": "unknown",
    }

    # 1. Read macro_outlook.json (from Macro Strategist)
    macro_path = Path(state_dir) / "macro_outlook.json"
    macro = {}
    if macro_path.exists():
        try:
            with open(macro_path) as f:
                macro = json.load(f)
            inputs_used["macro_outlook_available"] = True
            print(f"  Macro outlook loaded: regime suggestion = {macro.get('macro_regime_suggestion', 'N/A')}")
        except (json.JSONDecodeError, KeyError):
            print("  WARNING: Macro outlook file corrupted, proceeding without")

    # 2. Read yesterday's EOD review (with decay)
    eod_insights = get_recent_eod_insights()
    if eod_insights:
        inputs_used["yesterday_eod_available"] = True
        yesterday = eod_insights[0]
        print(f"  Yesterday's EOD: P&L={yesterday.get('portfolio_summary', {}).get('total_pnl_today', 'N/A')}")
        if yesterday.get("thesis_drift_alerts"):
            print(f"  WARNING: Thesis drift alerts: {len(yesterday['thesis_drift_alerts'])} positions")

    # 3. Get market regime
    regime_data = orch._detect_market_regime()
    regime = regime_data.get("regime", "transitional")
    inputs_used["market_regime"] = regime
    print(f"  Market regime: {regime}")

    # Apply stance triggers (from Research pitfall 1 prevention)
    vix_val = macro.get("cross_asset_signals", {}).get("vix", {}).get("value")
    yield_inverted = macro.get("cross_asset_signals", {}).get("yield_curve", {}).get("inverted")
    spy_aligned_risk_on = (regime == "risk_on")

    stance_triggers = []
    halt_trading = False

    # Emergency halt
    halt_threshold = cio_cfg.get("halt_on_vix_above", 40)
    if vix_val and vix_val > halt_threshold:
        halt_trading = True
        stance_triggers.append(f"VIX={vix_val:.1f} > halt_threshold={halt_threshold}")

    # Determine stance
    defensive_vix = cio_cfg.get("vix_defensive_threshold", 30)
    aggressive_vix = cio_cfg.get("vix_aggressive_threshold", 18)

    if halt_trading:
        trading_stance = "defensive"
        risk_budget_multiplier = 0.0
        stance_triggers.append("HALT: all trading suspended")
    elif vix_val and vix_val > defensive_vix and yield_inverted:
        trading_stance = "defensive"
        risk_budget_multiplier = cio_cfg.get("defensive_multiplier", 0.6)
        stance_triggers.append(f"VIX={vix_val:.1f}>{defensive_vix} AND yield_curve_inverted")
    elif vix_val and vix_val < aggressive_vix and spy_aligned_risk_on:
        trading_stance = "aggressive"
        risk_budget_multiplier = cio_cfg.get("aggressive_multiplier", 1.3)
        stance_triggers.append(f"VIX={vix_val:.1f}<{aggressive_vix} AND SPY_EMA_risk_on")
    else:
        trading_stance = "neutral"
        risk_budget_multiplier = cio_cfg.get("neutral_multiplier", 1.0)
        if not stance_triggers:
            stance_triggers.append("no_trigger_matched -> neutral")

    reasoning = f"Market regime: {regime}. "
    if vix_val:
        reasoning += f"VIX at {vix_val:.1f}. "
    if yield_inverted is not None:
        reasoning += f"Yield curve {'inverted' if yield_inverted else 'normal'}. "
    reasoning += f"Stance: {trading_stance} (multiplier: {risk_budget_multiplier})."

    print(f"\n  Stance: {trading_stance} | Multiplier: {risk_budget_multiplier} | Halt: {halt_trading}")

    result = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "timestamp": datetime.now().isoformat(),
        "trading_stance": trading_stance,
        "risk_budget_multiplier": risk_budget_multiplier,
        "halt_trading": halt_trading,
        "reasoning": reasoning,
        "inputs_used": inputs_used,
        "stance_triggers_met": stance_triggers,
    }

    output_path = Path(state_dir) / "daily_directive.json"
    save_state_atomic(output_path, result)
    print(f"  Wrote daily_directive.json")

    return result


def task_symbol_screener() -> dict:
    """Task for Symbol Screener agent. Discovers symbols dynamically."""
    print("🔎 [Symbol Screener] Starting market screening...")
    orch = get_orchestrator()
    result = orch.run_symbol_screener()
    print(f"🔎 [Symbol Screener] ✅ Complete: {len(result['stocks'])} stocks")
    return result


def task_market_analyst() -> dict:
    """Task for Market Analyst agent."""
    print("🔍 [Market Analyst] Starting data collection...")
    orch = get_orchestrator()
    result = orch.run_market_analyst()
    print("🔍 [Market Analyst] ✅ Complete")
    return result


def task_technical_analyst() -> dict:
    """Task for Technical Analyst agent."""
    print("📊 [Technical Analyst] Starting analysis...")
    orch = get_orchestrator()
    result = orch.run_technical_analyst()
    print("📊 [Technical Analyst] ✅ Complete")
    return result


def task_sentiment_analyst() -> dict:
    """Task for Sentiment Analyst agent."""
    print("💭 [Sentiment Analyst] Starting sentiment analysis...")
    orch = get_orchestrator()
    result = orch.run_sentiment_analyst()
    print("💭 [Sentiment Analyst] ✅ Complete")
    return result


def task_position_review() -> list[dict]:
    """Task for Position Exit Review agent. Reviews existing positions for exit signals."""
    print("🔄 [Position Reviewer] Reviewing existing positions...")
    orch = get_orchestrator()

    # Load tech signals and market data from shared state
    tech_signals = {}
    market_data = {}
    state_dir = get_state_dir()
    tech_path = state_dir / "technical_signals.json"
    market_path = state_dir / "market_overview.json"
    if tech_path.exists():
        with open(tech_path) as f:
            tech_signals = json.load(f)
    if market_path.exists():
        with open(market_path) as f:
            market_data = json.load(f)

    exit_candidates = orch.run_position_exit_review(tech_signals, market_data)
    print(f"🔄 [Position Reviewer] ✅ Complete: {len(exit_candidates)} positions flagged for exit")
    return exit_candidates


def task_execute_exits(exit_candidates: list[dict]) -> list[dict]:
    """Task for Executor agent. Closes positions flagged for exit."""
    print("📤 [Executor] Closing positions...")
    orch = get_orchestrator()
    notifier = TelegramNotifier()

    executed_exits = []
    for candidate in exit_candidates:
        try:
            print(f"  📤 Closing {candidate['symbol']} ({candidate['side']}): "
                  f"qty={abs(candidate['qty'])} @ ~${candidate['current_price']:.2f}")

            result = orch.client.close_position(
                symbol=candidate["symbol"],
            )
            candidate["order_id"] = result["id"]
            candidate["order_status"] = result["status"]
            executed_exits.append(candidate)

            print(f"  ✅ Closed: {result['id']} | Status: {result['status']}")

            # Telegram notification with ROI
            notifier.alert_position_closed(
                symbol=candidate["symbol"],
                side=candidate["side"],
                qty=candidate["qty"],
                avg_entry_price=candidate["avg_entry_price"],
                exit_price=candidate["current_price"],
                unrealized_pl=candidate["unrealized_pl"],
                unrealized_plpc=candidate["unrealized_plpc"],
                exit_reason=candidate["exit_reason"],
                order_id=result["id"],
            )

            # Log trade
            orch._log_trade({
                "symbol": candidate["symbol"],
                "side": "sell" if candidate["side"] == "long" else "buy",
                "suggested_qty": abs(candidate["qty"]),
                "entry_price": candidate["current_price"],
                "composite_score": candidate.get("exit_score", 0),
                "action": "close_position",
                "exit_reason": candidate["exit_reason"],
            }, result)

            # Trade journal close entry (MEM-02)
            try:
                from src.journal.trade_journal import journal_on_close
                journal_on_close(candidate, result)
            except Exception as e:
                print(f"  Warning: Journal on-close failed for {candidate['symbol']}: {e}")

        except Exception as e:
            print(f"  ❌ Failed to close {candidate['symbol']}: {e}")
            notifier.alert_order_rejected(candidate["symbol"], f"Exit failed: {e}")

    print(f"📤 [Executor] ✅ Exits complete: {len(executed_exits)}/{len(exit_candidates)} closed")
    return executed_exits


def task_risk_manager(candidates: list[dict]) -> list[dict]:
    """Task for Risk Manager agent. Requires candidates from decision engine."""
    print("🛡️ [Risk Manager] Starting risk assessment...")
    orch = get_orchestrator()
    result = orch.run_risk_manager(candidates)
    print("🛡️ [Risk Manager] ✅ Complete")
    return result


def task_portfolio_strategist(assessed: list[dict]) -> list[dict]:
    """Task for Portfolio Strategist. Post-processes risk-assessed trades for correlation optimization."""
    print("[Portfolio Strategist] Analyzing cross-position correlations...")
    orch = get_orchestrator()
    from src.portfolio.strategist import PortfolioStrategist

    strategist = PortfolioStrategist(orch.config)

    # Get current portfolio positions
    try:
        positions = orch.client.get_positions()
    except Exception as e:
        print(f"  Warning: Could not fetch positions: {e}. Skipping correlation analysis.")
        return assessed

    existing_symbols = [p["symbol"] for p in positions]
    approved_symbols = [t["symbol"] for t in assessed if t.get("approved")]

    # If no existing positions, skip correlation (first trades of the day)
    if not existing_symbols:
        print("  No existing positions. Skipping correlation analysis.")
        # Still write a minimal portfolio_construction.json
        save_state_atomic(
            Path(orch.state_dir) / "portfolio_construction.json",
            {
                "status": "skipped",
                "reason": "no_existing_positions",
                "adjustments": [],
                "partial_close_suggestions": [],
            },
        )
        return assessed

    # Combine all symbols for correlation matrix
    all_symbols = list(set(existing_symbols + approved_symbols))

    # Compute correlation matrix using cached bar data
    corr_matrix, metadata = strategist.compute_correlation_matrix(
        symbols=all_symbols,
        bar_getter=orch._get_bars,
    )

    if corr_matrix.empty:
        print(f"  Insufficient data for correlation matrix. Skipping.")
        return assessed

    print(
        f"  Correlation matrix: {len(metadata['symbols_included'])} symbols, "
        f"{metadata['data_points']} data points, {len(metadata['symbols_skipped'])} skipped"
    )

    # Apply sizing adjustments to approved trades
    adjusted = strategist.adjust_sizing(assessed, existing_symbols, corr_matrix)

    # Check for rejections and reductions
    for orig, adj in zip(assessed, adjusted):
        if orig.get("approved") and not adj.get("approved"):
            print(f"  REJECTED {adj['symbol']}: {adj.get('portfolio_rejection', 'correlation too high')}")
        elif adj.get("portfolio_correlation"):
            pc = adj["portfolio_correlation"]
            print(f"  REDUCED {adj['symbol']}: max_corr={pc['max_correlation']:.2f}, action={pc['action']}")

    # Suggest partial closes for concentrated portfolio (D-03)
    partial_suggestions = strategist.suggest_partial_closes(positions, corr_matrix)
    if partial_suggestions:
        print(f"  Portfolio concentration: {len(partial_suggestions)} partial close suggestion(s)")
        for s in partial_suggestions:
            print(f"    {s['symbol']}: close {s['partial_close_pct']*100:.0f}% -- {s['exit_reason']}")

    # Read CIO stance if available
    cio_stance = "neutral"
    try:
        directive_path = Path(orch.state_dir) / "daily_directive.json"
        if directive_path.exists():
            with open(directive_path) as f:
                cio_stance = json.load(f).get("trading_stance", "neutral")
    except Exception:
        pass

    # Build and save portfolio_construction.json
    result = strategist.build_result(corr_matrix, metadata, adjusted, partial_suggestions, cio_stance)
    save_state_atomic(
        Path(orch.state_dir) / "portfolio_construction.json",
        result,
    )
    print("[Portfolio Strategist] Complete")

    return adjusted


def task_generate_decisions(tech_signals: dict, sentiment: dict, market_data: dict = None) -> list[dict]:
    """Generate trade decisions from aggregated signals."""
    print("🧠 [Decision Engine] Aggregating signals...")
    orch = get_orchestrator()
    candidates = orch.generate_trade_plan(tech_signals, sentiment, market_data)
    print(f"🧠 [Decision Engine] ✅ Generated {len(candidates)} candidates")
    return candidates


def task_execute_trades(assessed: list[dict]) -> list[dict]:
    """Task for Executor agent. Places orders for approved trades.

    Reads execution_plan.json (if present) to dispatch the recommended
    order type (market, limit, or bracket) per trade. Falls back to
    bracket/market when no plan exists (D-12 graceful degradation).
    """
    print("⚡ [Executor] Starting order execution...")
    orch = get_orchestrator()
    notifier = TelegramNotifier()

    approved = [t for t in assessed if t.get("approved")]
    executed = []

    if not approved:
        print("⚡ [Executor] 📭 No approved trades to execute.")
        return []

    # Load execution plan if available (EXEC-02)
    exec_plan = {}
    exec_plan_path = get_state_dir() / "execution_plan.json"
    if exec_plan_path.exists():
        try:
            with open(exec_plan_path, "r", encoding="utf-8") as f:
                exec_plan_data = json.load(f)
            for p in exec_plan_data.get("plans", []):
                exec_plan[p["symbol"]] = p
            print(f"  📊 Execution plan loaded: {len(exec_plan)} trade recommendations")
        except Exception as e:
            print(f"  ⚠️  Failed to load execution plan: {e}. Using default order types.")

    # Market hours check
    try:
        clock = orch.client.is_market_open()
        if not clock["is_open"]:
            print(f"  ⚠️  Market closed. Orders will queue until open. Next open: {clock['next_open']}")
    except Exception:
        pass

    for trade in approved:
        try:
            side_emoji = "🟢 BUY" if trade["side"] == "buy" else "🔴 SELL"
            entry_str = f"@ ~${trade['entry_price']:.2f}" if trade.get("entry_price") else ""
            print(f"  📋 Placing order: {side_emoji} {trade['symbol']} "
                  f"x{trade['suggested_qty']} {entry_str}")

            # Determine order type from execution plan (EXEC-01/02)
            plan = exec_plan.get(trade["symbol"], {})
            order_type = plan.get("order_type", "bracket")  # Default: bracket

            if order_type == "limit" and plan.get("limit_price"):
                print(f"  📋 Order type: limit @ ${plan['limit_price']:.2f}")
                result = orch.client.place_limit_order(
                    symbol=trade["symbol"],
                    qty=trade["suggested_qty"],
                    limit_price=plan["limit_price"],
                    side=trade["side"],
                )
            elif order_type == "market":
                print(f"  📋 Order type: market")
                result = orch.client.place_market_order(
                    symbol=trade["symbol"],
                    qty=trade["suggested_qty"],
                    side=trade["side"],
                )
            else:
                # Default: bracket (existing behavior) or fallback from limit without price
                order_type = "bracket"
                if trade.get("stop_loss") and trade.get("take_profit"):
                    print(f"  📋 Order type: bracket")
                    result = orch.client.place_bracket_order(
                        symbol=trade["symbol"],
                        qty=trade["suggested_qty"],
                        side=trade["side"],
                        stop_loss_price=trade["stop_loss"],
                        take_profit_price=trade["take_profit"],
                    )
                else:
                    order_type = "market"
                    print(f"  📋 Order type: market (no SL/TP for bracket)")
                    result = orch.client.place_market_order(
                        symbol=trade["symbol"],
                        qty=trade["suggested_qty"],
                        side=trade["side"],
                    )

            # Track order type used for fill quality (EXEC-03)
            trade["order_type_used"] = order_type

            trade["order_id"] = result["id"]
            trade["order_status"] = result["status"]
            executed.append(trade)
            print(f"  ✅ Order placed: {result['id']} | Status: {result['status']}")

            # Log trade
            orch._log_trade(trade, result)

            # Trade journal entry (MEM-02)
            try:
                from src.journal.trade_journal import journal_on_fill
                journal_on_fill(trade, result)
            except Exception as e:
                print(f"  Warning: Journal on-fill failed for {trade['symbol']}: {e}")

            # Telegram notification
            notifier.alert_order_executed(
                symbol=trade["symbol"],
                side=trade["side"],
                qty=trade["suggested_qty"],
                price=trade.get("entry_price"),
                order_id=result["id"],
            )

        except Exception as e:
            print(f"  ❌ Order failed for {trade['symbol']}: {e}")
            notifier.alert_order_rejected(trade["symbol"], str(e))

    # Save execution results
    execution_results = {
        "timestamp": datetime.now().isoformat(),
        "total_approved": len(approved),
        "total_executed": len(executed),
        "trades": [
            {
                "symbol": t["symbol"],
                "side": t["side"],
                "qty": t["suggested_qty"],
                "entry_price": t.get("entry_price"),
                "order_id": t.get("order_id"),
                "order_status": t.get("order_status"),
            }
            for t in executed
        ],
    }
    exec_state_dir = get_state_dir()
    with open(exec_state_dir / "execution_results.json", "w") as f:
        json.dump(execution_results, f, indent=2, default=str)

    print(f"⚡ [Executor] ✅ Complete: {len(executed)}/{len(approved)} orders placed")
    return executed


def task_send_report():
    """Send full report via Telegram."""
    notifier = TelegramNotifier()
    client = AlpacaClient()

    account = client.get_account()
    positions = client.get_positions()
    notifier.report_portfolio(account, positions)

    # Load latest decisions
    report_state_dir = get_state_dir()
    decisions_path = report_state_dir / "decisions.json"
    if decisions_path.exists():
        with open(decisions_path) as f:
            decisions = json.load(f)

        candidates = decisions.get("candidates", [])
        risk_path = report_state_dir / "risk_assessment.json"
        if risk_path.exists():
            with open(risk_path) as f:
                risk_data = json.load(f)

            # Merge risk assessments onto candidates so report has both
            # composite_score (from candidate) and suggested_qty/reason (from risk)
            risk_by_symbol = {a["symbol"]: a for a in risk_data.get("assessments", [])}
            approved = []
            rejected = []
            for c in candidates:
                risk_info = risk_by_symbol.get(c["symbol"])
                if risk_info:
                    merged = {**c, **risk_info}
                    if risk_info.get("approved"):
                        approved.append(merged)
                    else:
                        merged["risk_assessment"] = {"reason": risk_info.get("reason", "N/A")}
                        rejected.append(merged)
            notifier.report_pipeline_summary(candidates, approved, rejected)

    print("📨 [Reporter] ✅ Telegram report sent")


# ══════════════════════════════════════════════
# Debate & Reflection Task Functions
# Called by Claude Agent Teams Lead agent
# ══════════════════════════════════════════════

def task_fundamentals_analyst(symbols: list[str]) -> dict:
    """Fetch fundamentals for Top-N debate candidates."""
    print(f"📋 [Fundamentals] Fetching data for {symbols}...")
    orch = get_orchestrator()
    result = orch.run_fundamentals_analyst(symbols)
    print(f"📋 [Fundamentals] ✅ Complete: {len(result.get('signals', {}))} symbols")
    return result


def task_prepare_debate(symbol: str) -> dict:
    """Prepare debate context for a single symbol. Called before spawning Bull/Bear/Judge."""
    print(f"📝 [Debate Prep] Assembling context for {symbol}...")
    orch = get_orchestrator()
    context = task_prepare_debate_context(symbol, orch)
    print(f"📝 [Debate Prep] ✅ Context saved to shared_state/debate_context_{symbol}.json")
    return context


def task_merge_debates(candidates: list[dict]) -> list[dict]:
    """Merge investment debate score_adjustments back into candidates."""
    print("🔀 [Debate Merge] Merging debate results...")
    result = task_merge_debate_results(candidates)
    print(f"🔀 [Debate Merge] ✅ Merged {len(result)} candidates")
    return result


def task_sector_specialist(symbol: str) -> dict:
    """Fetch sector intelligence for a symbol and persist to shared_state.

    Called by Lead Agent BEFORE task_prepare_debate() so that sector data
    is available when debate context is assembled.  The result is also saved
    to ``sector_intelligence_{symbol}.json`` so task_prepare_debate_context
    can load it without re-fetching (deduplication).
    """
    try:
        print(f"  [Sector Specialist] Fetching sector intelligence for {symbol}...")
        sector_data = _fetch_sector_intelligence(symbol, {})
        # Persist so debate prep can pick it up without re-fetching
        state_dir = get_state_dir()
        out_path = state_dir / f"sector_intelligence_{symbol}.json"
        save_state_atomic(out_path, sector_data)
        print(f"  [Sector Specialist] Sector intelligence for {symbol}")
        return sector_data
    except Exception as e:
        print(f"  [Sector Specialist] WARNING: Failed for {symbol}: {e}")
        return {}


def task_check_reflections() -> list[dict]:
    """Check for closed trades that need post-trade reflection."""
    print("🔍 [Reflection] Checking for unreflected trades...")
    trades = get_unreflected_trades()
    print(f"🔍 [Reflection] Found {len(trades)} trade(s) needing reflection")
    return trades


def task_prepare_reflection(trade_record: dict) -> dict:
    """Prepare reflection context for a single closed trade."""
    trade_id = trade_record.get("order_id", "unknown")
    print(f"📝 [Reflection Prep] Assembling context for trade {trade_id}...")
    orch = get_orchestrator()
    context = task_prepare_reflection_context(trade_record, orch)
    print(f"📝 [Reflection Prep] ✅ Context saved")
    return context


def task_save_reflection_results(trade_id: str) -> bool:
    """Save reflection results into memory banks."""
    print(f"💾 [Reflection Save] Saving lessons for trade {trade_id}...")
    orch = get_orchestrator()
    success = task_save_reflections(trade_id, orch)
    if success:
        print(f"💾 [Reflection Save] ✅ Lessons saved to memory banks")
    else:
        print(f"💾 [Reflection Save] ⚠️  No reflection result found for {trade_id}")
    return success


def task_extract_patterns() -> int:
    """Extract trade patterns from closed journal entries (MEM-03).

    Can be called standalone or is triggered automatically after reflection.
    Returns count of patterns extracted.
    """
    print("📊 [Pattern Learning] Extracting trade patterns...")
    try:
        from src.memory.patterns import load_and_extract_patterns
        count = load_and_extract_patterns()
        if count == 0:
            print("📊 [Pattern Learning] ℹ️  Not enough closed trades for pattern extraction")
        else:
            print(f"📊 [Pattern Learning] ✅ Extracted {count} patterns from journal")
        return count
    except Exception as e:
        print(f"📊 [Pattern Learning] ⚠️  Failed: {e}")
        return 0


# ══════════════════════════════════════════════
# EOD Review Task Function
# Produces eod_review.json with P&L attribution,
# thesis drift detection, and observation-framed insights
# ══════════════════════════════════════════════

def task_eod_review() -> dict:
    """Produce eod_review.json with P&L attribution and thesis drift detection.

    EOD-01: P&L attribution for all open positions.
    EOD-02: Thesis drift -- compare entry signals vs current state.
    EOD-03: confidence_weight=1.0 for today (decay applied by reader).

    Output is OBSERVATIONS not directives (Research pitfall 4 prevention).
    """
    orch = get_orchestrator()
    state_dir = get_state_dir()
    eod_cfg = orch.config.get("eod_review", {})

    print("\n" + "=" * 60)
    print("  EOD Review - Daily Performance Attribution")
    print("=" * 60)

    client = AlpacaClient()

    # Get current positions
    try:
        positions = client.get_positions()
    except Exception as e:
        print(f"  WARNING: Failed to get positions: {e}")
        positions = []

    # Get account for total P&L
    try:
        account = client.get_account()
        equity = float(account.get("equity", 0))
        last_equity = float(account.get("last_equity", 0))
        total_pnl_today = round(equity - last_equity, 2)
        total_pnl_pct = round((total_pnl_today / last_equity * 100) if last_equity else 0, 2)
    except Exception as e:
        print(f"  WARNING: Failed to get account: {e}")
        total_pnl_today = 0
        total_pnl_pct = 0

    # Read today's trade log for entry context
    trade_entries = {}
    for candidate_path in [Path(state_dir) / "trade_log.json",
                           Path(state_dir) / ".." / ".." / "logs" / "trade_log.json"]:
        if candidate_path.exists():
            try:
                with open(candidate_path) as f:
                    logs = json.load(f)
                for log in logs:
                    trade_entries[log.get("symbol", "")] = log
            except (json.JSONDecodeError, KeyError):
                pass

    # Review each position
    position_reviews = []
    thesis_drift_alerts = []
    observations = []

    drift_rsi_threshold = eod_cfg.get("drift_rsi_threshold", 15)
    drift_price_pct = eod_cfg.get("drift_price_reversal_pct", 5)

    for pos in positions:
        symbol = pos.get("symbol", "")
        try:
            unrealized_pl = float(pos.get("unrealized_pl", 0))
            unrealized_plpc = float(pos.get("unrealized_plpc", 0)) * 100
            avg_entry = float(pos.get("avg_entry_price", 0))
            current_price = float(pos.get("current_price", 0))
            qty = float(pos.get("qty", 0))
            side = pos.get("side", "long")

            # Get current technical signals for drift detection
            bars = orch._get_bars(symbol, "stock", lookback_days=30)
            current_rsi = None
            current_trend = "unknown"
            if bars is not None and len(bars) > 14:
                tech = TechnicalAnalyzer()
                signal = tech.analyze(bars, symbol)
                if signal:
                    current_rsi = signal.rsi
                    current_trend = (
                        "bullish" if signal.score > 0.1
                        else "bearish" if signal.score < -0.1
                        else "neutral"
                    )

            # Check for thesis drift
            entry_data = trade_entries.get(symbol, {})
            entry_score = entry_data.get("score", None)
            character_change = False
            drift_notes = []

            # Price reversal check
            if avg_entry > 0 and current_price > 0:
                price_change_pct = ((current_price - avg_entry) / avg_entry) * 100
                if side == "long" and price_change_pct < -drift_price_pct:
                    character_change = True
                    drift_notes.append(f"Price reversed {price_change_pct:.1f}% from entry")

            # RSI divergence check (if we have entry score and current RSI)
            if current_rsi is not None and entry_score is not None:
                # If entry was bullish but current RSI dropped significantly
                if entry_score > 0.2 and current_rsi < 45:
                    character_change = True
                    drift_notes.append(
                        f"RSI dropped to {current_rsi:.0f} (entry was bullish score={entry_score:.2f})"
                    )

            review = {
                "symbol": symbol,
                "qty": qty,
                "side": side,
                "avg_entry_price": avg_entry,
                "current_price": current_price,
                "pnl_today": round(unrealized_pl, 2),
                "pnl_pct": round(unrealized_plpc, 2),
                "thesis_status": "drift_detected" if character_change else "intact",
                "character_change": character_change,
                "current_trend": current_trend,
                "notes": (
                    "; ".join(drift_notes) if drift_notes
                    else "Position characteristics unchanged"
                ),
            }
            position_reviews.append(review)

            if character_change:
                thesis_drift_alerts.append({
                    "symbol": symbol,
                    "original_entry_score": entry_score,
                    "current_status": "; ".join(drift_notes),
                    "recommendation": "Monitor for exit signal",
                })

            drift_marker = " DRIFT" if character_change else " intact"
            print(
                f"  {symbol}: P&L={unrealized_pl:+.2f} ({unrealized_plpc:+.1f}%){drift_marker}"
            )

        except Exception as e:
            print(f"  WARNING: Error reviewing {symbol}: {e}")
            position_reviews.append({
                "symbol": symbol,
                "error": str(e),
                "thesis_status": "unknown",
                "character_change": False,
            })

    # Count today's trades
    today_str = datetime.now().strftime("%Y-%m-%d")
    new_entries = sum(
        1 for t in trade_entries.values()
        if t.get("side") == "buy" and t.get("timestamp", "").startswith(today_str)
    )
    exits = sum(
        1 for t in trade_entries.values()
        if t.get("side") == "sell" and t.get("timestamp", "").startswith(today_str)
    )

    # Generate observations (NOT directives, per Research pitfall 4)
    if total_pnl_today > 0:
        observations.append(f"Portfolio gained ${total_pnl_today:.2f} ({total_pnl_pct:+.2f}%) today")
    elif total_pnl_today < 0:
        observations.append(f"Portfolio lost ${abs(total_pnl_today):.2f} ({total_pnl_pct:+.2f}%) today")
    else:
        observations.append("Portfolio flat today")

    if thesis_drift_alerts:
        observations.append(f"{len(thesis_drift_alerts)} position(s) showing thesis drift")

    if len(positions) > 0:
        winners = sum(1 for r in position_reviews if r.get("pnl_today", 0) > 0)
        losers = sum(1 for r in position_reviews if r.get("pnl_today", 0) < 0)
        observations.append(
            f"Position performance: {winners} winning, {losers} losing out of {len(positions)}"
        )

    result = {
        "date": today_str,
        "timestamp": datetime.now().isoformat(),
        "portfolio_summary": {
            "total_pnl_today": total_pnl_today,
            "total_pnl_pct": total_pnl_pct,
            "positions_count": len(positions),
            "new_entries": new_entries,
            "exits": exits,
        },
        "position_reviews": position_reviews,
        "thesis_drift_alerts": thesis_drift_alerts,
        "observations": observations,
        "confidence_weight": 1.0,  # Today's review, full confidence. Decay applied by reader (MEM-05).
    }

    output_path = Path(state_dir) / "eod_review.json"
    save_state_atomic(output_path, result)
    print(
        f"\n  Wrote eod_review.json ({len(positions)} positions reviewed, "
        f"{len(thesis_drift_alerts)} drift alerts)"
    )

    return result


# ══════════════════════════════════════════════
# Full Pipeline (standalone mode)
# ══════════════════════════════════════════════

def run_full_pipeline(execute: bool = False, notify: bool = True):
    """
    Run the complete multi-agent pipeline.
    Can be used standalone or as a reference for Agent Teams.
    """
    notifier = TelegramNotifier()

    orch = get_orchestrator()

    print("\n" + "🚀" * 20)
    print("  MULTI-AGENT TRADING PIPELINE")
    print(f"  Watchlist: {orch.watchlist_mode.upper()}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("🚀" * 20)

    # ══════════════════════════════════════════════
    # Pre-Market Strategic Layer (D-10)
    # ══════════════════════════════════════════════

    # Phase -2: Macro Strategist
    print("\n" + "=" * 60)
    print("📍 PRE-MARKET: Macro Strategist")
    print("=" * 60)
    try:
        macro_result = task_macro_strategist()
        print(f"  ✅ Macro outlook: regime suggestion = {macro_result.get('macro_regime_suggestion', 'N/A')}")
    except Exception as e:
        # Graceful degradation per D-12: non-critical failure
        print(f"  ⚠️ Macro Strategist failed: {e}. CIO will decide without macro data.")
        macro_result = None

    # Phase -1: CIO Directive
    print("\n" + "=" * 60)
    print("📍 PRE-MARKET: CIO Directive")
    print("=" * 60)
    try:
        cio_result = task_cio_directive()
        print(f"  ✅ CIO stance: {cio_result.get('trading_stance', 'N/A')} (multiplier={cio_result.get('risk_budget_multiplier', 'N/A')})")

        # Check for halt (CIO-02)
        if cio_result.get("halt_trading", False):
            print("\n  🛑 CIO HALT: All trading suspended for today.")
            print("  Skipping analysis and trading phases.")
            print("  Running EOD Review only.\n")
            # Skip to EOD Review
            try:
                task_eod_review()
            except Exception as eod_err:
                print(f"  ⚠️ EOD Review failed: {eod_err}")
            if notify:
                try:
                    notifier.send("🛑 CIO HALT: All trading suspended for today. No trades executed.")
                except Exception:
                    pass
            return
    except Exception as e:
        # CIO failure is NOT a hard stop per D-12
        print(f"  ⚠️ CIO Directive failed: {e}. Proceeding with default stance (neutral).")
        cio_result = None

    # Phase 0: Dynamic symbol screening (if enabled)
    if orch.watchlist_mode == "dynamic":
        task_symbol_screener()

    # Phase 1: Parallel data collection
    # In Agent Teams, these run as separate teammates
    market_data = task_market_analyst()
    tech_signals = task_technical_analyst()
    sentiment = task_sentiment_analyst()

    # Phase 1.5: Position exit review
    exit_candidates = task_position_review()

    # Execute exits BEFORE new entries (frees capital & position slots)
    if execute and exit_candidates:
        task_execute_exits(exit_candidates)

    # Phase 2: Decision engine
    candidates = task_generate_decisions(tech_signals, sentiment, market_data)

    if not candidates:
        print("\n📭 No trade candidates. Pipeline complete.")
        if notify and not exit_candidates:
            notifier.send("📭 *Pipeline Complete*\nNo trade candidates meet threshold.")
        return

    # Phase 2.5: Fundamentals for Top-N (standalone mode — no debate)
    # In Agent Teams mode, this is followed by Investment Debate (Phase 2.6)
    debate_cfg = orch.config.get("debate", {})
    top_n = debate_cfg.get("top_n", 3)
    top_symbols = [c["symbol"] for c in candidates[:top_n]]
    if top_symbols:
        task_fundamentals_analyst(top_symbols)
    print("  ℹ️  Standalone mode: Investment Debate (Phase 2.6) skipped — use Agent Teams for debate")

    # Phase 3: Risk assessment
    assessed = task_risk_manager(candidates)

    # Phase 3.5: Portfolio optimization (PORT-03)
    try:
        assessed = task_portfolio_strategist(assessed)
    except Exception as e:
        # Graceful degradation per D-12: non-critical failure
        print(f"  ⚠️ Warning: Portfolio Strategist failed: {e}. Proceeding with risk-assessed trades.")

    # Phase 3.5b: Execution Strategy (EXEC-01/02)
    try:
        from src.execution.strategist import task_execution_strategist
        assessed = task_execution_strategist(assessed)
    except Exception as e:
        print(f"  ⚠️  Execution Strategist failed (using default orders): {e}")

    # Re-derive approved/rejected after portfolio strategist adjustment
    approved = [t for t in assessed if t.get("approved")]
    rejected = [t for t in assessed if not t.get("approved")]

    # Execute partial close suggestions from Portfolio Strategist (D-03)
    if execute:
        try:
            import json as _json
            pc_path = Path(orch.state_dir) / "portfolio_construction.json"
            if pc_path.exists():
                with open(pc_path) as f:
                    pc_data = _json.load(f)
                partial_closes = pc_data.get("partial_close_suggestions", [])
                if partial_closes:
                    print(f"\n  Portfolio Strategist: {len(partial_closes)} partial close suggestion(s)")
                    # Filter out symbols already exited by Position Reviewer
                    already_exited = {c["symbol"] for c in (exit_candidates or [])}
                    new_partials = [p for p in partial_closes if p["symbol"] not in already_exited]
                    if new_partials:
                        task_execute_exits(new_partials)
        except Exception as e:
            print(f"  ⚠️ Warning: Partial close execution failed: {e}")

    # Phase 4: Notify
    if notify:
        for trade in approved:
            notifier.alert_signal(
                symbol=trade["symbol"],
                side=trade.get("side", "buy"),
                score=trade.get("composite_score", 0),
                entry_price=trade.get("entry_price", 0),
                stop_loss=trade.get("stop_loss"),
                take_profit=trade.get("take_profit"),
                rsi=trade.get("rsi"),
                trend=trade.get("trend"),
            )
        notifier.report_pipeline_summary(candidates, approved, rejected)

    # Phase 5: Execute new entries (if enabled)
    if execute and approved:
        executed = task_execute_trades(assessed)
        print(f"\n✅ Pipeline complete: {len(executed)} executed, {len(rejected)} rejected"
              + (f", {len(exit_candidates)} exited" if exit_candidates else ""))
    else:
        print(f"\n✅ Pipeline complete: {len(approved)} approved, {len(rejected)} rejected"
              + (f", {len(exit_candidates)} exit signals" if exit_candidates else ""))
        if approved:
            print("   Run with --trade flag to execute orders")

    # Phase 6: Reflection — check for unreflected closed trades
    try:
        unreflected = task_check_reflections()
        if unreflected:
            print(f"\n🔄 Phase 6: Reflecting on {len(unreflected)} closed trade(s)...")
            for trade_record in unreflected:
                task_prepare_reflection(trade_record)
                # In standalone mode, reflection-analyst teammate is not available.
                # The reflection context is prepared for manual review or next Agent Teams run.
            print("  ℹ️  Standalone mode: Reflection Analyst skipped — contexts prepared for Agent Teams")
    except Exception as e:
        print(f"  ⚠️  Reflection check skipped: {e}")

    # ══════════════════════════════════════════════
    # Post-Market: EOD Review
    # ══════════════════════════════════════════════

    print("\n" + "=" * 60)
    print("📍 POST-MARKET: EOD Review")
    print("=" * 60)
    try:
        eod_result = task_eod_review()
        drift_count = len(eod_result.get("thesis_drift_alerts", []))
        if drift_count > 0:
            print(f"  ⚠️ {drift_count} thesis drift alert(s) detected")
        print(f"  ✅ EOD Review complete")
    except Exception as e:
        # Graceful degradation per D-12: non-critical failure
        print(f"  ⚠️ EOD Review failed: {e}. Pipeline complete without EOD review.")

    return assessed


# ══════════════════════════════════════════════
# Agent Teams Launch Prompt
# ══════════════════════════════════════════════

# DEPRECATED: Use src.team_orchestrator.build_team_prompt() instead.
# Kept for backward compatibility with existing scripts.
# The team_orchestrator generates a dynamic, config-driven prompt that
# reads model tiers from settings.yaml and embeds the CIO agent spec.
AGENT_TEAMS_PROMPT = """
# ─── Copy this into Claude Code after enabling Agent Teams ───

啟動一個 trading-analysis agent team 來分析市場並生成交易建議。
此 pipeline 包含投資辯論環節，模擬真實投資團隊的決策流程。
新增戰略監督層：宏觀策略師 → CIO 指令 → 原有 pipeline → EOD 審查。

## 架構說明
- **Subagent** = 讀取對應 agent spec（`agents/` 下的 .md），整份內容作為 Task tool prompt spawn 執行
- **Teammate** = 需要 LLM 推理，作為獨立 teammate spawn
- **Lead 直接執行** = 極簡操作，Lead 直接呼叫 Python 函數
- Agent spec 是自包含的，包含執行方式、輸入參數、輸出格式，可直接作為 Task tool prompt

## Model 分級（節省 Token 成本）
- **Tier 1 (Haiku)**: 純程式碼執行 subagent → `model="haiku"`
- **Tier 2 (Sonnet)**: 結構化論述 teammate → `model="sonnet"`
- **Tier 3 (Opus)**: 深度推理判決 teammate → 不指定 model（使用預設 Opus）

## Pipeline 總覽
```
Phase -2:  Macro Strategist     [Subagent, Sonnet]  (跨資產數據收集 → macro_outlook.json)
Phase -1:  CIO Directive        [Lead 直接執行]      (交易立場 + 風險預算 → daily_directive.json)
           → 如果 halt_trading=true: 跳至 EOD Review，跳過所有分析和交易
Phase 0:   Symbol Screener      [Subagent, Haiku]   (動態 watchlist，僅 dynamic 模式)
Phase 1:   Market/Tech/Sentiment [Subagent x3, Haiku] (可並行)
Phase 1.5: Position Exit Review  [Subagent, Haiku]
Phase 2:   Decision Engine       [Lead 直接執行]
Phase 2.5: Fundamentals + Debate [Subagent + Teammate]
Phase 3:   Risk Manager          [Subagent, Haiku]
Phase 4:   Executor              [Subagent, Haiku]
Phase 5:   Reporter              [Subagent, Haiku]   (Telegram 通知)
Phase 6:   EOD Review            [Subagent, Sonnet]  (P&L 歸因 + 論點漂移 → eod_review.json)
Phase 7:   Reflection            [Teammate, Opus]    (交易後學習)
```

---

## Phase -2 (Macro Strategist, 盤前第一步)
**[Subagent, model="sonnet"]** 讀取 `agents/strategic/macro_strategist.md` 完整內容，用 Task tool spawn 執行。使用 `model="sonnet"`。
或者 Lead 直接呼叫：
```python
from src.agents_launcher import task_macro_strategist
macro_result = task_macro_strategist()
```
輸出：`shared_state/YYYY-MM-DD/macro_outlook.json`（跨資產信號、宏觀環境建議）

---

## Phase -1 (CIO Directive, 等 Phase -2 完成)
**[Lead 直接執行]** CIO 讀取 macro_outlook.json + 昨日 eod_review.json + 市場環境，產生當日交易指令：
```python
from src.agents_launcher import task_cio_directive
cio_result = task_cio_directive()
```
輸出：`shared_state/YYYY-MM-DD/daily_directive.json`（trading_stance, risk_budget_multiplier, halt_trading）

**halt_trading 檢查**：如果 `daily_directive.json` 中 `halt_trading=true`，跳過所有分析和交易，直接執行 EOD Review 後結束 pipeline。

---

## Phase 0 (Symbol Discovery, 如果 watchlist_mode == "dynamic")
**[Subagent, model="haiku"]** 讀取 `agents/analysts/symbol_screener.md` 完整內容，用 Task tool spawn 執行。使用 `model="haiku"`。

---

## Phase 1 (Parallel Data Collection, 等 Phase 0 完成)
**[3 個並行 Subagent, model="haiku"]** 用 Task tool 同時 spawn 以下 3 個 subagents，全部使用 `model="haiku"`：
1. **market-data** → 讀取 `agents/analysts/market_analyst.md` 完整內容作為 prompt
2. **tech-signals** → 讀取 `agents/analysts/technical_analyst.md` 完整內容作為 prompt
3. **sentiment** → 讀取 `agents/analysts/sentiment_analyst.md` 完整內容作為 prompt

---

## Phase 1.5 (Position Exit Review, 等 Phase 1 全部完成)
**[Subagent, model="haiku"]** 讀取 `agents/trader/position_reviewer.md` 完整內容，用 Task tool spawn 執行。使用 `model="haiku"`。

---

## Phase 2 (Decision Engine, 等 Phase 1.5 完成)
**[Lead 直接執行]** Decision Engine — 純 Python 分數聚合：
```python
from src.agents_launcher import task_generate_decisions
from src.state_dir import get_state_dir
import json
state_dir = get_state_dir()
with open(state_dir / 'technical_signals.json') as f:
    tech = json.load(f)
with open(state_dir / 'sentiment_signals.json') as f:
    sent = json.load(f)
with open(state_dir / 'market_overview.json') as f:
    market = json.load(f)
candidates = task_generate_decisions(tech, sent, market)
```

---

## Phase 2.5 (Fundamentals + Investment Debate, 取 Top-N 候選)

**[Subagent, model="haiku"]** 取得基本面資料：讀取 `agents/analysts/fundamentals_analyst.md`，附加輸入參數 `symbols = Top-N 候選標的列表`。使用 `model="haiku"`。

**[Lead]** 準備辯論上下文：
```python
from src.agents_launcher import task_prepare_debate
for symbol in top_symbols:
    task_prepare_debate(symbol)
```

### 投資辯論（對每個 Top-N 候選，可並行）
**[Teammates]** 對每個候選 symbol，依序 spawn 以下 teammates：

- **bull-researcher-{symbol}** (model="sonnet") → 讀取 `agents/researchers/bull_researcher.md` + `shared_state/debate_context_{symbol}.json`。使用 `model="sonnet"`。
- **bear-researcher-{symbol}** (等 bull 完成, model="sonnet") → 讀取 `agents/researchers/bear_researcher.md` + bull 論點。使用 `model="sonnet"`。
- **research-judge-{symbol}** (等 bear 完成, Opus 預設) → 讀取 `agents/researchers/research_judge.md` + 完整辯論紀錄。不指定 model，使用預設 Opus。
  → 裁決 BUY/SELL/HOLD + score_adjustment (-0.5 ~ +0.5)

**[Lead]** 合併辯論結果：
```python
from src.agents_launcher import task_merge_debates
candidates = task_merge_debates(candidates)
```

---

## Phase 3 (Risk Manager 硬性規則, 等 Phase 2.5 完成)
**[Subagent, model="haiku"]** 讀取 `agents/risk_mgmt/risk_manager.md`，附加輸入參數 `candidates = Decision Engine 的候選列表` 到 prompt 末尾，用 Task tool spawn 執行。使用 `model="haiku"`。

---

## Phase 4 (Execution, 等 Phase 3 完成)
**[Subagent, model="haiku"]** 讀取 `agents/trader/executor.md`，附加輸入參數 `assessed = 風控評估後的交易列表` 到 prompt 末尾，用 Task tool spawn 執行。使用 `model="haiku"`。

---

## Phase 5 (Report)
**[Subagent, model="haiku"]** 讀取 `agents/reporting/reporter.md` 完整內容，用 Task tool spawn 執行。使用 `model="haiku"`。

---

## Phase 6 (EOD Review, 等 Phase 5 完成)
**[Subagent, model="sonnet"]** 讀取 `agents/strategic/eod_review.md` 完整內容，用 Task tool spawn 執行。使用 `model="sonnet"`。
或者 Lead 直接呼叫：
```python
from src.agents_launcher import task_eod_review
eod_result = task_eod_review()
```
輸出：`shared_state/YYYY-MM-DD/eod_review.json`（P&L 歸因、論點漂移警報、觀察性洞察）
注意：EOD 輸出是**觀察**而非**指令**，避免循環推理。明日 CIO 讀取時自帶信心衰減。

---

## Phase 7 (Reflection & Memory Update)

**[Lead]** 檢查未反思的交易：
```python
from src.agents_launcher import task_check_reflections, task_prepare_reflection, task_save_reflection_results
unreflected = task_check_reflections()
for trade_record in unreflected:
    task_prepare_reflection(trade_record)
```

**[Teammates]** 對每筆需反思的交易 spawn：
- **reflection-analyst-{trade_id}** (Opus 預設) → 讀取 `agents/reflection/reflection_analyst.md` + `shared_state/reflection_context_{trade_id}.json`。不指定 model，使用預設 Opus。

**[Lead]** 儲存反思結果到記憶庫：
```python
for trade_record in unreflected:
    trade_id = trade_record.get('order_id', 'unknown')
    task_save_reflection_results(trade_id)
```

---

最後匯報所有結果給我，包括：
- 辯論摘要（各候選的 Bull/Bear 核心論點和 Judge 裁決）
- 已下單的交易明細
- 反思結果（如有）
"""


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Agent Teams Launcher")
    parser.add_argument("--run", action="store_true", help="Run full pipeline once")
    parser.add_argument("--trade", action="store_true", help="Enable trade execution")
    parser.add_argument("--notify", action="store_true", help="Send Telegram notifications")
    parser.add_argument("--prompt", action="store_true", help="Print Agent Teams launch prompt")
    parser.add_argument("--test-telegram", action="store_true", help="Test Telegram connection")
    args = parser.parse_args()

    if args.prompt:
        from src.team_orchestrator import build_team_prompt
        print(build_team_prompt(
            execute=args.trade,
            notify=args.notify if hasattr(args, "notify") else True,
        ))
    elif args.test_telegram:
        notifier = TelegramNotifier()
        notifier.test_connection()
    elif args.run:
        run_full_pipeline(execute=args.trade, notify=args.notify)
    else:
        print("Usage:")
        print("  python -m src.agents_launcher --run                  # Run pipeline once (one-shot)")
        print("  python -m src.agents_launcher --run --trade          # Run + execute trades")
        print("  python -m src.agents_launcher --run --trade --notify # Run + execute + Telegram")
        print("  python -m src.agents_launcher --prompt               # Show Agent Teams launch prompt")
        print("  python -m src.agents_launcher --test-telegram        # Test Telegram")
