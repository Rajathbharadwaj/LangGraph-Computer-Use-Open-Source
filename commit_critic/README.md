# Commit Critic

AI-powered commit message analyzer using LangGraph Deep Agents.

## Overview

Commit Critic is a terminal tool that helps developers write better commit messages. It uses Claude (Anthropic) to:

1. **Analyze Mode**: Review commit history and score message quality
2. **Write Mode**: Generate well-formatted commits based on staged changes

## Architecture

Built using LangGraph's `deepagents` library with a multi-agent architecture:

```
Main Agent (Orchestrator)
    │
    ├── fetch_commits      → Clone repos & fetch commit history
    ├── analyze_commits    → Score and categorize commit messages
    ├── get_staged_changes → Get git diff --staged
    ├── suggest_commit     → Generate commit messages from diff
    └── execute_commit     → Run git commit
```

## Installation

```bash
# Navigate to the commit_critic directory
cd /path/to/cua/commit_critic

# Install dependencies
pip install deepagents langchain langchain-anthropic langgraph anthropic rich pydantic pytz

# Set your Anthropic API key
export ANTHROPIC_API_KEY=sk-ant-...
```

## Usage

### Analyze Commits

```bash
# Analyze last 50 commits from current repository
python -m commit_critic.cli --analyze

# Analyze last 100 commits
python -m commit_critic.cli --analyze --limit 100

# Analyze a remote repository
python -m commit_critic.cli --analyze --url="https://github.com/steel-dev/steel-browser"
```

**Example Output:**

```
Analyzing last 50 commits...

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💩 COMMITS THAT NEED WORK
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Commit: "fixed bug"
Score: 2/10
Issue: Too vague - which bug? What was the impact?
Better: "fix(auth): resolve token expiration handling"

Commit: "wip"
Score: 1/10
Issue: No information about what's in progress
Better: Squash into a descriptive commit before merging

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💎 WELL-WRITTEN COMMITS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Commit: "feat(api): add Redis caching layer
         - Implement cache for read endpoints
         - Add TTL configuration
         - Improves response time by 200ms"
Score: 9/10
Why it's good: Clear scope, specific changes, measurable impact

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 YOUR STATS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Average score: 4.2/10
Vague commits: 34 (68%)
One-word commits: 12 (24%)
```

### Write Commits

```bash
# Stage your changes first
git add .

# Get AI-suggested commit message
python -m commit_critic.cli --write
```

**Example Output:**

```
Analyzing staged changes... (12 files changed, +247 -89 lines)

Changes detected:
- Modified authentication logic
- Added error handling
- Updated unit tests

Suggested commit message:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
refactor(auth): improve error handling

- Add specific error types for auth failures
- Extract validation into separate methods
- Update tests to cover edge cases
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Press Enter to accept, or type your own message:
>
```

## Scoring Criteria

Commits are scored 1-10 based on:

| Criterion | Points | Description |
|-----------|--------|-------------|
| Clarity   | 0-3    | Does it explain WHAT changed? |
| Context   | 0-3    | Does it explain WHY? |
| Format    | 0-2    | Follows conventional commits? |
| Scope     | 0-2    | Is the affected area clear? |

**Categories:**
- **needs_work (1-3)**: Vague, one-word, or unclear
- **acceptable (4-6)**: Understandable but could be better
- **excellent (7-10)**: Clear, scoped, and contextual

## Conventional Commits Format

The tool encourages the [Conventional Commits](https://www.conventionalcommits.org/) format:

```
<type>(<scope>): <subject>

<body>
```

**Types:**
- `feat`: New feature
- `fix`: Bug fix
- `refactor`: Code restructuring
- `docs`: Documentation
- `test`: Adding tests
- `chore`: Maintenance
- `style`: Formatting
- `perf`: Performance

## Dependencies

- `deepagents` - LangGraph deep agent library
- `langchain` - LLM framework
- `langchain-anthropic` - Anthropic Claude integration
- `langgraph` - Graph-based agent orchestration
- `anthropic` - Anthropic API client
- `rich` - Terminal formatting
- `pydantic` - Data validation
- `pytz` - Timezone handling

## Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Your Anthropic API key |

## File Structure

```
commit_critic/
├── __init__.py              # Package exports
├── commit_critic_agent.py   # Main agent creation
├── subagents.py             # Subagent definitions
├── prompts.py               # System prompts
├── tools.py                 # Git operation tools
├── models.py                # Pydantic models
├── cli.py                   # CLI entry point
└── README.md                # This file
```

## Development

The tool follows the same patterns as the existing LangGraph agents in this repository:

- `x_growth_deep_agent.py` - Agent creation pattern
- `ads_agent/subagents.py` - Subagent structure
- `ads_agent/tools.py` - Tool decoration

## License

MIT
