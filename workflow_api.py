"""
Workflow API - FastAPI endpoints for workflow execution

Provides REST API and WebSocket streaming for visual workflow execution
"""

import json
import asyncio
from typing import Dict, List, Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
import uuid

from workflow_parser import parse_workflow, load_workflow, list_available_workflows
from x_growth_deep_agent import create_x_growth_agent


app = FastAPI(title="Workflow Execution API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Data Models
# ============================================================================

class WorkflowExecuteRequest(BaseModel):
    workflow_json: Dict[str, Any]
    user_id: Optional[str] = None
    config_overrides: Optional[Dict[str, Any]] = None


class WorkflowExecuteResponse(BaseModel):
    execution_id: str
    status: str
    workflow_id: str
    workflow_name: str
    started_at: str
    completed_at: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class WorkflowListResponse(BaseModel):
    workflows: List[Dict[str, Any]]
    total_count: int


# ============================================================================
# In-Memory Execution Tracking (In production, use PostgreSQL)
# ============================================================================

workflow_executions: Dict[str, Dict[str, Any]] = {}


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Health check"""
    return {
        "status": "healthy",
        "service": "Workflow Execution API",
        "version": "1.0.0"
    }


@app.get("/api/workflows", response_model=WorkflowListResponse)
async def list_workflows():
    """List all available workflow templates"""
    try:
        workflows = list_available_workflows()
        return WorkflowListResponse(
            workflows=workflows,
            total_count=len(workflows)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get a specific workflow template"""
    try:
        workflows = list_available_workflows()
        workflow = next((w for w in workflows if w["id"] == workflow_id), None)

        if not workflow:
            raise HTTPException(status_code=404, detail=f"Workflow {workflow_id} not found")

        # Load full workflow JSON
        workflow_json = load_workflow(workflow["file_path"])
        return workflow_json

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/workflow/execute", response_model=WorkflowExecuteResponse)
async def execute_workflow(request: WorkflowExecuteRequest):
    """
    Execute a workflow (non-streaming)

    Takes workflow JSON, converts to agent instructions, and executes.
    Returns result when complete.
    """
    execution_id = str(uuid.uuid4())
    workflow_json = request.workflow_json
    workflow_id = workflow_json.get("workflow_id", "unknown")
    workflow_name = workflow_json.get("name", "Unnamed Workflow")

    try:
        # Track execution
        workflow_executions[execution_id] = {
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
            "completed_at": None,
            "result": None,
            "error": None
        }

        # Parse workflow JSON → Agent instructions
        prompt = parse_workflow(workflow_json)

        print(f"🚀 Executing workflow: {workflow_name}")
        print(f"📋 Prompt:\n{prompt}\n")

        # Create and execute agent
        agent = create_x_growth_agent(config={
            "configurable": {
                "user_id": request.user_id,
                "use_longterm_memory": True if request.user_id else False
            }
        })

        # Execute workflow
        result = await agent.ainvoke({
            "messages": [{"role": "user", "content": prompt}]
        })

        # Update execution record
        workflow_executions[execution_id].update({
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "result": result
        })

        return WorkflowExecuteResponse(**workflow_executions[execution_id])

    except Exception as e:
        # Update execution record with error
        workflow_executions[execution_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e)
        })

        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/execution/{execution_id}")
async def get_execution_status(execution_id: str):
    """Get status of a workflow execution"""
    if execution_id not in workflow_executions:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return workflow_executions[execution_id]


@app.websocket("/api/workflow/execute/stream")
async def execute_workflow_stream(websocket: WebSocket):
    """
    Execute workflow with real-time streaming updates

    Client sends workflow JSON, server streams execution progress
    """
    await websocket.accept()

    try:
        # Receive workflow JSON from client
        data = await websocket.receive_json()
        workflow_json = data.get("workflow_json")
        user_id = data.get("user_id")

        if not workflow_json:
            await websocket.send_json({
                "type": "error",
                "error": "No workflow_json provided"
            })
            await websocket.close()
            return

        execution_id = str(uuid.uuid4())
        workflow_id = workflow_json.get("workflow_id", "unknown")
        workflow_name = workflow_json.get("name", "Unnamed Workflow")

        # Send started message
        await websocket.send_json({
            "type": "started",
            "execution_id": execution_id,
            "workflow_id": workflow_id,
            "workflow_name": workflow_name,
            "started_at": datetime.utcnow().isoformat()
        })

        # Parse workflow
        prompt = parse_workflow(workflow_json)

        await websocket.send_json({
            "type": "parsing_complete",
            "prompt": prompt
        })

        # Create agent
        agent = create_x_growth_agent(config={
            "configurable": {
                "user_id": user_id,
                "use_longterm_memory": True if user_id else False
            }
        })

        # Stream execution
        async for chunk in agent.astream({
            "messages": [{"role": "user", "content": prompt}]
        }):
            # Send each chunk to client
            await websocket.send_json({
                "type": "chunk",
                "data": str(chunk)  # Convert to string for JSON serialization
            })

        # Send completion message
        await websocket.send_json({
            "type": "completed",
            "execution_id": execution_id,
            "completed_at": datetime.utcnow().isoformat()
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })
        await websocket.close()


# ============================================================================
# Run Server
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    print("=" * 60)
    print("🚀 Workflow Execution API")
    print("=" * 60)
    print("\nStarting server on http://localhost:8006")
    print("\nEndpoints:")
    print("  GET    /api/workflows           - List workflows")
    print("  GET    /api/workflows/{id}      - Get workflow")
    print("  POST   /api/workflow/execute    - Execute workflow")
    print("  GET    /api/workflow/execution/{id} - Get execution status")
    print("  WS     /api/workflow/execute/stream - Stream execution")
    print("\n" + "=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8006)
