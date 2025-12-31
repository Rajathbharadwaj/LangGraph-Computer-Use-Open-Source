# Multi-Repo Commit Command

Commit changes across all project repositories with proper branching conventions.

## Branching Convention

- **`feature/{name}`** - New features or enhancements
- **`fix/{name}`** - Bug fixes
- **`update/{name}`** - Updates, refactors, config changes

## Usage

```
/commit-all feature/add-dark-mode
/commit-all fix/auth-token-refresh
/commit-all update/landing-page-copy
```

## Repositories

| Repo | Path | Description |
|------|------|-------------|
| cua (backend) | `/home/rajathdb/cua` | FastAPI backend, Deep Agent, LangGraph |
| cua-frontend | `/home/rajathdb/cua-frontend` | Next.js frontend app |
| deep-agents-ui | `/home/rajathdb/deep-agents-ui` | PsY Agent chat interface |

## Process

When this command is invoked with a branch name argument (e.g., `/commit-all feature/multi-model-support`):

### Step 1: Parse Branch Type
Extract the branch type (feature/fix/update) and name from the argument.

### Step 2: Check All Repos for Changes
Run `git status --porcelain` in each repository to identify which have uncommitted changes.

### Step 3: For Each Repo with Changes

1. **Create/Switch Branch**
   ```bash
   git checkout -b {branch_name} || git checkout {branch_name}
   ```

2. **Stage Changes**
   ```bash
   git add -A
   ```

3. **Generate Commit Message**
   Based on the branch type:
   - `feature/` → "feat: {description}"
   - `fix/` → "fix: {description}"
   - `update/` → "refactor: {description}" or "chore: {description}"

   Analyze the diff to generate an appropriate commit message.

4. **Commit**
   ```bash
   git commit -m "{message}

   🤖 Generated with [Claude Code](https://claude.com/claude-code)

   Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
   ```

### Step 4: Summary
Report which repos were committed and their new branch names.

## Example Output

```
📦 Multi-Repo Commit: feature/multi-model-support
================================================

✅ cua (backend)
   Branch: feature/multi-model-support
   Commit: feat: Add multi-model support with provider-aware tools
   Files: 3 changed

✅ cua-frontend
   Branch: feature/multi-model-support
   Commit: feat: Add LLM Selection dropdown to workflow builder
   Files: 2 changed

✅ deep-agents-ui
   Branch: feature/multi-model-support
   Commit: feat: Add LLM Selection dropdown to PsY Agent header
   Files: 1 changed

⏭️  No changes in: (none)

📋 Summary: 3/3 repos committed to feature/multi-model-support
```

## Notes

- If a repo has no changes, it will be skipped
- Does NOT push to remote (use separate push commands)
- Always uses conventional commit format (feat:, fix:, refactor:, chore:)
- Branch names should be lowercase with hyphens (e.g., `feature/add-dark-mode`)
