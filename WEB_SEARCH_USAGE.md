# Web Search in Deep Agent

## Overview

The X Growth Deep Agent now has **web search capability** powered by Tavily. This allows the agent to research topics, gather current information, and create more informed content.

## Setup

### 1. Get Tavily API Key

Sign up at https://tavily.com to get your free API key.

### 2. Set Environment Variable

Add to your `.env` file:
```bash
TAVILY_API_KEY=your_key_here
```

Or export it:
```bash
export TAVILY_API_KEY=your_key_here
```

### 3. Restart LangGraph Container

```bash
docker-compose -f docker-compose.langgraph.yml restart langgraph-api
```

## How It Works

The agent now has a new subagent called `research_topic` that can search the web using Tavily.

### Subagent: `research_topic`

**Description**: Research a topic using web search to get current information, trends, and facts

**Capabilities**:
- Search the web for current information
- Return up to 5 relevant results with full content
- Synthesize findings into a concise summary
- Provide sources with URLs

**When to use**:
- Before creating posts about trending topics
- To gather facts for commenting
- To understand context for technical discussions
- To find current information on breaking news

## Usage Examples

### Example 1: Research Before Posting

```python
# User: "Create a post about the latest Claude AI model"

# Agent workflow:
1. task("research_topic", "Research latest Claude AI model features and capabilities")
2. [Agent receives: "Claude Sonnet 4.5 released Dec 2024, features..."]
3. task("create_post", "Just tried Claude Sonnet 4.5's new computer use API - the multimodal capabilities are incredible! 🤖")
```

### Example 2: Research Before Commenting

```python
# User: "Comment on posts about LangGraph"

# Agent workflow:
1. analyze_page() - sees post about LangGraph v1.0
2. task("research_topic", "Research LangGraph v1.0 new features")
3. [Agent receives: "LangGraph v1.0 adds..., improves..."]
4. task("comment_on_post", "The new streaming in LangGraph v1.0 is game-changing for real-time agents. Have you tried the checkpointing feature yet?")
```

### Example 3: Fact-Check Before Engaging

```python
# User: "Engage with AI news posts"

# Agent workflow:
1. analyze_page() - sees post claiming "GPT-5 released"
2. task("research_topic", "Research GPT-5 release date latest news")
3. [Agent receives: "No official GPT-5 announcement as of..."]
4. [Agent decides NOT to engage with misinformation]
```

## Search Tool Details

**Tool Name**: `tavily_search_results_json`

**Parameters**:
- `query` (str): The search query
- `max_results` (int): Maximum results to return (default: 5)
- `include_raw_content` (bool): Include full page content (default: True)

**Returns**:
```json
{
  "results": [
    {
      "title": "Page Title",
      "url": "https://...",
      "content": "Relevant excerpt...",
      "raw_content": "Full page content if include_raw_content=True",
      "score": 0.95
    }
  ]
}
```

## Best Practices

### ✅ Good Use Cases

- **Research trending topics** before creating content
- **Gather facts and statistics** to make comments more valuable
- **Verify information** before engaging with controversial topics
- **Understand context** for technical discussions
- **Find sources** to cite in your posts

### ❌ Avoid

- Don't search for every single post you comment on (use judiciously)
- Don't search for basic information the agent already knows
- Don't use for spamming or bulk content generation
- Don't ignore rate limits (free tier: ~1000 searches/month)

## Rate Limits

Tavily free tier:
- 1,000 searches per month
- 5 results per search
- Standard speed

For higher volume, upgrade to paid tier at https://tavily.com/pricing

## Troubleshooting

### Error: "TAVILY_API_KEY not set"

**Solution**: Make sure your `.env` file contains:
```bash
TAVILY_API_KEY=your_key_here
```

Then restart the container:
```bash
docker-compose -f docker-compose.langgraph.yml restart langgraph-api
```

### Error: "No module named 'langchain_community'"

**Solution**: Already installed in the Docker container. If running locally:
```bash
pip install langchain-community
```

### Search Returns Empty Results

**Possible causes**:
1. Query is too vague or broad
2. Topic is very new (less than 1 hour old)
3. API key is invalid or expired

**Solutions**:
- Make queries more specific
- Try different search terms
- Verify API key is correct

## Integration with Workflows

The research subagent integrates seamlessly with existing workflows:

### Engagement Workflow (Enhanced)

```
1. Navigate to home timeline
2. Analyze posts
3. FOR each interesting post:
   - IF topic is complex or trending:
     - research_topic(post topic)
   - THEN comment with informed response
4. Track in action_history.json
```

### Content Posting Workflow (Enhanced)

```
1. User requests: "Post about [topic]"
2. research_topic(topic)
3. Synthesize findings
4. create_post with well-informed content
5. Track in action_history.json
```

## Example Agent Invocation

```python
from x_growth_deep_agent import create_x_growth_agent

# Create agent (automatically includes research subagent)
agent = create_x_growth_agent()

# Use in workflow
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Research the latest AI agent frameworks and create a post about it"
    }]
})

# Agent will:
# 1. task("research_topic", "latest AI agent frameworks 2025")
# 2. Receive search results about LangGraph, CrewAI, AutoGPT, etc.
# 3. task("create_post", "The AI agent ecosystem is evolving fast! LangGraph's new streaming + CrewAI's hierarchical teams are game-changers. What framework are you using? 🤖")
```

## Architecture

```
┌─────────────────────────────────────────┐
│  Main Deep Agent                        │
│  - Plans workflow                       │
│  - Delegates to subagents              │
└──────────────┬──────────────────────────┘
               │
               ├──> navigate subagent
               ├──> analyze_page subagent
               ├──> like_post subagent
               ├──> comment_on_post subagent
               └──> research_topic subagent ⭐ NEW
                    │
                    └──> Tavily Web Search API
                         - Searches web
                         - Returns relevant results
                         - Includes full content
```

## Notes

- Web search is **optional** - agent can still function without it
- Search results are **summarized** by the subagent before returning
- Agent **decides when to search** based on task needs
- All searches are **logged** for monitoring usage
- Free tier is sufficient for **personal/small-scale** use

## Resources

- Tavily Docs: https://docs.tavily.com
- LangChain Tavily Integration: https://python.langchain.com/docs/integrations/tools/tavily_search
- DeepAgents Docs: https://docs.langchain.com/oss/python/deepagents/overview
