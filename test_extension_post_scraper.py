"""
Test Extension Post Scraper

Simple server to receive scraped posts from Chrome extension and display them.

Usage:
1. Run this script: python test_extension_post_scraper.py
2. Open Chrome extension
3. Navigate to your X profile
4. Run the scraper (from extension console or add button)
5. See the scraped posts here!
"""

import asyncio
import json
from datetime import datetime
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn


app = FastAPI(title="Post Scraper Test Server")

# Enable CORS for extension
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# WEBSOCKET ENDPOINT
# ============================================================================

@app.websocket("/ws/test")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint to receive scraped posts from extension"""
    await websocket.accept()
    print("\n" + "=" * 80)
    print("✅ WebSocket Connected!")
    print("=" * 80)
    print("\n📡 Waiting for scraped posts from extension...")
    print("   (Run the scraper from your extension)")
    
    try:
        while True:
            # Receive message from extension
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            print("\n" + "=" * 80)
            print(f"📨 Received message: {message_type}")
            print("=" * 80)
            
            if message_type == "POSTS_SCRAPED":
                posts = data.get("posts", [])
                username = data.get("username", "unknown")
                
                print(f"\n🎉 SUCCESS! Scraped {len(posts)} posts from @{username}")
                print("\n" + "-" * 80)
                
                # Display each post
                for i, post in enumerate(posts[:10], 1):  # Show first 10
                    print(f"\n📝 Post {i}:")
                    print(f"   Content: {post.get('content', '')[:100]}...")
                    print(f"   Timestamp: {post.get('timestamp', 'N/A')}")
                    
                    engagement = post.get('engagement', {})
                    print(f"   Engagement:")
                    print(f"      - Likes: {engagement.get('likes', 0)}")
                    print(f"      - Replies: {engagement.get('replies', 0)}")
                    print(f"      - Reposts: {engagement.get('reposts', 0)}")
                    print(f"      - Views: {engagement.get('views', 0)}")
                    
                    print(f"   URL: {post.get('postUrl', 'N/A')}")
                
                if len(posts) > 10:
                    print(f"\n   ... and {len(posts) - 10} more posts")
                
                print("\n" + "-" * 80)
                print("\n📊 SUMMARY:")
                print(f"   Total posts scraped: {len(posts)}")
                
                # Calculate stats
                total_likes = sum(p.get('engagement', {}).get('likes', 0) for p in posts)
                total_replies = sum(p.get('engagement', {}).get('replies', 0) for p in posts)
                total_reposts = sum(p.get('engagement', {}).get('reposts', 0) for p in posts)
                
                print(f"   Total engagement:")
                print(f"      - Likes: {total_likes}")
                print(f"      - Replies: {total_replies}")
                print(f"      - Reposts: {total_reposts}")
                
                avg_length = sum(len(p.get('content', '')) for p in posts) / max(len(posts), 1)
                print(f"   Average post length: {int(avg_length)} characters")
                
                # Save to file for inspection
                filename = f"scraped_posts_{username}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                with open(filename, 'w') as f:
                    json.dump(posts, f, indent=2)
                print(f"\n💾 Saved to: {filename}")
                
                # Send acknowledgment
                await websocket.send_json({
                    "type": "ACK",
                    "message": f"Received {len(posts)} posts!",
                    "success": True
                })
                
                print("\n✅ Data received and saved successfully!")
                print("=" * 80)
            
            elif message_type == "SCRAPING_STARTED":
                username = data.get("username", "unknown")
                target_count = data.get("targetCount", 50)
                print(f"\n🔍 Scraping started for @{username}")
                print(f"   Target: {target_count} posts")
                
                await websocket.send_json({
                    "type": "ACK",
                    "message": "Scraping acknowledged"
                })
            
            elif message_type == "SCRAPING_PROGRESS":
                current = data.get("current", 0)
                target = data.get("target", 0)
                print(f"\n⏳ Progress: {current}/{target} posts scraped")
                
            elif message_type == "SCRAPING_FAILED":
                error = data.get("error", "Unknown error")
                print(f"\n❌ Scraping failed: {error}")
                
                await websocket.send_json({
                    "type": "ERROR",
                    "message": f"Scraping failed: {error}"
                })
            
            else:
                print(f"\n⚠️  Unknown message type: {message_type}")
                print(f"   Data: {json.dumps(data, indent=2)}")
    
    except WebSocketDisconnect:
        print("\n" + "=" * 80)
        print("❌ WebSocket Disconnected")
        print("=" * 80)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()


# ============================================================================
# HTTP ENDPOINT (for testing)
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "status": "running",
        "message": "Post Scraper Test Server",
        "websocket_url": "ws://localhost:8765/ws/test",
        "instructions": [
            "1. Connect to WebSocket at ws://localhost:8765/ws/test",
            "2. Send scraped posts with type: 'POSTS_SCRAPED'",
            "3. Server will display and save the posts"
        ]
    }


@app.post("/test-posts")
async def test_posts(posts: list):
    """HTTP endpoint to test with sample posts"""
    print("\n" + "=" * 80)
    print(f"📨 Received {len(posts)} posts via HTTP")
    print("=" * 80)
    
    for i, post in enumerate(posts[:5], 1):
        print(f"\nPost {i}: {post.get('content', '')[:80]}...")
    
    return {"status": "success", "received": len(posts)}


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("🚀 POST SCRAPER TEST SERVER")
    print("=" * 80)
    print("\nServer starting on: http://localhost:8765")
    print("WebSocket endpoint: ws://localhost:8765/ws/test")
    print("\n" + "=" * 80)
    print("INSTRUCTIONS:")
    print("=" * 80)
    print("""
1. Open Chrome DevTools on your X.com tab
2. Go to Console tab
3. Paste this code:

// Connect to test server
const ws = new WebSocket('ws://localhost:8765/ws/test');

ws.onopen = () => {
    console.log('✅ Connected to test server');
    
    // Notify scraping started
    ws.send(JSON.stringify({
        type: 'SCRAPING_STARTED',
        username: 'YOUR_USERNAME',
        targetCount: 50
    }));
    
    // Start scraping (paste the scraper code here)
    // Or if you have the scraper loaded:
    const scraper = new XPostScraper();
    scraper.scrapeUserPosts('YOUR_USERNAME', 50).then(posts => {
        console.log(`✅ Scraped ${posts.length} posts`);
        
        // Send to test server
        ws.send(JSON.stringify({
            type: 'POSTS_SCRAPED',
            posts: posts,
            username: 'YOUR_USERNAME'
        }));
    });
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log('📨 Server response:', data);
};

4. Replace 'YOUR_USERNAME' with your actual X username
5. Watch this terminal for the scraped posts!
""")
    print("=" * 80)
    print("\nWaiting for connections...\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8765)

