"""
JSON Workflow Loader - Converts structured JSON workflows into natural language prompts for the deep agent.

The deep agent is an autonomous LLM agent, not a step-executor. Instead of executing predefined steps,
we convert the JSON workflow structure into a comprehensive natural language prompt that guides the agent.
"""

import json
from typing import Dict, Any, Optional
from pathlib import Path


def load_json_workflow(workflow_id: str) -> Optional[Dict[str, Any]]:
    """
    Load a JSON workflow file by ID.

    Args:
        workflow_id: The workflow ID (e.g., "reply_guy_strategy")

    Returns:
        Parsed JSON workflow or None if not found
    """
    workflow_dir = Path(__file__).parent / "workflows"
    workflow_path = workflow_dir / f"{workflow_id}.json"

    if not workflow_path.exists():
        print(f"❌ Workflow file not found: {workflow_path}")
        return None

    try:
        with open(workflow_path, 'r') as f:
            workflow = json.load(f)
        print(f"✅ Loaded JSON workflow: {workflow_id}")
        return workflow
    except Exception as e:
        print(f"❌ Error loading workflow {workflow_id}: {e}")
        return None


def json_workflow_to_prompt(workflow: Dict[str, Any]) -> str:
    """
    Convert a JSON workflow structure into a natural language prompt for the deep agent.

    The agent will use this prompt as guidance for its autonomous decision-making,
    rather than executing predefined steps.

    Args:
        workflow: Parsed JSON workflow dictionary

    Returns:
        Natural language prompt string
    """
    # Extract workflow metadata
    name = workflow.get("name", "Unknown Workflow")
    description = workflow.get("description", "")
    category = workflow.get("category", "general")
    estimated_time = workflow.get("estimated_time_minutes", 30)
    config = workflow.get("config", {})

    # Start building the prompt
    prompt_parts = [
        f"# {name}",
        "",
        f"**Category:** {category}",
        f"**Time Budget:** ~{estimated_time} minutes",
        "",
        "## Objective",
        description,
        "",
        "## Configuration Parameters",
    ]

    # Add configuration as constraints
    for key, value in config.items():
        # Convert snake_case to Title Case
        readable_key = key.replace("_", " ").title()
        prompt_parts.append(f"- **{readable_key}:** {value}")

    prompt_parts.append("")
    prompt_parts.append("## Execution Strategy")

    # Convert steps to natural language instructions
    steps = workflow.get("steps", [])
    prompt_parts.append("")
    prompt_parts.append("Follow this general strategy:")
    prompt_parts.append("")

    step_instructions = _convert_steps_to_instructions(steps, config)
    prompt_parts.extend(step_instructions)

    # Add success metrics
    success_metrics = workflow.get("success_metrics", {})
    if success_metrics:
        prompt_parts.append("")
        prompt_parts.append("## Success Metrics to Track")
        for metric_name in success_metrics.keys():
            readable_name = metric_name.replace("_", " ").title()
            prompt_parts.append(f"- {readable_name}")

    # Add learning note if enabled
    if workflow.get("learning_enabled", False):
        prompt_parts.append("")
        prompt_parts.append("## Learning")
        prompt_parts.append("After execution, analyze what worked well and what didn't. Save insights to memory for future improvements.")

    return "\n".join(prompt_parts)


def _convert_steps_to_instructions(steps: list, config: Dict[str, Any]) -> list:
    """
    Convert structured JSON steps into natural language instructions.

    Args:
        steps: List of step dictionaries from JSON workflow
        config: Configuration dictionary for template substitution

    Returns:
        List of instruction strings
    """
    instructions = []

    for i, step in enumerate(steps, 1):
        step_type = step.get("type", "unknown")
        description = step.get("description", "")
        action = step.get("action", "")
        params = step.get("params", {})

        # Substitute config template variables in params
        params = _substitute_templates(params, config)

        # Convert step type to instruction
        if step_type == "navigate":
            url = params.get("url", "")
            instructions.append(f"{i}. **Navigate:** {description or f'Go to {url}'}")

        elif step_type == "analyze":
            instructions.append(f"{i}. **Analyze:** {description or 'Examine the current page context'}")

        elif step_type == "loop":
            loop_count = step.get("loop_count", "multiple")
            # Substitute template in loop_count
            if isinstance(loop_count, str) and "{{" in loop_count:
                loop_count = _substitute_single_template(loop_count, config)

            instructions.append(f"{i}. **Repeat {loop_count} times:** {description}")

            # Process children steps
            children = step.get("children", [])
            if children:
                child_instructions = _convert_steps_to_instructions(children, config)
                for child_inst in child_instructions:
                    instructions.append(f"   {child_inst}")

        elif step_type == "filter":
            instructions.append(f"{i}. **Filter:** {description}")
            if params:
                criteria = ", ".join(f"{k}={v}" for k, v in params.items())
                instructions.append(f"   - Criteria: {criteria}")

        elif step_type == "research":
            query = params.get("query", "the topic")
            instructions.append(f"{i}. **Research:** {description or f'Research {query}'}")

        elif step_type == "action":
            instructions.append(f"{i}. **Action:** {description or f'Execute {action}'}")
            if params:
                param_desc = ", ".join(f"{k}={v}" for k, v in params.items() if not str(v).startswith("{{"))
                if param_desc:
                    instructions.append(f"   - Parameters: {param_desc}")

        elif step_type == "memory":
            instructions.append(f"{i}. **Memory:** {description or 'Save action to memory'}")

        elif step_type == "end":
            instructions.append(f"{i}. **Complete:** {description or 'Workflow complete'}")

        else:
            # Generic fallback
            if description:
                instructions.append(f"{i}. {description}")

    return instructions


def _substitute_templates(params: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Substitute {{config.key}} template variables with actual config values.

    Args:
        params: Parameter dictionary that may contain template strings
        config: Configuration dictionary with substitution values

    Returns:
        Dictionary with templates substituted
    """
    substituted = {}
    for key, value in params.items():
        if isinstance(value, str):
            substituted[key] = _substitute_single_template(value, config)
        else:
            substituted[key] = value
    return substituted


def _substitute_single_template(template: str, config: Dict[str, Any]) -> str:
    """
    Substitute a single template string like "{{config.max_likes}}" with the actual value.

    Args:
        template: Template string (e.g., "{{config.max_likes}}")
        config: Configuration dictionary

    Returns:
        Substituted string or original if no match
    """
    if not isinstance(template, str) or "{{" not in template:
        return template

    # Extract variable name from {{config.variable_name}}
    import re
    matches = re.findall(r'\{\{config\.(\w+)\}\}', template)

    result = template
    for var_name in matches:
        if var_name in config:
            result = result.replace(f"{{{{config.{var_name}}}}}", str(config[var_name]))

    return result


def get_json_workflow_prompt(workflow_id: str) -> Optional[str]:
    """
    Load a JSON workflow and convert it to a natural language prompt.

    This is the main entry point for the deep agent.

    Args:
        workflow_id: The workflow ID (e.g., "reply_guy_strategy")

    Returns:
        Natural language prompt string or None if workflow not found
    """
    workflow = load_json_workflow(workflow_id)
    if not workflow:
        return None

    return json_workflow_to_prompt(workflow)


def list_json_workflows() -> list:
    """
    List all available JSON workflows.

    Returns:
        List of workflow IDs
    """
    workflow_dir = Path(__file__).parent / "workflows"
    if not workflow_dir.exists():
        return []

    workflows = []
    for file_path in workflow_dir.glob("*.json"):
        workflow_id = file_path.stem
        workflows.append(workflow_id)

    return workflows


# Test function
if __name__ == "__main__":
    print("🧪 Testing JSON Workflow Loader\n")

    # List available workflows
    print("Available JSON workflows:")
    workflows = list_json_workflows()
    for wf_id in workflows:
        print(f"  - {wf_id}")

    print("\n" + "="*80 + "\n")

    # Test loading a workflow
    if workflows:
        test_id = "reply_guy_strategy"
        print(f"Loading workflow: {test_id}\n")
        prompt = get_json_workflow_prompt(test_id)

        if prompt:
            print("Generated Prompt:")
            print("="*80)
            print(prompt)
            print("="*80)
        else:
            print(f"❌ Failed to load workflow: {test_id}")
