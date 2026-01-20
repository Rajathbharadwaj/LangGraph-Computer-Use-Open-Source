#!/usr/bin/env python3
"""
Commit Critic - AI-powered commit message analyzer.

Simple entry point that matches the challenge requirements:
    python commit_critic.py --analyze
    python commit_critic.py --analyze --url="https://github.com/..."
    python commit_critic.py --write
"""

from commit_critic.cli import main

if __name__ == "__main__":
    main()
