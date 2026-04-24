# Learning Agents for OpenCode

Structured engineering education as an OpenCode agent workflow.
**Goal:** Understanding before implementation, tradeoffs before code.

---

## Structure

```
.
├── opencode.json                          # OpenCode config — wires instructions + permissions
├── AGENTS.md                              # Root rules, loaded automatically by OpenCode
│
├── .opencode/
│   ├── agents/
│   │   ├── mentor.md                      # Primary agent — orchestrator and entry point
│   │   ├── concept.md                     # Subagent — concept teaching (no edits allowed)
│   │   ├── architect.md                   # Subagent — design sessions with AFT reads
│   │   ├── implement.md                   # Subagent — guided implementation with AFT
│   │   └── review.md                      # Subagent — retrospective + session notes
│   │
│   ├── skills/
│   │   ├── learning-principles/SKILL.md   # Core teaching rules, loaded on demand
│   │   ├── aft-guide/SKILL.md             # AFT tool reference, loaded on demand
│   │   └── distributed-systems-map/SKILL.md  # Concept dependency graph
│   │
│   └── context/
│       ├── core/principles.md             # Loaded automatically (opencode.json instructions)
│       └── project-intelligence/stack.md  # Your tech stack — fill this in
│
└── .learning/
    ├── progress.md                        # Session history and concept status
    └── sessions/
        ├── TEMPLATE.md                    # Template for session notes
        └── YYYY-MM-DD-<concept>.md        # Created by REVIEW after each session
```

---

## How OpenCode Loads This

| File type | How it loads |
|-----------|-------------|
| `AGENTS.md` | Automatically, every session |
| `.opencode/context/core/principles.md` | Automatically via `opencode.json instructions` |
| `.opencode/context/project-intelligence/stack.md` | Automatically via `opencode.json instructions` |
| `.opencode/agents/*.md` | On agent switch (Tab) or `@mention` |
| `.opencode/skills/*/SKILL.md` | On demand — agent calls the `skill` tool by name |

---

## Setup

**1. Drop these files into your project root**

```
cp -r .opencode opencode.json AGENTS.md .learning /your-project/
```

**2. Fill in your stack details**

Edit `.opencode/context/project-intelligence/stack.md` with your actual project structure,
tech stack, directory layout, and constraints. The more specific this is, the more
codebase-aware the agents will be.

**3. AFT is already installed in your devcontainer**

The Dockerfile runs `bunx --bun @cortexkit/aft-opencode@latest setup` which wires AFT
into OpenCode globally. No project-level configuration needed for AFT.

**4. Commit everything**

```bash
git add .opencode opencode.json AGENTS.md .learning
git commit -m "add: learning agent workflow"
```

The context and session notes become part of your repo — available every time you open the devcontainer.

---

## Starting a Session

Open the devcontainer, navigate to your project, run OpenCode:

```bash
opencode
```

Switch to the MENTOR agent with **Tab** (it appears in the primary agent cycle).

Or start directly:
```bash
opencode --agent mentor
```

Then just describe your intent:

```
> I want to understand Kafka consumer group rebalancing

> Let's continue the distributed tracing session from yesterday

> I already know circuit breakers — can we go straight to designing one?

> I want to understand continuous aggregates in TimescaleDB and implement them
```

MENTOR reads your progress file, asks one clarifying question, and routes to the right phase.

---

## The Four Phases

```
CONCEPT → ARCHITECT → IMPLEMENT → REVIEW
```

You can start at any phase. You can skip phases explicitly. You can stop after CONCEPT
if today is just a learning day. The pipeline is a guide, not a constraint.

| Phase | Subagent | What happens |
|-------|----------|-------------|
| 1 | `@concept` | Socratic teaching, mental model building, no code |
| 2 | `@architect` | 2–3 design approaches with tradeoffs, you choose, design doc written |
| 3 | `@implement` | AFT-guided step-by-step implementation, one unit at a time |
| 4 | `@review` | Retrospective, session note written, next steps suggested |

---

## AFT Integration

AFT (Agent File Toolkit) is a tree-sitter powered semantic layer over your codebase.
The IMPLEMENT and ARCHITECT agents use it automatically.

**Why this matters for learning:**
- `aft_zoom` reads one function by name (~40 tokens vs ~375 for a full file)
- `aft_outline` maps a directory's structure before any design decision
- `aft_navigate` shows what calls a function before you change its signature
- `edit` in symbol mode edits by function name — never breaks on line number shifts

This means the agent works with *your actual code*, not a generic template.
Every implementation decision is grounded in what already exists.

---

## Customising the Agents

Every agent is a markdown file. Edit them directly to change behaviour:

```bash
# Change CONCEPT's teaching style
nano .opencode/agents/concept.md

# Adjust IMPLEMENT's code quality rules
nano .opencode/agents/implement.md

# Add your project's specific pitfalls to the principles skill
nano .opencode/skills/learning-principles/SKILL.md
```

No compilation. No vendor lock-in. The agents are yours.

---

## Skills Reference

| Skill name | When it loads | What it contains |
|------------|--------------|-----------------|
| `learning-principles` | Start of every agent session | Full teaching rules and anti-patterns |
| `aft-guide` | When IMPLEMENT or ARCHITECT needs AFT syntax | Tool reference with examples |
| `distributed-systems-map` | When REVIEW suggests next steps | Concept dependency graph |

Agents call these on demand via the OpenCode `skill` tool — they're not loaded into every
session automatically, which keeps the context window lean.