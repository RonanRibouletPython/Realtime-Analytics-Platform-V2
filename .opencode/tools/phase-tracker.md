---
description: >
    File-backed session state persistence tool. Provides atomic read/write
    operations on .opencode/phase_state.json. Used exclusively by the Session
    Orchestrator — no other agent calls this tool directly.
name: Phase Tracker
type: tool
---

# Phase Tracker

A lightweight key-value persistence tool scoped to `.opencode/phase_state.json`.
It is not an agent — it has no reasoning capability. It is a pure I/O primitive
that the Session Orchestrator calls to read and write session state.

## Operations

### `read_state() → dict`

Reads `.opencode/phase_state.json` and returns the parsed object.

Returns the default initial state if the file does not exist:

```json
{
  "schema_version": 1,
  "current_phase": "[STARTING_PHASE]",
  "current_step": "[STARTING_STEP_SLUG]",
  "step_status": "in_progress",
  "completed_steps":[],
  "rejection_count": 0,
  "last_review_verdict": null,
  "last_review_summary": null,
  "blocked_reason": null,
  "session_log":[]
}