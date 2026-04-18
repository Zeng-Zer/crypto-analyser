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
- Link related issues automatically

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
gh pr list --head $HEAD_BRANCH --state all --json number,title,state,url
```

Interpreting results:
- No PR exists → proceed to Step 3
- Open PR exists → stop, show existing PR URL, ask user: "PR already exists. Close it and create new, or update existing?"
- Closed PR exists → proceed, note in new PR body: "Supersedes #{number}"

### Step 3: Push to Remote (if needed)

```bash
# Check if branch exists on remote
git ls-remote --heads origin $HEAD_BRANCH

# Push if not on remote
git push -u origin $HEAD_BRANCH
```

If branch already on remote, skip push.

### Step 4: Extract Commits and Build Body

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

# Add link-issue if provided
if [ -n "{link-issue}" ]; then
  echo "Closes #{link-issue}" >> /tmp/pr-body.md
fi

# Verify body file was created
[ -f /tmp/pr-body.md ] || echo "ERROR: body file not created"
```

Note: For complex bodies with categorized changes, manually edit `/tmp/pr-body.md` before creating PR.

### Step 5: Generate Title

```bash
# Get first commit message for title
git log -1 --format='%s'
```

Title format: Imperative mood, concise, no trailing punctuation.
Example: "Clean POC structure and simplify download script"

### Step 6: Create PR

```bash
# Capture title from user input or first commit
PR_TITLE="{title}"
[ -z "$PR_TITLE" ] && PR_TITLE=$(git log -1 --format='%s')

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

# Create PR
gh pr create \
  --title "$PR_TITLE" \
  --base "$BASE_BRANCH" \
  --head "$HEAD_BRANCH" \
  $REVIEWER_FLAGS \
  $DRAFT_FLAG \
  --body-file /tmp/pr-body.md
```

### Step 7: Capture PR URL

```bash
# gh pr create outputs the PR URL to stdout
PR_URL=$(gh pr create \
  --title "$PR_TITLE" \
  --base "$BASE_BRANCH" \
  --head "$HEAD_BRANCH" \
  $REVIEWER_FLAGS \
  $DRAFT_FLAG \
  --body-file /tmp/pr-body.md)

# Check exit code
[ $? -eq 0 ] || echo "ERROR: PR creation failed"
```

### Step 8: Return to User

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

PR labels (optional, add with `--label`):

| Label | Color | Description |
|-------|-------|-------------|
| `wave-0` | FF6B6B | Blocker Resolution |
| `wave-1` | 4ECDC4 | Foundation |
| `wave-2` | 45B7D1 | Data Pipeline |
| `wave-3` | 96CEB4 | Detection + Classification |
| `wave-4` | FFEAA7 | Validation + Evaluation |
| `wave-final` | DDA0DD | Final Verification |

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
| Skipping Step 8 confirmation | User can't catch errors before PR is public |