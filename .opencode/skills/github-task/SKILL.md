---
name: github-task
description: "Create GitHub issues with labels, milestone, assignees, and body content. Use for importing tasks from plans into GitHub Projects."
license: MIT
compatibility: opencode
metadata:
  category: project-management
  triggers: create issue, add task, import task, github issue
---

## What I Do

Create GitHub issues programmatically with full metadata:
- Title and body content
- Labels (comma-separated)
- Milestone (by number or name)
- Assignees (GitHub usernames)
- Add to GitHub Project automatically

## When to Use Me

Use this skill when:
- Importing tasks from execution plans into GitHub
- Creating structured issues with acceptance criteria and QA scenarios
- Bulk task creation for project management

## Parameters Required

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | YES | Issue title (e.g., "0.1 Verify Binance Historical Data") |
| `body` | string | YES | Full issue body with sections: What to do, Acceptance Criteria, QA Scenarios, etc. |
| `labels` | string | NO | Comma-separated labels (e.g., "wave-0,blocker") |
| `milestone` | string/number | NO | Milestone number or name (e.g., "Wave 0" or 1) |
| `assignees` | string | NO | Comma-separated GitHub usernames |

## How to Execute

### Step 1: Check for Duplicates
```bash
# Extract 2-3 key terms from the title and search
gh issue list --search "{key terms}" --state all --json number,title,state,url
```
Extract the most meaningful nouns from the title (strip task numbers, wave prefixes). For example, "0.1 Verify Binance Historical Data" → search "Binance historical data".
Interpreting results:

- No matches → proceed to Step 2
- Open match found → stop and inform the user, show the matching issue URL, ask whether to proceed or link to the existing issue instead
- Closed match found → flag it but proceed with creation, noting in the issue body: > Possible duplicate of #{number} (closed)

### Step 2: Resolve Milestone Number (if using name)

```bash
# Get milestone number from name
MILESTONE_NUM=$(gh api repos/{owner}/{repo}/milestones --jq '.[] | select(.title=="Wave 0") | .number')
[ -z "$MILESTONE_NUM" ] && echo "ERROR: milestone not found" && exit 1
```

### Step 3: Create Issue

```bash
gh issue create \
  --title "{title}" \
  --label "{labels}" \
  --milestone "{milestone_number}" \
  --assignee "{assignees}" \
  --body "{body}"
```

**Note**: If milestone is a name, resolve to number first via API.

## Body Template Structure

Use this structure for task bodies:

```markdown
## What to do
{description of the task}

## References
{API endpoints, documentation links, relevant files}

## Acceptance Criteria
- [ ] {criterion 1}
- [ ] {criterion 2}
- [ ] {criterion 3}

## QA Scenarios
```
Scenario: {scenario name}
  Tool: Bash (curl)
  Steps:
    1. {step 1}
    2. {step 2}
  Expected Result: {expected outcome}
  Evidence: .sisyphus/evidence/task-{id}-{slug}.txt
```

## Parallelization
- **Can Run In Parallel**: YES/NO (with Tasks X, Y, Z)
- **Blocks**: {tasks that depend on this}
- **Blocked By**: {tasks this depends on}

## Commit
- Message: `{commit_message}`
- Files: `{files_to_commit}`
```

## Labels Available

Standard labels for crypto-analyser:

| Label | Color | Description |
|-------|-------|-------------|
| `wave-0` | FF6B6B | Blocker Resolution |
| `wave-1` | 4ECDC4 | Foundation |
| `wave-2` | 45B7D1 | Data Pipeline |
| `wave-3` | 96CEB4 | Detection + Classification |
| `wave-4` | FFEAA7 | Validation + Evaluation |
| `wave-final` | DDA0DD | Final Verification |
| `blocker` | B60205 | Must complete before next wave |
| `intern` | 5319E7 | Intern task (non-blocking) |

## Milestones Available

| Milestone | Number | Description |
|-----------|--------|-------------|
| Wave 0 | 1 | Blocker Resolution (MUST COMPLETE FIRST) |
| Wave 1 | 2 | Foundation (scaffolding + configuration) |
| Wave 2 | 3 | Data Pipeline (OHLCV + Funding + OI + RAG) |
| Wave 3 | 4 | Detection + Classification |
| Wave 4 | 5 | Validation + Evaluation + Ablation Study |
| Wave Final | 6 | Final Verification (Audit + Review + QA) |

## Example Usage

```
Create issue with:
- title: "0.2 Test Wayback CDX API for Crypto RSS Feeds"
- labels: "wave-0,blocker"
- milestone: "Wave 0" (resolve to number 1)
- body: full task description from plan
```

## Execution Flow

1. Parse task from plan file
2. Extract: title, labels, milestone, body sections
3. Resolve milestone number if needed
4. Execute `gh issue create` command
5. Capture issue URL from output
6. Return issue URL to user for verification

## Error Handling

- **Label not found**: Create label first with `gh label create`
- **Milestone not found**: Create milestone via API
- **Assignee not found**: Skip assignee, proceed without
- **Project scope missing**: User needs `gh auth refresh -s project`

## Notes

- Labels must exist before creating issue (create with `gh label create {name} --color {hex} --description "{desc}"`)
- Milestones can be created via `gh api repos/{owner}/{repo}/milestones -X POST -f title="{name}"`
- Project linking requires `project` scope: `gh auth refresh -s project`
