# Learning Agents for OpenCode - v2

Structured engineering education as an OpenCode agent workflow.
**Goal:** Understanding before implementation, tradeoffs before code.

---

## What's new in v2

| Change | Why |
|--------|-----|
| `@debug` agent | Routes errors by type - code mistake vs conceptual gap. No more silent self-patching. |
| `@test` agent | Split from IMPLEMENT. Tests are written as a learning check, not an afterthought. |
| `@scout` agent | Fetches live library docs before design or implementation. Prevents stale-API mistakes. |
| `@challenge` agent | Generates 2–3 exercises after each session. MENTOR surfaces them as a next-session warm-up. |
| Recap mode in `@concept` | Mid-session confusion routes to a 5-minute targeted recap, not a full session restart. |
| Lazy skill loading | Skills load on demand per agent, not globally. Keeps context windows lean. |
| `principles.md` | Always-loaded session rules. Fill it in once; it applies to every session. |
| `stack.md` | Always-loaded codebase context. The more specific it is, the better agents design and implement. |

---

## Structure

```
.
├── opencode.json                              # OpenCode config - wires instructions + permissions
├── AGENTS.md                                  # Root rules, loaded automatically by OpenCode
│
├── .opencode/
│   ├── agents/
│   │   ├── mentor.md                          # Primary - orchestrator and entry point
│   │   ├── concept.md                         # Subagent - Socratic concept teaching (no edits)
│   │   ├── architect.md                       # Subagent - design sessions with AFT + @scout
│   │   ├── implement.md                       # Subagent - guided implementation with AFT
│   │   ├── review.md                          # Subagent - retrospective + session notes
│   │   ├── debug.md                  ✦ new    # Subagent - error diagnosis and routing
│   │   ├── test.md                   ✦ new    # Subagent - test writing as a learning check
│   │   ├── scout.md                  ✦ new    # Subagent - live library doc fetcher (MVI)
│   │   └── challenge.md              ✦ new    # Subagent - spaced repetition exercise generator
│   │
│   ├── skills/
│   │   ├── learning-principles/SKILL.md       # Extended teaching rules - loaded on demand
│   │   ├── aft-guide/SKILL.md                 # AFT tool reference - loaded on demand
│   │   └── distributed-systems-map/SKILL.md   # Concept dependency graph - domain only
│   │
│   └── context/
│       ├── core/principles.md                 # Session rules - loaded automatically
│       └── project-intelligence/stack.md      # Your tech stack - fill this in ← start here
│
└── .learning/
    ├── progress.md                            # Concept status and session history
    ├── sessions/
    │   ├── TEMPLATE.md                        # Session note template
    │   └── YYYY-MM-DD-<concept>.md            # Written by REVIEW after each session
    └── challenges/
        └── YYYY-MM-DD-<concept>.md   ✦ new   # Written by CHALLENGE, surfaced by MENTOR
```

---

## How OpenCode Loads This

| File | How it loads |
|------|-------------|
| `AGENTS.md` | Automatically, every session |
| `.opencode/context/core/principles.md` | Automatically via `opencode.json instructions` |
| `.opencode/context/project-intelligence/stack.md` | Automatically via `opencode.json instructions` |
| `.opencode/agents/*.md` | On agent switch (Tab) or `@mention` |
| `.opencode/skills/*/SKILL.md` | On demand - agent calls the `skill` tool by name |

Skills load lazily. `distributed-systems-map` only loads when the topic is in that domain.
`aft-guide` only loads when AFT tools are about to be used. This keeps context windows lean.

---

## Setup

**1. Drop these files into your project root**

```bash
cp -r .opencode opencode.json AGENTS.md .learning /your-project/
```

**2. Fill in `stack.md` - do this first**

```bash
nano .opencode/context/project-intelligence/stack.md
```

This file is the codebase context that ARCHITECT and IMPLEMENT use to ground every design
and implementation in your real code. Fill in:

- What your project does (one paragraph)
- Your actual tech stack with real versions
- Your directory layout with key classes noted
- Key components IMPLEMENT will zoom into with AFT
- External services and how to reach them locally
- Settled decisions that agents should not re-open
- Known gaps - what isn't built yet

The more specific this file is, the more codebase-aware the agents become.
Generic entries produce generic designs. Specific entries produce specific ones.

**3. Check `principles.md`**

```bash
nano .opencode/context/core/principles.md
```

This file ships with sane defaults. Read it and adjust anything that doesn't match how
you want to work. The session rules and agent conduct rules are the main things to tune.

**4. AFT is already installed in your devcontainer**

The Dockerfile runs:
```bash
bunx --bun @cortexkit/aft-opencode@latest setup
```
This wires AFT into OpenCode globally. No project-level configuration needed.

**5. Commit everything**

```bash
git add .opencode opencode.json AGENTS.md .learning
git commit -m "add: learning agent workflow v2"
```

Context files and session notes become part of your repo - available every time you open
the devcontainer. Your learning history travels with the code.

---

## Starting a Session

```bash
opencode
```

Switch to MENTOR with **Tab**, or start directly:

```bash
opencode --agent mentor
```

Describe your intent:

```
> I want to understand Kafka consumer group rebalancing

> Let's continue the distributed tracing session from yesterday

> I already know circuit breakers - can we design one?

> Something broke mid-session - [paste error]
```

MENTOR reads your progress file, offers a warm-up challenge if one is pending, asks
one clarifying question, and routes to the right phase.

---

## The Full Session Flow

```
[warm-up challenge?] → CONCEPT → ARCHITECT → IMPLEMENT → TEST → REVIEW → CHALLENGE
                                                  ↕
                                               DEBUG
                                                  ↕
                                      CONCEPT (recap mode)
```

You can start at any phase. You can skip phases explicitly. The pipeline is a guide,
not a constraint.

| Phase | Agent | What happens |
|-------|-------|-------------|
| 0 (optional) | `@mentor` | Surfaces a pending challenge from last session as warm-up |
| 1 | `@concept` | Socratic teaching, mental model, understanding check, no code |
| 1b (on-demand) | `@concept` (recap) | 5-minute targeted re-explanation when stuck mid-session |
| 2 | `@architect` | 2–3 design approaches, you choose and defend, design doc written |
| 2b (on-demand) | `@scout` | Fetches live library docs before committing to an approach |
| 3 | `@implement` | AFT-guided step-by-step implementation, one unit at a time |
| 3b (on-demand) | `@debug` | Diagnoses errors - code mistake vs conceptual gap |
| 4 | `@test` | Writes tests per unit; user names cases first; routes failures to @debug |
| 5 | `@review` | Retrospective, session note, next concept suggested |
| 6 | `@challenge` | 2–3 exercises grounded in what was built - stored for next warm-up |

---

## The Four New Agents

### `@debug` - error diagnosis, not silent fixing

When IMPLEMENT or TEST hits a runtime error, it does not attempt to fix it.
It routes to @debug, which reads the code, traces the failure, and returns one of:

- **`code_mistake`** - bug in the implementation. Debug explains what broke and why,
  suggests the fix. IMPLEMENT applies it.
- **`concept_gap`** - the error reveals a misunderstanding. Debug routes back to MENTOR,
  which invokes a CONCEPT recap.
- **`environment`** - missing dependency, wrong config, service not running.

The distinction matters. A fix the user doesn't understand is a future bug they won't diagnose.

### `@test` - test writing as an understanding check

Before writing tests, @test asks the user: "What would you test for this function?"
The answer reveals more about understanding than any verbal explanation.

Test coverage bar is deliberately low for a learning session: happy path + one failure mode.
You're writing for understanding, not coverage metrics.

### `@scout` - live docs before stale training data causes design mistakes

If ARCHITECT or IMPLEMENT is about to use an external library, @scout fetches the current
API surface from the primary docs source (not blogs, not Stack Overflow) and returns only
the minimum viable slice needed for the task.

This matters especially for libraries with active development - the API in training data
may be deprecated or renamed. Scout surfaces version-specific notes explicitly.

### `@challenge` - spaced repetition that ships with the workflow

After every REVIEW, @challenge generates 2–3 exercises based on what was actually built:

- **Broken code diagnosis** - a realistic bug introduced into something you wrote
- **Write from scratch** - a spec for a function you already implemented, without looking
- **Tradeoff reasoning** - a scenario requiring you to apply the tradeoff table

Exercises are stored in `.learning/challenges/`. MENTOR surfaces them at the next session
start as an optional warm-up.

---

## AFT Integration

AFT (Agent File Toolkit) is a tree-sitter powered semantic layer over your codebase.
IMPLEMENT and ARCHITECT use it automatically.

| Tool | What it does | Why it matters |
|------|-------------|---------------|
| `aft_zoom` | Reads one function by name (~40 tokens vs ~375 for a full file) | Keeps context lean |
| `aft_outline` | Maps a directory's symbol structure | Grounds design in real code shape |
| `aft_navigate` | Shows callers/callees of a function | Prevents signature-change surprises |
| `edit` (symbol mode) | Edits by function name, not line number | Robust to file changes |

IMPLEMENT and DEBUG never modify code without first reading it with AFT.
The design is always grounded in what actually exists.

---

## Filling in `stack.md` - quick reference

The file ships with annotated examples. Here's what each section is for:

| Section | What to write | Why agents need it |
|---------|--------------|-------------------|
| Project overview | One paragraph on what the system does | Routes concept chains to relevant patterns |
| Tech stack table | Real versions, not approximate | @scout knows which API version to fetch |
| Directory layout | Annotated tree with key classes noted | @architect outlines the right dirs first |
| Key components | Symbol + file + one-line description | @implement zooms the right things |
| External services | Service name, role, local dev address | IMPLEMENT knows where to point test config |
| Settled decisions | Things that are not up for debate | Prevents agents re-opening closed questions |
| Known gaps | What isn't built yet | MENTOR uses this for next-session routing |
| Run commands | Actual commands for your setup | IMPLEMENT suggests the right test command |

---

## Customising the Agents

Every agent is a markdown file. Edit them directly:

```bash
# Adjust CONCEPT's depth levels
nano .opencode/agents/concept.md

# Add domain-specific pitfalls to DEBUG's classification
nano .opencode/agents/debug.md

# Change CHALLENGE's exercise ratio (more broken-code, fewer write-from-scratch)
nano .opencode/agents/challenge.md
```

No compilation. No vendor lock-in. The agents are yours.

---

## Skills Reference

| Skill | Loaded by | When | What it contains |
|-------|-----------|------|-----------------|
| `learning-principles` | concept, review, challenge | Start of session | Full teaching rules and anti-patterns |
| `aft-guide` | implement, architect | Before AFT tool use | Tool reference with examples |
| `distributed-systems-map` | concept, architect | Domain-relevant sessions only | Concept dependency graph |

Skills load on demand, not at startup. The `distributed-systems-map` skill does not load
during a session on circuit breakers - only on distributed systems topics.

---

## `.learning/` Reference

| File | Written by | Read by | Purpose |
|------|-----------|---------|---------|
| `progress.md` | review | mentor | Concept status, what's in progress, known gaps |
| `sessions/YYYY-MM-DD-[concept].md` | review | mentor, architect | Session narrative, design decisions, what was hard |
| `sessions/design-[topic]-[date].md` | architect | implement | Design doc - the blueprint for implementation |
| `challenges/YYYY-MM-DD-[concept].md` | challenge | mentor | Exercises for next session warm-up |

These files are the institutional memory of the workflow. They persist across sessions,
accumulate over time, and make each session more context-aware than the last.