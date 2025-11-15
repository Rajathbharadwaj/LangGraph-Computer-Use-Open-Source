"""
Workflow Parser - Converts visual workflow JSON to LangGraph agent instructions

Takes drag-and-drop workflow JSON and converts it to structured prompts
that the X Growth Deep Agent can execute.
"""

import json
from typing import Dict, List, Any, Optional
from pathlib import Path


class WorkflowParser:
    """Parse workflow JSON and convert to agent instructions"""

    def __init__(self, workflow_json: Dict[str, Any]):
        self.workflow = workflow_json
        self.workflow_id = workflow_json.get("workflow_id")
        self.name = workflow_json.get("name")
        self.config = workflow_json.get("config", {})
        self.steps = workflow_json.get("steps", [])

    def parse(self) -> str:
        """
        Convert workflow JSON to structured agent prompt

        Returns:
            str: Structured prompt for the deep agent
        """
        prompt_parts = []

        # Header
        prompt_parts.append(f"🎯 WORKFLOW: {self.name}")
        prompt_parts.append(f"ID: {self.workflow_id}")
        prompt_parts.append(f"Description: {self.workflow.get('description', '')}")
        prompt_parts.append("")

        # Configuration
        if self.config:
            prompt_parts.append("⚙️ CONFIGURATION:")
            for key, value in self.config.items():
                prompt_parts.append(f"  - {key}: {value}")
            prompt_parts.append("")

        # Instructions
        prompt_parts.append("📋 EXECUTE THESE STEPS IN ORDER:")
        prompt_parts.append("")

        # Parse steps
        for i, step in enumerate(self.steps, 1):
            step_instructions = self._parse_step(step, step_number=i)
            prompt_parts.append(step_instructions)
            prompt_parts.append("")

        # Footer
        prompt_parts.append("✅ IMPORTANT REMINDERS:")
        prompt_parts.append("- Execute steps ONE at a time using task() delegation")
        prompt_parts.append("- Wait for each step to complete before moving to next")
        prompt_parts.append("- Track all actions in action_history.json")
        prompt_parts.append("- Check rate limits before each action")
        prompt_parts.append("- Use get_comprehensive_context() to see page state")

        if self.workflow.get("learning_enabled"):
            prompt_parts.append("- This workflow has learning enabled - track metrics!")

        return "\n".join(prompt_parts)

    def _parse_step(self, step: Dict[str, Any], step_number: int, indent_level: int = 0) -> str:
        """Parse a single step into instructions"""
        indent = "  " * indent_level
        step_type = step.get("type")
        description = step.get("description", "")

        if step_type == "navigate":
            return self._parse_navigate_step(step, step_number, indent)

        elif step_type == "analyze":
            return self._parse_analyze_step(step, step_number, indent)

        elif step_type == "loop":
            return self._parse_loop_step(step, step_number, indent)

        elif step_type == "action":
            return self._parse_action_step(step, step_number, indent)

        elif step_type == "research":
            return self._parse_research_step(step, step_number, indent)

        elif step_type == "memory":
            return self._parse_memory_step(step, step_number, indent)

        elif step_type == "condition":
            return self._parse_condition_step(step, step_number, indent)

        elif step_type == "filter":
            return self._parse_filter_step(step, step_number, indent)

        elif step_type == "end":
            return f"{indent}Step {step_number}: ✅ Workflow complete!"

        else:
            return f"{indent}Step {step_number}: {description}"

    def _parse_navigate_step(self, step: Dict, step_number: int, indent: str) -> str:
        url = step.get("params", {}).get("url", "")
        return f"""{indent}Step {step_number}: NAVIGATE
{indent}  → task("navigate", "Navigate to {url}")
{indent}  → Description: {step.get("description", "")}"""

    def _parse_analyze_step(self, step: Dict, step_number: int, indent: str) -> str:
        return f"""{indent}Step {step_number}: ANALYZE PAGE
{indent}  → Call get_comprehensive_context() to see current page
{indent}  → Parse the results to understand what's visible
{indent}  → Description: {step.get("description", "")}"""

    def _parse_loop_step(self, step: Dict, step_number: int, indent: str) -> str:
        loop_count = step.get("loop_count", 1)
        children = step.get("children", [])
        description = step.get("description", "")

        instructions = [f"{indent}Step {step_number}: LOOP (repeat {loop_count} times)"]
        instructions.append(f"{indent}  → {description}")
        instructions.append(f"{indent}  → For each iteration:")

        for i, child in enumerate(children, 1):
            child_instructions = self._parse_step(child, f"{step_number}.{i}", indent_level=1)
            instructions.append(child_instructions)

        return "\n".join(instructions)

    def _parse_action_step(self, step: Dict, step_number: int, indent: str) -> str:
        action = step.get("action", "")
        params = step.get("params", {})
        description = step.get("description", "")

        # Format params for display
        param_str = ", ".join([f"{k}='{v}'" for k, v in params.items()])

        return f"""{indent}Step {step_number}: ACTION - {action}
{indent}  → task("{self._map_action_to_subagent(action)}", "Execute {action}")
{indent}  → Parameters: {param_str}
{indent}  → Description: {description}"""

    def _parse_research_step(self, step: Dict, step_number: int, indent: str) -> str:
        query = step.get("params", {}).get("query", "")
        return f"""{indent}Step {step_number}: RESEARCH
{indent}  → task("research_topic", "Research: {query}")
{indent}  → Use web search to gather current information
{indent}  → Description: {step.get("description", "")}"""

    def _parse_memory_step(self, step: Dict, step_number: int, indent: str) -> str:
        action = step.get("action", "")
        params = step.get("params", {})

        if action == "save_to_history":
            return f"""{indent}Step {step_number}: SAVE TO MEMORY
{indent}  → Write action to action_history.json
{indent}  → Track: {params.get('action', '')}
{indent}  → Description: {step.get("description", "")}"""
        elif action == "read_file":
            path = params.get("path", "")
            return f"""{indent}Step {step_number}: READ FROM MEMORY
{indent}  → Read file: {path}
{indent}  → Description: {step.get("description", "")}"""
        else:
            return f"{indent}Step {step_number}: MEMORY - {action}"

    def _parse_condition_step(self, step: Dict, step_number: int, indent: str) -> str:
        condition = step.get("condition", "")
        description = step.get("description", "")

        return f"""{indent}Step {step_number}: CONDITION
{indent}  → Check if: {condition}
{indent}  → If true: proceed to step {step.get('if_true', 'next')}
{indent}  → If false: proceed to step {step.get('if_false', 'next')}
{indent}  → Description: {description}"""

    def _parse_filter_step(self, step: Dict, step_number: int, indent: str) -> str:
        action = step.get("action", "")
        params = step.get("params", {})
        description = step.get("description", "")

        # Format filter criteria
        criteria_str = ", ".join([f"{k}={v}" for k, v in params.items()])

        return f"""{indent}Step {step_number}: FILTER
{indent}  → Find: {action}
{indent}  → Criteria: {criteria_str}
{indent}  → Description: {description}"""

    def _map_action_to_subagent(self, action: str) -> str:
        """Map action name to subagent name"""
        action_map = {
            "navigate_to_url": "navigate",
            "get_comprehensive_context": "analyze_page",
            "like_post": "like_post",
            "unlike_post": "unlike_post",
            "comment_on_post": "comment_on_post",
            "create_post_on_x": "create_post",
            "research_topic": "research_topic",
            "scroll_page": "scroll",
            "click_at_coordinates": "click",
            "type_text": "type_text",
        }
        return action_map.get(action, action)


def load_workflow(workflow_path: str) -> Dict[str, Any]:
    """Load workflow JSON from file"""
    with open(workflow_path, 'r') as f:
        return json.load(f)


def parse_workflow(workflow_json: Dict[str, Any]) -> str:
    """
    Main entry point - parse workflow JSON to agent instructions

    Args:
        workflow_json: Workflow configuration as dict

    Returns:
        str: Structured prompt for deep agent
    """
    parser = WorkflowParser(workflow_json)
    return parser.parse()


def list_available_workflows(workflows_dir: str = "workflows") -> List[Dict[str, str]]:
    """List all available workflow files"""
    workflows_path = Path(workflows_dir)
    workflows = []

    if not workflows_path.exists():
        return workflows

    for workflow_file in workflows_path.glob("*.json"):
        try:
            with open(workflow_file, 'r') as f:
                workflow_data = json.load(f)
                workflows.append({
                    "id": workflow_data.get("workflow_id"),
                    "name": workflow_data.get("name"),
                    "description": workflow_data.get("description"),
                    "category": workflow_data.get("category"),
                    "difficulty": workflow_data.get("difficulty"),
                    "estimated_time_minutes": workflow_data.get("estimated_time_minutes"),
                    "expected_roi": workflow_data.get("expected_roi"),
                    "file_path": str(workflow_file)
                })
        except Exception as e:
            print(f"Error loading workflow {workflow_file}: {e}")
            continue

    return workflows


# Example usage
if __name__ == "__main__":
    print("=" * 60)
    print("Workflow Parser - Example Usage")
    print("=" * 60)

    # List available workflows
    workflows = list_available_workflows()
    print(f"\n📋 Available Workflows: {len(workflows)}")
    for wf in workflows:
        print(f"  • {wf['name']} ({wf['id']})")
        print(f"    Category: {wf['category']}, ROI: {wf['expected_roi']}")

    # Parse example workflow
    if workflows:
        print(f"\n🔄 Parsing: {workflows[0]['name']}")
        print("=" * 60)

        workflow_json = load_workflow(workflows[0]['file_path'])
        prompt = parse_workflow(workflow_json)

        print(prompt)
        print("\n" + "=" * 60)
        print("✅ Parser ready to use!")
