#!/usr/bin/env python3
"""
Extension Backend Server
Bridges the agent (async_extension_tools.py) with the Chrome Extension
Handles bidirectional communication via WebSocket
"""

import asyncio
import json
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from datetime import datetime
import httpx
import uuid

app = FastAPI(title="Extension Backend Server")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Store active WebSocket connections
# Key: user_id, Value: WebSocket connection
active_connections: Dict[str, WebSocket] = {}

# Store pending requests waiting for extension response
# Key: request_id, Value: asyncio.Future
pending_requests: Dict[str, asyncio.Future] = {}

# Store user cookies
# Key: user_id, Value: {username, cookies, timestamp}
user_cookies: Dict[str, dict] = {}


# ============================================================================
# WebSocket Connection Management
# ============================================================================

@app.websocket("/ws/extension/{user_id}")
async def extension_websocket(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for Chrome Extension to connect
    Extension connects here and stays connected
    """
    await websocket.accept()
    active_connections[user_id] = websocket
    print(f"✅ Extension connected: {user_id}")
    
    try:
        while True:
            # Receive messages from extension
            data = await websocket.receive_json()
            
            # Handle response to pending request
            if "request_id" in data:
                request_id = data["request_id"]
                if request_id in pending_requests:
                    # Resolve the pending future
                    pending_requests[request_id].set_result(data)
                    del pending_requests[request_id]
            
            # Handle extension-initiated messages (e.g., rate limit alerts)
            elif data.get("type") == "ALERT":
                print(f"⚠️ Alert from extension: {data.get('message')}")
            
            # Handle cookies from extension
            elif data.get("type") == "COOKIES_CAPTURED":
                username = data.get("username")
                cookies = data.get("cookies", [])
                print(f"🍪 Received {len(cookies)} cookies from @{username}")
                
                # Store cookies
                user_cookies[user_id] = {
                    "username": username,
                    "cookies": cookies,
                    "timestamp": data.get("timestamp")
                }
                
                # Inject cookies into Docker VNC browser (stealth server)
                try:
                    print(f"💉 Injecting cookies into Docker VNC browser...")
                    async with httpx.AsyncClient() as client:
                        inject_response = await client.post(
                            "http://localhost:8005/inject_cookies",
                            json={
                                "cookies": cookies,
                                "username": username
                            },
                            timeout=45.0
                        )
                        inject_result = inject_response.json()
                        
                        if inject_result.get("success"):
                            print(f"✅ Cookies injected into VNC browser for @{username}")
                            if inject_result.get("logged_in"):
                                print(f"✅ VNC browser is now logged in as @{username}")
                            else:
                                print(f"⚠️ {inject_result.get('warning', 'Login verification pending')}")
                        else:
                            print(f"❌ Failed to inject cookies: {inject_result.get('error')}")
                except Exception as e:
                    print(f"⚠️ Error injecting cookies to VNC: {e}")
                    # Don't fail the whole flow if injection fails
                
                # Acknowledge receipt
                await websocket.send_json({
                    "type": "COOKIES_RECEIVED",
                    "message": f"Stored {len(cookies)} cookies for @{username}"
                })
                
                print(f"✅ Cookies stored for {user_id} (@{username})")
            
            # Handle login status
            elif data.get("type") == "LOGIN_STATUS":
                print(f"👤 Login status: {data.get('username')} - {data.get('loggedIn')}")
            
    except WebSocketDisconnect:
        print(f"❌ Extension disconnected: {user_id}")
        if user_id in active_connections:
            del active_connections[user_id]


async def send_to_extension(user_id: str, command: dict, timeout: int = 30) -> dict:
    """
    Send command to extension and wait for response
    
    Args:
        user_id: User ID to send command to
        command: Command dict to send
        timeout: Timeout in seconds
    
    Returns:
        Response from extension
    """
    if user_id not in active_connections:
        return {
            "success": False,
            "error": "Extension not connected"
        }
    
    # Generate unique request ID
    request_id = str(uuid.uuid4())
    command["request_id"] = request_id
    
    # Create future for response
    future = asyncio.Future()
    pending_requests[request_id] = future
    
    try:
        # Send command to extension
        websocket = active_connections[user_id]
        await websocket.send_json(command)
        
        # Wait for response with timeout
        response = await asyncio.wait_for(future, timeout=timeout)
        return response
        
    except asyncio.TimeoutError:
        if request_id in pending_requests:
            del pending_requests[request_id]
        return {
            "success": False,
            "error": f"Timeout waiting for extension response ({timeout}s)"
        }
    except Exception as e:
        if request_id in pending_requests:
            del pending_requests[request_id]
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# Extension Tool Endpoints (Called by Agent)
# ============================================================================

class ExtractEngagementRequest(BaseModel):
    post_identifier: str
    user_id: str = "default"

@app.post("/extension/extract_engagement")
async def extract_engagement(request: ExtractEngagementRequest):
    """Extract hidden engagement data from a post"""
    command = {
        "type": "EXTRACT_ENGAGEMENT",
        "post_identifier": request.post_identifier
    }
    
    response = await send_to_extension(request.user_id, command)
    return response


class RateLimitRequest(BaseModel):
    user_id: str = "default"

@app.get("/extension/rate_limit_status")
async def rate_limit_status(user_id: str = "default"):
    """Check if X is showing rate limit warnings"""
    command = {
        "type": "CHECK_RATE_LIMIT"
    }
    
    response = await send_to_extension(user_id, command)
    return response


class PostContextRequest(BaseModel):
    post_identifier: str
    user_id: str = "default"

@app.post("/extension/post_context")
async def post_context(request: PostContextRequest):
    """Get full context of a post including hidden data"""
    command = {
        "type": "GET_POST_CONTEXT",
        "post_identifier": request.post_identifier
    }
    
    response = await send_to_extension(request.user_id, command)
    return response


class HumanClickRequest(BaseModel):
    element_description: str
    user_id: str = "default"

@app.post("/extension/human_click")
async def human_click(request: HumanClickRequest):
    """Click an element with human-like behavior"""
    command = {
        "type": "HUMAN_CLICK",
        "element_description": request.element_description
    }
    
    response = await send_to_extension(request.user_id, command)
    return response


class MonitorActionRequest(BaseModel):
    action_type: str
    timeout: int = 5
    user_id: str = "default"

@app.post("/extension/monitor_action")
async def monitor_action(request: MonitorActionRequest):
    """Monitor DOM for action result"""
    command = {
        "type": "MONITOR_ACTION",
        "action_type": request.action_type,
        "timeout": request.timeout
    }
    
    response = await send_to_extension(request.user_id, command, timeout=request.timeout + 5)
    return response


class AccountInsightsRequest(BaseModel):
    username: str
    user_id: str = "default"

@app.post("/extension/account_insights")
async def account_insights(request: AccountInsightsRequest):
    """Extract detailed account insights"""
    command = {
        "type": "EXTRACT_ACCOUNT_INSIGHTS",
        "username": request.username
    }
    
    response = await send_to_extension(request.user_id, command)
    return response


@app.get("/extension/session_health")
async def session_health(user_id: str = "default"):
    """Check if browser session is healthy"""
    command = {
        "type": "CHECK_SESSION_HEALTH"
    }
    
    response = await send_to_extension(user_id, command)
    return response


@app.get("/extension/trending_topics")
async def trending_topics(user_id: str = "default"):
    """Get current trending topics"""
    command = {
        "type": "GET_TRENDING_TOPICS"
    }
    
    response = await send_to_extension(user_id, command)
    return response


class FindPostsRequest(BaseModel):
    topic: str
    limit: int = 10
    sort_by: str = "engagement"
    user_id: str = "default"

@app.post("/extension/find_posts")
async def find_posts(request: FindPostsRequest):
    """Find high-engagement posts on a topic"""
    command = {
        "type": "FIND_HIGH_ENGAGEMENT_POSTS",
        "topic": request.topic,
        "limit": request.limit,
        "sort_by": request.sort_by
    }

    response = await send_to_extension(request.user_id, command)
    return response


class CreatePostRequest(BaseModel):
    post_text: str
    user_id: str = "default"

@app.post("/extension/create-post")
async def create_post(request: CreatePostRequest):
    """
    Create a new post on X using the extension.
    
    Args:
        post_text: The text content of the post (max 280 chars)
        user_id: User ID for routing to correct extension instance
    
    Returns:
        Success/failure status with post details
    """
    command = {
        "type": "CREATE_POST",
        "post_text": request.post_text
    }
    
    response = await send_to_extension(request.user_id, command, timeout=15)
    return response


class CommentRequest(BaseModel):
    post_identifier: str
    comment_text: str
    user_id: str = "default"

@app.post("/extension/comment")
async def comment_on_post(request: CommentRequest):
    """Comment on a post - uses extension for reliability"""
    command = {
        "type": "COMMENT_ON_POST",
        "post_identifier": request.post_identifier,
        "comment_text": request.comment_text
    }

    response = await send_to_extension(request.user_id, command, timeout=45)
    return response


# ============================================================================
# Status & Health Endpoints
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Extension Backend Server",
        "active_connections": len(active_connections),
        "connected_users": list(active_connections.keys()),
        "pending_requests": len(pending_requests)
    }


@app.get("/status")
async def status():
    """Server status"""
    # Include user info with cookies
    users_with_info = []
    for user_id in active_connections.keys():
        user_info = {"userId": user_id}
        if user_id in user_cookies:
            user_info["username"] = user_cookies[user_id].get("username")
            user_info["hasCookies"] = True
        else:
            user_info["hasCookies"] = False
        users_with_info.append(user_info)
    
    return {
        "success": True,
        "active_connections": len(active_connections),
        "connected_users": list(active_connections.keys()),
        "users_with_info": users_with_info,
        "pending_requests": len(pending_requests),
        "timestamp": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "extensions_connected": len(active_connections) > 0
    }


@app.post("/scrape-posts")
async def scrape_posts(data: dict):
    """
    Request extension to scrape user's X posts
    """
    user_id = data.get("user_id")
    target_count = data.get("targetCount", 50)
    
    if not user_id or user_id not in active_connections:
        return {
            "success": False,
            "error": "Extension not connected"
        }
    
    try:
        # Send scrape request to extension
        request_id = str(uuid.uuid4())
        websocket = active_connections[user_id]
        
        await websocket.send_json({
            "type": "SCRAPE_POSTS_REQUEST",
            "request_id": request_id,
            "targetCount": target_count
        })
        
        # Wait for response
        future = asyncio.Future()
        pending_requests[request_id] = future
        
        try:
            result = await asyncio.wait_for(future, timeout=30.0)
            return {
                "success": True,
                "posts": result.get("posts", []),
                "count": result.get("count", 0)
            }
        except asyncio.TimeoutError:
            if request_id in pending_requests:
                del pending_requests[request_id]
            return {
                "success": False,
                "error": "Scraping timed out"
            }
            
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/cookies/{user_id}")
async def get_user_cookies(user_id: str):
    """Get cookies for a specific user"""
    if user_id not in user_cookies:
        return {
            "success": False,
            "error": "No cookies found for this user"
        }
    
    return {
        "success": True,
        "user_id": user_id,
        "username": user_cookies[user_id].get("username"),
        "cookies": user_cookies[user_id].get("cookies", []),
        "timestamp": user_cookies[user_id].get("timestamp")
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("🚀 Starting Extension Backend Server...")
    print("📡 Extension should connect to: ws://localhost:8001/ws/extension/{user_id}")
    print("🔧 Agent tools will call: http://localhost:8001/extension/*")
    
    uvicorn.run(
        "backend_extension_server:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )

