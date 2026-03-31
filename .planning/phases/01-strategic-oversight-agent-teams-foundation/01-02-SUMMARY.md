---
phase: 01-strategic-oversight-agent-teams-foundation
plan: 02
subsystem: agents
tags: [agent-specs, cio, macro-strategist, eod-review, yaml-config, model-tiers]

# Dependency graph
requires: []
provides:
  - "CIO agent specification (agents/strategic/cio.md) with Opus model tier"
  - "Macro Strategist agent specification (agents/strategic/macro_strategist.md) with Sonnet model tier"
  - "EOD Review agent specification (agents/strategic/eod_review.md) with Sonnet model tier"
  - "Strategic oversight configuration sections in config/settings.yaml"
  - "Model tier map for all 16 agent roles in settings.yaml"
affects: [01-03-PLAN, 01-04-PLAN, 01-05-PLAN, 01-07-PLAN]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "YAML frontmatter in agent specs for model tier assignment"
    - "Quantitative stance triggers in CIO spec to prevent LLM neutrality bias"
    - "Explicit LLM data hallucination warning in Macro Strategist spec"
    - "Observation-not-directive framing in EOD Review spec to prevent circular reasoning"

key-files:
  created:
    - agents/strategic/cio.md
    - agents/strategic/macro_strategist.md
    - agents/strategic/eod_review.md
  modified:
    - config/settings.yaml

key-decisions:
  - "CIO uses Opus tier for critical daily stance decisions; Macro/EOD use Sonnet for analytical reasoning"
  - "Quantitative VIX/EMA triggers defined to prevent CIO rubber-stamping neutral every day"
  - "EOD Review frames output as observations, not directives, to break circular reasoning loop"
  - "Model tier map covers all 16 agent roles in a single settings.yaml section"

patterns-established:
  - "Strategic agent spec pattern: YAML frontmatter (model, tools) + Chinese role description + quantitative rules + execution code + JSON output schema"
  - "Config convention: strategic role tunables in dedicated settings.yaml sections (cio:, macro:, eod_review:)"

requirements-completed: [TEAMS-02, TEAMS-03]

# Metrics
duration: 4min
completed: 2026-03-31
---

# Phase 1 Plan 02: Strategic Role Agent Specs Summary

**Three Chinese-language strategic agent specs (CIO/Macro/EOD) with YAML model tier frontmatter and quantitative decision rules, plus settings.yaml strategic config sections and full model tier map**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-31T15:02:05Z
- **Completed:** 2026-03-31T15:05:58Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- Created CIO agent spec with Opus model tier, quantitative stance triggers (VIX/EMA thresholds), halt_trading mechanism, and daily_directive.json output schema
- Created Macro Strategist agent spec with Sonnet model tier, explicit warning against LLM data hallucination, cross-asset data sources (VIX, TLT, UUP, yield curve), and macro_outlook.json output schema
- Created EOD Review agent spec with Sonnet model tier, thesis drift detection framework, observation-not-directive framing, confidence decay mechanism, and eod_review.json output schema
- Added strategic oversight configuration to settings.yaml: CIO thresholds, macro tickers/lookback, EOD decay weights/drift thresholds, and comprehensive model_tiers map for all 16 agents

## Task Commits

Each task was committed atomically:

1. **Task 1: Create strategic role agent specs** - `8340855` (feat)
2. **Task 2: Add strategic role configuration to settings.yaml** - `9aff459` (feat)

## Files Created/Modified
- `agents/strategic/cio.md` - CIO agent spec: daily stance setter with quantitative triggers, Opus model
- `agents/strategic/macro_strategist.md` - Macro Strategist spec: cross-asset intelligence, Sonnet model
- `agents/strategic/eod_review.md` - EOD Review spec: P&L attribution and thesis drift detection, Sonnet model
- `config/settings.yaml` - Added cio:, macro:, eod_review:, model_tiers: sections

## Decisions Made
- CIO assigned Opus model tier (critical daily decisions per TEAMS-03); Macro Strategist and EOD Review assigned Sonnet (analytical reasoning, not final decisions)
- Defined explicit quantitative stance triggers (VIX > 30 + inverted curve = defensive, VIX < 18 + bullish EMAs = aggressive) to counter LLM neutrality bias (Research Pitfall 1)
- Macro Strategist spec includes bold warning against using LLM training data (Research Pitfall 2)
- EOD Review frames all output as observations ("today's P&L was X because Y") not directives ("tomorrow should be more aggressive") to prevent circular reasoning (Research Pitfall 4)
- halt_trading threshold set at VIX > 40 (configurable via cio.halt_on_vix_above)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Known Stubs
None - all specs are complete with full content as specified.

## Next Phase Readiness
- Agent specs ready for Plan 01-03 (Macro Strategist + CIO task functions) and Plan 01-04 (EOD Review task function)
- settings.yaml configuration ready for task function implementations to read tunables
- model_tiers map ready for Plan 01-07 (Team Orchestrator) to assign models when spawning teammates

## Self-Check: PASSED
- [x] agents/strategic/cio.md exists
- [x] agents/strategic/macro_strategist.md exists
- [x] agents/strategic/eod_review.md exists
- [x] config/settings.yaml loads with all new sections
- [x] Commit 8340855 exists
- [x] Commit 9aff459 exists

---
*Phase: 01-strategic-oversight-agent-teams-foundation*
*Completed: 2026-03-31*
