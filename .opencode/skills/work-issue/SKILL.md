---
name: work-issue
description: "Work on a GitHub issue end-to-end: fetch issue details, create feature branch, implement the task, commit with convention, and create PR via github-pr skill. Triggers: 'work on issue', 'do issue', 'implement issue', 'take issue', 'start issue', 'pick up issue', 'handle issue', 'work on #', 'do #', 'implement #'."
---

# Work Issue

You are a task execution specialist. When triggered with an issue number or title, you own that issue from branch creation to PR. You implement the work, commit with the project convention, and hand off to the github-pr skill for PR creation.

---

## Workflow

### Phase 1: Resolve Issue

Get the issue details from GitHub.

```bash
# If number provided:
gh issue view {number} --json number,title,labels,body,milestone

# If title provided (fuzzy search):
gh issue list --search "{title keywords}" --state open --json number,title
```

If no match found: stop, tell user "Issue not found", ask for number or exact title.

If multiple matches: show list, ask user to pick one.

Once resolved, extract:
- `ISSUE_NUMBER`: the issue number
- `ISSUE_TITLE`: the issue title (full, as-is from GitHub)
- `ISSUE_BODY`: the issue body (for implementation context)

### Phase 2: Create Branch

```bash
# Check for uncommitted changes first
git status --porcelain

# If dirty working tree: stop, ask user to stash or commit first
# If clean: proceed

# Create and switch to feature branch
git checkout main
git pull origin main
git checkout -b feat-{ISSUE_NUMBER}
```

Branch naming: `feat-{ISSUE_NUMBER}` (e.g., `feat-11`, `feat-25`)

### Phase 3: Implement

Read the issue body carefully. Implement the task as described.

Key rules:
- Work ONLY on what the issue describes. No scope creep.
- Follow existing codebase patterns. Check 2-3 similar files first.
- Run `lsp_diagnostics` on every file you create or modify.
- If the issue references other tasks/files, read them for context.
- Verify your work: run build/test commands if they exist.

### Phase 4: Commit

```bash
# Stage all relevant files (be specific, no git add .)
git add {files_from_issue_or_changed}

# Commit with convention
git commit -m "[{ISSUE_NUMBER}] {ISSUE_TITLE}"
```

Commit message format: `[{ISSUE_NUMBER}] {ISSUE_TITLE}` (verbatim from GitHub)

Example: `[11] 1. Project scaffolding + UV initialization`

### Phase 5: Create PR via github-pr Skill

Load and follow the `github-pr` skill. The PR:

- Title: `[{ISSUE_NUMBER}] {ISSUE_TITLE}`
- Body: structured with Summary, Changes, Testing, Related Issues
- `link-issue`: `{ISSUE_NUMBER}` (so PR auto-closes the issue on merge)
- Inherit wave-* labels from the linked issue

After PR creation, show the PR URL to the user.

### Phase 6: Wait for User Validation

**STOP here.** Show the PR URL and wait for the user to review.

Do NOT merge the PR. Do not push additional changes. Just wait.

If user approves: inform them they can merge.
If user requests changes: make the changes, amend or new commit (follow git-master rules), push, and wait again.

---

## Anti-Patterns

| Violation | Why Bad |
|----------|---------|
| Working on wrong issue | Wastes time -- always verify issue number/title match |
| Dirty working tree before branch | Commits mixed with unrelated changes |
| `git add .` | Stages build artifacts, secrets, unintended files |
| Deviating from commit convention | Breaks project convention: must be `[NUMBER] TITLE` |
| Merging PR without user approval | User must validate before merge -- always wait |
| Implementing more than the issue says | Scope creep delays delivery -- stick to the issue |
| Skipping diagnostics check | Type errors slip through -- always verify |
| Not reading issue body | Missing acceptance criteria and QA scenarios |
