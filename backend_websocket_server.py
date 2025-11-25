"""
Simple Backend WebSocket Server for Extension
This connects your Chrome extension to the dashboard
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
from contextlib import asynccontextmanager
import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Extension backend URL - use Cloud Run URL in production
EXTENSION_BACKEND_URL = os.getenv("EXTENSION_BACKEND_URL", "http://localhost:8001")

# VNC Browser URL - Docker stealth browser service (port 8005 locally, Cloud Run in production)
VNC_BROWSER_URL = os.getenv("VNC_BROWSER_URL", "http://localhost:8005")

# LangGraph SDK for agent control
from langgraph_sdk import get_client

# LangGraph Store for persistent memory
from langgraph.store.postgres import PostgresStore

# Writing style learner
from x_writing_style_learner import XWritingStyleManager, WritingSample

# Workflow imports
from workflow_parser import parse_workflow, load_workflow, list_available_workflows

# Scheduled post executor
from scheduled_post_executor import get_executor

# UUID for generating IDs
import uuid

# Database imports
from database.database import SessionLocal, get_db
from database.models import ScheduledPost, XAccount
from sqlalchemy.orm import Session
from fastapi import Depends

# Clerk authentication imports
from clerk_auth import get_current_user
from clerk_webhooks import router as webhook_router

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize scheduled post executor on startup"""
    print("🚀 Starting Parallel Universe Backend...")

    # Initialize database tables
    try:
        from database.database import init_db
        init_db()
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")

    try:
        executor = await get_executor()
        print(f"✅ Scheduled post executor initialized with {len(executor.get_scheduled_posts())} pending posts")
    except Exception as e:
        print(f"❌ Failed to initialize scheduled post executor: {e}")
        import traceback
        traceback.print_exc()

    print("📡 WebSocket: ws://localhost:8001/ws/extension/{user_id}")
    print("🌐 Dashboard: http://localhost:3000")
    print("🔌 Extension will connect automatically!")
    print("🤖 LangGraph Agent: http://localhost:8124")

    yield

    # Shutdown
    print("🛑 Shutting down...")

app = FastAPI(title="Parallel Universe Backend", lifespan=lifespan)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://app.paralleluniverse.ai",
        "https://frontend-644185288504.us-central1.run.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Clerk webhook router
app.include_router(webhook_router)

# Store active connections
active_connections = {}

# Store user cookies (in production, this would be encrypted in database)
user_cookies = {}  # {user_id: {"username": str, "cookies": [...], "timestamp": int}}

# Store user posts for writing style learning
user_posts = {}  # {user_id: [{"content": str, "engagement": {...}, ...}]}

# Store agent threads per user (current active thread)
user_threads = {}  # {user_id: thread_id}

# Store thread metadata in memory (in production, use a database)
# Format: {thread_id: {"user_id": str, "title": str, "created_at": str, "last_message": str}}
thread_metadata = {}

# Track active runs for cancellation
# Format: {user_id: {"thread_id": str, "run_id": str, "task": asyncio.Task, "cancelled": bool}}
active_runs = {}

# Initialize LangGraph client
LANGGRAPH_URL = os.getenv("LANGGRAPH_URL", "http://localhost:8124")
langgraph_client = get_client(url=LANGGRAPH_URL)
print(f"✅ Initialized LangGraph client: {LANGGRAPH_URL}")

# Initialize PostgreSQL Store for persistent memory (writing samples, preferences, etc.)
# Using the same database as the main app
DB_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5433/xgrowth")

# Create store instance using direct initialization (not context manager)
# This is appropriate for long-running FastAPI servers
store = None
try:
    # Direct initialization - appropriate for servers
    # Use connection_string parameter as per LangGraph docs
    store = PostgresStore(connection_string=DB_URI)
    # Setup store table - required on first run, uses CREATE TABLE IF NOT EXISTS
    store.setup()
    print(f"✅ Initialized PostgresStore for persistent memory: {DB_URI}")
except Exception as e:
    print(f"⚠️ Failed to initialize PostgresStore (will retry on demand): {e}")
    import traceback
    traceback.print_exc()
    store = None


# ============================================================================
# Per-User VNC Client Helper
# ============================================================================
# This enables competitor discovery to use per-user VNC sessions instead of
# a shared global browser. Each user gets their own isolated browser.

import redis.asyncio as aioredis

async def get_user_vnc_client(user_id: str):
    """
    Get an AsyncPlaywrightClient for the user's VNC session.

    Looks up the user's VNC URL from Redis and creates a client for it.
    This enables per-user browser isolation for competitor discovery.

    Args:
        user_id: The Clerk user ID (e.g., user_35sAy5DRwouHPOUOk3okhywCGXN)

    Returns:
        AsyncPlaywrightClient configured for the user's VNC session

    Raises:
        HTTPException if no VNC session found for user
    """
    from async_playwright_tools import AsyncPlaywrightClient, get_client_for_url

    redis_host = os.environ.get('REDIS_HOST', '10.110.183.147')
    redis_port = int(os.environ.get('REDIS_PORT', 6379))
    redis_key = f"vnc:session:{user_id}"

    try:
        r = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)
        session_json = await r.get(redis_key)
        await r.aclose()

        if session_json:
            session_data = json.loads(session_json)
            vnc_url = session_data.get("https_url") or session_data.get("service_url")
            if vnc_url:
                print(f"✅ Found VNC session for user {user_id}: {vnc_url}")
                return get_client_for_url(vnc_url)

        # No session in Redis - check if service exists and cache it
        print(f"⚠️ No VNC session in Redis for user {user_id}, checking Cloud Run...")

        # Try to get session from VNC manager (which will cache it in Redis)
        from vnc_session_manager import VNCSessionManager
        vnc_manager = VNCSessionManager()
        await vnc_manager.connect()

        session = await vnc_manager.get_session(user_id)
        if session:
            vnc_url = session.get("https_url") or session.get("service_url")
            if vnc_url:
                print(f"✅ Recovered VNC session from Cloud Run for user {user_id}: {vnc_url}")
                return get_client_for_url(vnc_url)

        await vnc_manager.close()

        raise HTTPException(
            status_code=400,
            detail=f"No active VNC session for user. Please start a browser session first."
        )

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Failed to get VNC client for user {user_id}: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to connect to user's browser session: {str(e)}"
        )


# Initialize scheduled post executor on startup
@app.get("/")
async def root():
    return {
        "message": "Parallel Universe Backend",
        "websocket": "ws://localhost:8000/ws/extension/{user_id}",
        "active_connections": len(active_connections)
    }

@app.post("/api/generate-preview")
async def generate_preview(data: dict):
    """
    Generate a preview post/comment in the user's style
    
    Request body:
    {
        "user_id": "user_xxx",
        "clerk_user_id": "user_yyy",
        "content_type": "post" or "comment",
        "context": "What to write about or reply to",
        "feedback": "Optional previous feedback to incorporate"
    }
    """
    try:
        user_id = data.get("user_id")
        clerk_user_id = data.get("clerk_user_id")
        content_type = data.get("content_type", "post")
        context = data.get("context", "")
        feedback = data.get("feedback", "")
        
        if not user_id or not context:
            return {"success": False, "error": "Missing user_id or context"}
        
        print(f"🎨 Generating {content_type} preview for user: {user_id}")
        
        # Initialize style manager
        from x_writing_style_learner import XWritingStyleManager
        style_manager = XWritingStyleManager(store, user_id)
        
        # If there's feedback, append it to the context
        if feedback:
            context = f"{context}\n\nUSER FEEDBACK: {feedback}\nPlease incorporate this feedback in your response."
        
        # Generate the few-shot prompt first (so we can return it)
        few_shot_prompt = style_manager.generate_few_shot_prompt(
            context=context,
            content_type=content_type,
            num_examples=7  # Increased from 3 to 7 for better style learning
        )
        
        # Generate content
        generated = await style_manager.generate_content(
            context=context,
            content_type=content_type
        )
        
        return {
            "success": True,
            "content": generated.content,
            "mentions": getattr(generated, 'mentions', []),
            "content_type": content_type,
            "few_shot_prompt": few_shot_prompt
        }
        
    except Exception as e:
        print(f"❌ Error generating preview: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/save-feedback")
async def save_feedback(data: dict):
    """
    Save user feedback about generated content for style refinement
    
    Request body:
    {
        "user_id": "user_xxx",
        "feedback": "Make it more casual",
        "original_content": "The generated content",
        "context": "What it was about"
    }
    """
    try:
        user_id = data.get("user_id")
        feedback_text = data.get("feedback", "")
        original_content = data.get("original_content", "")
        context = data.get("context", "")
        
        if not user_id or not feedback_text:
            return {"success": False, "error": "Missing user_id or feedback"}
        
        print(f"💬 Saving feedback for user: {user_id}")
        
        # Store feedback in the store
        namespace = (user_id, "style_feedback")
        feedback_id = str(uuid.uuid4())
        
        feedback_data = {
            "feedback_id": feedback_id,
            "user_id": user_id,
            "feedback": feedback_text,
            "original_content": original_content,
            "context": context,
            "timestamp": datetime.now().isoformat()
        }
        
        store.put(namespace, feedback_id, feedback_data)
        
        print(f"✅ Saved feedback: {feedback_text[:50]}...")
        
        return {
            "success": True,
            "feedback_id": feedback_id,
            "message": "Feedback saved successfully"
        }
        
    except Exception as e:
        print(f"❌ Error saving feedback: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/agent/create-post")
async def agent_create_post(data: dict):
    """
    Generate a styled post and publish it to X via the Docker VNC extension.
    
    Request body:
    {
        "user_id": "user_xxx",  // Extension user ID (for scraping/posting)
        "clerk_user_id": "user_yyy",  // Clerk user ID (for style/memory)
        "context": "What to write about",
        "post_text": "Optional: pre-generated text to post directly"
    }
    
    If post_text is provided, it will be posted directly.
    Otherwise, content will be generated using the user's writing style.
    """
    try:
        user_id = data.get("user_id")  # Extension user ID
        clerk_user_id = data.get("clerk_user_id")  # Clerk user ID
        context = data.get("context", "")
        post_text = data.get("post_text", "")
        
        if not user_id:
            return {"success": False, "error": "Missing user_id"}
        
        print(f"📝 Creating post for user: {user_id}")
        
        # If no post_text provided, generate it
        if not post_text:
            if not context:
                return {"success": False, "error": "Missing context or post_text"}
            
            print(f"🎨 Generating styled post...")
            
            # Initialize style manager
            from x_writing_style_learner import XWritingStyleManager
            style_manager = XWritingStyleManager(store, user_id)
            
            # Generate content
            generated = await style_manager.generate_content(
                context=context,
                content_type="post"
            )
            
            post_text = generated.content
            print(f"✅ Generated post: {post_text[:50]}...")
        
        # Validate post length
        if len(post_text) > 280:
            return {
                "success": False,
                "error": f"Post too long ({len(post_text)} chars, max 280)"
            }
        
        # Call extension backend to create post
        print(f"📤 Sending post to extension backend...")

        import requests
        response = requests.post(
            f"{EXTENSION_BACKEND_URL}/extension/create-post",
            json={
                "post_text": post_text,
                "user_id": user_id
            },
            timeout=20
        )
        
        result = response.json()
        
        if result.get("success"):
            print(f"✅ Post created successfully!")
            return {
                "success": True,
                "post_text": post_text,
                "message": "Post created successfully!",
                "timestamp": result.get("timestamp", "")
            }
        else:
            print(f"❌ Failed to create post: {result.get('error')}")
            return {
                "success": False,
                "error": result.get("error", "Unknown error"),
                "post_text": post_text
            }
        
    except Exception as e:
        print(f"❌ Error creating post: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


# ============================================================================
# VNC Session Management Endpoints
# ============================================================================

# VNC Session Manager - only available in GCP production environment
try:
    from vnc_session_manager import get_vnc_manager
    VNC_MANAGER_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ VNC Session Manager not available (GCP-only): {e}")
    VNC_MANAGER_AVAILABLE = False

    # Provide a mock for local development
    async def get_vnc_manager():
        return None


@app.post("/api/vnc/create")
async def create_vnc_session(data: dict, auth_user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Create a new VNC browser session for authenticated user.

    This creates a dedicated Cloud Run Service for the user with their
    X.com cookies pre-loaded. Each user gets their own isolated browser.

    Request body:
    {
        "user_id": "clerk_user_id"  # Optional, will use auth user if not provided
    }

    Returns:
    {
        "success": true,
        "session": {
            "session_id": "uuid",
            "url": "wss://...",
            "status": "starting|running",
            "created_at": "timestamp"
        }
    }
    """
    try:
        # Get user ID from Clerk auth or request body
        user_id = data.get("user_id") or auth_user_id

        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        print(f"🖥️ Creating VNC session for user: {user_id}")

        # Get VNC manager
        vnc_manager = await get_vnc_manager()

        if not vnc_manager:
            raise HTTPException(status_code=503, detail="VNC session manager not available in this environment")

        # Get user's X cookies from database for injection
        user_cookies_data = None
        try:
            x_account = db.query(XAccount).filter(XAccount.user_id == user_id).first()
            if x_account and x_account.cookies:
                user_cookies_data = x_account.cookies
                print(f"✅ Found X cookies for user {user_id}")
        except Exception as e:
            print(f"⚠️ Could not load user cookies: {e}")

        # Create session with user's cookies
        session_data = await vnc_manager.create_session(user_id, cookies=user_cookies_data)

        return {
            "success": True,
            "session": session_data
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error creating VNC session: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/vnc/session")
async def get_vnc_session(user_id: str = Depends(get_current_user), db: Session = Depends(get_db)):
    """
    Get current user's VNC session or create new one if none exists.

    This endpoint creates a dedicated Cloud Run Service for the user with
    their X.com cookies pre-loaded for session isolation.

    Returns:
    {
        "success": true,
        "session": {
            "session_id": "uuid",
            "url": "wss://...",
            "status": "starting|running|stopped",
            "created_at": "timestamp"
        }
    }
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        print(f"🔍 Getting VNC session for user: {user_id}")

        # Get VNC manager
        vnc_manager = await get_vnc_manager()

        if not vnc_manager:
            # Development fallback - return shared VNC URL
            return {
                "success": True,
                "session": {
                    "session_id": "dev-shared",
                    "url": os.getenv("VNC_BROWSER_URL", "wss://vnc-browser-service-644185288504.us-central1.run.app"),
                    "status": "running",
                    "created_at": datetime.utcnow().isoformat(),
                    "user_id": user_id
                }
            }

        # Get user's X cookies from database for injection
        user_cookies_data = None
        try:
            x_account = db.query(XAccount).filter(XAccount.user_id == user_id).first()
            if x_account and x_account.cookies:
                user_cookies_data = x_account.cookies
                print(f"✅ Found X cookies for user {user_id}")
        except Exception as e:
            print(f"⚠️ Could not load user cookies: {e}")

        # Get or create session with user's cookies
        session_data = await vnc_manager.get_or_create_session(user_id, cookies=user_cookies_data)

        return {
            "success": True,
            "session": session_data
        }

    except Exception as e:
        print(f"❌ Error getting VNC session: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/vnc/{session_id}")
async def destroy_vnc_session(session_id: str, user_id: str = Depends(get_current_user)):
    """
    Terminate VNC session

    Returns:
    {
        "success": true,
        "message": "Session terminated"
    }
    """
    try:
        if not user_id:
            raise HTTPException(status_code=401, detail="Authentication required")

        print(f"🗑️ Destroying VNC session {session_id} for user: {user_id}")

        # Get VNC manager
        vnc_manager = await get_vnc_manager()

        # Destroy session
        success = await vnc_manager.destroy_session(user_id)

        if success:
            return {
                "success": True,
                "message": "VNC session terminated"
            }
        else:
            raise HTTPException(status_code=404, detail="Session not found")

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error destroying VNC session: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/posts/cleanup-duplicates/{user_id}")
async def cleanup_duplicate_posts(user_id: str):
    """Remove duplicate posts from both LangGraph Store and database"""
    try:
        # Clean up LangGraph Store
        style_manager = XWritingStyleManager(store, user_id)
        store_duplicates_removed = style_manager.remove_duplicate_posts()
        
        # Clean up database
        from database.models import UserPost, XAccount
        from database.database import SessionLocal
        from sqlalchemy import text
        
        db = SessionLocal()
        
        # Get username from user_id (assuming it's stored somewhere)
        # For now, we'll clean all duplicates regardless of user
        result = db.execute(text("""
            DELETE FROM user_posts a USING user_posts b
            WHERE a.id > b.id AND a.content = b.content
            RETURNING a.id
        """))
        db_duplicates_removed = result.rowcount
        db.commit()
        db.close()
        
        return {
            "success": True,
            "store_duplicates_removed": store_duplicates_removed,
            "db_duplicates_removed": db_duplicates_removed,
            "message": f"Removed {store_duplicates_removed} duplicates from store and {db_duplicates_removed} from database"
        }
        
    except Exception as e:
        print(f"❌ Error cleaning duplicates: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }

@app.get("/api/posts/count/{username}")
async def get_posts_count(username: str):
    """Get total count of imported posts from database"""
    try:
        from database.models import UserPost, XAccount
        from database.database import SessionLocal
        
        db = SessionLocal()
        
        # Get X account
        x_account = db.query(XAccount).filter(XAccount.username == username).first()
        
        if not x_account:
            db.close()
            return {
                "success": True,
                "count": 0,
                "username": username
            }
        
        # Count posts
        count = db.query(UserPost).filter(UserPost.x_account_id == x_account.id).count()
        db.close()
        
        return {
            "success": True,
            "count": count,
            "username": username
        }
        
    except Exception as e:
        print(f"❌ Error getting posts count: {e}")
        return {
            "success": False,
            "error": str(e),
            "count": 0
        }

@app.get("/api/posts/{user_id}")
async def get_user_posts(user_id: str):
    """Get stored posts for a user (from PostgreSQL database)"""
    try:
        # First try PostgreSQL database (most reliable source)
        from database.models import UserPost, XAccount
        from database.database import SessionLocal

        db = SessionLocal()
        try:
            # Get the user's X account by clerk_user_id
            x_account = db.query(XAccount).filter(XAccount.clerk_user_id == user_id).first()

            if x_account:
                # Get all posts for this X account
                db_posts = db.query(UserPost).filter(UserPost.x_account_id == x_account.id).order_by(UserPost.scraped_at.desc()).all()

                if db_posts:
                    posts = []
                    for post in db_posts:
                        posts.append({
                            "content": post.content,
                            "engagement": {
                                "likes": post.likes or 0,
                                "retweets": post.retweets or 0,
                                "replies": post.replies or 0,
                                "views": post.views or 0
                            },
                            "timestamp": post.posted_at.isoformat() if post.posted_at else "",
                            "content_type": post.content_type or "post",
                            "scraped_at": post.scraped_at.isoformat() if post.scraped_at else ""
                        })

                    print(f"✅ Retrieved {len(posts)} posts from PostgreSQL for user {user_id}")
                    return {
                        "success": True,
                        "user_id": user_id,
                        "posts": posts,
                        "count": len(posts),
                        "source": "postgresql"
                    }
        finally:
            db.close()

        # Try LangGraph store if PostgreSQL had no results
        if store:
            namespace = (user_id, "writing_samples")
            items = store.search(namespace)
            posts = []

            for item in items:
                sample_data = item.value
                posts.append({
                    "content": sample_data.get("content", ""),
                    "engagement": sample_data.get("engagement", {}),
                    "timestamp": sample_data.get("timestamp", ""),
                    "content_type": sample_data.get("content_type", "post")
                })

            if posts:
                return {
                    "success": True,
                    "user_id": user_id,
                    "posts": posts,
                    "count": len(posts),
                    "source": "persistent_store"
                }

        # Fallback to in-memory if nothing in store
        if user_id in user_posts:
            return {
                "success": True,
                "user_id": user_id,
                "posts": user_posts[user_id],
                "count": len(user_posts[user_id]),
                "source": "memory"
            }

        return {
            "success": False,
            "error": "No posts found for this user",
            "user_id": user_id
        }

    except Exception as e:
        print(f"❌ Error retrieving posts: {e}")
        import traceback
        traceback.print_exc()

        # Fallback to in-memory
        if user_id in user_posts:
            return {
                "success": True,
                "user_id": user_id,
                "posts": user_posts[user_id],
                "count": len(user_posts[user_id]),
                "source": "memory_fallback"
            }
        
        return {
            "success": False,
            "error": str(e),
            "user_id": user_id
        }

@app.get("/api/extension/status")
async def extension_status(user_id: Optional[str] = None):
    """
    Check if any extensions are connected

    Args:
        user_id: Optional Clerk user ID to filter results to a specific user
    """
    import aiohttp

    # Check extension backend for connected extensions
    try:
        async with aiohttp.ClientSession() as session:
            # Pass user_id parameter to extension backend for security filtering
            url = f'{EXTENSION_BACKEND_URL}/status'
            if user_id:
                url = f'{url}?user_id={user_id}'

            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    ext_data = await resp.json()
                    users_with_info = ext_data.get('users_with_info', [])

                    return {
                        "connected": len(users_with_info) > 0,
                        "count": len(users_with_info),
                        "users": users_with_info
                    }
    except Exception as e:
        print(f"Failed to check extension backend: {e}")

    # Fallback to local connections (also filter by user_id)
    users_with_cookies = []
    for uid in active_connections.keys():
        # Skip if filtering by user_id and this isn't the user
        if user_id and uid != user_id:
            continue

        user_info = {"userId": uid}
        if uid in user_cookies:
            user_info["username"] = user_cookies[uid].get("username")
            user_info["hasCookies"] = True
        users_with_cookies.append(user_info)

    return {
        "connected": len(active_connections) > 0,
        "count": len(active_connections),
        "users": users_with_cookies
    }


@app.delete("/api/extension/disconnect/{user_id}")
async def extension_disconnect(user_id: str):
    """
    Disconnect a user's X account by clearing their cookies from the extension backend.
    This proxies the request to the extension backend service.

    Args:
        user_id: Clerk user ID to disconnect
    """
    import aiohttp

    try:
        async with aiohttp.ClientSession() as session:
            url = f'{EXTENSION_BACKEND_URL}/disconnect/{user_id}'
            async with session.delete(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data
                else:
                    return {
                        "success": False,
                        "error": f"Extension backend returned status {resp.status}"
                    }
    except Exception as e:
        print(f"❌ Error calling extension disconnect: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/activity/recent/{user_id}")
async def get_recent_activity(user_id: str, limit: int = 50):
    """
    Get recent activity logs for a user from the LangGraph Store.

    This retrieves activity logs (posts, comments, likes, etc.) stored by the agent
    for display on the dashboard's "Recent Activity" section.

    Args:
        user_id: User ID to get activity for
        limit: Maximum number of activities to return (default: 50)

    Returns:
        List of activity objects sorted by timestamp (newest first)
    """
    try:
        if not store:
            return {"success": False, "error": "Store not initialized", "activities": [], "count": 0}
        from activity_logger import ActivityLogger

        # Use the global store instance (already initialized at startup)
        # Create activity logger instance
        logger = ActivityLogger(store, user_id)

        # Get recent activity
        activities = logger.get_recent_activity(limit=limit)

        return {
            "success": True,
            "activities": activities,
            "count": len(activities)
        }

    except Exception as e:
        print(f"❌ Error retrieving recent activity: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "activities": []
        }


# ============================================================================
# SOCIAL GRAPH ENDPOINTS
# ============================================================================

@app.post("/api/social-graph/validate/{user_id}")
async def validate_discovery_ready(user_id: str):
    """
    Pre-flight validation before discovery.
    Checks authentication and returns actionable errors.
    """
    try:
        import aiohttp

        # Check Extension Backend for cookies
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{EXTENSION_BACKEND_URL}/status") as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": "Extension backend not responding",
                        "action": "restart_extension_backend"
                    }

                status_data = await resp.json()

                # Find user with cookies
                user_with_cookies = None
                for user_info in status_data.get("users_with_info", []):
                    if user_info.get("hasCookies") and user_info.get("username"):
                        user_with_cookies = user_info
                        break

                if not user_with_cookies:
                    return {
                        "success": False,
                        "error": "No X account connected. Please open x.com in your browser with the extension installed.",
                        "action": "connect_extension"
                    }

                return {
                    "success": True,
                    "username": user_with_cookies.get("username"),
                    "message": "Ready to discover competitors"
                }

    except Exception as e:
        return {
            "success": False,
            "error": f"Validation failed: {str(e)}",
            "action": "check_services"
        }


@app.post("/api/social-graph/smart-discover/{user_id}")
async def smart_discover_competitors(user_id: str):
    """
    PRODUCTION-READY smart discovery with automatic fallback and validation.

    Flow:
    1. Validate authentication first
    2. Check for cached data (< 7 days old)
    3. Reuse following list if available (< 24 hours)
    4. Run optimized discovery if we have candidate pool
    5. Fall back to standard discovery if needed
    """
    try:
        from social_graph_scraper import SocialGraphBuilder
        from social_graph_scraper_v2 import OptimizedSocialGraphBuilder
        from datetime import datetime, timedelta
        import aiohttp

        # STEP 0: Check if discovery is already running (prevent duplicates)
        lock_namespace = (user_id, "discovery_lock")
        if store:
            lock_items = list(store.search(lock_namespace, limit=1))

            if lock_items and lock_items[0].value.get("running"):
                return {
                    "success": False,
                    "error": "Discovery already in progress. Please wait for it to complete.",
                    "action": "wait"
                }

            # Set lock
            store.put(lock_namespace, "lock", {"running": True, "started_at": datetime.utcnow().isoformat()})

    
        # STEP 1: Validate authentication
        print("\n" + "="*80)
        print("🎯 SMART COMPETITOR DISCOVERY")
        print("="*80 + "\n")

        print("STEP 1: Validating authentication...")

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{EXTENSION_BACKEND_URL}/status") as resp:
                if resp.status != 200:
                    return {
                        "success": False,
                        "error": "Extension backend not responding. Please restart services.",
                        "action": "restart_services"
                    }

                status_data = await resp.json()
                user_with_cookies = None

                for user_info in status_data.get("users_with_info", []):
                    if user_info.get("hasCookies") and user_info.get("username"):
                        user_with_cookies = user_info
                        break

                if not user_with_cookies:
                    return {
                        "success": False,
                        "error": "No X account connected. Please open x.com in your browser with the extension installed.",
                        "action": "connect_extension"
                    }

                user_handle = user_with_cookies.get("username")
                print(f"✅ Authenticated as @{user_handle}\n")

        # STEP 2: Check for recent cached data
        print("STEP 2: Checking for cached data...")
        builder = SocialGraphBuilder(store, user_id)
        existing_graph = builder.get_graph()

        if existing_graph:
            last_updated = existing_graph.get("last_updated")
            if last_updated:
                last_updated_dt = datetime.fromisoformat(last_updated)
                age_days = (datetime.utcnow() - last_updated_dt).days

                # Only use cache if it has valid competitor data
                num_competitors = len(existing_graph.get('all_competitors_raw', []))
                num_quality_competitors = existing_graph.get('high_quality_competitors', 0)

                if age_days < 7 and num_competitors > 0 and num_quality_competitors > 0:
                    print(f"✅ Found cached data ({age_days} days old)")
                    print(f"   - {num_competitors} competitors ({num_quality_competitors} high quality)")
                    print(f"   - Using cached data\n")

                    return {
                        "success": True,
                        "graph": existing_graph,
                        "cached": True,
                        "age_days": age_days,
                        "message": f"Using cached data from {age_days} days ago"
                    }
                elif age_days < 7 and (num_competitors == 0 or num_quality_competitors == 0):
                    print(f"⚠️ Found cached data ({age_days} days old) but it has {num_quality_competitors} high-quality competitors")
                    print(f"   - Running fresh discovery to get better results\n")

        print("❌ No recent cached data, running fresh discovery\n")

        # STEP 3: Check if we can reuse following list
        following_cached = False
        cached_following = []

        if existing_graph and "user_following" in existing_graph:
            last_updated = existing_graph.get("last_updated")
            if last_updated:
                last_updated_dt = datetime.fromisoformat(last_updated)
                age_hours = (datetime.utcnow() - last_updated_dt).total_seconds() / 3600

                if age_hours < 24 and len(existing_graph.get("user_following", [])) > 10:
                    cached_following = existing_graph["user_following"]
                    following_cached = True
                    print(f"STEP 3: Reusing following list ({int(age_hours)} hours old, {len(cached_following)} accounts)\n")

        # STEP 4: Run STANDARD discovery to build candidate pool
        print("STEP 4: Running STANDARD discovery to find candidates...\n")

        # Clear cancel flag
        cancel_namespace = (user_id, "discovery_control")
        store.put(cancel_namespace, "cancel_flag", {"cancelled": False})

        graph_data = await builder.build_graph(
            user_handle,
            max_following=200,
            analyze_count=100,  # Analyze more accounts to find better candidates
            follower_sample_size=200
        )

        # STEP 5: Return results
        print("STEP 5: Standard discovery complete\n")

        # Clear cancel flag
        cancel_namespace = (user_id, "discovery_control")
        store.put(cancel_namespace, "cancel_flag", {"cancelled": False})

        graph_data = await builder.build_graph(
            user_handle,
            max_following=200,
            analyze_count=50,
            follower_sample_size=100
        )

        return {
            "success": True,
            "graph": graph_data,
            "method": "standard",
            "message": f"Found {len(graph_data.get('top_competitors', []))} competitors"
        }

    except Exception as e:
        print(f"❌ Smart discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "action": "retry",
            "message": "Discovery failed. Please try again."
        }
    finally:
        # Release lock
        lock_namespace = (user_id, "discovery_lock")
        store.put(lock_namespace, "lock", {"running": False})


@app.post("/api/social-graph/cancel/{user_id}")
async def cancel_discovery(user_id: str):
    """Cancel ongoing discovery and save partial results"""
    try:
        # Set cancellation flag in store
        cancel_namespace = (user_id, "discovery_control")
        store.put(cancel_namespace, "cancel_flag", {"cancelled": True, "timestamp": datetime.utcnow().isoformat()})

        return {"success": True, "message": "Cancellation requested. Discovery will stop gracefully."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/social-graph/progress/{user_id}")
async def get_discovery_progress(user_id: str):
    """Get current discovery progress"""
    try:
        if not store:
            return {"success": False, "error": "Store not initialized", "progress": None}
        progress_namespace = (user_id, "discovery_progress")
        items = list(store.search(progress_namespace, limit=1))

        if items:
            progress = items[0].value
            return {
                "success": True,
                "progress": progress
            }
        else:
            return {
                "success": False,
                "progress": None
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/social-graph/discover-optimized/{user_id}")
async def discover_competitors_optimized(user_id: str, user_handle: str):
    """
    OPTIMIZED competitor discovery using direct following comparison.

    This is MUCH better than the sampling approach:
    - Directly compares following lists (not followers)
    - More accurate matches (60-90% instead of 10-30%)
    - Faster and more reliable

    Requires: Previous discovery to have run first (to get candidate pool)
    """
    try:
        from social_graph_scraper_v2 import OptimizedSocialGraphBuilder

        # Clear any previous cancel flag
        cancel_namespace = (user_id, "discovery_control")
        store.put(cancel_namespace, "cancel_flag", {"cancelled": False})

        # Initialize optimized builder
        builder = OptimizedSocialGraphBuilder(store, user_id)

        # Run optimized discovery (faster settings)
        graph_data = await builder.build_optimized_graph(
            user_handle,
            max_user_following=100,  # Reduced for speed
            candidates_to_check=10   # Only check top 10 for speed
        )

        if "error" in graph_data:
            return {
                "success": False,
                "error": graph_data["error"]
            }

        return {
            "success": True,
            "graph": graph_data,
            "message": f"✅ Found {len(graph_data['top_competitors'])} high-quality competitors"
        }

    except Exception as e:
        print(f"❌ Optimized discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Optimized discovery failed"
        }


@app.post("/api/social-graph/discover-followers/{user_id}")
async def discover_competitors_from_followers(user_id: str, user_handle: str):
    """
    FOLLOWER-BASED competitor discovery - analyzes YOUR followers instead of who you follow.

    This is the BEST method because:
    - YOUR followers are already interested in your niche
    - Much faster (2-3 minutes vs 10 minutes)
    - Better quality matches (peers, not one-way celebrity follows)
    - Higher overlap percentages (30-60% vs 5-15%)

    Algorithm:
    1. Get YOUR followers list
    2. Filter for peer accounts (500-10K followers)
    3. Compare their following with yours
    4. High overlap = true competitor
    """
    try:
        from follower_based_discovery import FollowerBasedDiscovery

        print(f"🎯 Starting FOLLOWER-BASED discovery for @{user_handle}")

        # Get per-user VNC client (enables multi-user scaling)
        user_client = await get_user_vnc_client(user_id)
        print(f"✅ Using per-user VNC session for competitor discovery")

        # Check if discovery is already running (only if store is available)
        lock_namespace = (user_id, "discovery_lock")
        if store:
            lock_items = list(store.search(lock_namespace, limit=1))
            if lock_items and lock_items[0].value.get("running"):
                return {
                    "success": False,
                    "error": "Discovery already in progress. Please wait for it to complete.",
                    "action": "wait"
                }
            # Set lock
            store.put(lock_namespace, "lock", {"running": True, "started_at": datetime.utcnow().isoformat()})

        try:
            # Clear cancel flag (only if store is available)
            if store:
                cancel_namespace = (user_id, "discovery_control")
                store.put(cancel_namespace, "cancel_flag", {"cancelled": False})

            # Initialize follower-based discovery with per-user client
            discovery = FollowerBasedDiscovery(user_client, store, user_id)

            # Run discovery with increased limits to get all 912 following
            graph_data = await discovery.discover_competitors(
                user_handle,
                max_followers_to_check=50,  # Analyze 50 of your followers
                min_follower_count=500,     # Filter for peers with 500+ followers
                max_follower_count=10000,   # Up to 10K followers
                max_user_following=1000     # Increased to 1000 to get all your following
            )

            return {
                "success": True,
                "graph": graph_data,
                "method": "follower_based",
                "message": f"✅ Found {graph_data['high_quality_competitors']} high-quality competitors (30%+ overlap)"
            }

        finally:
            # Release lock (only if store is available)
            if store:
                store.put(lock_namespace, "lock", {"running": False})

    except Exception as e:
        print(f"❌ Follower-based discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Follower-based discovery failed"
        }


@app.post("/api/social-graph/discover-native/{user_id}")
async def discover_competitors_native(user_id: str, user_handle: str):
    """
    X NATIVE competitor discovery - uses X's "Followed by" feature.

    This is the FASTEST method:
    - Reads X's native "Followed by @user1 and 5 others you follow" text
    - No need to scrape full following lists
    - ~2 seconds per account vs ~20 seconds
    - Directly shows mutual connections count

    This leverages X's own algorithm!
    """
    try:
        from x_native_common_followers import XNativeCommonFollowersDiscovery

        print(f"⚡ Starting X NATIVE discovery for @{user_handle}")

        # Get per-user VNC client (enables multi-user scaling)
        user_client = await get_user_vnc_client(user_id)
        print(f"✅ Using per-user VNC session for X Native discovery")

        # Warm up the VNC service (handles cold start - can take 30+ seconds)
        print(f"🔥 Warming up VNC service (cold start may take 30+ seconds)...")
        warmup_result = await user_client._request("GET", "/status", timeout=60)
        if warmup_result.get("error"):
            print(f"⚠️ VNC warmup failed: {warmup_result.get('error')}")
            # Try one more time with longer timeout
            print(f"🔄 Retrying VNC warmup...")
            warmup_result = await user_client._request("GET", "/status", timeout=90)
            if warmup_result.get("error"):
                return {
                    "success": False,
                    "error": f"VNC service not responding. Please try again in a minute. Error: {warmup_result.get('error')}",
                    "action": "retry"
                }
        print(f"✅ VNC service is warm and ready")

        # Check if discovery is already running (only if store is available)
        lock_namespace = (user_id, "discovery_lock")
        if store:
            lock_items = list(store.search(lock_namespace, limit=1))
            if lock_items and lock_items[0].value.get("running"):
                return {
                    "success": False,
                    "error": "Discovery already in progress. Please wait for it to complete.",
                    "action": "wait"
                }
            # Set lock
            store.put(lock_namespace, "lock", {"running": True, "started_at": datetime.utcnow().isoformat()})

        try:
            # Clear cancel flag (only if store is available)
            if store:
                cancel_namespace = (user_id, "discovery_control")
                store.put(cancel_namespace, "cancel_flag", {"cancelled": False})

            # Initialize X native discovery with per-user client
            discovery = XNativeCommonFollowersDiscovery(user_client, store, user_id)

            # Run ultra-fast discovery
            graph_data = await discovery.discover_competitors_fast(
                user_handle,
                max_followers_to_check=100  # Check 100 of your followers
            )

            return {
                "success": True,
                "graph": graph_data,
                "method": "x_native",
                "message": f"✅ Found {graph_data['high_quality_competitors']} high-quality competitors (5+ mutual connections)"
            }

        finally:
            # Release lock (only if store is available)
            if store:
                store.put(lock_namespace, "lock", {"running": False})

    except Exception as e:
        print(f"❌ X Native discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "X Native discovery failed"
        }


@app.post("/api/social-graph/discover/{user_id}")
async def discover_competitors(user_id: str, user_handle: str):
    """Standard competitor discovery with cancellation support"""

    # Clear any previous cancel flag
    cancel_namespace = (user_id, "discovery_control")
    store.put(cancel_namespace, "cancel_flag", {"cancelled": False})
    """
    Discover competitors by building social graph.

    This is a LONG-RUNNING operation (5-10 minutes).
    In production, should be run as background task.

    Args:
        user_id: User identifier
        user_handle: Twitter/X handle (without @)

    Returns:
        Graph data with competitor rankings
    """
    try:
        from social_graph_scraper import SocialGraphBuilder

        print(f"🕸️ Starting competitor discovery for @{user_handle} (user: {user_id})")

        # Check if user has cookies injected (check extension backend)
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{EXTENSION_BACKEND_URL}/status") as resp:
                status_data = await resp.json()
                user_with_cookies = None
                for user_info in status_data.get("users_with_info", []):
                    if user_info.get("hasCookies") and user_info.get("username"):
                        user_with_cookies = user_info
                        break

                if not user_with_cookies:
                    return {
                        "success": False,
                        "error": "No X account connected. Please connect your X account via the Chrome extension first.",
                        "message": "❌ Please inject your X cookies before discovery"
                    }

                print(f"✅ Cookies found for user: {user_with_cookies['username']}")

        # Initialize builder with global store
        builder = SocialGraphBuilder(store, user_id)

        # Build the graph (this takes time!)
        # INCREASED SCALE for 80%+ accuracy threshold
        graph_data = await builder.build_graph(
            user_handle,
            max_following=200,       # Scrape up to 200 accounts you follow
            analyze_count=50,        # Analyze 50 of those deeply
            follower_sample_size=100 # Sample 100 followers per account = 5000 total samples!
        )

        return {
            "success": True,
            "graph": graph_data,
            "message": f"✅ Discovered {len(graph_data['top_competitors'])} competitors"
        }

    except Exception as e:
        print(f"❌ Competitor discovery failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to discover competitors"
        }


@app.post("/api/social-graph/analyze-content/{user_id}")
async def analyze_competitor_content(user_id: str):
    """
    Scrape and analyze content from discovered competitors.
    This adds topic clustering to the social graph.

    Args:
        user_id: User identifier

    Returns:
        Content analysis results with clusters
    """
    try:
        from competitor_content_analyzer import analyze_all_competitors

        # Get per-user VNC client
        user_client = await get_user_vnc_client(user_id)

        # Run content analysis with per-user client
        result = await analyze_all_competitors(
            user_id,
            store,
            user_client
        )

        return result

    except Exception as e:
        print(f"❌ Content analysis failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to analyze competitor content"
        }


@app.post("/api/social-graph/scrape-posts/{user_id}")
async def scrape_competitor_posts(
    user_id: str,
    force_rescrape: bool = Query(False),
    request: Request = None
):
    """
    Scrape posts for all competitors that don't have posts yet.

    Args:
        user_id: User identifier
        force_rescrape: If True, re-scrape all competitors even if they have posts
        request: Optional request body with filtered_usernames

    Returns:
        Updated graph with posts scraped
    """
    try:
        print(f"🔍 force_rescrape parameter value: {force_rescrape}")

        # Check if we have a request body with filtered usernames
        filtered_usernames = None
        if request:
            try:
                body = await request.json()
                print(f"📦 Request body received: {body}")
                filtered_usernames = body.get("filtered_usernames")
                if filtered_usernames:
                    print(f"🎯 Filtered scraping for {len(filtered_usernames)} specific users: {filtered_usernames[:5]}...")
                else:
                    print(f"⚠️ No filtered_usernames in body")
            except Exception as e:
                print(f"⚠️ Failed to parse request body: {e}")
                pass  # No body or invalid JSON, continue normally

        from social_graph_scraper import SocialGraphBuilder, SocialGraphScraper

        # Get per-user VNC client (enables multi-user scaling)
        user_client = await get_user_vnc_client(user_id)

        # Check if scraping is already in progress (prevent concurrent scraping)
        progress_namespace = (user_id, "discovery_progress")
        existing_progress = store.get(progress_namespace, "current")
        if existing_progress and existing_progress.value.get("stage") == "scraping_posts":
            print("⚠️ Scraping already in progress, ignoring duplicate request")
            return {
                "success": False,
                "error": "Scraping is already in progress. Please wait for it to complete."
            }

        builder = SocialGraphBuilder(store, user_id)
        graph = builder.get_graph()

        if not graph:
            return {
                "success": False,
                "error": "No graph data found. Run discovery first."
            }

        # Get all competitors (from raw data)
        all_competitors = graph.get("all_competitors_raw", [])

        if not all_competitors:
            return {
                "success": False,
                "error": "No competitors found"
            }

        # If filtered usernames provided, only scrape those
        if filtered_usernames:
            top_competitors = [c for c in all_competitors if c['username'] in filtered_usernames]
            print(f"📝 Scraping {len(top_competitors)} filtered competitors")
        else:
            # Sort by overlap and take top 20 to avoid scraping for hours
            top_competitors = sorted(
                all_competitors,
                key=lambda x: x['overlap_percentage'],
                reverse=True
            )[:20]

        # Initialize scraper with per-user client
        scraper = SocialGraphScraper(user_client)

        # Scrape posts for competitors that don't have them
        scraped_count = 0
        progress_namespace = (user_id, "discovery_progress")
        total_to_scrape = len(top_competitors) if force_rescrape else len([c for c in top_competitors if not (c.get("posts") and len(c.get("posts", [])) > 0)])
        current_index = 0

        for comp in top_competitors:
            # Skip if already has posts (unless force_rescrape)
            if not force_rescrape and comp.get("posts") and len(comp.get("posts", [])) > 0:
                continue

            current_index += 1

            # Update progress
            builder.store.put(progress_namespace, "current", {
                "current": current_index,
                "total": total_to_scrape,
                "current_account": comp['username'],
                "status": "scraping_posts",
                "stage": "scraping_posts",
                "posts_scraped": scraped_count
            })

            print(f"📝 Scraping posts for @{comp['username']}...")

            try:
                posts, follower_count = await scraper.scrape_competitor_posts(
                    comp['username'],
                    max_posts=30
                )

                comp['posts'] = posts
                comp['post_count'] = len(posts)
                comp['follower_count'] = follower_count  # Store follower count!
                scraped_count += 1

                # Update progress with post count
                builder.store.put(progress_namespace, "current", {
                    "current": current_index,
                    "total": total_to_scrape,
                    "current_account": comp['username'],
                    "status": "scraping_posts",
                    "stage": "scraping_posts",
                    "posts_scraped": scraped_count,
                    "last_scraped_count": len(posts)
                })

                # Rate limit
                await asyncio.sleep(3)

            except Exception as e:
                print(f"   ⚠️ Failed: {e}")
                comp['posts'] = []
                comp['post_count'] = 0

        # Update the full competitors list with scraped posts
        # Create a lookup for faster updates
        posts_lookup = {c['username']: c for c in top_competitors if c.get('posts')}

        for comp in all_competitors:
            if comp['username'] in posts_lookup:
                comp['posts'] = posts_lookup[comp['username']]['posts']
                comp['post_count'] = posts_lookup[comp['username']]['post_count']
                comp['follower_count'] = posts_lookup[comp['username']].get('follower_count', 0)

        # Update graph in database
        graph['all_competitors_raw'] = all_competitors
        graph['last_updated'] = datetime.utcnow().isoformat()

        builder.store.put(
            builder.namespace_graph,
            "latest",
            graph
        )

        return {
            "success": True,
            "graph": graph,
            "message": f"✅ Scraped posts for {scraped_count} competitors"
        }

    except Exception as e:
        print(f"❌ Post scraping failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/social-graph/refilter/{user_id}")
async def refilter_competitors(user_id: str, min_threshold: int = 50):
    """
    Re-filter existing graph data with a new threshold.
    No re-scraping needed!

    Args:
        user_id: User identifier
        min_threshold: Minimum overlap percentage (default 50)

    Returns:
        Re-filtered competitor list
    """
    try:
        from social_graph_scraper import SocialGraphBuilder

        builder = SocialGraphBuilder(store, user_id)
        graph = builder.get_graph()

        if not graph:
            return {
                "success": False,
                "error": "No graph data found. Run discovery first."
            }

        # Check if we have raw data
        if "all_competitors_raw" not in graph:
            return {
                "success": False,
                "error": "Old graph format. Please re-run discovery to enable re-filtering."
            }

        # Re-filter with new threshold
        raw_competitors = graph["all_competitors_raw"]
        filtered = [c for c in raw_competitors if c["overlap_percentage"] >= min_threshold]

        # Update graph data
        graph["top_competitors"] = filtered
        graph["high_quality_competitors"] = len(filtered)
        graph["config"]["min_overlap_threshold"] = min_threshold
        graph["last_updated"] = datetime.utcnow().isoformat()

        # Save updated graph
        builder.store.put(
            builder.namespace_graph,
            "latest",
            graph
        )

        return {
            "success": True,
            "graph": graph,
            "message": f"✅ Re-filtered to {len(filtered)} competitors at {min_threshold}%+ threshold"
        }

    except Exception as e:
        print(f"❌ Re-filter failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/social-graph/insights/{user_id}")
async def generate_content_insights(user_id: str):
    """
    Analyze competitor posts to extract patterns and generate content suggestions.

    Uses AI to:
    - Extract high-performing posts
    - Identify topics, hooks, and engagement patterns
    - Generate personalized content suggestions
    - Calculate engagement benchmarks

    Args:
        user_id: User identifier

    Returns:
        Content insights with patterns, suggestions, and benchmarks
    """
    try:
        from content_insights_analyzer import ContentInsightsAnalyzer
        from social_graph_scraper import SocialGraphBuilder

        # Get graph data
        builder = SocialGraphBuilder(store, user_id)
        graph = builder.get_graph()

        if not graph:
            return {
                "success": False,
                "error": "No graph data found. Run discovery first."
            }

        # Get competitors data
        competitors = graph.get('all_competitors_raw', [])

        if not competitors:
            return {
                "success": False,
                "error": "No competitors found. Run discovery first."
            }

        # Get user handle from cookies or default
        user_handle = user_cookies.get(user_id, {}).get("username", "User")

        print(f"🧠 Analyzing content insights for @{user_handle}...")

        # Run content insights analysis
        analyzer = ContentInsightsAnalyzer()
        insights_result = await analyzer.analyze_competitor_content(
            competitors,
            user_handle
        )

        # Store insights in database
        if insights_result.get('success'):
            insights_namespace = (user_id, "content_insights")
            store.put(
                insights_namespace,
                "latest",
                insights_result['insights']
            )
            print(f"✅ Content insights generated and stored")

        return insights_result

    except Exception as e:
        print(f"❌ Content insights failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/social-graph/insights/{user_id}")
async def get_content_insights(user_id: str):
    """
    Get cached content insights if available.

    Args:
        user_id: User identifier

    Returns:
        Cached content insights or null
    """
    try:
        if not store:
            return {"success": False, "insights": None, "error": "Store not initialized"}
        insights_namespace = (user_id, "content_insights")
        items = list(store.search(insights_namespace, limit=1))

        if not items:
            return {
                "success": False,
                "insights": None,
                "message": "No insights found. Generate insights first."
            }

        return {
            "success": True,
            "insights": items[0].value
        }

    except Exception as e:
        print(f"❌ Failed to get insights: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/social-graph/calculate-relevancy/{user_id}")
async def calculate_relevancy_scores(
    user_id: str,
    user_handle: str,
    batch_size: int = 20,
    overlap_weight: float = 0.4,
    relevancy_weight: float = 0.6
):
    """
    Calculate relevancy scores for competitors with smart batching.

    Args:
        user_id: User identifier
        user_handle: User's X handle
        batch_size: Number of competitors to analyze in this batch (default 20)
        overlap_weight: Weight for overlap percentage (default 0.4)
        relevancy_weight: Weight for relevancy score (default 0.6)

    Returns:
        Updated graph data with relevancy_score, quality_score, and progress info
    """
    try:
        from competitor_relevancy_scorer import add_relevancy_scores
        from social_graph_scraper import SocialGraphBuilder

        print(f"\n🎯 Calculating relevancy scores for @{user_handle} (batch size: {batch_size})...")

        # Get per-user VNC client (enables multi-user scaling)
        user_client = await get_user_vnc_client(user_id)

        # Get existing graph data
        builder = SocialGraphBuilder(store, user_id)
        graph_data = builder.get_graph()

        if not graph_data:
            return {
                "success": False,
                "error": "No graph data found. Run discovery first.",
                "message": "Please discover competitors before calculating relevancy."
            }

        # Calculate relevancy scores with batching using per-user client
        updated_graph = await add_relevancy_scores(
            user_client,
            user_handle,
            graph_data,
            user_id=user_id,
            store=store,
            batch_size=batch_size,
            overlap_weight=overlap_weight,
            relevancy_weight=relevancy_weight
        )

        # Save updated graph to store
        graph_namespace = (user_id, "social_graph")
        store.put(graph_namespace, "graph_data", updated_graph)

        # Get progress info
        analysis_info = updated_graph.get("relevancy_analysis", {})
        analyzed_count = analysis_info.get("analyzed_count", 0)
        total_count = analysis_info.get("total_count", 0)
        has_more = analysis_info.get("has_more", False)
        batch_analyzed = analysis_info.get("batch_analyzed", 0)

        # Count high quality competitors (quality_score >= 60)
        high_quality = [c for c in updated_graph.get("all_competitors_raw", []) if c.get("quality_score", 0) >= 60]

        message = f"✅ Analyzed {batch_analyzed} competitors this batch. "
        message += f"Progress: {analyzed_count}/{total_count} total. "
        message += f"Found {len(high_quality)} high-quality matches."
        if has_more:
            message += f" ({total_count - analyzed_count} remaining)"

        return {
            "success": True,
            "graph": updated_graph,
            "message": message,
            "progress": {
                "analyzed_count": analyzed_count,
                "total_count": total_count,
                "has_more": has_more,
                "batch_analyzed": batch_analyzed,
                "high_quality_count": len(high_quality)
            }
        }

    except Exception as e:
        print(f"❌ Failed to calculate relevancy scores: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to calculate relevancy scores"
        }


@app.post("/api/social-graph/reset-relevancy/{user_id}")
async def reset_relevancy_analysis(user_id: str):
    """Reset relevancy analysis state to re-analyze all competitors from scratch"""
    try:
        from competitor_relevancy_scorer import CompetitorRelevancyScorer

        print(f"\n🔄 Resetting relevancy analysis state for user: {user_id}")

        # Clear the analysis state
        scorer = CompetitorRelevancyScorer(None, store=store)
        scorer.save_analysis_state(user_id, [], 0)

        print(f"✅ Reset complete! All competitors can now be re-analyzed.")

        return {
            "success": True,
            "message": "Relevancy analysis state reset successfully. You can now re-analyze all competitors."
        }

    except Exception as e:
        print(f"❌ Error resetting relevancy analysis: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to reset relevancy analysis state"
        }


@app.get("/api/social-graph/{user_id}")
async def get_social_graph(user_id: str):
    """
    Get the stored social graph for a user.

    Args:
        user_id: User identifier

    Returns:
        Latest social graph data from PostgreSQL
    """
    try:
        if not store:
            return {"success": False, "error": "Store not initialized", "graph": None, "has_data": False}
        from social_graph_scraper import SocialGraphBuilder

        # Initialize builder
        builder = SocialGraphBuilder(store, user_id)

        # Get from database
        graph = builder.get_graph()

        if graph:
            return {
                "success": True,
                "graph": graph,
                "has_data": True
            }
        else:
            return {
                "success": True,
                "graph": None,
                "has_data": False,
                "message": "No graph found. Run discovery first."
            }

    except Exception as e:
        print(f"❌ Failed to get social graph: {e}")
        return {
            "success": False,
            "error": str(e)
        }


@app.get("/api/competitors/{user_id}")
async def list_competitors(user_id: str, limit: int = 50):
    """
    List all discovered competitors for a user.

    Args:
        user_id: User identifier
        limit: Max competitors to return

    Returns:
        List of competitor profiles from PostgreSQL
    """
    try:
        from social_graph_scraper import SocialGraphBuilder

        builder = SocialGraphBuilder(store, user_id)
        competitors = builder.list_competitors(limit=limit)

        return {
            "success": True,
            "competitors": competitors,
            "count": len(competitors)
        }

    except Exception as e:
        print(f"❌ Failed to list competitors: {e}")
        return {
            "success": False,
            "error": str(e),
            "competitors": []
        }


@app.get("/api/competitor/{user_id}/{username}")
async def get_competitor(user_id: str, username: str):
    """
    Get details for a specific competitor.

    Args:
        user_id: User identifier
        username: Competitor's Twitter handle (without @)

    Returns:
        Competitor profile from PostgreSQL
    """
    try:
        from social_graph_scraper import SocialGraphBuilder

        builder = SocialGraphBuilder(store, user_id)
        competitor = builder.get_competitor(username)

        if competitor:
            return {
                "success": True,
                "competitor": competitor
            }
        else:
            return {
                "success": False,
                "message": f"Competitor @{username} not found"
            }

    except Exception as e:
        print(f"❌ Failed to get competitor: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# ============================================================================
# ACTIVITY TRACKING ENDPOINTS
# ============================================================================

@app.websocket("/ws/activity/{user_id}")
async def activity_websocket(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for real-time activity streaming.

    This endpoint:
    1. Accepts WebSocket connection
    2. Streams agent execution with custom events enabled
    3. Captures activity events and saves to Store
    4. Forwards activity events to frontend in real-time
    """
    await websocket.accept()
    print(f"📡 Activity WebSocket connected for user: {user_id}")

    try:
        # Initialize activity capture with global store
        from activity_tracking_streaming import StreamActivityCapture
        activity_capture = StreamActivityCapture(store, user_id)

        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for messages from client (could be tasks to run)
                data = await asyncio.wait_for(websocket.receive_json(), timeout=300.0)

                if data.get("type") == "ping":
                    # Respond to ping
                    await websocket.send_json({"type": "pong"})
                    continue

                if data.get("type") == "run_agent":
                    # Run agent and stream activity
                    task = data.get("task")
                    if not task:
                        continue

                    # Get user's VNC session URL for the agent to use
                    vnc_url = None
                    try:
                        vnc_manager = await get_vnc_manager()
                        if vnc_manager:
                            vnc_session = await vnc_manager.get_session(user_id)
                            if vnc_session:
                                vnc_url = vnc_session.get("https_url") or vnc_session.get("service_url")
                                print(f"🖥️ Activity WS: Using VNC URL for agent: {vnc_url}")
                    except Exception as e:
                        print(f"⚠️ Activity WS: Could not get VNC session for agent: {e}")

                    # Create thread
                    client = get_client(url=LANGGRAPH_URL)
                    thread = await client.threads.create()
                    thread_id = thread["thread_id"]

                    # Stream with CUSTOM mode enabled for activity events
                    async for chunk in client.runs.stream(
                        thread_id,
                        "x_growth_deep_agent",
                        input={"messages": [{"role": "user", "content": task}]},
                        config={"configurable": {"user_id": user_id, "cua_url": vnc_url}},
                        stream_mode=["messages", "custom"]  # Enable custom events!
                    ):
                        # Capture and forward activity events
                        if chunk.event == "custom":
                            event_data = chunk.data

                            # Save to Store
                            if activity_capture:
                                await activity_capture.handle_event(event_data)

                            # Forward to frontend in real-time
                            await websocket.send_json({
                                "type": "activity",
                                "data": event_data
                            })

                        # Also stream messages
                        if chunk.event == "messages":
                            await websocket.send_json({
                                "type": "message",
                                "data": chunk.data
                            })

            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "keepalive"})
                except:
                    break
            except WebSocketDisconnect:
                break

    except WebSocketDisconnect:
        print(f"📡 Activity WebSocket disconnected for user: {user_id}")
    except Exception as e:
        print(f"❌ Activity WebSocket error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        try:
            await websocket.close()
        except:
            pass

async def _inject_cookies_internal(extension_user_id: str, clerk_user_id: str) -> dict:
    """
    Internal helper to inject cookies into a user's VNC session.
    This can be called both from HTTP endpoints and internal functions.
    """
    import aiohttp

    print(f"🔐 Clerk user: {clerk_user_id}, Extension user: {extension_user_id}")

    # Get the user's VNC session from Redis
    vnc_manager = await get_vnc_manager()
    vnc_session = await vnc_manager.get_session(clerk_user_id)

    if not vnc_session or not vnc_session.get("https_url"):
        print(f"❌ No VNC session found for Clerk user {clerk_user_id}")
        return {"success": False, "error": "No VNC session found. Please load the VNC viewer first."}

    vnc_service_url = vnc_session.get("https_url")
    print(f"✅ Found VNC session at: {vnc_service_url}")

    # Fetch cookies from extension backend
    cookie_data = None
    print(f"🔍 Looking for cookies for extension user: {extension_user_id}")

    if extension_user_id not in user_cookies:
        # Fetch from extension backend
        print(f"   Fetching from extension backend...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'{EXTENSION_BACKEND_URL}/cookies/{extension_user_id}', timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    print(f"   Extension backend response status: {resp.status}")
                    if resp.status == 200:
                        ext_data = await resp.json()
                        print(f"   Extension backend data: {ext_data.get('success')}, username: {ext_data.get('username')}")
                        if ext_data.get('success'):
                            # Got cookies from extension backend!
                            cookie_data = {
                                "username": ext_data.get("username"),
                                "cookies": ext_data.get("cookies", []),
                                "timestamp": ext_data.get("timestamp")
                            }
                            print(f"✅ Fetched {len(cookie_data['cookies'])} cookies from extension backend for @{cookie_data['username']}")
                    else:
                        print(f"   ❌ Extension backend returned {resp.status}")
        except Exception as e:
            print(f"❌ Failed to fetch from extension backend: {e}")
            import traceback
            traceback.print_exc()

        if not cookie_data:
            print(f"❌ No cookie data found for {extension_user_id}")
            return {"success": False, "error": "No cookies found for this user"}
    else:
        cookie_data = user_cookies[extension_user_id]

    if not cookie_data:
        return {"success": False, "error": "No cookies found for this user"}

    cookies = cookie_data["cookies"]
    username = cookie_data["username"]

    try:
        # Convert Chrome cookies to Playwright format
        playwright_cookies = []
        for cookie in cookies:
            # Handle expiration - Chrome uses expirationDate, Playwright uses expires
            expires_value = cookie.get("expirationDate", -1)
            if expires_value and expires_value != -1:
                # Convert to integer timestamp
                expires_value = int(expires_value)
            else:
                expires_value = -1

            # Handle sameSite - must be exactly "Strict", "Lax", or "None"
            same_site = cookie.get("sameSite", "lax")
            if same_site:
                same_site_lower = same_site.lower()
                if same_site_lower == "strict":
                    same_site = "Strict"
                elif same_site_lower == "lax":
                    same_site = "Lax"
                elif same_site_lower == "none":
                    same_site = "None"
                elif same_site_lower == "no_restriction":
                    same_site = "None"
                else:
                    same_site = "Lax"  # Default fallback
            else:
                same_site = "Lax"

            pw_cookie = {
                "name": cookie["name"],
                "value": cookie["value"],
                "domain": cookie["domain"],
                "path": cookie.get("path", "/"),
                "expires": expires_value,
                "httpOnly": cookie.get("httpOnly", False),
                "secure": cookie.get("secure", False),
                "sameSite": same_site
            }
            playwright_cookies.append(pw_cookie)

        print(f"🔄 Converted {len(playwright_cookies)} cookies to Playwright format")

        # Call the user's VNC service to inject cookies
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{vnc_service_url}/session/load",
                json={"cookies": playwright_cookies},
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                result = await response.json()

                if result.get("success"):
                    print(f"✅ Injected cookies into VNC session for @{username}")
                    return {
                        "success": True,
                        "message": f"Session loaded for @{username}",
                        "logged_in": result.get("logged_in"),
                        "username": result.get("username"),
                        "vnc_url": vnc_service_url  # Return the user's VNC URL for subsequent operations
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("error", "Failed to load session")
                    }
    except Exception as e:
        print(f"❌ Error injecting cookies: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


@app.post("/api/inject-cookies-to-docker")
async def inject_cookies_to_docker(
    request: dict,
    clerk_user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Inject user's X cookies into their per-user VNC browser session.

    Request: {"user_id": "extension_user_xxx"}  - Extension user ID (has the cookies)

    This endpoint:
    1. Gets the Clerk user's VNC session from Redis
    2. Fetches cookies using the extension user ID
    3. Injects cookies into the user's VNC session
    """
    extension_user_id = request.get("user_id")
    if not extension_user_id:
        return {"success": False, "error": "user_id required"}

    return await _inject_cookies_internal(extension_user_id, clerk_user_id)


@app.websocket("/ws/extension/{user_id}")
async def extension_websocket(websocket: WebSocket, user_id: str):
    """WebSocket endpoint for Chrome extension"""
    
    await websocket.accept()
    active_connections[user_id] = websocket
    
    print(f"✅ Extension connected: {user_id}")
    print(f"📊 Total connections: {len(active_connections)}")
    
    try:
        # Send welcome message
        await websocket.send_json({
            "type": "CONNECTED",
            "message": "Successfully connected to backend!",
            "userId": user_id
        })
        
        # Listen for messages from extension
        while True:
            data = await websocket.receive_json()
            print(f"📨 Received from extension ({user_id}):", data)
            
            # Handle different message types
            if data.get("type") == "LOGIN_STATUS":
                print(f"👤 User logged in as: @{data.get('username')}")
                
                # You can store this in database
                # await db.update_user_x_account(user_id, data.get('username'))
            
            elif data.get("type") == "COOKIES_CAPTURED":
                # Extension sent X cookies!
                username = data.get("username")
                cookies = data.get("cookies", [])
                print(f"🍪 Received {len(cookies)} cookies from @{username}")
                
                # Store cookies (in production: encrypt and save to database)
                user_cookies[user_id] = {
                    "username": username,
                    "cookies": cookies,
                    "timestamp": data.get("timestamp")
                }
                
                # Acknowledge receipt
                await websocket.send_json({
                    "type": "COOKIES_RECEIVED",
                    "message": f"Stored {len(cookies)} cookies for @{username}"
                })
                
                print(f"✅ Cookies stored for {user_id} (@{username})")
            
            elif data.get("type") == "ACTION_RESULT":
                print(f"✅ Action completed: {data.get('action')}")
                # Forward result to your LangGraph agent or store in DB
            
            elif data.get("type") == "SCRAPE_USER_POSTS":
                # Dashboard wants to scrape posts - forward to extension
                print(f"📝 Scraping {data.get('targetCount', 50)} posts for {user_id}")
                await websocket.send_json({
                    "type": "SCRAPE_POSTS_REQUEST",
                    "targetCount": data.get('targetCount', 50)
                })
            
            elif data.get("type") == "POSTS_SCRAPED":
                # Extension scraped posts - store them
                posts = data.get("posts", [])
                print(f"✅ Received {len(posts)} scraped posts")
                
                # Store posts
                if user_id not in user_posts:
                    user_posts[user_id] = []
                user_posts[user_id].extend(posts)
                
                # Send success back to dashboard
                await websocket.send_json({
                    "type": "IMPORT_COMPLETE",
                    "imported": len(posts),
                    "total": len(user_posts[user_id])
                })
            
            # Echo back for now
            await websocket.send_json({
                "type": "ACK",
                "message": "Message received",
                "data": data
            })
            
    except WebSocketDisconnect:
        print(f"❌ Extension disconnected: {user_id}")
        if user_id in active_connections:
            del active_connections[user_id]
        print(f"📊 Total connections: {len(active_connections)}")
    except Exception as e:
        print(f"⚠️ Error with {user_id}: {e}")
        if user_id in active_connections:
            del active_connections[user_id]

@app.post("/api/scrape-posts-docker")
async def scrape_posts_docker(data: dict):
    """
    Use Docker VNC browser to scrape user's X posts (doesn't disturb user)
    Optimized: Only scrapes if new posts are available
    """
    import aiohttp
    
    user_id = data.get("user_id", "default_user")  # Extension/Docker user ID
    clerk_user_id = data.get("clerk_user_id", user_id)  # Clerk user ID for WebSocket and Store
    target_count = data.get("targetCount", 50)
    min_posts_threshold = 30  # Minimum posts we want to have
    
    print(f"🔍 Scraping for extension user_id: {user_id}")
    print(f"📡 WebSocket/Store user_id (Clerk): {clerk_user_id}")
    print(f"📊 Active WebSocket connections: {list(active_connections.keys())}")
    
    # Check existing posts in store using CLERK user ID (consistent with where posts are saved)
    try:
        namespace = (clerk_user_id, "writing_samples")
        existing_items = store.search(namespace)
        existing_posts = [item.value for item in existing_items]
        existing_count = len(existing_posts)
        
        print(f"📚 Found {existing_count} existing posts in store")
        
        # If we have enough posts, check if we need to update
        if existing_count >= min_posts_threshold:
            # Get the most recent post (by timestamp)
            if existing_posts:
                sorted_posts = sorted(
                    existing_posts, 
                    key=lambda x: x.get('timestamp', ''), 
                    reverse=True
                )
                most_recent_post = sorted_posts[0]
                most_recent_content = most_recent_post.get('content', '')[:100]
                
                print(f"🔍 Most recent stored post: {most_recent_content}...")
                print(f"   Will check if new posts exist by comparing first post only")
                
                # Only scrape 1 post to check if it's new
                # If the first post matches our most recent, we're up to date
                target_count = 1  # Only check the very first post
                print(f"   📉 Reduced target to {target_count} for quick update check")
        else:
            print(f"⚠️ Only {existing_count} posts (< {min_posts_threshold}), will do full scrape")
            
    except Exception as e:
        print(f"⚠️ Error checking existing posts: {e}")
        existing_count = 0
        existing_posts = []  # Initialize to empty list to avoid UnboundLocalError
    
    try:
        # Get username AND user_id with cookies from extension backend
        username = None
        extension_user_id = None
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{EXTENSION_BACKEND_URL}/status") as resp:
                    status_data = await resp.json()
                    if status_data.get("users_with_info"):
                        for user_info in status_data["users_with_info"]:
                            if user_info.get("username") and user_info.get("hasCookies"):
                                username = user_info["username"]
                                extension_user_id = user_info["userId"]
                                print(f"✅ Found user with cookies: {extension_user_id} (@{username})")
                                break
            except Exception as e:
                print(f"⚠️ Could not fetch username from extension backend: {e}")
        
        if not username or not extension_user_id:
            return {
                "success": False,
                "error": "No X account connected. Please connect your X account first."
            }
        
        print(f"📝 Scraping posts for @{username} using Docker VNC browser...")
        
        # Inject cookies into Docker browser using the CORRECT user_id (the one with cookies)
        print(f"🍪 Injecting cookies into Docker browser for user {extension_user_id}...")
        inject_result = await _inject_cookies_internal(extension_user_id, clerk_user_id)
        if not inject_result.get("success"):
            print(f"⚠️ Cookie injection failed: {inject_result.get('error')}")
            return {
                "success": False,
                "error": f"Cookie injection failed: {inject_result.get('error')}"
            }
        
        print(f"✅ Docker browser is now logged in as @{username}")

        # Get the user's VNC URL from the inject result (per-user, not hardcoded!)
        vnc_url = inject_result.get("vnc_url")
        if not vnc_url:
            return {"success": False, "error": "No VNC URL returned from cookie injection"}
        print(f"🔗 Using per-user VNC URL: {vnc_url}")

        # Navigate to user's profile
        # Create new session for each request to avoid connection reuse issues
        async with aiohttp.ClientSession() as session:
            profile_url = f"https://x.com/{username}"
            print(f"🌐 Navigating to {profile_url}...")

            async with session.post(
                f"{vnc_url}/navigate",
                json={"url": profile_url}
            ) as resp:
                nav_result = await resp.json()
                if not nav_result.get("success"):
                    return {"success": False, "error": "Failed to navigate to profile"}
            
            # Wait for page to load
            print(f"⏳ Waiting for page to load...")
            await asyncio.sleep(5)
        
        # Smart scrolling - keep scrolling until we have target posts or no new posts
        print(f"📜 Scrolling to load posts (target: {target_count})...")
        
        # Collect unique posts progressively
        collected_posts = {}  # Use dict to deduplicate by content
        # Dynamic max scrolls based on target (roughly 5 posts per scroll)
        max_scrolls = min(30, (target_count // 3) + 5)  # Cap at 30 scrolls for safety
        print(f"   Max scrolls: {max_scrolls}")
        
        # Track if we're stuck (no new posts for multiple scrolls)
        last_count = 0
        no_new_posts_count = 0
        
        # Create fresh session for scraping to avoid connection issues
        async with aiohttp.ClientSession() as scrape_session:
            for i in range(max_scrolls):
                try:
                    # Check for X.com's "Something went wrong" error and auto-retry
                    retry_check_script = """
                    (() => {
                        const retryButton = document.querySelector('[role="button"]');
                        const errorText = document.body.innerText;
                        
                        if (errorText.includes('Something went wrong') || errorText.includes('Try again')) {
                            console.log('⚠️ X.com rate limit detected, clicking retry...');
                            if (retryButton && retryButton.innerText.includes('Retry')) {
                                retryButton.click();
                                return { needsRetry: true };
                            }
                        }
                        return { needsRetry: false };
                    })()
                    """
                    
                    async with scrape_session.post(
                        f"{vnc_url}/execute",
                        json={"script": retry_check_script},
                        timeout=aiohttp.ClientTimeout(total=5)
                    ) as resp:
                        retry_result = await resp.json()
                        if retry_result.get("result", {}).get("needsRetry"):
                            print(f"   🔄 Auto-clicking retry button...")
                            await asyncio.sleep(3)  # Wait for page to reload
                    
                    # Scrape current posts on page
                    scrape_script = """
                    Array.from(document.querySelectorAll('[data-testid="tweet"]')).map(tweet => {
                        const text = tweet.querySelector('[data-testid="tweetText"]')?.innerText || '';
                        const timeEl = tweet.querySelector('time');
                        const likeBtn = tweet.querySelector('[data-testid="like"]');
                        const replyBtn = tweet.querySelector('[data-testid="reply"]');
                        
                        return {
                            content: text,
                            timestamp: timeEl ? timeEl.getAttribute('datetime') : new Date().toISOString(),
                            engagement: {
                                likes: parseInt(likeBtn?.getAttribute('aria-label')?.match(/\\d+/)?.[0] || '0'),
                                replies: parseInt(replyBtn?.getAttribute('aria-label')?.match(/\\d+/)?.[0] || '0'),
                                reposts: 0
                            }
                        };
                    }).filter(p => p.content);
                    """
                    
                    async with scrape_session.post(
                        f"{vnc_url}/execute",
                        json={"script": scrape_script},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as resp:
                        exec_result = await resp.json()
                        current_posts = exec_result.get("result", [])
                    
                    # Add new unique posts
                    for post in current_posts:
                        if post["content"] and post["content"] not in collected_posts:
                            collected_posts[post["content"]] = post
                    
                    unique_count = len(collected_posts)
                    print(f"   Scroll {i+1}: {unique_count} unique posts collected")
                    
                    # Send progress update to user's WebSocket if connected
                    # Use clerk_user_id for WebSocket connection
                    websocket = active_connections.get(clerk_user_id)
                    if not websocket and active_connections:
                        # Fallback: use the first connected user (likely the current user)
                        websocket = list(active_connections.values())[0]
                        print(f"   ⚠️ Using fallback WebSocket (user_id mismatch)")
                    
                    if websocket:
                        try:
                            await websocket.send_json({
                                "type": "SCRAPE_PROGRESS",
                                "current": unique_count,
                                "target": target_count,
                                "scroll": i + 1
                            })
                            print(f"   📤 Sent progress update: {unique_count}/{target_count}")
                        except Exception as ws_err:
                            print(f"   ⚠️ Failed to send WebSocket update: {ws_err}")
                    else:
                        print(f"   ⚠️ No WebSocket connection found for user {user_id}")
                    
                    # Check if we're stuck (no new posts)
                    if unique_count == last_count:
                        no_new_posts_count += 1
                        print(f"   ⚠️ No new posts on this scroll ({no_new_posts_count}/3)")
                        if no_new_posts_count >= 3:
                            print(f"   🛑 Stopping: No new posts after 3 scrolls")
                            break
                    else:
                        no_new_posts_count = 0  # Reset counter if we got new posts
                    
                    last_count = unique_count
                    
                    # If we have enough posts, stop
                    if unique_count >= target_count:
                        print(f"✅ Reached target of {target_count} posts!")
                        break
                    
                    # Scroll down with human-like behavior (slower, variable speed)
                    try:
                        # Smooth scroll instead of instant jump (more human-like)
                        smooth_scroll_script = """
                        (() => {
                            const scrollAmount = 800 + Math.random() * 400; // Random 800-1200px
                            window.scrollBy({
                                top: scrollAmount,
                                behavior: 'smooth'
                            });
                            return { scrolled: scrollAmount };
                        })()
                        """
                        async with scrape_session.post(
                            f"{vnc_url}/execute",
                            json={"script": smooth_scroll_script},
                            timeout=aiohttp.ClientTimeout(total=5)
                        ) as resp:
                            scroll_result = await resp.json()
                            print(f"   📜 Scrolled {scroll_result.get('result', {}).get('scrolled', 0)}px")
                    except Exception as scroll_err:
                        print(f"⚠️ Scroll failed: {scroll_err}, continuing...")
                    
                    # Random wait time between 4-7 seconds (more human-like, avoids rate limits)
                    wait_time = 4 + (i % 4)  # Varies between 4-7 seconds
                    print(f"   ⏳ Waiting {wait_time}s for posts to load...")
                    await asyncio.sleep(wait_time)
                    
                except Exception as e:
                    print(f"⚠️ Error on scroll {i+1}: {e}")
                    # Continue with what we have
                    if len(collected_posts) > 0:
                        print(f"   Continuing with {len(collected_posts)} posts collected so far")
                        break
                    else:
                        raise
        
        # Convert dict to list and limit to target
        posts = list(collected_posts.values())[:target_count]
        print(f"📊 Collected {len(posts)} unique posts total")
        
        # Check against LangGraph Store (more reliable than in-memory)
        existing_store_contents = {p.get("content") for p in existing_posts}
        new_posts = [p for p in posts if p.get("content") not in existing_store_contents]
        
        # Also update in-memory cache
        if user_id not in user_posts:
            user_posts[user_id] = []
        
        existing_contents = {p.get("content") for p in user_posts[user_id]}
        for post in new_posts:
            if post.get("content") not in existing_contents:
                user_posts[user_id].append(post)
        
        print(f"✅ Found {len(new_posts)} new posts out of {len(posts)} scraped for @{username}")
        
        # Check if we actually got new posts
        if len(new_posts) == 0:
            print(f"ℹ️ No new posts found - you're already up to date!")
            
            # Send message to user
            websocket = active_connections.get(clerk_user_id)
            if websocket:
                try:
                    await websocket.send_json({
                        "type": "IMPORT_COMPLETE",
                        "imported": 0,
                        "total": len(user_posts[user_id]),
                        "username": username,
                        "message": "Already up to date! No new posts found."
                    })
                except Exception as ws_err:
                    print(f"   ⚠️ Failed to send message: {ws_err}")
            
            return {
                "success": True,
                "imported": 0,
                "total": len(user_posts[user_id]),
                "username": username,
                "message": "Already up to date"
            }
        
        # Store in LangGraph Store with embeddings for persistent memory
        # Use CLERK user ID to keep data consistent across sessions
        try:
            style_manager = XWritingStyleManager(store, clerk_user_id)
            
            # bulk_import_posts expects dicts, not WritingSample objects
            # It will create WritingSample objects internally
            print(f"💾 Saving {len(new_posts)} posts to LangGraph Store with embeddings...")
            style_manager.bulk_import_posts(new_posts)
            print(f"✅ Successfully saved {len(new_posts)} posts to LangGraph Store")
            
        except Exception as e:
            print(f"⚠️ Error saving to LangGraph store: {e}")
            import traceback
            traceback.print_exc()
        
        # Also save to PostgreSQL database for persistence
        try:
            from database.models import UserPost, XAccount
            from database.database import SessionLocal
            
            db = SessionLocal()
            
            # Get or create X account
            x_account = db.query(XAccount).filter(XAccount.username == username).first()
            if not x_account:
                x_account = XAccount(
                    user_id=clerk_user_id,
                    username=username,
                    is_connected=True
                )
                db.add(x_account)
                db.commit()
                db.refresh(x_account)
                print(f"✅ Created X account record for @{username}")
            
            # Save posts to database
            saved_count = 0
            for post in new_posts:
                # Check if post already exists (by content or URL)
                existing = db.query(UserPost).filter(
                    UserPost.x_account_id == x_account.id,
                    UserPost.content == post["content"]
                ).first()
                
                if not existing:
                    user_post = UserPost(
                        x_account_id=x_account.id,
                        content=post["content"],
                        post_url=post.get("url"),
                        likes=post.get("engagement", {}).get("likes", 0),
                        retweets=post.get("engagement", {}).get("retweets", 0),
                        replies=post.get("engagement", {}).get("replies", 0),
                        posted_at=post.get("timestamp")
                    )
                    db.add(user_post)
                    saved_count += 1
            
            db.commit()
            db.close()
            print(f"✅ Saved {saved_count} posts to PostgreSQL database")
            
        except Exception as e:
            print(f"⚠️ Error saving to database: {e}")
            import traceback
            traceback.print_exc()
        
        # Send completion message to user's WebSocket
        websocket = active_connections.get(clerk_user_id)
        if not websocket and active_connections:
            websocket = list(active_connections.values())[0]
            print(f"   ⚠️ Using fallback WebSocket for completion message")
        
        if websocket:
            try:
                await websocket.send_json({
                    "type": "IMPORT_COMPLETE",
                    "imported": len(new_posts),
                    "total": len(user_posts[user_id]),
                    "username": username
                })
                print(f"   📤 Sent completion message")
            except Exception as ws_err:
                print(f"   ⚠️ Failed to send completion message: {ws_err}")
        
        return {
            "success": True,
            "imported": len(new_posts),
            "total": len(user_posts[user_id]),
            "username": username
        }
        
    except Exception as e:
        print(f"❌ Error scraping posts: {e}")
        import traceback
        traceback.print_exc()
        
        # Send error message to user's WebSocket
        if clerk_user_id in active_connections:
            try:
                await active_connections[clerk_user_id].send_json({
                    "type": "SCRAPE_ERROR",
                    "error": str(e)
                })
            except:
                pass
        
        return {
            "success": False,
            "error": str(e)
        }

@app.post("/api/import-posts")
async def import_posts(data: dict):
    """
    Import user's X posts for writing style learning
    """
    user_id = data.get("user_id", "default_user")
    posts = data.get("posts", [])
    
    if not posts:
        return {
            "success": False,
            "error": "No posts provided"
        }
    
    # Store posts for this user
    if user_id not in user_posts:
        user_posts[user_id] = []
    
    # Add new posts (avoid duplicates by content)
    existing_contents = {p.get("content") for p in user_posts[user_id]}
    new_posts = [p for p in posts if p.get("content") not in existing_contents]
    user_posts[user_id].extend(new_posts)
    
    print(f"✅ Imported {len(new_posts)} posts for user {user_id}")
    print(f"📊 Total posts for {user_id}: {len(user_posts[user_id])}")
    
    # Store in LangGraph Store with embeddings for persistent memory
    try:
        style_manager = XWritingStyleManager(store, user_id)
        
        # Convert posts to WritingSample format
        writing_samples = []
        for post in new_posts:
            sample = WritingSample(
                sample_id=str(uuid.uuid4()),
                user_id=user_id,
                timestamp=post.get("timestamp", datetime.now().isoformat()),
                content_type="post",
                content=post.get("content", ""),
                context=None,
                engagement=post.get("engagement", {}),
                topic=None  # Could use AI to extract topic later
            )
            writing_samples.append(sample)
        
        # Bulk save to store
        style_manager.bulk_import_posts(writing_samples)
        print(f"💾 Saved {len(writing_samples)} posts to LangGraph Store with embeddings")
        
    except Exception as e:
        print(f"⚠️ Error saving to store: {e}")
        import traceback
        traceback.print_exc()
    
    return {
        "success": True,
        "imported": len(new_posts),
        "total": len(user_posts[user_id]),
        "message": f"Imported {len(new_posts)} new posts"
    }

@app.post("/api/automate/like-post")
async def like_post(data: dict):
    """
    Endpoint called by your dashboard
    Forwards command to extension
    """
    user_id = data.get("user_id")
    post_url = data.get("post_url")
    
    if user_id not in active_connections:
        return {
            "success": False,
            "error": "Extension not connected"
        }
    
    # Send command to extension
    websocket = active_connections[user_id]
    await websocket.send_json({
        "action": "LIKE_POST",
        "postUrl": post_url
    })
    
    # In production, you'd wait for response
    # For now, just return success
    return {
        "success": True,
        "message": "Command sent to extension"
    }

@app.post("/api/automate/follow-user")
async def follow_user(data: dict):
    """Follow a user"""
    user_id = data.get("user_id")
    username = data.get("username")
    
    if user_id not in active_connections:
        return {"success": False, "error": "Extension not connected"}
    
    websocket = active_connections[user_id]
    await websocket.send_json({
        "action": "FOLLOW_USER",
        "username": username
    })
    
    return {"success": True, "message": "Command sent to extension"}

@app.post("/api/automate/comment-on-post")
async def comment_on_post(data: dict):
    """Comment on a post"""
    user_id = data.get("user_id")
    post_url = data.get("post_url")
    comment_text = data.get("comment_text")
    
    if user_id not in active_connections:
        return {"success": False, "error": "Extension not connected"}
    
    websocket = active_connections[user_id]
    await websocket.send_json({
        "action": "COMMENT_ON_POST",
        "postUrl": post_url,
        "commentText": comment_text
    })
    
    return {"success": True, "message": "Command sent to extension"}

# ============================================================================
# SCHEDULED POSTS API - Content Calendar
# ============================================================================

# Pydantic models for request/response validation
class CreateScheduledPostRequest(BaseModel):
    user_id: str
    content: str
    media_urls: Optional[List[str]] = []
    scheduled_at: str  # ISO format datetime
    status: Optional[str] = "draft"

class UpdateScheduledPostRequest(BaseModel):
    content: Optional[str] = None
    media_urls: Optional[List[str]] = None
    scheduled_at: Optional[str] = None
    status: Optional[str] = None

@app.get("/api/scheduled-posts")
async def get_scheduled_posts(
    user_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """
    Get all scheduled posts for a user within a date range
    Query params:
    - user_id: Clerk user ID
    - start_date: ISO datetime string (optional)
    - end_date: ISO datetime string (optional)
    """
    try:
        # Get user's X accounts
        x_accounts = db.query(XAccount).filter(XAccount.user_id == user_id).all()
        if not x_accounts:
            return {"success": True, "posts": [], "message": "No X accounts connected"}

        x_account_ids = [acc.id for acc in x_accounts]

        # Query scheduled posts
        query = db.query(ScheduledPost).filter(ScheduledPost.x_account_id.in_(x_account_ids))

        # Apply date filters if provided
        if start_date:
            query = query.filter(ScheduledPost.scheduled_at >= datetime.fromisoformat(start_date.replace('Z', '+00:00')))
        if end_date:
            query = query.filter(ScheduledPost.scheduled_at <= datetime.fromisoformat(end_date.replace('Z', '+00:00')))

        posts = query.order_by(ScheduledPost.scheduled_at).all()

        # Convert to dict
        posts_data = []
        for post in posts:
            posts_data.append({
                "id": post.id,
                "content": post.content,
                "media_urls": post.media_urls or [],
                "status": post.status,
                "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
                "posted_at": post.posted_at.isoformat() if post.posted_at else None,
                "ai_generated": post.ai_generated,
                "ai_confidence": post.ai_confidence,
                "error_message": post.error_message,
                "created_at": post.created_at.isoformat(),
                "updated_at": post.updated_at.isoformat()
            })

        return {"success": True, "posts": posts_data, "count": len(posts_data)}

    except Exception as e:
        print(f"Error fetching scheduled posts: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduled-posts")
async def create_scheduled_post(
    request: CreateScheduledPostRequest,
    db: Session = Depends(get_db)
):
    """Create a new scheduled post"""
    try:
        # Get user's primary X account
        x_account = db.query(XAccount).filter(
            XAccount.user_id == request.user_id,
            XAccount.is_connected == True
        ).first()

        if not x_account:
            raise HTTPException(status_code=404, detail="No connected X account found")

        # Create new scheduled post
        new_post = ScheduledPost(
            x_account_id=x_account.id,
            content=request.content,
            media_urls=request.media_urls,
            scheduled_at=datetime.fromisoformat(request.scheduled_at.replace('Z', '+00:00')),
            status=request.status,
            ai_generated=False
        )

        db.add(new_post)
        db.commit()
        db.refresh(new_post)

        return {
            "success": True,
            "post": {
                "id": new_post.id,
                "content": new_post.content,
                "media_urls": new_post.media_urls,
                "status": new_post.status,
                "scheduled_at": new_post.scheduled_at.isoformat(),
                "created_at": new_post.created_at.isoformat()
            }
        }

    except Exception as e:
        db.rollback()
        print(f"Error creating scheduled post: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/scheduled-posts/{post_id}")
async def update_scheduled_post(
    post_id: int,
    request: UpdateScheduledPostRequest,
    db: Session = Depends(get_db)
):
    """Update an existing scheduled post"""
    try:
        post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        old_status = post.status
        needs_rescheduling = False

        # Update fields if provided
        if request.content is not None:
            post.content = request.content
        if request.media_urls is not None:
            post.media_urls = request.media_urls
        if request.scheduled_at is not None:
            post.scheduled_at = datetime.fromisoformat(request.scheduled_at.replace('Z', '+00:00'))
            needs_rescheduling = True
        if request.status is not None:
            post.status = request.status
            if request.status == "scheduled" and old_status != "scheduled":
                needs_rescheduling = True

        post.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(post)

        # Schedule or reschedule the post if status changed to "scheduled"
        if needs_rescheduling and post.status == "scheduled":
            try:
                executor = await get_executor()

                # Get the X account info
                x_account = db.query(XAccount).filter(
                    XAccount.id == post.x_account_id
                ).first()

                if x_account and post.scheduled_at:
                    # Cancel existing job if rescheduling
                    if old_status == "scheduled":
                        executor.cancel_scheduled_post(post.id)

                    # Check if post should execute immediately (in the past)
                    if post.scheduled_at <= datetime.now():
                        print(f"⚠️ Post {post.id} scheduled for past time {post.scheduled_at}, executing immediately")
                        # Execute immediately
                        await executor._execute_post_action(
                            post_id=post.id,
                            post_content=post.content,
                            user_id=x_account.user_id,
                            username=x_account.username,
                            media_urls=post.media_urls or []
                        )
                    else:
                        # Schedule for future execution
                        executor.schedule_post(
                            post_id=post.id,
                            post_content=post.content,
                            scheduled_time=post.scheduled_at,
                            user_id=x_account.user_id,
                            username=x_account.username,
                            media_urls=post.media_urls or []
                        )
                        print(f"✅ Post {post.id} scheduled for {post.scheduled_at}")
            except Exception as e:
                print(f"⚠️ Failed to schedule post {post.id}: {e}")
                import traceback
                traceback.print_exc()

        return {
            "success": True,
            "post": {
                "id": post.id,
                "content": post.content,
                "media_urls": post.media_urls,
                "status": post.status,
                "scheduled_at": post.scheduled_at.isoformat() if post.scheduled_at else None,
                "updated_at": post.updated_at.isoformat()
            }
        }

    except Exception as e:
        db.rollback()
        print(f"Error updating scheduled post: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/scheduled-posts/{post_id}")
async def delete_scheduled_post(
    post_id: int,
    db: Session = Depends(get_db)
):
    """Delete a scheduled post"""
    try:
        post = db.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()

        if not post:
            raise HTTPException(status_code=404, detail="Post not found")

        # Cancel scheduled job if post was scheduled
        if post.status == "scheduled":
            try:
                executor = await get_executor()
                executor.cancel_scheduled_post(post.id)
                print(f"🗑️ Cancelled scheduled job for post {post.id}")
            except Exception as e:
                print(f"⚠️ Failed to cancel scheduled job for post {post.id}: {e}")

        db.delete(post)
        db.commit()

        return {"success": True, "message": "Post deleted successfully"}

    except Exception as e:
        db.rollback()
        print(f"Error deleting scheduled post: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_media(file: UploadFile = File(...)):
    """
    Upload media file (image/video) for scheduled post
    Saves to local uploads directory (in production would use S3/Cloudinary)
    """
    try:
        # Create uploads directory if it doesn't exist
        upload_dir = "uploads/media"
        os.makedirs(upload_dir, exist_ok=True)

        # Generate unique filename
        import uuid
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"{uuid.uuid4()}{file_extension}"
        file_path = os.path.join(upload_dir, unique_filename)

        # Save file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        # Return URL (in production this would be S3/Cloudinary URL)
        file_url = f"/uploads/media/{unique_filename}"

        return {
            "success": True,
            "url": file_url,
            "filename": unique_filename,
            "content_type": file.content_type,
            "size": len(content)
        }

    except Exception as e:
        print(f"Error uploading file: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/scheduled-posts/generate-ai")
async def generate_ai_content(
    user_id: str,
    count: int = 7,  # Always generate 7 for the week
    db: Session = Depends(get_db)
):
    """
    Generate weekly AI content using the Weekly Content Generator Agent

    This uses LangGraph to:
    1. Analyze user's writing style from imported posts
    2. Analyze high-quality competitor posts
    3. Conduct web research with Perplexity API
    4. Strategize content for growth
    5. Generate 7 posts for next week
    """
    try:
        from weekly_content_generator import generate_weekly_content
        from langgraph.store.postgres import PostgresStore

        # Get user's X account to get username
        x_account = db.query(XAccount).filter(
            XAccount.user_id == user_id,
            XAccount.is_connected == True
        ).first()

        if x_account:
            user_handle = x_account.username
        else:
            # Fallback: Try to get username from social graph data
            print("⚠️  No X account found, trying to get username from social graph...")
            conn_string = os.getenv("POSTGRES_CONNECTION_STRING",
                                   "postgresql://postgres:password@localhost:5433/xgrowth")

            with PostgresStore.from_conn_string(conn_string) as store:
                graph_namespace = (user_id, "social_graph")
                graph_item = (store.get(graph_namespace, "graph_data") or
                            store.get(graph_namespace, "latest") or
                            store.get(graph_namespace, "current"))

                if graph_item and graph_item.value.get("user_handle"):
                    user_handle = graph_item.value.get("user_handle")
                    print(f"✅ Found username from social graph: @{user_handle}")
                else:
                    raise HTTPException(status_code=404, detail="Could not determine user's X handle")

        print(f"🚀 Generating weekly content for @{user_handle}...")

        # Run the weekly content generator agent
        generated_posts = await generate_weekly_content(
            user_id=user_id,
            user_handle=user_handle
        )

        print(f"✅ Generated {len(generated_posts)} posts")

        # Save generated posts to database as drafts for persistence
        saved_posts = []

        # Get or create x_account
        if not x_account:
            # Create a temporary x_account entry if it doesn't exist
            x_account = XAccount(
                user_id=user_id,
                username=user_handle,
                is_connected=True
            )
            db.add(x_account)
            db.flush()  # Get the ID without committing

        for post_data in generated_posts:
            scheduled_post = ScheduledPost(
                x_account_id=x_account.id,
                content=post_data["content"],
                scheduled_at=datetime.fromisoformat(post_data["scheduled_at"].replace("Z", "+00:00")),
                status="draft",
                ai_generated=True,
                ai_confidence=int(post_data.get("confidence", 1.0) * 100),
                ai_metadata=post_data.get("metadata", {})
            )
            db.add(scheduled_post)
            db.flush()

            # Add ID to response
            saved_post = {
                "id": scheduled_post.id,
                **post_data
            }
            saved_posts.append(saved_post)

        db.commit()
        print(f"💾 Saved {len(saved_posts)} posts to database as drafts")

        return {
            "success": True,
            "posts": saved_posts,
            "count": len(saved_posts),
            "message": f"Generated {len(saved_posts)} posts for next week"
        }

    except Exception as e:
        print(f"❌ Error generating AI content: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/scheduled-posts/ai-drafts")
async def get_ai_drafts(
    user_id: str,
    db: Session = Depends(get_db)
):
    """
    Get all AI-generated draft posts for a user
    """
    try:
        # Get user's X accounts
        x_accounts = db.query(XAccount).filter(XAccount.user_id == user_id).all()
        if not x_accounts:
            return {"success": True, "posts": [], "message": "No X accounts connected"}

        x_account_ids = [acc.id for acc in x_accounts]

        # Query AI-generated draft posts only
        drafts = db.query(ScheduledPost).filter(
            ScheduledPost.x_account_id.in_(x_account_ids),
            ScheduledPost.status == "draft",
            ScheduledPost.ai_generated == True
        ).order_by(ScheduledPost.scheduled_at.asc()).all()

        # Format response
        posts = []
        for draft in drafts:
            posts.append({
                "id": draft.id,
                "content": draft.content,
                "scheduled_at": draft.scheduled_at.isoformat(),
                "confidence": draft.ai_confidence / 100.0 if draft.ai_confidence else 1.0,
                "ai_generated": True,
                "metadata": draft.ai_metadata or {}
            })

        return {
            "success": True,
            "posts": posts,
            "count": len(posts)
        }

    except Exception as e:
        print(f"❌ Error fetching AI drafts: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# AGENT CONTROL ENDPOINTS
# ============================================================================

@app.post("/api/agent/run")
async def run_agent(data: dict):
    """
    Run the X Growth Deep Agent with streaming updates
    
    Implements LangGraph's double-texting behavior with rollback strategy:
    - If agent is already running, uses multitask_strategy="rollback" 
    - This stops the previous run and DELETES it from the database
    - Starts the new run with the new message
    - Clean conversation history (no interrupted runs)
    """
    user_id = data.get("user_id")
    task = data.get("task", "Help me grow my X account")
    thread_id = data.get("thread_id")  # Optional: continue existing thread
    
    if not user_id:
        return {"success": False, "error": "user_id is required"}
    
    try:
        # Use provided thread_id or create/get thread for this user
        if thread_id:
            # Continue existing conversation
            user_threads[user_id] = thread_id
            print(f"📝 Continuing thread for user {user_id}: {thread_id}")
        elif user_id not in user_threads:
            # Create new thread
            thread = await langgraph_client.threads.create()
            user_threads[user_id] = thread["thread_id"]
            print(f"✨ Created new thread for user {user_id}: {thread['thread_id']}")
        
        thread_id = user_threads[user_id]
        
        # 🔥 DOUBLE-TEXTING: Check if there's already a run in progress
        is_double_texting = user_id in active_runs and not active_runs[user_id].get("cancelled")
        
        if is_double_texting:
            print(f"⚡ Double-texting detected! User sent new message while agent is running")
            print(f"   Previous run will be rolled back (deleted)")
            # Set cancellation flag for the old streaming loop
            active_runs[user_id]["cancelled"] = True
        
        # Start the agent run (will stream via WebSocket)
        print(f"🤖 Starting agent for user {user_id} with task: {task}")
        
        # Send initial status to WebSocket
        if user_id in active_connections:
            await active_connections[user_id].send_json({
                "type": "AGENT_STARTED",
                "thread_id": thread_id,
                "task": task,
                "is_double_texting": is_double_texting
            })
        
        # Stream agent execution in background with rollback strategy if double-texting
        task_obj = asyncio.create_task(
            stream_agent_execution(user_id, thread_id, task, use_rollback=is_double_texting)
        )
        
        # Add error handler for the background task
        def task_done_callback(task):
            try:
                task.result()  # This will raise any exception that occurred
            except Exception as e:
                print(f"❌ Background task error: {e}")
                import traceback
                traceback.print_exc()
        
        task_obj.add_done_callback(task_done_callback)
        
        return {
            "success": True,
            "thread_id": thread_id,
            "message": "Agent started successfully",
            "double_texting": is_double_texting
        }
        
    except Exception as e:
        print(f"❌ Error starting agent: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

async def stream_agent_execution(user_id: str, thread_id: str, task: str, use_rollback: bool = False):
    """
    Stream agent execution to WebSocket with token-by-token streaming

    Args:
        user_id: User identifier
        thread_id: LangGraph thread ID
        task: User's message/task
        use_rollback: If True, uses multitask_strategy="rollback" for double-texting
                     (deletes the previous run completely)
    """
    run_id = None
    try:
        print(f"🔄 Starting agent stream for user {user_id}, thread {thread_id}")
        if use_rollback:
            print(f"   Using rollback strategy (double-texting - will delete previous run)")

        # Get user's VNC session URL for the agent to use
        vnc_url = None
        try:
            vnc_manager = await get_vnc_manager()
            if vnc_manager:
                vnc_session = await vnc_manager.get_session(user_id)
                if vnc_session:
                    vnc_url = vnc_session.get("https_url") or vnc_session.get("service_url")
                    print(f"🖥️ Using VNC URL for agent: {vnc_url}")
        except Exception as e:
            print(f"⚠️ Could not get VNC session for agent: {e}")

        # Track the last sent content to calculate diffs
        last_content = ""

        # Mark this run as active (will be populated with run_id once we get it)
        active_runs[user_id] = {
            "thread_id": thread_id,
            "run_id": None,  # Will be set when we get it from the stream
            "cancelled": False,
            "task": asyncio.current_task()
        }

        # Use "messages" stream mode for token-by-token streaming
        # If double-texting, use rollback strategy to delete the previous run
        stream_kwargs = {
            "thread_id": thread_id,
            "assistant_id": "x_growth_deep_agent",
            "input": {
                "messages": [{
                    "role": "user",
                    "content": task
                }]
            },
            "stream_mode": "messages",
            "config": {
                "configurable": {
                    "user_id": user_id,
                    "cua_url": vnc_url,  # Per-user VNC URL
                }
            }
        }
        
        # Add multitask_strategy if double-texting
        if use_rollback:
            stream_kwargs["multitask_strategy"] = "rollback"
        
        try:
            async for chunk in langgraph_client.runs.stream(**stream_kwargs):
                # Check if cancelled
                if user_id in active_runs and active_runs[user_id].get("cancelled"):
                    print(f"🛑 Run cancelled by user {user_id}")
                    break

                # Extract run_id from chunk if available
                if run_id is None and hasattr(chunk, 'metadata'):
                    run_id = chunk.metadata.get('run_id')
                    if run_id and user_id in active_runs:
                        active_runs[user_id]["run_id"] = run_id

                # LangGraph stream_mode="messages" returns (message, metadata) tuples
                # Filter by langgraph_node to skip tool execution nodes
                if hasattr(chunk, 'data'):
                    # Check metadata to skip tool nodes
                    metadata = {}
                    if hasattr(chunk, 'metadata') and chunk.metadata:
                        metadata = chunk.metadata if isinstance(chunk.metadata, dict) else {}
                    node_name = metadata.get('langgraph_node', '')

                    # Skip only messages that are explicitly from tool nodes
                    # Allow messages with no node_name (they're usually LLM streaming tokens)
                    if node_name and node_name != 'model':
                        continue

                    message_list = chunk.data
                    if user_id in active_connections:
                        try:
                            # chunk.data contains the message chunk from LangGraph
                            # It's usually a list with message objects
                            if isinstance(message_list, list) and len(message_list) > 0:
                                message_data = message_list[0]  # Get first item

                                # Extract content from the message chunk
                                # LangGraph returns content as a list of content blocks
                                if isinstance(message_data, dict):
                                    content_blocks = message_data.get('content', [])

                                    # Extract text from content blocks
                                    current_content = ""
                                    if isinstance(content_blocks, list) and len(content_blocks) > 0:
                                        for block in content_blocks:
                                            if isinstance(block, dict) and block.get('type') == 'text':
                                                current_content += block.get('text', '')
                                    elif isinstance(content_blocks, str):
                                        current_content = content_blocks

                                    # Calculate the new token (diff from last content)
                                    if current_content and current_content != last_content:
                                        if current_content.startswith(last_content):
                                            # Send only the new part
                                            new_token = current_content[len(last_content):]
                                            if new_token:
                                                await active_connections[user_id].send_json({
                                                    "type": "AGENT_TOKEN",
                                                    "token": new_token
                                                })
                                                print(f"📤 Sent new token: {repr(new_token[:30])}...")
                                        else:
                                            # Content changed completely (new message), send all
                                            await active_connections[user_id].send_json({
                                                "type": "AGENT_TOKEN",
                                                "token": current_content
                                            })
                                            print(f"📤 Sent full content: {current_content[:50]}...")

                                        last_content = current_content
                        except Exception as e:
                            print(f"⚠️ Failed to send WebSocket update: {e}")
                            import traceback
                            traceback.print_exc()
            
            # Update thread metadata with last message
            if thread_id in thread_metadata and last_content:
                thread_metadata[thread_id]["last_message"] = last_content[:100] + "..." if len(last_content) > 100 else last_content
                thread_metadata[thread_id]["updated_at"] = datetime.now().isoformat()
                
                # Auto-generate title from first message if still "New Chat"
                if thread_metadata[thread_id]["title"] == "New Chat" and last_content:
                    # Use first 50 chars of the response as title
                    title = last_content[:50].strip()
                    if len(last_content) > 50:
                        title += "..."
                    thread_metadata[thread_id]["title"] = title
            
            # Send completion message
            if user_id in active_connections:
                # Check if it was cancelled
                was_cancelled = user_id in active_runs and active_runs[user_id].get("cancelled")
                
                await active_connections[user_id].send_json({
                    "type": "AGENT_CANCELLED" if was_cancelled else "AGENT_COMPLETED",
                    "thread_id": thread_id
                })
            
            # Clean up active run
            if user_id in active_runs:
                del active_runs[user_id]
            
            print(f"✅ Agent completed for user {user_id}")
        
        except Exception as stream_error:
            # Handle 404 errors (thread not found) by creating a new thread
            if "404" in str(stream_error) or "not found" in str(stream_error).lower():
                print(f"⚠️  Thread {thread_id} not found, creating new thread...")
                
                # Create new thread
                new_thread = await langgraph_client.threads.create()
                new_thread_id = new_thread["thread_id"]
                user_threads[user_id] = new_thread_id
                
                print(f"✨ Created new thread {new_thread_id}, retrying...")
                
                # Notify frontend of new thread
                if user_id in active_connections:
                    await active_connections[user_id].send_json({
                        "type": "THREAD_RECREATED",
                        "old_thread_id": thread_id,
                        "new_thread_id": new_thread_id,
                        "message": "Previous conversation not found. Starting fresh."
                    })
                
                # Retry with new thread (preserve use_rollback parameter)
                await stream_agent_execution(user_id, new_thread_id, task, use_rollback)
            else:
                raise stream_error
        
    except Exception as e:
        print(f"❌ Error during agent execution: {e}")
        import traceback
        traceback.print_exc()
        
        # Clean up active run
        if user_id in active_runs:
            del active_runs[user_id]
        
        # Send error to frontend
        if user_id in active_connections:
            try:
                await active_connections[user_id].send_json({
                    "type": "AGENT_ERROR",
                    "error": str(e)
                })
            except:
                pass

# Stop button removed - use double-texting instead!
# Just send a new message while agent is running and it will automatically
# use multitask_strategy="rollback" to cancel the previous run

@app.get("/api/agent/status/{user_id}")
async def get_agent_status(user_id: str):
    """
    Check if an agent is currently running for a user
    """
    try:
        is_running = user_id in active_runs and not active_runs[user_id].get("cancelled")
        
        if is_running:
            return {
                "is_running": True,
                "thread_id": active_runs[user_id].get("thread_id"),
                "run_id": active_runs[user_id].get("run_id")
            }
        else:
            return {
                "is_running": False
            }
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/agent/history/{thread_id}")
async def get_agent_history(thread_id: str):
    """
    Get agent execution history for a thread
    """
    try:
        history = await langgraph_client.threads.get_history(
            thread_id=thread_id,
            limit=50
        )
        
        # Convert async iterator to list
        history_list = []
        async for checkpoint in history:
            history_list.append(checkpoint)
        
        return {
            "success": True,
            "thread_id": thread_id,
            "history": history_list
        }
    except Exception as e:
        print(f"❌ Error fetching history: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/agent/state/{thread_id}")
async def get_agent_state(thread_id: str):
    """
    Get current state of an agent thread
    """
    try:
        state = await langgraph_client.threads.get_state(
            thread_id=thread_id
        )
        
        return {
            "success": True,
            "thread_id": thread_id,
            "state": state
        }
    except Exception as e:
        print(f"❌ Error fetching state: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/agent/threads/new")
async def create_new_thread(data: dict):
    """
    Create a new thread for a user (starts fresh conversation)
    """
    user_id = data.get("user_id")
    title = data.get("title", "New Chat")
    
    if not user_id:
        return {"success": False, "error": "user_id is required"}
    
    try:
        # Create new thread with metadata
        thread = await langgraph_client.threads.create(
            metadata={"user_id": user_id}
        )
        thread_id = thread["thread_id"]
        
        # Update user's current thread
        user_threads[user_id] = thread_id
        
        # Store thread metadata
        thread_metadata[thread_id] = {
            "user_id": user_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "last_message": None,
            "updated_at": datetime.now().isoformat()
        }
        
        print(f"✨ Created new thread for user {user_id}: {thread_id}")
        
        return {
            "success": True,
            "thread_id": thread_id,
            "title": title,
            "created_at": thread_metadata[thread_id]["created_at"],
            "message": "New thread created"
        }
    except Exception as e:
        print(f"❌ Error creating thread: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.get("/api/agent/threads/list/{user_id}")
async def list_user_threads(user_id: str):
    """
    List all threads for a user using LangGraph SDK
    """
    try:
        # Use LangGraph SDK to search threads by metadata
        print(f"🔍 Searching threads for user: {user_id}")
        threads_response = await langgraph_client.threads.search(
            metadata={"user_id": user_id},
            limit=100  # Adjust as needed
        )
        
        if not threads_response:
            print(f"📋 No threads found for user {user_id}")
            return {
                "success": True,
                "threads": [],
                "count": 0
            }
        
        print(f"📋 Found {len(threads_response)} thread(s) for user {user_id}")
        
        # Process threads from search response
        threads_list = []
        for thread in threads_response:
            try:
                thread_id = thread['thread_id']
                # Get thread state to fetch messages
                state = await langgraph_client.threads.get_state(thread_id)
                
                # state is a dict with 'values' key
                if state and "values" in state:
                    values_dict = state["values"]
                    messages = values_dict.get("messages", [])
                    
                    print(f"🔍 Thread {thread_id}: Found {len(messages)} messages")
                    
                    # Skip empty threads (no messages)
                    if not messages:
                        print(f"   ⏭️ Skipping empty thread")
                        continue
                    
                    if messages:
                        first_msg = messages[0] if isinstance(messages[0], dict) else (messages[0].dict() if hasattr(messages[0], 'dict') else {})
                        print(f"   First message structure: {first_msg.keys() if isinstance(first_msg, dict) else 'not a dict'}")
                    
                    # Extract first user message as title
                    title = "New Chat"
                    last_message = None
                    created_at = None
                    updated_at = None
                    
                    for msg in messages:
                        # Handle both dict and LangChain message objects
                        msg_dict = msg if isinstance(msg, dict) else (msg.dict() if hasattr(msg, 'dict') else {})
                        
                        # Check message type/role (could be 'human', 'user', 'HumanMessage', etc.)
                        msg_type = msg_dict.get("type", "").lower()
                        msg_role = msg_dict.get("role", "").lower()
                        msg_class = msg_dict.get("__class__", {}).get("__name__", "").lower() if isinstance(msg_dict.get("__class__"), dict) else ""
                        
                        is_human = "human" in msg_type or "user" in msg_type or "user" in msg_role or "human" in msg_class
                        is_ai = "ai" in msg_type or "assistant" in msg_type or "assistant" in msg_role or "ai" in msg_class
                        
                        if is_human and (title == "New Chat" or not title):
                            content = msg_dict.get("content", "")
                            if isinstance(content, str) and content.strip():
                                title = content[:50] + ("..." if len(content) > 50 else "")
                        
                        # Get last AI message
                        if is_ai:
                            content = msg_dict.get("content", "")
                            if isinstance(content, str) and content.strip():
                                last_message = content[:100] + ("..." if len(content) > 100 else "")
                            elif isinstance(content, list):
                                # Extract text from content blocks
                                text_parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
                                if text_parts:
                                    last_message = " ".join(text_parts)[:100]
                    
                    # Use metadata from state if available
                    # state might be a dict or an object
                    if isinstance(state, dict):
                        metadata = state.get("metadata", {})
                        created_at = metadata.get("created_at") or state.get("created_at") or thread.get("created_at")
                        updated_at = metadata.get("updated_at") or state.get("updated_at") or thread.get("updated_at")
                    else:
                        metadata = getattr(state, 'metadata', {}) or {}
                        created_at = metadata.get("created_at") or getattr(state, 'created_at', None) or thread.get("created_at")
                        updated_at = metadata.get("updated_at") or getattr(state, 'created_at', None) or thread.get("updated_at")
                    
                    threads_list.append({
                        "thread_id": thread_id,
                        "title": title,
                        "last_message": last_message,
                        "created_at": created_at,
                        "updated_at": updated_at,
                        "user_id": user_id
                    })
            except Exception as e:
                print(f"⚠️ Error fetching thread {thread_id}: {e}")
                continue
        
        # Sort by updated_at (most recent first)
        threads_list.sort(key=lambda x: x.get("updated_at", x["created_at"]), reverse=True)
        
        print(f"📋 Found {len(threads_list)} threads for user {user_id}")
        
        return {
            "success": True,
            "threads": threads_list,
            "count": len(threads_list)
        }
    except Exception as e:
        print(f"❌ Error listing threads: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.get("/api/agent/threads/{user_id}")
async def get_user_thread(user_id: str):
    """
    Get the current active thread ID for a user
    """
    thread_id = user_threads.get(user_id)
    
    if not thread_id:
        return {
            "success": False,
            "message": "No active thread found for this user"
        }
    
    return {
        "success": True,
        "user_id": user_id,
        "thread_id": thread_id
    }

@app.get("/api/agent/threads/{thread_id}/messages")
async def get_thread_messages(thread_id: str):
    """
    Fetch all messages for a specific thread from LangGraph's PostgreSQL store
    """
    try:
        print(f"📖 Fetching messages for thread: {thread_id}")
        
        # Get thread state from LangGraph
        state = await langgraph_client.threads.get_state(thread_id)
        
        if not state or "values" not in state:
            return {
                "success": True,
                "messages": [],
                "thread_id": thread_id
            }
        
        # Extract messages from state
        messages_data = state["values"].get("messages", [])
        
        # Format messages for frontend
        formatted_messages = []
        for msg in messages_data:
            msg_type = msg.get("type", "")

            # Filter: Skip tool messages (tool execution results)
            if msg_type in ["tool", "function"]:
                continue

            # Filter: Skip AI messages with tool_calls (agent invoking tools)
            if msg_type == "ai" and msg.get("tool_calls"):
                continue

            # Only include human and AI messages without tool calls
            if msg_type not in ["human", "ai"]:
                continue

            # LangGraph stores messages as BaseMessage objects
            role = "user" if msg_type == "human" else "assistant"
            content = msg.get("content", "")

            # Handle content that's an array of objects (from LangGraph)
            if isinstance(content, list):
                # Extract text from content blocks
                text_parts = []
                for block in content:
                    if isinstance(block, dict) and "text" in block:
                        text_parts.append(block["text"])
                    elif isinstance(block, str):
                        text_parts.append(block)
                content = "\n".join(text_parts)
            elif not isinstance(content, str):
                content = str(content)

            formatted_messages.append({
                "role": role,
                "content": content,
                "timestamp": msg.get("additional_kwargs", {}).get("timestamp", "")
            })
        
        print(f"✅ Retrieved {len(formatted_messages)} messages for thread {thread_id}")
        
        return {
            "success": True,
            "messages": formatted_messages,
            "thread_id": thread_id,
            "count": len(formatted_messages)
        }
        
    except Exception as e:
        print(f"❌ Error fetching thread messages: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "messages": []
        }


# ============================================================================
# Workflow Endpoints
# ============================================================================

# In-Memory Execution Tracking (Could be moved to PostgreSQL in future)
workflow_executions: dict[str, dict[str, any]] = {}


@app.get("/api/workflows")
async def list_workflows_endpoint():
    """List all available workflow templates"""
    try:
        workflows = list_available_workflows()
        return {
            "workflows": workflows,
            "total_count": len(workflows)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflows/{workflow_id}")
async def get_workflow_endpoint(workflow_id: str):
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


@app.post("/api/workflow/execute")
async def execute_workflow_endpoint(workflow_json: dict, user_id: Optional[str] = None, thread_id: Optional[str] = None):
    """
    Execute a workflow (non-streaming) via LangGraph Platform

    Args:
        workflow_json: The workflow definition
        user_id: Optional user ID for personalization
        thread_id: Optional thread ID for continuing a conversation/workflow
                   If None, creates a new thread for this execution
    """
    # Generate execution ID and thread ID
    execution_id = str(uuid.uuid4())
    workflow_thread_id = thread_id or f"workflow_{execution_id}"

    workflow_id = workflow_json.get("workflow_id", "unknown")
    workflow_name = workflow_json.get("name", "Unnamed Workflow")

    try:
        # Track execution
        workflow_executions[execution_id] = {
            "execution_id": execution_id,
            "thread_id": workflow_thread_id,
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
        print(f"🧵 Thread ID: {workflow_thread_id}")
        print(f"📋 Prompt:\n{prompt}\n")

        # Get user's VNC session URL for the agent to use
        vnc_url = None
        if user_id:
            try:
                vnc_manager = await get_vnc_manager()
                if vnc_manager:
                    vnc_session = await vnc_manager.get_session(user_id)
                    if vnc_session:
                        vnc_url = vnc_session.get("https_url") or vnc_session.get("service_url")
                        print(f"🖥️ Workflow: Using VNC URL for agent: {vnc_url}")
            except Exception as e:
                print(f"⚠️ Workflow: Could not get VNC session for agent: {e}")

        # Use LangGraph Client SDK (deployed agent with PostgreSQL persistence!)
        langgraph_client = get_client(url=LANGGRAPH_URL)

        # Execute via LangGraph Platform - automatic PostgreSQL checkpointing!
        input_data = {
            "messages": [{"role": "user", "content": prompt}]
        }

        config = {
            "configurable": {
                "user_id": user_id,
                "cua_url": vnc_url,
                "use_longterm_memory": True if user_id else False
            }
        }

        # Create run via client - PostgreSQL handles persistence automatically
        result = await langgraph_client.runs.create(
            thread_id=workflow_thread_id,  # Thread managed by PostgreSQL
            assistant_id="x_growth_deep_agent",  # From langgraph.json
            input=input_data,
            config=config
        )

        # Wait for completion
        await langgraph_client.runs.join(
            thread_id=workflow_thread_id,
            run_id=result["run_id"]
        )

        # Get final state
        final_state = await langgraph_client.threads.get_state(workflow_thread_id)

        # Update execution record
        workflow_executions[execution_id].update({
            "status": "completed",
            "completed_at": datetime.utcnow().isoformat(),
            "result": final_state
        })

        return workflow_executions[execution_id]

    except Exception as e:
        # Update execution record with error
        workflow_executions[execution_id].update({
            "status": "failed",
            "completed_at": datetime.utcnow().isoformat(),
            "error": str(e)
        })

        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/execution/{execution_id}")
async def get_execution_status_endpoint(execution_id: str):
    """Get status of a workflow execution"""
    if execution_id not in workflow_executions:
        raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

    return workflow_executions[execution_id]


@app.websocket("/api/workflow/execute/stream")
async def execute_workflow_stream_endpoint(websocket: WebSocket):
    """
    Execute workflow with real-time streaming updates via LangGraph Platform

    Supports thread management with PostgreSQL persistence:
    - If client sends thread_id, continues existing conversation
    - If no thread_id, creates new thread for this execution
    - All state automatically persisted to PostgreSQL
    """
    await websocket.accept()

    try:
        # Receive workflow JSON from client
        data = await websocket.receive_json()
        workflow_json = data.get("workflow_json")
        user_id = data.get("user_id")
        thread_id = data.get("thread_id")  # Optional: continue existing thread
        human_in_loop = data.get("human_in_loop", False)  # HIL toggle from UI

        if not workflow_json:
            await websocket.send_json({
                "type": "error",
                "error": "No workflow_json provided"
            })
            await websocket.close()
            return

        execution_id = str(uuid.uuid4())
        workflow_thread_id = thread_id or f"workflow_{execution_id}"

        workflow_id = workflow_json.get("workflow_id", "unknown")
        workflow_name = workflow_json.get("name", "Unnamed Workflow")

        # Send started message
        await websocket.send_json({
            "type": "started",
            "execution_id": execution_id,
            "thread_id": workflow_thread_id,
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

        # Get user's VNC session URL for the agent to use
        vnc_url = None
        if user_id:
            try:
                vnc_manager = await get_vnc_manager()
                if vnc_manager:
                    vnc_session = await vnc_manager.get_session(user_id)
                    if vnc_session:
                        vnc_url = vnc_session.get("https_url") or vnc_session.get("service_url")
                        print(f"🖥️ Workflow WS: Using VNC URL for agent: {vnc_url}")
            except Exception as e:
                print(f"⚠️ Workflow WS: Could not get VNC session for agent: {e}")

        # Use LangGraph Client SDK for streaming with PostgreSQL persistence
        langgraph_client = get_client(url=LANGGRAPH_URL)

        # Create or get thread
        if not thread_id:
            # Create new thread for this workflow execution
            thread = await langgraph_client.threads.create()
            workflow_thread_id = thread["thread_id"]
        else:
            # Reuse existing thread
            workflow_thread_id = thread_id

        input_data = {
            "messages": [{"role": "user", "content": prompt}]
        }

        config = {
            "configurable": {
                "user_id": user_id,
                "cua_url": vnc_url,
                "use_longterm_memory": True if user_id else False
            }
        }

        # Configure interrupts if Human-in-Loop is enabled
        if human_in_loop:
            # Pause before these critical actions
            interrupt_before = [
                "comment_on_post",  # Subagent that comments
                "create_post",  # Subagent that posts
                "follow_account",  # Subagent that follows
            ]
            config["interrupt_before"] = interrupt_before
            await websocket.send_json({
                "type": "info",
                "message": f"🛡️ Human-in-Loop enabled. Will pause before: {', '.join(interrupt_before)}"
            })

        # Stream execution via LangGraph Platform - automatic PostgreSQL checkpointing!
        # NOTE: thread_id and assistant_id MUST be positional arguments (not keyword args)
        # stream_mode="messages" returns tuples of (message_chunk, metadata)
        async for chunk in langgraph_client.runs.stream(
            workflow_thread_id,  # Positional: thread_id (managed by PostgreSQL)
            "x_growth_deep_agent",  # Positional: assistant_id (from langgraph.json)
            input=input_data,
            config=config,
            stream_mode="messages"  # Stream LLM tokens + metadata
        ):
            # chunk is a tuple: (message_chunk, metadata)
            if isinstance(chunk, tuple) and len(chunk) == 2:
                msg, metadata = chunk

                # Only send AI messages (agent responses) to the user
                # Skip tool calls, tool messages, and system messages
                if hasattr(msg, 'type'):
                    msg_type = msg.type if hasattr(msg.type, '__call__') else msg.type

                    # Debug logging
                    print(f"📨 Message type: {msg_type}")
                    if hasattr(msg, 'content'):
                        content_preview = str(msg.content)[:100] if msg.content else "None"
                        print(f"   Content preview: {content_preview}")
                    if hasattr(msg, 'tool_calls'):
                        print(f"   Has tool_calls: {bool(msg.tool_calls)}")

                    # Only stream AI messages (the agent's responses)
                    # BUT filter out messages that contain tool calls
                    if msg_type == 'ai' and hasattr(msg, 'content') and msg.content:
                        # Check if this is a tool call message (AI invoking a tool)
                        has_tool_calls = hasattr(msg, 'tool_calls') and msg.tool_calls

                        if not has_tool_calls:
                            # Only send AI messages without tool calls (pure responses)
                            print(f"   ✅ Sending AI message to frontend")
                            await websocket.send_json({
                                "type": "chunk",
                                "data": msg.content
                            })
                        else:
                            print(f"   ⏭️  Skipping AI message with tool calls")
                    # Skip tool messages, tool calls, human messages, etc.

            # Handle interrupts (Human-in-Loop)
            elif hasattr(chunk, 'event') and chunk.event == 'interrupt':
                await websocket.send_json({
                    "type": "interrupt",
                    "data": {
                        "action": chunk.data.get('next', ['Unknown action'])[0] if hasattr(chunk, 'data') else "Action pending",
                        "details": chunk.data if hasattr(chunk, 'data') else None
                    }
                })

                # Wait for user approval/rejection
                approval_msg = await websocket.receive_json()
                if approval_msg.get('type') == 'approval':
                    if approval_msg.get('approved'):
                        # Resume execution
                        await langgraph_client.runs.create(
                            thread_id=workflow_thread_id,
                            assistant_id="x_growth_deep_agent",
                            input=None,
                            config=config
                        )
                    else:
                        # Cancel execution
                        await websocket.send_json({
                            "type": "error",
                            "error": "Action rejected by user"
                        })
                        break

        # Send completion message
        await websocket.send_json({
            "type": "completed",
            "execution_id": execution_id,
            "thread_id": workflow_thread_id,
            "completed_at": datetime.utcnow().isoformat()
        })

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as e:
        print(f"❌ Workflow execution error: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })
        await websocket.close()


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Parallel Universe Backend...")
    print("📡 WebSocket: ws://localhost:8001/ws/extension/{user_id}")
    print("🌐 Dashboard: http://localhost:3000")
    print("🔌 Extension will connect automatically!")
    print("🤖 LangGraph Agent: http://localhost:8124")
    uvicorn.run(app, host="0.0.0.0", port=8002)

