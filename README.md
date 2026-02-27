# Finance Agent Team

Multi-agent trading system built on Alpaca API, using a **momentum/trend-following** strategy. Each agent handles a specialized role in the pipeline, communicating via shared JSON state files.

Supports both **paper trading** and **live trading**.

## Architecture

```
Phase 0:   Symbol Screener           (dynamic watchlist mode only)
Phase 1:   Market + Technical + Sentiment Analyst  (parallelizable)
Phase 1.5: Position Exit Reviewer    (evaluates existing positions for close)
Phase 1.8: Market Regime Detection   (SPY EMA alignment → risk_on/risk_off/neutral)
Phase 2:   Decision Engine           (confidence-weighted composite scoring)
Phase 2.5: Investment Debate         (Bull/Bear/Judge; Agent Teams only)
Phase 3:   Risk Manager              (veto power, kill switch)
Phase 3.5: Risk Debate               (Aggressive/Conservative/Neutral/Judge; Agent Teams only)
Phase 4:   Executor                  (exits first, then new entries)
Phase 5:   Reporter                  (Telegram notifications)
Phase 6:   Reflection                (post-trade learning; Agent Teams only)
```

The system runs in **one-shot mode** — execute once per invocation, no continuous monitoring or scheduler.

Two execution modes:
- **Standalone mode** (`--run`): Pure rule-based pipeline; debate/reflection phases are skipped
- **Agent Teams mode**: Full pipeline with investment debate, risk debate, and reflection (requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true`)

## Setup

### 1. Install Dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure API Keys

```bash
cp .env.example config/.env
```

Edit `config/.env` with your credentials:

- **Alpaca API** (required) — Get keys at [app.alpaca.markets](https://app.alpaca.markets). Paper trading requires no real money.
- **Telegram** (optional) — For trade notifications. Create a bot via [@BotFather](https://t.me/BotFather).
- **Finnhub / NewsAPI** (optional) — For enhanced sentiment analysis.

### 3. Configure Strategy

Edit `config/settings.yaml` to adjust:

- `watchlist_mode`: `dynamic` (screener selects symbols) or `static` (use predefined list)
- `scoring`: weights for each analyst agent
- `decision`: score thresholds for buy/sell signals
- `risk`: position sizing, exposure limits, kill switch, max drawdown
- `position_exit`: exit score threshold, ATR trailing stop multiplier
- `debate`: top_n candidates, investment/risk debate rounds
- `memory`: BM25 memory storage directory, max entries

## Usage

All commands must be run from the **project root**.

```bash
# Analysis only (no trades)
python -m src.orchestrator

# Analysis + execute trades (paper)
python -m src.orchestrator --trade

# Full pipeline via agents launcher
python -m src.agents_launcher --run
python -m src.agents_launcher --run --trade
python -m src.agents_launcher --run --trade --notify

# Test Telegram connection
python -m src.agents_launcher --test-telegram
```

### Claude Code Agent Teams Mode

The system can also run as a [Claude Code Agent Team](https://docs.anthropic.com/en/docs/claude-code), where each agent runs as a separate Claude Code teammate:

```bash
export CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=true
claude

# Inside Claude Code, generate the launch prompt:
python -m src.agents_launcher --prompt
```

In Agent Teams mode, subagent specs (`agents/*.md`) are self-contained — they include role description, scoring logic, execution code, and I/O schema. The lead agent reads a spec file and uses it directly as the Task tool prompt.

## Project Structure

```
src/
  orchestrator.py           # Main pipeline orchestrator
  agents_launcher.py        # Standalone pipeline + Agent Teams launcher
  alpaca_client.py          # Alpaca API wrapper (market data, orders, positions)
  analysis/
    screener.py             # Symbol screener (Phase 0)
    technical.py            # Technical indicators & momentum scoring
    sentiment.py            # News sentiment analysis (VADER)
    fundamentals.py         # Fundamental data via yfinance
    position_reviewer.py    # Existing position exit evaluation
  risk/
    manager.py              # Risk validation, position sizing, kill switch
  notifications/
    telegram.py             # Telegram bot notifications
  memory/
    situation_memory.py     # BM25 lexical similarity memory banks
    reflection.py           # Reflection helpers & lesson extraction
  debate/
    helpers.py              # Debate context preparation & merge functions
agents/
  analysts/                 # Phase 0-1 data collection agents
  researchers/              # Phase 2.5 investment debate (Bull/Bear/Judge)
  risk_mgmt/                # Phase 3-3.5 risk assessment & debate
  trader/                   # Phase 1.5, 2, 4 position management & execution
  reporting/                # Phase 5 notifications
  reflection/               # Phase 6 post-trade learning
config/
  settings.yaml             # Strategy & risk configuration
  .env                      # API keys (not tracked)
shared_state/               # Inter-agent JSON communication (not tracked)
memory_store/               # BM25 memory JSON files (not tracked)
logs/                       # Trade logs (not tracked)
```
