# Sell Put Hermes MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy the Sell Put scorecard strategy into Hermes as a deterministic MVP for single-contract open scoring, hold scoring, candidate ranking, and Gateway cron invocation.

**Architecture:** Keep the scoring core inside `openclaw/skills/quant-options-strategy/` with small focused modules: dataclass models, scorecard calculations, Markdown formatting, and a Hermes-facing service wrapper. Gateway only imports the service for cron/API orchestration and does not own scoring logic.

**Tech Stack:** Python standard library dataclasses, unittest, FastAPI Gateway, existing OpenClaw skill layout.

---

### Task 1: Scorecard Models And Open Scoring

**Files:**
- Create: `openclaw/skills/quant-options-strategy/sellput_models.py`
- Create: `openclaw/skills/quant-options-strategy/sellput_scorecard.py`
- Test: `openclaw/skills/quant-options-strategy/tests/test_sellput_scorecard.py`

- [x] Write failing unittest tests for A/B/C open-score classification and risk warnings.
- [x] Run `python3 -m unittest openclaw/skills/quant-options-strategy/tests/test_sellput_scorecard.py -v` and verify imports fail because implementation does not exist.
- [x] Implement minimal dataclasses and score functions.
- [x] Re-run unittest and confirm green.

### Task 2: Hold Scoring And Candidate Ranking

**Files:**
- Modify: `openclaw/skills/quant-options-strategy/sellput_models.py`
- Modify: `openclaw/skills/quant-options-strategy/sellput_scorecard.py`
- Test: `openclaw/skills/quant-options-strategy/tests/test_sellput_scorecard.py`

- [x] Add failing tests for hold score 90+ => `TAKE_PROFIT`, hold 70-89 => `HOLD`, below 70 => `ADJUST_OR_HEDGE`.
- [x] Add failing test that chain scan returns only min-score candidates sorted descending.
- [x] Implement hold scoring and scan sorting.
- [x] Re-run unittest and confirm green.

### Task 3: Hermes Service And Markdown Formatter

**Files:**
- Create: `openclaw/skills/quant-options-strategy/sellput_formatter.py`
- Create: `openclaw/skills/quant-options-strategy/hermes_sellput.py`
- Test: `openclaw/skills/quant-options-strategy/tests/test_hermes_sellput.py`

- [x] Add failing tests for service output shape and formatted report content.
- [x] Implement service wrapper with `evaluate_open`, `evaluate_hold`, and `scan_candidates`.
- [x] Implement concise Markdown report rendering.
- [x] Re-run unittest and confirm green.

### Task 4: Gateway Deployment Hook

**Files:**
- Modify: `openclaw/gateway_app.py`
- Modify: `openclaw/skills/quant-options-strategy/SKILL.md`

- [x] Add Gateway cron endpoint `/api/cron/sellput-score`.
- [x] Register `quant-options-strategy` in heartbeat active skills.
- [x] Update skill docs with deployed module entry points.
- [x] Run `python3 -m py_compile openclaw/gateway_app.py openclaw/skills/quant-options-strategy/*.py`.

### Verification

- [x] Run all Sell Put unittests with `python3 -m unittest discover -s openclaw/skills/quant-options-strategy/tests -v`.
- [x] Run syntax checks on Gateway and skill modules.
- [x] Report any unavailable dependency limitations.
