# LangChain Integration for Computer Use Agent (CUA)

This directory contains LangChain tools and LangGraph agents that integrate with the Computer Use Agent (CUA) server, allowing you to control computers using natural language through LangChain/LangGraph workflows.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements_langchain.txt
```

### 2. Start CUA Server

Make sure your CUA Docker container is running:

```bash
# If not already running
docker run -d --name cua-container -p 5900:5900 -p 8001:8001 --shm-size=2g cua-ubuntu
```

### 3. Set API Key

```bash
export OPENAI_API_KEY="your-openai-api-key"
# Or use other providers like Anthropic:
# export ANTHROPIC_API_KEY="your-anthropic-api-key"
```

### 4. Run the Agent

```bash
python langgraph_cua_agent.py
```

## 📁 Files Overview

- **`langchain_cua_tools.py`** - LangChain tools that interface with CUA server
- **`langgraph_cua_agent.py`** - LangGraph agent implementation using CUA tools
- **`requirements_langchain.txt`** - Python dependencies
- **`README_LANGCHAIN.md`** - This documentation

## 🛠️ Available Tools

Based on the [LangChain custom tools documentation](https://python.langchain.com/docs/how_to/custom_tools/), we've created the following tools:

### Basic Tools

| Tool | Description | Parameters |
|------|-------------|------------|
| `take_screenshot` | Capture current screen | None |
| `click_at_coordinates` | Click at specific location | `x`, `y`, `button` |
| `type_text` | Type text | `text` |
| `press_keys` | Press key combination | `keys` (list) |
| `move_cursor` | Move mouse cursor | `x`, `y` |
| `scroll_at_location` | Scroll at location | `x`, `y`, `scroll_x`, `scroll_y` |
| `double_click_at_coordinates` | Double-click | `x`, `y` |
| `get_screen_dimensions` | Get screen size | None |

### Advanced Tools

| Tool | Description | Features |
|------|-------------|----------|
| `take_screenshot_with_metadata` | Screenshot with metadata | Returns artifacts |
| `NavigateToURL` | Navigate to URL | Class-based tool |

## 🔧 Usage Examples

### Simple Tool Usage

```python
import asyncio
from langchain_cua_tools import take_screenshot, click_at_coordinates

async def example():
    # Take a screenshot
    screenshot = await take_screenshot.ainvoke({})
    print(f"Screenshot: {len(screenshot)} chars")
    
    # Click somewhere
    result = await click_at_coordinates.ainvoke({"x": 100, "y": 100})
    print(result)

asyncio.run(example())
```

### LangGraph Agent

```python
from langgraph_cua_agent import run_cua_agent_task

# Run a task
await run_cua_agent_task("Take a screenshot and describe what you see")
```

### Interactive Session

```python
from langgraph_cua_agent import run_interactive_session

# Start interactive session
await run_interactive_session()
```

## 🤖 Agent Capabilities

The LangGraph agent can:

- **Visual Understanding**: Take screenshots and analyze screen content
- **Precise Control**: Click, type, and navigate with pixel-perfect accuracy
- **Browser Automation**: Navigate websites, fill forms, interact with web apps
- **Keyboard Shortcuts**: Use system shortcuts (Ctrl+C, Ctrl+V, etc.)
- **Multi-step Tasks**: Chain actions together for complex workflows
- **Error Recovery**: Handle failures and retry actions

## 📋 Example Tasks

### Web Browsing
```python
await run_cua_agent_task("Navigate to google.com and search for 'langchain'")
```

### Application Control
```python
await run_cua_agent_task("Open a new tab and go to github.com")
```

### Data Entry
```python
await run_cua_agent_task("Fill out the form on the current page with test data")
```

### Screenshot Analysis
```python
await run_cua_agent_task("Take a screenshot and describe all the UI elements you see")
```

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   LangGraph     │───▶│  LangChain CUA   │───▶│   CUA Server    │
│     Agent       │    │     Tools        │    │  (FastAPI)      │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                       │                       │
         │              HTTP REST API                    │
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│      LLM        │    │   Tool Schemas   │    │  Docker + VNC   │
│ (GPT-4, etc.)   │    │   & Validation   │    │  (Ubuntu GUI)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🎯 Key Features

### 1. **Type Safety**
All tools use Pydantic models for input validation:

```python
class ClickInput(BaseModel):
    x: int = Field(description="X coordinate to click")
    y: int = Field(description="Y coordinate to click")
    button: str = Field(default="left", description="Mouse button")
```

### 2. **Error Handling**
Comprehensive error handling with descriptive messages:

```python
if result.get("success"):
    return f"Successfully clicked at ({x}, {y})"
else:
    return f"Click failed: {result.get('error', 'Unknown error')}"
```

### 3. **Async Support**
All tools are async-first for better performance:

```python
@tool
async def take_screenshot() -> str:
    """Async screenshot tool"""
    client = await get_cua_client()
    # ... async operations
```

### 4. **Memory & State**
LangGraph agent maintains conversation memory:

```python
memory = MemorySaver()
agent = create_react_agent(llm, tools, checkpointer=memory)
```

### 5. **Tool Artifacts**
Advanced tools can return both content and artifacts:

```python
@tool(response_format="content_and_artifact")
async def take_screenshot_with_metadata() -> Tuple[str, Dict[str, Any]]:
    content = "Screenshot taken successfully"
    artifact = {"image_base64": image_data, "width": w, "height": h}
    return content, artifact
```

## 🔧 Customization

### Adding New Tools

Follow the [LangChain tool patterns](https://python.langchain.com/docs/how_to/custom_tools/):

```python
@tool
async def my_custom_tool(param: str) -> str:
    """Description of what this tool does"""
    # Your implementation
    client = await get_cua_client()
    result = await client._request("POST", "/my_endpoint", {"param": param})
    return f"Result: {result}"
```

### Custom Agent Behavior

Modify the system message in `create_cua_agent()`:

```python
system_message = """You are a specialized agent that focuses on [your use case].
Follow these specific guidelines:
1. Always do X before Y
2. Never do Z without confirming
3. etc.
"""
```

### Different LLM Providers

```python
# Use Anthropic
from langchain_anthropic import ChatAnthropic
llm = ChatAnthropic(model="claude-3-sonnet-20240229")

# Use local models via Ollama
from langchain_ollama import ChatOllama  
llm = ChatOllama(model="llama2")
```

## 🛡️ Safety Considerations

1. **Sandboxing**: Always run CUA in Docker for isolation
2. **VNC Access**: Monitor agent actions via VNC viewer
3. **Rate Limiting**: Add delays between actions if needed
4. **Error Recovery**: Agent can detect and recover from failures
5. **User Oversight**: Use interactive mode for critical tasks

## 🚀 Advanced Usage

### Streaming Responses

```python
async for chunk in agent.astream({"messages": [HumanMessage("Take a screenshot")]}, config):
    print(chunk)
```

### Custom Checkpointers

```python
from langgraph.checkpoint.postgres import PostgresSaver
checkpointer = PostgresSaver.from_conn_string("postgresql://...")
```

### Tool Composition

```python
# Combine CUA tools with other LangChain tools
from langchain_community.tools import DuckDuckGoSearchRun

all_tools = get_all_cua_tools() + [DuckDuckGoSearchRun()]
agent = create_react_agent(llm, all_tools)
```

## 📊 Monitoring & Debugging

### Tool Execution Logs

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Now you'll see detailed tool execution logs
```

### LangSmith Integration

```python
import os
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_API_KEY"] = "your-langsmith-key"
```

## 🤝 Contributing

1. Add new tools in `langchain_cua_tools.py`
2. Update agent prompts in `langgraph_cua_agent.py`
3. Add tests for new functionality
4. Update this README

## 📄 License

Same as the main CUA project.

---

**🎉 You now have a powerful LangChain/LangGraph integration for computer control!**

The agent can understand natural language requests and execute them by controlling the computer through visual feedback, making it perfect for automation, testing, and AI-powered workflows.
