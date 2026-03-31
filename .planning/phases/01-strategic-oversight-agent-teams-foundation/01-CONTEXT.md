# Phase 1: Strategic Oversight & Agent Teams Foundation - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Transform the trading pipeline to run entirely through Claude Code Agent Teams (TeamCreate + SendMessage) with a strategic oversight layer: CIO sets daily trading stance, Macro Strategist provides cross-asset intelligence, EOD Review closes the daily feedback loop. Fix memory reliability for concurrent execution.

Delivers: TEAMS-01..05, CIO-01..03, MACRO-01..03, EOD-01..03, MEM-01, MEM-04, MEM-05 (17 requirements).

</domain>

<decisions>
## Implementation Decisions

### Team Topology
- **D-01:** Single team per daily run via TeamCreate. CIO agent is the Lead that orchestrates all phases, spawns and shuts down teammates as needed. Human monitors but does not intervene.
- **D-02:** Phased spawning: spawn 3-5 teammates per phase group (e.g., analysts together, then debaters), keeping active teammate count low to save tokens. Shut down completed teammates before spawning next group.
- **D-03:** Keep standalone mode (`run_full_pipeline()`) as fallback for quick tests or when Agent Teams is unavailable. Agent Teams is the default execution mode.

### CIO Behavior Design
- **D-04:** CIO scope is narrow: sets trading stance (aggressive/neutral/defensive) and risk_budget_multiplier. Does NOT veto individual trades -- that remains Risk Manager's job. Prevents compound rejection problem.
- **D-05:** CIO reads macro_outlook.json + market regime + yesterday's eod_review.json to decide stance. Cross-asset signals and recent performance inform the decision.
- **D-06:** CIO goes live from day 1 (no shadow mode). Faster feedback loop. If stance distribution is skewed after 2 weeks, prompt will be adjusted.

### Agent Spec Format
- **D-07:** All agent specs stay in Chinese for consistency. New roles (CIO, Macro Strategist, EOD Review) are also written in Chinese.
- **D-08:** Agent specs remain in existing `agents/` directory structure. No migration to `.claude/agents/`. Specs are project-specific and self-contained with execution code, I/O schema, and role descriptions.
- **D-09:** Hybrid communication: SendMessage for coordination (task completion, dependency triggers, debate turn-taking). JSON files in `shared_state/` for structured data (signals, scores, directives, debate arguments). Preserves auditability and standalone compatibility.

### Pipeline Orchestration
- **D-10:** Pre-market layer runs first: Macro Strategist -> CIO Directive -> then existing pipeline (Screener -> Analysts -> Debate -> Risk -> Execute -> Report -> EOD Review). New roles bookend the existing flow.
- **D-11:** Parallel groups: Group 1 (Macro data collection), Group 2 (Market/Tech/Sentiment analysts), Group 3 (Reporter + EOD Review + Reflection post-execution). All other phases are sequential.
- **D-12:** Graceful degradation: Only Risk Manager failure is a hard stop (veto power). All other teammate failures skip that phase and continue. E.g., if Macro Strategist fails, CIO decides without macro data.

### Claude's Discretion
- Model tier assignment per specific agent (within the Opus/Sonnet/Haiku framework from TEAMS-03)
- Exact JSON schema for daily_directive.json, macro_outlook.json, eod_review.json
- How to wire CIO's risk_budget_multiplier into existing Decision Engine scoring
- Memory corruption fix approach (MEM-01) and trade log race condition fix (MEM-04)
- EOD Review confidence decay implementation details (MEM-05)

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` -- Project vision, core value, constraints
- `.planning/REQUIREMENTS.md` -- All 17 requirements for this phase with REQ-IDs
- `.planning/ROADMAP.md` -- Phase structure and success criteria

### Research
- `.planning/research/SUMMARY.md` -- Research synthesis: recommended roles, architecture, pitfalls
- `.planning/research/FEATURES.md` -- Trading desk role analysis with priority ranking
- `.planning/research/ARCHITECTURE.md` -- Team topology and communication pattern recommendations
- `.planning/research/PITFALLS.md` -- Critical pitfalls: agent proliferation tax, CIO calibration, veto chains

### Codebase
- `.planning/codebase/ARCHITECTURE.md` -- Current system architecture and layer diagram
- `.planning/codebase/CONCERNS.md` -- Known bugs: trade log race condition, memory corruption, silent exceptions
- `.planning/codebase/STACK.md` -- Technology stack and dependencies

### Agent Specs (existing, in Chinese)
- `agents/analysts/market_analyst.md` -- Market data collection spec
- `agents/analysts/technical_analyst.md` -- Technical analysis spec
- `agents/analysts/sentiment_analyst.md` -- Sentiment analysis spec
- `agents/analysts/symbol_screener.md` -- Dynamic watchlist screener
- `agents/analysts/fundamentals_analyst.md` -- Fundamentals data spec
- `agents/researchers/bull_researcher.md` -- Bull debate role
- `agents/researchers/bear_researcher.md` -- Bear debate role
- `agents/researchers/research_judge.md` -- Judge verdict role
- `agents/risk_mgmt/risk_manager.md` -- Risk assessment spec
- `agents/trader/position_reviewer.md` -- Position exit review spec
- `agents/trader/executor.md` -- Order execution spec
- `agents/reporting/reporter.md` -- Telegram report spec
- `agents/reflection/reflection_analyst.md` -- Post-trade learning spec

### Key Source Files
- `src/agents_launcher.py` -- Current AGENT_TEAMS_PROMPT and task_*() functions (to be refactored)
- `src/orchestrator.py` -- TradingOrchestrator god object (phase methods to be called by teammates)
- `src/memory/situation_memory.py` -- BM25 memory with corruption bug (lines 119-120)
- `src/orchestrator.py:983-1007` -- Trade log race condition

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `task_*()` functions in `agents_launcher.py`: 15+ task functions already work as standalone callable units. Teammates can call these directly.
- `TradingOrchestrator` class: All phase methods exist and work. CIO/Macro/EOD will produce JSON consumed by existing methods.
- `shared_state/YYYY-MM-DD/` pattern: Proven JSON file communication. New roles just add new files (daily_directive.json, macro_outlook.json, eod_review.json).
- `SituationMemory` class: BM25 memory with 5 banks. Works but has corruption bug to fix.

### Established Patterns
- Agent spec pattern: Role description + execution code + I/O schema in one .md file. New roles follow same pattern.
- Phase method pattern: `TradingOrchestrator.run_*()` methods return dict/list, caller writes to shared_state. New roles follow same pattern.
- Config pattern: All tunables in `config/settings.yaml`. New role settings (CIO thresholds, macro weights) go here.

### Integration Points
- `agents_launcher.py:AGENT_TEAMS_PROMPT` -- Replace with programmatic TeamCreate orchestration
- `agents_launcher.py:run_full_pipeline()` -- Keep as standalone fallback, but default path uses Agent Teams
- `orchestrator.py:generate_trade_plan()` -- Must read CIO's risk_budget_multiplier to adjust scoring
- `orchestrator.py:_detect_market_regime()` -- Macro Strategist enriches this with cross-asset signals

</code_context>

<specifics>
## Specific Ideas

- The earlier session (2026-03-30) successfully demonstrated Agent Teams with TeamCreate for the debate phase. That pattern should be generalized to the full pipeline.
- Research found the TradingAgents framework (arXiv:2412.20138) validates this multi-agent approach with measurable Sharpe ratio improvements.
- CIO's daily_directive.json should include explicit trading stance triggers (e.g., VIX > 35 = defensive, yield curve inverted = defensive).
- EOD Review confidence decay: 1.0 yesterday, 0.5 two days ago, 0.25 three days ago -- prevents circular reasoning.

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 01-strategic-oversight-agent-teams-foundation*
*Context gathered: 2026-03-31*
