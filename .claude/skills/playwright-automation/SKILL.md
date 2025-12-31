---
name: playwright-automation
description: Create browser automation tools using Playwright. Use when adding new X/Twitter interactions, scraping capabilities, or browser-based automation. Triggers on "automate X", "browser action", "scrape", "click element", "playwright".
allowed-tools: Read, Edit, Grep, Glob
---

# Playwright Automation Guide

## Main Files

| File | Purpose |
|------|---------|
| `async_playwright_tools.py` | 36+ browser automation tools (105K) |
| `stealth_cua_server.py` | Anti-detection browser server |
| `async_extension_tools.py` | Chrome extension integration |

## Tool Architecture

Tools communicate with browser via JSON-RPC:

```python
async def your_tool(
    client: JsonRpcClient,
    param: str
) -> str:
    """
    Tool description for the agent.

    Args:
        client: JSON-RPC client for browser communication
        param: Description of parameter

    Returns:
        Result description
    """
    js_code = '''
        // JavaScript executed in browser context
        return document.title;
    '''
    result = await client.send_command("evaluate", {"expression": js_code})
    return result
```

## Common Browser Commands

### Navigate
```python
await client.send_command("navigate", {"url": "https://x.com"})
```

### Click Element
```python
await client.send_command("click", {"selector": "button[data-testid='tweet']"})
```

### Type Text
```python
await client.send_command("type", {
    "selector": "div[data-testid='tweetTextarea_0']",
    "text": "Hello world"
})
```

### Evaluate JavaScript
```python
result = await client.send_command("evaluate", {
    "expression": "document.querySelectorAll('article').length"
})
```

### Wait for Element
```python
await client.send_command("waitForSelector", {
    "selector": "div[data-testid='tweet']",
    "timeout": 10000
})
```

### Screenshot
```python
screenshot = await client.send_command("screenshot", {})
# Returns base64 encoded image
```

## Creating a New Tool

### Step 1: Define the Tool Function

```python
async def search_posts_by_topic(
    client: JsonRpcClient,
    topic: str,
    max_results: int = 10
) -> str:
    """
    Search for posts about a specific topic on X.

    Args:
        client: Browser client
        topic: Topic to search for
        max_results: Maximum number of posts to return

    Returns:
        JSON string with post data
    """
    # Navigate to search
    await client.send_command("navigate", {
        "url": f"https://x.com/search?q={topic}&src=typed_query&f=live"
    })

    # Wait for results
    await asyncio.sleep(2)

    # Extract posts
    js_code = f'''
        const posts = [];
        const articles = document.querySelectorAll('article');

        for (let i = 0; i < Math.min(articles.length, {max_results}); i++) {{
            const article = articles[i];
            const text = article.querySelector('[data-testid="tweetText"]')?.innerText || '';
            const author = article.querySelector('[data-testid="User-Name"]')?.innerText || '';
            const link = article.querySelector('a[href*="/status/"]')?.href || '';

            posts.push({{ text, author, link }});
        }}

        return JSON.stringify(posts);
    '''

    result = await client.send_command("evaluate", {"expression": js_code})
    return result
```

### Step 2: Register as Agent Tool

Add to the tool list in `x_growth_deep_agent.py`:

```python
tools = [
    # ... existing tools
    search_posts_by_topic,
]
```

## X.com Selectors Reference

| Element | Selector |
|---------|----------|
| Tweet text | `[data-testid="tweetText"]` |
| Tweet button | `[data-testid="tweetButtonInline"]` |
| Reply button | `[data-testid="reply"]` |
| Like button | `[data-testid="like"]` |
| Retweet button | `[data-testid="retweet"]` |
| User name | `[data-testid="User-Name"]` |
| Tweet input | `[data-testid="tweetTextarea_0"]` |
| Article/Post | `article[data-testid="tweet"]` |

## Anti-Detection Best Practices

1. **Use stealth mode** from `stealth_cua_server.py`
2. **Add human-like delays**:
   ```python
   await asyncio.sleep(random.uniform(1.0, 3.0))
   ```
3. **Randomize patterns** - don't always do same sequence
4. **Respect rate limits** - X has aggressive bot detection
5. **Use realistic user agents**

## Error Handling

```python
async def safe_action(client: JsonRpcClient, action: str) -> str:
    try:
        result = await client.send_command("evaluate", {"expression": action})
        return result
    except asyncio.TimeoutError:
        return "Action timed out"
    except Exception as e:
        logger.error(f"Browser action failed: {e}")
        return f"Error: {str(e)}"
```

## DOM Extraction Pattern

```python
async def extract_page_data(client: JsonRpcClient) -> dict:
    """Extract structured data from current page."""
    js_code = '''
        return JSON.stringify({
            title: document.title,
            url: window.location.href,
            posts: Array.from(document.querySelectorAll('article')).map(a => ({
                text: a.querySelector('[data-testid="tweetText"]')?.innerText,
                likes: a.querySelector('[data-testid="like"]')?.innerText
            }))
        });
    '''
    result = await client.send_command("evaluate", {"expression": js_code})
    return json.loads(result)
```

## Best Practices

1. **Always wait** for elements before interacting
2. **Use specific selectors** - data-testid is most reliable
3. **Handle failures gracefully** - X DOM changes frequently
4. **Log actions** for debugging and activity feed
5. **Check element exists** before clicking
6. **Add delays** to appear human-like
