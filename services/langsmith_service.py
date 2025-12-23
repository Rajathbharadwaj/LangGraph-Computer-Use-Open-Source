"""
LangSmith Cost Tracking Service

Retrieves actual costs from LangSmith API for usage-based billing.
"""
import os
import logging
from langsmith import Client
from typing import Dict, Any

logger = logging.getLogger(__name__)


class LangSmithService:
    """Service for retrieving cost data from LangSmith."""

    def __init__(self):
        self.client = Client(api_key=os.getenv("LANGSMITH_API_KEY"))

    def get_run_cost(self, run_id: str) -> Dict[str, Any]:
        """
        Get the total cost for a completed run.

        Args:
            run_id: The LangSmith run ID

        Returns:
            Dict with cost breakdown:
            {
                "total_cost": 4.55,
                "prompt_tokens": 150000,
                "completion_tokens": 50000,
                "total_tokens": 200000,
                "model": "claude-sonnet-4-20250514",
                "latency_ms": 5000
            }
        """
        try:
            run = self.client.read_run(run_id)

            # Get total cost - LangSmith calculates this automatically
            total_cost = getattr(run, 'total_cost', None) or 0

            # Get token counts
            prompt_tokens = getattr(run, 'prompt_tokens', None) or 0
            completion_tokens = getattr(run, 'completion_tokens', None) or 0

            # Get model name from metadata
            extra = getattr(run, 'extra', {}) or {}
            metadata = extra.get('metadata', {}) if isinstance(extra, dict) else {}
            model = metadata.get('ls_model_name', 'unknown')

            # Get latency
            latency_ms = getattr(run, 'latency_ms', None) or 0

            return {
                "total_cost": total_cost,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
                "model": model,
                "latency_ms": latency_ms,
                "run_id": run_id,
            }
        except Exception as e:
            logger.error(f"Failed to get LangSmith run cost for {run_id}: {e}")
            return {
                "total_cost": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "model": "unknown",
                "latency_ms": 0,
                "run_id": run_id,
                "error": str(e)
            }

    def get_run_cost_with_children(self, run_id: str) -> Dict[str, Any]:
        """
        Get the total cost for a run including all child runs.

        This is useful for getting the total cost of an entire agent session
        which may have multiple LLM calls as child runs.

        Args:
            run_id: The parent LangSmith run ID

        Returns:
            Dict with aggregated cost breakdown
        """
        try:
            # Get the parent run
            parent_run = self.client.read_run(run_id)

            total_cost = getattr(parent_run, 'total_cost', None) or 0
            total_prompt_tokens = getattr(parent_run, 'prompt_tokens', None) or 0
            total_completion_tokens = getattr(parent_run, 'completion_tokens', None) or 0

            # List all child runs and sum their costs
            child_runs = list(self.client.list_runs(
                project_name=os.getenv("LANGSMITH_PROJECT", "default"),
                filter=f'eq(parent_run_id, "{run_id}")'
            ))

            for child in child_runs:
                child_cost = getattr(child, 'total_cost', None) or 0
                child_prompt = getattr(child, 'prompt_tokens', None) or 0
                child_completion = getattr(child, 'completion_tokens', None) or 0

                total_cost += child_cost
                total_prompt_tokens += child_prompt
                total_completion_tokens += child_completion

            return {
                "total_cost": total_cost,
                "prompt_tokens": total_prompt_tokens,
                "completion_tokens": total_completion_tokens,
                "total_tokens": total_prompt_tokens + total_completion_tokens,
                "child_run_count": len(child_runs),
                "run_id": run_id,
            }
        except Exception as e:
            logger.error(f"Failed to get LangSmith run cost with children for {run_id}: {e}")
            # Fall back to single run cost
            return self.get_run_cost(run_id)

    @staticmethod
    def cost_to_credits(cost: float, markup: float = 1.5) -> int:
        """
        Convert actual cost to credits with markup.

        Formula: credits = cost × 100 × markup

        At markup=1.5:
        - $1.00 actual cost = 150 credits charged
        - $10.00 actual cost = 1,500 credits charged

        Args:
            cost: Actual cost in dollars from LangSmith
            markup: Profit margin multiplier (1.5 = 50% markup)

        Returns:
            Number of credits to charge
        """
        # $1 = 100 credits base, then apply markup
        base_credits = cost * 100
        return int(base_credits * markup)

    @staticmethod
    def credits_to_cost(credits: int, markup: float = 1.5) -> float:
        """
        Convert credits back to approximate actual cost.

        Useful for displaying cost estimates to users.

        Args:
            credits: Number of credits
            markup: The markup multiplier used

        Returns:
            Estimated actual cost in dollars
        """
        return credits / (100 * markup)


# Usage-based billing constants
USAGE_BILLING_CONFIG = {
    "markup_multiplier": 1.5,      # 50% profit margin
    "cents_per_credit": 1,         # $0.01 = 1 credit base
    "minimum_credits": 50,         # Minimum charge per session
    "minimum_cost": 0.50,          # $0.50 fallback if LangSmith returns 0
}
