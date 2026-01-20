#!/usr/bin/env python3
"""
Commit Critic CLI - Terminal interface for the AI commit analyzer.

Usage:
    python -m commit_critic.cli --analyze              # Analyze current repo
    python -m commit_critic.cli --analyze --url URL    # Analyze remote repo
    python -m commit_critic.cli --write                # Write commit for staged changes
"""

import argparse
import asyncio
import json
import os
import sys
from typing import Optional

# Load environment variables from .env file
from dotenv import load_dotenv
load_dotenv()

# Enable LangSmith tracing
import os
os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
os.environ.setdefault("LANGCHAIN_PROJECT", "commit-critic")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from langchain_core.messages import HumanMessage, AIMessage

console = Console()


def print_banner():
    """Print the Commit Critic banner."""
    banner = """
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   ██████╗ ██████╗ ███╗   ███╗███╗   ███╗██╗████████╗     ║
║  ██╔════╝██╔═══██╗████╗ ████║████╗ ████║██║╚══██╔══╝     ║
║  ██║     ██║   ██║██╔████╔██║██╔████╔██║██║   ██║        ║
║  ██║     ██║   ██║██║╚██╔╝██║██║╚██╔╝██║██║   ██║        ║
║  ╚██████╗╚██████╔╝██║ ╚═╝ ██║██║ ╚═╝ ██║██║   ██║        ║
║   ╚═════╝ ╚═════╝ ╚═╝     ╚═╝╚═╝     ╚═╝╚═╝   ╚═╝        ║
║                                                           ║
║   ██████╗██████╗ ██╗████████╗██╗ ██████╗                 ║
║  ██╔════╝██╔══██╗██║╚══██╔══╝██║██╔════╝                 ║
║  ██║     ██████╔╝██║   ██║   ██║██║                      ║
║  ██║     ██╔══██╗██║   ██║   ██║██║                      ║
║  ╚██████╗██║  ██║██║   ██║   ██║╚██████╗                 ║
║   ╚═════╝╚═╝  ╚═╝╚═╝   ╚═╝   ╚═╝ ╚═════╝                 ║
║                                                           ║
║          AI-Powered Commit Message Analyzer               ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
    console.print(banner, style="bold cyan")


def run_analyze(url: Optional[str] = None, limit: int = 50, thread_id: Optional[str] = None):
    """Run the analysis workflow."""
    from .commit_critic_agent import create_commit_critic_agent, invoke_agent

    repo_path = os.getcwd()

    if url:
        console.print(f"\n[bold]Analyzing remote repository:[/bold] {url}")
    else:
        console.print(f"\n[bold]Analyzing local repository:[/bold] {repo_path}")

    console.print(f"[dim]Fetching last {limit} commits...[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating agent...", total=None)

        # Create agent with thread support
        # Pass URL as repo context when analyzing remote, otherwise local path
        agent, thread_id = create_commit_critic_agent({
            "repo_path": url if url else repo_path,
            "thread_id": thread_id
        })

        progress.update(task, description="Analyzing commits...")

        # Build prompt
        if url:
            prompt = f"""Analyze the last {limit} commits from this remote repository: {url}

Steps:
1. Clone the repository using task("fetch_commits", "Clone and fetch from {url}")
2. Analyze all commits using task("analyze_commits", "Analyze: [commits]")
3. Format the results showing:
   - Commits that need work (score 1-3) with suggestions
   - Well-written commits (score 7-10) with praise
   - Stats summary

Present the results in a clear, formatted way."""
        else:
            prompt = f"""Analyze the last {limit} commits from the current repository at {repo_path}

Steps:
1. Fetch commits using task("fetch_commits", "Fetch last {limit} commits from {repo_path}")
2. Analyze all commits using task("analyze_commits", "Analyze: [commits]")
3. Format the results showing:
   - Commits that need work (score 1-3) with suggestions
   - Well-written commits (score 7-10) with praise
   - Stats summary

Present the results in a clear, formatted way."""

        # Run agent with thread ID
        result = invoke_agent(agent, prompt, thread_id)

        progress.update(task, description="Done!")

    # Show thread ID for future reference
    console.print(f"\n[dim]Thread ID: {thread_id}[/dim]")

    # Extract and display results
    console.print("\n")
    display_results(result)


def run_write(thread_id: Optional[str] = None):
    """Run the interactive write workflow."""
    from .commit_critic_agent import create_commit_critic_agent, invoke_agent, continue_conversation

    repo_path = os.getcwd()
    console.print(f"\n[bold]Writing commit for:[/bold] {repo_path}")
    console.print("[dim]Checking staged changes...[/dim]\n")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Creating agent...", total=None)

        # Create agent with thread support
        agent, thread_id = create_commit_critic_agent({
            "repo_path": repo_path,
            "thread_id": thread_id
        })

        progress.update(task, description="Analyzing staged changes...")

        prompt = f"""Help me write a commit message for my staged changes in {repo_path}

Steps:
1. Get staged changes using task("get_staged_changes", "Get staged diff from {repo_path}")
2. If no staged changes, tell me to stage files first
3. If there are staged changes, generate a commit message using task("suggest_commit_message", "Suggest commit for: [diff]")
4. Present the suggested commit message clearly

Do NOT execute the commit - just suggest the message and wait for my approval."""

        # Run agent with thread ID
        result = invoke_agent(agent, prompt, thread_id)

        progress.update(task, description="Done!")

    # Show thread ID
    console.print(f"\n[dim]Thread ID: {thread_id}[/dim]")

    # Display suggestion
    console.print("\n")
    display_results(result)

    # Ask for user input
    console.print("\n[bold yellow]Options:[/bold yellow]")
    console.print("  [green]y/yes[/green]    - Accept and commit with suggested message")
    console.print("  [yellow]r/revise[/yellow] - Give feedback to revise the suggestion")
    console.print("  [cyan]c/custom[/cyan] - Type your own commit message")
    console.print("  [red]n/no[/red]     - Cancel without committing")
    console.print()
    user_input = input("> ").strip()

    if user_input.lower() in ["", "y", "yes", "accept"]:
        # User accepted - execute commit
        console.print("\n[bold green]Executing commit with suggested message...[/bold green]")

        # Continue conversation with approval (using thread)
        result = continue_conversation(
            agent,
            result["messages"],
            "Yes, execute the commit with that message using task('execute_commit', '...')",
            thread_id
        )

        display_results(result)
    elif user_input.lower() in ["n", "no", "cancel", "q", "quit"]:
        console.print("\n[yellow]Commit cancelled.[/yellow]")
    elif user_input.lower() in ["r", "revise", "feedback"]:
        # User wants to revise
        console.print("\n[cyan]What would you like to change?[/cyan]")
        feedback = input("> ").strip()

        console.print("\n[bold cyan]Revising based on your feedback...[/bold cyan]")
        result = continue_conversation(
            agent,
            result["messages"],
            f"Please revise the commit message based on this feedback: {feedback}",
            thread_id
        )
        display_results(result)

        # Ask again after revision
        console.print("\n[bold yellow]Use this revised message? (y/n)[/bold yellow]")
        confirm = input("> ").strip()
        if confirm.lower() in ["", "y", "yes"]:
            console.print("\n[bold green]Executing commit...[/bold green]")
            result = continue_conversation(
                agent,
                result["messages"],
                "Yes, execute the commit with that revised message",
                thread_id
            )
            display_results(result)
        else:
            console.print("\n[yellow]Commit cancelled.[/yellow]")
    elif user_input.lower() in ["c", "custom"]:
        # User wants to type custom message
        console.print("\n[cyan]Enter your commit message:[/cyan]")
        custom_msg = input("> ").strip()

        if custom_msg:
            console.print(f"\n[bold green]Executing commit with your message...[/bold green]")
            result = continue_conversation(
                agent,
                result["messages"],
                f"Execute commit with this exact message: {custom_msg}",
                thread_id
            )
            display_results(result)
        else:
            console.print("\n[yellow]No message provided. Commit cancelled.[/yellow]")
    else:
        console.print("\n[yellow]Unknown option. Commit cancelled.[/yellow]")


def display_results(result):
    """Display agent results in a formatted way."""
    messages = result.get("messages", [])

    for msg in messages:
        if isinstance(msg, AIMessage):
            content = msg.content
            if isinstance(content, str):
                # Try to detect and format JSON
                if content.strip().startswith("{") or content.strip().startswith("["):
                    try:
                        data = json.loads(content)
                        console.print_json(data=data)
                    except json.JSONDecodeError:
                        console.print(Markdown(content))
                else:
                    console.print(Markdown(content))
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "text":
                            console.print(Markdown(block.get("text", "")))
                    elif isinstance(block, str):
                        console.print(Markdown(block))


def run_list_threads():
    """List all conversation threads."""
    from .commit_critic_agent import list_threads, CHECKPOINT_DB

    threads = list_threads()

    if not threads:
        console.print("[yellow]No conversation threads found.[/yellow]")
        console.print(f"[dim]Checkpoint DB: {CHECKPOINT_DB}[/dim]")
        return

    console.print(f"\n[bold]Conversation Threads[/bold] ({len(threads)} total)")
    console.print(f"[dim]Stored in: {CHECKPOINT_DB}[/dim]\n")

    for thread in threads:
        console.print(f"  • {thread}")

    console.print("\n[dim]Use --thread <id> to continue a conversation[/dim]")


def run_clear_threads(thread_id: Optional[str] = None):
    """Clear thread history."""
    from .commit_critic_agent import clear_thread, clear_all_threads

    if thread_id:
        if clear_thread(thread_id):
            console.print(f"[green]Cleared thread: {thread_id}[/green]")
        else:
            console.print(f"[red]Thread not found: {thread_id}[/red]")
    else:
        count = clear_all_threads()
        console.print(f"[green]Cleared {count} thread(s)[/green]")


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Commit Critic - AI-powered commit message analyzer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --analyze                    Analyze last 50 commits of current repo
  %(prog)s --analyze --limit 100        Analyze last 100 commits
  %(prog)s --analyze --url URL          Analyze a remote repository
  %(prog)s --write                      Help write a commit for staged changes
  %(prog)s --threads                    List all conversation threads
  %(prog)s --thread ID --write          Continue a specific thread
  %(prog)s --clear-threads              Clear all thread history

Environment:
  ANTHROPIC_API_KEY    Required for Claude API access
        """
    )

    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze commit messages from the repository"
    )
    parser.add_argument(
        "--write",
        action="store_true",
        help="Interactive mode to help write a commit message"
    )
    parser.add_argument(
        "--url",
        type=str,
        help="Remote repository URL to analyze (for --analyze mode)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=50,
        help="Number of commits to analyze (default: 50)"
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress banner output"
    )
    parser.add_argument(
        "--thread",
        type=str,
        help="Thread ID to continue an existing conversation"
    )
    parser.add_argument(
        "--threads",
        action="store_true",
        help="List all conversation threads"
    )
    parser.add_argument(
        "--clear-threads",
        action="store_true",
        help="Clear all thread history (or use with --thread to clear specific thread)"
    )

    args = parser.parse_args()

    # Handle thread management commands first (don't need API key)
    if args.threads:
        run_list_threads()
        sys.exit(0)

    if args.clear_threads:
        run_clear_threads(args.thread)
        sys.exit(0)

    # Check for API key for other commands
    if not os.environ.get("ANTHROPIC_API_KEY"):
        console.print("[bold red]Error:[/bold red] ANTHROPIC_API_KEY environment variable not set.")
        console.print("Set it with: export ANTHROPIC_API_KEY=sk-ant-...")
        sys.exit(1)

    # Print banner
    if not args.quiet:
        print_banner()

    # Run appropriate mode with optional thread continuation
    if args.analyze:
        run_analyze(url=args.url, limit=args.limit, thread_id=args.thread)
    elif args.write:
        run_write(thread_id=args.thread)
    else:
        parser.print_help()
        console.print("\n[yellow]Please specify --analyze, --write, or --threads[/yellow]")
        sys.exit(1)


if __name__ == "__main__":
    main()
