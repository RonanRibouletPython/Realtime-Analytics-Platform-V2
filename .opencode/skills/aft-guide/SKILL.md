---
name: aft-guide
description: Reference guide for AFT (Agent File Toolkit) tree-sitter powered tools available in this devcontainer. Load this when you need to use AFT tools in IMPLEMENT or ARCHITECT sessions.
license: MIT
compatibility: opencode
---

## What AFT Does

AFT replaces the default read/write/edit tools with tree-sitter-aware versions.
Every operation addresses code by what it *is* — a function, a class, a type — not by line number.

AFT is pre-installed in this devcontainer via:
```
bunx --bun @cortexkit/aft-opencode@latest setup
```

---

## Tools Available in This Workflow

### Read and Inspect

**`aft_outline`** — List all symbols in a file or directory. Use this first to orient.
```json
{ "filePath": "src/ingestion/consumer.py" }
{ "directory": "src/ingestion/" }
{ "files": ["src/ingestion/consumer.py", "src/query/api.py"] }
```
Returns: symbol names, kind (function/class/method), line range, visibility.

**`aft_zoom`** — Read one specific function/class by name. ~40 tokens vs ~375 for a whole file.
```json
{ "filePath": "src/ingestion/consumer.py", "symbol": "process_batch" }
{ "filePath": "src/ingestion/consumer.py", "symbols": ["KafkaConsumer", "process_batch"] }
```
Returns: full source of the symbol with call-graph annotations (`calls_out`, `called_by`).

**`read`** — AFT-enhanced file reading with line numbers. Paginate large files.
```json
{ "filePath": "src/ingestion/consumer.py" }
{ "filePath": "src/ingestion/consumer.py", "startLine": 50, "endLine": 100 }
```

### Edit

**`edit` (symbol mode)** — Edit a function by name. Line-number free. Robust to file changes.
```json
{
  "filePath": "src/ingestion/consumer.py",
  "symbol": "process_batch",
  "content": "async def process_batch(self, messages: list[Message]) -> BatchResult:\n    ..."
}
```

**`edit` (find-replace mode)** — Exact string replacement with fuzzy fallback.
```json
{
  "filePath": "src/config.py",
  "oldString": "MAX_RETRIES = 3",
  "newString": "MAX_RETRIES = 8"
}
```

**`write`** — Write a full new file. Creates directories. Auto-formats.
```json
{ "filePath": "src/tracing/middleware.py", "content": "..." }
```

### Navigate

**`aft_navigate`** — Call graph and impact analysis.
```json
{ "op": "callers", "filePath": "src/...", "symbol": "process_batch", "depth": 2 }
{ "op": "call_tree", "filePath": "src/...", "symbol": "process_batch", "depth": 3 }
{ "op": "impact", "filePath": "src/...", "symbol": "process_batch", "depth": 2 }
```

Use `impact` before changing a function signature. Use `callers` to find all usages.

### Imports

**`aft_import`** — Language-aware import management for Python, TypeScript, etc.
```json
{ "op": "add", "filePath": "src/ingestion/consumer.py", "module": "opentelemetry.trace", "names": ["get_tracer"] }
{ "op": "organize", "filePath": "src/ingestion/consumer.py" }
```

### Safety

**`aft_safety`** — Checkpoints and undo before risky changes.
```json
{ "op": "checkpoint", "name": "before-tracing-integration" }
{ "op": "undo", "filePath": "src/ingestion/consumer.py" }
{ "op": "restore", "name": "before-tracing-integration" }
```

---

## The IMPLEMENT Loop

Always follow this pattern for each unit of work:

1. `aft_outline` the directory → understand structure
2. `aft_zoom` the target symbol → read the specific function
3. `aft_navigate` with `callers` → check what calls this (if modifying an existing symbol)
4. `aft_safety` checkpoint → before any destructive change
5. `edit` with symbol mode → write the new implementation
6. Run tests → confirm nothing broke

---

## Token Efficiency

| Operation | Tokens |
|-----------|--------|
| Full 500-line file via `read` | ~375 |
| One function via `aft_zoom` | ~40 |
| Directory structure via `aft_outline` | ~60 |

For a multi-step implementation task, the savings compound quickly.
Always zoom before editing. Never read a full file when you need one function.