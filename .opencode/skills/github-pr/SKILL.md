---
name: github-pr
description: Create well-structured GitHub pull requests with organized body sections, proper formatting, and context from commit history. Triggers: 'create a PR', 'create a pull request', 'make a PR', 'open a pull request', 'push and create PR', 'I need a PR', 'generate PR description', 'prepare pull request'.
license: MIT
compatibility: opencode
metadata:
  category: project-management
  triggers: create a PR, create a pull request, make a PR, open a pull request, push and create PR, I need a PR, generate PR description, prepare pull request
---

## What I Do

Create GitHub pull requests programmatically with full context:
- Title from commit messages or branch name
- Body with structured sections (Summary, Changes, Testing)
- Base branch selection (default: main)
- Reviewer assignment
- Draft vs ready-for-review
- Auto-detect linked issue from branch name (task number pattern)
- Auto-assign: PR creator + repo maintainer
- Inherit category labels from linked issue

## When to Use Me

Use this skill when:
- Pushing completed work to remote and creating PR
- Generating PR description from commit history
- Creating structured PRs with testing instructions
- Linking PRs to existing issues

## Parameters Required

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `title` | string | YES | PR title (concise, imperative mood, e.g., "Add Binance data download POC") |
| `body` | string | YES | PR body with sections: Summary, Changes, Testing |
| `base` | string | NO | Base branch (default: main) |
| `head` | string | NO | Head branch (default: current branch) |
| `reviewers` | string | NO | Space-separated GitHub usernames (e.g., "user1 user2") |
| `draft` | boolean | NO | Create as draft (default: false) |
| `link-issue` | number | NO | Issue number to link in body |

## How to Execute

### Step 0: Pre-flight Check

```bash
# Check gh CLI is installed
gh --version

# Check gh is authenticated
gh auth status

# Detect PR creator (current authenticated user)
PR_CREATOR=$(gh api user --jq '.login')

# Detect repo maintainer (repo owner)
REPO_OWNER=$(gh repo view --json owner --jq '.owner.login')

# Detect repo name for API calls
REPO=$(gh repo view --json nameWithOwner --jq '.nameWithOwner')
```

If `gh` not installed: stop, inform user to install from https://cli.github.com/
If not authenticated: run `gh auth login`, then retry

### Step 1: Check Branch State

```bash
# Determine base branch (default: main if not specified)
BASE_BRANCH="{base}"
if [ -z "$BASE_BRANCH" ]; then
  # Try to detect default branch from remote
  BASE_BRANCH=$(git remote show origin 2>/dev/null | grep 'HEAD branch' | cut -d':' -f2 | tr -d ' ')
  [ -z "$BASE_BRANCH" ] && BASE_BRANCH="main"
fi

# Verify current branch and unpushed commits
HEAD_BRANCH=$(git branch --show-current)
git status
git log origin/$BASE_BRANCH..HEAD --oneline
```

Interpreting results:
- Detached HEAD → stop, inform user to checkout a branch first
- No commits ahead of base → stop, nothing to PR
- Commits ahead → proceed to Step 2

### Step 2: Check for Existing PR

```bash
# Check if PR already exists for this branch
gh pr list --head "$HEAD_BRANCH" --state all --json number,title,state,url
```

Interpreting results:
- No PR exists → proceed to Step 3
- Open PR exists → stop, show existing PR URL, ask user: "PR already exists. Close it and create new, or update existing?"
- Closed PR exists → proceed, note in new PR body: "Supersedes #{number}"

### Step 3: Detect Linked Issue from Branch Name

```bash
# Extract task number from branch name using bash regex
# Patterns: "0.1-slug", "wave-0-slug", "task-5-slug"
TASK_NUMBER=""
LINK_ISSUE=""

if [[ "$HEAD_BRANCH" =~ ^([0-9]+\.[0-9]+)- ]]; then
  TASK_NUMBER="${BASH_REMATCH[1]}"
elif [[ "$HEAD_BRANCH" =~ ^wave-([0-9]+)- ]]; then
  TASK_NUMBER="${BASH_REMATCH[1]}"
elif [[ "$HEAD_BRANCH" =~ ^task-([0-9]+)- ]]; then
  TASK_NUMBER="${BASH_REMATCH[1]}"
fi

# Search for matching issue by task number in title
if [ -n "$TASK_NUMBER" ]; then
  # Get all open issues with this task number in title
  MATCHING_ISSUES=$(gh issue list --search "$TASK_NUMBER" --state open --json number,title)
  
  # Filter to issues where title starts with task number
  FILTERED_ISSUES=$(echo "$MATCHING_ISSUES" | jq --arg task "$TASK_NUMBER" '.[] | select(.title | startswith($task))')
  
  # Count matches correctly (handle empty case)
  if [ -z "$FILTERED_ISSUES" ]; then
    MATCH_COUNT=0
  else
    MATCH_COUNT=$(echo "$FILTERED_ISSUES" | jq -s 'length')
  fi
  
  if [ "$MATCH_COUNT" -eq 1 ]; then
    # Single match - use it
    LINK_ISSUE=$(echo "$FILTERED_ISSUES" | jq -r '.number')
  elif [ "$MATCH_COUNT" -gt 1 ]; then
    # Multiple matches - ambiguous, ask user
    echo "Multiple issues found with task number $TASK_NUMBER:"
    echo "$FILTERED_ISSUES" | jq -r '. | "- #\(.number): \(.title)"'
    echo "Which issue does this PR close? Provide issue number or 'none' to skip."
    # User input expected here
  fi
fi

# Override with explicit link-issue parameter if provided
[ -n "{link-issue}" ] && LINK_ISSUE="{link-issue}"
```

Interpreting results:
- Single match → auto-link to that issue
- Multiple matches → stop, show list, ask user which issue
- No match → proceed without linked issue (optional manual link later)
- Explicit `link-issue` parameter → overrides auto-detection

### Step 4: Push to Remote (if needed)

```bash
# Check if branch exists on remote
git ls-remote --heads origin "$HEAD_BRANCH"

# Push if not on remote
git push -u origin "$HEAD_BRANCH"
```

If branch already on remote, skip push.

### Step 5: Extract Commits and Build Body

```bash
# Extract commit messages between base and HEAD
COMMITS=$(git log origin/$BASE_BRANCH..HEAD --format='- %s')

# Build PR body using heredoc (handles special characters safely)
cat <<EOF > /tmp/pr-body.md
## Summary
$COMMITS

## Changes
- [Describe specific changes based on commit analysis]

## Testing
[Add commands to verify changes work]

## Related Issues
EOF

# Add link-issue if detected/provided
if [ -n "$LINK_ISSUE" ]; then
  echo "Closes #$LINK_ISSUE" >> /tmp/pr-body.md
fi

# Verify body file was created
[ -f /tmp/pr-body.md ] || echo "ERROR: body file not created"
```

Note: For complex bodies with categorized changes, manually edit `/tmp/pr-body.md` before creating PR.

### Step 6: Generate Title

```bash
# Get first commit message for title
git log -1 --format='%s'
```

Title format: Imperative mood, concise, no trailing punctuation.
Example: "Clean POC structure and simplify download script"

### Step 7: Inherit Labels from Linked Issue

```bash
# Fetch category labels from linked issue (auto-detected or explicit)
LABEL_FLAGS=""

if [ -n "$LINK_ISSUE" ]; then
  # Get labels from the issue
  ISSUE_LABELS=$(gh issue view $LINK_ISSUE --json labels --jq '.labels[].name')
  
  # Filter to only category labels (wave-* pattern)
  for label in $ISSUE_LABELS; do
    if [[ "$label" == wave-* ]]; then
      LABEL_FLAGS="$LABEL_FLAGS --label $label"
    fi
  done
fi
```

Note: Only inherits `wave-*` category labels. Status labels (blocker, intern) are not applied to PRs.

### Step 8: Create PR and Capture URL

```bash
# Capture title from user input or first commit
PR_TITLE="{title}"
[ -z "$PR_TITLE" ] && PR_TITLE=$(git log -1 --format='%s')

# Build assignee flags: creator + maintainer
ASSIGNEE_FLAGS="--assignee $PR_CREATOR --assignee $REPO_OWNER"

# Build reviewers flags (multiple --reviewer for each user)
REVIEWER_FLAGS=""
REVIEWERS="{reviewers}"
if [ -n "$REVIEWERS" ]; then
  for user in $REVIEWERS; do
    REVIEWER_FLAGS="$REVIEWER_FLAGS --reviewer $user"
  done
fi

# Build draft flag conditionally
DRAFT_FLAG=""
[ "{draft}" = "true" ] && DRAFT_FLAG="--draft"

# Create PR and capture URL in one command
PR_URL=$(gh pr create \
  --title "$PR_TITLE" \
  --base "$BASE_BRANCH" \
  --head "$HEAD_BRANCH" \
  $ASSIGNEE_FLAGS \
  $REVIEWER_FLAGS \
  $LABEL_FLAGS \
  $DRAFT_FLAG \
  --body-file /tmp/pr-body.md)

# Check exit code
if [ $? -ne 0 ]; then
  echo "ERROR: PR creation failed"
  exit 1
fi
```

### Step 9: Return to User

Show the PR URL and ask: "PR created: $PR_URL. Does this look right?"

## Body Template Structure

Use this structure for PR bodies:

```markdown
## Summary
{1-3 bullet points capturing the core change}

## Changes
{Grouped by category}
- **{category}**: {specific change}
- **{category}**: {specific change}

## Testing
```bash
{command to verify changes work}
```
Expected: {expected outcome}

## Related Issues
Closes #{link-issue}  # Add only if link-issue parameter provided
```

## Example PR Bodies

### Feature Addition
```markdown
## Summary
- Add single-file download script for LUNAUSDT derivatives data
- Remove external dependencies (stdlib only)
- Add 0.5s rate limiting between downloads

## Changes
- **Simplified**: Merged multiple scripts into `main.py`
- **Removed**: `binance-bulk-downloader` dependency
- **Added**: `.gitignore` for Python/data exclusion
- **Updated**: README with actual data range (Dec 2021 - May 2022)

## Testing
```bash
cd poc_binance_api && uv run main.py
```
Expected: Downloads ~31M of data across klines, funding_rate, metrics

## Related Issues
Closes #5
```

### Cleanup/Refactor
```markdown
## Summary
- Consolidate POC into single script
- Remove duplicate data directories

## Changes
- **Deleted**: `data/binance/`, `scripts/`, `BINANCE_DATA_VISION.md`
- **Rewrote**: `main.py` with urllib-only approach
- **Updated**: README with simplified structure

## Testing
```bash
ls poc_binance_api/
```
Expected: Only `main.py`, `README.md`, `pyproject.toml`, `.gitignore`, `data/`
```

## Labels Available

Category labels (inherited from linked issue, `wave-*` pattern only):

| Label | Color | Description |
|-------|-------|-------------|
| `wave-0` | FF6B6B | Blocker Resolution |
| `wave-1` | 4ECDC4 | Foundation |
| `wave-2` | 45B7D1 | Data Pipeline |
| `wave-3` | 96CEB4 | Detection + Classification |
| `wave-4` | FFEAA7 | Validation + Evaluation |
| `wave-final` | DDA0DD | Final Verification |

Note: Status labels (`blocker`, `intern`) are NOT inherited — they describe issue state, not PR state.

## Example Usage

```
Create PR with:
- title: "Clean POC structure and simplify download script"
- base: main
- body: generated from commit history + context
- link-issue: 5
```

## Error Handling

| Error | Action |
|-------|--------|
| `gh` CLI not installed | Stop, inform user to install from https://cli.github.com/ |
| Detached HEAD state | Stop, inform user to checkout a branch first |
| No commits ahead | Stop, inform user nothing to PR |
| PR already exists (open) | Stop, show existing PR URL, ask user: close & recreate, or update existing? |
| PR already exists (closed) | Proceed, note in body: "Supersedes #{number}" |
| Branch not on remote | Push first with `git push -u origin {branch}` |
| Task number not in branch name | Proceed without auto-link (user can provide `link-issue` param) |
| Multiple issues match task number | Stop, show list, ask user which issue to link |
| Linked issue not found | Proceed without labels, warn user issue number invalid |
| Label not found on repo | Skip label, proceed without (create later if needed) |
| Assignee not collaborator | Skip failed assignee, proceed with remaining |
| Reviewer not found | Skip reviewer flag, proceed without |
| Base branch doesn't exist | Ask user for correct base branch name |
| `gh` not authenticated | Run `gh auth login`, then retry |
| Body too long (>65KB) | Truncate commit list in body, summarize instead |
| Network timeout | Retry after brief delay |
| Force push needed | Warn user branch was modified, ask if should force push |

## Anti-patterns

| Violation | Why Bad |
|-----------|---------|
| Using inline `--body "{body}"` | Breaks on quotes, backticks, dollar signs — use `--body-file` |
| Assuming `main` is default branch | Many repos use `master` or `develop` — check first |
| Skipping existing PR check | Creates duplicate PRs, confusing history |
| Hardcoding `--draft` | Contradicts parameter default — add conditionally |
| Comma-separated reviewers | `gh` needs multiple `--reviewer` flags — split on spaces |
| Vague title ("Updates", "Fixes") | Reviewers can't understand PR purpose — use specific imperative |
| Inheriting status labels (`blocker`, `intern`) | Status describes issue state, not PR — only inherit `wave-*` |
| Skipping Step 9 confirmation | User can't catch errors before PR is public |