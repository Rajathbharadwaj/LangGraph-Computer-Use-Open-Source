"""
LinkedIn Growth Workflows

Workflow definitions for LinkedIn automation using the same structure as X/Twitter.
Each workflow is a sequence of steps that the LinkedIn agent executes.

Workflows are designed for professional engagement:
- Feed engagement (react, comment on feed posts)
- Profile engagement (build relationships with specific users)
- Content posting (create posts/articles)
- Connection outreach (send personalized connection requests)
"""

from typing import Dict, List, Any

# =============================================================================
# Workflow Definitions
# =============================================================================

LINKEDIN_ENGAGEMENT_WORKFLOW = {
    "id": "linkedin_engagement",
    "name": "LinkedIn Feed Engagement",
    "description": "Engage professionally with posts in the LinkedIn feed",
    "version": "1.0.0",

    "steps": [
        {
            "id": "navigate_to_feed",
            "name": "Navigate to Feed",
            "action": "linkedin_navigate_to_feed",
            "description": "Navigate to the LinkedIn home feed",
            "timeout": 30,
        },
        {
            "id": "check_session",
            "name": "Verify Session",
            "action": "linkedin_check_session_health",
            "description": "Verify we're logged in properly",
            "on_failure": "abort",
        },
        {
            "id": "get_feed_posts",
            "name": "Get Feed Posts",
            "action": "linkedin_get_feed_posts",
            "params": {"limit": 10},
            "description": "Extract posts from the feed for analysis",
        },
        {
            "id": "analyze_posts",
            "name": "Analyze Posts",
            "action": "llm_analyze",
            "description": "Use extended thinking to analyze posts for engagement worthiness",
            "prompt": """Analyze these LinkedIn posts and select the 3-5 best posts to engage with.

Consider:
- Relevance to professional interests
- Quality and substance of content
- Engagement potential (not too viral, not too quiet)
- Avoid: job postings, ads, controversial topics

For each selected post, note:
1. Why it's worth engaging
2. What kind of value we can add (insight, question, experience)
3. Suggested reaction type (Like, Insightful, Celebrate)
""",
        },
        {
            "id": "engage_with_posts",
            "name": "Engage with Posts",
            "action": "loop",
            "description": "For each selected post, like and/or comment",
            "loop_over": "selected_posts",
            "max_iterations": 5,
            "substeps": [
                {
                    "id": "get_post_context",
                    "action": "linkedin_get_post_context",
                    "description": "Get full context of the post",
                },
                {
                    "id": "craft_comment",
                    "action": "llm_generate",
                    "description": "Generate a thoughtful, professional comment",
                    "prompt": """Write a professional LinkedIn comment for this post.

Requirements:
- 50-300 characters
- Add genuine value (insight, question, or relevant experience)
- Professional but personable tone
- Reference specific content from the post
- NO generic phrases like "Great post!" or "Love this!"
- NO emojis (or maximum 1 if truly appropriate)

Post context:
{post_context}
""",
                },
                {
                    "id": "validate_comment",
                    "action": "validate_linkedin_comment",
                    "description": "Ensure comment meets quality standards",
                },
                {
                    "id": "react_to_post",
                    "action": "linkedin_like_post",
                    "description": "React to the post",
                    "params": {"reaction_type": "like"},
                },
                {
                    "id": "post_comment",
                    "action": "linkedin_comment_on_post",
                    "description": "Post the comment",
                    "delay_before": 2,  # Wait 2 seconds before commenting
                },
                {
                    "id": "wait_between_posts",
                    "action": "delay",
                    "params": {"seconds": 30},
                    "description": "Wait between engagements to appear human",
                },
            ],
        },
        {
            "id": "scroll_feed",
            "name": "Scroll for More",
            "action": "scroll_page",
            "params": {"scroll_y": 800},
            "description": "Scroll down to load more posts",
            "optional": True,
        },
    ],

    "daily_limits": {
        "reactions": 50,  # Conservative for safety
        "comments": 15,
    },

    "scheduling": {
        "recommended_times": ["09:00", "12:30", "17:00"],
        "recommended_days": ["Monday", "Tuesday", "Wednesday", "Thursday"],
        "timezone": "America/New_York",
    },
}


LINKEDIN_PROFILE_ENGAGEMENT_WORKFLOW = {
    "id": "linkedin_profile_engagement",
    "name": "LinkedIn Profile Engagement",
    "description": "Build relationship with a specific LinkedIn user",
    "version": "1.0.0",

    "inputs": {
        "profile_url": {
            "type": "string",
            "required": True,
            "description": "LinkedIn profile URL or username",
        },
        "send_connection": {
            "type": "boolean",
            "default": False,
            "description": "Whether to send a connection request",
        },
    },

    "steps": [
        {
            "id": "navigate_to_profile",
            "name": "Navigate to Profile",
            "action": "linkedin_navigate_to_profile",
            "params": {"profile_url": "{profile_url}"},
        },
        {
            "id": "extract_profile",
            "name": "Extract Profile Data",
            "action": "linkedin_extract_profile_insights",
            "description": "Get profile info for personalization",
        },
        {
            "id": "analyze_profile",
            "name": "Analyze Profile",
            "action": "llm_analyze",
            "description": "Analyze profile for engagement strategy",
            "prompt": """Analyze this LinkedIn profile to plan engagement:

Profile:
{profile_data}

Determine:
1. What topics/interests are relevant
2. What recent activity we can reference
3. How to personalize our engagement
4. If applicable, what connection note would resonate
""",
        },
        {
            "id": "find_recent_posts",
            "name": "Find Recent Posts",
            "action": "navigate_and_extract",
            "description": "Find user's recent posts to engage with",
        },
        {
            "id": "engage_with_posts",
            "name": "Engage with Posts",
            "action": "loop",
            "loop_over": "profile_posts",
            "max_iterations": 3,
            "substeps": [
                {
                    "id": "react_to_post",
                    "action": "linkedin_like_post",
                    "params": {"reaction_type": "insightful"},
                },
                {
                    "id": "delay",
                    "action": "delay",
                    "params": {"seconds": 5},
                },
            ],
        },
        {
            "id": "comment_on_best",
            "name": "Comment on Best Post",
            "action": "linkedin_comment_on_post",
            "description": "Leave a thoughtful comment on their best recent post",
            "conditional": "best_post_found",
        },
        {
            "id": "send_connection",
            "name": "Send Connection Request",
            "action": "linkedin_send_connection_request",
            "conditional": "{send_connection}",
            "params": {"note": "{personalized_note}"},
        },
    ],

    "daily_limits": {
        "profile_visits": 20,
        "reactions_per_profile": 3,
        "comments_per_profile": 1,
        "connection_requests": 5,
    },
}


LINKEDIN_CONTENT_POSTING_WORKFLOW = {
    "id": "linkedin_content_posting",
    "name": "LinkedIn Content Posting",
    "description": "Create and publish LinkedIn content",
    "version": "1.0.0",

    "inputs": {
        "content": {
            "type": "string",
            "required": False,
            "description": "Content to post (if not provided, will generate)",
        },
        "topic": {
            "type": "string",
            "required": False,
            "description": "Topic to write about (if generating content)",
        },
        "content_type": {
            "type": "string",
            "default": "post",
            "enum": ["post", "article"],
            "description": "Type of content to create",
        },
    },

    "steps": [
        {
            "id": "navigate_to_feed",
            "name": "Navigate to Feed",
            "action": "linkedin_navigate_to_feed",
        },
        {
            "id": "check_session",
            "name": "Verify Session",
            "action": "linkedin_check_session_health",
        },
        {
            "id": "generate_content",
            "name": "Generate Content",
            "action": "llm_generate",
            "conditional": "not content",
            "description": "Generate post content based on topic",
            "prompt": """Write a professional LinkedIn post about: {topic}

Guidelines:
- 150-500 words for optimal engagement
- Start with a hook (question, bold statement, or story)
- Provide genuine value (insights, tips, lessons)
- End with a question to encourage comments
- Use line breaks for readability
- 3-5 relevant hashtags at the end
- Professional but personable tone
- NO emoji overuse
""",
        },
        {
            "id": "validate_content",
            "name": "Validate Content",
            "action": "validate_linkedin_post",
            "description": "Ensure post meets guidelines",
        },
        {
            "id": "create_post",
            "name": "Create Post",
            "action": "linkedin_create_post",
            "params": {"content": "{final_content}"},
        },
        {
            "id": "verify_posted",
            "name": "Verify Posted",
            "action": "check_post_success",
            "description": "Confirm post was published successfully",
        },
    ],

    "daily_limits": {
        "posts": 2,
        "articles": 1,
    },

    "scheduling": {
        "recommended_times": ["09:00", "12:00", "17:30"],
        "avoid_times": ["22:00-06:00"],
    },
}


LINKEDIN_CONNECTION_OUTREACH_WORKFLOW = {
    "id": "linkedin_connection_outreach",
    "name": "LinkedIn Connection Outreach",
    "description": "Send personalized connection requests",
    "version": "1.0.0",

    "inputs": {
        "profiles": {
            "type": "array",
            "required": True,
            "description": "List of profile URLs to connect with",
        },
        "context": {
            "type": "string",
            "required": False,
            "description": "Context for personalization (e.g., 'met at conference')",
        },
    },

    "steps": [
        {
            "id": "process_profiles",
            "name": "Process Profiles",
            "action": "loop",
            "loop_over": "profiles",
            "max_iterations": 10,  # Daily limit
            "substeps": [
                {
                    "id": "navigate_to_profile",
                    "action": "linkedin_navigate_to_profile",
                    "params": {"profile_url": "{profile}"},
                },
                {
                    "id": "extract_profile",
                    "action": "linkedin_extract_profile_insights",
                },
                {
                    "id": "craft_note",
                    "action": "llm_generate",
                    "description": "Create personalized connection note",
                    "prompt": """Write a personalized LinkedIn connection request note.

Profile:
{profile_data}

Context: {context}

Requirements:
- Maximum 300 characters
- Reference something specific from their profile
- Explain why you want to connect
- Professional and genuine tone
- NO sales pitch or self-promotion
- Make it feel personal, not templated
""",
                },
                {
                    "id": "send_request",
                    "action": "linkedin_send_connection_request",
                    "params": {"note": "{connection_note}"},
                },
                {
                    "id": "wait",
                    "action": "delay",
                    "params": {"seconds": 60},
                    "description": "Wait between requests to avoid rate limits",
                },
            ],
        },
    ],

    "daily_limits": {
        "connection_requests": 10,
    },

    "warnings": [
        "LinkedIn is strict about connection request limits",
        "Too many ignored requests can restrict your account",
        "Quality over quantity - only connect with relevant people",
    ],
}


# =============================================================================
# Workflow Registry
# =============================================================================

LINKEDIN_WORKFLOWS: Dict[str, Dict[str, Any]] = {
    "linkedin_engagement": LINKEDIN_ENGAGEMENT_WORKFLOW,
    "linkedin_profile_engagement": LINKEDIN_PROFILE_ENGAGEMENT_WORKFLOW,
    "linkedin_content_posting": LINKEDIN_CONTENT_POSTING_WORKFLOW,
    "linkedin_connection_outreach": LINKEDIN_CONNECTION_OUTREACH_WORKFLOW,
}


def get_workflow(workflow_id: str) -> Dict[str, Any]:
    """Get a workflow by ID."""
    if workflow_id not in LINKEDIN_WORKFLOWS:
        raise ValueError(f"Unknown workflow: {workflow_id}")
    return LINKEDIN_WORKFLOWS[workflow_id]


def list_workflows() -> List[Dict[str, str]]:
    """List all available LinkedIn workflows."""
    return [
        {
            "id": w["id"],
            "name": w["name"],
            "description": w["description"],
        }
        for w in LINKEDIN_WORKFLOWS.values()
    ]


# =============================================================================
# Export
# =============================================================================

__all__ = [
    'LINKEDIN_ENGAGEMENT_WORKFLOW',
    'LINKEDIN_PROFILE_ENGAGEMENT_WORKFLOW',
    'LINKEDIN_CONTENT_POSTING_WORKFLOW',
    'LINKEDIN_CONNECTION_OUTREACH_WORKFLOW',
    'LINKEDIN_WORKFLOWS',
    'get_workflow',
    'list_workflows',
]
