# Phase 1: Strategic Oversight & Agent Teams Foundation - Research

**Researched:** 2026-03-30
**Domain:** Claude Code Agent Teams orchestration, trading desk strategic oversight agents, memory concurrency
**Confidence:** MEDIUM-HIGH

## Summary

This phase transforms the existing trading pipeline from a prompt-pasted Agent Teams workflow into a programmatic TeamCreate-based orchestration, adds three new strategic roles (CIO, Macro Strategist, EOD Review Analyst), and fixes two memory/concurrency bugs. The core technical challenge is replacing the `AGENT_TEAMS_PROMPT` text blob in `agents_launcher.py` with a Python-driven orchestration layer that uses Claude Code's TeamCreate + SendMessage + shared task list APIs.

The existing codebase has strong foundations: 15+ `task_*()` functions that work as callable units, a proven `shared_state/YYYY-MM-DD/` JSON communication pattern, and 12 agent specs in Chinese that follow a consistent format. The three new roles (CIO, Macro Strategist, EOD Review) each produce a new JSON file that bookends the existing pipeline -- Macro and CIO run before everything else, EOD Review runs after. The CIO's `risk_budget_multiplier` integrates into the Decision Engine's scoring formula at a single, well-defined point (`orchestrator.py:generate_trade_plan()`).

The memory fixes (MEM-01, MEM-04) are straightforward: replace `except (json.JSONDecodeError, KeyError): pass` with proper error logging + backup file rotation (MEM-01), and add `filelock` around the trade log read-modify-write cycle (MEM-04). Both are isolated changes with no ripple effects.

**Primary recommendation:** Build a `src/team_orchestrator.py` module that programmatically creates a team, spawns teammates in phased groups (3-5 at a time per D-02), and coordinates via SendMessage + shared_state JSON files. The CIO agent is the Team Lead. New agent specs follow the existing Chinese-language pattern in `agents/` with execution code + I/O schema embedded.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Single team per daily run via TeamCreate. CIO agent is the Lead that orchestrates all phases, spawns and shuts down teammates as needed. Human monitors but does not intervene.
- **D-02:** Phased spawning: spawn 3-5 teammates per phase group (e.g., analysts together, then debaters), keeping active teammate count low to save tokens. Shut down completed teammates before spawning next group.
- **D-03:** Keep standalone mode (`run_full_pipeline()`) as fallback for quick tests or when Agent Teams is unavailable. Agent Teams is the default execution mode.
- **D-04:** CIO scope is narrow: sets trading stance (aggressive/neutral/defensive) and risk_budget_multiplier. Does NOT veto individual trades -- that remains Risk Manager's job. Prevents compound rejection problem.
- **D-05:** CIO reads macro_outlook.json + market regime + yesterday's eod_review.json to decide stance. Cross-asset signals and recent performance inform the decision.
- **D-06:** CIO goes live from day 1 (no shadow mode). Faster feedback loop. If stance distribution is skewed after 2 weeks, prompt will be adjusted.
- **D-07:** All agent specs stay in Chinese for consistency. New roles (CIO, Macro Strategist, EOD Review) are also written in Chinese.
- **D-08:** Agent specs remain in existing `agents/` directory structure. No migration to `.claude/agents/`. Specs are project-specific and self-contained with execution code, I/O schema, and role descriptions.
- **D-09:** Hybrid communication: SendMessage for coordination (task completion, dependency triggers, debate turn-taking). JSON files in `shared_state/` for structured data (signals, scores, directives, debate arguments). Preserves auditability and standalone compatibility.
- **D-10:** Pre-market layer runs first: Macro Strategist -> CIO Directive -> then existing pipeline (Screener -> Analysts -> Debate -> Risk -> Execute -> Report -> EOD Review). New roles bookend the existing flow.
- **D-11:** Parallel groups: Group 1 (Macro data collection), Group 2 (Market/Tech/Sentiment analysts), Group 3 (Reporter + EOD Review + Reflection post-execution). All other phases are sequential.
- **D-12:** Graceful degradation: Only Risk Manager failure is a hard stop (veto power). All other teammate failures skip that phase and continue. E.g., if Macro Strategist fails, CIO decides without macro data.

### Claude's Discretion
- Model tier assignment per specific agent (within the Opus/Sonnet/Haiku framework from TEAMS-03)
- Exact JSON schema for daily_directive.json, macro_outlook.json, eod_review.json
- How to wire CIO's risk_budget_multiplier into existing Decision Engine scoring
- Memory corruption fix approach (MEM-01) and trade log race condition fix (MEM-04)
- EOD Review confidence decay implementation details (MEM-05)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| TEAMS-01 | Pipeline runs via TeamCreate with persistent teammates | Team orchestrator module replaces AGENT_TEAMS_PROMPT; CIO as Lead creates team, spawns/shuts down teammates per phase group |
| TEAMS-02 | Each agent role has a spec with model tier and permissions | Existing `agents/*.md` pattern extended with YAML frontmatter for model tier; new specs for CIO, Macro, EOD Review |
| TEAMS-03 | Tiered model assignment (Opus/Sonnet/Haiku) per role | Model tier map defined per role; subagent definitions can specify model |
| TEAMS-04 | Team lifecycle managed programmatically | `src/team_orchestrator.py` handles spawn, SendMessage coordination, shutdown per phase group |
| TEAMS-05 | Dual communication: SendMessage + shared_state JSON | SendMessage for coordination signals; JSON files for structured data; both patterns documented |
| CIO-01 | CIO produces daily_directive.json with stance + risk_budget_multiplier | CIO agent spec + task function + JSON schema defined |
| CIO-02 | CIO has veto power to halt all trading | daily_directive.json `halt_trading` field; downstream pipeline checks before proceeding |
| CIO-03 | CIO directive cascades to downstream agents | Decision Engine reads risk_budget_multiplier; Risk Manager reads trading_stance |
| MACRO-01 | Macro Strategist produces macro_outlook.json | Macro agent spec + task function using code-fetched data |
| MACRO-02 | Macro uses code-fetched real-time data | task function calls AlpacaClient + yfinance for TLT, UUP, VIX, yield curve data |
| MACRO-03 | Macro outlook integrates into market regime detection | macro_outlook.json enriches `_detect_market_regime()` with cross-asset signals |
| EOD-01 | EOD Review produces eod_review.json with P&L attribution | EOD agent spec + task function reading positions + trade log |
| EOD-02 | EOD identifies thesis drift positions | Comparison of entry signals vs current technical state |
| EOD-03 | EOD insights feed into next day with confidence decay | Memory integration with decay weights (1.0, 0.5, 0.25) |
| MEM-01 | Fix silent memory corruption | Replace `pass` in SituationMemory.load() with logging + backup rotation |
| MEM-04 | Fix trade log race condition | Add filelock around _log_trade() read-modify-write cycle |
| MEM-05 | EOD review confidence decay | Timestamped EOD entries with decay function for memory retrieval |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Tech Stack**: Python 3.11+, Alpaca API, Claude Code Agent Teams -- no framework changes
- **Cost**: Tiered model usage (Opus for critical decisions, Sonnet for analysis/debate, Haiku for execution tasks)
- **Compatibility**: Must preserve existing `config/settings.yaml` structure and `shared_state/` communication pattern
- **No tests/linter**: Currently none configured (CLAUDE.md states this explicitly)
- **Agent specs**: Written in Chinese, self-contained with execution code + I/O schema
- **Entry points**: `python -m src.orchestrator` and `python -m src.agents_launcher`
- **Naming**: `snake_case` modules, `PascalCase` classes, `task_*()` for agent-callable functions, `run_*()` for orchestrator pipeline methods
- **Error handling**: Emoji-prefixed print statements (no logging module yet)
- **Data structures**: `@dataclass` with `to_dict()` for single-symbol results, plain dicts for aggregates, JSON files for inter-agent communication
- **GSD workflow**: Must use GSD commands for file changes, no direct repo edits outside workflow

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Claude Code Agent Teams | v2.1.32+ | Team orchestration (TeamCreate, SendMessage, shared task list) | Only option for multi-agent Claude Code coordination |
| Python | 3.12.10 (installed) | Runtime | Already in use |
| alpaca-py | >=0.21.0 | Market data, orders, positions | Already in use |
| yfinance | >=0.2.36 | VIX, yield curve, cross-asset data for Macro Strategist | Already in use |
| filelock | 3.13.1 (installed) | Trade log race condition fix | Standard file locking; already available in environment |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| json (stdlib) | - | Shared state serialization | All inter-agent communication |
| pathlib (stdlib) | - | File path handling | All file operations |
| shutil (stdlib) | - | Backup file rotation for memory corruption fix | MEM-01 fix |
| fcntl (stdlib) | - | Alternative to filelock if simplicity preferred | MEM-04 fix (Unix-only) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| filelock | fcntl (stdlib) | fcntl is Unix-only but zero dependencies; filelock is cross-platform and already installed |
| JSON files for state | SQLite | SQLite handles concurrency natively but breaks existing shared_state pattern (locked decision) |
| Print logging | Python logging module | Logging module is better but out of scope for this phase (tech debt, not required) |

**Installation:**
```bash
# filelock is already available. No new packages needed for Phase 1.
# If filelock were missing:
pip install filelock>=3.13.0
```

## Architecture Patterns

### New Module Structure
```
src/
├── team_orchestrator.py      # NEW: TeamCreate orchestration, phase group spawning
├── agents_launcher.py        # MODIFIED: add task_macro_strategist(), task_cio_directive(), task_eod_review()
├── orchestrator.py           # MODIFIED: generate_trade_plan() reads risk_budget_multiplier
├── memory/
│   └── situation_memory.py   # MODIFIED: fix silent corruption (MEM-01)
└── ...

agents/
├── strategic/                # NEW directory for strategic oversight roles
│   ├── cio.md               # NEW: CIO agent spec (Chinese)
│   ├── macro_strategist.md  # NEW: Macro Strategist spec (Chinese)
│   └── eod_review.md        # NEW: EOD Review Analyst spec (Chinese)
└── ...existing directories...

shared_state/YYYY-MM-DD/
├── macro_outlook.json        # NEW: Macro Strategist output
├── daily_directive.json      # NEW: CIO output
├── eod_review.json           # NEW: EOD Review output
└── ...existing files...
```

### Pattern 1: Team Orchestrator (replaces AGENT_TEAMS_PROMPT)

**What:** A Python module that programmatically creates an Agent Team with CIO as Lead, spawns teammates in phased groups, and coordinates via SendMessage.

**When to use:** Every Agent Teams pipeline run (default mode).

**Design:**

The CIO-as-Lead approach means the main Claude Code session IS the CIO. It creates the team, runs its own CIO logic (reading macro_outlook.json, yesterday's eod_review.json, market regime), produces daily_directive.json, then spawns and manages downstream teammates in phase groups.

```
Pipeline Flow (CIO as Team Lead):

1. CIO/Lead creates team via TeamCreate
2. CIO/Lead spawns Macro Strategist teammate
3. Macro Strategist produces macro_outlook.json, notifies Lead via SendMessage
4. CIO/Lead reads macro_outlook.json + yesterday's eod_review.json + market regime
5. CIO/Lead produces daily_directive.json (stance + risk_budget_multiplier)
6. IF halt_trading == true: skip to EOD Review
7. CIO/Lead spawns Phase Group 2 (Screener, Market, Tech, Sentiment analysts)
8. Analysts complete, notify Lead
9. CIO/Lead shuts down analyst teammates
10. CIO/Lead runs Decision Engine (Lead direct -- task_generate_decisions)
11. CIO/Lead spawns Debate teammates (Bull/Bear/Judge per symbol)
12. Debate completes, Lead merges results
13. CIO/Lead spawns Risk Manager teammate
14. CIO/Lead spawns Executor teammate
15. CIO/Lead spawns Phase Group 3 (Reporter + EOD Review + Reflection)
16. All complete, Lead shuts down team
```

**Key insight:** The CIO is not a separate teammate -- it IS the Lead. This is architecturally clean because:
- The Lead already has full orchestration authority (spawn, shutdown, SendMessage)
- No extra teammate cost for the CIO role
- CIO decisions are synchronous checkpoints, not parallel work
- Matches D-01: "CIO agent is the Lead"

### Pattern 2: Directive Cascade

**What:** CIO's daily_directive.json is read by all downstream agents to adjust their behavior.

**When to use:** Every phase after CIO produces the directive.

**Integration points:**
1. **Decision Engine** (`orchestrator.py:generate_trade_plan()`): Reads `risk_budget_multiplier` to scale composite scores or thresholds
2. **Risk Manager** (`risk/manager.py:assess_trade()`): Reads `trading_stance` to adjust position sizing or threshold strictness
3. **Standalone fallback**: When running without Agent Teams, `daily_directive.json` defaults are used (stance=neutral, multiplier=1.0)

**Wiring risk_budget_multiplier into Decision Engine:**

The simplest integration: multiply the buy/sell thresholds by the inverse of risk_budget_multiplier.

```python
# In generate_trade_plan(), after loading regime info:
directive_path = self.state_dir / "daily_directive.json"
risk_budget_multiplier = 1.0  # default: neutral
if directive_path.exists():
    with open(directive_path) as f:
        directive = json.load(f)
    risk_budget_multiplier = directive.get("risk_budget_multiplier", 1.0)

# Adjust thresholds: higher multiplier = more aggressive = lower buy threshold
effective_min_buy = min_buy / risk_budget_multiplier
effective_min_sell = min_sell / risk_budget_multiplier
```

Alternatively, scale the composite score directly:
```python
composite = composite * risk_budget_multiplier
```

**Recommendation:** Scale the thresholds (first approach). This preserves the original score for audit trail while making it easier/harder to qualify as a candidate. A multiplier of 1.2 (aggressive) lowers the bar by ~17%; 0.8 (defensive) raises it by ~25%.

### Pattern 3: Graceful Degradation

**What:** Each phase wrapped in try/except. Only Risk Manager failure halts the pipeline.

**When to use:** All teammate spawning and phase execution.

```python
# Pseudocode for graceful degradation
try:
    macro_outlook = spawn_and_wait("macro-strategist")
except TeammateFailure:
    print("WARNING: Macro Strategist failed, CIO will decide without macro data")
    macro_outlook = {"status": "unavailable"}

# CIO always runs (it's the Lead, it can't "fail" in teammate sense)
directive = cio_decide(macro_outlook, yesterday_eod, market_regime)

# Risk Manager is the ONLY hard stop
try:
    risk_result = spawn_and_wait("risk-manager", candidates)
except TeammateFailure:
    print("CRITICAL: Risk Manager failed -- HALTING ALL TRADES")
    return []  # No trades executed
```

### Pattern 4: Agent Spec Format (new roles)

**What:** New agent specs follow the existing Chinese-language pattern with embedded execution code.

**Structure for new specs:**
```markdown
# [Role Name] Agent（中文職稱）

你是 **[Role Name]**，對應真實交易室中的**中文職稱**，負責...

## 你的職責
1. ...
2. ...

## [Domain-specific logic/framework]

## 執行方式
\```python
from src.agents_launcher import task_[role]
result = task_[role]()
\```

## 輸出格式
寫入 `shared_state/[output_file].json`:
\```json
{ ... schema ... }
\```
```

### Anti-Patterns to Avoid
- **CIO as separate teammate:** Creates unnecessary token cost and coordination overhead. CIO IS the Lead.
- **Spawning all teammates at once:** Violates D-02 (phased spawning). Token waste from idle teammates waiting for dependencies.
- **SendMessage for structured data:** JSON files in shared_state are the right channel for structured data (D-09). SendMessage is for coordination signals only.
- **Modifying existing task_*() function signatures:** Existing functions are called by standalone mode too. Add new functions; don't break existing ones.
- **Hardcoding model tiers in Python:** Put model tier in agent spec YAML frontmatter or a config mapping, not scattered in orchestration code.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| File locking for trade log | Custom lock file protocol | `filelock` library | Handles stale locks, cross-platform, already installed |
| Agent team orchestration | Custom subprocess management | Claude Code TeamCreate + SendMessage | Built-in coordination, task list, mailbox, shutdown |
| Atomic file writes | Manual temp file + rename | `tempfile.NamedTemporaryFile` + `os.replace` | OS-level atomic rename prevents partial writes |
| JSON schema validation | Manual field checking | Simple dict.get() with defaults | Full schema validation (pydantic) is overkill for this phase; keep it simple with sensible defaults |
| Yield curve data | Custom FRED API integration | yfinance `^TYX` (30yr), `^TNX` (10yr), `^IRX` (3mo) | yfinance already a dependency; FRED API (fredapi) deferred to Phase 2+ |

**Key insight:** This phase adds no new external dependencies. Everything needed is already installed or in the standard library.

## Common Pitfalls

### Pitfall 1: CIO Rubber Stamp / Over-Conservatism
**What goes wrong:** LLM defaults to "neutral" stance every day, providing no strategic value. Or always says "defensive" because it's risk-averse by training.
**Why it happens:** LLMs hedge by default. Without explicit stance triggers, the CIO will rationalize inaction.
**How to avoid:** Define explicit quantitative triggers in the CIO agent spec:
- VIX > 30 AND yield curve inverted = defensive (risk_budget_multiplier: 0.6)
- VIX < 18 AND SPY EMA20 > EMA50 > EMA200 = aggressive (risk_budget_multiplier: 1.3)
- All other conditions = neutral (risk_budget_multiplier: 1.0)
Track stance distribution after 2 weeks (per D-06). If >80% neutral, adjust triggers.
**Warning signs:** Same stance 5+ days in a row. risk_budget_multiplier always exactly 1.0.

### Pitfall 2: Macro Strategist Data Hallucination
**What goes wrong:** LLM teammate fabricates market numbers from training data instead of using code-fetched real-time data.
**Why it happens:** LLM training data contains plausible-sounding market data. If the code execution fails silently, the LLM fills in from "memory."
**How to avoid:** The Macro Strategist task function MUST fetch all data via Python code (AlpacaClient + yfinance) BEFORE the LLM reasons about it. The agent spec should mandate: "Use ONLY the data provided in the function output. Do NOT cite market numbers from your training data."
**Warning signs:** Macro outlook mentions specific prices/levels that don't match `market_overview.json` data.

### Pitfall 3: Teammate Spawn/Shutdown Timing
**What goes wrong:** Lead spawns next phase group before current group finishes. Or forgets to shut down completed teammates, wasting tokens.
**Why it happens:** Agent Teams communication is async. SendMessage delivery is not instant. Lead may proceed optimistically.
**How to avoid:** Use explicit SendMessage acknowledgment pattern. Lead waits for "phase complete" message from each teammate before proceeding. Set timeouts (e.g., 120s per phase group) and use graceful degradation if timeout expires.
**Warning signs:** Token costs much higher than expected. Multiple teammate sessions running simultaneously.

### Pitfall 4: EOD Review Circular Reasoning
**What goes wrong:** "Be more aggressive" -> losses -> "be more conservative" -> missed gains -> "be more aggressive" -> oscillation.
**Why it happens:** EOD insights framed as directives instead of observations. No decay on older insights.
**How to avoid:**
1. Frame EOD output as observations: "today's P&L was X because Y" not "tomorrow should be more aggressive"
2. Apply confidence decay: yesterday's insights weight 1.0, two days ago 0.5, three days ago 0.25, older dropped
3. CIO reads EOD insights but makes its own judgment -- EOD does NOT directly control stance
**Warning signs:** Daily stance flip-flops. CIO reasoning cites EOD review as primary justification.

### Pitfall 5: Standalone Mode Regression
**What goes wrong:** Refactoring for Agent Teams breaks `run_full_pipeline()` standalone mode.
**Why it happens:** New code assumes Agent Teams context (TeamCreate, SendMessage) that doesn't exist in standalone.
**How to avoid:**
1. New task functions (`task_macro_strategist()`, `task_cio_directive()`, `task_eod_review()`) work standalone -- they produce JSON files without needing SendMessage
2. `run_full_pipeline()` calls them directly, same as existing task functions
3. Agent Teams orchestration is a separate layer ON TOP of the task functions
**Warning signs:** `python -m src.agents_launcher --run` crashes or skips new phases.

### Pitfall 6: Race Condition in Shared State Reads
**What goes wrong:** Two parallel analyst teammates write to shared_state while another reads a partial file.
**Why it happens:** JSON file writes are not atomic by default. `json.dump()` to an open file can be read mid-write.
**How to avoid:** Use atomic writes: write to temp file, then `os.replace()` to target path. `os.replace()` is atomic on all major OSes.
**Warning signs:** JSONDecodeError in downstream phase. Truncated JSON files in shared_state.

## Code Examples

### Example 1: Atomic JSON Write (for all shared_state files)
```python
import json
import os
import tempfile
from pathlib import Path

def save_state_atomic(filepath: Path, data: dict) -> None:
    """Atomically write JSON to shared_state. Prevents partial reads."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    # Write to temp file in same directory (same filesystem for atomic rename)
    fd, tmp_path = tempfile.mkstemp(dir=filepath.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        os.replace(tmp_path, filepath)  # atomic on POSIX and Windows
    except Exception:
        os.unlink(tmp_path)  # clean up on failure
        raise
```

### Example 2: Trade Log with File Locking (MEM-04)
```python
from filelock import FileLock

def _log_trade(self, trade: dict, result: dict):
    """Append trade to trade log with file locking for concurrent safety."""
    log_path = self.log_dir / "trade_log.json"
    lock_path = self.log_dir / "trade_log.json.lock"

    with FileLock(lock_path, timeout=10):
        logs = []
        if log_path.exists():
            with open(log_path) as f:
                logs = json.load(f)

        logs.append({
            "timestamp": datetime.now().isoformat(),
            "symbol": trade["symbol"],
            "side": trade["side"],
            "qty": trade["suggested_qty"],
            "entry_price": trade["entry_price"],
            "stop_loss": trade.get("stop_loss"),
            "take_profit": trade.get("take_profit"),
            "score": trade["composite_score"],
            "order_id": result["id"],
            "order_status": result["status"],
        })

        # Atomic write within the lock
        save_state_atomic(log_path, logs)
```

### Example 3: Memory Corruption Fix (MEM-01)
```python
def load(self):
    """Load memory from JSON file if it exists. Creates backup on corruption."""
    path = self.storage_dir / f"{self.name}.json"
    if not path.exists():
        return
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        self.documents = [e["situation"] for e in data.get("entries", [])]
        self.lessons = [e["lesson"] for e in data.get("entries", [])]
        self._rebuild_index()
    except (json.JSONDecodeError, KeyError) as e:
        # Backup corrupted file instead of silently discarding
        backup_path = path.with_suffix(f".corrupted.{int(time.time())}.json")
        import shutil
        shutil.copy2(path, backup_path)
        print(f"  WARNING: Memory bank '{self.name}' corrupted: {e}")
        print(f"  Backed up to {backup_path}. Starting fresh.")
        self.documents = []
        self.lessons = []
        self.bm25 = None
```

### Example 4: daily_directive.json Schema
```json
{
  "date": "2026-03-30",
  "timestamp": "2026-03-30T09:15:00-04:00",
  "trading_stance": "neutral",
  "risk_budget_multiplier": 1.0,
  "halt_trading": false,
  "reasoning": "VIX at 18.5, SPY EMA alignment risk_on, no macro headwinds. Neutral stance appropriate.",
  "inputs_used": {
    "macro_outlook_available": true,
    "yesterday_eod_available": true,
    "market_regime": "risk_on"
  },
  "stance_triggers_met": []
}
```

### Example 5: macro_outlook.json Schema
```json
{
  "date": "2026-03-30",
  "timestamp": "2026-03-30T09:10:00-04:00",
  "cross_asset_signals": {
    "vix": {"value": 18.5, "trend": "declining", "sma5_vs_sma20": "below"},
    "tlt": {"price": 92.30, "trend": "declining", "interpretation": "yields_rising_risk_on"},
    "uup": {"price": 27.80, "trend": "flat", "interpretation": "dollar_neutral"},
    "yield_curve": {"spread_10y_3m": 0.45, "inverted": false}
  },
  "macro_regime_suggestion": "risk_on",
  "key_events": ["FOMC minutes Wednesday", "NFP Friday"],
  "data_freshness": {
    "vix_source": "yfinance",
    "tlt_source": "alpaca",
    "uup_source": "alpaca"
  }
}
```

### Example 6: eod_review.json Schema
```json
{
  "date": "2026-03-30",
  "timestamp": "2026-03-30T16:30:00-04:00",
  "portfolio_summary": {
    "total_pnl_today": 245.30,
    "total_pnl_pct": 0.82,
    "positions_count": 5,
    "new_entries": 2,
    "exits": 1
  },
  "position_reviews": [
    {
      "symbol": "NVDA",
      "entry_date": "2026-03-28",
      "pnl_today": 120.50,
      "pnl_total": 380.00,
      "thesis_status": "intact",
      "character_change": false,
      "notes": "Momentum continuing. ADX 35, trend strong."
    }
  ],
  "thesis_drift_alerts": [
    {
      "symbol": "AAPL",
      "original_thesis": "Momentum breakout above $195",
      "current_status": "Price reversed below entry. RSI dropped from 65 to 48.",
      "recommendation": "Monitor for exit signal"
    }
  ],
  "observations": [
    "Risk_on regime confirmed by macro signals",
    "Tech sector outperforming today"
  ],
  "confidence_weight": 1.0
}
```

### Example 7: EOD Confidence Decay (MEM-05)
```python
from datetime import datetime, timedelta
from pathlib import Path
import json

def get_recent_eod_insights(state_base_dir: Path, max_days: int = 3) -> list[dict]:
    """Load recent EOD reviews with confidence decay.

    Returns list of dicts with 'insights' and 'weight' keys.
    Yesterday = 1.0, 2 days ago = 0.5, 3 days ago = 0.25.
    """
    decay_weights = {1: 1.0, 2: 0.5, 3: 0.25}
    results = []
    today = datetime.now().date()

    for days_ago in range(1, max_days + 1):
        target_date = today - timedelta(days=days_ago)
        eod_path = state_base_dir / target_date.isoformat() / "eod_review.json"
        if eod_path.exists():
            try:
                with open(eod_path) as f:
                    eod_data = json.load(f)
                results.append({
                    "date": target_date.isoformat(),
                    "weight": decay_weights.get(days_ago, 0.0),
                    "observations": eod_data.get("observations", []),
                    "thesis_drift_alerts": eod_data.get("thesis_drift_alerts", []),
                })
            except (json.JSONDecodeError, KeyError):
                continue
    return results
```

### Example 8: Model Tier Map
```python
# Recommended model tier assignments for all agents
MODEL_TIERS = {
    # Strategic (CIO is Lead, no model needed)
    "macro-strategist": "sonnet",      # Cross-asset synthesis, analytical reasoning
    "eod-review": "sonnet",            # P&L attribution, connecting multiple data points

    # Existing analysts
    "symbol-screener": "haiku",        # Pure code execution
    "market-analyst": "haiku",         # Pure code execution
    "technical-analyst": "haiku",      # Pure code execution
    "sentiment-analyst": "haiku",      # Pure code execution
    "fundamentals-analyst": "haiku",   # Pure code execution

    # Debate
    "bull-researcher": "sonnet",       # Structured argumentation
    "bear-researcher": "sonnet",       # Structured argumentation
    "research-judge": "opus",          # Deep reasoning, verdict

    # Risk + Execution
    "risk-manager": "haiku",           # Rule-based checks
    "executor": "haiku",              # Order placement
    "position-reviewer": "haiku",     # Code execution

    # Post-trade
    "reporter": "haiku",              # Template-based reporting
    "reflection-analyst": "opus",     # Deep reasoning, lesson extraction
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| AGENT_TEAMS_PROMPT text blob pasted by user | Programmatic TeamCreate via Python orchestrator | This phase | Eliminates manual prompt pasting; enables automated daily runs |
| Subagent-only execution | Teammate-based with SendMessage coordination | Claude Code v2.1.32 (Feb 2026) | Real-time inter-agent communication; shared task list |
| No strategic layer | CIO + Macro Strategist pre-market | This phase | Trading decisions informed by macro context and strategic stance |
| No daily feedback loop | EOD Review with confidence decay | This phase | Next day's pipeline learns from today's outcomes |
| Silent memory corruption | Backup + error reporting | This phase (MEM-01) | No more lost memory data |
| Race condition in trade log | File locking | This phase (MEM-04) | Safe concurrent writes |

## Open Questions

1. **CIO-as-Lead prompt engineering**
   - What we know: CIO is the Lead agent. It needs a system prompt that combines orchestration instructions with CIO decision logic.
   - What's unclear: How to structure the Lead's initial prompt so it both orchestrates the pipeline AND makes CIO decisions. Two approaches: (a) single combined prompt, (b) CIO decision logic in a separate agent spec that the Lead reads.
   - Recommendation: Use approach (b) -- Lead reads `agents/strategic/cio.md` for decision logic but handles orchestration from `team_orchestrator.py` instructions. Cleaner separation of concerns.

2. **Yield curve data source**
   - What we know: yfinance provides `^TYX` (30yr), `^TNX` (10yr), `^IRX` (3mo) for basic yield curve spread calculation.
   - What's unclear: Reliability of yfinance for these tickers (it uses Yahoo Finance scraping which can break).
   - Recommendation: Use yfinance with graceful degradation. If yield curve data unavailable, Macro Strategist proceeds without it. Flag for Phase 2+ FRED API integration.

3. **Teammate timeout handling**
   - What we know: Agent Teams has no built-in timeout per teammate. Teammates run until done or until Lead sends shutdown.
   - What's unclear: What happens if a teammate hangs indefinitely.
   - Recommendation: Implement timeout logic in the orchestrator: if no SendMessage received within N seconds, send shutdown and proceed with graceful degradation.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | All | Yes | 3.12.10 | -- |
| Claude Code | Agent Teams | Yes (assumed) | v2.1.32+ required | Standalone mode (run_full_pipeline) |
| CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS | Agent Teams | Configurable | env var | Standalone mode |
| alpaca-py | Market data, execution | Yes | >=0.21.0 | -- |
| yfinance | VIX, yield curve, cross-asset | Yes | >=0.2.36 | Graceful degradation (skip yield curve data) |
| filelock | MEM-04 trade log fix | Yes | 3.13.1 | fcntl (stdlib, Unix-only) |
| tmux | Split-pane display (optional) | Check at runtime | -- | In-process mode (default) |

**Missing dependencies with no fallback:**
- None. All required dependencies are available.

**Missing dependencies with fallback:**
- tmux: Only needed for split-pane Agent Teams display. In-process mode works without it.

## Sources

### Primary (HIGH confidence)
- [Claude Code Agent Teams official docs](https://code.claude.com/docs/en/agent-teams) - TeamCreate, SendMessage, task list, shutdown, model selection, limitations
- Existing codebase analysis: `src/agents_launcher.py`, `src/orchestrator.py`, `src/memory/situation_memory.py`, `agents/**/*.md`
- `.planning/codebase/ARCHITECTURE.md` - Current system architecture, data flow, layers
- `.planning/codebase/CONCERNS.md` - Known bugs (MEM-01 lines 119-120, MEM-04 lines 983-1007)

### Secondary (MEDIUM confidence)
- `.planning/research/SUMMARY.md` - Role definitions, cost estimates, pitfall analysis based on TradingAgents framework
- [TradingAgents framework (arXiv:2412.20138)](https://arxiv.org/abs/2412.20138) - Multi-agent trading desk validation

### Tertiary (LOW confidence)
- Cost estimates ($3-7 per daily run for Phase 1 roles) - Based on approximate token counts from research summary, needs validation with actual runs
- Yield curve data reliability via yfinance - Known to be fragile; needs runtime validation

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new dependencies, all verified installed
- Architecture: HIGH - Extends existing patterns cleanly; Agent Teams API well-documented
- Agent spec patterns: HIGH - Following existing proven pattern (12 specs already work)
- CIO integration: MEDIUM-HIGH - Single integration point in generate_trade_plan() is clear; exact scaling formula is discretionary
- Pitfalls: MEDIUM-HIGH - Well-documented from research phase; CIO calibration is the biggest unknown
- Memory fixes: HIGH - Bugs are precisely located, fixes are standard patterns

**Research date:** 2026-03-30
**Valid until:** 2026-04-30 (stable domain, no fast-moving dependencies)
