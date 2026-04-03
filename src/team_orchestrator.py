"""
Team Orchestrator - Programmatic Agent Teams Pipeline

Replaces the manual AGENT_TEAMS_PROMPT with a structured orchestration
module. CIO is the Lead agent (D-01). Teammates are spawned in phased
groups (D-02) and shut down after completion.

Usage:
    python -m src.team_orchestrator          # Generate team prompt
    python -m src.team_orchestrator --run     # Run via standalone fallback
"""

import json
import sys
import argparse
from pathlib import Path
from datetime import datetime

import yaml

# Ensure project root in path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.state_dir import get_state_dir


def load_model_tiers() -> dict:
    """Load model tier assignments from settings.yaml."""
    config_path = Path("config/settings.yaml")
    if config_path.exists():
        with open(config_path) as f:
            cfg = yaml.safe_load(f)
        return cfg.get("model_tiers", {})
    return {}


def load_agent_spec(spec_path: str) -> str:
    """Load an agent specification file."""
    path = Path(spec_path)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return f"[Agent spec not found: {spec_path}]"


def build_team_prompt(execute: bool = False, notify: bool = True) -> str:
    """Build the complete orchestration prompt for the CIO Lead agent.

    This prompt is what the Lead agent reads to know how to orchestrate
    the full pipeline via TeamCreate + SendMessage.

    Args:
        execute: Whether to enable trade execution (--trade flag).
        notify: Whether to enable Telegram notifications.

    Returns:
        Complete orchestration prompt string for the CIO Lead agent.
    """
    model_tiers = load_model_tiers()
    state_dir = get_state_dir()
    today = datetime.now().strftime("%Y-%m-%d")

    # Load CIO spec for Lead's decision logic
    cio_spec = load_agent_spec("agents/strategic/cio.md")

    prompt = f"""# Agent Teams Pipeline -- {today}

你是 **CIO (首席投資官)**，同時也是這個交易團隊的 Lead Agent。
你負責：(1) 制定每日交易方針，(2) 管理整個交易團隊的生命週期。

## 你的 CIO 決策邏輯

{cio_spec}

## 團隊管理協議

使用 TeamCreate 建立團隊後，依照以下 Phase Group 依序執行。
每個 Phase Group 完成後，**關閉所有該組 teammates 再啟動下一組**（D-02 分階段生成）。

### Phase Group 1: 宏觀數據收集
1. 生成 Macro Strategist teammate (model: {model_tiers.get('macro-strategist', 'sonnet')})
   - 指令: 讀取 agents/strategic/macro_strategist.md 並執行
   - 執行: `from src.agents_launcher import task_macro_strategist; result = task_macro_strategist()`
   - 等待 SendMessage 確認完成
   - 完成後關閉此 teammate

2. 執行 CIO 決策 (Lead direct -- 你自己執行):
   - 執行: `from src.agents_launcher import task_cio_directive; result = task_cio_directive()`
   - 讀取結果: `daily_directive.json`
   - 如果 result["halt_trading"] == True: 跳至 Phase Group 5 (EOD Review)

### Phase Group 2: 分析師 (平行, D-11)
生成以下 teammates (平行執行):

- Symbol Screener (model: {model_tiers.get('symbol-screener', 'haiku')}):
  `from src.agents_launcher import task_symbol_screener; result = task_symbol_screener()`
- Market Analyst (model: {model_tiers.get('market-analyst', 'haiku')}):
  `from src.agents_launcher import task_market_analyst; result = task_market_analyst()`
- Technical Analyst (model: {model_tiers.get('technical-analyst', 'haiku')}):
  `from src.agents_launcher import task_technical_analyst; result = task_technical_analyst()`
- Sentiment Analyst (model: {model_tiers.get('sentiment-analyst', 'haiku')}):
  `from src.agents_launcher import task_sentiment_analyst; result = task_sentiment_analyst()`

等待全部完成，然後關閉所有分析師 teammates。

### Phase Group 2.5: Position Review + Decision Engine
- Position Reviewer (model: {model_tiers.get('position-reviewer', 'haiku')}):
  `from src.agents_launcher import task_position_review; result = task_position_review()`
  完成後關閉此 teammate。

- Decision Engine (Lead direct -- 你自己執行):
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

### Phase Group 3: Investment Debate (Top-N candidates)
對每個候選標的:

1. **Sector Intelligence** (Lead直接執行):
   ```python
   from src.agents_launcher import task_sector_specialist
   sector_data = task_sector_specialist(symbol)
   ```
   行業情報包含供應鏈動態、板塊輪動信號、競爭格局，將寫入 debate_context。

2. **Debate Prep + Bull/Bear/Judge**:
   生成 3 個 teammates:
   - Bull Researcher (model: {model_tiers.get('bull-researcher', 'sonnet')})
   - Bear Researcher (model: {model_tiers.get('bear-researcher', 'sonnet')})
   - Research Judge (model: {model_tiers.get('research-judge', 'opus')})

辯論流程:
```python
from src.agents_launcher import task_sector_specialist, task_prepare_debate, task_merge_debates
# 為每個候選標的準備行業情報 + 辯論上下文
for symbol in top_candidates:
    sector_data = task_sector_specialist(symbol)  # 行業情報 (Lead直接)
    context = task_prepare_debate(symbol)           # 辯論上下文 (包含 sector_intelligence)
    # Bull/Bear/Judge teammates 執行辯論
    # ...
# 合併辯論結果
merged = task_merge_debates(candidates)
```

辯論完成後關閉所有辯論 teammates。

### Phase Group 4: Risk + Portfolio Optimization + Execution
- Risk Manager (model: {model_tiers.get('risk-manager', 'haiku')}):
  `from src.agents_launcher import task_risk_manager; assessed = task_risk_manager(candidates)`
  **Risk Manager 失敗 = 硬停止，不執行任何交易 (D-12)**
  完成後關閉此 teammate。

- Portfolio Strategist (model: {model_tiers.get('portfolio-strategist', 'sonnet')}):
  `from src.agents_launcher import task_portfolio_strategist; assessed = task_portfolio_strategist(assessed)`
  讀取: Risk Manager 的 assessed trades + 現有 Alpaca 持倉
  寫入: `{state_dir}/portfolio_construction.json`
  Portfolio Strategist 失敗 **不是** 硬停止 -- 繼續使用 risk-assessed trades (D-12)
  完成後關閉此 teammate。

- Execution Strategist (Lead直接執行):
  `from src.execution.strategist import task_execution_strategist; assessed = task_execution_strategist(assessed)`
  讀取: `technical_signals.json`, `market_overview.json`
  寫入: `{state_dir}/execution_plan.json`
  根據波動率和流動性為每筆交易推薦訂單類型 (market/limit/bracket)。
  Execution Strategist 失敗 **不是** 硬停止 -- Executor 使用預設 bracket 訂單 (D-12)

{"- Executor (model: " + model_tiers.get('executor', 'haiku') + "):" if execute else "- [執行已跳過 -- 分析模式]"}
{"  `from src.agents_launcher import task_execute_trades, task_execute_exits; task_execute_exits(exit_candidates); task_execute_trades(assessed)`" if execute else ""}
{"  完成後關閉此 teammate。" if execute else ""}

### Phase Group 5: 報告 + 盤後檢視 (平行, D-11)
生成以下 teammates (平行執行):

- Reporter (model: {model_tiers.get('reporter', 'haiku')}):
  `from src.agents_launcher import task_send_report; task_send_report()`
  {"(Telegram 通知已啟用)" if notify else "(Telegram 通知已停用)"}
- EOD Review (model: {model_tiers.get('eod-review', 'sonnet')}):
  讀取 agents/strategic/eod_review.md 並執行
  `from src.agents_launcher import task_eod_review; result = task_eod_review()`
- Reflection (如有已關閉交易需要反思):
  ```python
  from src.agents_launcher import task_check_reflections, task_prepare_reflection, task_save_reflection_results
  trades = task_check_reflections()
  for trade in trades:
      context = task_prepare_reflection(trade)
      # Reflection teammate 執行分析
      task_save_reflection_results(trade["id"])
  ```

完成後關閉所有 teammates 並結束團隊。

## 通訊協議 (D-09)

- **SendMessage**: 用於協調 (任務完成通知、依賴觸發、辯論輪次)
- **shared_state JSON**: 用於結構化數據 (信號、分數、指令)
- 所有 JSON 文件位於: `{state_dir}/`

## 容錯處理 (D-12)

| 失敗組件 | 處理方式 |
|---------|---------|
| Macro Strategist 失敗 | CIO 在沒有宏觀數據的情況下決策 |
| CIO 失敗 | 使用預設方針 (neutral, multiplier=1.0) |
| 分析師失敗 | 跳過該分析師，繼續 |
| Risk Manager 失敗 | **硬停止**，不執行任何交易 |
| Portfolio Strategist 失敗 | 繼續使用 risk-assessed trades（無相關性優化） |
| Reporter/EOD/Reflection 失敗 | 跳過，pipeline 仍算成功 |

## 執行模式

- 交易執行: {'啟用 (--trade)' if execute else '停用 (分析模式)'}
- 通知: {'啟用' if notify else '停用'}

## 最終匯報

完成所有 Phase Group 後，匯報:
- 宏觀展望摘要
- CIO 交易立場與風險預算
- 各分析師信號摘要
- 辯論結果（如有）
- 已下單的交易明細（如有）
- EOD 檢視摘要
- 反思結果（如有）
"""
    return prompt


def run_agent_teams_pipeline(execute: bool = False, notify: bool = True) -> str:
    """Entry point for Agent Teams mode.

    Prints the orchestration prompt for the CIO Lead agent.
    In a fully automated setup, this would be passed to Claude Code
    programmatically via the CLI.

    Args:
        execute: Whether to enable trade execution.
        notify: Whether to enable Telegram notifications.

    Returns:
        The generated orchestration prompt string.
    """
    prompt = build_team_prompt(execute=execute, notify=notify)
    print(prompt)
    return prompt


def run_standalone_fallback(execute: bool = False, notify: bool = True) -> None:
    """Fallback to standalone mode (D-03).

    Calls run_full_pipeline() directly without Agent Teams orchestration.
    """
    from src.agents_launcher import run_full_pipeline
    run_full_pipeline(execute=execute, notify=notify)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agent Teams Pipeline Orchestrator")
    parser.add_argument("--run", action="store_true", help="Run via standalone fallback")
    parser.add_argument("--trade", action="store_true", help="Enable trade execution")
    parser.add_argument("--notify", action="store_true", default=True, help="Enable notifications")
    parser.add_argument("--prompt", action="store_true", help="Print Agent Teams prompt")
    args = parser.parse_args()

    if args.run:
        run_standalone_fallback(execute=args.trade, notify=args.notify)
    else:
        # Default: print the Agent Teams orchestration prompt
        run_agent_teams_pipeline(execute=args.trade, notify=args.notify)
