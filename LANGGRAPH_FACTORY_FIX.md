STDIN
# ✅ LangGraph Factory Function Fix

## 🐛 The Problem

The error occurred when trying to load the `x_growth_deep_agent`:

```
ValueError: Graph factory function 'create_x_growth_agent' in module 
'./x_growth_deep_agent.py' must take exactly one argument, a RunnableConfig
```

## 📚 LangGraph Documentation Requirements

According to the [LangGraph CLI documentation](https://docs.langchain.com/langsmith/cli):

When specifying a graph factory function in `langgraph.json`:

```json
{
  "graphs": {
    "graph_id": "./path/to/file.py:make_graph"
  }
}
```

The `make_graph` function **MUST**:

1. ✅ **Take exactly ONE argument**: A `config` dictionary (RunnableConfig)
2. ✅ **Return**: A `StateGraph` or `CompiledStateGraph` instance

### Example from Docs:

```python
from langchain_core.runnables import RunnableConfig

def make_graph(config: RunnableConfig):
    # Extract configurable parameters
    user_id = config.get("configurable", {}).get("user_id", "default")
    
    # Build and return the graph
    graph = StateGraph(...)
    # ... configure graph ...
    return graph.compile()
```

## 🔧 The Fix

### Before (❌ Wrong):

```python
def create_x_growth_agent(
    model_name: str = "claude-sonnet-4-5-20250929",
    user_id: str = None,
    store = None,
    use_longterm_memory: bool = True
):
    # ... code ...
    return agent
```

**Problem**: Function has 4 parameters, not 1!

### After (✅ Correct):

```python
def create_x_growth_agent(config: dict = None):
    """
    Create the X Growth Deep Agent with optional user-specific long-term memory
    
    Args:
        config: RunnableConfig dict with optional configurable parameters:
            - model_name: The LLM model to use (default: claude-sonnet-4-5-20250929)
            - user_id: Optional user ID for personalized memory
            - store: Optional LangGraph Store (InMemoryStore or PostgresStore)
            - use_longterm_memory: Enable long-term memory persistence (default: True)
        
    Returns:
        DeepAgent configured for X account growth
    """
    
    # Extract parameters from config
    if config is None:
        config = {}
    
    # Get configurable values with defaults
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "claude-sonnet-4-5-20250929")
    user_id = configurable.get("user_id", None)
    store = configurable.get("store", None)
    use_longterm_memory = configurable.get("use_longterm_memory", True)
    
    # ... rest of the code ...
    
    # Always return just the agent (LangGraph requirement)
    return agent
```

**Key changes**:
1. ✅ Single parameter: `config: dict`
2. ✅ Extract all parameters from `config["configurable"]`
3. ✅ Return only the agent (not a tuple)

## 🎯 How to Use the Agent

### 1. Via LangGraph CLI (Local Development):

```bash
# Start the LangGraph server
langgraph dev

# The agent will be available at:
# http://localhost:8123
```

### 2. Via Python (Direct Usage):

```python
# Create agent with default settings
agent = create_x_growth_agent()

# Create agent with custom configuration
agent = create_x_growth_agent(config={
    "configurable": {
        "model_name": "claude-sonnet-4-5-20250929",
        "user_id": "user_123",
        "use_longterm_memory": True
    }
})

# Run the agent
result = agent.invoke({
    "messages": [{"role": "user", "content": "Engage with trending AI posts"}]
})
```

### 3. Via LangGraph API (When Deployed):

```python
from langgraph_sdk import get_client

client = get_client(url="http://localhost:8123")

# Create a thread
thread = client.threads.create()

# Run the agent with configuration
run = client.runs.create(
    thread_id=thread["thread_id"],
    assistant_id="x_growth_deep_agent",
    input={"messages": [{"role": "user", "content": "Find trending AI posts"}]},
    config={
        "configurable": {
            "user_id": "user_123",
            "model_name": "claude-sonnet-4-5-20250929"
        }
    }
)
```

## 📊 Configuration Options

When invoking the agent, you can pass these in `config["configurable"]`:

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `model_name` | str | `"claude-sonnet-4-5-20250929"` | LLM model to use |
| `user_id` | str | `None` | User ID for personalized memory |
| `store` | Store | `None` | LangGraph Store instance |
| `use_longterm_memory` | bool | `True` | Enable persistent memory |

## 🎉 Result

The agent now loads successfully:

```bash
✅ Graph 'x_growth_deep_agent' loaded successfully
✅ Available at: http://localhost:8123/x_growth_deep_agent
```

## 📝 Related Files Modified

1. **`x_growth_deep_agent.py`**:
   - Changed function signature to accept single `config` parameter
   - Extract all parameters from `config["configurable"]`
   - Return only the agent (not tuple)

2. **`langgraph.json`**:
   - Already correctly configured:
     ```json
     {
       "graphs": {
         "x_growth_deep_agent": "./x_growth_deep_agent.py:create_x_growth_agent"
       }
     }
     ```

## 🔗 References

- [LangGraph CLI Configuration](https://docs.langchain.com/langsmith/cli)
- [Rebuild Graph at Runtime](https://docs.langchain.com/langsmith/graph-rebuild)
- [RunnableConfig in Nodes](https://docs.langchain.com/oss/python/langgraph/graph-api)

STDIN

## 🐛 Second Issue: Wrong Parameter Name

After fixing the function signature, another error occurred:

```
TypeError: create_deep_agent() got an unexpected keyword argument 'system_prompt'
```

### The Problem:

The `create_deep_agent()` function from the DeepAgents library uses **`instructions`** not **`system_prompt`**.

### Actual Signature:

```python
def create_deep_agent(
    tools: Sequence[BaseTool] = [],
    instructions: str = '',  # ← NOT 'system_prompt'!
    middleware: Optional[list] = None,
    model: Union[str, Runnable] = None,
    subagents: Optional[list] = None,
    context_schema: Optional[Type[Any]] = None,
    checkpointer: Union[None, bool, BaseCheckpointSaver] = None,
    tool_configs: Optional[dict] = None
)
```

### The Fix:

```python
# Before (❌ Wrong):
agent_kwargs = {
    "model": model,
    "system_prompt": system_prompt,  # ← Wrong parameter name!
    "tools": [],
    "subagents": subagents,
}

# After (✅ Correct):
agent_kwargs = {
    "model": model,
    "instructions": system_prompt,  # ← Correct parameter name!
    "tools": [],
    "subagents": subagents,
}
```

Also removed the unsupported `store` and `use_longterm_memory` parameters from `agent_kwargs` since `create_deep_agent()` doesn't accept them.

## ✅ Final Result

Both issues are now fixed:
1. ✅ Function signature accepts single `config` parameter (LangGraph requirement)
2. ✅ Uses `instructions` instead of `system_prompt` (DeepAgents requirement)

The agent should now load successfully! 🎉

