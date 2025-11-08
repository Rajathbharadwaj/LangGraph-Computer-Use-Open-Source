"""
Backend Post Importer

Receives scraped posts from Chrome extension and imports them into
the writing style learning system.

Flow:
1. Extension scrapes user's posts from X.com
2. Extension sends posts via WebSocket
3. Backend receives and validates posts
4. Backend imports into writing_samples namespace
5. Backend analyzes writing style
6. Ready to generate in user's style!
"""

import json
import uuid
from datetime import datetime
from typing import List, Dict
from fastapi import WebSocket
from x_writing_style_learner import XWritingStyleManager, WritingSample


# ============================================================================
# POST IMPORT HANDLER
# ============================================================================

class PostImportHandler:
    """Handles importing scraped posts into writing style system"""
    
    def __init__(self, store):
        """
        Initialize post import handler
        
        Args:
            store: LangGraph Store with semantic search
        """
        self.store = store
        self.style_managers = {}  # Cache style managers per user
    
    def get_style_manager(self, user_id: str) -> XWritingStyleManager:
        """Get or create style manager for user"""
        if user_id not in self.style_managers:
            self.style_managers[user_id] = XWritingStyleManager(self.store, user_id)
        return self.style_managers[user_id]
    
    async def handle_posts_scraped(self, user_id: str, posts: List[Dict]) -> Dict:
        """
        Handle scraped posts from extension
        
        Args:
            user_id: User identifier
            posts: List of scraped posts
        
        Returns:
            Status dict with import results
        """
        try:
            print(f"📥 Importing {len(posts)} posts for user {user_id}...")
            
            # Get style manager
            style_manager = self.get_style_manager(user_id)
            
            # Filter and validate posts
            valid_posts = self.validate_posts(posts)
            print(f"✅ {len(valid_posts)} valid posts")
            
            # Import posts
            style_manager.bulk_import_posts(valid_posts)
            
            # Analyze writing style
            print("🔍 Analyzing writing style...")
            profile = style_manager.analyze_writing_style()
            
            result = {
                "success": True,
                "imported_count": len(valid_posts),
                "total_scraped": len(posts),
                "writing_style": {
                    "tone": profile.tone,
                    "avg_post_length": profile.avg_post_length,
                    "avg_comment_length": profile.avg_comment_length,
                    "uses_emojis": profile.uses_emojis,
                    "uses_questions": profile.uses_questions,
                    "technical_terms": profile.technical_terms[:5]
                },
                "message": f"✅ Imported {len(valid_posts)} posts and analyzed your writing style!"
            }
            
            print(f"✅ Import complete: {result}")
            return result
            
        except Exception as e:
            print(f"❌ Import failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to import posts"
            }
    
    def validate_posts(self, posts: List[Dict]) -> List[Dict]:
        """
        Validate and clean scraped posts
        
        Args:
            posts: Raw scraped posts
        
        Returns:
            List of valid posts
        """
        valid_posts = []
        
        for post in posts:
            # Must have content
            if not post.get("content"):
                continue
            
            # Must have reasonable length (not just "...")
            if len(post["content"]) < 10:
                continue
            
            # Skip retweets (they're not the user's words)
            if post["content"].startswith("RT @"):
                continue
            
            # Clean and format
            cleaned_post = {
                "content": post["content"].strip(),
                "timestamp": post.get("timestamp", datetime.now().isoformat()),
                "engagement": post.get("engagement", {
                    "likes": 0,
                    "replies": 0,
                    "reposts": 0
                }),
                "topic": self.extract_topic(post["content"]),
                "context": None  # Posts don't have context (unlike replies)
            }
            
            valid_posts.append(cleaned_post)
        
        return valid_posts
    
    def extract_topic(self, content: str) -> str:
        """
        Extract topic from post content (simple keyword matching)
        
        Args:
            content: Post text
        
        Returns:
            Topic string or "general"
        """
        content_lower = content.lower()
        
        # Define topic keywords
        topics = {
            "AI": ["ai", "artificial intelligence", "machine learning", "ml", "llm", "gpt"],
            "LangChain": ["langchain", "langgraph", "langsmith"],
            "Agents": ["agent", "agents", "agentic", "autonomous"],
            "Coding": ["code", "coding", "programming", "developer", "dev"],
            "Startup": ["startup", "founder", "saas", "product"],
        }
        
        for topic, keywords in topics.items():
            if any(keyword in content_lower for keyword in keywords):
                return topic
        
        return "general"


# ============================================================================
# WEBSOCKET INTEGRATION
# ============================================================================

async def handle_websocket_message(
    websocket: WebSocket,
    message: Dict,
    user_id: str,
    post_import_handler: PostImportHandler
):
    """
    Handle WebSocket messages from extension
    
    Add this to your backend_websocket_server.py
    """
    
    message_type = message.get("type")
    
    if message_type == "POSTS_SCRAPED":
        # Extension scraped user's posts
        posts = message.get("posts", [])
        username = message.get("username")
        
        print(f"📨 Received {len(posts)} scraped posts from @{username}")
        
        # Import posts
        result = await post_import_handler.handle_posts_scraped(user_id, posts)
        
        # Send response back to extension
        await websocket.send_json({
            "type": "IMPORT_COMPLETE",
            "result": result
        })
        
        return result
    
    elif message_type == "SCRAPING_FAILED":
        error = message.get("error")
        print(f"❌ Scraping failed: {error}")
        
        await websocket.send_json({
            "type": "ERROR",
            "message": f"Failed to scrape posts: {error}"
        })


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == "__main__":
    """
    Example: How to integrate with backend
    """
    
    print("=" * 80)
    print("📦 POST IMPORT HANDLER - Integration Example")
    print("=" * 80)
    
    print("""
This handler receives scraped posts from the Chrome extension and imports them
into the writing style learning system.

INTEGRATION STEPS:

1. Add to backend_websocket_server.py:

```python
from backend_post_importer import PostImportHandler
from langgraph.store.memory import InMemoryStore
from langchain.embeddings import init_embeddings

# Initialize store with semantic search
embeddings = init_embeddings("openai:text-embedding-3-small")
store = InMemoryStore(
    index={
        "embed": embeddings,
        "dims": 1536,
    }
)

# Initialize post import handler
post_import_handler = PostImportHandler(store)

# In WebSocket message handler:
@app.websocket("/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str):
    await websocket.accept()
    
    try:
        while True:
            message = await websocket.receive_json()
            
            if message["type"] == "POSTS_SCRAPED":
                result = await post_import_handler.handle_posts_scraped(
                    user_id,
                    message["posts"]
                )
                await websocket.send_json({
                    "type": "IMPORT_COMPLETE",
                    "result": result
                })
    except Exception as e:
        print(f"WebSocket error: {e}")
```

2. Add to Chrome extension background.js:

```javascript
// When posts are scraped
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    if (message.type === 'POSTS_SCRAPED') {
        // Send to backend via WebSocket
        ws.send(JSON.stringify({
            type: 'POSTS_SCRAPED',
            posts: message.posts,
            username: message.username
        }));
    }
});

// Receive import confirmation
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    if (data.type === 'IMPORT_COMPLETE') {
        console.log('✅ Posts imported:', data.result);
        // Update UI to show writing style learned
    }
};
```

3. Add UI button to trigger scraping:

```javascript
// In dashboard (Next.js)
<Button onClick={async () => {
    // Tell extension to scrape posts
    chrome.runtime.sendMessage(
        extensionId,
        { action: 'SCRAPE_POSTS', targetCount: 50 }
    );
}}>
    📚 Import My Posts
</Button>
```

FLOW:
1. User clicks "Import My Posts" on dashboard
2. Dashboard sends message to extension
3. Extension scrapes user's X profile
4. Extension sends posts to backend via WebSocket
5. Backend imports into writing_samples namespace
6. Backend analyzes writing style
7. Backend sends confirmation to extension
8. Extension updates dashboard UI
9. ✅ Agent can now write in user's style!
""")
    
    print("=" * 80)
    print("✅ See x_post_scraper_extension.js for extension code")
    print("✅ See COMPLETE_STYLE_INTEGRATION.md for full architecture")
    print("=" * 80)

