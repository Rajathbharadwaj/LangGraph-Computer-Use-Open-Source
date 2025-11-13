"""
Simple Backend WebSocket Server for Extension
This connects your Chrome extension to the dashboard
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import asyncio
import json
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# LangGraph SDK for agent control
from langgraph_sdk import get_client

# LangGraph Store for persistent memory
from langgraph.store.postgres import PostgresStore

# Writing style learner
from x_writing_style_learner import XWritingStyleManager, WritingSample

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

app = FastAPI(title="Parallel Universe Backend")

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
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
langgraph_client = get_client(url="http://localhost:8124")

# Initialize PostgreSQL Store for persistent memory (writing samples, preferences, etc.)
# Using the same database as the main app (port 5433 to avoid conflict with other postgres instances)
DB_URI = os.environ.get("DATABASE_URL", "postgresql://postgres:password@localhost:5433/xgrowth")

# Create store instance (not using context manager since we need it globally)
from psycopg_pool import ConnectionPool

# Create a connection pool for the store
conn_pool = ConnectionPool(
    conninfo=DB_URI,
    min_size=1,
    max_size=10
)

# Initialize store with the pool
store = PostgresStore(conn=conn_pool)
print(f"✅ Initialized PostgresStore for persistent memory: {DB_URI}")

# Note: store.setup() should be run ONCE manually or via migration script
# See: https://docs.langchain.com/oss/python/langgraph/add-memory
# After first setup, comment it out (as shown in docs)
# store.setup()  # Already initialized via migration

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
            "http://localhost:8001/extension/create-post",
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
    """Get stored posts for a user (from persistent store)"""
    try:
        # Try to get from persistent store first
        namespace = (user_id, "writing_samples")
        
        # Search for all writing samples for this user (no query = get all)
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
async def extension_status():
    """Check if any extensions are connected"""
    import aiohttp
    
    # Check extension backend (port 8001) for connected extensions
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8001/status', timeout=aiohttp.ClientTimeout(total=2)) as resp:
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
    
    # Fallback to local connections
    users_with_cookies = []
    for user_id in active_connections.keys():
        user_info = {"userId": user_id}
        if user_id in user_cookies:
            user_info["username"] = user_cookies[user_id].get("username")
            user_info["hasCookies"] = True
        users_with_cookies.append(user_info)
    
    return {
        "connected": len(active_connections) > 0,
        "count": len(active_connections),
        "users": users_with_cookies
    }

@app.post("/api/inject-cookies-to-docker")
async def inject_cookies_to_docker(request: dict):
    """
    Inject user's X cookies into Docker browser
    Request: {"user_id": "user_xxx"}
    """
    import aiohttp
    
    user_id = request.get("user_id")
    if not user_id:
        return {"success": False, "error": "user_id required"}
    
    # First, try to get cookies from extension backend (port 8001)
    cookie_data = None
    print(f"🔍 Looking for cookies for user: {user_id}")
    print(f"   In local cache: {user_id in user_cookies}")
    
    if user_id not in user_cookies:
        # Fetch from extension backend
        print(f"   Fetching from extension backend...")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f'http://localhost:8001/cookies/{user_id}', timeout=aiohttp.ClientTimeout(total=2)) as resp:
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
            print(f"❌ No cookie data found for {user_id}")
            return {"success": False, "error": "No cookies found for this user"}
    else:
        cookie_data = user_cookies[user_id]
    
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
        
        # Call Docker stealth_cua_server to inject cookies
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8005/session/load",
                json={"cookies": playwright_cookies}
            ) as response:
                result = await response.json()
                
                if result.get("success"):
                    print(f"✅ Injected cookies into Docker for @{username}")
                    return {
                        "success": True,
                        "message": f"Session loaded for @{username}",
                        "logged_in": result.get("logged_in"),
                        "username": result.get("username")
                    }
                else:
                    return {
                        "success": False,
                        "error": result.get("error", "Failed to load session")
                    }
    except Exception as e:
        print(f"❌ Error injecting cookies: {e}")
        return {"success": False, "error": str(e)}

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
    
    try:
        # Get username AND user_id with cookies from extension backend
        username = None
        extension_user_id = None
        async with aiohttp.ClientSession() as session:
            try:
                async with session.get("http://localhost:8001/status") as resp:
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
        inject_result = await inject_cookies_to_docker({"user_id": extension_user_id})
        if not inject_result.get("success"):
            print(f"⚠️ Cookie injection failed: {inject_result.get('error')}")
            return {
                "success": False,
                "error": f"Cookie injection failed: {inject_result.get('error')}"
            }
        
        print(f"✅ Docker browser is now logged in as @{username}")
        
        # Navigate to user's profile
        # Create new session for each request to avoid connection reuse issues
        async with aiohttp.ClientSession() as session:
            profile_url = f"https://x.com/{username}"
            print(f"🌐 Navigating to {profile_url}...")
            
            async with session.post(
                "http://localhost:8005/navigate",
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
                        "http://localhost:8005/execute",
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
                        "http://localhost:8005/execute",
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
                            "http://localhost:8005/execute",
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

        # Update fields if provided
        if request.content is not None:
            post.content = request.content
        if request.media_urls is not None:
            post.media_urls = request.media_urls
        if request.scheduled_at is not None:
            post.scheduled_at = datetime.fromisoformat(request.scheduled_at.replace('Z', '+00:00'))
        if request.status is not None:
            post.status = request.status

        post.updated_at = datetime.utcnow()

        db.commit()
        db.refresh(post)

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
    count: int = 5,
    db: Session = Depends(get_db)
):
    """
    Generate AI content suggestions for scheduled posts
    Uses the user's writing style learner
    """
    try:
        # Get user's X account
        x_account = db.query(XAccount).filter(
            XAccount.user_id == user_id,
            XAccount.is_connected == True
        ).first()

        if not x_account:
            raise HTTPException(status_code=404, detail="No connected X account found")

        # TODO: Integrate with your x_writing_style_learner.py
        # For now, generate mock AI content
        # In production, you would:
        # 1. Load user's writing style from user_posts table
        # 2. Use AI model to generate posts in their style
        # 3. Score confidence based on style similarity

        import random
        from datetime import timedelta

        ai_posts = []
        templates = [
            "Just shipped a major update! The response has been incredible. Here's what's next: {}",
            "Building in public taught me {}. This is the #1 lesson I learned this month.",
            "Quick reminder: {} Your product doesn't have to be perfect to launch.",
            "The best investment you can make? {} Everything else becomes easier after that.",
            "If you're working on {}, you need to see this. Game changer."
        ]

        topics = [
            "learning to build",
            "solving real problems",
            "shipping fast",
            "getting user feedback",
            "iterating quickly"
        ]

        for i in range(count):
            template = random.choice(templates)
            topic = random.choice(topics)
            content = template.format(topic)

            # Generate scheduled time (spread across next 7 days)
            days_ahead = (i % 7) + 1
            hours = random.choice([9, 14, 18])  # 9am, 2pm, or 6pm
            scheduled_time = datetime.utcnow() + timedelta(days=days_ahead, hours=hours-datetime.utcnow().hour)

            ai_posts.append({
                "content": content,
                "scheduled_at": scheduled_time.isoformat(),
                "confidence": random.randint(85, 98),
                "ai_generated": True
            })

        return {
            "success": True,
            "posts": ai_posts,
            "count": len(ai_posts),
            "message": "AI content generated successfully"
        }

    except Exception as e:
        print(f"Error generating AI content: {e}")
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
            "stream_mode": "messages"
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
                        print(f"📝 Tracking run_id: {run_id}")
                if user_id in active_connections:
                    try:
                        # chunk.data contains the message chunk from LangGraph
                        # It's usually a list with message objects
                        if hasattr(chunk, 'data') and isinstance(chunk.data, list) and len(chunk.data) > 0:
                            message_data = chunk.data[0]  # Get first item
                            
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
            # LangGraph stores messages as BaseMessage objects
            role = "user" if msg.get("type") == "human" else "assistant"
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

if __name__ == "__main__":
    import uvicorn
    print("🚀 Starting Parallel Universe Backend...")
    print("📡 WebSocket: ws://localhost:8001/ws/extension/{user_id}")
    print("🌐 Dashboard: http://localhost:3000")
    print("🔌 Extension will connect automatically!")
    print("🤖 LangGraph Agent: http://localhost:8124")
    uvicorn.run(app, host="0.0.0.0", port=8002)

