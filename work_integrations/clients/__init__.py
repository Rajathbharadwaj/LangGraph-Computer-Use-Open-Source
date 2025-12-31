"""
Platform API clients for Work Integrations.

Each client handles API calls to their respective platform:
- GitHub: REST API for repos, commits, PRs, releases
- Slack: Web API for channels, messages
- Notion: API for databases, pages
- Linear: GraphQL API for issues, projects
- Figma: REST API for files, comments
"""

from .github_client import GitHubClient, get_github_client
from .slack_client import SlackClient, get_slack_client
from .linear_client import LinearClient, get_linear_client
from .notion_client import NotionClient, get_notion_client
from .figma_client import FigmaClient, get_figma_client

__all__ = [
    # GitHub
    "GitHubClient",
    "get_github_client",
    # Slack
    "SlackClient",
    "get_slack_client",
    # Linear
    "LinearClient",
    "get_linear_client",
    # Notion
    "NotionClient",
    "get_notion_client",
    # Figma
    "FigmaClient",
    "get_figma_client",
]
