"""
CRM Deep Agent Package

Provides AI-powered customer relationship management:
- Draft reply generation for conversations
- Smart customer tagging
- Automated follow-up scheduling
- Attribution tracking

Main agent: Orchestrates CRM workflows
Subagents: Execute atomic actions (draft reply, send message, tag customer, etc.)
"""

from .prompts import MAIN_AGENT_PROMPT, get_main_prompt_with_context
from .subagents import get_crm_subagents, get_subagent_names

__all__ = [
    "MAIN_AGENT_PROMPT",
    "get_main_prompt_with_context",
    "get_crm_subagents",
    "get_subagent_names",
]
