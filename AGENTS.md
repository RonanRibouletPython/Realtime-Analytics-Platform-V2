# Learning Workflow — Project Rules

This project uses a structured **learning agent system** built on OpenCode.
The goal is guided engineering education: understanding before implementation, tradeoffs before code.

---

## How This Works

Five agents form a pipeline. MENTOR orchestrates. The others are subagents invoked by MENTOR or via `@mention`.

| Agent | Mode | Purpose |
|-------|------|---------|
| `mentor` | primary | Orchestrates sessions, reads learning history, routes to subagents |
| `concept` | subagent | Teaches WHY before HOW, no code edits allowed |
| `architect` | subagent | Design sessions with explicit tradeoffs, produces design docs |
| `implement` | subagent | Step-by-step guided implementation using AFT tools |
| `review` | subagent | Retrospective, session notes, progress tracking |

---

## Context Files

CRITICAL: Load these files when relevant to the task. Do NOT preemptively load all of them.

- Project tech stack and constraints: `@.opencode/context/project-intelligence/stack.md`
- Core teaching principles: `@.opencode/context/core/principles.md`

---

## AFT Tools Available

AFT (Agent File Toolkit) is installed in this devcontainer. It provides tree-sitter powered
semantic tools that replace the default read/write/edit with enhanced versions.

**Use these tools in IMPLEMENT and ARCHITECT sessions:**

- `aft_outline` — list all symbols in a file without reading it fully
- `aft_zoom` — read one specific function/class by name (~40 tokens vs ~375 for full file)
- `read` — AFT-enhanced, line-numbered, paginate with startLine/endLine
- `edit` (symbol mode) — edit a function by name, not by line number
- `aft_navigate` — understand call graphs before changing a function

**AFT zoom example** — use this before modifying any function:
```
aft_zoom({ "filePath": "src/ingestion/consumer.py", "symbol": "process_batch" })
```

**AFT outline example** — use this to orient before starting implementation:
```
aft_outline({ "directory": "src/ingestion/" })
```

Full AFT skill: load `aft-guide` via the skill tool when needed.

---

## Learning History

- Progress tracker: `.learning/progress.md`
- Session notes: `.learning/sessions/YYYY-MM-DD-<topic>.md`
- Session template: `.learning/sessions/TEMPLATE.md`

MENTOR reads `.learning/progress.md` at the start of every session.
REVIEW writes to both files at the end of every session.

---

## Session Entry Point

The user starts every learning session with the MENTOR agent (Tab to switch, or `opencode --agent mentor`).
MENTOR asks one clarifying question before routing to a subagent.

Do not start implementing anything without passing through CONCEPT and ARCHITECT phases,
unless the user explicitly states they are skipping a phase.