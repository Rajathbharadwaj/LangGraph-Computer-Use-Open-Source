"""
LinkedIn DOM Selectors for Playwright Automation

These selectors are used by async_linkedin_tools.py to interact with LinkedIn's UI.
LinkedIn's DOM is more stable than X's, but selectors should be verified periodically.

Selector Strategy:
1. Prefer aria-labels for buttons (accessible and stable)
2. Use data-* attributes when available
3. Fall back to class names for containers
4. Use text-based selectors for buttons as last resort
"""

# =============================================================================
# Authentication & Session Indicators
# =============================================================================

AUTH_SELECTORS = {
    # Logged-in indicators
    "profile_menu": '[data-control-name="nav.settings"]',
    "nav_profile_link": 'a[href*="/in/"][data-control-name="identity_profile_photo"]',
    "messaging_icon": '.msg-overlay-bubble-header',
    "notifications_icon": 'a[href*="/notifications/"]',

    # Feed presence (confirms logged in)
    "feed_container": '.scaffold-finite-scroll__content',
    "feed_post": '.feed-shared-update-v2',

    # Login page elements
    "login_button": 'a[href*="/login"]',
    "login_email_input": '#username',
    "login_password_input": '#password',
    "login_submit": 'button[type="submit"]',
}

# =============================================================================
# Navigation
# =============================================================================

NAV_SELECTORS = {
    "home_link": 'a[href*="/feed/"]',
    "my_network_link": 'a[href*="/mynetwork/"]',
    "jobs_link": 'a[href*="/jobs/"]',
    "messaging_link": 'a[href*="/messaging/"]',
    "notifications_link": 'a[href*="/notifications/"]',
    "search_input": 'input[placeholder*="Search"]',
}

# =============================================================================
# Post Containers & Content
# =============================================================================

POST_SELECTORS = {
    # Post container
    "post_container": '.feed-shared-update-v2',
    "post_inner": '.feed-shared-update-v2__description-wrapper',

    # Author info
    "post_author": '.feed-shared-actor__name',
    "post_author_link": '.feed-shared-actor__container-link',
    "post_author_headline": '.feed-shared-actor__description',
    "post_author_image": '.feed-shared-actor__avatar-image',

    # Post content
    "post_content": '.feed-shared-text',
    "post_content_expanded": '.feed-shared-text--less-emphasis',
    "see_more_button": 'button.feed-shared-inline-show-more-text__button',

    # Post media
    "post_image": '.feed-shared-image__image',
    "post_video": '.feed-shared-linkedin-video',
    "post_document": '.feed-shared-document',
    "post_poll": '.feed-shared-poll',

    # Post metadata
    "post_timestamp": '.feed-shared-actor__sub-description',
    "post_visibility": '.feed-shared-actor__supplementary-actor-info',
}

# =============================================================================
# Engagement Buttons
# =============================================================================

ENGAGEMENT_SELECTORS = {
    # Main engagement buttons (in post footer)
    "like_button": 'button[aria-label*="Like"]',
    "comment_button": 'button[aria-label*="Comment"]',
    "repost_button": 'button[aria-label*="Repost"]',
    "send_button": 'button[aria-label*="Send"]',

    # Reaction panel (shows on like button hover/click)
    "reaction_panel": '.reactions-menu',
    "reaction_like": '[aria-label="Like"]',
    "reaction_celebrate": '[aria-label="Celebrate"]',
    "reaction_support": '[aria-label="Support"]',
    "reaction_love": '[aria-label="Love"]',
    "reaction_insightful": '[aria-label="Insightful"]',
    "reaction_funny": '[aria-label="Funny"]',

    # Already reacted indicator
    "liked_button": 'button[aria-pressed="true"][aria-label*="Like"]',
    "reacted_indicator": '.reactions-react-button--active',

    # Engagement counts
    "reactions_count": '.social-details-social-counts__reactions-count',
    "comments_count": '.social-details-social-counts__comments',
    "reposts_count": '.social-details-social-counts__item--with-social-proof',
}

# =============================================================================
# Comment Section
# =============================================================================

COMMENT_SELECTORS = {
    # Comment input
    "comment_box": '.comments-comment-box',
    "comment_input": '.comments-comment-box__form-container .ql-editor',
    "comment_input_placeholder": '[data-placeholder="Add a comment..."]',
    "comment_submit": 'button.comments-comment-box__submit-button',
    "comment_submit_enabled": 'button.comments-comment-box__submit-button:not([disabled])',

    # Comment list
    "comments_section": '.comments-comments-list',
    "comment_item": '.comments-comment-item',
    "comment_author": '.comments-post-meta__name-text',
    "comment_content": '.comments-comment-item__main-content',
    "comment_reactions": '.comments-comment-social-bar__reactions-count',
    "comment_replies_count": '.comments-comment-social-bar__replies-count',

    # Comment actions
    "comment_like_button": 'button[aria-label*="Like this comment"]',
    "comment_reply_button": 'button[aria-label*="Reply"]',
    "comment_more_button": 'button[aria-label*="Open options"]',
}

# =============================================================================
# Profile Page
# =============================================================================

PROFILE_SELECTORS = {
    # Profile header
    "profile_name": '.text-heading-xlarge',
    "profile_headline": '.text-body-medium.break-words',
    "profile_location": '.text-body-small.inline.t-black--light',
    "profile_connections": 'a[href*="/connections"] span.t-bold',
    "profile_followers": 'span:has-text("followers")',
    "profile_image": '.pv-top-card-profile-picture__image',
    "profile_banner": '.profile-background-image',

    # Profile sections
    "about_section": '#about',
    "experience_section": '#experience',
    "education_section": '#education',
    "skills_section": '#skills',

    # Profile actions
    "connect_button": 'button:has-text("Connect")',
    "connect_button_alt": 'button[aria-label*="Invite"][aria-label*="connect"]',
    "follow_button": 'button:has-text("Follow")',
    "message_button": 'button:has-text("Message")',
    "more_button": 'button[aria-label="More actions"]',

    # Connection request modal
    "add_note_button": 'button[aria-label="Add a note"]',
    "note_input": 'textarea[name="message"]',
    "send_invitation_button": 'button[aria-label="Send invitation"]',
    "send_without_note_button": 'button[aria-label="Send without a note"]',
}

# =============================================================================
# Content Creation
# =============================================================================

COMPOSE_SELECTORS = {
    # Start post button
    "start_post_button": 'button:has-text("Start a post")',
    "start_post_area": '.share-box-feed-entry__trigger',

    # Post composer modal
    "composer_modal": '.share-creation-state__text-editor',
    "composer_input": '.ql-editor[data-placeholder="What do you want to talk about?"]',
    "composer_input_alt": '[role="textbox"][contenteditable="true"]',

    # Media buttons
    "add_photo_button": 'button[aria-label="Add a photo"]',
    "add_video_button": 'button[aria-label="Add a video"]',
    "add_document_button": 'button[aria-label="Add a document"]',
    "add_poll_button": 'button[aria-label="Create a poll"]',

    # Post settings
    "visibility_button": '.share-creation-state__visibility-container button',
    "anyone_option": '[data-control-name="visibility_anyone"]',
    "connections_option": '[data-control-name="visibility_connections_only"]',

    # Submit
    "post_button": 'button.share-actions__primary-action',
    "post_button_enabled": 'button.share-actions__primary-action:not([disabled])',

    # Hashtag suggestions
    "hashtag_suggestions": '.share-creation-hashtag-pill',
}

# =============================================================================
# Messaging / DMs
# =============================================================================

MESSAGING_SELECTORS = {
    # Messaging overlay
    "messaging_overlay": '.msg-overlay-list-bubble',
    "messaging_compose": 'button[aria-label="Compose message"]',

    # Conversation list
    "conversation_list": '.msg-conversations-container__conversations-list',
    "conversation_item": '.msg-conversation-listitem',
    "conversation_name": '.msg-conversation-card__participant-names',
    "unread_indicator": '.msg-conversation-card__unread-count',

    # Message thread
    "message_input": '.msg-form__contenteditable',
    "send_message_button": 'button.msg-form__send-button',
    "message_list": '.msg-s-message-list',
    "message_item": '.msg-s-event-listitem',
}

# =============================================================================
# Search Results
# =============================================================================

SEARCH_SELECTORS = {
    "search_input": 'input[placeholder*="Search"]',
    "search_button": 'button[aria-label="Search"]',

    # Filters
    "people_filter": 'button:has-text("People")',
    "posts_filter": 'button:has-text("Posts")',
    "companies_filter": 'button:has-text("Companies")',

    # Results
    "search_result_item": '.search-result__wrapper',
    "search_result_name": '.search-result__title',
    "search_result_headline": '.search-result__subtitle',
}

# =============================================================================
# Utility Selectors
# =============================================================================

UTILITY_SELECTORS = {
    # Loading indicators
    "spinner": '.artdeco-spinner',
    "loading_overlay": '.artdeco-loader',

    # Modals
    "modal_container": '[role="dialog"]',
    "modal_close": 'button[aria-label="Dismiss"]',

    # Toasts/Alerts
    "toast": '.artdeco-toast-item',
    "alert": '[role="alert"]',

    # Pagination
    "load_more": 'button:has-text("Load more")',
    "show_more_results": 'button:has-text("Show more results")',
}


# =============================================================================
# Helper Functions
# =============================================================================

def get_selector(category: str, name: str) -> str:
    """
    Get a selector by category and name.

    Args:
        category: One of 'auth', 'nav', 'post', 'engagement', 'comment',
                  'profile', 'compose', 'messaging', 'search', 'utility'
        name: The selector name within that category

    Returns:
        The CSS selector string
    """
    categories = {
        'auth': AUTH_SELECTORS,
        'nav': NAV_SELECTORS,
        'post': POST_SELECTORS,
        'engagement': ENGAGEMENT_SELECTORS,
        'comment': COMMENT_SELECTORS,
        'profile': PROFILE_SELECTORS,
        'compose': COMPOSE_SELECTORS,
        'messaging': MESSAGING_SELECTORS,
        'search': SEARCH_SELECTORS,
        'utility': UTILITY_SELECTORS,
    }

    if category not in categories:
        raise ValueError(f"Unknown category: {category}")

    if name not in categories[category]:
        raise ValueError(f"Unknown selector '{name}' in category '{category}'")

    return categories[category][name]


def get_all_selectors() -> dict:
    """Return all selectors as a flat dictionary."""
    all_selectors = {}
    all_selectors.update(AUTH_SELECTORS)
    all_selectors.update(NAV_SELECTORS)
    all_selectors.update(POST_SELECTORS)
    all_selectors.update(ENGAGEMENT_SELECTORS)
    all_selectors.update(COMMENT_SELECTORS)
    all_selectors.update(PROFILE_SELECTORS)
    all_selectors.update(COMPOSE_SELECTORS)
    all_selectors.update(MESSAGING_SELECTORS)
    all_selectors.update(SEARCH_SELECTORS)
    all_selectors.update(UTILITY_SELECTORS)
    return all_selectors
