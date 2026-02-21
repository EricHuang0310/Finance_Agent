# Finance Agent Team

Multi-agent trading system built on Alpaca API, using a **momentum/trend-following** strategy. Each agent handles a specialized role in the pipeline, communicating via shared JSON state files.

Supports both **paper trading** and **live trading**.

## Architecture

```
Phase 0:   Symbol Screener         (dynamic watchlist mode only)
Phase 1:   Market Analyst + Technical Analyst + Sentiment Analyst  (parallelizable)
Phase 1.5: Position Exit Reviewer  (evaluates existing positions for close)
Phase 2:   Decision Engine         (composite scoring)
Phase 3:   Risk Manager            (veto power)
Phase 4:   Executor                (exits first, then new entries)
Phase 5:   Reporter                (Telegram notifications)
```

The system runs in **one-shot mode** — execute once per invocation, no continuous monitoring or scheduler.

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
    position_reviewer.py    # Existing position exit evaluation
  risk/
    manager.py              # Risk validation, position sizing, kill switch
  notifications/
    telegram.py             # Telegram bot notifications
agents/                     # Agent specification docs (Chinese)
config/
  settings.yaml             # Strategy & risk configuration
  .env                      # API keys (not tracked)
shared_state/               # Inter-agent JSON communication (not tracked)
logs/                       # Trade logs (not tracked)
```
