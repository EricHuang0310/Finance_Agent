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
from datetime import datetime
from pathlib import Path

# Ensure project root is in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.alpaca_client import AlpacaClient
from src.orchestrator import TradingOrchestrator
from src.notifications.telegram import TelegramNotifier
from src.debate.helpers import (
    task_prepare_debate_context,
    task_prepare_risk_context,
    task_merge_debate_results,
    task_merge_risk_debate_results,
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

def task_symbol_screener() -> dict:
    """Task for Symbol Screener agent. Discovers symbols dynamically."""
    print("🔎 [Symbol Screener] Starting market screening...")
    orch = get_orchestrator()
    result = orch.run_symbol_screener()
    print(f"🔎 [Symbol Screener] ✅ Complete: {len(result['stocks'])} stocks, {len(result['crypto'])} crypto")
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
    tech_path = Path("shared_state/technical_signals.json")
    market_path = Path("shared_state/market_overview.json")
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
            close_side = "sell" if candidate["side"] == "long" else "buy"
            print(f"  📤 Closing {candidate['symbol']} ({candidate['side']}): "
                  f"qty={candidate['qty']} @ ~${candidate['current_price']:.2f}")

            result = orch.client.place_market_order(
                symbol=candidate["symbol"],
                qty=candidate["qty"],
                side=close_side,
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
                "side": close_side,
                "suggested_qty": candidate["qty"],
                "entry_price": candidate["current_price"],
                "composite_score": candidate.get("exit_score", 0),
                "action": "close_position",
                "exit_reason": candidate["exit_reason"],
            }, result)

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


def task_generate_decisions(tech_signals: dict, sentiment: dict, market_data: dict = None) -> list[dict]:
    """Generate trade decisions from aggregated signals."""
    print("🧠 [Decision Engine] Aggregating signals...")
    orch = get_orchestrator()
    candidates = orch.generate_trade_plan(tech_signals, sentiment, market_data)
    print(f"🧠 [Decision Engine] ✅ Generated {len(candidates)} candidates")
    return candidates


def task_execute_trades(assessed: list[dict]) -> list[dict]:
    """Task for Executor agent. Places orders for approved trades."""
    print("⚡ [Executor] Starting order execution...")
    orch = get_orchestrator()
    notifier = TelegramNotifier()

    approved = [t for t in assessed if t.get("approved")]
    executed = []

    if not approved:
        print("⚡ [Executor] 📭 No approved trades to execute.")
        return []

    # Market hours check
    try:
        clock = orch.client.is_market_open()
        if not clock["is_open"]:
            has_stock_trades = any(t.get("asset_type") != "crypto" for t in approved)
            if has_stock_trades:
                print(f"  ⚠️  Market closed. Stock orders will queue. Next open: {clock['next_open']}")
    except Exception:
        pass

    for trade in approved:
        try:
            side_emoji = "🟢 BUY" if trade["side"] == "buy" else "🔴 SELL"
            print(f"  📋 Placing order: {side_emoji} {trade['symbol']} "
                  f"x{trade['suggested_qty']} @ ~${trade['entry_price']:.2f}")

            if trade.get("stop_loss") and trade.get("take_profit"):
                result = orch.client.place_bracket_order(
                    symbol=trade["symbol"],
                    qty=trade["suggested_qty"],
                    side=trade["side"],
                    stop_loss_price=trade["stop_loss"],
                    take_profit_price=trade["take_profit"],
                )
            else:
                result = orch.client.place_market_order(
                    symbol=trade["symbol"],
                    qty=trade["suggested_qty"],
                    side=trade["side"],
                )

            trade["order_id"] = result["id"]
            trade["order_status"] = result["status"]
            executed.append(trade)
            print(f"  ✅ Order placed: {result['id']} | Status: {result['status']}")

            # Log trade
            orch._log_trade(trade, result)

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
    state_dir = Path("shared_state")
    state_dir.mkdir(exist_ok=True)
    with open(state_dir / "execution_results.json", "w") as f:
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
    decisions_path = Path("shared_state/decisions.json")
    if decisions_path.exists():
        with open(decisions_path) as f:
            decisions = json.load(f)

        candidates = decisions.get("candidates", [])
        risk_path = Path("shared_state/risk_assessment.json")
        if risk_path.exists():
            with open(risk_path) as f:
                risk_data = json.load(f)

            approved = [a for a in risk_data.get("assessments", []) if a.get("approved")]
            rejected = [a for a in risk_data.get("assessments", []) if not a.get("approved")]
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


def task_prepare_risk_debate(trade: dict) -> dict:
    """Prepare risk debate context for a single approved trade."""
    symbol = trade.get("symbol", "")
    print(f"📝 [Risk Debate Prep] Assembling context for {symbol}...")
    orch = get_orchestrator()
    context = task_prepare_risk_context(trade, orch)
    print(f"📝 [Risk Debate Prep] ✅ Context saved to shared_state/risk_debate_context_{symbol}.json")
    return context


def task_merge_risk_debates(trades: list[dict]) -> list[dict]:
    """Merge risk debate qty_ratio and adjusted stop/target into trades."""
    print("🔀 [Risk Debate Merge] Merging risk debate results...")
    result = task_merge_risk_debate_results(trades)
    print(f"🔀 [Risk Debate Merge] ✅ Merged {len(result)} trades")
    return result


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
    approved = [t for t in assessed if t.get("approved")]
    rejected = [t for t in assessed if not t.get("approved")]

    # Phase 3.5: Risk Debate skipped in standalone mode
    print("  ℹ️  Standalone mode: Risk Debate (Phase 3.5) skipped — use Agent Teams for debate")

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

    return assessed


# ══════════════════════════════════════════════
# Agent Teams Launch Prompt
# ══════════════════════════════════════════════

AGENT_TEAMS_PROMPT = """
# ─── Copy this into Claude Code after enabling Agent Teams ───

啟動一個 trading-analysis agent team 來分析市場並生成交易建議。
此 pipeline 包含投資辯論和風控辯論環節，模擬真實投資團隊的決策流程。

---

## Phase 0 (Symbol Discovery, 如果 watchlist_mode == "dynamic")
先執行 Symbol Screener 來自動篩選標的：

0. **symbol-screener** - 讀取 agents/symbol_screener.md 的指令，
   然後執行:
   ```python
   from src.agents_launcher import task_symbol_screener
   result = task_symbol_screener()
   # result 寫入 shared_state/dynamic_watchlist.json
   ```

---

## Phase 1 (Parallel Analysts, 等 Phase 0 完成)
同時 spawn 以下 3 個 agents：

1. **market-analyst** - 讀取 agents/market_analyst.md，執行:
   ```python
   from src.agents_launcher import task_market_analyst
   task_market_analyst()
   # 包含 Market Regime Detection (SPY EMA alignment)
   # 結果寫入 shared_state/market_overview.json（含 market_regime 欄位）
   ```

2. **tech-analyst** - 讀取 agents/technical_analyst.md，執行:
   ```python
   from src.agents_launcher import task_technical_analyst
   task_technical_analyst()
   # 結果含 confidence 信心度 (0.0-1.0)
   ```

3. **sentiment-analyst** - 執行:
   ```python
   from src.agents_launcher import task_sentiment_analyst
   task_sentiment_analyst()
   # 結果含 confidence 信心度 (基於新聞數量)
   ```

---

## Phase 1.5 (Position Exit Review, 等 Phase 1 全部完成)

4. **position-reviewer** - 讀取 agents/position_reviewer.md，執行:
   ```python
   from src.agents_launcher import task_position_review
   exit_candidates = task_position_review()
   # 如有需要平倉的持倉：
   if exit_candidates:
       from src.agents_launcher import task_execute_exits
       task_execute_exits(exit_candidates)
   ```

---

## Phase 2 (Decision Engine, 等 Phase 1.5 完成)

5. 我 (Lead) 執行 Decision Engine（含 confidence 加權 + regime 動態權重）：
   ```python
   from src.agents_launcher import task_generate_decisions
   import json
   with open('shared_state/technical_signals.json') as f:
       tech = json.load(f)
   with open('shared_state/sentiment_signals.json') as f:
       sent = json.load(f)
   with open('shared_state/market_overview.json') as f:
       market = json.load(f)
   candidates = task_generate_decisions(tech, sent, market)
   ```

---

## Phase 2.5 (Fundamentals + Investment Debate, 取 Top-N 候選)

6. 我 (Lead) 為 Top-N 候選取得基本面資料：
   ```python
   from src.agents_launcher import task_fundamentals_analyst, task_prepare_debate
   import yaml
   with open('config/settings.yaml') as f:
       cfg = yaml.safe_load(f)
   top_n = cfg.get('debate', {}).get('top_n', 3)
   top_symbols = [c['symbol'] for c in candidates[:top_n]]
   task_fundamentals_analyst(top_symbols)
   ```

7. 我 (Lead) 為每個 Top-N 候選準備辯論上下文：
   ```python
   for symbol in top_symbols:
       task_prepare_debate(symbol)
   ```

### 投資辯論（對每個 Top-N 候選，可並行）

對每個候選 symbol，依序 spawn 以下 teammates：

8a. **bull-researcher-{symbol}** - 讀取 agents/bull_researcher.md
    → 讀取 shared_state/debate_context_{symbol}.json
    → 用 Claude 推理寫出看多論點
    → 寫入 shared_state/debate_{symbol}_bull_r1.json

8b. **bear-researcher-{symbol}** (等 bull 完成)
    → 讀取 agents/bear_researcher.md + bull 論點
    → 用 Claude 推理寫出看空論點 + 反駁
    → 寫入 shared_state/debate_{symbol}_bear_r1.json

8c. **research-judge-{symbol}** (等 bear 完成)
    → 讀取 agents/research_judge.md + 完整辯論紀錄
    → 裁決 BUY/SELL/HOLD + score_adjustment (-0.5 ~ +0.5)
    → 寫入 shared_state/debate_{symbol}_result.json

9. 我 (Lead) 合併辯論結果：
   ```python
   from src.agents_launcher import task_merge_debates
   candidates = task_merge_debates(candidates)
   ```

---

## Phase 3 (Risk Manager 硬性規則, 等 Phase 2.5 完成)

10. **risk-manager** - 讀取 agents/risk_manager.md，對候選執行硬性風控驗證:
    ```python
    from src.agents_launcher import task_risk_manager
    assessed = task_risk_manager(candidates)
    approved = [t for t in assessed if t.get('approved')]
    ```

---

## Phase 3.5 (Risk Debate, 對每筆通過硬規則的交易)

11. 我 (Lead) 為每筆 approved 交易準備風控辯論上下文：
    ```python
    from src.agents_launcher import task_prepare_risk_debate
    for trade in approved:
        task_prepare_risk_debate(trade)
    ```

### 風控辯論（對每筆 approved 交易，可並行）

12a. **aggressive-analyst-{symbol}** - 讀取 agents/aggressive_analyst.md
     → 讀取 shared_state/risk_debate_context_{symbol}.json
     → 主張接受較高風險，強調機會成本
     → 寫入 shared_state/risk_debate_{symbol}_aggressive.json

12b. **conservative-analyst-{symbol}** (等 aggressive 完成)
     → 讀取 agents/conservative_analyst.md + aggressive 論點
     → 主張縮減曝險，強調下行風險
     → 寫入 shared_state/risk_debate_{symbol}_conservative.json

12c. **neutral-analyst-{symbol}** (等 conservative 完成)
     → 讀取 agents/neutral_analyst.md + aggressive + conservative 論點
     → 提出平衡觀點
     → 寫入 shared_state/risk_debate_{symbol}_neutral.json

12d. **risk-judge-{symbol}** (等 neutral 完成)
     → 讀取 agents/risk_judge.md + 三方辯論紀錄
     → 裁決最終 qty_ratio (0.5~1.0) + 調整 stop_loss / take_profit
     → 寫入 shared_state/risk_debate_{symbol}_result.json

13. 我 (Lead) 合併風控辯論結果：
    ```python
    from src.agents_launcher import task_merge_risk_debates
    approved = task_merge_risk_debates(approved)
    ```

---

## Phase 4 (Execution, 等 Phase 3.5 完成)

14. **executor** - 讀取 agents/executor.md，下單:
    ```python
    from src.agents_launcher import task_execute_trades
    executed = task_execute_trades(approved)
    ```

---

## Phase 5 (Report)

15. 發送 Telegram 通知（含辯論摘要）:
    ```python
    from src.agents_launcher import task_send_report
    task_send_report()
    ```

---

## Phase 6 (Reflection & Memory Update)

16. 我 (Lead) 檢查是否有已平倉但尚未反思的交易：
    ```python
    from src.agents_launcher import task_check_reflections, task_prepare_reflection, task_save_reflection_results
    unreflected = task_check_reflections()
    ```

17. 對每筆需反思的交易 spawn **reflection-analyst**：
    ```python
    for trade_record in unreflected:
        task_prepare_reflection(trade_record)
    ```

    17a. **reflection-analyst-{trade_id}** - 讀取 agents/reflection_analyst.md
         → 讀取 shared_state/reflection_context_{trade_id}.json
         → 分析決策正確性、萃取教訓
         → 寫入 shared_state/reflection_{trade_id}_result.json

18. 我 (Lead) 儲存反思結果到記憶庫：
    ```python
    for trade_record in unreflected:
        trade_id = trade_record.get('order_id', 'unknown')
        task_save_reflection_results(trade_id)
    ```

---

最後匯報所有結果給我，包括：
- 辯論摘要（各候選的 Bull/Bear 核心論點和 Judge 裁決）
- 風控辯論摘要（各交易的倉位調整和理由）
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
        print(AGENT_TEAMS_PROMPT)
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
