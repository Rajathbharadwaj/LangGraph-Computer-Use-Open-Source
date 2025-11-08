"""
User Container Server
Runs inside each user's dedicated container
Handles automation for a single user
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging
import os
from datetime import datetime

# Import your existing automation code
from x_growth_deep_agent import XGrowthDeepAgent
from x_growth_workflows import run_engagement_workflow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Get user ID from environment
USER_ID = os.getenv("USER_ID", "unknown")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

app = FastAPI(title=f"User Container - {USER_ID[:8]}")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# State
automation_running = False
agent: Optional[XGrowthDeepAgent] = None
websocket_connections = set()


# ============================================================================
# Models
# ============================================================================

class AutomationStartRequest(BaseModel):
    workflow: str = "engagement"
    config: Optional[Dict[str, Any]] = None


# ============================================================================
# WebSocket Management
# ============================================================================

async def broadcast_message(message: Dict[str, Any]):
    """Broadcast message to all connected clients"""
    dead_connections = set()

    for ws in websocket_connections:
        try:
            await ws.send_json(message)
        except:
            dead_connections.add(ws)

    # Clean up dead connections
    websocket_connections.difference_update(dead_connections)


# ============================================================================
# Automation Logic
# ============================================================================

async def run_automation_loop(workflow: str, config: Dict[str, Any]):
    """Run automation loop"""
    global automation_running, agent

    try:
        logger.info(f"🚀 Starting {workflow} workflow for user {USER_ID[:8]}")
        await broadcast_message({
            "type": "status",
            "status": "starting",
            "workflow": workflow
        })

        # Initialize agent
        agent = XGrowthDeepAgent(
            user_id=USER_ID,
            anthropic_api_key=ANTHROPIC_API_KEY
        )

        automation_running = True

        await broadcast_message({
            "type": "status",
            "status": "running",
            "workflow": workflow
        })

        # Run workflow
        while automation_running:
            try:
                # Execute workflow step
                result = await run_engagement_workflow(
                    agent=agent,
                    config=config
                )

                # Broadcast action
                await broadcast_message({
                    "type": "action",
                    "action": result.get("action"),
                    "target": result.get("target"),
                    "success": result.get("success", True),
                    "timestamp": datetime.utcnow().isoformat()
                })

                # Wait before next action (rate limiting)
                await asyncio.sleep(config.get("delay", 60))

            except Exception as e:
                logger.error(f"Automation error: {e}")
                await broadcast_message({
                    "type": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                })

                # Continue or stop based on error
                if "rate limit" in str(e).lower():
                    await asyncio.sleep(300)  # 5 min backoff
                else:
                    break

        logger.info(f"🛑 Automation stopped for user {USER_ID[:8]}")

    except Exception as e:
        logger.error(f"Fatal automation error: {e}")
        await broadcast_message({
            "type": "error",
            "error": f"Fatal error: {str(e)}",
            "timestamp": datetime.utcnow().isoformat()
        })

    finally:
        automation_running = False
        await broadcast_message({
            "type": "status",
            "status": "stopped",
            "timestamp": datetime.utcnow().isoformat()
        })


# ============================================================================
# API Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Container info"""
    return {
        "container": "User Automation Container",
        "user_id": USER_ID,
        "status": "running" if automation_running else "idle",
        "timestamp": datetime.utcnow().isoformat()
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "user_id": USER_ID,
        "automation_running": automation_running
    }


@app.post("/api/automation/start")
async def start_automation(request: AutomationStartRequest):
    """Start automation"""
    global automation_running

    if automation_running:
        return {
            "success": False,
            "error": "Automation already running"
        }

    # Start automation in background
    asyncio.create_task(run_automation_loop(
        workflow=request.workflow,
        config=request.config or {}
    ))

    return {
        "success": True,
        "message": "Automation started",
        "workflow": request.workflow
    }


@app.post("/api/automation/stop")
async def stop_automation():
    """Stop automation"""
    global automation_running

    if not automation_running:
        return {
            "success": False,
            "error": "Automation not running"
        }

    automation_running = False

    return {
        "success": True,
        "message": "Automation stopped"
    }


@app.get("/api/automation/status")
async def get_status():
    """Get automation status"""
    return {
        "user_id": USER_ID,
        "running": automation_running,
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# WebSocket
# ============================================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await websocket.accept()
    websocket_connections.add(websocket)

    logger.info(f"WebSocket connected for user {USER_ID[:8]}")

    # Send current status
    await websocket.send_json({
        "type": "status",
        "status": "running" if automation_running else "idle",
        "user_id": USER_ID
    })

    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()

            # Handle incoming messages
            # (e.g., commands from frontend)

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {USER_ID[:8]}")
    finally:
        websocket_connections.discard(websocket)


if __name__ == "__main__":
    import uvicorn

    logger.info(f"🚀 Starting container server for user {USER_ID[:8]}")
    logger.info(f"   Port: 8000")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
