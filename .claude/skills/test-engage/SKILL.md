---
name: test-engage
description: Test the engage workflow end-to-end with VNC browser. Use when testing agent functionality, verifying engage workflow, or debugging agent issues. Triggers on "test engage", "verify engage", "run engage test", "test agent workflow".
allowed-tools: mcp__plugin_playwright_playwright__*, Bash(curl:*)
---

# Test Engage Workflow

This skill runs the complete engage workflow test, verifying that the X growth agent is working correctly with VNC browser automation.

## What This Test Verifies

1. **App Connectivity**: Can we reach app.paralleluniverse.ai?
2. **VNC Browser**: Is the Docker browser visible and running?
3. **X Cookie Injection**: Are X session cookies successfully injected?
4. **Agent Execution**: Does the agent start and complete successfully?
5. **Tool Availability**: Are all 35 Playwright tools loaded without KeyError?
6. **Engagement**: Can the agent like and comment on posts?

## Test Procedure

### Step 1: Navigate to App
```
Navigate to: https://app.paralleluniverse.ai/
```

### Step 2: Setup VNC Browser
1. Click "Show Browser" button to reveal VNC view
2. Verify Docker status shows "Docker Running"
3. Click "Connect X Account to VNC" button
4. Wait for success toast: "Cookies injected to VNC!"

### Step 3: Configure Agent
1. In the PsY Agent iframe, click "New Thread"
2. Select model from LLM dropdown (default: GPT-5.2)
3. Type "engage" in the chat textbox
4. Click Send or press Enter

### Step 4: Monitor Execution
Monitor agent progress by taking periodic snapshots:
- Watch for tool calls: `get_my_posts`, `check_rate_limits`, `like_and_comment`
- Track successful engagements in the output
- Detect when agent completes (textbox changes to "Write your message...")

### Step 5: Verify Results
Check the agent output for:
- "Liked" confirmations
- "Commented" confirmations
- No KeyError exceptions
- No "Could not find tool" errors

## Success Criteria

| Criteria | Expected |
|----------|----------|
| VNC visible | Browser viewport shown |
| Cookies injected | Success toast appears |
| Agent starts | "Running..." appears in textbox |
| Tools loaded | "Loaded 35 Playwright tools" in logs |
| Engagement | At least 1 like OR comment |
| Completion | Agent finishes without crash |

## Common Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `KeyError: 'tool_name'` | Stale Docker cache | Run `./deploy_langgraph_service.sh` with cache bust |
| Rate limit error | Too many X actions | Wait 15 minutes, reduce engagement velocity |
| Anthropic credit error | API credits exhausted | Add credits at console.anthropic.com |
| VNC not connecting | Docker not running | Start Docker with `docker compose up -d` |
| Cookie injection fails | X session expired | Re-authenticate X account in main app |

## Key Files

| File | Purpose |
|------|---------|
| `x_growth_deep_agent.py` | Main agent orchestrator |
| `async_playwright_tools.py` | 35 browser automation tools |
| `deploy_langgraph_service.sh` | Deployment script |
| `langgraph.json` | Agent configuration |

## After Running This Test

If the test passes:
- Agent is ready for production use
- All tools are available
- VNC integration is working

If the test fails:
1. Check Cloud Run logs: `/logs langgraph`
2. Verify tool count in startup logs
3. Redeploy if necessary: `./deploy_langgraph_service.sh`
