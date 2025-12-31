"""
OpenAI Native Tools - GPT-5.2 web search using web_search_preview

This module provides native web search tools for OpenAI models (GPT-5.2 and later)
that use the web_search_preview tool type, similar to how Anthropic models use
web_search_20250305.
"""
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
import json


# OpenAI's native web search tool spec (GPT-5.2+)
OPENAI_WEB_SEARCH_TOOL = {"type": "web_search_preview"}


def create_openai_web_search_tool(model: ChatOpenAI):
    """
    Create native web search tool for OpenAI models.
    Uses web_search_preview tool type (GPT-5.2 and later).

    Args:
        model: ChatOpenAI model instance

    Returns:
        Async tool function for web search
    """
    @tool
    async def web_search(query: str) -> str:
        """Search the web for current information using OpenAI's native web search.

        Args:
            query: The search query to look up

        Returns:
            Search results as a string
        """
        try:
            print(f"🔍 [OpenAI Web Search] Query: {query}")

            # Bind the web search tool to the model
            search_model = model.bind_tools([OPENAI_WEB_SEARCH_TOOL])

            # Invoke with search query
            response = await search_model.ainvoke(
                f"Search the web for: {query}. Return the search results with sources."
            )

            # Parse response - handle both string and structured outputs
            if hasattr(response, 'content'):
                result = response.content
            else:
                result = str(response)

            print(f"✅ [OpenAI Web Search] Got {len(result)} chars of results")
            return result

        except Exception as e:
            error_msg = f"Web search failed: {str(e)}"
            print(f"❌ [OpenAI Web Search] {error_msg}")
            return error_msg

    return web_search


def create_openai_web_fetch_tool(model: ChatOpenAI):
    """
    Create web fetch tool for OpenAI models.

    Note: OpenAI doesn't have a native web_fetch like Anthropic.
    This implementation uses web_search as a fallback to find and summarize
    content from a specific URL.

    Args:
        model: ChatOpenAI model instance

    Returns:
        Async tool function for web fetch
    """
    @tool
    async def web_fetch(url: str, prompt: str = "Summarize this page") -> str:
        """Fetch and analyze a web page.

        Note: Uses web search as OpenAI lacks native fetch capability.

        Args:
            url: The URL to fetch content from
            prompt: Instructions for what to extract/analyze

        Returns:
            Page content or summary as a string
        """
        try:
            print(f"🌐 [OpenAI Web Fetch] URL: {url}")
            print(f"📝 [OpenAI Web Fetch] Prompt: {prompt}")

            # Bind the web search tool to the model
            search_model = model.bind_tools([OPENAI_WEB_SEARCH_TOOL])

            # Use web search to find and summarize content from the URL
            response = await search_model.ainvoke(
                f"Find and analyze the content from this URL: {url}\n\nTask: {prompt}"
            )

            if hasattr(response, 'content'):
                result = response.content
            else:
                result = str(response)

            print(f"✅ [OpenAI Web Fetch] Got {len(result)} chars of content")
            return result

        except Exception as e:
            error_msg = f"Web fetch failed: {str(e)}"
            print(f"❌ [OpenAI Web Fetch] {error_msg}")
            return error_msg

    return web_fetch


# Convenience function to create both tools at once
def create_openai_native_tools(model: ChatOpenAI) -> tuple:
    """
    Create both web search and web fetch tools for OpenAI models.

    Args:
        model: ChatOpenAI model instance

    Returns:
        Tuple of (web_search_tool, web_fetch_tool)
    """
    return (
        create_openai_web_search_tool(model),
        create_openai_web_fetch_tool(model)
    )
