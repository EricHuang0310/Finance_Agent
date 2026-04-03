# Phase 2: Portfolio Intelligence - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Add a Portfolio Strategist agent that analyzes cross-position correlations and produces sizing adjustments before new positions are approved. Also suggests partial closes when existing portfolio becomes too concentrated. Implement structured trade journals with entry/exit lifecycle tracking and R-multiple outcome tagging.

Delivers: PORT-01, PORT-02, PORT-03, MEM-02 (4 requirements).

</domain>

<decisions>
## Implementation Decisions

### Correlation Method
- **D-01:** Claude's discretion on exact correlation approach (rolling price correlation, sector+correlation hybrid, or factor-based). 20-day rolling window for computation, matching existing screener lookback. Correlation threshold and flagging logic at Claude's discretion.

### Sizing Adjustments
- **D-02:** Claude's discretion on adjustment action when correlated positions detected (reduce qty, reject, or reduce+warn). Choose the approach that best balances risk management with signal preservation.
- **D-03:** Portfolio Strategist SHOULD also suggest partial closes of existing positions when portfolio becomes too concentrated. This extends beyond just gating new entries -- if the portfolio is overly correlated, suggest reducing existing positions.

### Trade Journal Schema
- **D-04:** Journal entries written at TWO lifecycle points: (1) on fill -- captures entry thesis, signals at entry, scoring data; (2) on close -- adds exit data, P&L, holding period, outcome tag.
- **D-05:** Outcome tagging: Win (P&L > 0), Loss (P&L < 0), Scratch (|P&L| < 0.5%). Include R-multiple = P&L / initial risk (stop distance from entry). Enables risk-adjusted strategy learning in Phase 3.

### Pipeline Integration
- **D-06:** Claude's discretion on exact pipeline placement (after Risk Manager before Executor, or before Risk Manager). Choose based on architectural analysis of how portfolio context best integrates with existing risk flow.
- **D-07:** Portfolio Strategist is a hybrid agent: quantitative correlation computation via code (task function), but LLM reasoning about portfolio narrative and diversification quality. Model tier: Sonnet.

### Carried from Phase 1
- **D-07/P1:** Agent specs in Chinese, in `agents/` directory
- **D-09/P1:** Hybrid communication: SendMessage + JSON files
- **D-12/P1:** Graceful degradation: Portfolio Strategist failure should not halt pipeline

### Claude's Discretion
- Correlation computation method (price correlation, sector hybrid, or factor-based)
- Correlation threshold for flagging (0.7 suggested by research, Claude may adjust)
- Sizing adjustment strategy (reduce, reject, or reduce+warn)
- Pipeline placement (after or before Risk Manager)
- portfolio_construction.json schema details
- Trade journal storage format (new JSON file vs extending trade_log.json)
- How partial close suggestions integrate with Position Reviewer

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` -- Project vision, constraints
- `.planning/REQUIREMENTS.md` -- PORT-01, PORT-02, PORT-03, MEM-02 requirements
- `.planning/ROADMAP.md` -- Phase 2 success criteria

### Phase 1 Context (prior decisions)
- `.planning/phases/01-strategic-oversight-agent-teams-foundation/01-CONTEXT.md` -- All Phase 1 decisions (team topology, CIO design, pipeline order, etc.)

### Research
- `.planning/research/SUMMARY.md` -- Portfolio Strategist role analysis, correlation approach notes
- `.planning/research/FEATURES.md` -- Role priority and agent type recommendations

### Codebase (modified by Phase 1)
- `src/orchestrator.py` -- Decision Engine with CIO directive cascade (Phase 1 output)
- `src/risk/manager.py` -- RiskManager with cio_stance field (Phase 1 output)
- `src/agents_launcher.py` -- All task functions including Macro/CIO/EOD (Phase 1 output)
- `src/team_orchestrator.py` -- TeamCreate orchestration (Phase 1 output)
- `src/utils/state_io.py` -- Atomic JSON write utility (Phase 1 output)

### Agent Specs
- `agents/strategic/cio.md` -- CIO spec (Phase 1, reference for new spec pattern)
- `agents/strategic/macro_strategist.md` -- Macro Strategist spec
- `agents/strategic/eod_review.md` -- EOD Review spec
- `agents/risk_mgmt/risk_manager.md` -- Existing risk manager spec
- `agents/trader/position_reviewer.md` -- Position exit review spec (relevant for partial close integration)

### Config
- `config/settings.yaml` -- Existing risk limits, position exit config, strategic role config (Phase 1 additions)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `save_state_atomic()` from `src/utils/state_io` -- Use for writing portfolio_construction.json and trade journal entries
- `TradingOrchestrator._bar_cache` -- Reuse cached bar data for correlation computation (no extra API calls)
- `AlpacaClient.get_positions()` -- Get current portfolio for correlation analysis
- `RiskManager.assess_trade()` -- Returns RiskAssessment with approved/rejected + cio_stance. Portfolio Strategist post-processes approved trades.
- `TradingOrchestrator._log_trade()` -- Existing trade logging with FileLock. Trade journal may extend or parallel this.

### Established Patterns
- `task_*()` function pattern in `agents_launcher.py` -- New `task_portfolio_strategist()` follows same pattern
- Agent spec pattern: Role + execution code + I/O schema in one .md file
- JSON state file pattern: Write to `shared_state/YYYY-MM-DD/portfolio_construction.json`
- Config pattern: Add `portfolio:` section to `settings.yaml`

### Integration Points
- After `task_risk_manager()` returns assessed trades, Portfolio Strategist processes approved ones
- `run_full_pipeline()` needs new Portfolio Strategist call inserted at correct pipeline position
- `AGENT_TEAMS_PROMPT` / `build_team_prompt()` needs Portfolio Strategist phase added
- Trade journal writes need to hook into `task_execute_trades()` (on fill) and `task_execute_exits()` (on close)

</code_context>

<specifics>
## Specific Ideas

- Research noted scipy for correlation matrices -- this is optional, numpy can handle 20-day rolling correlation for a small portfolio
- Portfolio Strategist's partial close suggestions should produce output compatible with Position Reviewer's existing exit_candidates format
- Trade journal R-multiple calculation needs the initial stop distance, which is already available in bracket orders (stop_loss field)

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 02-portfolio-intelligence*
*Context gathered: 2026-04-03*
