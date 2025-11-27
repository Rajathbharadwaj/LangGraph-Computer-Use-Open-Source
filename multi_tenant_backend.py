"""
Multi-Tenant Backend API
Routes requests to user-specific containers
"""
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, Dict, Any
import asyncio
import logging
import aiohttp
from datetime import datetime

from container_manager import get_container_manager
from database.database import get_db, engine
from database.models import User
from database.container_models import UserContainer, ContainerAction, ContainerLog, Base
from sqlalchemy.orm import Session

# Create tables
Base.metadata.create_all(bind=engine)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="X Growth Multi-Tenant API",
    description="Container-as-a-Service for X automation"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://*.xgrowth.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Container manager
container_manager = get_container_manager()


# ============================================================================
# Pydantic Models
# ============================================================================

class CreateContainerRequest(BaseModel):
    user_id: str
    plan: str = "starter"
    anthropic_api_key: Optional[str] = None


class ContainerActionRequest(BaseModel):
    action: str  # start, stop, restart


# ============================================================================
# Helper Functions
# ============================================================================

async def get_user_container(user_id: str, db: Session) -> Optional[UserContainer]:
    """Get user's container from database"""
    return db.query(UserContainer).filter(UserContainer.user_id == user_id).first()


async def proxy_to_container(
    user_id: str,
    endpoint: str,
    method: str = "GET",
    data: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    Proxy request to user's container
    """
    # Get container info
    container = await container_manager.get_container_status(user_id)

    if not container:
        raise HTTPException(status_code=404, detail="Container not found")

    if container['status'] != 'running':
        raise HTTPException(status_code=503, detail="Container not running")

    # Build URL
    url = f"http://localhost:{container['host_port']}{endpoint}"

    try:
        async with aiohttp.ClientSession() as session:
            if method == "GET":
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    return await resp.json()
            elif method == "POST":
                async with session.post(url, json=data, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                    return await resp.json()
    except Exception as e:
        logger.error(f"Failed to proxy to container: {e}")
        raise HTTPException(status_code=502, detail=f"Container error: {str(e)}")


# ============================================================================
# Health & Info
# ============================================================================

@app.get("/")
async def root():
    """API info"""
    containers = await container_manager.list_all_containers()

    return {
        "service": "X Growth Multi-Tenant API",
        "version": "1.0.0",
        "containers": {
            "total": len(containers),
            "running": len([c for c in containers if c['status'] == 'running']),
        }
    }


@app.get("/health")
async def health_check():
    """Health check"""
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


# ============================================================================
# Container Management
# ============================================================================

@app.post("/api/containers/create")
async def create_container(
    request: CreateContainerRequest,
    db: Session = Depends(get_db)
):
    """
    Create a dedicated container for user
    """
    user_id = request.user_id

    # Check if user exists
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if container already exists
    existing = db.query(UserContainer).filter(UserContainer.user_id == user_id).first()
    if existing and existing.status == "running":
        return {
            "success": True,
            "message": "Container already exists",
            "container": {
                "id": existing.container_id,
                "name": existing.container_name,
                "status": existing.status,
                "websocket_url": existing.websocket_url
            }
        }

    try:
        # Create container
        logger.info(f"Creating container for user {user_id[:8]}...")
        container_info = await container_manager.create_user_container(
            user_id=user_id,
            plan=request.plan,
            anthropic_api_key=request.anthropic_api_key
        )

        # Save to database
        db_container = UserContainer(
            user_id=user_id,
            container_id=container_info['container_id'],
            container_name=container_info['container_name'],
            host_port=container_info['host_port'],
            internal_port=container_info['internal_port'],
            websocket_url=container_info['websocket_url'],
            status=container_info['status'],
            started_at=datetime.utcnow()
        )
        db.add(db_container)
        db.commit()

        logger.info(f"✅ Container created and saved to DB")

        return {
            "success": True,
            "message": "Container created successfully",
            "container": {
                "id": container_info['container_id'],
                "name": container_info['container_name'],
                "status": container_info['status'],
                "websocket_url": container_info['websocket_url'],
                "host_port": container_info['host_port']
            }
        }

    except Exception as e:
        logger.error(f"Failed to create container: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/containers/{user_id}/action")
async def container_action(
    user_id: str,
    request: ContainerActionRequest,
    db: Session = Depends(get_db)
):
    """
    Perform action on container (start, stop, restart)
    """
    action = request.action

    # Get container from DB
    db_container = await get_user_container(user_id, db)
    if not db_container:
        raise HTTPException(status_code=404, detail="Container not found in database")

    try:
        if action == "stop":
            success = await container_manager.stop_user_container(user_id)
            if success:
                db_container.status = "stopped"
                db_container.stopped_at = datetime.utcnow()
                db.commit()

        elif action == "restart":
            success = await container_manager.restart_user_container(user_id)
            if success:
                db_container.status = "running"
                db_container.started_at = datetime.utcnow()
                db.commit()

        elif action == "remove":
            success = await container_manager.remove_user_container(user_id)
            if success:
                db.delete(db_container)
                db.commit()

        else:
            raise HTTPException(status_code=400, detail=f"Unknown action: {action}")

        return {
            "success": success,
            "action": action,
            "user_id": user_id
        }

    except Exception as e:
        logger.error(f"Container action failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/containers/{user_id}/status")
async def get_container_status(
    user_id: str,
    db: Session = Depends(get_db)
):
    """Get container status"""

    # Get from DB
    db_container = await get_user_container(user_id, db)
    if not db_container:
        return {
            "exists": False,
            "user_id": user_id
        }

    # Get live status from Docker
    live_status = await container_manager.get_container_status(user_id)

    # Update DB if status changed
    if live_status and live_status['status'] != db_container.status:
        db_container.status = live_status['status']
        db_container.last_health_check = datetime.utcnow()
        db.commit()

    return {
        "exists": True,
        "user_id": user_id,
        "container_id": db_container.container_id,
        "container_name": db_container.container_name,
        "status": db_container.status,
        "websocket_url": db_container.websocket_url,
        "host_port": db_container.host_port,
        "created_at": db_container.created_at.isoformat(),
        "started_at": db_container.started_at.isoformat() if db_container.started_at else None,
        "uptime_seconds": db_container.uptime_seconds,
        "total_actions": db_container.total_actions
    }


@app.get("/api/containers/{user_id}/logs")
async def get_container_logs(user_id: str, tail: int = 100):
    """Get container logs"""
    logs = await container_manager.get_container_logs(user_id, tail=tail)
    return {
        "user_id": user_id,
        "logs": logs
    }


@app.get("/api/admin/containers")
async def list_all_containers():
    """List all containers (admin only)"""
    containers = await container_manager.list_all_containers()
    return {
        "total": len(containers),
        "containers": containers
    }


# ============================================================================
# Proxy Endpoints (Route to User Containers)
# ============================================================================

@app.post("/api/automation/{user_id}/start")
async def start_automation(
    user_id: str,
    data: Optional[Dict] = None,
    db: Session = Depends(get_db)
):
    """
    Start automation in user's container
    """
    result = await proxy_to_container(
        user_id=user_id,
        endpoint="/api/automation/start",
        method="POST",
        data=data or {}
    )

    return result


@app.post("/api/automation/{user_id}/stop")
async def stop_automation(user_id: str, db: Session = Depends(get_db)):
    """Stop automation in user's container"""
    result = await proxy_to_container(
        user_id=user_id,
        endpoint="/api/automation/stop",
        method="POST"
    )

    return result


@app.get("/api/automation/{user_id}/status")
async def get_automation_status(user_id: str):
    """Get automation status from user's container"""
    result = await proxy_to_container(
        user_id=user_id,
        endpoint="/api/automation/status",
        method="GET"
    )

    return result


@app.get("/api/automation/{user_id}/actions")
async def get_actions(user_id: str, limit: int = 50, db: Session = Depends(get_db)):
    """Get actions from user's container"""

    # Get from database
    actions = db.query(ContainerAction)\
        .filter(ContainerAction.user_id == user_id)\
        .order_by(ContainerAction.performed_at.desc())\
        .limit(limit)\
        .all()

    return {
        "user_id": user_id,
        "count": len(actions),
        "actions": [
            {
                "id": a.id,
                "type": a.action_type,
                "target": a.target,
                "success": a.success,
                "performed_at": a.performed_at.isoformat(),
                "details": a.details
            }
            for a in actions
        ]
    }


# ============================================================================
# WebSocket Proxy
# ============================================================================

@app.websocket("/ws/{user_id}")
async def websocket_proxy(websocket: WebSocket, user_id: str):
    """
    WebSocket proxy to user's container
    Connects frontend to user's specific container
    """
    await websocket.accept()
    logger.info(f"WebSocket connection from user {user_id[:8]}")

    # Get user's container
    container = await container_manager.get_container_status(user_id)

    if not container or container['status'] != 'running':
        await websocket.send_json({
            "error": "Container not running",
            "message": "Please start your container first"
        })
        await websocket.close()
        return

    # Connect to user's container WebSocket
    container_ws_url = f"ws://localhost:{container['host_port']}/ws"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(container_ws_url) as container_ws:
                logger.info(f"Connected to container WebSocket: {container_ws_url}")

                # Bidirectional proxy
                async def forward_to_container():
                    """Forward messages from client to container"""
                    try:
                        while True:
                            data = await websocket.receive_text()
                            await container_ws.send_str(data)
                    except WebSocketDisconnect:
                        logger.info(f"Client disconnected: {user_id[:8]}")
                    except Exception as e:
                        logger.error(f"Error forwarding to container: {e}")

                async def forward_to_client():
                    """Forward messages from container to client"""
                    try:
                        async for msg in container_ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                await websocket.send_text(msg.data)
                            elif msg.type == aiohttp.WSMsgType.ERROR:
                                break
                    except Exception as e:
                        logger.error(f"Error forwarding to client: {e}")

                # Run both directions concurrently
                await asyncio.gather(
                    forward_to_container(),
                    forward_to_client()
                )

    except Exception as e:
        logger.error(f"WebSocket proxy error: {e}")
        await websocket.send_json({"error": str(e)})
        await websocket.close()


# ============================================================================
# User Onboarding
# ============================================================================

@app.post("/api/users/onboard")
async def onboard_user(
    user_id: str,
    email: str,
    plan: str = "starter",
    db: Session = Depends(get_db)
):
    """
    Complete user onboarding:
    1. Create user in database
    2. Spin up their container
    3. Return ready-to-use environment
    """
    try:
        # 1. Create user
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            user = User(
                id=user_id,
                email=email,
                plan=plan,
                is_active=True
            )
            db.add(user)
            db.commit()
            logger.info(f"✅ User created: {user_id[:8]}")

        # 2. Create container
        container_info = await container_manager.create_user_container(
            user_id=user_id,
            plan=plan
        )

        # 3. Save container to DB
        db_container = UserContainer(
            user_id=user_id,
            container_id=container_info['container_id'],
            container_name=container_info['container_name'],
            host_port=container_info['host_port'],
            internal_port=container_info['internal_port'],
            websocket_url=container_info['websocket_url'],
            status=container_info['status'],
            started_at=datetime.utcnow()
        )
        db.add(db_container)
        db.commit()

        logger.info(f"✅ User onboarded successfully: {user_id[:8]}")

        return {
            "success": True,
            "message": "Welcome to X Growth!",
            "user": {
                "id": user_id,
                "email": email,
                "plan": plan
            },
            "container": {
                "status": "running",
                "websocket_url": container_info['websocket_url'],
                "dashboard_url": f"http://localhost:3000/dashboard"
            },
            "next_steps": [
                "Connect your X account",
                "Import your posts to train AI",
                "Start automation"
            ]
        }

    except Exception as e:
        logger.error(f"Onboarding failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
