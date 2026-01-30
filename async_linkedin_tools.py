"""
LinkedIn Playwright Tools for Browser Automation

This module provides LangChain-compatible tools for interacting with LinkedIn
through browser automation. Uses the same architecture as async_playwright_tools.py
for X/Twitter, with LinkedIn-specific selectors and logic.

Tools are designed for:
- Professional engagement (reactions, comments)
- Profile analysis
- Content creation
- Connection management
"""

import json
import logging
from typing import Optional
from langchain_core.tools import tool

from linkedin_selectors import (
    AUTH_SELECTORS,
    POST_SELECTORS,
    ENGAGEMENT_SELECTORS,
    COMMENT_SELECTORS,
    PROFILE_SELECTORS,
    COMPOSE_SELECTORS,
)

logger = logging.getLogger(__name__)


# =============================================================================
# Helper Functions
# =============================================================================

def _get_cua_url_from_runtime(runtime) -> str:
    """Extract CUA URL from runtime context."""
    if hasattr(runtime, 'context') and runtime.context:
        return runtime.context.get('cua_url', '')
    return ''


async def _get_client_for_url(url: str):
    """Get or create AsyncPlaywrightClient for the given URL."""
    # Import here to avoid circular imports
    from async_playwright_client import AsyncPlaywrightClient, get_client_for_url
    return get_client_for_url(url)


# =============================================================================
# Tool Factory Function
# =============================================================================

def create_async_linkedin_tools():
    """
    Create LinkedIn-specific Playwright tools.

    Returns:
        List of LangChain tools for LinkedIn automation
    """

    # =========================================================================
    # Session Health Tools
    # =========================================================================

    @tool
    async def linkedin_check_session_health(runtime=None) -> str:
        """
        Check if the LinkedIn session is healthy and logged in.

        Returns:
            JSON with login status, username if found, and any warnings
        """
        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available", "logged_in": False})

        client = await _get_client_for_url(cua_url)

        try:
            # Get page info
            page_info = await client.get_page_info()
            current_url = page_info.get('url', '')

            # Check if on LinkedIn
            if 'linkedin.com' not in current_url:
                return json.dumps({
                    "logged_in": False,
                    "error": "Not on LinkedIn",
                    "current_url": current_url
                })

            # Look for logged-in indicators
            elements = await client.get_dom_elements()
            element_texts = [e.get('text', '').lower() for e in elements]
            element_selectors = [e.get('selector', '') for e in elements]

            # Check for feed content (strong indicator of logged in)
            has_feed = any('.feed-shared-update' in s for s in element_selectors)

            # Check for messaging icon
            has_messaging = any('messaging' in t for t in element_texts)

            # Check for profile/nav elements
            has_nav = any('my network' in t or 'notifications' in t for t in element_texts)

            logged_in = has_feed or (has_messaging and has_nav)

            # Try to get username from nav
            username = None
            for elem in elements:
                if '/in/' in elem.get('selector', ''):
                    # Extract username from profile link
                    selector = elem.get('selector', '')
                    if 'href' in selector:
                        parts = selector.split('/in/')
                        if len(parts) > 1:
                            username = parts[1].split('/')[0].split('"')[0]
                            break

            result = {
                "logged_in": logged_in,
                "username": username,
                "current_url": current_url,
                "has_feed": has_feed,
                "has_messaging": has_messaging,
            }

            if not logged_in:
                result["warning"] = "Session may be expired. User should re-authenticate."

            return json.dumps(result)

        except Exception as e:
            logger.error(f"Error checking LinkedIn session: {e}")
            return json.dumps({"error": str(e), "logged_in": False})

    # =========================================================================
    # Navigation Tools
    # =========================================================================

    @tool
    async def linkedin_navigate_to_feed(runtime=None) -> str:
        """
        Navigate to the LinkedIn home feed.

        Returns:
            JSON with success status and current URL
        """
        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            result = await client.navigate("https://www.linkedin.com/feed/")
            return json.dumps({
                "success": True,
                "url": "https://www.linkedin.com/feed/",
                "navigation_result": result
            })
        except Exception as e:
            logger.error(f"Error navigating to LinkedIn feed: {e}")
            return json.dumps({"error": str(e), "success": False})

    @tool
    async def linkedin_navigate_to_profile(profile_url: str, runtime=None) -> str:
        """
        Navigate to a LinkedIn profile page.

        Args:
            profile_url: Full LinkedIn profile URL or username (e.g., 'johndoe' or 'https://linkedin.com/in/johndoe')

        Returns:
            JSON with success status and profile data
        """
        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        # Normalize URL
        if not profile_url.startswith('http'):
            profile_url = f"https://www.linkedin.com/in/{profile_url}/"

        try:
            result = await client.navigate(profile_url)
            return json.dumps({
                "success": True,
                "url": profile_url,
                "navigation_result": result
            })
        except Exception as e:
            logger.error(f"Error navigating to profile: {e}")
            return json.dumps({"error": str(e), "success": False})

    # =========================================================================
    # Feed Analysis Tools
    # =========================================================================

    @tool
    async def linkedin_get_feed_posts(limit: int = 5, runtime=None) -> str:
        """
        Get posts from the LinkedIn feed.

        Args:
            limit: Maximum number of posts to return (default 5)

        Returns:
            JSON array of posts with author, content, and engagement data
        """
        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # JavaScript to extract posts
            js_code = f"""
            (function() {{
                const posts = [];
                const containers = document.querySelectorAll('.feed-shared-update-v2');

                for (let i = 0; i < Math.min(containers.length, {limit}); i++) {{
                    const container = containers[i];
                    const post = {{}};

                    // Author info
                    const authorEl = container.querySelector('.feed-shared-actor__name');
                    post.author = authorEl ? authorEl.innerText.trim() : 'Unknown';

                    const headlineEl = container.querySelector('.feed-shared-actor__description');
                    post.author_headline = headlineEl ? headlineEl.innerText.trim() : '';

                    // Content
                    const contentEl = container.querySelector('.feed-shared-text');
                    post.content = contentEl ? contentEl.innerText.trim() : '';

                    // Engagement counts
                    const reactionsEl = container.querySelector('.social-details-social-counts__reactions-count');
                    post.reactions = reactionsEl ? reactionsEl.innerText.trim() : '0';

                    const commentsEl = container.querySelector('.social-details-social-counts__comments');
                    post.comments = commentsEl ? commentsEl.innerText.trim() : '0';

                    // Post link
                    const linkEl = container.querySelector('a[href*="/feed/update/"]');
                    post.url = linkEl ? linkEl.href : '';

                    // Index for reference
                    post.index = i;

                    posts.push(post);
                }}

                return JSON.stringify(posts);
            }})();
            """

            result = await client.evaluate(js_code)
            posts = json.loads(result) if isinstance(result, str) else result

            return json.dumps({
                "success": True,
                "count": len(posts),
                "posts": posts
            })

        except Exception as e:
            logger.error(f"Error getting feed posts: {e}")
            return json.dumps({"error": str(e), "success": False})

    @tool
    async def linkedin_get_post_context(post_identifier: str, runtime=None) -> str:
        """
        Get detailed context for a specific post.

        Args:
            post_identifier: Post author name, content snippet, or index number

        Returns:
            JSON with post details including author, content, and engagement
        """
        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # JavaScript to find and extract post
            js_code = f"""
            (function() {{
                const identifier = `{post_identifier.replace('`', '\\`')}`;
                const containers = document.querySelectorAll('.feed-shared-update-v2');

                for (let container of containers) {{
                    const authorEl = container.querySelector('.feed-shared-actor__name');
                    const contentEl = container.querySelector('.feed-shared-text');

                    const author = authorEl ? authorEl.innerText.trim() : '';
                    const content = contentEl ? contentEl.innerText.trim() : '';

                    // Match by author, content, or index
                    const isIndex = !isNaN(parseInt(identifier));
                    const matchesAuthor = author.toLowerCase().includes(identifier.toLowerCase());
                    const matchesContent = content.toLowerCase().includes(identifier.toLowerCase());

                    if (matchesAuthor || matchesContent || (isIndex && Array.from(containers).indexOf(container) === parseInt(identifier))) {{
                        const post = {{}};
                        post.author = author;

                        const headlineEl = container.querySelector('.feed-shared-actor__description');
                        post.author_headline = headlineEl ? headlineEl.innerText.trim() : '';

                        post.content = content;

                        // Engagement
                        const reactionsEl = container.querySelector('.social-details-social-counts__reactions-count');
                        post.reactions = reactionsEl ? reactionsEl.innerText.trim() : '0';

                        const commentsEl = container.querySelector('.social-details-social-counts__comments');
                        post.comments = commentsEl ? commentsEl.innerText.trim() : '0';

                        // Post URL
                        const linkEl = container.querySelector('a[href*="/feed/update/"]');
                        post.url = linkEl ? linkEl.href : '';

                        // Timestamp
                        const timeEl = container.querySelector('.feed-shared-actor__sub-description');
                        post.timestamp = timeEl ? timeEl.innerText.trim() : '';

                        return JSON.stringify({{found: true, post: post}});
                    }}
                }}

                return JSON.stringify({{found: false, error: 'Post not found'}});
            }})();
            """

            result = await client.evaluate(js_code)
            data = json.loads(result) if isinstance(result, str) else result

            return json.dumps(data)

        except Exception as e:
            logger.error(f"Error getting post context: {e}")
            return json.dumps({"error": str(e), "found": False})

    # =========================================================================
    # Engagement Tools
    # =========================================================================

    @tool
    async def linkedin_like_post(post_identifier: str, reaction_type: str = "like", runtime=None) -> str:
        """
        React to a LinkedIn post.

        Args:
            post_identifier: Post author name, content snippet, or index number
            reaction_type: One of 'like', 'celebrate', 'support', 'love', 'insightful', 'funny'

        Returns:
            JSON with success status
        """
        # Validate reaction type first (before CUA check)
        valid_reactions = ['like', 'celebrate', 'support', 'love', 'insightful', 'funny']
        if reaction_type.lower() not in valid_reactions:
            return json.dumps({"error": f"Invalid reaction type. Must be one of: {valid_reactions}"})

        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # JavaScript to find post and click like button
            js_code = f"""
            (function() {{
                const identifier = `{post_identifier.replace('`', '\\`')}`;
                const reactionType = '{reaction_type.lower()}';
                const containers = document.querySelectorAll('.feed-shared-update-v2');

                for (let container of containers) {{
                    const authorEl = container.querySelector('.feed-shared-actor__name');
                    const contentEl = container.querySelector('.feed-shared-text');

                    const author = authorEl ? authorEl.innerText.trim() : '';
                    const content = contentEl ? contentEl.innerText.trim() : '';

                    const isIndex = !isNaN(parseInt(identifier));
                    const matchesAuthor = author.toLowerCase().includes(identifier.toLowerCase());
                    const matchesContent = content.toLowerCase().includes(identifier.toLowerCase());

                    if (matchesAuthor || matchesContent || (isIndex && Array.from(containers).indexOf(container) === parseInt(identifier))) {{
                        // Find like button
                        const likeButton = container.querySelector('button[aria-label*="Like"]');

                        if (!likeButton) {{
                            return JSON.stringify({{success: false, error: 'Like button not found'}});
                        }}

                        // Check if already liked
                        if (likeButton.getAttribute('aria-pressed') === 'true') {{
                            return JSON.stringify({{success: true, already_liked: true, author: author}});
                        }}

                        // For simple like, just click
                        if (reactionType === 'like') {{
                            likeButton.click();
                            return JSON.stringify({{success: true, reaction: 'like', author: author}});
                        }}

                        // For other reactions, need to hover and select
                        // Trigger hover to show reaction panel
                        const hoverEvent = new MouseEvent('mouseenter', {{bubbles: true}});
                        likeButton.dispatchEvent(hoverEvent);

                        // Wait briefly for panel
                        return JSON.stringify({{
                            success: true,
                            note: 'Hover triggered - select reaction from panel',
                            reaction: reactionType,
                            author: author
                        }});
                    }}
                }}

                return JSON.stringify({{success: false, error: 'Post not found'}});
            }})();
            """

            result = await client.evaluate(js_code)
            data = json.loads(result) if isinstance(result, str) else result

            return json.dumps(data)

        except Exception as e:
            logger.error(f"Error liking post: {e}")
            return json.dumps({"error": str(e), "success": False})

    @tool
    async def linkedin_comment_on_post(post_identifier: str, comment_text: str, runtime=None) -> str:
        """
        Comment on a LinkedIn post.

        Args:
            post_identifier: Post author name, content snippet, or index number
            comment_text: The comment to post (50-500 chars recommended)

        Returns:
            JSON with success status
        """
        # Validate comment length first (before CUA check)
        if len(comment_text) < 10:
            return json.dumps({"error": "Comment too short. Minimum 10 characters."})
        if len(comment_text) > 1250:
            return json.dumps({"error": "Comment too long. Maximum 1250 characters."})

        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # Step 1: Find post and click comment button
            find_js = f"""
            (function() {{
                const identifier = `{post_identifier.replace('`', '\\`')}`;
                const containers = document.querySelectorAll('.feed-shared-update-v2');

                for (let i = 0; i < containers.length; i++) {{
                    const container = containers[i];
                    const authorEl = container.querySelector('.feed-shared-actor__name');
                    const contentEl = container.querySelector('.feed-shared-text');

                    const author = authorEl ? authorEl.innerText.trim() : '';
                    const content = contentEl ? contentEl.innerText.trim() : '';

                    const isIndex = !isNaN(parseInt(identifier));
                    const matchesAuthor = author.toLowerCase().includes(identifier.toLowerCase());
                    const matchesContent = content.toLowerCase().includes(identifier.toLowerCase());

                    if (matchesAuthor || matchesContent || (isIndex && i === parseInt(identifier))) {{
                        // Click comment button to open comment box
                        const commentButton = container.querySelector('button[aria-label*="Comment"]');
                        if (commentButton) {{
                            commentButton.click();
                            return JSON.stringify({{found: true, author: author, index: i}});
                        }}
                        return JSON.stringify({{found: false, error: 'Comment button not found'}});
                    }}
                }}

                return JSON.stringify({{found: false, error: 'Post not found'}});
            }})();
            """

            find_result = await client.evaluate(find_js)
            find_data = json.loads(find_result) if isinstance(find_result, str) else find_result

            if not find_data.get('found'):
                return json.dumps(find_data)

            # Wait for comment box to appear
            import asyncio
            await asyncio.sleep(0.5)

            # Step 2: Type the comment
            # Find and focus the comment input
            focus_js = """
            (function() {
                const inputs = document.querySelectorAll('.ql-editor, [contenteditable="true"]');
                for (let input of inputs) {
                    if (input.offsetParent !== null) {  // Visible
                        input.focus();
                        return JSON.stringify({focused: true});
                    }
                }
                return JSON.stringify({focused: false, error: 'Comment input not found'});
            })();
            """

            focus_result = await client.evaluate(focus_js)
            focus_data = json.loads(focus_result) if isinstance(focus_result, str) else focus_result

            if not focus_data.get('focused'):
                return json.dumps({"error": "Could not focus comment input", "success": False})

            # Type the comment
            await client.type_text(comment_text)

            await asyncio.sleep(0.3)

            # Step 3: Submit the comment
            submit_js = """
            (function() {
                const submitButtons = document.querySelectorAll('button.comments-comment-box__submit-button');
                for (let btn of submitButtons) {
                    if (!btn.disabled && btn.offsetParent !== null) {
                        btn.click();
                        return JSON.stringify({submitted: true});
                    }
                }
                return JSON.stringify({submitted: false, error: 'Submit button not found or disabled'});
            })();
            """

            submit_result = await client.evaluate(submit_js)
            submit_data = json.loads(submit_result) if isinstance(submit_result, str) else submit_result

            return json.dumps({
                "success": submit_data.get('submitted', False),
                "author": find_data.get('author'),
                "comment_length": len(comment_text),
                "submit_result": submit_data
            })

        except Exception as e:
            logger.error(f"Error commenting on post: {e}")
            return json.dumps({"error": str(e), "success": False})

    # =========================================================================
    # Profile Tools
    # =========================================================================

    @tool
    async def linkedin_extract_profile_insights(profile_url: str = None, runtime=None) -> str:
        """
        Extract insights from a LinkedIn profile page.

        Args:
            profile_url: Optional profile URL. If not provided, extracts from current page.

        Returns:
            JSON with profile data including name, headline, about, experience
        """
        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # Navigate if URL provided
            if profile_url:
                if not profile_url.startswith('http'):
                    profile_url = f"https://www.linkedin.com/in/{profile_url}/"
                await client.navigate(profile_url)
                import asyncio
                await asyncio.sleep(1)

            # Extract profile data
            js_code = """
            (function() {
                const profile = {};

                // Name
                const nameEl = document.querySelector('.text-heading-xlarge');
                profile.name = nameEl ? nameEl.innerText.trim() : '';

                // Headline
                const headlineEl = document.querySelector('.text-body-medium.break-words');
                profile.headline = headlineEl ? headlineEl.innerText.trim() : '';

                // Location
                const locationEl = document.querySelector('.text-body-small.inline.t-black--light.break-words');
                profile.location = locationEl ? locationEl.innerText.trim() : '';

                // Connections
                const connectionsEl = document.querySelector('a[href*="/connections"] span');
                profile.connections = connectionsEl ? connectionsEl.innerText.trim() : '';

                // About section
                const aboutEl = document.querySelector('#about ~ .display-flex .inline-show-more-text');
                profile.about = aboutEl ? aboutEl.innerText.trim() : '';

                // Current company/role (first experience)
                const experienceEl = document.querySelector('#experience ~ .display-flex .display-flex.flex-column');
                if (experienceEl) {
                    const roleEl = experienceEl.querySelector('.t-bold span');
                    const companyEl = experienceEl.querySelector('.t-normal span');
                    profile.current_role = roleEl ? roleEl.innerText.trim() : '';
                    profile.current_company = companyEl ? companyEl.innerText.trim() : '';
                }

                // Profile URL
                profile.url = window.location.href;

                return JSON.stringify(profile);
            })();
            """

            result = await client.evaluate(js_code)
            profile = json.loads(result) if isinstance(result, str) else result

            return json.dumps({
                "success": True,
                "profile": profile
            })

        except Exception as e:
            logger.error(f"Error extracting profile: {e}")
            return json.dumps({"error": str(e), "success": False})

    @tool
    async def linkedin_send_connection_request(profile_url: str, note: str = None, runtime=None) -> str:
        """
        Send a connection request to a LinkedIn user.

        Args:
            profile_url: Profile URL or username
            note: Optional personalized note (max 300 chars)

        Returns:
            JSON with success status
        """
        # Validate note length first (before CUA check)
        if note and len(note) > 300:
            return json.dumps({"error": "Note too long. Maximum 300 characters."})

        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # Navigate to profile
            if not profile_url.startswith('http'):
                profile_url = f"https://www.linkedin.com/in/{profile_url}/"

            await client.navigate(profile_url)
            import asyncio
            await asyncio.sleep(1)

            # Find and click Connect button
            connect_js = """
            (function() {
                // Try different connect button selectors
                // Try specific selectors first
                const specificBtn = document.querySelector('button[aria-label*="Invite"][aria-label*="connect"]');
                if (specificBtn && specificBtn.offsetParent !== null) {
                    specificBtn.click();
                    return JSON.stringify({clicked: true});
                }

                // Fallback: find any visible button containing "Connect"
                const btn = Array.from(document.querySelectorAll('button')).find(b =>
                    b.innerText.trim() === 'Connect' && b.offsetParent !== null);
                if (btn) {
                    btn.click();
                    return JSON.stringify({clicked: true});
                }

                return JSON.stringify({clicked: false, error: 'Connect button not found'});
            })();
            """

            connect_result = await client.evaluate(connect_js)
            connect_data = json.loads(connect_result) if isinstance(connect_result, str) else connect_result

            if not connect_data.get('clicked'):
                return json.dumps(connect_data)

            await asyncio.sleep(0.5)

            # If note provided, click "Add a note"
            if note:
                add_note_js = """
                (function() {
                    const addNoteBtn = document.querySelector('button[aria-label="Add a note"]');
                    if (addNoteBtn) {
                        addNoteBtn.click();
                        return JSON.stringify({clicked: true});
                    }
                    return JSON.stringify({clicked: false});
                })();
                """

                note_result = await client.evaluate(add_note_js)
                note_data = json.loads(note_result) if isinstance(note_result, str) else note_result

                if note_data.get('clicked'):
                    await asyncio.sleep(0.3)
                    # Type the note
                    await client.type_text(note)
                    await asyncio.sleep(0.2)

            # Click send
            send_js = """
            (function() {
                const sendBtn = document.querySelector('button[aria-label*="Send"]') ||
                               Array.from(document.querySelectorAll('button')).find(b =>
                                   b.innerText.trim() === 'Send' || b.innerText.trim() === 'Send now');
                if (sendBtn && !sendBtn.disabled) {
                    sendBtn.click();
                    return JSON.stringify({sent: true});
                }
                return JSON.stringify({sent: false, error: 'Send button not found'});
            })();
            """

            send_result = await client.evaluate(send_js)
            send_data = json.loads(send_result) if isinstance(send_result, str) else send_result

            return json.dumps({
                "success": send_data.get('sent', False),
                "profile_url": profile_url,
                "note_included": bool(note)
            })

        except Exception as e:
            logger.error(f"Error sending connection request: {e}")
            return json.dumps({"error": str(e), "success": False})

    # =========================================================================
    # Content Creation Tools
    # =========================================================================

    @tool
    async def linkedin_create_post(content: str, runtime=None) -> str:
        """
        Create a new LinkedIn post.

        Args:
            content: Post content (max 3000 chars for regular posts)

        Returns:
            JSON with success status
        """
        # Validate content first (before CUA check)
        if len(content) > 3000:
            return json.dumps({"error": "Post too long. Maximum 3000 characters for posts."})
        if len(content) < 1:
            return json.dumps({"error": "Post content cannot be empty."})

        cua_url = _get_cua_url_from_runtime(runtime)
        if not cua_url:
            return json.dumps({"error": "No CUA URL available"})

        client = await _get_client_for_url(cua_url)

        try:
            # Navigate to feed if not already there
            page_info = await client.get_page_info()
            if '/feed' not in page_info.get('url', ''):
                await client.navigate("https://www.linkedin.com/feed/")
                import asyncio
                await asyncio.sleep(1)

            # Click "Start a post"
            start_js = """
            (function() {
                const startBtn = document.querySelector('.share-box-feed-entry__trigger') ||
                                Array.from(document.querySelectorAll('button')).find(b =>
                                    b.innerText.toLowerCase().includes('start a post'));
                if (startBtn) {
                    startBtn.click();
                    return JSON.stringify({clicked: true});
                }
                return JSON.stringify({clicked: false, error: 'Start post button not found'});
            })();
            """

            start_result = await client.evaluate(start_js)
            start_data = json.loads(start_result) if isinstance(start_result, str) else start_result

            if not start_data.get('clicked'):
                return json.dumps(start_data)

            import asyncio
            await asyncio.sleep(0.5)

            # Focus the editor and type content
            focus_js = """
            (function() {
                const editor = document.querySelector('.ql-editor') ||
                              document.querySelector('[contenteditable="true"]');
                if (editor) {
                    editor.focus();
                    return JSON.stringify({focused: true});
                }
                return JSON.stringify({focused: false, error: 'Editor not found'});
            })();
            """

            focus_result = await client.evaluate(focus_js)
            focus_data = json.loads(focus_result) if isinstance(focus_result, str) else focus_result

            if not focus_data.get('focused'):
                return json.dumps({"error": "Could not focus post editor", "success": False})

            # Type the content
            await client.type_text(content)
            await asyncio.sleep(0.3)

            # Click Post button
            post_js = """
            (function() {
                const postBtn = document.querySelector('button.share-actions__primary-action');
                if (postBtn && !postBtn.disabled) {
                    postBtn.click();
                    return JSON.stringify({posted: true});
                }
                return JSON.stringify({posted: false, error: 'Post button not found or disabled'});
            })();
            """

            post_result = await client.evaluate(post_js)
            post_data = json.loads(post_result) if isinstance(post_result, str) else post_result

            return json.dumps({
                "success": post_data.get('posted', False),
                "content_length": len(content)
            })

        except Exception as e:
            logger.error(f"Error creating post: {e}")
            return json.dumps({"error": str(e), "success": False})

    # =========================================================================
    # Return All Tools
    # =========================================================================

    return [
        # Session
        linkedin_check_session_health,

        # Navigation
        linkedin_navigate_to_feed,
        linkedin_navigate_to_profile,

        # Feed Analysis
        linkedin_get_feed_posts,
        linkedin_get_post_context,

        # Engagement
        linkedin_like_post,
        linkedin_comment_on_post,

        # Profile
        linkedin_extract_profile_insights,
        linkedin_send_connection_request,

        # Content Creation
        linkedin_create_post,
    ]


# =============================================================================
# Export
# =============================================================================

__all__ = ['create_async_linkedin_tools']
