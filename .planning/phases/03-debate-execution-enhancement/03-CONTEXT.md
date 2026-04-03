# Phase 3: Debate & Execution Enhancement - Context

**Gathered:** 2026-04-03
**Status:** Ready for planning

<domain>
## Phase Boundary

Add Sector Specialist as 4th voice in investment debate, Execution Strategist for intelligent order type selection, and cross-session pattern recognition in the memory system.

Delivers: SECT-01, SECT-02, SECT-03, EXEC-01, EXEC-02, EXEC-03, MEM-03 (7 requirements).

</domain>

<decisions>
## Implementation Decisions

### Claude's Discretion (All Areas)

User granted full discretion on all Phase 3 decisions. Claude should make choices based on research findings, prior phase patterns, and architectural consistency.

**Sector Specialist:**
- Agent type, model tier, spec format, data sources
- How it integrates into Bull/Bear/Judge debate flow (timing, ordering)
- What sector intelligence it provides (supply chain, rotation signals, competitive landscape)

**Execution Strategist:**
- Order type selection logic (market vs limit vs bracket vs TWAP)
- Fill quality tracking mechanism
- How execution_plan.json is consumed by Executor

**Memory Pattern Learning:**
- How to identify trade "setups" from journal entries
- Pattern recognition approach (tag-based grouping, statistical clustering, or LLM-driven)
- How to surface relevant lessons during analysis phases

### Carried from Phase 1 & 2
- **D-07/P1:** Agent specs in Chinese, in `agents/` directory
- **D-09/P1:** Hybrid communication: SendMessage + JSON files
- **D-12/P1:** Graceful degradation: new roles fail gracefully, pipeline continues
- **D-07/P2:** Hybrid agent pattern for complex roles: code for quantitative work, LLM for reasoning

### Design Guidelines (from research)
- Research recommended Sector Specialist as "supply chain + sector catalysts only" (narrow scope to avoid bloat)
- Execution Strategist is lowest priority — current bracket orders work; this is optimization
- Memory pattern learning needs accumulated trade journal data (from Phase 2's MEM-02) to be meaningful
- Agent proliferation tax: measure cumulative latency/cost before adding all three roles

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` -- Project vision, constraints
- `.planning/REQUIREMENTS.md` -- SECT-01..03, EXEC-01..03, MEM-03 requirements
- `.planning/ROADMAP.md` -- Phase 3 success criteria

### Prior Phase Context
- `.planning/phases/01-strategic-oversight-agent-teams-foundation/01-CONTEXT.md` -- Phase 1 decisions (team topology, agent spec patterns, pipeline order)
- `.planning/phases/02-portfolio-intelligence/02-CONTEXT.md` -- Phase 2 decisions (hybrid agent pattern, trade journal schema)

### Research
- `.planning/research/SUMMARY.md` -- Role analysis, pitfalls, phase ordering rationale
- `.planning/research/FEATURES.md` -- Sector Specialist and Execution Strategist role definitions

### Existing Agent Specs (debate flow reference)
- `agents/researchers/bull_researcher.md` -- Bull debate role (Sector Specialist joins this flow)
- `agents/researchers/bear_researcher.md` -- Bear debate role
- `agents/researchers/research_judge.md` -- Judge verdict role
- `agents/trader/executor.md` -- Current executor spec (Execution Strategist pre-processes for this)

### Key Source Files
- `src/agents_launcher.py` -- All task functions, pipeline flow, debate prep/merge
- `src/team_orchestrator.py` -- build_team_prompt (add new phase groups)
- `src/debate/helpers.py` -- Debate context preparation and merge functions
- `src/memory/situation_memory.py` -- BM25 memory system (pattern learning extends this)
- `src/journal/trade_journal.py` -- Trade journal (Phase 2, source data for pattern learning)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `task_prepare_debate()` and `task_merge_debates()` in agents_launcher.py -- Sector Specialist integrates into this existing debate flow
- `debate_context_{symbol}.json` -- Already contains technical, fundamental, sentiment data. Sector Specialist adds sector-specific enrichment.
- `SituationMemory` class with BM25 -- Pattern learning can extend existing memory banks or add new ones
- `trade_journal.py` -- Journal entries have outcome tags and R-multiples from Phase 2, ready for pattern analysis
- `save_state_atomic()` -- Use for all new JSON state files

### Established Patterns
- Agent spec pattern: Chinese, in `agents/`, with execution code and I/O schema
- `task_*()` function pattern in agents_launcher.py
- Debate flow: Bull → Bear → Judge. Sector Specialist can be inserted before or alongside.
- Config pattern: New sections in settings.yaml

### Integration Points
- Debate prep: `task_prepare_debate_context()` in `src/debate/helpers.py` -- add sector data
- Debate merge: `task_merge_debate_results()` -- incorporate Sector Specialist influence
- Execution: Between Risk Manager/Portfolio Strategist approval and actual order placement
- Memory: Extend existing `get_recent_eod_insights()` pattern for surfacing trade patterns

</code_context>

<specifics>
## Specific Ideas

No specific requirements from user -- full Claude discretion.

</specifics>

<deferred>
## Deferred Ideas

None -- discussion stayed within phase scope.

</deferred>

---

*Phase: 03-debate-execution-enhancement*
*Context gathered: 2026-04-03*
