---
name: sisyphus
description: "Project workflow engine for .sisyphus/ directory. Navigate plan tasks, track progress via checkbox updates, auto-save QA evidence, and enforce execution order. Triggers: 'next task', 'pick up task', 'work on plan', 'what's next', 'sisyphus', 'plan status', 'mark task done'."
---

# Sisyphus Workflow Engine

Manage the `.sisyphus/` project plan — task navigation, progress tracking, evidence collection, and plan state management.

## Directory Structure

```
.sisyphus/
├── PROJECT.md              # Project overview, constraints, decisions
├── plans/*.md               # Detailed task plans (waves, tasks, QA scenarios)
├── drafts/*.md              # Early-stage / uncommitted docs
└── evidence/                # QA verification artifacts
    task-{N}-{slug}.{ext}   # Naming: task number + scenario slug
```

## Core Workflow

### 1. Load Project Context

When starting any work session or when asked "what's next":

1. Read `.sisyphus/PROJECT.md` for constraints, scope, and decisions
2. Read relevant plan file(s) from `.sisyphus/plans/`
3. Identify current progress (checkboxes in plan)

### 2. Find Next Task

Scan plan for incomplete tasks. Apply dependency rules:

- Tasks marked `[x]` are DONE — skip
- Tasks marked `- [ ]` are TODO
- Check **Blocked By** — task cannot start until blockers are done
- Check **Parallel Group** — tasks in same wave can run concurrently
- Prefer tasks on the critical path
- Respect intern/you allocation — never pick intern tasks for yourself

Priority order:
1. Blocker tasks (other tasks depend on them)
2. Critical path tasks (longest chain of dependencies)
3. Tasks whose dependencies are all complete
4. Newest available wave

### 3. Execute Task

Follow the task spec exactly:

1. Read full task description from plan
2. Read **What to do** section — this is the spec
3. Read **Acceptance Criteria** — this must pass
4. Do NOT add features beyond the spec (guardrails in PROJECT.md)
5. Do NOT skip anything in the spec

### 4. Run QA Scenarios

Each task has **QA Scenarios** with specific verification steps.

After implementing a task:

1. Execute every QA scenario listed for that task
2. Use the specified tool (Bash, curl, python, jq, etc.)
3. Capture the output
4. Save evidence (see Evidence section below)
5. If any scenario fails, fix and re-run

### 5. Save Evidence

After each QA scenario passes, auto-save output:

```
.sisyyphus/evidence/task-{N}-{scenario-slug}.{ext}
```

Where:
- `{N}` = task number (e.g., `0.3`, `7`, `14`)
- `{scenario-slug}` = lowercase, hyphenated scenario name from plan (e.g., `pgvector-start`, `ohlcv-download`)
- `{ext}` = `.txt` for command output, `.json` for structured data, `.md` for documentation

Implementation — use bash to capture:

```bash
# Capture command output to evidence file
python scripts/download_ohlcv.py --symbol LUNAUSDT --month 2022-05 2>&1 | tee .sisyphus/evidence/task-7-ohlcv-download.txt

# For structured output, redirect separately
duckdb -c "SELECT COUNT(*) FROM read_parquet('data/ohlcv/LUNAUSDT_2022-05.parquet')" > .sisyphus/evidence/task-7-ohlcv-count.txt
```

### 6. Mark Task Complete

After ALL acceptance criteria pass and ALL QA scenarios have evidence:

1. Edit the plan file
2. Change `- [ ]` to `- [x]` for that task's checkbox
3. Append completion status to the task's **Evidence** section in the plan (if present), e.g.:
   ```
   **Evidence**:
   - Existing evidence...
   - [NEW] Task completed. All QA scenarios passed. Evidence: task-{N}-*.txt
   ```

### 7. Commit

Task spec includes commit message and files. Use them:

```bash
git add {files_from_task_spec}
git commit -m "{message_from_task_spec}"
```

Do NOT amend commit messages — use the exact message from the task spec.

## Status Commands

### "plan status" / "what's next"

Show current project status:
1. Count done vs total tasks per wave
2. Show next available task(s) with dependency status
3. Highlight any blocked tasks waiting on dependencies

Output format:

```
Wave 0: [2/2] Blocker Resolution ✓
Wave 1: [1/5] Foundation
Wave 2: [0/8] Data Pipeline
Wave 3: [0/6] Detection + Classification
Wave 4: [0/5] Validation
Final: [0/4] Verification

Next available: Task 3 (Docker Compose Setup)
  Blocked by: Wave 0 ✓ (complete)
  Wave: 1, Priority: Foundation

Also available: Task 4, Task 5, Task 6 (same wave, no dependencies between them)
```

### "mark task {N} done"

1. Verify the task exists in the plan
2. Verify all acceptance criteria can be met (ask user to confirm if can't verify programmatically)
3. Update checkbox: `- [ ]` → `- [x]`
4. Add evidence note

## Rules

### Guardrails (from PROJECT.md)

Tasks MUST NOT violate these constraints:

- No more than 2 derivatives signals (funding rate + OI only)
- No automated test suite (manual scripts, agent-executed QA)
- No Bull/Bear/Judge debate
- No ML classifier (LLM zero-shot first)
- No real-time infrastructure (Kafka/WebSocket/Redis)
- No reranker in RAG
- No intern on critical path (LUNA validation is main developer task)

### Anti-Patterns

| Violation | Why Bad |
|-----------|---------|
| Skipping QA scenarios | Unverified work is incomplete work |
| Working on blocked tasks | Dependencies exist for a reason |
| Adding features beyond spec | Scope creep — guardrails exist |
| Picking intern tasks | They're assigned for a reason, you have your own |
| Not saving evidence | QA results must be reproducible |
| Changing task spec | Plan is the contract — implement, don't redesign |
| Working out of wave order | Wave dependencies are real — don't skip ahead |

## File Format Reference

### Plan Task Structure

Each task in the plan follows this pattern:

```markdown
- [ ] {N}. {Task Title}  ← Checkbox + number + title
  **What to do**:          ← The spec
  **Evidence**:             ← Completion evidence
  **Recommended Agent Profile**:
  **Parallelization**:      ← Dependencies and parallel info
  **References**:           ← URLs, docs
  **Acceptance Criteria**:  ← Must-pass checks
  **QA Scenarios**:         ← Verification steps with evidence paths
  **Commit**:               ← Message and files
```

### Evidence File Naming

Pattern: `task-{N}-{slug}.{ext}`

Examples from existing evidence:
- `task-0.3-pgvector-start.txt`
- `task-0.3-hybrid-query.txt`
- `task-0.3-versions.txt`
- `task-2-data-structure.txt`
- `task-4-config-load.txt`

### Checkbox States

- `- [ ]` = TODO (not started)
- `- [x]` = DONE (all QA passed, evidence saved)

No "in progress" state — either it's done or it isn't.
