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

__all__ = ["GitHubClient", "get_github_client"]
