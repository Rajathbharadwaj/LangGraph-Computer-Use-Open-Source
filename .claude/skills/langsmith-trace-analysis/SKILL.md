---
name: langsmith-trace-analysis
description: Analyze LangSmith traces and thread runs using the Python SDK. Use when debugging agent issues, analyzing tool calls, or understanding what happened in a session. Triggers on "analyze trace", "langsmith", "debug thread", "what happened in session".
allowed-tools: Bash(python*), Read
---

# LangSmith Trace Analysis

This skill documents how to use the LangSmith Python SDK to analyze agent thread runs, tool calls, and debug issues.

## Prerequisites

```bash
pip install langsmith
export LANGCHAIN_API_KEY="lsv2_pt_..."
```

## Step 1: List Available Projects

```python
from langsmith import Client

client = Client()

for project in client.list_projects(limit=20):
    print(f"  - {project.name} (id: {project.id})")
```

## Step 2: Get Runs for a Thread

When you have a LangSmith URL like:
```
https://smith.langchain.com/o/{org_id}/projects/p/{project_id}?searchModel=...thread_id...
```

Extract the `project_id` and `thread_id`, then:

```python
from langsmith import Client

client = Client()

thread_id = "69dd568c-7c30-42f8-8fe0-e0a3a3669a4d"
project_id = "9d7247aa-c2c5-43c3-90e6-444cea749b0b"

# Get all runs (limit 100 max per request)
all_runs = list(client.list_runs(
    project_id=project_id,
    limit=100
))

# Filter by thread_id in metadata
runs = [r for r in all_runs
        if r.extra and r.extra.get("metadata", {}).get("thread_id") == thread_id]

print(f"Found {len(runs)} runs for thread {thread_id}")
```

## Step 3: Analyze Tool Calls

```python
for run in sorted(runs, key=lambda x: x.start_time):
    if run.run_type == "tool":
        status = "OK" if run.status == "success" else "ERR"
        duration = (run.end_time - run.start_time).total_seconds()

        print(f"{status} {run.name} ({duration:.1f}s)")

        # Show input
        if run.inputs and 'input' in run.inputs:
            print(f"   INPUT: {run.inputs['input'][:100]}...")

        # Show output
        if run.outputs and 'output' in run.outputs:
            out = run.outputs['output']
            if isinstance(out, dict) and 'content' in out:
                print(f"   OUTPUT: {out['content'][:100]}...")

        # Show errors
        if run.error:
            print(f"   ERROR: {run.error[:150]}")
```

## Step 4: Build Execution Tree

```python
# Build parent-child relationships
run_by_id = {str(r.id): r for r in runs}
children = {}
for r in runs:
    parent_id = str(r.parent_run_id) if r.parent_run_id else None
    if parent_id:
        if parent_id not in children:
            children[parent_id] = []
        children[parent_id].append(r)

def print_tree(run, indent=0):
    status = "OK" if run.status == "success" else "ERR"
    duration = (run.end_time - run.start_time).total_seconds()
    prefix = "  " * indent
    print(f"{prefix}{status} {run.name} ({run.run_type}, {duration:.1f}s)")

    run_id = str(run.id)
    if run_id in children:
        for child in sorted(children[run_id], key=lambda x: x.start_time):
            print_tree(child, indent + 1)

# Find root runs
roots = [r for r in runs if not r.parent_run_id or str(r.parent_run_id) not in run_by_id]
for root in sorted(roots, key=lambda x: x.start_time)[:5]:
    print_tree(root)
```

## Step 5: Get Detailed Subagent Info

```python
# Read a specific run by ID
subagent_id = "95b50393-32fd-43df-afff-7f16c1649907"
run = client.read_run(subagent_id)

print(f"Name: {run.name} | Status: {run.status}")

# Get all messages from outputs
if run.outputs and 'messages' in run.outputs:
    for msg in run.outputs['messages']:
        msg_type = msg.get('type', 'unknown')
        content = msg.get('content', '')

        if isinstance(content, list):
            for item in content:
                if item.get('type') == 'tool_use':
                    print(f"TOOL_CALL: {item.get('name')}")
                elif item.get('type') == 'text':
                    print(f"TEXT: {item.get('text')[:200]}")
```

## Step 6: Find Specific Tool Calls

```python
# Get trace_id from any run
trace_id = runs[0].trace_id

# Get all runs in trace
trace_runs = list(client.list_runs(trace_id=trace_id, limit=100))

# Find engagement tools
engagement_tools = ['like_post', 'comment_on_post', 'generate_styled_comment']
for run in trace_runs:
    if run.run_type == "tool" and run.name in engagement_tools:
        print(f"{run.name}: {run.status}")
```

## Common Patterns

### Debug Time Limit Issues
Look for runs where output contains "SESSION TIME LIMIT REACHED":
```python
for run in runs:
    if run.outputs and 'output' in run.outputs:
        out = run.outputs['output']
        if isinstance(out, dict) and 'content' in out:
            if 'TIME LIMIT' in str(out['content']):
                print(f"Time limit hit in: {run.name}")
```

### Count Tool Types
```python
from collections import Counter
tool_counts = Counter(r.name for r in runs if r.run_type == "tool")
for name, count in tool_counts.most_common():
    print(f"  {name}: {count}x")
```

## Full Analysis Script

```python
import os
os.environ['LANGCHAIN_API_KEY'] = 'lsv2_pt_...'

from langsmith import Client
client = Client()

thread_id = "YOUR_THREAD_ID"
project_id = "YOUR_PROJECT_ID"

# Get runs
all_runs = list(client.list_runs(project_id=project_id, limit=100))
runs = [r for r in all_runs if r.extra and r.extra.get("metadata", {}).get("thread_id") == thread_id]

print(f"Thread: {thread_id}")
print(f"Total runs: {len(runs)}")
print(f"Trace ID: {runs[0].trace_id if runs else 'N/A'}")
print()

# Summarize
for run in sorted(runs, key=lambda x: x.start_time):
    if run.run_type == "tool":
        status = "OK" if run.status == "success" else "ERR"
        duration = (run.end_time - run.start_time).total_seconds()
        print(f"{status} {run.name} ({duration:.1f}s)")
        if run.error:
            print(f"   ERROR: {run.error[:100]}")
```
