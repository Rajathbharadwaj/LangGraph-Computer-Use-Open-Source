"""
Utility functions shared across agents.
"""

import json
from pathlib import Path


def load_template(mode: str, template_name: str) -> dict:
    """
    Load mode-specific template JSON file.

    Args:
        mode: The generation mode (ecom_product, local_business, personal_brand)
        template_name: Name of the template file (without .json extension)

    Returns:
        Parsed JSON as dict

    Raises:
        ValueError: If template file doesn't exist
        json.JSONDecodeError: If template is invalid JSON
    """
    base_dir = Path(__file__).parent.parent
    template_path = base_dir / "templates" / mode / f"{template_name}.json"

    if not template_path.exists():
        raise ValueError(
            f"No {template_name} template for mode: {mode}. "
            f"Expected file at: {template_path}"
        )

    return json.loads(template_path.read_text())


def generate_id(prefix: str, index: int) -> str:
    """Generate a consistent ID for pipeline objects."""
    return f"{prefix}_{index:03d}"
