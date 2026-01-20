"""
Commit Critic Deep Agent - Main Agent Creation

Uses LangGraph's deepagents library to create a multi-agent system
for analyzing and writing commit messages.

Architecture:
- Main agent: Orchestrator that delegates to subagents via task()
- Subagents: Execute atomic actions (fetch, analyze, suggest, commit)
- Checkpointer: SQLite-based persistence for threaded conversations

Following the same pattern as x_growth_deep_agent.py.
"""

import os
import uuid
from pathlib import Path
from typing import Optional, Dict, Any

# Import deepagents - the core library for multi-agent orchestration
from deepagents import create_deep_agent

# LangChain imports
from langchain.chat_models import init_chat_model

# LangGraph checkpointer for thread persistence
# Try SqliteSaver for persistence, fall back to InMemorySaver
try:
    from langgraph.checkpoint.sqlite import SqliteSaver
    SQLITE_AVAILABLE = True
except ImportError:
    SQLITE_AVAILABLE = False

from langgraph.checkpoint.memory import InMemorySaver

# Local imports
from .prompts import MAIN_AGENT_PROMPT, get_date_context
from .subagents import get_commit_critic_subagents
from .tools import get_repo_info_tool


# =============================================================================
# CHECKPOINTER SETUP
# =============================================================================

# Store checkpoints in ~/.commit_critic/checkpoints.db
CHECKPOINT_DIR = Path.home() / ".commit_critic"
CHECKPOINT_DB = CHECKPOINT_DIR / "checkpoints.db"

# Global in-memory saver (persists within session)
_memory_saver = None


def get_checkpointer():
    """
    Get or create the checkpointer for thread persistence.

    Uses SqliteSaver if langgraph-checkpoint-sqlite is installed (persists across runs).
    Falls back to InMemorySaver (persists within session only).

    Install for persistence: pip install langgraph-checkpoint-sqlite
    """
    global _memory_saver

    if SQLITE_AVAILABLE:
        # Ensure directory exists
        CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
        checkpointer = SqliteSaver.from_conn_string(str(CHECKPOINT_DB))
        return checkpointer, "sqlite"
    else:
        # Use in-memory saver (session-only persistence)
        if _memory_saver is None:
            _memory_saver = InMemorySaver()
        return _memory_saver, "memory"


def generate_thread_id() -> str:
    """Generate a new unique thread ID."""
    return f"thread_{uuid.uuid4().hex[:12]}"


def get_or_create_thread_id(thread_id: Optional[str] = None) -> str:
    """
    Get existing thread ID or create a new one.

    Args:
        thread_id: Optional existing thread ID to reuse

    Returns:
        Thread ID string
    """
    if thread_id:
        return thread_id
    return generate_thread_id()


# =============================================================================
# AGENT CREATION
# =============================================================================

def create_commit_critic_agent(config: Optional[Dict[str, Any]] = None):
    """
    Create the Commit Critic deep agent with thread persistence.

    The agent uses the deepagents library to orchestrate multiple subagents:
    - fetch_commits: Get commits from repos
    - analyze_commits: Score and categorize messages
    - get_staged_changes: Get diff for write mode
    - suggest_commit_message: Generate commit messages
    - execute_commit: Create commits

    Args:
        config: Optional configuration dict with:
            - model_name: LLM model to use (default: claude-sonnet-4-5-20250929)
            - model_provider: "anthropic" or "openai" (default: anthropic)
            - repo_path: Default repository path (default: current directory)
            - thread_id: Thread ID for conversation continuity (auto-generated if not provided)

    Returns:
        Tuple of (agent, thread_id) - LangGraph agent and the thread ID for this session
    """
    config = config or {}

    # Get configuration with defaults
    model_name = config.get("model_name", "claude-sonnet-4-5-20250929")
    model_provider = config.get("model_provider", "anthropic")
    repo_path = config.get("repo_path", os.getcwd())
    thread_id = get_or_create_thread_id(config.get("thread_id"))

    print(f"🤖 Creating Commit Critic Agent...")
    print(f"   Model: {model_name} ({model_provider})")
    print(f"   Target: {repo_path}")
    print(f"   Thread: {thread_id}")

    # Initialize the LLM
    if model_provider == "openai":
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(model=model_name, temperature=0.7)
    else:
        # Default to Anthropic
        model = init_chat_model(model_name)

    # Build the system prompt with date context
    date_context = get_date_context()
    system_prompt = f"{MAIN_AGENT_PROMPT}\n\n{date_context}"

    # Add repo context if available
    system_prompt += f"\n\nDefault repository path: {repo_path}"

    # Get atomic subagents
    subagents = get_commit_critic_subagents()
    print(f"   Subagents: {[s['name'] for s in subagents]}")

    # Main agent tools (read-only context tools)
    main_tools = [get_repo_info_tool]

    # Get checkpointer for thread persistence
    checkpointer, checkpointer_type = get_checkpointer()
    if checkpointer_type == "sqlite":
        print(f"   Checkpointer: SQLite ({CHECKPOINT_DB})")
    else:
        print(f"   Checkpointer: InMemory (session only - install langgraph-checkpoint-sqlite for persistence)")

    # Create the deep agent with checkpointer
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,
        tools=main_tools,
        subagents=subagents,
        checkpointer=checkpointer,
    )

    print(f"✅ Commit Critic Agent created successfully!")
    return agent, thread_id


def invoke_agent(
    agent,
    message: str,
    thread_id: str,
) -> Dict[str, Any]:
    """
    Invoke the agent with thread-aware configuration.

    Args:
        agent: The LangGraph agent
        message: User message to process
        thread_id: Thread ID for conversation continuity

    Returns:
        Agent result dict
    """
    from langchain_core.messages import HumanMessage

    result = agent.invoke(
        {"messages": [HumanMessage(content=message)]},
        config={"configurable": {"thread_id": thread_id}}
    )

    return result


def continue_conversation(
    agent,
    messages: list,
    new_message: str,
    thread_id: str,
) -> Dict[str, Any]:
    """
    Continue an existing conversation with a new message.

    Args:
        agent: The LangGraph agent
        messages: Existing messages from previous result
        new_message: New user message to add
        thread_id: Thread ID for conversation continuity

    Returns:
        Agent result dict
    """
    from langchain_core.messages import HumanMessage

    result = agent.invoke(
        {"messages": messages + [HumanMessage(content=new_message)]},
        config={"configurable": {"thread_id": thread_id}}
    )

    return result


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

def run_analysis(
    repo_path: str = ".",
    url: Optional[str] = None,
    limit: int = 50,
    thread_id: Optional[str] = None
):
    """
    Run commit analysis workflow.

    Args:
        repo_path: Local repository path
        url: Remote repository URL (if analyzing remote)
        limit: Number of commits to analyze
        thread_id: Optional thread ID to continue a conversation

    Returns:
        Tuple of (result, thread_id)
    """
    agent, thread_id = create_commit_critic_agent({
        "repo_path": repo_path,
        "thread_id": thread_id
    })

    if url:
        prompt = f"Analyze the last {limit} commits from this remote repository: {url}"
    else:
        prompt = f"Analyze the last {limit} commits from the current repository at {repo_path}"

    result = invoke_agent(agent, prompt, thread_id)

    return result, thread_id


def run_write_mode(repo_path: str = ".", thread_id: Optional[str] = None):
    """
    Run interactive commit writing workflow.

    Args:
        repo_path: Local repository path
        thread_id: Optional thread ID to continue a conversation

    Returns:
        Tuple of (result, agent, thread_id) - for continuing the conversation
    """
    agent, thread_id = create_commit_critic_agent({
        "repo_path": repo_path,
        "thread_id": thread_id
    })

    prompt = f"Help me write a commit message for my staged changes in {repo_path}"

    result = invoke_agent(agent, prompt, thread_id)

    return result, agent, thread_id


# =============================================================================
# THREAD MANAGEMENT
# =============================================================================

def list_threads() -> list:
    """
    List all available thread IDs from the checkpoint database.

    Returns:
        List of thread IDs
    """
    if not SQLITE_AVAILABLE:
        # InMemorySaver doesn't support listing threads easily
        return ["(in-memory threads not listable - install langgraph-checkpoint-sqlite)"]

    import sqlite3

    if not CHECKPOINT_DB.exists():
        return []

    conn = sqlite3.connect(str(CHECKPOINT_DB))
    cursor = conn.cursor()

    try:
        cursor.execute("SELECT DISTINCT thread_id FROM checkpoints")
        threads = [row[0] for row in cursor.fetchall()]
        return threads
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def clear_thread(thread_id: str) -> bool:
    """
    Clear a specific thread's history.

    Args:
        thread_id: Thread ID to clear

    Returns:
        True if cleared successfully
    """
    if not SQLITE_AVAILABLE:
        return False

    import sqlite3

    if not CHECKPOINT_DB.exists():
        return False

    conn = sqlite3.connect(str(CHECKPOINT_DB))
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM checkpoints WHERE thread_id = ?", (thread_id,))
        conn.commit()
        return cursor.rowcount > 0
    except sqlite3.OperationalError:
        return False
    finally:
        conn.close()


def clear_all_threads() -> int:
    """
    Clear all thread history.

    Returns:
        Number of threads cleared
    """
    global _memory_saver

    if not SQLITE_AVAILABLE:
        # Reset in-memory saver
        _memory_saver = None
        return 1

    import sqlite3

    if not CHECKPOINT_DB.exists():
        return 0

    conn = sqlite3.connect(str(CHECKPOINT_DB))
    cursor = conn.cursor()

    try:
        cursor.execute("DELETE FROM checkpoints")
        conn.commit()
        return cursor.rowcount
    except sqlite3.OperationalError:
        return 0
    finally:
        conn.close()


# =============================================================================
# USAGE EXAMPLE
# =============================================================================

if __name__ == "__main__":
    # Quick test
    print("\n" + "=" * 60)
    print("COMMIT CRITIC - Quick Test")
    print("=" * 60 + "\n")

    # Test agent creation
    agent, thread_id = create_commit_critic_agent()

    print(f"\n✅ Agent created successfully!")
    print(f"   Thread ID: {thread_id}")
    print(f"   Checkpoint DB: {CHECKPOINT_DB}")
    print("\nUse cli.py for full functionality:")
    print("  python -m commit_critic.cli --analyze")
    print("  python -m commit_critic.cli --write")
    print("  python -m commit_critic.cli --threads  # List threads")
