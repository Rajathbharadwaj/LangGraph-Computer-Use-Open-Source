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
from database.models import ScheduledPost, XAccount, CronJob, CronJobRun, User, WorkflowExecution
from sqlalchemy.orm import Session
from fastapi import Depends

# Clerk authentication imports
from clerk_auth import get_current_user
from clerk_webhooks import router as webhook_router

# Global store variable (initialized in lifespan)
store = None
_pg_pool = None  # Connection pool for PostgresStore

# Lifespan context manager for startup/shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize scheduled post executor and PostgresStore on startup"""
    global store, _pg_pool
    print("🚀 Starting Parallel Universe Backend...")

    # Initialize database tables
    try:
        from database.database import init_db
        init_db()
    except Exception as e:
        print(f"⚠️ Database initialization warning: {e}")

    # Initialize PostgresStore with a connection pool
    # This is the proper way to use PostgresStore in a long-running server
    # LangGraph uses POSTGRES_URI, backend-api uses DATABASE_URL - check both
    DB_URI = os.environ.get("POSTGRES_URI") or os.environ.get("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"
    try:
        from psycopg_pool import ConnectionPool

        # Create a connection pool (will be shared across requests)
        # Keep pool small for Cloud Run (4 workers × N instances can exhaust connections)
        # Cloud SQL default max_connections is ~100, so we use very small pools
        _pg_pool = ConnectionPool(
            conninfo=DB_URI,
            min_size=1,
            max_size=3,  # Small pool to avoid exhausting Cloud SQL connections
            timeout=10,  # Fail fast if can't get connection
            open=True  # Open the pool immediately
        )

        # Create PostgresStore with the pool
        store = PostgresStore(conn=_pg_pool)

        # Setup tables (idempotent - safe to call multiple times)
        # Wrap in try/except for concurrent worker startup race condition
        try:
            store.setup()
        except Exception as setup_err:
            if "duplicate key" in str(setup_err).lower() or "already exists" in str(setup_err).lower():
                print(f"ℹ️ PostgresStore tables already exist (concurrent setup)")
            else:
                raise
        print(f"✅ Initialized PostgresStore with connection pool")
    except Exception as e:
        print(f"⚠️ Failed to initialize PostgresStore: {e}")
        import traceback
        traceback.print_exc()
        store = None
        if _pg_pool:
            _pg_pool.close()
            _pg_pool = None

    try:
        executor = await get_executor()
        print(f"✅ Scheduled post executor initialized with {len(executor.get_scheduled_posts())} pending posts")
    except Exception as e:
        print(f"❌ Failed to initialize scheduled post executor: {e}")
        import traceback
        traceback.print_exc()

    # Initialize cron job executor
    try:
        from cron_job_executor import get_cron_executor
        cron_executor = await get_cron_executor()
        print(f"✅ Cron job executor initialized with {len(cron_executor.scheduled_jobs)} active jobs")
    except Exception as e:
        print(f"❌ Failed to initialize cron executor: {e}")
        import traceback
        traceback.print_exc()

    print("📡 WebSocket: ws://localhost:8001/ws/extension/{user_id}")
    print("🌐 Dashboard: http://localhost:3000")
    print("🔌 Extension will connect automatically!")
    print(f"🤖 LangGraph Agent: {os.getenv('LANGGRAPH_URL', 'http://localhost:8124')}")

    yield

    # Shutdown
    print("🛑 Shutting down...")

    # Clean up connection pool
    if _pg_pool is not None:
        try:
            _pg_pool.close()
            print("✅ PostgresStore connection pool closed")
        except Exception as e:
            print(f"⚠️ Error closing connection pool: {e}")

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

# Note: PostgresStore is initialized in the lifespan handler above
# The global 'store' variable is set there


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

        await vnc_manager.disconnect()

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
async def generate_preview(data: dict, clerk_user_id: str = Depends(get_current_user)):
    """
    Generate a preview post/comment in the user's style

    IMPORTANT: Uses authenticated clerk_user_id from JWT token for multi-tenancy isolation

    Request body:
    {
        "content_type": "post" or "comment",
        "context": "What to write about or reply to",
        "feedback": "Optional previous feedback to incorporate"
    }
    """
    try:
        content_type = data.get("content_type", "post")
        context = data.get("context", "")
        feedback = data.get("feedback", "")

        if not clerk_user_id or not context:
            return {"success": False, "error": "Missing authentication or context"}

        print(f"🎨 Generating {content_type} preview for authenticated user: {clerk_user_id}")

        # Initialize style manager with AUTHENTICATED clerk_user_id from JWT
        # This ensures users can only generate content based on THEIR OWN posts
        from x_writing_style_learner import XWritingStyleManager
        style_manager = XWritingStyleManager(store, clerk_user_id)
        
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
async def save_feedback(data: dict, clerk_user_id: str = Depends(get_current_user)):
    """
    Save user feedback about generated content for style refinement

    IMPORTANT: Uses authenticated clerk_user_id from JWT token for multi-tenancy isolation

    Request body:
    {
        "feedback": "Make it more casual",
        "original_content": "The generated content",
        "context": "What it was about"
    }
    """
    try:
        feedback_text = data.get("feedback", "")
        original_content = data.get("original_content", "")
        context = data.get("context", "")

        if not clerk_user_id or not feedback_text:
            return {"success": False, "error": "Missing authentication or feedback"}

        print(f"💬 Saving feedback for authenticated user: {clerk_user_id}")

        # Store feedback in the store using AUTHENTICATED clerk_user_id
        namespace = (clerk_user_id, "style_feedback")
        feedback_id = str(uuid.uuid4())

        feedback_data = {
            "feedback_id": feedback_id,
            "user_id": clerk_user_id,
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
async def agent_create_post(data: dict, clerk_user_id: str = Depends(get_current_user)):
    """
    Generate a styled post and publish it to X via the Docker VNC extension.

    IMPORTANT: Uses authenticated clerk_user_id from JWT for style generation and user isolation

    Request body:
    {
        "user_id": "user_xxx",  // Extension user ID (for posting via extension)
        "context": "What to write about",
        "post_text": "Optional: pre-generated text to post directly"
    }

    If post_text is provided, it will be posted directly.
    Otherwise, content will be generated using the AUTHENTICATED user's writing style.
    """
    try:
        extension_user_id = data.get("user_id")  # Extension user ID for posting
        context = data.get("context", "")
        post_text = data.get("post_text", "")

        if not extension_user_id:
            return {"success": False, "error": "Missing extension user_id"}

        print(f"📝 Creating post for authenticated user: {clerk_user_id}, extension_id: {extension_user_id}")

        # If no post_text provided, generate it using AUTHENTICATED user's style
        if not post_text:
            if not context:
                return {"success": False, "error": "Missing context or post_text"}

            print(f"🎨 Generating styled post for authenticated user: {clerk_user_id}")

            # Initialize style manager with AUTHENTICATED clerk_user_id
            # This ensures content is generated based on THIS user's posts only
            from x_writing_style_learner import XWritingStyleManager
            style_manager = XWritingStyleManager(store, clerk_user_id)
            
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
        print(f"📤 Sending post to extension backend for extension user: {extension_user_id}")

        import requests
        response = requests.post(
            f"{EXTENSION_BACKEND_URL}/extension/create-post",
            json={
                "post_text": post_text,
                "user_id": extension_user_id
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


@app.post("/api/posts/cleanup-duplicates")
async def cleanup_duplicate_posts(user_id: str = Depends(get_current_user)):
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

@app.get("/api/vnc/session")
async def get_vnc_session_by_user_id(user_id: str = Depends(get_current_user)):
    """
    Internal endpoint for LangGraph middleware to get VNC session URL by user ID.
    No authentication required for internal service-to-service calls.
    """
    try:
        print(f"🔍 [Internal] Fetching VNC session for user: {user_id}")

        # Get VNC manager
        vnc_manager = await get_vnc_manager()

        if not vnc_manager:
            print(f"⚠️ [Internal] No VNC manager available")
            return {"success": False, "error": "VNC manager not available"}

        # Get session from Redis
        session = await vnc_manager.get_session(user_id)

        if not session:
            print(f"⚠️ [Internal] No VNC session found for user {user_id}")
            return {"success": False, "error": "No VNC session found"}

        https_url = session.get("https_url") or session.get("service_url")

        if not https_url:
            print(f"⚠️ [Internal] VNC session exists but has no URL")
            return {"success": False, "error": "VNC session has no URL"}

        print(f"✅ [Internal] Found VNC URL: {https_url}")

        return {
            "success": True,
            "https_url": https_url,
            "service_url": session.get("service_url"),
            "session_id": session.get("session_id")
        }

    except Exception as e:
        print(f"❌ [Internal] Error fetching VNC session: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}

@app.get("/api/posts/count/{username}")
async def get_posts_count(username: str, user_id: str = Depends(get_current_user)):
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

@app.get("/api/posts")
async def get_user_posts(user_id: str = Depends(get_current_user)):
    """Get stored posts for authenticated user (from PostgreSQL database)"""
    try:
        # First try PostgreSQL database (most reliable source)
        from database.models import UserPost, XAccount
        from database.database import SessionLocal

        db = SessionLocal()
        try:
            # Get the user's X account by user_id (correct column name)
            x_account = db.query(XAccount).filter(XAccount.user_id == user_id).first()

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
async def extension_status(user_id: str = Depends(get_current_user)):
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
                        "users": users_with_info,
                        "users_with_info": users_with_info  # Include both field names for compatibility
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
        "users": users_with_cookies,
        "users_with_info": users_with_cookies  # Include both field names for compatibility
    }


@app.delete("/api/extension/disconnect/{user_id}")
async def extension_disconnect(user_id: str, auth_user_id: str = Depends(get_current_user)):
    """
    Disconnect a user's X account by clearing their cookies from the extension backend.
    This proxies the request to the extension backend service.

    Args:
        user_id: Clerk user ID to disconnect
    """
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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


@app.get("/api/activity/recent")
async def get_recent_activity(user_id: str = Depends(get_current_user), limit: int = 50):
    """
    Get recent activity logs for a user from BOTH ActivityLogger and /memories/action_history.json.

    Checks TWO sources:
    1. ActivityLogger namespace (user_id, "activity") - structured activity logs
    2. /memories/action_history.json in (user_id, "filesystem") - file-based history

    Args:
        user_id: User ID to get activity for
        limit: Maximum number of activities to return (default: 50)

    Returns:
        List of activity objects sorted by timestamp (newest first)
    """
    try:
        if not store:
            return {"success": False, "error": "Store not initialized", "activities": [], "count": 0}

        all_activities = []

        # SOURCE 1: ActivityLogger namespace (user_id, "activity")
        activity_namespace = (user_id, "activity")
        print(f"🔍 [Activity API] Checking ActivityLogger namespace: {activity_namespace}")

        try:
            items = list(store.search(activity_namespace, limit=limit))
            print(f"  ✓ Found {len(items)} items from ActivityLogger")

            if items:
                print(f"  📋 Sample activity item: {items[0].value if items else 'none'}")

            for item in items:
                # ActivityLogger format: { id, timestamp, action_type, status, details, target }
                all_activities.append(item.value)
        except Exception as e:
            print(f"  ⚠️ ActivityLogger error: {e}")
            import traceback
            traceback.print_exc()

        # SOURCE 2: /memories/action_history.json in filesystem namespace
        filesystem_namespace = (user_id, "filesystem")
        print(f"🔍 [Activity API] Checking /memories/action_history.json in namespace: {filesystem_namespace}")

        try:
            item = store.get(filesystem_namespace, "/memories/action_history.json")

            if item and item.value:
                print(f"  ✓ Found /memories/action_history.json")
                action_history = item.value

                # Extract actions from file format
                actions = []
                if isinstance(action_history, dict):
                    if "content" in action_history:
                        import json
                        content = action_history["content"]
                        if isinstance(content, list):
                            content_str = "\n".join(content)
                            history_data = json.loads(content_str)
                        elif isinstance(content, str):
                            history_data = json.loads(content)
                        else:
                            history_data = content
                    else:
                        history_data = action_history

                    if isinstance(history_data, dict) and "actions" in history_data:
                        actions = history_data["actions"]
                    elif isinstance(history_data, list):
                        actions = history_data

                print(f"  ✓ Extracted {len(actions)} actions from file")

                # Convert to ActivityLogger format
                for idx, action in enumerate(actions):
                    timestamp = action.get("timestamp", "")
                    action_type = action.get("action", "unknown")

                    normalized = {
                        "id": f"file_{action_type}_{timestamp}_{idx}",
                        "timestamp": timestamp,
                        "action_type": action_type,
                        "status": "success",
                        "target": action.get("post_author", ""),
                        "details": {
                            "content": action.get("post_content_snippet", ""),
                            "post_url": action.get("post_url", ""),
                        }
                    }
                    all_activities.append(normalized)
            else:
                print(f"  ⚠️ No /memories/action_history.json found")
        except Exception as e:
            print(f"  ⚠️ Filesystem read error: {e}")

        # Combine and sort all activities
        if not all_activities:
            print(f"⚠️  [Activity API] No activities found from any source for user {user_id}")
            return {
                "success": True,
                "activities": [],
                "count": 0
            }

        # Sort by timestamp (newest first)
        all_activities.sort(
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )

        # Limit results
        limited_activities = all_activities[:limit]

        print(f"✅ [Activity API] Returning {len(limited_activities)} activities from {len(all_activities)} total")

        return {
            "success": True,
            "activities": limited_activities,
            "count": len(limited_activities)
        }

    except Exception as e:
        print(f"❌ [Activity API] Error fetching recent activity: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e),
            "activities": [],
            "count": 0
        }


# WebSocket endpoint for real-time activity updates
@app.websocket("/ws/activity/{user_id}")
async def activity_websocket(websocket: WebSocket, user_id: str):
    """
    WebSocket endpoint for streaming real-time activity updates
    """
    await websocket.accept()

    try:
        # Keep connection alive and send updates when activities change
        # For now, just keep connection open - frontend can poll or we can add pub/sub later
        while True:
            # Wait for ping from client
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_text("keepalive")
    except WebSocketDisconnect:
        print(f"🔌 [Activity WS] Client {user_id} disconnected")
    except Exception as e:
        print(f"❌ [Activity WS] Error: {e}")


# LEGACY ENDPOINT - For backwards compatibility with /memories/action_history.json format
@app.get("/api/activity/legacy")
async def get_legacy_activity(user_id: str = Depends(get_current_user), limit: int = 50):
    """
    LEGACY: Get activity from /memories/action_history.json (old format)

    This is kept for backwards compatibility but should not be used for new code.
    Use /api/activity/recent/{user_id} instead which reads from ActivityLogger namespace.
    """
    try:
        if not store:
            return {"success": False, "error": "Store not initialized", "activities": [], "count": 0}

        # Read from old location
        namespace = (user_id, "filesystem")
        item = store.get(namespace, "/memories/action_history.json")

        if not item:
            return {
                "success": True,
                "activities": [],
                "count": 0
            }

        action_history = item.value

        # Extract actions from the stored format
        activities = []
        if isinstance(action_history, dict):
            # Check if it's a file object with content field
            if "content" in action_history:
                import json
                content = action_history["content"]
                if isinstance(content, list):
                    content_str = "\n".join(content)
                    history_data = json.loads(content_str)
                elif isinstance(content, str):
                    history_data = json.loads(content)
                else:
                    history_data = content
            else:
                history_data = action_history

            if isinstance(history_data, dict) and "actions" in history_data:
                activities = history_data["actions"]
            elif isinstance(history_data, list):
                # If it's already a list of actions
                activities = history_data

        # Normalize and sort activities
        normalized_activities = []
        if activities:
            for idx, activity in enumerate(activities):
                # Transform to match frontend ActivityItem interface
                # Frontend expects: id, timestamp, action_type, status, target?, details{}
                timestamp = activity.get("timestamp", "")
                action = activity.get("action", "unknown")

                # Clean post URL - don't include if it's invalid
                post_url = activity.get("post_url", "")
                if "unknown" in post_url or not post_url.startswith("https://"):
                    post_url = ""  # Don't show invalid URLs

                normalized = {
                    "id": f"{action}_{timestamp}_{idx}",  # Create unique ID
                    "timestamp": timestamp,
                    "action_type": action,  # Frontend uses "action_type" not "action"
                    "status": "success",  # Mark completed actions as success
                    "target": activity.get("post_author", ""),
                    "details": {
                        "content": activity.get("post_content_snippet", ""),
                        "post_url": post_url,
                    }
                }
                normalized_activities.append(normalized)

            # Sort by timestamp (newest first) and limit
            normalized_activities.sort(
                key=lambda x: x.get("timestamp", ""),
                reverse=True
            )
            normalized_activities = normalized_activities[:limit]

        return {
            "success": True,
            "activities": normalized_activities,
            "count": len(normalized_activities)
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

@app.post("/api/social-graph/validate")
async def validate_discovery_ready(user_id: str = Depends(get_current_user)):
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

                # Find user with cookies - SECURITY: MUST filter by authenticated user_id
                user_with_cookies = None
                print(f"🔐 [MULTI-TENANCY] validate_discovery_ready: Looking for cookies for user: {user_id}")
                for user_info in status_data.get("users_with_info", []):
                    user_info_id = user_info.get("userId")
                    # SECURITY: Only accept cookies belonging to the authenticated user
                    if user_info_id == user_id and user_info.get("hasCookies") and user_info.get("username"):
                        user_with_cookies = user_info
                        print(f"✅ [MULTI-TENANCY] Found cookies for authenticated user: {user_info_id} (@{user_info.get('username')})")
                        break
                    elif user_info.get("hasCookies"):
                        print(f"⚠️ [MULTI-TENANCY] Skipping cookies for different user: {user_info_id} (@{user_info.get('username')})")

                if not user_with_cookies:
                    return {
                        "success": False,
                        "error": f"No X account connected for your account. Please open x.com in your browser with the extension installed. (Looking for user: {user_id})",
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
async def smart_discover_competitors(user_id: str, auth_user_id: str = Depends(get_current_user)):
    """
    PRODUCTION-READY smart discovery with automatic fallback and validation.

    Flow:
    1. Validate authentication first
    2. Check for cached data (< 7 days old)
    3. Reuse following list if available (< 24 hours)
    4. Run optimized discovery if we have candidate pool
    5. Fall back to standard discovery if needed
    """
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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

                # SECURITY: MUST filter by authenticated user_id to prevent cross-user data leakage
                print(f"🔐 [MULTI-TENANCY] smart_discover: Looking for cookies for user: {user_id}")
                for user_info in status_data.get("users_with_info", []):
                    user_info_id = user_info.get("userId")
                    # SECURITY: Only accept cookies belonging to the authenticated user
                    if user_info_id == user_id and user_info.get("hasCookies") and user_info.get("username"):
                        user_with_cookies = user_info
                        print(f"✅ [MULTI-TENANCY] Found cookies for authenticated user: {user_info_id} (@{user_info.get('username')})")
                        break
                    elif user_info.get("hasCookies"):
                        print(f"⚠️ [MULTI-TENANCY] Skipping cookies for different user: {user_info_id} (@{user_info.get('username')})")

                if not user_with_cookies:
                    return {
                        "success": False,
                        "error": f"No X account connected for your account. Please open x.com in your browser with the extension installed. (Looking for user: {user_id})",
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
async def cancel_discovery(user_id: str, auth_user_id: str = Depends(get_current_user)):
    """Cancel ongoing discovery and save partial results"""
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Set cancellation flag in store
        cancel_namespace = (user_id, "discovery_control")
        store.put(cancel_namespace, "cancel_flag", {"cancelled": True, "timestamp": datetime.utcnow().isoformat()})

        return {"success": True, "message": "Cancellation requested. Discovery will stop gracefully."}
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.get("/api/social-graph/progress/{user_id}")
async def get_discovery_progress(user_id: str, auth_user_id: str = Depends(get_current_user)):
    """Get current discovery progress"""
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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


@app.post("/api/social-graph/reset-progress")
async def reset_discovery_progress(user_id: str = Depends(get_current_user)):
    """Reset/clear the discovery progress state (clears stuck locks)"""
    try:
        if not store:
            return {"success": False, "error": "Store not initialized"}

        progress_namespace = (user_id, "discovery_progress")
        # Clear the progress by setting to idle state
        store.put(progress_namespace, "current", {
            "stage": "idle",
            "status": "idle",
            "current": 0,
            "total": 0
        })

        # Also clear any cancel flags
        cancel_namespace = (user_id, "discovery_control")
        store.put(cancel_namespace, "cancel_flag", {"cancelled": False})

        print(f"✅ Reset progress state for user {user_id}")
        return {
            "success": True,
            "message": "Progress state reset. You can now start a new scraping/discovery."
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@app.post("/api/social-graph/discover-optimized")
async def discover_competitors_optimized(user_handle: str, user_id: str = Depends(get_current_user)):
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


@app.post("/api/social-graph/discover-followers")
async def discover_competitors_from_followers(user_handle: str, user_id: str = Depends(get_current_user)):
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


@app.post("/api/social-graph/discover-native")
async def discover_competitors_native(user_handle: str, user_id: str = Depends(get_current_user)):
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

        # CRITICAL: Fail early if store is not available - prevents data loss!
        if store is None:
            print("❌ CRITICAL: PostgresStore is None - cannot save discovery results!")
            return {
                "success": False,
                "error": "Database connection unavailable. Please try again in a moment.",
                "action": "retry",
                "detail": "PostgresStore not initialized - results would be lost if discovery runs"
            }

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


@app.post("/api/social-graph/discover")
async def discover_competitors(user_handle: str, user_id: str = Depends(get_current_user)):
    """Standard competitor discovery with cancellation support"""

    # CRITICAL: Fail early if store is not available - prevents data loss!
    if store is None:
        print("❌ CRITICAL: PostgresStore is None - cannot save discovery results!")
        return {
            "success": False,
            "error": "Database connection unavailable. Please try again in a moment.",
            "action": "retry",
            "detail": "PostgresStore not initialized - results would be lost if discovery runs"
        }

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
        # SECURITY: MUST filter by authenticated user_id to prevent cross-user data leakage
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{EXTENSION_BACKEND_URL}/status") as resp:
                status_data = await resp.json()
                user_with_cookies = None
                print(f"🔐 [MULTI-TENANCY] discover_competitors: Looking for cookies for user: {user_id}")
                for user_info in status_data.get("users_with_info", []):
                    user_info_id = user_info.get("userId")
                    # SECURITY: Only accept cookies belonging to the authenticated user
                    if user_info_id == user_id and user_info.get("hasCookies") and user_info.get("username"):
                        user_with_cookies = user_info
                        print(f"✅ [MULTI-TENANCY] Found cookies for authenticated user: {user_info_id} (@{user_info.get('username')})")
                        break
                    elif user_info.get("hasCookies"):
                        print(f"⚠️ [MULTI-TENANCY] Skipping cookies for different user: {user_info_id} (@{user_info.get('username')})")

                if not user_with_cookies:
                    return {
                        "success": False,
                        "error": f"No X account connected for your account. Please connect your X account via the Chrome extension first. (Looking for user: {user_id})",
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


@app.post("/api/social-graph/analyze-content")
async def analyze_competitor_content(user_id: str = Depends(get_current_user)):
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


async def _release_redis_lock(redis_client, lock_key: str, request_id: str, user_id: str):
    """Helper function to safely release Redis lock"""
    try:
        if redis_client:
            # Only delete if we still own the lock (check request_id)
            current_lock = await redis_client.get(lock_key)
            if current_lock == request_id:
                await redis_client.delete(lock_key)
                print(f"🔓 Released scraping lock for user {user_id}")
            else:
                print(f"⚠️ Lock already released or taken over by another request")
    except Exception as unlock_error:
        print(f"⚠️ Failed to release lock: {unlock_error}")
    finally:
        try:
            if redis_client:
                await redis_client.aclose()
        except Exception as close_error:
            print(f"⚠️ Failed to close Redis connection: {close_error}")


@app.post("/api/social-graph/scrape-posts/{user_id}")
async def scrape_competitor_posts(
    user_id: str,
    force_rescrape: bool = Query(False),
    request: Request = None,
    auth_user_id: str = Depends(get_current_user)
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
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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

        # Check if store is initialized
        if store is None:
            print("❌ CRITICAL: PostgresStore is None")
            return {
                "success": False,
                "error": "Database connection unavailable",
            }

        # Get per-user VNC client (enables multi-user scaling)
        user_client = await get_user_vnc_client(user_id)

        # Constants for lock management
        STALE_LOCK_TIMEOUT_SECONDS = 600  # 10 minutes
        MAX_COMPETITORS_TO_SCRAPE = 20

        # Distributed lock using Redis (atomic SETNX operation)
        # This prevents race conditions that can occur with store.put() + store.get()
        import time
        import uuid

        redis_host = os.getenv("REDIS_HOST", "localhost")
        redis_port = int(os.getenv("REDIS_PORT", "6379"))

        request_id = str(uuid.uuid4())
        lock_key = f"lock:scrape_posts:{user_id}"
        redis_client = None

        try:
            # Create Redis client with context manager for proper cleanup
            redis_client = aioredis.Redis(host=redis_host, port=redis_port, decode_responses=True)

            # Atomic lock acquisition with auto-expiration
            # Returns True if lock acquired, False if already held
            lock_acquired = await redis_client.set(
                lock_key,
                request_id,
                nx=True,  # Only set if not exists (atomic check-and-set)
                ex=STALE_LOCK_TIMEOUT_SECONDS  # Auto-expire to prevent stuck locks
            )

            if not lock_acquired:
                # Check who owns the lock (for debugging)
                existing_lock = await redis_client.get(lock_key)
                print(f"⚠️ Scraping already in progress (lock held by request {existing_lock})")
                return {
                    "success": False,
                    "error": "Scraping is already in progress. Please wait for it to complete."
                }

            print(f"🔒 Acquired scraping lock for user {user_id} (request {request_id})")

        except Exception as lock_error:
            print(f"❌ Failed to acquire Redis lock: {lock_error}")
            return {
                "success": False,
                "error": "Failed to acquire lock. Please try again."
            }

        # Store progress state (non-critical, for UI updates)
        progress_namespace = (user_id, "discovery_progress")
        current_time = time.time()

        builder = SocialGraphBuilder(store, user_id)
        graph = builder.get_graph()

        if not graph:
            # Release lock before returning
            await _release_redis_lock(redis_client, lock_key, request_id, user_id)
            return {
                "success": False,
                "error": "No graph data found. Run discovery first."
            }

        # Get all competitors (from raw data)
        all_competitors = graph.get("all_competitors_raw", [])

        if not all_competitors:
            # Release lock before returning
            await _release_redis_lock(redis_client, lock_key, request_id, user_id)
            return {
                "success": False,
                "error": "No competitors found"
            }

        # If filtered usernames provided, only scrape those
        if filtered_usernames:
            top_competitors = [c for c in all_competitors if c['username'] in filtered_usernames]
            print(f"📝 Scraping {len(top_competitors)} filtered competitors")
        else:
            # Sort by overlap and take top N to avoid scraping for hours
            top_competitors = sorted(
                all_competitors,
                key=lambda x: x['overlap_percentage'],
                reverse=True
            )[:MAX_COMPETITORS_TO_SCRAPE]

        # Initialize scraper with per-user client
        scraper = SocialGraphScraper(user_client)

        # Scrape posts for competitors that don't have them
        scraped_count = 0
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

        # CRITICAL: Release Redis lock FIRST before updating progress state
        # This prevents race condition where another request acquires lock
        # but sees stale "scraping" status
        await _release_redis_lock(redis_client, lock_key, request_id, user_id)

        # THEN update progress state (non-critical, for UI only)
        try:
            store.put(progress_namespace, "current", {
                "stage": "idle",
                "status": "complete",
                "current": 0,
                "total": 0,
                "message": f"Scraped {scraped_count} competitors"
            })
        except Exception as progress_error:
            print(f"⚠️ Failed to update progress state: {progress_error}")

        return {
            "success": True,
            "graph": graph,
            "message": f"✅ Scraped posts for {scraped_count} competitors"
        }

    except Exception as e:
        print(f"❌ Post scraping failed: {e}")
        import traceback
        traceback.print_exc()

        # Release Redis lock on error FIRST
        try:
            await _release_redis_lock(redis_client, lock_key, request_id, user_id)
        except Exception as unlock_error:
            print(f"⚠️ Failed to release lock helper: {unlock_error}")

        # THEN clear progress state (non-critical)
        try:
            progress_namespace = (user_id, "discovery_progress")
            store.put(progress_namespace, "current", {
                "stage": "idle",
                "status": "error",
                "current": 0,
                "total": 0,
                "error": str(e)
            })
        except Exception as clear_error:
            print(f"⚠️ Failed to clear progress state: {clear_error}")

        return {
            "success": False,
            "error": str(e)
        }


@app.post("/api/social-graph/refilter")
async def refilter_competitors(min_threshold: int = 50, user_id: str = Depends(get_current_user)):
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
async def generate_content_insights(user_id: str, auth_user_id: str = Depends(get_current_user)):
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
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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
async def get_content_insights(user_id: str, auth_user_id: str = Depends(get_current_user)):
    """
    Get cached content insights if available.

    Args:
        user_id: User identifier

    Returns:
        Cached content insights or null
    """
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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
    auth_user_id: str = Depends(get_current_user),
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
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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
async def reset_relevancy_analysis(user_id: str, auth_user_id: str = Depends(get_current_user)):
    """Reset relevancy analysis state to re-analyze all competitors from scratch"""
    # SECURITY: Verify path user_id matches authenticated user
    if user_id != auth_user_id:
        raise HTTPException(status_code=403, detail="Access denied")

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


@app.get("/api/social-graph")
async def get_social_graph(user_id: str = Depends(get_current_user)):
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


@app.get("/api/competitors")
async def list_competitors(limit: int = 50, user_id: str = Depends(get_current_user)):
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


@app.get("/api/competitor/{username}")
async def get_competitor(username: str, user_id: str = Depends(get_current_user)):
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
                        config={"configurable": {
                            "user_id": user_id,
                            "cua_url": vnc_url,
                            # Extract host and port for screenshot middleware
                            "x-cua-host": vnc_url.split("://")[1].split(":")[0] if vnc_url and "://" in vnc_url else None,
                            "x-cua-port": vnc_url.split(":")[-1].rstrip("/") if vnc_url and ":" in vnc_url else None,
                        }},
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

    print(f"🔐 [Cookie Injection] Clerk user: {clerk_user_id}, Extension user: {extension_user_id}")
    print(f"🔍 [Cookie Injection] Looking up VNC session for Clerk user: {clerk_user_id}")

    # Get or create the user's VNC session from Redis
    vnc_manager = await get_vnc_manager()
    vnc_session = await vnc_manager.get_session(clerk_user_id)
    print(f"🔍 [Cookie Injection] VNC session lookup result: {vnc_session is not None}")

    if not vnc_session or not vnc_session.get("https_url"):
        print(f"⚠️ No VNC session found for Clerk user {clerk_user_id}, creating new session...")
        try:
            # Auto-create VNC session for the user
            vnc_session = await vnc_manager.get_or_create_session(clerk_user_id)
            print(f"✅ Created new VNC session for user {clerk_user_id}")
        except Exception as e:
            print(f"❌ Failed to create VNC session: {e}")
            return {"success": False, "error": f"Failed to create VNC session: {str(e)}"}

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
async def scrape_posts_docker(
    data: dict,
    clerk_user_id: str = Depends(get_current_user)
):
    """
    Use Docker VNC browser to scrape authenticated user's X posts (doesn't disturb user)
    Optimized: Only scrapes if new posts are available
    """
    import aiohttp

    # SECURITY: Use ONLY authenticated Clerk user ID, ignore any user_id from request body
    target_count = data.get("targetCount", 50)
    min_posts_threshold = 30  # Minimum posts we want to have

    print(f"🔍 Scraping for authenticated Clerk user: {clerk_user_id}")
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
        # SECURITY: MUST filter by authenticated clerk_user_id to prevent cross-user data leakage
        username = None
        extension_user_id = None
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{EXTENSION_BACKEND_URL}/status") as resp:
                    status_data = await resp.json()
                    if status_data.get("users_with_info"):
                        print(f"🔐 [MULTI-TENANCY] Looking for cookies belonging to authenticated user: {clerk_user_id}")
                        for user_info in status_data["users_with_info"]:
                            user_info_id = user_info.get("userId")
                            # SECURITY: Only use cookies belonging to the AUTHENTICATED user
                            if user_info_id == clerk_user_id and user_info.get("username") and user_info.get("hasCookies"):
                                username = user_info["username"]
                                extension_user_id = user_info["userId"]
                                print(f"✅ [MULTI-TENANCY] Found cookies for authenticated user: {extension_user_id} (@{username})")
                                break
                            elif user_info.get("hasCookies"):
                                print(f"⚠️ [MULTI-TENANCY] Skipping cookies for different user: {user_info_id} (@{user_info.get('username')}) - not authenticated user")
            except Exception as e:
                print(f"⚠️ Could not fetch username from extension backend: {e}")

        if not username or not extension_user_id:
            print(f"❌ [MULTI-TENANCY] No cookies found for authenticated user {clerk_user_id}")
            return {
                "success": False,
                "error": f"No X account connected for your account. Please connect your X account first. (Looking for user: {clerk_user_id})"
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
                        print(f"   ⚠️ No WebSocket connection found for user {clerk_user_id}")
                    
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

        # Also update in-memory cache (using clerk_user_id)
        if clerk_user_id not in user_posts:
            user_posts[clerk_user_id] = []

        existing_contents = {p.get("content") for p in user_posts[clerk_user_id]}
        for post in new_posts:
            if post.get("content") not in existing_contents:
                user_posts[clerk_user_id].append(post)
        
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
                        "total": len(user_posts[clerk_user_id]),
                        "username": username,
                        "message": "Already up to date! No new posts found."
                    })
                except Exception as ws_err:
                    print(f"   ⚠️ Failed to send message: {ws_err}")

            return {
                "success": True,
                "imported": 0,
                "total": len(user_posts[clerk_user_id]),
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

        if websocket:
            try:
                await websocket.send_json({
                    "type": "IMPORT_COMPLETE",
                    "imported": len(new_posts),
                    "total": len(user_posts[clerk_user_id]),
                    "username": username
                })
                print(f"   📤 Sent completion message")
            except Exception as ws_err:
                print(f"   ⚠️ Failed to send completion message: {ws_err}")

        return {
            "success": True,
            "imported": len(new_posts),
            "total": len(user_posts[clerk_user_id]),
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

@app.get("/api/debug/check-stored-posts")
async def debug_check_stored_posts(
    user_id: str = Depends(get_current_user)
):
    """
    DEBUG: Check what posts are stored for the authenticated user
    """
    from langgraph.store.postgres import PostgresStore

    conn_string = os.environ.get("POSTGRES_URI") or os.environ.get("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"

    with PostgresStore.from_conn_string(conn_string) as store:
        posts_namespace = (user_id, "writing_samples")
        stored_posts = list(store.search(posts_namespace, limit=10))

        return {
            "success": True,
            "clerk_user_id": user_id,
            "total_posts_found": len(stored_posts),
            "sample_posts": [
                {
                    "content": p.value.get("content", "")[:200],
                    "user_id": p.value.get("user_id"),
                    "timestamp": p.value.get("timestamp")
                }
                for p in stored_posts[:5]
            ]
        }

@app.delete("/api/debug/delete-all-posts")
async def debug_delete_all_posts(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    DEBUG: Delete ALL posts stored for the authenticated user from BOTH storage locations
    WARNING: This is irreversible!

    Deletes from:
    1. LangGraph Store (writing_samples namespace) - used for AI style learning
    2. Postgres UserPost table - used for post count/metadata
    """
    from langgraph.store.postgres import PostgresStore
    from database.models import UserPost

    conn_string = os.environ.get("POSTGRES_URI") or os.environ.get("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"

    # ============= DELETE FROM LANGGRAPH STORE =============
    langgraph_deleted = 0
    with PostgresStore.from_conn_string(conn_string) as store:
        posts_namespace = (user_id, "writing_samples")

        # Get ALL posts without limit
        all_posts = list(store.search(posts_namespace, limit=10000))

        # Delete each one
        for post in all_posts:
            store.delete(posts_namespace, post.key)
            langgraph_deleted += 1

        print(f"🗑️ Deleted {langgraph_deleted} posts from LangGraph store for user_id: {user_id}")

    # ============= DELETE FROM POSTGRES DATABASE =============
    postgres_deleted = 0
    try:
        # Get all X accounts for this user
        x_accounts = db.query(XAccount).filter(XAccount.user_id == user_id).all()

        for x_account in x_accounts:
            # Delete all UserPosts for this X account
            posts_to_delete = db.query(UserPost).filter(UserPost.x_account_id == x_account.id).all()
            postgres_deleted += len(posts_to_delete)

            for post in posts_to_delete:
                db.delete(post)

            print(f"🗑️ Deleted {len(posts_to_delete)} posts from Postgres for @{x_account.username}")

        db.commit()
    except Exception as e:
        db.rollback()
        print(f"❌ Error deleting from Postgres: {e}")

    return {
        "success": True,
        "clerk_user_id": user_id,
        "langgraph_deleted": langgraph_deleted,
        "postgres_deleted": postgres_deleted,
        "total_deleted": langgraph_deleted + postgres_deleted,
        "message": f"Deleted {langgraph_deleted} from LangGraph + {postgres_deleted} from Postgres = {langgraph_deleted + postgres_deleted} total posts"
    }

@app.post("/api/import-posts")
async def import_posts(
    data: dict,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Import authenticated user's X posts for writing style learning

    SECURITY: Validates that posts being imported match the user's connected X account
    """
    # Use authenticated user_id instead of untrusted data
    posts = data.get("posts", [])
    x_handle_from_request = data.get("x_handle")  # X handle from the extension

    if not posts:
        return {
            "success": False,
            "error": "No posts provided"
        }

    # ==================== SECURITY CHECK ====================
    # Verify that the X handle matches the authenticated user's connected account
    x_account = db.query(XAccount).filter(
        XAccount.user_id == user_id,
        XAccount.is_connected == True
    ).first()

    if x_account:
        # User has a connected X account - verify it matches
        if x_handle_from_request and x_handle_from_request.lower() != x_account.username.lower():
            print(f"⚠️ SECURITY ALERT: User {user_id} attempted to import posts from @{x_handle_from_request}")
            print(f"   But their connected X account is @{x_account.username}")
            return {
                "success": False,
                "error": f"Security Error: You are trying to import posts from @{x_handle_from_request}, but your connected account is @{x_account.username}. Please import posts from your own account only."
            }
        print(f"✅ Security check passed: Importing posts for @{x_account.username} (user_id: {user_id})")
    else:
        # No X account in database yet - this might be first import
        # Store the handle for future reference
        if x_handle_from_request:
            print(f"⚠️ No X account found for user {user_id}, importing posts for @{x_handle_from_request}")
            print(f"   Creating X account entry...")
            x_account = XAccount(
                user_id=user_id,
                username=x_handle_from_request,
                is_connected=True
            )
            db.add(x_account)
            db.commit()
    # ========================================================

    # Store posts for this user
    if user_id not in user_posts:
        user_posts[user_id] = []

    # Add new posts (avoid duplicates by content)
    existing_contents = {p.get("content") for p in user_posts[user_id]}
    new_posts = [p for p in posts if p.get("content") not in existing_contents]
    user_posts[user_id].extend(new_posts)

    print(f"✅ Imported {len(new_posts)} posts for user {user_id} (@{x_handle_from_request or 'unknown'})")
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
async def like_post(data: dict, user_id: str = Depends(get_current_user)):
    """
    Endpoint called by your dashboard
    Forwards command to extension
    """
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
async def follow_user(data: dict, user_id: str = Depends(get_current_user)):
    """Follow a user"""
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
async def comment_on_post(data: dict, user_id: str = Depends(get_current_user)):
    """Comment on a post"""
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
    user_id: str = Depends(get_current_user),
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
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new scheduled post"""
    try:
        # SECURITY: Use authenticated user_id instead of request
        # Get user's primary X account
        x_account = db.query(XAccount).filter(
            XAccount.user_id == user_id,
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
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update an existing scheduled post"""
    try:
        # SECURITY: Verify post belongs to user before allowing update
        post = (
            db.query(ScheduledPost)
            .join(XAccount, ScheduledPost.x_account_id == XAccount.id)
            .filter(
                ScheduledPost.id == post_id,
                XAccount.user_id == user_id  # CRITICAL: Verify ownership
            )
            .first()
        )

        if not post:
            raise HTTPException(
                status_code=404,
                detail="Post not found or access denied"  # Don't reveal if post exists
            )

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
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a scheduled post"""
    try:
        # SECURITY: Verify post belongs to user before allowing deletion
        post = (
            db.query(ScheduledPost)
            .join(XAccount, ScheduledPost.x_account_id == XAccount.id)
            .filter(
                ScheduledPost.id == post_id,
                XAccount.user_id == user_id  # CRITICAL: Verify ownership
            )
            .first()
        )

        if not post:
            raise HTTPException(
                status_code=404,
                detail="Post not found or access denied"  # Don't reveal if post exists
            )

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
async def upload_media(
    user_id: str = Depends(get_current_user),file: UploadFile = File(...)):
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
    request: Request,
    clerk_user_id: str = Depends(get_current_user),
    count: int = 7,  # Always generate 7 for the week
    db: Session = Depends(get_db)
):
    """
    Generate weekly AI content using the Weekly Content Generator Agent

    IMPORTANT: Uses authenticated clerk_user_id from JWT token for multi-tenancy isolation

    This uses LangGraph to:
    1. Analyze user's writing style from imported posts
    2. Analyze high-quality competitor posts
    3. Conduct web research with Perplexity API
    4. Strategize content for growth
    5. Generate 7 posts for next week
    """
    try:
        # ==================== SECURITY AUDIT LOGGING ====================
        print("=" * 80)
        print("🔒 SECURITY AUDIT: AI Content Generation Request")
        print("=" * 80)
        print(f"📋 Request URL: {request.url}")
        print(f"📋 Query Params: {dict(request.query_params)}")
        print(f"🔐 Authenticated clerk_user_id from JWT: {clerk_user_id}")
        print(f"📊 Count parameter: {count}")
        print("=" * 80)
        # ================================================================

        from weekly_content_generator import generate_weekly_content
        from langgraph.store.postgres import PostgresStore

        # Get user's X account to get username
        x_account = db.query(XAccount).filter(
            XAccount.user_id == clerk_user_id,
            XAccount.is_connected == True
        ).first()

        if x_account:
            user_handle = x_account.username
            print(f"✅ Found X account in database: @{user_handle} for clerk_user_id: {clerk_user_id}")
        else:
            # Fallback: Try to get username from social graph data
            print(f"⚠️  No X account found for clerk_user_id: {clerk_user_id}, trying social graph...")
            # Use same DB_URI as main store connection (POSTGRES_URI or DATABASE_URL)
            conn_string = os.environ.get("POSTGRES_URI") or os.environ.get("DATABASE_URL") or "postgresql://postgres:password@localhost:5433/xgrowth"

            with PostgresStore.from_conn_string(conn_string) as store:
                graph_namespace = (clerk_user_id, "social_graph")
                print(f"🔍 Looking up social graph with namespace: {graph_namespace}")
                graph_item = (store.get(graph_namespace, "graph_data") or
                            store.get(graph_namespace, "latest") or
                            store.get(graph_namespace, "current"))

                if graph_item and graph_item.value.get("user_handle"):
                    user_handle = graph_item.value.get("user_handle")
                    print(f"✅ Found username from social graph: @{user_handle}")
                else:
                    print(f"❌ Could not find user_handle in social graph for clerk_user_id: {clerk_user_id}")
                    raise HTTPException(status_code=404, detail="Could not determine user's X handle")

        print(f"🚀 GENERATING CONTENT - clerk_user_id: {clerk_user_id}, user_handle: @{user_handle}")
        print(f"📝 This will use posts from @{user_handle}'s imported X posts ONLY")

        # Run the weekly content generator agent with AUTHENTICATED user_id
        generated_posts = await generate_weekly_content(
            user_id=clerk_user_id,
            user_handle=user_handle
        )

        print(f"✅ Generated {len(generated_posts)} posts")

        # Save generated posts to database as drafts for persistence
        saved_posts = []

        # Get or create x_account
        if not x_account:
            # Ensure user exists in database (in case webhook hasn't run yet)
            user = db.query(User).filter(User.id == clerk_user_id).first()
            if not user:
                user = User(
                    id=clerk_user_id,
                    email=f"{clerk_user_id}@temp.com"  # Temporary email, will be updated by webhook
                )
                db.add(user)
                db.commit()
                print(f"✅ Created user {clerk_user_id} in database")

            # Create a temporary x_account entry if it doesn't exist
            x_account = XAccount(
                user_id=clerk_user_id,
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
        error_msg = str(e) or repr(e) or "Unknown error occurred"
        print(f"❌ Error generating AI content: {error_msg}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to generate AI content: {error_msg}"
        )


# ============================================================================
# CRON JOBS API - Recurring Workflow Automation
# ============================================================================

@app.post("/api/cron-jobs")
async def create_cron_job(
    request: dict,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create a new recurring cron job for workflow automation

    Body:
    {
        "name": "Daily Reply Guy Strategy",
        "schedule": "0 9 * * *",  # Cron expression
        "workflow_id": "reply_guy_strategy",  # Optional
        "custom_prompt": "...",  # Optional (if no workflow)
        "input_config": {}  # Optional additional params
    }
    """
    try:
        from cron_job_executor import get_cron_executor

        # Ensure user exists in database (in case webhook hasn't run yet)
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            # Get email from JWT token payload
            from clerk_auth import verify_clerk_token
            from fastapi import Header
            # Create user on the fly if they don't exist
            user = User(
                id=user_id,
                email=f"{user_id}@temp.com"  # Temporary email, will be updated by webhook
            )
            db.add(user)
            db.commit()
            print(f"✅ Created user {user_id} in database")

        # Validate that at least workflow_id OR custom_prompt is provided
        workflow_id = request.get("workflow_id")
        custom_prompt = request.get("custom_prompt")

        if not workflow_id and not custom_prompt:
            raise HTTPException(
                status_code=400,
                detail="Either 'workflow_id' or 'custom_prompt' must be provided"
            )

        # Create cron job in database
        cron_job = CronJob(
            user_id=user_id,
            name=request["name"],
            schedule=request["schedule"],
            workflow_id=workflow_id,
            custom_prompt=custom_prompt,
            input_config=request.get("input_config", {}),
            is_active=True
        )
        db.add(cron_job)
        db.commit()
        db.refresh(cron_job)

        # Schedule with APScheduler
        executor = await get_cron_executor()
        executor.schedule_cron_job(cron_job)

        return {
            "cron_job_id": cron_job.id,
            "message": "Cron job created successfully"
        }
    except Exception as e:
        print(f"Error creating cron job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cron-jobs")
async def list_cron_jobs(
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all cron jobs for authenticated user"""
    try:
        cron_jobs = db.query(CronJob).filter(
            CronJob.user_id == user_id
        ).order_by(CronJob.created_at.desc()).all()

        return {
            "cron_jobs": [
                {
                    "id": job.id,
                    "name": job.name,
                    "schedule": job.schedule,
                    "workflow_id": job.workflow_id,
                    "is_active": job.is_active,
                    "last_run_at": job.last_run_at.isoformat() if job.last_run_at else None,
                    "created_at": job.created_at.isoformat()
                }
                for job in cron_jobs
            ]
        }
    except Exception as e:
        print(f"Error listing cron jobs: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/cron-jobs/{cron_job_id}")
async def delete_cron_job(
    cron_job_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a cron job"""
    try:
        from cron_job_executor import get_cron_executor

        cron_job = db.query(CronJob).filter(
            CronJob.id == cron_job_id,
            CronJob.user_id == user_id
        ).first()

        if not cron_job:
            raise HTTPException(status_code=404, detail="Cron job not found")

        # Cancel from scheduler
        executor = await get_cron_executor()
        executor.cancel_cron_job(cron_job_id)

        # Delete from database
        db.delete(cron_job)
        db.commit()

        return {"message": "Cron job deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error deleting cron job: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/cron-jobs/{cron_job_id}/runs")
async def get_cron_job_runs(
    cron_job_id: int,
    user_id: str = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = 20
):
    """Get execution history for a cron job"""
    try:
        # Verify ownership
        cron_job = db.query(CronJob).filter(
            CronJob.id == cron_job_id,
            CronJob.user_id == user_id
        ).first()

        if not cron_job:
            raise HTTPException(status_code=404, detail="Cron job not found")

        # Get runs
        runs = db.query(CronJobRun).filter(
            CronJobRun.cron_job_id == cron_job_id
        ).order_by(CronJobRun.started_at.desc()).limit(limit).all()

        return {
            "runs": [
                {
                    "id": run.id,
                    "started_at": run.started_at.isoformat(),
                    "completed_at": run.completed_at.isoformat() if run.completed_at else None,
                    "status": run.status,
                    "thread_id": run.thread_id,
                    "error_message": run.error_message
                }
                for run in runs
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting cron job runs: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/cron-jobs/debug/scheduler-status")
async def get_scheduler_status(user_id: str = Depends(get_current_user)):
    """Debug endpoint to check APScheduler status for current user's jobs"""
    try:
        from cron_job_executor import get_cron_executor
        executor = await get_cron_executor()

        # Filter jobs to only show current user's jobs
        user_jobs = {}
        for job_id, info in executor.scheduled_jobs.items():
            cron_job_id = info["cron_job_id"]

            # Look up the cron job in database to check user_id
            db = SessionLocal()
            try:
                cron_job = db.query(CronJob).filter(CronJob.id == cron_job_id).first()
                if cron_job and cron_job.user_id == user_id:
                    user_jobs[job_id] = {
                        "cron_job_id": info["cron_job_id"],
                        "name": info["name"],
                        "schedule": info["schedule"]
                    }
            finally:
                db.close()

        return {
            "scheduler_running": executor.is_running,
            "total_scheduled_jobs": len(user_jobs),
            "scheduled_jobs": user_jobs
        }
    except Exception as e:
        return {
            "error": str(e),
            "scheduler_running": False,
            "total_scheduled_jobs": 0
        }


@app.get("/api/scheduled-posts/ai-drafts")
async def get_ai_drafts(
    user_id: str = Depends(get_current_user),
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
async def run_agent(data: dict, user_id: str = Depends(get_current_user)):
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

        # Parse host and port from VNC URL
        print(f"🔍 [Backend] DEBUG: vnc_url RAW = {repr(vnc_url)}")
        cua_host = None
        cua_port = None
        if vnc_url and "://" in vnc_url:
            try:
                # Example: http://vnc-service-xyz:8080/
                after_protocol = vnc_url.split("://")[1]  # "vnc-service-xyz:8080/"
                print(f"🔍 [Backend] DEBUG: after_protocol = {repr(after_protocol)}")
                host_and_port = after_protocol.rstrip("/")  # "vnc-service-xyz:8080"
                print(f"🔍 [Backend] DEBUG: host_and_port = {repr(host_and_port)}")
                if ":" in host_and_port:
                    cua_host = host_and_port.split(":")[0]
                    cua_port = host_and_port.split(":")[1]
                else:
                    cua_host = host_and_port
                    cua_port = "80" if vnc_url.startswith("http://") else "443"
            except Exception as e:
                print(f"❌ [Backend] ERROR parsing VNC URL: {e}")

        print(f"🔍 [Backend] DEBUG: FINAL cua_host = {repr(cua_host)}")
        print(f"🔍 [Backend] DEBUG: FINAL cua_port = {repr(cua_port)}")

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
                    "x-cua-host": cua_host,
                    "x-cua-port": cua_port,
                    "x-user-id": user_id,  # For StoreBackend namespace (checked by DeepAgents)
                },
                "metadata": {
                    "x-user-id": user_id  # Store user_id in metadata for namespace isolation
                }
            }
        }
        
        # Add multitask_strategy if double-texting
        if use_rollback:
            stream_kwargs["multitask_strategy"] = "rollback"

        # DEBUG: Log what we're sending to LangGraph
        print(f"🔍 DEBUG: vnc_url = {vnc_url}")
        print(f"🔍 DEBUG: stream_kwargs['config']['configurable'] = {stream_kwargs['config']['configurable']}")

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

@app.get("/api/agent/status")
async def get_agent_status(user_id: str = Depends(get_current_user)):
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
async def get_agent_history(thread_id: str, user_id: str = Depends(get_current_user)):
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
async def get_agent_state(thread_id: str, user_id: str = Depends(get_current_user)):
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
async def create_new_thread(data: dict, user_id: str = Depends(get_current_user)):
    """
    Create a new thread for a user (starts fresh conversation)
    """
    title = data.get("title", "New Chat")
    
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

@app.get("/api/agent/threads/list")
async def list_user_threads(user_id: str = Depends(get_current_user)):
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

@app.get("/api/agent/threads")
async def get_user_thread(user_id: str = Depends(get_current_user)):
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
async def get_thread_messages(thread_id: str, user_id: str = Depends(get_current_user)):
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
async def list_workflows_endpoint(user_id: str = Depends(get_current_user)):
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
async def get_workflow_endpoint(workflow_id: str, user_id: str = Depends(get_current_user)):
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
async def execute_workflow_endpoint(workflow_json: dict, user_id: str = Depends(get_current_user), thread_id: Optional[str] = None):
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

        # Parse host and port from VNC URL (same logic as task execution)
        print(f"🔍 [Backend-Workflow] DEBUG: vnc_url RAW = {repr(vnc_url)}")
        cua_host = None
        cua_port = None
        if vnc_url and "://" in vnc_url:
            try:
                after_protocol = vnc_url.split("://")[1]
                print(f"🔍 [Backend-Workflow] DEBUG: after_protocol = {repr(after_protocol)}")
                host_and_port = after_protocol.rstrip("/")
                print(f"🔍 [Backend-Workflow] DEBUG: host_and_port = {repr(host_and_port)}")
                if ":" in host_and_port:
                    cua_host = host_and_port.split(":")[0]
                    cua_port = host_and_port.split(":")[1]
                else:
                    cua_host = host_and_port
                    cua_port = "80" if vnc_url.startswith("http://") else "443"
            except Exception as e:
                print(f"❌ [Backend-Workflow] ERROR parsing VNC URL: {e}")

        print(f"🔍 [Backend-Workflow] DEBUG: FINAL cua_host = {repr(cua_host)}")
        print(f"🔍 [Backend-Workflow] DEBUG: FINAL cua_port = {repr(cua_port)}")

        config = {
            "configurable": {
                "user_id": user_id,
                "cua_url": vnc_url,
                "use_longterm_memory": True if user_id else False,
                "x-cua-host": cua_host,
                "x-cua-port": cua_port,
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
async def get_execution_status_endpoint(execution_id: str, user_id: str = Depends(get_current_user)):
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

        # Create workflow execution record in database for persistence
        db = SessionLocal()
        workflow_execution = None
        try:
            workflow_steps = workflow_json.get("steps", [])
            workflow_execution = WorkflowExecution(
                id=execution_id,
                user_id=user_id,
                workflow_id=workflow_id,
                workflow_name=workflow_name,
                thread_id=thread_id or workflow_thread_id,
                status="running",
                total_steps=len(workflow_steps),
                current_step=0,
                completed_steps=[]
            )
            db.add(workflow_execution)
            db.commit()
            db.refresh(workflow_execution)
            print(f"✅ Created workflow execution record: {execution_id}")
        except Exception as e:
            print(f"⚠️ Failed to create workflow execution record: {e}")
            # Continue even if database fails
        finally:
            db.close()

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

        # Parse host and port from VNC URL (same logic as task execution)
        print(f"🔍 [Backend-Workflow] DEBUG: vnc_url RAW = {repr(vnc_url)}")
        cua_host = None
        cua_port = None
        if vnc_url and "://" in vnc_url:
            try:
                after_protocol = vnc_url.split("://")[1]
                print(f"🔍 [Backend-Workflow] DEBUG: after_protocol = {repr(after_protocol)}")
                host_and_port = after_protocol.rstrip("/")
                print(f"🔍 [Backend-Workflow] DEBUG: host_and_port = {repr(host_and_port)}")
                if ":" in host_and_port:
                    cua_host = host_and_port.split(":")[0]
                    cua_port = host_and_port.split(":")[1]
                else:
                    cua_host = host_and_port
                    cua_port = "80" if vnc_url.startswith("http://") else "443"
            except Exception as e:
                print(f"❌ [Backend-Workflow] ERROR parsing VNC URL: {e}")

        print(f"🔍 [Backend-Workflow] DEBUG: FINAL cua_host = {repr(cua_host)}")
        print(f"🔍 [Backend-Workflow] DEBUG: FINAL cua_port = {repr(cua_port)}")

        config = {
            "configurable": {
                "user_id": user_id,
                "cua_url": vnc_url,
                "use_longterm_memory": True if user_id else False,
                "x-cua-host": cua_host,
                "x-cua-port": cua_port,
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
        # stream_mode="events" returns event objects - we only send tool execution updates

        # Step tracking for workflow progress
        workflow_steps = workflow_json.get("steps", [])
        total_steps = len(workflow_steps)
        current_step_index = 0

        # Tools that typically indicate step completion (customize per workflow type)
        step_completing_tools = [
            "navigate_to_url",      # Navigation step done
            "search_posts",         # Research step done
            "create_post",          # Action step done
            "save_memory",          # Memory step done
            "comment_on_post",      # Comment action done
            "follow_account",       # Follow action done
            "analyze_post",         # Analysis step done
            "filter_posts"          # Filter step done
        ]

        async for chunk in langgraph_client.runs.stream(
            workflow_thread_id,  # Positional: thread_id (managed by PostgreSQL)
            "x_growth_deep_agent",  # Positional: assistant_id (from langgraph.json)
            input=input_data,
            config=config,
            stream_mode="events"  # Stream all events including tool calls
        ):
            # Handle event-based streaming - ONLY send tool updates to frontend
            if isinstance(chunk, dict):
                event_type = chunk.get("event")
                data = chunk.get("data", {})

                # Stream tool calls (when agent decides to use a tool)
                if event_type == "on_tool_start":
                    tool_name = data.get("name", "unknown_tool")
                    tool_input = data.get("input", {})
                    print(f"   🔧 Tool starting: {tool_name}")
                    await websocket.send_json({
                        "type": "tool_start",
                        "tool_name": tool_name,
                        "tool_input": tool_input
                    })

                # Stream tool results (when tool execution completes)
                elif event_type == "on_tool_end":
                    tool_name = data.get("name", "unknown_tool")
                    print(f"   ✅ Tool completed: {tool_name}")
                    await websocket.send_json({
                        "type": "tool_end",
                        "tool_name": tool_name
                    })

                    # Check if this tool completion should advance the step
                    if tool_name in step_completing_tools and current_step_index < total_steps:
                        # Send step_complete event for current step
                        await websocket.send_json({
                            "type": "step_complete",
                            "step_index": current_step_index,
                            "step_id": workflow_steps[current_step_index]["id"] if current_step_index < total_steps else None,
                            "total_steps": total_steps
                        })
                        print(f"   ✅ Step {current_step_index + 1}/{total_steps} completed")

                        # Update database with step progress
                        try:
                            db = SessionLocal()
                            exec_record = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
                            if exec_record:
                                exec_record.current_step = current_step_index
                                if workflow_steps[current_step_index]["id"] not in exec_record.completed_steps:
                                    exec_record.completed_steps.append(workflow_steps[current_step_index]["id"])
                                db.commit()
                            db.close()
                        except Exception as e:
                            print(f"⚠️ Failed to update step progress in database: {e}")

                        # Advance to next step
                        current_step_index += 1

                        # Send step_start event for next step if exists
                        if current_step_index < total_steps:
                            next_step = workflow_steps[current_step_index]
                            await websocket.send_json({
                                "type": "step_start",
                                "step_index": current_step_index,
                                "step_id": next_step["id"],
                                "description": next_step.get("description", next_step.get("action", "")),
                                "total_steps": total_steps
                            })
                            print(f"   ▶️ Step {current_step_index + 1}/{total_steps} started: {next_step.get('description', '')}")

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

        # Mark execution as completed in database
        try:
            db = SessionLocal()
            exec_record = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
            if exec_record:
                exec_record.status = "completed"
                exec_record.completed_at = datetime.utcnow()
                db.commit()
            db.close()
            print(f"✅ Marked workflow execution {execution_id} as completed")
        except Exception as e:
            print(f"⚠️ Failed to mark execution as completed in database: {e}")

    except WebSocketDisconnect:
        print("Client disconnected")
        # Mark execution as failed if disconnected mid-execution
        try:
            db = SessionLocal()
            exec_record = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
            if exec_record and exec_record.status == "running":
                exec_record.status = "failed"
                exec_record.error_message = "Client disconnected"
                exec_record.completed_at = datetime.utcnow()
                db.commit()
            db.close()
        except Exception as e:
            print(f"⚠️ Failed to update execution status after disconnect: {e}")
    except Exception as e:
        print(f"❌ Workflow execution error: {e}")
        import traceback
        traceback.print_exc()
        await websocket.send_json({
            "type": "error",
            "error": str(e)
        })

        # Mark execution as failed in database
        try:
            db = SessionLocal()
            exec_record = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
            if exec_record:
                exec_record.status = "failed"
                exec_record.error_message = str(e)
                exec_record.completed_at = datetime.utcnow()
                db.commit()
            db.close()
            print(f"✅ Marked workflow execution {execution_id} as failed")
        except Exception as db_error:
            print(f"⚠️ Failed to mark execution as failed in database: {db_error}")

        await websocket.close()


# ============================================================================
# WORKFLOW EXECUTION STATUS & HISTORY ENDPOINTS
# ============================================================================

@app.get("/api/workflow/execution/{execution_id}/status")
async def get_workflow_execution_status(execution_id: str, user_id: str = Depends(get_current_user)):
    """
    Get the status of a workflow execution.
    Enables frontend to check execution state and reconnect if needed.

    Returns:
        - status: 'running', 'completed', or 'failed'
        - thread_id: LangGraph thread ID
        - current_step: Current step index
        - completed_steps: Array of completed step IDs
        - started_at, completed_at: Timestamps
    """
    try:
        db = SessionLocal()
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
        db.close()

        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

        return {
            "execution_id": execution.id,
            "thread_id": execution.thread_id,
            "workflow_id": execution.workflow_id,
            "workflow_name": execution.workflow_name,
            "status": execution.status,
            "current_step": execution.current_step,
            "total_steps": execution.total_steps,
            "completed_steps": execution.completed_steps,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "error_message": execution.error_message
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching execution status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/workflow/execution/{execution_id}")
async def get_workflow_execution(execution_id: str, user_id: str = Depends(get_current_user)):
    """
    Get full workflow execution details including logs (if stored).
    Enables frontend to restore execution history.
    """
    try:
        db = SessionLocal()
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
        db.close()

        if not execution:
            raise HTTPException(status_code=404, detail=f"Execution {execution_id} not found")

        return {
            "id": execution.id,
            "user_id": execution.user_id,
            "thread_id": execution.thread_id,
            "workflow_id": execution.workflow_id,
            "workflow_name": execution.workflow_name,
            "status": execution.status,
            "current_step": execution.current_step,
            "total_steps": execution.total_steps,
            "completed_steps": execution.completed_steps,
            "logs": execution.logs if execution.logs else [],
            "error_message": execution.error_message,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching execution: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# POST MIGRATION ENDPOINT
# ============================================================================

@app.post("/api/migrate-posts-to-langgraph")
async def migrate_posts_to_langgraph(data: dict, user_id: str = Depends(get_current_user)):
    """
    Migrate user posts from PostgreSQL to LangGraph Store for style learning.

    This fixes the issue where posts exist in PostgreSQL but not in LangGraph Store,
    preventing the agent from learning the user's writing style.
    """
    user_id = data.get("user_id")
    username = data.get("username")

    if not user_id or not username:
        return {"success": False, "error": "Missing user_id or username"}

    print(f"\n{'='*80}")
    print(f"🔄 MIGRATING POSTS TO LANGGRAPH STORE")
    print(f"   User: @{username} ({user_id})")
    print(f"{'='*80}\n")

    try:
        from database.models import UserPost, XAccount
        from database.database import SessionLocal
        from x_writing_style_learner import XWritingStyleManager

        # Get posts from PostgreSQL
        db = SessionLocal()
        try:
            x_account = db.query(XAccount).filter(XAccount.username == username).first()

            if not x_account:
                return {"success": False, "error": f"User @{username} not found in database"}

            posts = db.query(UserPost).filter(UserPost.x_account_id == x_account.id).all()

            if not posts:
                return {"success": False, "error": "No posts found in database"}

            print(f"📊 Found {len(posts)} posts in PostgreSQL")

            # Convert to dict format expected by bulk_import_posts
            post_dicts = []
            for post in posts:
                post_dicts.append({
                    "content": post.content,
                    "timestamp": post.imported_at.isoformat() if post.imported_at else None,
                    "engagement": {}  # No engagement data in PostgreSQL
                })

            print(f"📦 Prepared {len(post_dicts)} posts for import\n")

        finally:
            db.close()

        # Import to LangGraph Store
        print(f"💾 Importing to LangGraph Store...")
        style_manager = XWritingStyleManager(store, user_id)
        style_manager.bulk_import_posts(post_dicts)

        print(f"\n✅ Migration complete!")

        return {
            "success": True,
            "migrated_count": len(post_dicts),
            "username": username
        }

    except Exception as e:
        print(f"❌ Migration failed: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Parallel Universe Backend...")
    print("📡 WebSocket: ws://localhost:8001/ws/extension/{user_id}")
    print("🌐 Dashboard: http://localhost:3000")
    print("🔌 Extension will connect automatically!")
    print("🤖 LangGraph Agent: http://localhost:8124")
    uvicorn.run(app, host="0.0.0.0", port=8002)

