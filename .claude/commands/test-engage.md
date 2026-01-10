---
description: Test the engage workflow end-to-end with VNC browser
argument-hint: [model] | GPT-5.2 | claude-sonnet
allowed-tools: mcp__plugin_playwright_playwright__*, Bash(curl:*)
---

# Test Engage Workflow

This command tests the full engage workflow:
1. Navigate to app.paralleluniverse.ai
2. Show the VNC browser
3. Connect X account to VNC
4. Start a new thread with the specified model
5. Send "engage" command
6. Monitor until the agent completes

## Model Selection

**Model:** `$ARGUMENTS` (default: GPT-5.2)

## Step-by-Step Process

### 1. Navigate to the App
Use `mcp__plugin_playwright_playwright__browser_navigate` to go to:
```
https://app.paralleluniverse.ai/
```

### 2. Take Initial Snapshot
Use `mcp__plugin_playwright_playwright__browser_snapshot` to capture the current page state.

### 3. Show VNC Browser
Look for the "Show Browser" button and click it using `mcp__plugin_playwright_playwright__browser_click`.

### 4. Connect X Account to VNC
Click the "Connect X Account to VNC" button. This injects X session cookies into the VNC browser.

Verify the success message: "Cookies injected to VNC!"

### 5. Start New Thread
In the PsY Agent iframe:
- Click "New Thread" button
- Select the model from the LLM dropdown (GPT-5.2 by default)

### 6. Send Engage Command
Type "engage" into the chat textbox and submit.

### 7. Monitor Agent Progress
Repeatedly take snapshots every 10-15 seconds until the agent completes:
- Watch for the textbox to change from "Running..." to "Write your message..."
- Log tool calls observed: `get_my_posts`, `check_rate_limits`, `like_and_comment`, etc.
- Track successful engagements (likes + comments)

### 8. Report Results
When the agent finishes, summarize:
- Total engagements attempted
- Successful likes/comments
- Any errors encountered
- Rate limit status

## Success Criteria

The test passes when:
- VNC browser is visible and connected
- X cookies are injected successfully
- Agent runs and completes at least one engagement
- No KeyError or tool-not-found errors

## Common Issues

| Issue | Solution |
|-------|----------|
| KeyError for tools | Redeploy with `./deploy_langgraph_service.sh` |
| Rate limited | Wait 5-15 minutes, try again |
| VNC not connecting | Check Docker is running on localhost:8005 |
| Anthropic credit error | Add credits to Anthropic account |

## Usage

```
/test-engage           # Use default GPT-5.2 model
/test-engage claude    # Use Claude Sonnet model
```
