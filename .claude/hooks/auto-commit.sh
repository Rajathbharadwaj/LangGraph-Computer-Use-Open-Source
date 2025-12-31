#!/bin/bash
# Auto-commit hook for Claude Code
# Triggers after Edit/Write operations on feature/fix/update branches

set -e

# Read hook input from stdin (JSON with tool info)
INPUT=$(cat)

# Safety: Only run in git repos
if [ ! -d .git ]; then
  exit 0
fi

# Get current branch
BRANCH=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo "")

# Only auto-commit on proper branches (feature/, fix/, update/)
if [[ ! "$BRANCH" =~ ^(feature|fix|update)/ ]]; then
  # Not on a proper branch - output reminder
  echo '{"systemMessage": "Reminder: Not on a feature/fix/update branch. Use /commit-all to create proper branch and commit."}'
  exit 0
fi

# Check if there are uncommitted changes
if git diff-index --quiet HEAD -- 2>/dev/null; then
  # No changes to commit
  exit 0
fi

# Get changed files for commit message
CHANGED_FILES=$(git diff --name-only HEAD 2>/dev/null | head -5 | tr '\n' ', ' | sed 's/,$//')

# Determine commit type from branch prefix
if [[ "$BRANCH" =~ ^feature/ ]]; then
  COMMIT_PREFIX="feat"
elif [[ "$BRANCH" =~ ^fix/ ]]; then
  COMMIT_PREFIX="fix"
elif [[ "$BRANCH" =~ ^update/ ]]; then
  COMMIT_PREFIX="chore"
else
  COMMIT_PREFIX="chore"
fi

# Extract feature name from branch
FEATURE_NAME=$(echo "$BRANCH" | sed 's/^[^/]*\///' | tr '-' ' ')

# Create commit message
COMMIT_MSG="$COMMIT_PREFIX: Update $FEATURE_NAME

Modified: $CHANGED_FILES

[Auto-commit by Claude Code hook]
Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"

# Stage and commit
git add -A
git commit -m "$COMMIT_MSG" --no-verify 2>/dev/null || true

echo "Auto-committed on $BRANCH" >&2
exit 0
