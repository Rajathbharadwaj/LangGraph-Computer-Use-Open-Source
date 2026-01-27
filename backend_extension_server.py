#!/usr/bin/env python3
"""
Extension Backend Server
Bridges the agent (async_extension_tools.py) with the Chrome Extension
Handles bidirectional communication via WebSocket
"""

import asyncio
import json
import os
from typing import Dict, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from datetime import datetime
import httpx
import uuid
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

# Database imports - lazy initialization to avoid startup failures
import os

# Only import database if DATABASE_URL is set (production)
DATABASE_ENABLED = bool(os.getenv("DATABASE_URL"))

if DATABASE_ENABLED:
    try:
        from database.database import SessionLocal, engine, Base, get_db
        from database.models import User, XAccount, UserCookies, LinkedInAccount, LinkedInCookies
    except Exception as e:
        print(f"⚠️ Database import failed: {e}")
        DATABASE_ENABLED = False
else:
    SessionLocal = None
    User = None
    XAccount = None
    UserCookies = None
    LinkedInAccount = None
    LinkedInCookies = None

# Encryption key for cookies (in production, use a proper secret management)
COOKIE_ENCRYPTION_KEY = os.getenv("COOKIE_ENCRYPTION_KEY", Fernet.generate_key().decode())
fernet = Fernet(COOKIE_ENCRYPTION_KEY.encode() if isinstance(COOKIE_ENCRYPTION_KEY, str) else COOKIE_ENCRYPTION_KEY)

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

# In-memory cache for active session cookies (also persisted to DB)
# Key: user_id, Value: {username, cookies, timestamp}
user_cookies: Dict[str, dict] = {}

# LinkedIn in-memory cookie cache
# Key: user_id, Value: {profile_url, cookies, timestamp}
linkedin_cookies: Dict[str, dict] = {}


# ============================================================================
# Database Helper Functions
# ============================================================================

def init_database():
    """Initialize database tables - call this lazily when needed"""
    if not DATABASE_ENABLED:
        return False
    try:
        from database.database import Base, engine
        Base.metadata.create_all(bind=engine)
        print("✅ Database tables initialized")
        return True
    except Exception as e:
        print(f"⚠️ Database initialization failed: {e}")
        return False


def get_or_create_user(db: Session, user_id: str) -> User:
    """Get or create a user in the database"""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, email=f"{user_id}@extension.local")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_x_account(db: Session, user_id: str, username: str) -> XAccount:
    """Get or create an X account for a user"""
    user = get_or_create_user(db, user_id)

    # Check if account already exists
    x_account = db.query(XAccount).filter(
        XAccount.user_id == user_id,
        XAccount.username == username
    ).first()

    if not x_account:
        x_account = XAccount(
            user_id=user_id,
            username=username,
            is_connected=True
        )
        db.add(x_account)
        db.commit()
        db.refresh(x_account)
    else:
        # Update connection status
        x_account.is_connected = True
        x_account.last_synced_at = datetime.utcnow()
        db.commit()

    return x_account


def save_cookies_to_db(db: Session, user_id: str, username: str, cookies: list) -> bool:
    """Save encrypted cookies to database"""
    try:
        x_account = get_or_create_x_account(db, user_id, username)

        # Encrypt cookies
        cookies_json = json.dumps(cookies)
        encrypted_cookies = fernet.encrypt(cookies_json.encode()).decode()

        # Check if cookies already exist for this account
        existing_cookies = db.query(UserCookies).filter(
            UserCookies.x_account_id == x_account.id
        ).first()

        if existing_cookies:
            existing_cookies.encrypted_cookies = encrypted_cookies
            existing_cookies.captured_at = datetime.utcnow()
        else:
            new_cookies = UserCookies(
                x_account_id=x_account.id,
                encrypted_cookies=encrypted_cookies,
                captured_at=datetime.utcnow()
            )
            db.add(new_cookies)

        db.commit()
        print(f"✅ Cookies saved to database for @{username}")
        return True
    except Exception as e:
        print(f"❌ Error saving cookies to database: {e}")
        db.rollback()
        return False


def load_cookies_from_db(db: Session, user_id: str = None, username: str = None) -> Optional[dict]:
    """Load and decrypt cookies from database"""
    try:
        query = db.query(XAccount, UserCookies).join(
            UserCookies, XAccount.id == UserCookies.x_account_id
        )

        if user_id:
            query = query.filter(XAccount.user_id == user_id)
        if username:
            query = query.filter(XAccount.username == username)

        result = query.first()

        if result:
            x_account, user_cookies_record = result
            decrypted_cookies = fernet.decrypt(user_cookies_record.encrypted_cookies.encode()).decode()
            return {
                "user_id": x_account.user_id,
                "username": x_account.username,
                "cookies": json.loads(decrypted_cookies),
                "captured_at": user_cookies_record.captured_at.isoformat()
            }
        return None
    except Exception as e:
        print(f"❌ Error loading cookies from database: {e}")
        return None


# ============================================================================
# LinkedIn Database Helper Functions
# ============================================================================

def get_or_create_linkedin_account(db: Session, user_id: str, profile_url: str, display_name: str = None) -> "LinkedInAccount":
    """Get or create a LinkedIn account for a user"""
    user = get_or_create_user(db, user_id)

    # Extract username from profile URL
    username = None
    if profile_url:
        # Extract from linkedin.com/in/username
        if '/in/' in profile_url:
            username = profile_url.split('/in/')[-1].strip('/').split('/')[0].split('?')[0]

    # Check if account already exists
    linkedin_account = db.query(LinkedInAccount).filter(
        LinkedInAccount.user_id == user_id
    ).first()

    if not linkedin_account:
        linkedin_account = LinkedInAccount(
            user_id=user_id,
            profile_url=profile_url,
            username=username,
            display_name=display_name,
            is_connected=True
        )
        db.add(linkedin_account)
        db.commit()
        db.refresh(linkedin_account)
    else:
        # Update info
        linkedin_account.is_connected = True
        linkedin_account.profile_url = profile_url or linkedin_account.profile_url
        linkedin_account.username = username or linkedin_account.username
        if display_name:
            linkedin_account.display_name = display_name
        linkedin_account.last_synced_at = datetime.utcnow()
        db.commit()

    return linkedin_account


def save_linkedin_cookies_to_db(db: Session, user_id: str, profile_url: str, cookies: list, display_name: str = None) -> bool:
    """Save encrypted LinkedIn cookies to database"""
    try:
        linkedin_account = get_or_create_linkedin_account(db, user_id, profile_url, display_name)

        # Encrypt cookies
        cookies_json = json.dumps(cookies)
        encrypted_cookies = fernet.encrypt(cookies_json.encode()).decode()

        # Check if cookies already exist for this account
        existing_cookies = db.query(LinkedInCookies).filter(
            LinkedInCookies.linkedin_account_id == linkedin_account.id
        ).first()

        if existing_cookies:
            existing_cookies.encrypted_cookies = encrypted_cookies
            existing_cookies.captured_at = datetime.utcnow()
        else:
            new_cookies = LinkedInCookies(
                linkedin_account_id=linkedin_account.id,
                encrypted_cookies=encrypted_cookies,
                captured_at=datetime.utcnow()
            )
            db.add(new_cookies)

        db.commit()
        print(f"✅ LinkedIn cookies saved to database for {profile_url}")
        return True
    except Exception as e:
        print(f"❌ Error saving LinkedIn cookies to database: {e}")
        db.rollback()
        return False


def load_linkedin_cookies_from_db(db: Session, user_id: str = None) -> Optional[dict]:
    """Load and decrypt LinkedIn cookies from database"""
    try:
        query = db.query(LinkedInAccount, LinkedInCookies).join(
            LinkedInCookies, LinkedInAccount.id == LinkedInCookies.linkedin_account_id
        )

        if user_id:
            query = query.filter(LinkedInAccount.user_id == user_id)

        result = query.first()

        if result:
            linkedin_account, linkedin_cookies_record = result
            decrypted_cookies = fernet.decrypt(linkedin_cookies_record.encrypted_cookies.encode()).decode()
            return {
                "user_id": linkedin_account.user_id,
                "profile_url": linkedin_account.profile_url,
                "username": linkedin_account.username,
                "display_name": linkedin_account.display_name,
                "cookies": json.loads(decrypted_cookies),
                "captured_at": linkedin_cookies_record.captured_at.isoformat()
            }
        return None
    except Exception as e:
        print(f"❌ Error loading LinkedIn cookies from database: {e}")
        return None


def get_all_users_with_cookies(db: Session) -> list:
    """Get all users who have cookies stored in the database"""
    try:
        results = db.query(XAccount, UserCookies).join(
            UserCookies, XAccount.id == UserCookies.x_account_id
        ).all()

        users = []
        for x_account, user_cookies_record in results:
            users.append({
                "userId": x_account.user_id,
                "username": x_account.username,
                "hasCookies": True,
                "connected": x_account.user_id in active_connections,
                "capturedAt": user_cookies_record.captured_at.isoformat() if user_cookies_record.captured_at else None
            })
        return users
    except Exception as e:
        print(f"❌ Error getting users with cookies: {e}")
        return []


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

                # Store cookies in memory cache
                user_cookies[user_id] = {
                    "username": username,
                    "cookies": cookies,
                    "timestamp": data.get("timestamp")
                }

                # Persist cookies to database (if enabled)
                if DATABASE_ENABLED and SessionLocal:
                    db = SessionLocal()
                    try:
                        init_database()  # Lazy init
                        save_cookies_to_db(db, user_id, username, cookies)
                    except Exception as e:
                        print(f"⚠️ Failed to save cookies to database: {e}")
                    finally:
                        db.close()
                
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
            
            # Handle LinkedIn cookies from extension
            elif data.get("type") == "LINKEDIN_COOKIES_CAPTURED":
                username = data.get("username")
                cookies = data.get("cookies", [])
                print(f"🔗 Received {len(cookies)} LinkedIn cookies for {username or 'user'}")

                # Store cookies in memory cache
                linkedin_cookies[user_id] = {
                    "username": username,
                    "cookies": cookies,
                    "timestamp": data.get("timestamp")
                }

                # Persist cookies to database
                if DATABASE_ENABLED and SessionLocal:
                    db = SessionLocal()
                    try:
                        save_linkedin_cookies_to_db(db, user_id, username, cookies)
                        print(f"✅ LinkedIn cookies saved to database for {user_id}")
                    except Exception as e:
                        print(f"⚠️ Failed to save LinkedIn cookies to database: {e}")
                    finally:
                        db.close()

                # Acknowledge receipt
                await websocket.send_json({
                    "type": "LINKEDIN_COOKIES_RECEIVED",
                    "message": f"Stored {len(cookies)} LinkedIn cookies for {username or 'user'}"
                })

                print(f"✅ LinkedIn cookies stored for {user_id}")

            # Handle LinkedIn login status
            elif data.get("type") == "LINKEDIN_LOGIN_STATUS":
                print(f"🔗 LinkedIn login status: {data.get('username')} - {data.get('loggedIn')}")

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


class PostUrlRequest(BaseModel):
    identifier: str
    user_id: str = "default"

@app.post("/extension/get_post_url")
async def get_post_url(request: PostUrlRequest):
    """Extract URL of a specific post to navigate to thread view"""
    command = {
        "action": "GET_POST_URL",
        "identifier": request.identifier,
        "requestId": f"get_post_url_{request.identifier[:20]}"
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


@app.get("/extension/premium_status")
async def premium_status(user_id: str = "default"):
    """Check if current X account has Premium/Blue subscription"""
    command = {
        "type": "CHECK_PREMIUM_STATUS"
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
    
    response = await send_to_extension(request.user_id, command, timeout=30)
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
async def status(user_id: Optional[str] = None):
    """
    Server status - returns user connection info

    Args:
        user_id: Optional Clerk user ID to filter results to a specific user
                 If not provided, returns all users (for extension compatibility)
    """
    users_with_info = []

    # Query database for all users with cookies (if database enabled)
    if DATABASE_ENABLED and SessionLocal:
        db = SessionLocal()
        try:
            all_users = get_all_users_with_cookies(db)
            # If user_id specified, filter to only that user
            if user_id:
                users_with_info = [u for u in all_users if u.get("userId") == user_id]
            else:
                users_with_info = all_users
        except Exception as e:
            print(f"⚠️ Failed to get users from database: {e}")
        finally:
            db.close()

    # Also add users from in-memory cache (for active sessions or when DB is disabled)
    db_user_ids = {u["userId"] for u in users_with_info}

    # Add users from in-memory cookie cache
    for uid, cookie_data in user_cookies.items():
        # Skip if filtering by user_id and this isn't the user
        if user_id and uid != user_id:
            continue

        if uid not in db_user_ids:
            users_with_info.append({
                "userId": uid,
                "username": cookie_data.get("username"),
                "hasCookies": True,
                "connected": uid in active_connections
            })
            db_user_ids.add(uid)

    # Add connected users without cookies
    for uid in active_connections.keys():
        # Skip if filtering by user_id and this isn't the user
        if user_id and uid != user_id:
            continue

        if uid not in db_user_ids:
            users_with_info.append({
                "userId": uid,
                "hasCookies": False,
                "connected": True
            })

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


@app.get("/get-cookies/{user_id}")
async def get_cookies(user_id: str):
    """Get stored cookies for a user (from database or memory)"""
    # First check in-memory cache
    if user_id in user_cookies:
        cookie_data = user_cookies[user_id]
        return {
            "success": True,
            "username": cookie_data.get("username"),
            "cookies": cookie_data.get("cookies", []),
            "captured_at": cookie_data.get("timestamp")
        }

    # Then check database if enabled
    if DATABASE_ENABLED and SessionLocal:
        db = SessionLocal()
        try:
            cookie_data = load_cookies_from_db(db, user_id=user_id)
            if cookie_data:
                return {
                    "success": True,
                    "username": cookie_data["username"],
                    "cookies": cookie_data["cookies"],
                    "captured_at": cookie_data["captured_at"]
                }
        except Exception as e:
            print(f"⚠️ Error loading cookies from database: {e}")
        finally:
            db.close()

    return {
        "success": False,
        "error": "No cookies found for user"
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


@app.delete("/disconnect/{user_id}")
async def disconnect_user(user_id: str):
    """
    Disconnect a user by clearing their cookies from memory and database.
    This is called when the user clicks "Disconnect" in the frontend.
    """
    cleared_memory = False
    cleared_database = False
    username = None

    # Clear from in-memory cache
    if user_id in user_cookies:
        username = user_cookies[user_id].get("username")
        del user_cookies[user_id]
        cleared_memory = True
        print(f"🗑️ Cleared in-memory cookies for user {user_id}")

    # Clear from database if enabled
    if DATABASE_ENABLED:
        try:
            db = SessionLocal()
            try:
                # Find and delete the user's cookies from database
                x_account = db.query(XAccount).filter(XAccount.user_id == user_id).first()
                if x_account:
                    username = username or x_account.username
                    # Delete associated cookies
                    db.query(UserCookies).filter(UserCookies.x_account_id == x_account.id).delete()
                    # Delete the X account record
                    db.delete(x_account)
                    db.commit()
                    cleared_database = True
                    print(f"🗑️ Cleared database cookies for user {user_id}")
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️ Error clearing database cookies: {e}")

    # Close WebSocket connection if active
    if user_id in active_connections:
        try:
            ws = active_connections[user_id]
            await ws.close(code=1000, reason="User disconnected")
            del active_connections[user_id]
            print(f"🔌 Closed WebSocket for user {user_id}")
        except Exception as e:
            print(f"⚠️ Error closing WebSocket: {e}")

    if cleared_memory or cleared_database:
        return {
            "success": True,
            "message": f"Disconnected user {user_id}",
            "username": username,
            "cleared_memory": cleared_memory,
            "cleared_database": cleared_database
        }
    else:
        return {
            "success": False,
            "error": "No data found for this user",
            "user_id": user_id
        }


# ============================================================================
# LinkedIn Cookie Endpoints
# ============================================================================

@app.post("/linkedin/cookies")
async def save_linkedin_cookies_endpoint(data: dict):
    """
    Save LinkedIn cookies from extension or manual capture.

    Expected payload:
    {
        "user_id": "clerk_user_id",
        "profile_url": "https://linkedin.com/in/username",
        "display_name": "John Doe",
        "cookies": [...]
    }
    """
    user_id = data.get("user_id")
    profile_url = data.get("profile_url")
    display_name = data.get("display_name")
    cookies = data.get("cookies", [])

    if not user_id:
        return {"success": False, "error": "user_id is required"}
    if not cookies:
        return {"success": False, "error": "cookies are required"}

    # Store in memory cache
    linkedin_cookies[user_id] = {
        "profile_url": profile_url,
        "display_name": display_name,
        "cookies": cookies,
        "timestamp": datetime.utcnow().isoformat()
    }
    print(f"🔗 LinkedIn cookies stored for user {user_id}")

    # Persist to database if enabled
    if DATABASE_ENABLED and SessionLocal:
        db = SessionLocal()
        try:
            init_database()
            save_linkedin_cookies_to_db(db, user_id, profile_url, cookies, display_name)
        except Exception as e:
            print(f"⚠️ Failed to save LinkedIn cookies to database: {e}")
        finally:
            db.close()

    return {
        "success": True,
        "message": f"Stored {len(cookies)} LinkedIn cookies",
        "user_id": user_id,
        "profile_url": profile_url
    }


@app.get("/linkedin/cookies/{user_id}")
async def get_linkedin_cookies_endpoint(user_id: str):
    """Get LinkedIn cookies for a specific user"""
    # First check in-memory cache
    if user_id in linkedin_cookies:
        cookie_data = linkedin_cookies[user_id]
        return {
            "success": True,
            "profile_url": cookie_data.get("profile_url"),
            "display_name": cookie_data.get("display_name"),
            "cookies": cookie_data.get("cookies", []),
            "captured_at": cookie_data.get("timestamp")
        }

    # Then check database if enabled
    if DATABASE_ENABLED and SessionLocal:
        db = SessionLocal()
        try:
            cookie_data = load_linkedin_cookies_from_db(db, user_id=user_id)
            if cookie_data:
                return {
                    "success": True,
                    "profile_url": cookie_data.get("profile_url"),
                    "username": cookie_data.get("username"),
                    "display_name": cookie_data.get("display_name"),
                    "cookies": cookie_data["cookies"],
                    "captured_at": cookie_data["captured_at"]
                }
        except Exception as e:
            print(f"⚠️ Error loading LinkedIn cookies from database: {e}")
        finally:
            db.close()

    return {
        "success": False,
        "error": "No LinkedIn cookies found for user"
    }


@app.delete("/linkedin/disconnect/{user_id}")
async def disconnect_linkedin_user(user_id: str):
    """
    Disconnect a user's LinkedIn account by clearing their cookies.
    """
    cleared_memory = False
    cleared_database = False
    profile_url = None

    # Clear from in-memory cache
    if user_id in linkedin_cookies:
        profile_url = linkedin_cookies[user_id].get("profile_url")
        del linkedin_cookies[user_id]
        cleared_memory = True
        print(f"🗑️ Cleared LinkedIn in-memory cookies for user {user_id}")

    # Clear from database if enabled
    if DATABASE_ENABLED and SessionLocal:
        try:
            db = SessionLocal()
            try:
                linkedin_account = db.query(LinkedInAccount).filter(
                    LinkedInAccount.user_id == user_id
                ).first()
                if linkedin_account:
                    profile_url = profile_url or linkedin_account.profile_url
                    # Delete associated cookies
                    db.query(LinkedInCookies).filter(
                        LinkedInCookies.linkedin_account_id == linkedin_account.id
                    ).delete()
                    # Delete the LinkedIn account record
                    db.delete(linkedin_account)
                    db.commit()
                    cleared_database = True
                    print(f"🗑️ Cleared LinkedIn database cookies for user {user_id}")
            finally:
                db.close()
        except Exception as e:
            print(f"⚠️ Error clearing LinkedIn database cookies: {e}")

    if cleared_memory or cleared_database:
        return {
            "success": True,
            "message": f"Disconnected LinkedIn for user {user_id}",
            "profile_url": profile_url,
            "cleared_memory": cleared_memory,
            "cleared_database": cleared_database
        }
    else:
        return {
            "success": False,
            "error": "No LinkedIn data found for this user",
            "user_id": user_id
        }


@app.get("/linkedin/status/{user_id}")
async def linkedin_status(user_id: str):
    """Check LinkedIn connection status for a user"""
    has_cookies = False
    profile_url = None
    display_name = None

    # Check in-memory cache
    if user_id in linkedin_cookies:
        has_cookies = True
        profile_url = linkedin_cookies[user_id].get("profile_url")
        display_name = linkedin_cookies[user_id].get("display_name")

    # Check database if not in memory
    if not has_cookies and DATABASE_ENABLED and SessionLocal:
        db = SessionLocal()
        try:
            cookie_data = load_linkedin_cookies_from_db(db, user_id=user_id)
            if cookie_data:
                has_cookies = True
                profile_url = cookie_data.get("profile_url")
                display_name = cookie_data.get("display_name")
        except Exception as e:
            print(f"⚠️ Error checking LinkedIn status: {e}")
        finally:
            db.close()

    return {
        "success": True,
        "user_id": user_id,
        "is_connected": has_cookies,
        "profile_url": profile_url,
        "display_name": display_name
    }


# ============================================================================
# Main
# ============================================================================

if __name__ == "__main__":
    print("🚀 Starting Extension Backend Server...")
    print("📡 Extension should connect to: ws://localhost:8001/ws/extension/{user_id}")
    print("🔧 Agent tools will call: http://localhost:8001/extension/*")
    print("🔗 LinkedIn endpoints available at: http://localhost:8001/linkedin/*")
    
    uvicorn.run(
        "backend_extension_server:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )

