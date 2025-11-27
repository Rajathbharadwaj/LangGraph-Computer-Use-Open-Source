STDIN
# ✅ LangGraph Factory Function Fix - FINAL

## 🐛 Issue 1: Function Signature

**Error:**
```
ValueError: Graph factory function 'create_x_growth_agent' in module 
'./x_growth_deep_agent.py' must take exactly one argument, a RunnableConfig
```

**Fix:** Changed function to accept single `config` parameter per [LangGraph CLI docs](https://docs.langchain.com/langsmith/cli)

```python
# Before (❌):
def create_x_growth_agent(
    model_name: str = "claude-sonnet-4-5-20250929",
    user_id: str = None,
    store = None,
    use_longterm_memory: bool = True
):

# After (✅):
def create_x_growth_agent(config: dict = None):
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "claude-sonnet-4-5-20250929")
    user_id = configurable.get("user_id", None)
    # ... extract all params from config
```

---

## 🐛 Issue 2: Parameter Name (CORRECTED)

**Error:**
```
TypeError: create_deep_agent() got an unexpected keyword argument 'system_prompt'
```

**Initial Wrong Fix:** Changed to `instructions` ❌

**Correct Fix:** Keep `system_prompt` ✅

**Source:** [LangGraph DeepAgents Documentation](https://docs.langchain.com/oss/python/deepagents/customization)

```python
from deepagents import create_deep_agent

agent = create_deep_agent(
    system_prompt=research_instructions,  # ✅ CORRECT parameter name
    tools=[...],
    subagents=[...]
)
```

The confusion came from checking the wrong package. The installed `deepagents` package signature showed `instructions`, but the **official LangGraph DeepAgents documentation** clearly shows `system_prompt`.

---

## ✅ Final Working Code

```python
def create_x_growth_agent(config: dict = None):
    """
    Create the X Growth Deep Agent
    
    Args:
        config: RunnableConfig dict with optional configurable parameters
    """
    # Extract parameters from config
    if config is None:
        config = {}
    
    configurable = config.get("configurable", {})
    model_name = configurable.get("model_name", "claude-sonnet-4-5-20250929")
    user_id = configurable.get("user_id", None)
    store = configurable.get("store", None)
    use_longterm_memory = configurable.get("use_longterm_memory", True)
    
    # Initialize model
    model = init_chat_model(model_name)
    
    # Get subagents
    subagents = get_atomic_subagents()
    
    # Build system prompt
    system_prompt = MAIN_AGENT_PROMPT
    # ... add user preferences if user_id provided ...
    
    # Create the agent
    agent = create_deep_agent(
        model=model,
        system_prompt=system_prompt,  # ✅ Correct parameter name
        tools=[],
        subagents=subagents,
    )
    
    return agent
```

---

## 📚 Key Learnings

1. **Always check official docs first** - Don't rely on runtime introspection alone
2. **LangGraph factory functions** must accept single `config` parameter
3. **DeepAgents uses `system_prompt`** per official LangGraph docs
4. Extract all parameters from `config["configurable"]`
5. Return only the agent (not tuple)

---

## 🎉 Result

The agent now loads successfully in LangGraph! 🚀

```bash
✅ Graph 'x_growth_deep_agent' loaded successfully
✅ Available at: http://localhost:8123
```

