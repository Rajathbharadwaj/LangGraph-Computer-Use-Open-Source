# Competitor Data Architecture

## Overview

This document explains how competitor data is stored and accessed in the CUA system, particularly for the X Growth Deep Agent's competitor learning feature (Issue #15).

## Data Storage Architecture

### LangGraph Store Namespaces

Competitor data is stored in **TWO different namespaces** in LangGraph Store (PostgreSQL-backed):

#### 1. Social Graph Namespace (PRIMARY DATA SOURCE)
- **Namespace**: `(user_id, "social_graph")`
- **Key**: `"latest"`
- **Purpose**: Contains the complete social graph analysis with ALL competitor data
- **Structure**:
  ```python
  {
    "user_handle": "@username",
    "top_competitors": [...],           # Filtered high-quality competitors
    "all_competitors_raw": [            # FULL list with all scraped data
      {
        "username": "code_star",
        "overlap_score": 15,
        "overlap_percentage": 75.0,
        "posts": [                      # ← Posts are HERE!
          {
            "text": "Post content...",
            "likes": 163,
            "retweets": 21,
            "replies": 15,
            "views": 336000,
            "scraped_at": "2024-11-20T..."
          }
        ],
        "post_count": 7
      }
    ],
    "created_at": "...",
    "last_updated": "..."
  }
  ```

#### 2. Competitor Profiles Namespace (SECONDARY - NO POSTS)
- **Namespace**: `(user_id, "competitor_profiles")`
- **Keys**: Individual competitor usernames (e.g., `"code_star"`)
- **Purpose**: Individual competitor metadata (without posts)
- **Structure**:
  ```python
  {
    "username": "code_star",
    "overlap_score": 15,
    "tracked_since": "...",
    "status": "discovered",
    # NOTE: posts field exists but is often empty []
  }
  ```

### Why Two Namespaces?

**Historical Context:**
1. `competitor_profiles` was created to store individual competitor entries for quick lookups
2. `social_graph` stores the complete analysis including the full post data
3. The scraper (`social_graph_scraper.py`) populates posts in `social_graph.all_competitors_raw`
4. Individual `competitor_profiles` entries may NOT have posts populated

## Critical Implementation Detail

### ✅ CORRECT: Access posts from social_graph namespace

```python
async def get_competitor_posts(user_id, runtime):
    store = runtime.store

    # Get graph data (contains all posts)
    namespace_graph = (user_id, "social_graph")
    graph_results = await store.asearch(namespace_graph, limit=1)
    graph_data = graph_results[0].value

    # Extract competitors with posts
    all_competitors = graph_data.get("all_competitors_raw", [])

    for comp in all_competitors:
        posts = comp.get("posts", [])  # ← Has actual post data
        for post in posts:
            print(f"{post['text']} - {post['likes']} likes")
```

### ❌ INCORRECT: Searching competitor_profiles (posts may be empty)

```python
# DON'T DO THIS - posts will be empty!
namespace = (user_id, "competitor_profiles")
search_results = await store.asearch(namespace, limit=50)

for item in search_results:
    comp = item.value
    posts = comp.get("posts", [])  # ← Usually empty []
```

## Data Flow

```
┌──────────────────────────────────────────────────────────┐
│ social_graph_scraper.py                                  │
│                                                           │
│  1. Discover competitors (overlap analysis)              │
│  2. Scrape posts for each competitor                     │
│  3. Store data in BOTH namespaces:                       │
│                                                           │
│     ┌─────────────────────────────────────────┐          │
│     │ social_graph namespace                  │          │
│     │  - key: "latest"                        │          │
│     │  - Contains: all_competitors_raw        │          │
│     │              with FULL post data        │          │
│     └─────────────────────────────────────────┘          │
│                      │                                    │
│                      ▼                                    │
│     ┌─────────────────────────────────────────┐          │
│     │ competitor_profiles namespace           │          │
│     │  - keys: individual usernames           │          │
│     │  - Contains: metadata only              │          │
│     │  - Posts: may be empty                  │          │
│     └─────────────────────────────────────────┘          │
└──────────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────┐
│ UI Dashboard (localhost:3000)                            │
│  - Reads: social_graph namespace                         │
│  - Displays: all_competitors_raw[].posts                 │
│  - Shows: 69 accounts, 47 with posts                     │
└──────────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────┐
│ X Growth Deep Agent                                      │
│  - Tool: get_high_performing_competitor_posts()          │
│  - Reads: social_graph namespace                         │
│  - Extracts: all_competitors_raw[].posts                 │
│  - Filters by: min_likes, topic                          │
│  - Returns: Top performing posts for ICL                 │
└──────────────────────────────────────────────────────────┘
```

## API Endpoints

### Backend API Endpoints

1. **Get Social Graph** (includes all post data)
   ```bash
   GET /api/social-graph/{user_id}

   Response:
   {
     "success": true,
     "graph": {
       "all_competitors_raw": [
         {"username": "...", "posts": [...], "post_count": N}
       ]
     }
   }
   ```

2. **List Competitors** (may not include posts)
   ```bash
   GET /api/competitors/{user_id}

   Response:
   {
     "competitors": [
       {"username": "...", "posts": []}  # Often empty
     ]
   }
   ```

3. **Get Individual Competitor** (may not include posts)
   ```bash
   GET /api/competitor/{user_id}/{username}

   Response:
   {
     "competitor": {
       "username": "code_star",
       "posts": [],  # Often empty
       "post_count": 0
     }
   }
   ```

## Debugging Tips

### How to verify posts exist for a user

```bash
# Check the social_graph data (should have posts)
curl "https://backend-api-YOUR-PROJECT.run.app/api/social-graph/USER_ID" | \
  python3 -c "
import sys, json
data = json.load(sys.stdin)
graph = data.get('graph', {})
raw = graph.get('all_competitors_raw', [])
with_posts = [c for c in raw if c.get('posts')]
print(f'Total: {len(raw)}, With posts: {len(with_posts)}')
if with_posts:
    first = with_posts[0]
    print(f\"Example: @{first['username']} has {len(first['posts'])} posts\")
    print(f\"  First post: {first['posts'][0]['text'][:100]}...\")
"
```

### Common Issues

**Issue**: Tool returns "No competitor data found"
- **Cause**: User hasn't run competitor discovery yet
- **Fix**: Run discovery from dashboard first

**Issue**: Tool finds competitors but says "No high-performing posts"
- **Cause**: `min_likes` threshold too high or posts not scraped
- **Fix**: Lower min_likes or re-run post scraping

**Issue**: Tool is using competitor_profiles namespace
- **Cause**: Wrong namespace in tool implementation
- **Fix**: Use `social_graph` namespace instead

## Related Files

- **Scraper**: `/social_graph_scraper.py` (lines 650-750)
  - Line 675: Posts added to competitor dict
  - Line 709: Posts merged into `all_competitors_raw`
  - Line 741: Individual competitors stored (may not have posts)

- **Agent Tool**: `/x_growth_deep_agent.py` (lines 110-240)
  - Line 153: Accesses `social_graph` namespace
  - Line 164: Extracts `all_competitors_raw`

- **Backend API**: `/backend_websocket_server.py`
  - Line 2338: GET `/api/social-graph/{user_id}` (has posts)
  - Line 2382: GET `/api/competitors/{user_id}` (may not have posts)
  - Line 2415: GET `/api/competitor/{user_id}/{username}` (may not have posts)

## Version History

- **2024-11-30**: Initial documentation after fixing Issue #15
  - Fixed tool to use `social_graph` namespace instead of `competitor_profiles`
  - Tool now successfully accesses 47 competitors with posts
  - Verified posts match UI display (163 likes, 21 retweets, etc.)
