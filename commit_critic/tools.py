"""
Git operation tools for Commit Critic.

These tools wrap git commands via subprocess for:
- Fetching commit history
- Cloning remote repositories
- Getting staged changes
- Creating commits

All tools use the @tool decorator pattern from langchain_core.tools,
following the same pattern as ads_agent/tools.py.
"""

import json
import os
import subprocess
import tempfile
from langchain_core.tools import tool


@tool
def get_commits_tool(repo_path: str = ".", limit: int = 50) -> str:
    """
    Fetch recent commits from a git repository.

    Args:
        repo_path: Path to the git repository (default: current directory)
        limit: Maximum number of commits to fetch (default: 50, max: 500)

    Returns:
        JSON string with list of commits, each containing:
        - hash: Short commit hash (8 chars)
        - message: First line of commit message
        - body: Rest of commit message (if any)
    """
    try:
        # Validate and clamp limit to reasonable range
        limit = max(1, min(int(limit), 500))

        # Use ASCII Unit Separator (\x1f) between fields - won't appear in commit messages
        # Use NULL (\x00) between commits for multi-line body support
        result = subprocess.run(
            [
                "git", "-C", repo_path, "log", f"-n{limit}",
                "--format=%H%x1f%s%x1f%b%x00"
            ],
            capture_output=True,
            text=True,
            check=True
        )

        commits = []
        for entry in result.stdout.split('\x00'):
            entry = entry.strip()
            if not entry:
                continue

            # Split by Unit Separator (ASCII 31)
            parts = entry.split('\x1f')
            if len(parts) >= 2:
                commits.append({
                    "hash": parts[0][:8],  # Short hash
                    "message": parts[1].strip(),
                    "body": parts[2].strip() if len(parts) > 2 else ""
                })

        return json.dumps(commits, indent=2)

    except subprocess.CalledProcessError as e:
        return json.dumps({
            "error": f"Failed to fetch commits: {e.stderr}",
            "commits": []
        })
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}",
            "commits": []
        })


@tool
def clone_repo_tool(url: str) -> str:
    """
    Clone a remote repository to a temp directory for analysis.

    Uses --depth=50 for shallow clone (faster, only recent history).
    Keeps the cloned repo in /tmp/commit_critic_* for debugging.

    Args:
        url: Git repository URL (e.g., https://github.com/user/repo)

    Returns:
        JSON with:
        - success: Boolean indicating if clone succeeded
        - repo_path: Path to cloned repository
        - message: Status message
        - error: Error message if failed
    """
    try:
        # Basic URL validation
        url = url.strip()
        if not url:
            return json.dumps({
                "success": False,
                "repo_path": None,
                "error": "Empty URL provided"
            })

        # Only allow http(s) and git protocols for security
        if not (url.startswith("https://") or url.startswith("http://") or
                url.startswith("git://") or url.startswith("git@")):
            return json.dumps({
                "success": False,
                "repo_path": None,
                "error": f"Invalid URL protocol. Use https://, http://, git://, or git@ URLs"
            })

        # Create temp directory (kept for debugging)
        temp_dir = tempfile.mkdtemp(prefix="commit_critic_")

        # Clone with shallow depth for efficiency, 60 second timeout
        result = subprocess.run(
            ["git", "clone", "--depth=50", url, temp_dir],
            capture_output=True,
            text=True,
            check=True,
            timeout=60  # 60 second timeout for clone
        )

        return json.dumps({
            "success": True,
            "repo_path": temp_dir,
            "message": f"Successfully cloned {url} to {temp_dir}"
        })

    except subprocess.TimeoutExpired:
        return json.dumps({
            "success": False,
            "repo_path": None,
            "error": "Clone timed out after 60 seconds. Repository may be too large or network is slow."
        })
    except subprocess.CalledProcessError as e:
        return json.dumps({
            "success": False,
            "repo_path": None,
            "error": f"Clone failed: {e.stderr}"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "repo_path": None,
            "error": f"Unexpected error: {str(e)}"
        })


@tool
def get_staged_diff_tool(repo_path: str = ".") -> str:
    """
    Get staged changes (git diff --staged) for commit writing.

    Args:
        repo_path: Path to the git repository (default: current directory)

    Returns:
        JSON with:
        - has_staged: Boolean indicating if there are staged changes
        - stat: Summary of files changed (git diff --staged --stat)
        - diff: Full diff content (truncated to 5000 chars)
        - files: List of changed file paths
        - file_count: Number of staged files
        - message: Status message if no staged changes
    """
    try:
        # Get diff stat (summary)
        stat_result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--staged", "--stat"],
            capture_output=True,
            text=True,
            check=True
        )

        # Get full diff
        diff_result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--staged"],
            capture_output=True,
            text=True,
            check=True
        )

        # Get list of staged files
        files_result = subprocess.run(
            ["git", "-C", repo_path, "diff", "--staged", "--name-only"],
            capture_output=True,
            text=True,
            check=True
        )

        files = [f for f in files_result.stdout.strip().split('\n') if f]

        if not files:
            return json.dumps({
                "has_staged": False,
                "message": "No staged changes found. Stage files with 'git add' first."
            })

        return json.dumps({
            "has_staged": True,
            "stat": stat_result.stdout,
            "diff": diff_result.stdout[:5000],  # Limit diff size for LLM context
            "files": files,
            "file_count": len(files)
        })

    except subprocess.CalledProcessError as e:
        return json.dumps({
            "has_staged": False,
            "error": f"Failed to get staged changes: {e.stderr}"
        })
    except Exception as e:
        return json.dumps({
            "has_staged": False,
            "error": f"Unexpected error: {str(e)}"
        })


@tool
def create_commit_tool(message: str, repo_path: str = ".") -> str:
    """
    Execute git commit with the given message.

    IMPORTANT: Only call this after the user has approved the commit message!

    Args:
        message: The commit message to use
        repo_path: Path to the git repository (default: current directory)

    Returns:
        JSON with:
        - success: Boolean indicating if commit succeeded
        - output: Git commit output
        - message: Status message
        - error: Error message if failed
    """
    try:
        # Validate message
        message = message.strip() if message else ""
        if not message:
            return json.dumps({
                "success": False,
                "error": "Empty commit message provided"
            })

        result = subprocess.run(
            ["git", "-C", repo_path, "commit", "-m", message],
            capture_output=True,
            text=True,
            check=True
        )

        return json.dumps({
            "success": True,
            "output": result.stdout,
            "message": f"Successfully committed: {message[:50]}..."
        })

    except subprocess.CalledProcessError as e:
        return json.dumps({
            "success": False,
            "error": f"Commit failed: {e.stderr}"
        })
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        })


@tool
def get_repo_info_tool(repo_path: str = ".") -> str:
    """
    Get basic repository info (current branch, remote URL, status).

    This is a read-only context tool for the main agent to understand
    the current repository state.

    Args:
        repo_path: Path to the git repository (default: current directory)

    Returns:
        JSON with:
        - repo_path: Absolute path to repository
        - branch: Current branch name
        - remote: Remote origin URL
        - has_staged_changes: Boolean indicating staged changes exist
        - error: Error message if not a git repo
    """
    try:
        # Get current branch
        branch_result = subprocess.run(
            ["git", "-C", repo_path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            check=True
        )
        branch = branch_result.stdout.strip()

        # Get remote URL (may not exist)
        try:
            remote_result = subprocess.run(
                ["git", "-C", repo_path, "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=True
            )
            remote = remote_result.stdout.strip()
        except subprocess.CalledProcessError:
            remote = "No remote configured"

        # Check if there are staged changes
        staged_check = subprocess.run(
            ["git", "-C", repo_path, "diff", "--staged", "--quiet"],
            capture_output=True
        )
        has_staged = staged_check.returncode != 0  # Non-zero = has changes

        return json.dumps({
            "repo_path": os.path.abspath(repo_path),
            "branch": branch,
            "remote": remote,
            "has_staged_changes": has_staged
        })

    except subprocess.CalledProcessError as e:
        return json.dumps({
            "error": f"Not a git repository or git error: {e.stderr}"
        })
    except Exception as e:
        return json.dumps({
            "error": f"Unexpected error: {str(e)}"
        })
