"""
Linear GraphQL API Client for Work Integrations.

Handles Linear API calls for:
- Issues (create, update, list)
- Projects and cycles
- Comments and activity
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
import httpx

from ..config import get_work_integrations_settings

logger = logging.getLogger(__name__)

LINEAR_API_URL = "https://api.linear.app/graphql"


class LinearClient:
    """
    Linear GraphQL API client for work integrations.

    Uses OAuth tokens to access workspace data.
    """

    def __init__(self, access_token: str):
        """Initialize with access token."""
        self.access_token = access_token
        self.settings = get_work_integrations_settings()
        self._headers = {
            "Authorization": access_token,
            "Content-Type": "application/json",
        }

    async def _query(
        self,
        query: str,
        variables: Dict[str, Any] = None,
    ) -> Dict[str, Any]:
        """Execute a GraphQL query."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                LINEAR_API_URL,
                headers=self._headers,
                json={
                    "query": query,
                    "variables": variables or {},
                },
            )
            response.raise_for_status()
            data = response.json()

            if "errors" in data:
                raise Exception(f"Linear API error: {data['errors']}")

            return data.get("data", {})

    # =========================================================================
    # User & Organization
    # =========================================================================

    async def get_viewer(self) -> Dict[str, Any]:
        """Get current user info."""
        query = """
        query {
            viewer {
                id
                name
                email
                displayName
                avatarUrl
            }
        }
        """
        data = await self._query(query)
        return data.get("viewer", {})

    async def get_organization(self) -> Dict[str, Any]:
        """Get organization info."""
        query = """
        query {
            organization {
                id
                name
                urlKey
                logoUrl
            }
        }
        """
        data = await self._query(query)
        return data.get("organization", {})

    # =========================================================================
    # Teams
    # =========================================================================

    async def list_teams(self) -> List[Dict[str, Any]]:
        """List all teams in the organization."""
        query = """
        query {
            teams {
                nodes {
                    id
                    name
                    key
                    description
                    icon
                    color
                }
            }
        }
        """
        data = await self._query(query)
        return data.get("teams", {}).get("nodes", [])

    async def get_team(self, team_id: str) -> Dict[str, Any]:
        """Get a specific team."""
        query = """
        query($id: String!) {
            team(id: $id) {
                id
                name
                key
                description
                icon
                color
                activeCycle {
                    id
                    name
                    number
                }
            }
        }
        """
        data = await self._query(query, {"id": team_id})
        return data.get("team", {})

    # =========================================================================
    # Issues
    # =========================================================================

    async def list_issues(
        self,
        team_id: str = None,
        assignee_id: str = None,
        states: List[str] = None,
        limit: int = 50,
        updated_after: datetime = None,
    ) -> List[Dict[str, Any]]:
        """
        List issues with optional filters.

        Args:
            team_id: Filter by team
            assignee_id: Filter by assignee
            states: Filter by state names
            limit: Maximum issues to return
            updated_after: Only issues updated after this time

        Returns:
            List of issue objects
        """
        filters = []
        if team_id:
            filters.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')
        if assignee_id:
            filters.append(f'assignee: {{ id: {{ eq: "{assignee_id}" }} }}')
        if updated_after:
            filters.append(f'updatedAt: {{ gte: "{updated_after.isoformat()}" }}')

        filter_str = ", ".join(filters)
        if filter_str:
            filter_str = f"filter: {{ {filter_str} }}"

        query = f"""
        query($first: Int!) {{
            issues({filter_str}, first: $first, orderBy: updatedAt) {{
                nodes {{
                    id
                    identifier
                    title
                    description
                    priority
                    priorityLabel
                    url
                    state {{
                        id
                        name
                        type
                    }}
                    assignee {{
                        id
                        name
                    }}
                    project {{
                        id
                        name
                    }}
                    cycle {{
                        id
                        name
                        number
                    }}
                    createdAt
                    updatedAt
                    completedAt
                }}
            }}
        }}
        """
        data = await self._query(query, {"first": limit})
        return data.get("issues", {}).get("nodes", [])

    async def get_issue(self, issue_id: str) -> Dict[str, Any]:
        """Get a specific issue by ID."""
        query = """
        query($id: String!) {
            issue(id: $id) {
                id
                identifier
                title
                description
                priority
                priorityLabel
                url
                state {
                    id
                    name
                    type
                }
                assignee {
                    id
                    name
                }
                project {
                    id
                    name
                }
                labels {
                    nodes {
                        id
                        name
                        color
                    }
                }
                comments {
                    nodes {
                        id
                        body
                        createdAt
                        user {
                            id
                            name
                        }
                    }
                }
                createdAt
                updatedAt
                completedAt
            }
        }
        """
        data = await self._query(query, {"id": issue_id})
        return data.get("issue", {})

    # =========================================================================
    # Cycles
    # =========================================================================

    async def list_cycles(
        self,
        team_id: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """List cycles for a team."""
        query = """
        query($teamId: String!, $first: Int!) {
            team(id: $teamId) {
                cycles(first: $first, orderBy: createdAt) {
                    nodes {
                        id
                        name
                        number
                        startsAt
                        endsAt
                        completedAt
                        progress
                        issueCountHistory
                        completedIssueCountHistory
                    }
                }
            }
        }
        """
        data = await self._query(query, {"teamId": team_id, "first": limit})
        return data.get("team", {}).get("cycles", {}).get("nodes", [])

    async def get_active_cycle(self, team_id: str) -> Optional[Dict[str, Any]]:
        """Get the active cycle for a team."""
        team = await self.get_team(team_id)
        return team.get("activeCycle")

    # =========================================================================
    # Projects
    # =========================================================================

    async def list_projects(
        self,
        team_id: str = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List projects."""
        filter_str = ""
        if team_id:
            filter_str = f'filter: {{ accessibleTeams: {{ id: {{ eq: "{team_id}" }} }} }}'

        query = f"""
        query($first: Int!) {{
            projects({filter_str}, first: $first) {{
                nodes {{
                    id
                    name
                    description
                    icon
                    color
                    state
                    progress
                    url
                    startDate
                    targetDate
                    completedAt
                }}
            }}
        }}
        """
        data = await self._query(query, {"first": limit})
        return data.get("projects", {}).get("nodes", [])

    # =========================================================================
    # Activity
    # =========================================================================

    async def get_user_activity(
        self,
        user_id: str,
        since: datetime = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Get recent activity for a user.

        Returns issues created/completed and comments made.
        """
        if since is None:
            since = datetime.utcnow() - timedelta(days=1)

        # Get issues assigned to user that were recently updated
        issues = await self.list_issues(
            assignee_id=user_id,
            updated_after=since,
            limit=limit,
        )

        return issues

    # =========================================================================
    # Webhooks
    # =========================================================================

    async def create_webhook(
        self,
        url: str,
        team_id: str = None,
        label: str = "Parallel Universe",
        resource_types: List[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a webhook for the organization.

        Args:
            url: Webhook URL
            team_id: Optional team to scope to
            label: Webhook label
            resource_types: Event types to subscribe to

        Returns:
            Created webhook object
        """
        if resource_types is None:
            resource_types = ["Issue", "Comment", "Project", "Cycle"]

        mutation = """
        mutation($input: WebhookCreateInput!) {
            webhookCreate(input: $input) {
                success
                webhook {
                    id
                    url
                    enabled
                    resourceTypes
                }
            }
        }
        """

        input_data = {
            "url": url,
            "label": label,
            "resourceTypes": resource_types,
        }
        if team_id:
            input_data["teamId"] = team_id

        data = await self._query(mutation, {"input": input_data})
        return data.get("webhookCreate", {}).get("webhook", {})


def get_linear_client(access_token: str) -> LinearClient:
    """Create a Linear client with the given access token."""
    return LinearClient(access_token)
