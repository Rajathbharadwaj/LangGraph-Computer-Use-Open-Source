"""
Anthropic Native Tools Module

Provides Anthropic's server-side tools (web_fetch, web_search, memory) for use
with LangChain and the Deep Agent architecture.

These tools use Anthropic's built-in capabilities:
- web_fetch: Server-side URL content fetching with citations
- web_search: Server-side web search with citations
- memory: Client-side persistent memory with LangGraph Store backend

Usage:
    from anthropic_native_tools import (
        create_web_fetch_tool,
        create_web_search_tool,
        create_memory_tool,
    )

    # Create tools with model/user context
    web_fetch = create_web_fetch_tool(model)
    web_search = create_web_search_tool(model)
    memory = create_memory_tool(user_id)
"""

from typing import Literal, Optional, Any
from langchain_core.tools import tool
from langchain.tools import ToolRuntime


# ============================================================================
# TOOL SPECIFICATIONS (Anthropic Native Format)
# ============================================================================

# Web Fetch Tool - server-side URL content fetching
WEB_FETCH_TOOL_SPEC = {
    "type": "web_fetch_20250910",
    "name": "web_fetch",
    "max_uses": 5,
}

# Web Search Tool - server-side web search
WEB_SEARCH_TOOL_SPEC = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}

# Memory Tool - client-side persistent storage
# Using dict format for compatibility (BetaMemoryTool20250818Param equivalent)
MEMORY_TOOL_SPEC = {
    "type": "memory_20250818",
    "name": "memory",
}


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_text_from_response(response) -> str:
    """
    Extract text content from a LangChain response.

    Handles different response formats:
    - String content
    - List of content blocks (Anthropic format)
    - AIMessage objects
    """
    if not response:
        return ""

    result = ""

    # Handle response.content
    if hasattr(response, 'content'):
        content = response.content

        if isinstance(content, str):
            result = content
        elif isinstance(content, list):
            # Content blocks format
            for block in content:
                if isinstance(block, dict):
                    if block.get('type') == 'text':
                        result += block.get('text', '')
                    elif block.get('type') == 'tool_result':
                        result += str(block.get('content', ''))
                elif hasattr(block, 'text'):
                    result += block.text
                elif isinstance(block, str):
                    result += block
    elif isinstance(response, str):
        result = response

    return result.strip()


# ============================================================================
# WEB FETCH TOOL
# ============================================================================

def create_web_fetch_tool(model):
    """
    Create a web fetch tool that uses Anthropic's server-side URL fetching.

    This tool can:
    - Fetch content from any URL (web pages, PDFs)
    - Analyze and summarize the content
    - Provide citations from the source

    Args:
        model: ChatAnthropic model instance

    Returns:
        LangChain tool function for web fetching
    """

    @tool
    async def web_fetch(
        url: str,
        prompt: str = "Summarize the key points from this content"
    ) -> str:
        """
        Fetch and analyze content from a URL using Anthropic's server-side fetching.

        Use this to:
        - Read documentation, articles, or blog posts
        - Analyze PDF documents
        - Get current information from specific sources
        - Research specific URLs mentioned in discussions

        Args:
            url: The URL to fetch content from (web page or PDF)
            prompt: What to focus on when analyzing the content

        Returns:
            Analysis of the fetched content with key insights
        """
        try:
            print(f"🌐 [Web Fetch] Fetching: {url[:100]}...")

            # Bind the web fetch tool to the model
            bound_model = model.bind_tools([WEB_FETCH_TOOL_SPEC])

            # Create the fetch request
            fetch_prompt = f"""Please fetch and analyze the content at this URL:

URL: {url}

ANALYSIS FOCUS:
{prompt}

After fetching, provide:
1. A concise summary of the main content
2. Key facts, statistics, or insights
3. Relevant quotes or data points
4. Any important context from the source"""

            # Execute the fetch (server-side)
            response = await bound_model.ainvoke(fetch_prompt)

            # Extract the result
            result = extract_text_from_response(response)

            if result:
                print(f"✅ [Web Fetch] Success ({len(result)} chars)")
                return result
            else:
                print("⚠️ [Web Fetch] No content returned")
                return f"Could not fetch content from {url}"

        except Exception as e:
            print(f"❌ [Web Fetch] Error: {e}")
            return f"Error fetching {url}: {str(e)}"

    return web_fetch


# ============================================================================
# WEB SEARCH TOOL
# ============================================================================

def create_web_search_tool(model):
    """
    Create a web search tool that uses Anthropic's server-side search.

    This tool can:
    - Search the web for current information
    - Find recent news, trends, and data
    - Provide citations from search results

    Args:
        model: ChatAnthropic model instance

    Returns:
        LangChain tool function for web searching
    """

    @tool
    async def web_search(query: str) -> str:
        """
        Search the web for current information using Anthropic's server-side search.

        Use this to:
        - Research topics before creating content
        - Find current news and trends
        - Gather facts, statistics, and expert opinions
        - Understand context around discussions

        Args:
            query: The search query or topic to research

        Returns:
            Search results summary with key findings and sources
        """
        try:
            print(f"🔍 [Web Search] Searching: {query[:100]}...")

            # Bind the web search tool to the model
            bound_model = model.bind_tools([WEB_SEARCH_TOOL_SPEC])

            # Create the search request
            search_prompt = f"""Search the web for information about:

QUERY: {query}

RESEARCH TASK:
1. Find the most relevant and current information
2. Look for recent news, trends, or developments
3. Gather statistics, data points, or expert opinions
4. Identify unique angles or insights

After searching, provide:
- Key findings (2-3 main points)
- Relevant facts or statistics
- Sources or citations for verification
- Any important context or nuance"""

            # Execute the search (server-side)
            response = await bound_model.ainvoke(search_prompt)

            # Extract the result
            result = extract_text_from_response(response)

            if result:
                print(f"✅ [Web Search] Success ({len(result)} chars)")
                return result
            else:
                print("⚠️ [Web Search] No results returned")
                return f"No search results found for: {query}"

        except Exception as e:
            print(f"❌ [Web Search] Error: {e}")
            return f"Error searching for '{query}': {str(e)}"

    return web_search


# ============================================================================
# MEMORY TOOL
# ============================================================================

def create_memory_tool(user_id: str):
    """
    Create a memory tool that uses LangGraph Store for persistence.

    This tool provides Anthropic's memory interface backed by LangGraph Store:
    - view: List memories or read specific memory
    - create: Create new memory at path
    - str_replace: Replace text in memory
    - insert: Insert text at line
    - delete: Delete memory
    - rename: Rename memory path

    Args:
        user_id: User ID for namespacing memories

    Returns:
        LangChain tool function with memory operations
    """

    @tool(extras={"provider_tool_definition": MEMORY_TOOL_SPEC})
    async def memory(
        command: Literal["view", "create", "str_replace", "insert", "delete", "rename"],
        path: str,
        content: Optional[str] = None,
        old_str: Optional[str] = None,
        new_str: Optional[str] = None,
        insert_line: Optional[int] = None,
        new_path: Optional[str] = None,
        runtime: ToolRuntime = None,
        **kw,
    ) -> str:
        """
        Manage persistent memory across conversations using Anthropic's memory interface.

        Commands:
        - view: List all memories (path="/memories") or read specific memory
        - create: Create new memory with content at path
        - str_replace: Replace old_str with new_str in memory at path
        - insert: Insert content at insert_line in memory at path
        - delete: Delete memory at path
        - rename: Rename memory from path to new_path

        Args:
            command: The memory operation to perform
            path: Memory path (e.g., "/memories/notes/topic")
            content: Content for create/insert operations
            old_str: String to replace (for str_replace)
            new_str: Replacement string (for str_replace)
            insert_line: Line number for insert operation
            new_path: New path for rename operation

        Returns:
            Result of the memory operation
        """
        try:
            # Get store from runtime
            store = getattr(runtime, 'store', None) if runtime else None

            if not store:
                print("⚠️ [Memory] No store available in runtime")
                return "Error: Memory store not available"

            # Namespace for this user's memories
            namespace = (user_id, "anthropic_memory")

            # Normalize path (remove leading /memories if present)
            normalized_path = path
            if path.startswith("/memories/"):
                normalized_path = path[10:]  # Remove "/memories/"
            elif path == "/memories":
                normalized_path = ""

            print(f"📝 [Memory] {command} at {path} (normalized: {normalized_path})")

            if command == "view":
                if not normalized_path:
                    # List all memories
                    items = list(store.search(namespace, limit=100))
                    if not items:
                        return "No memories stored yet."
                    memory_list = [f"/memories/{item.key}" for item in items]
                    return "Stored memories:\n" + "\n".join(memory_list)
                else:
                    # Read specific memory
                    item = store.get(namespace, normalized_path)
                    if item and item.value:
                        content_val = item.value.get("content", str(item.value))
                        return content_val
                    return f"No memory found at {path}"

            elif command == "create":
                if not content:
                    return "Error: content required for create command"
                store.put(namespace, normalized_path, {"content": content})
                print(f"✅ [Memory] Created: {path}")
                return f"Created memory at {path}"

            elif command == "str_replace":
                if old_str is None:
                    return "Error: old_str required for str_replace command"

                # Get existing content
                item = store.get(namespace, normalized_path)
                if not item or not item.value:
                    return f"No memory found at {path}"

                existing_content = item.value.get("content", str(item.value))

                # Replace
                new_content = existing_content.replace(old_str, new_str or "", 1)
                store.put(namespace, normalized_path, {"content": new_content})
                print(f"✅ [Memory] Updated: {path}")
                return f"Updated memory at {path}"

            elif command == "insert":
                if content is None or insert_line is None:
                    return "Error: content and insert_line required for insert command"

                # Get existing content
                item = store.get(namespace, normalized_path)
                existing_content = ""
                if item and item.value:
                    existing_content = item.value.get("content", str(item.value))

                # Insert at line
                lines = existing_content.split("\n") if existing_content else []
                lines.insert(min(insert_line, len(lines)), content)
                new_content = "\n".join(lines)

                store.put(namespace, normalized_path, {"content": new_content})
                print(f"✅ [Memory] Inserted at line {insert_line}: {path}")
                return f"Inserted content at line {insert_line} in {path}"

            elif command == "delete":
                store.delete(namespace, normalized_path)
                print(f"✅ [Memory] Deleted: {path}")
                return f"Deleted memory at {path}"

            elif command == "rename":
                if not new_path:
                    return "Error: new_path required for rename command"

                # Get existing content
                item = store.get(namespace, normalized_path)
                if not item or not item.value:
                    return f"No memory found at {path}"

                # Normalize new path
                new_normalized = new_path
                if new_path.startswith("/memories/"):
                    new_normalized = new_path[10:]

                # Copy to new path and delete old
                store.put(namespace, new_normalized, item.value)
                store.delete(namespace, normalized_path)
                print(f"✅ [Memory] Renamed: {path} -> {new_path}")
                return f"Renamed {path} to {new_path}"

            else:
                return f"Unknown command: {command}"

        except Exception as e:
            print(f"❌ [Memory] Error: {e}")
            import traceback
            traceback.print_exc()
            return f"Error executing {command}: {str(e)}"

    return memory


# ============================================================================
# CONVENIENCE FUNCTIONS
# ============================================================================

def get_all_native_tools(model, user_id: str = None):
    """
    Get all Anthropic native tools configured for use.

    Args:
        model: ChatAnthropic model instance
        user_id: Optional user ID for memory tool

    Returns:
        List of tool functions ready to use with create_deep_agent
    """
    tools = [
        create_web_fetch_tool(model),
        create_web_search_tool(model),
    ]

    if user_id:
        tools.append(create_memory_tool(user_id))

    return tools


def get_research_tools(model):
    """
    Get tools useful for research tasks (web fetch + web search).

    Args:
        model: ChatAnthropic model instance

    Returns:
        List of research tool functions
    """
    return [
        create_web_fetch_tool(model),
        create_web_search_tool(model),
    ]
