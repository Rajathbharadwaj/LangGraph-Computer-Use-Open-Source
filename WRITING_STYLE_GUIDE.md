# 🎨 Writing Style Learning - Match User's Voice

## **The Problem**

The agent needs to **write comments and posts that sound EXACTLY like the user** - not generic AI-generated content.

**Bad (Generic AI)**:
```
"Great post! I completely agree with your insights on AI agents."
```

**Good (Sounds like the user)**:
```
"Interesting pattern! I've noticed similar behavior with subagent delegation. 
Have you experimented with different context isolation strategies?"
```

---

## 🎯 **The Solution: Few-Shot Learning with User's Past Posts**

### **Architecture**

```
1. CAPTURE user's past X posts/threads
    ↓
2. STORE in namespace with EMBEDDINGS (semantic search)
    ↓
3. ANALYZE writing style (tone, length, vocabulary)
    ↓
4. RETRIEVE similar examples when generating content
    ↓
5. FEW-SHOT PROMPTING with user's examples
    ↓
6. GENERATE content that matches user's style
```

---

## 📊 **What We Store**

### **1. Writing Samples**
```python
namespace = (user_id, "writing_samples")

# Each sample stored with embeddings for semantic search
{
  "sample_id": "uuid",
  "content_type": "comment",  # or "post", "thread"
  "content": "User's actual text...",
  "context": "What they were responding to",
  "engagement": {"likes": 15, "replies": 5},
  "topic": "LangGraph"
}
```

### **2. Writing Style Profile**
```python
namespace = (user_id, "writing_style")

{
  "tone": "technical",  # professional, casual, friendly
  "avg_post_length": 180,
  "avg_comment_length": 95,
  "uses_emojis": False,
  "uses_hashtags": False,
  "uses_questions": True,  # Often asks questions
  "sentence_structure": "medium",  # short, medium, long
  "technical_terms": ["LangGraph", "subagents", "RAG"],
  "common_phrases": ["interesting pattern", "have you tried", "in my experience"]
}
```

---

## 🔄 **How It Works**

### **Step 1: Import User's Past Posts**

```python
from x_writing_style_learner import XWritingStyleManager
from langgraph.store.memory import InMemoryStore
from langchain.embeddings import init_embeddings

# Create store with semantic search
embeddings = init_embeddings("openai:text-embedding-3-small")
store = InMemoryStore(
    index={
        "embed": embeddings,
        "dims": 1536,
    }
)

# Initialize style manager
style_manager = XWritingStyleManager(store, user_id="user_123")

# Import user's past posts (from X API or manual entry)
past_posts = [
    {
        "content": "Interesting pattern with LangGraph subagents...",
        "timestamp": "2025-10-15T10:30:00",
        "engagement": {"likes": 15, "replies": 5},
        "topic": "LangGraph"
    },
    # ... more posts
]

style_manager.bulk_import_posts(past_posts)
```

---

### **Step 2: Analyze Writing Style**

```python
# Analyze user's writing patterns
profile = style_manager.analyze_writing_style()

print(f"Tone: {profile.tone}")  # "technical"
print(f"Avg length: {profile.avg_comment_length}")  # 95 chars
print(f"Uses questions: {profile.uses_questions}")  # True
print(f"Technical terms: {profile.technical_terms}")  # ["LangGraph", "subagents"]
```

**What it analyzes:**
- Average post/comment length
- Tone (professional, casual, technical, friendly)
- Emoji and hashtag usage
- Question frequency
- Sentence structure (short, medium, long)
- Common phrases and vocabulary
- Technical terminology

---

### **Step 3: Retrieve Similar Examples (Semantic Search)**

```python
# When generating a comment, find similar past comments
context = "Someone posted: 'How do you handle agent context management?'"

similar_examples = style_manager.get_similar_examples(
    query=context,
    content_type="comment",
    limit=3
)

# Returns user's past comments about similar topics
for example in similar_examples:
    print(example.content)
    # "I've found that subagent delegation helps with context..."
    # "Context isolation is key. Have you tried..."
```

**Semantic search finds:**
- Comments on similar topics
- Comments with similar context
- Comments that got high engagement

---

### **Step 4: Generate Few-Shot Prompt**

```python
# Generate prompt with user's examples
prompt = style_manager.generate_few_shot_prompt(
    context="Post about: 'Struggling with LangGraph memory management'",
    content_type="comment",
    num_examples=3
)

print(prompt)
```

**Generated prompt:**
```
You are writing a comment in the style of this user.

WRITING STYLE PROFILE:
- Tone: technical
- Average length: 95 characters
- Uses emojis: False
- Uses questions: True
- Sentence structure: medium
- Technical terms: LangGraph, subagents, context isolation

EXAMPLES OF USER'S WRITING:

Example 1:
Context: Discussion about agent performance
User wrote: Interesting pattern! I've found that delegating to subagents 
really helps with token efficiency. Have you experimented with different 
context isolation strategies? (Got 15 engagement)

Example 2:
Context: Question about LangGraph
User wrote: In my experience, the key is keeping the main agent focused 
on high-level coordination. What's your current architecture look like?
(Got 23 engagement)

Example 3:
Context: Agent optimization discussion
User wrote: Quick tip: if your agent is making too many tool calls, try 
subagent delegation. Keeps context clean. (Got 31 engagement)

NOW, write a comment for this context:
Context: Post about: 'Struggling with LangGraph memory management'

Write in the EXACT same style as the examples above. Match:
- Tone and personality
- Sentence length and structure
- Technical terminology
- Question style

Your comment:
```

---

### **Step 5: LLM Generates in User's Style**

The LLM receives the few-shot prompt and generates:

```
"Have you looked into using the Store for cross-thread memory? 
I've found it really helps with persistent state. What's your 
current memory setup look like?"
```

**✅ Sounds like the user!**
- Technical terminology ✓
- Question style ✓
- Medium length ✓
- Helpful tone ✓

---

## 🎯 **Integration with Comment Generator Subagent**

Update the comment generator to use writing style:

```python
{
    "name": "style_aware_comment_generator",
    "description": "Generate comments in user's authentic writing style",
    "system_prompt": """You generate comments that sound EXACTLY like the user.

PROCESS:
1. Receive post to comment on
2. Search user's past comments (semantic search)
3. Get user's writing style profile
4. Use few-shot prompting with examples
5. Generate comment matching user's style

CRITICAL:
- ALWAYS retrieve similar examples first
- ALWAYS match user's tone and length
- ALWAYS use user's vocabulary
- NEVER use generic phrases

Access via:
- store.search((user_id, "writing_samples"), query=post, limit=3)
- store.get((user_id, "writing_style"), "profile")
""",
    "tools": []  # Uses store for retrieval
}
```

---

## 📈 **Benefits**

### **1. Authenticity**
- Comments sound like the user wrote them
- Maintains user's personality and voice
- No generic AI-sounding responses

### **2. Learning from Success**
```python
# Get high-engagement examples
best_comments = style_manager.get_high_engagement_examples(
    content_type="comment",
    min_engagement=10,
    limit=5
)

# Learn what works for this user
for comment in best_comments:
    print(f"{comment.content} → {sum(comment.engagement.values())} engagement")
```

### **3. Continuous Improvement**
- As user posts more, style profile improves
- Agent learns what gets engagement
- Adapts to user's evolving style

---

## 🚀 **Complete Flow Example**

### **User onboarding:**
```python
# 1. User connects X account
# 2. Fetch their last 100 posts/comments via X API
# 3. Import into writing_samples namespace
style_manager.bulk_import_posts(fetched_posts)

# 4. Analyze writing style
profile = style_manager.analyze_writing_style()

# 5. Ready to generate in user's style!
```

### **When agent needs to comment:**
```python
# 1. Agent sees a post to comment on
post_content = "Struggling with LangGraph context management..."

# 2. Retrieve similar examples
examples = style_manager.get_similar_examples(post_content, limit=3)

# 3. Generate few-shot prompt
prompt = style_manager.generate_few_shot_prompt(
    context=post_content,
    content_type="comment",
    num_examples=3
)

# 4. LLM generates comment
comment = llm.invoke(prompt)

# 5. Post comment (sounds like user!)
```

---

## 🎨 **Style Matching Examples**

### **User A (Technical, Question-based)**

**Past posts:**
- "Interesting pattern with subagent delegation. Anyone else seeing this?"
- "Have you experimented with different context isolation strategies?"
- "Quick tip: try delegating web searches to subagents for better token efficiency."

**Generated comment:**
```
"Have you looked into using the Store for persistent memory? 
I've found it really helps with cross-thread state. What's your 
current setup look like?"
```

---

### **User B (Casual, Emoji-heavy)**

**Past posts:**
- "Just shipped a new feature! 🚀 LangGraph is amazing"
- "This is so cool! 😍 Finally got subagents working"
- "Pro tip: context isolation = game changer 💯"

**Generated comment:**
```
"This is super helpful! 🙌 I had the same issue and Store 
solved it for me. Definitely worth trying! 💡"
```

---

### **User C (Professional, Detailed)**

**Past posts:**
- "In my experience, the most effective approach to agent context management involves..."
- "I've found that implementing a hierarchical memory structure significantly improves..."
- "The key consideration here is balancing token efficiency with context retention..."

**Generated comment:**
```
"In my experience, implementing the LangGraph Store for cross-thread 
memory has proven highly effective. I'd recommend exploring the 
namespace-based organization for better scalability."
```

---

## 🔧 **Production Setup**

### **1. Fetch User's Posts via X API**

```python
# When user connects their X account
import tweepy

# Use X API to fetch user's posts
api = tweepy.Client(bearer_token=os.environ["X_BEARER_TOKEN"])
tweets = api.get_users_tweets(
    user_id=x_user_id,
    max_results=100,
    tweet_fields=["created_at", "public_metrics"]
)

# Import into style manager
posts = []
for tweet in tweets.data:
    posts.append({
        "content": tweet.text,
        "timestamp": tweet.created_at.isoformat(),
        "engagement": {
            "likes": tweet.public_metrics["like_count"],
            "replies": tweet.public_metrics["reply_count"],
            "reposts": tweet.public_metrics["retweet_count"]
        }
    })

style_manager.bulk_import_posts(posts)
```

### **2. Update Style Profile Regularly**

```python
# Re-analyze style every week or after 50 new posts
if new_posts_count > 50:
    profile = style_manager.analyze_writing_style()
    print("✅ Style profile updated!")
```

### **3. A/B Test Generated Content**

```python
# Generate 2 versions
version_a = style_manager.generate_few_shot_prompt(context, num_examples=3)
version_b = style_manager.generate_few_shot_prompt(context, num_examples=5)

# Track which gets more engagement
# Update strategy based on results
```

---

## 🎉 **Summary**

**You now have:**
- ✅ **Writing sample storage** with semantic search
- ✅ **Style analysis** (tone, length, vocabulary)
- ✅ **Similar example retrieval** for few-shot prompting
- ✅ **Authentic content generation** that sounds like the user
- ✅ **Continuous learning** from high-engagement examples

**The agent can now:**
- ✅ Write comments that sound like YOU
- ✅ Match your tone and personality
- ✅ Use your vocabulary and phrases
- ✅ Learn from what works for you
- ✅ Improve over time

🚀 **No more generic AI comments - only authentic, user-style content!**

