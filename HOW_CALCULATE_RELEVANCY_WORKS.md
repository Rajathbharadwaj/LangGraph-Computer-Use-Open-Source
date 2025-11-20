# How "Calculate Relevancy" Works

## TL;DR
Calculate Relevancy uses AI to analyze if competitors are **actually in your niche** (not just sharing followers). It combines **Overlap** (mutual audience) with **Relevancy** (content similarity) to create a **Quality Score**.

---

## The Problem It Solves

**Current Issue:**
You're finding web3/crypto accounts as "competitors" even though you post about AI, just because you share mutual followers.

**Why this happens:**
Discovery only looks at "who you both follow" which is a weak signal. People follow accounts for many reasons (news, entertainment, celebrities) - not just because they're in the same niche.

---

## How It Works (Step-by-Step)

### 1. **Get Your Profile**
```
- Scrapes YOUR bio
- Grabs your 10 most recent posts
- Builds a "content fingerprint" of your niche
```

**Example:**
- Bio: "AI researcher, prompt engineering, LLMs"
- Posts: About GPT-4, Claude, AI agents, etc.
- → **Your Niche: AI/Tech**

### 2. **Get Competitor Profiles**
```
- Uses existing posts if already scraped
- Otherwise scrapes bio + recent posts
- Does this for top 20 competitors
```

### 3. **AI Semantic Analysis** (The Magic Part)
```python
For each competitor:
  1. Send YOUR content + THEIR content to Claude AI
  2. Ask: "Are these accounts in the same niche?"
  3. Get back:
     - Relevancy Score (0-100%)
     - Your niche (e.g., "AI/ML")
     - Their niche (e.g., "Crypto/Web3")
     - Reasoning
```

**Example AI Response:**
```json
{
  "relevancy_score": 25,
  "user_niche": "AI & Machine Learning",
  "competitor_niche": "Crypto & Blockchain",
  "reasoning": "Weak relevance. Both are tech-focused but serve different audiences. Competitor focuses on decentralized systems while user focuses on AI applications."
}
```

### 4. **Calculate Quality Score**
```python
Quality Score = (Overlap × 40%) + (Relevancy × 60%)
```

**Example 1: Bad Match**
- Overlap: 70% (shared followers)
- Relevancy: 25% (different niche)
- Quality = (70 × 0.4) + (25 × 0.6) = **43%** ❌

**Example 2: Great Match**
- Overlap: 60% (shared followers)
- Relevancy: 90% (same niche)
- Quality = (60 × 0.4) + (90 × 0.6) = **78%** ✅

### 5. **Re-Rank & Filter**
```
- Sort ALL competitors by Quality Score (descending)
- Update UI to show all 3 metrics
- Filters out low-quality matches
```

---

## What You See in the UI

Before Calculate Relevancy:
```
@crypto_whale    |  70% match
```

After Calculate Relevancy:
```
@crypto_whale    |  Quality: 43%  |  Relevancy: 25%  |  Overlap: 70%
@AI_researcher   |  Quality: 78%  |  Relevancy: 90%  |  Overlap: 60%
```

Now `@AI_researcher` ranks higher even though overlap is lower!

---

## Why It's Better

### Old Way (Overlap Only)
- ✅ Fast
- ❌ Finds accounts that share your followers
- ❌ Doesn't care if they're in your niche
- ❌ Crypto account with 70% overlap > AI account with 60% overlap

### New Way (Quality Score)
- ✅ Finds accounts in your actual niche
- ✅ Weights content similarity higher (60%) than follower overlap (40%)
- ✅ AI account with 90% relevancy > Crypto account with 70% overlap
- ⚠️ Slower (needs to analyze content with AI)

---

## Limitations & Future Improvements

### Current Limitations:
1. **Only analyzes top 20 competitors** (API cost optimization)
2. **Uses bio + 10 recent posts** (limited data)
3. **Takes 2-3 minutes to run** (AI analysis per competitor)
4. **One-time calculation** (doesn't run continuously)

### To Get to 80-90% Matches:

**Option A: Engagement-Based Discovery** (Recommended)
```
Instead of "who you follow":
→ Scrape who likes/retweets YOUR posts
→ Find accounts that get engagement from same users
→ = True competitors fighting for same eyeballs
```

**Option B: Content-First Discovery**
```
1. Extract topics from YOUR posts (AI, productivity, etc.)
2. Search X for those topics
3. Find high-engagement accounts posting similar content
4. THEN check overlap
```

**Option C: Background Tasks**
```
- Daily: Scrape new posts, update scores
- Weekly: Re-discovery with expanded parameters
- Continuous: Quality improves over time
```

---

## Usage

1. Click **"Calculate Relevancy"** button (green)
2. Wait 2-3 minutes (analyzing top 20 with AI)
3. See updated scores:
   - **Quality** (green) = Overall match
   - **Relevancy** (blue) = Content/niche similarity
   - **Overlap** (purple) = Mutual followers %
4. Competitors auto-sorted by Quality Score

---

## Technical Details

**Files:**
- `competitor_relevancy_scorer.py` - Core logic
- `backend_websocket_server.py:1413` - API endpoint
- `page.tsx:264` - Frontend trigger

**AI Model:**
- Claude 3.5 Haiku (fast & cheap)
- ~$0.01 per 20 competitors
- Analyzes semantic similarity, not just keyword matching

**Weights (Configurable):**
```python
overlap_weight = 0.4      # 40% weight
relevancy_weight = 0.6    # 60% weight (niche matters more!)
```

**Storage:**
- Scores saved to PostgreSQL
- Persisted across sessions
- Updated only when you click "Calculate Relevancy"

---

## Next Steps

Want to improve match quality to 80-90%? Choose one:

1. **Engagement-Based Discovery** - Find accounts your audience actually engages with
2. **Content-First Search** - Search X for your exact topics first
3. **Background Processing** - Continuous improvement over time

Which approach do you want to implement?
