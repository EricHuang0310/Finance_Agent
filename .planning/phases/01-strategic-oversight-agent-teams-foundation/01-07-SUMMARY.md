---
phase: 01-strategic-oversight-agent-teams-foundation
plan: 07
subsystem: team-orchestration
tags: [agent-teams, orchestration, cio-lead, phased-spawning]
dependency_graph:
  requires: [01-02, 01-03, 01-04, 01-05, 01-06]
  provides: [team-orchestrator-module, programmatic-pipeline-entry]
  affects: [agents_launcher, pipeline-execution-mode]
tech_stack:
  added: []
  patterns: [cio-as-lead, phased-teammate-spawning, config-driven-model-tiers]
key_files:
  created:
    - src/team_orchestrator.py
  modified:
    - src/agents_launcher.py
decisions:
  - "build_team_prompt() generates dynamic prompt from settings.yaml model tiers and CIO agent spec"
  - "CIO spec embedded verbatim in Lead prompt so Lead IS the CIO (no separate CIO teammate)"
  - "AGENT_TEAMS_PROMPT constant preserved with deprecation comment for backward compatibility"
metrics:
  duration: 120s
  completed: "2026-04-03T00:50:12Z"
---

# Phase 1 Plan 7: Team Orchestrator Module Summary

Programmatic TeamCreate orchestrator with CIO as Lead agent, phased teammate spawning from settings.yaml model tiers, and standalone fallback via --run flag.

## What Was Built

### src/team_orchestrator.py (242 lines, new)
The capstone module that replaces the manual AGENT_TEAMS_PROMPT text blob with a programmatic, config-driven orchestration prompt generator. Key functions:

- **`build_team_prompt(execute, notify)`**: Generates the complete CIO Lead agent prompt that includes:
  - Full CIO agent spec (loaded from `agents/strategic/cio.md`)
  - 5 Phase Groups with phased spawning instructions (D-02)
  - Model tier per role from `config/settings.yaml` (TEAMS-03)
  - Graceful degradation table (D-12): only Risk Manager failure is hard stop
  - Communication protocol (D-09): SendMessage for coordination, JSON for data
  - halt_trading check after CIO directive (CIO-02)

- **`run_agent_teams_pipeline(execute, notify)`**: Prints the prompt for consumption by Claude Code CLI.

- **`run_standalone_fallback(execute, notify)`**: Delegates to `run_full_pipeline()` (D-03).

- **CLI**: `python -m src.team_orchestrator` prints prompt; `--run` falls back to standalone.

### src/agents_launcher.py (modified)
- `--prompt` flag now delegates to `build_team_prompt()` instead of printing the hardcoded `AGENT_TEAMS_PROMPT`
- `AGENT_TEAMS_PROMPT` constant preserved with deprecation comment for backward compatibility
- `--run` flag still calls `run_full_pipeline()` directly (D-03 fallback intact)

## Phase Groups in Generated Prompt

| Group | Agents | Model | Spawning |
|-------|--------|-------|----------|
| 1 | Macro Strategist + CIO (Lead direct) | sonnet / Lead | Sequential, 1 teammate |
| 2 | Symbol Screener, Market/Tech/Sentiment Analysts | haiku | Parallel, 4 teammates |
| 2.5 | Position Reviewer + Decision Engine (Lead direct) | haiku / Lead | Sequential, 1 teammate |
| 3 | Bull/Bear Researchers + Judge (per symbol) | sonnet/opus | Per-candidate, 3 teammates |
| 4 | Risk Manager + Executor | haiku | Sequential, 1-2 teammates |
| 5 | Reporter + EOD Review + Reflection | haiku/sonnet/opus | Parallel, 2-3 teammates |

## Decisions Made

1. **CIO spec embedded verbatim**: The Lead reads the full CIO agent spec inline in the prompt, so the Lead IS the CIO. No separate CIO teammate needed (saves tokens, matches D-01).
2. **Dynamic model tiers from config**: Model assignments loaded from `settings.yaml` at prompt generation time, not hardcoded in Python.
3. **Backward compatibility preserved**: Old `AGENT_TEAMS_PROMPT` kept with deprecation comment so existing scripts referencing it still work.

## Deviations from Plan

None -- plan executed exactly as written.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| 1 | b40a1f7 | Create team_orchestrator.py with phased spawning |
| 2 | 6782e8a | Update agents_launcher --prompt to use team_orchestrator |

## Known Stubs

None. All functions are fully wired to real data sources (settings.yaml, agent specs, state_dir).

## Self-Check: PASSED
