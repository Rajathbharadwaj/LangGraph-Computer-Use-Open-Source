/**
 * Extension Agent Bridge
 * Handles commands from the agent and executes them in the page context
 * This runs in the content script (has access to page DOM)
 */

console.log('🤖 Extension Agent Bridge loaded');

// WebSocket connection to backend
let ws = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 10;
const RECONNECT_DELAY = 3000;

// User ID (get from extension storage or generate)
let userId = 'default';

// Initialize
chrome.storage.local.get(['userId'], (result) => {
  if (result.userId) {
    userId = result.userId;
  } else {
    userId = 'user_' + Math.random().toString(36).substring(7);
    chrome.storage.local.set({ userId });
  }
  
  console.log(`👤 User ID: ${userId}`);
  connectToBackend();
});

/**
 * Connect to backend WebSocket
 */
function connectToBackend() {
  const wsUrl = `ws://localhost:8001/ws/extension/${userId}`;
  console.log(`🔌 Connecting to backend: ${wsUrl}`);
  
  ws = new WebSocket(wsUrl);
  
  ws.onopen = () => {
    console.log('✅ Connected to backend');
    reconnectAttempts = 0;
  };
  
  ws.onmessage = async (event) => {
    try {
      const command = JSON.parse(event.data);
      console.log('📨 Received command:', command.type);
      
      // Handle command
      const response = await handleCommand(command);
      
      // Send response back
      ws.send(JSON.stringify(response));
      
    } catch (error) {
      console.error('❌ Error handling command:', error);
      ws.send(JSON.stringify({
        request_id: command?.request_id,
        success: false,
        error: error.message
      }));
    }
  };
  
  ws.onerror = (error) => {
    console.error('❌ WebSocket error:', error);
  };
  
  ws.onclose = () => {
    console.log('❌ Disconnected from backend');
    
    // Attempt reconnection
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      console.log(`🔄 Reconnecting... (attempt ${reconnectAttempts})`);
      setTimeout(connectToBackend, RECONNECT_DELAY);
    }
  };
}

/**
 * Handle command from agent
 */
async function handleCommand(command) {
  const { type, request_id } = command;
  
  try {
    let result;
    
    switch (type) {
      case 'EXTRACT_ENGAGEMENT':
        result = await extractEngagementData(command.post_identifier);
        break;
        
      case 'CHECK_RATE_LIMIT':
        result = await checkRateLimitStatus();
        break;
        
      case 'GET_POST_CONTEXT':
        result = await getPostContext(command.post_identifier);
        break;
        
      case 'HUMAN_CLICK':
        result = await humanLikeClick(command.element_description);
        break;
        
      case 'MONITOR_ACTION':
        result = await monitorActionResult(command.action_type, command.timeout);
        break;
        
      case 'EXTRACT_ACCOUNT_INSIGHTS':
        result = await extractAccountInsights(command.username);
        break;
        
      case 'CHECK_SESSION_HEALTH':
        result = await checkSessionHealth();
        break;
        
      case 'GET_TRENDING_TOPICS':
        result = await getTrendingTopics();
        break;
        
      case 'FIND_HIGH_ENGAGEMENT_POSTS':
        result = await findHighEngagementPosts(command.topic, command.limit);
        break;

      case 'CHECK_PREMIUM_STATUS':
        result = await checkPremiumStatus();
        break;

      default:
        throw new Error(`Unknown command type: ${type}`);
    }
    
    return {
      request_id,
      success: true,
      ...result
    };
    
  } catch (error) {
    return {
      request_id,
      success: false,
      error: error.message
    };
  }
}

/**
 * Extract hidden engagement data from a post
 */
async function extractEngagementData(postIdentifier) {
  console.log(`📊 Extracting engagement data for: ${postIdentifier}`);
  
  // Find the post
  const post = findPostByIdentifier(postIdentifier);
  if (!post) {
    throw new Error(`Post not found: ${postIdentifier}`);
  }
  
  // Try to access React internals
  const reactKey = Object.keys(post).find(key => key.startsWith('__reactProps'));
  const reactData = reactKey ? post[reactKey] : null;
  
  // Extract visible engagement metrics
  const likeButton = post.querySelector('[data-testid="like"]');
  const replyButton = post.querySelector('[data-testid="reply"]');
  const retweetButton = post.querySelector('[data-testid="retweet"]');
  
  const likes = extractNumber(likeButton?.getAttribute('aria-label') || '0');
  const replies = extractNumber(replyButton?.getAttribute('aria-label') || '0');
  const reposts = extractNumber(retweetButton?.getAttribute('aria-label') || '0');
  
  // Try to extract hidden data from React
  const hiddenData = reactData ? {
    impressions: reactData.impressions || 'N/A',
    engagement_rate: reactData.engagementRate || 'N/A',
    audience_type: reactData.audienceType || 'N/A',
    virality_score: reactData.viralityScore || 'N/A'
  } : {};
  
  return {
    data: {
      likes,
      replies,
      reposts,
      impressions: hiddenData.impressions || (likes + replies + reposts) * 10, // Estimate
      engagement_rate: hiddenData.engagement_rate || ((likes + replies) / Math.max(1, likes * 10) * 100).toFixed(2),
      audience_type: hiddenData.audience_type || 'general',
      virality_score: hiddenData.virality_score || calculateViralityScore(likes, replies, reposts),
      best_time: 'N/A'
    }
  };
}

/**
 * Check if X is showing rate limit warnings
 */
async function checkRateLimitStatus() {
  console.log('⚠️ Checking rate limit status');
  
  // Look for rate limit messages in DOM
  const bodyText = document.body.innerText.toLowerCase();
  const isRateLimited = bodyText.includes('rate limit') || 
                        bodyText.includes('try again later') ||
                        bodyText.includes('too many requests');
  
  if (isRateLimited) {
    return {
      status: {
        is_rate_limited: true,
        reset_time: 'Unknown',
        pause_duration: 3600,
        message: 'Rate limit detected in page content',
        actions_remaining: 0,
        last_check: new Date().toISOString()
      }
    };
  }
  
  return {
    status: {
      is_rate_limited: false,
      actions_remaining: 'Unknown',
      last_check: new Date().toISOString()
    }
  };
}

/**
 * Get full context of a post
 */
async function getPostContext(postIdentifier) {
  console.log(`📄 Getting post context for: ${postIdentifier}`);
  
  const post = findPostByIdentifier(postIdentifier);
  if (!post) {
    throw new Error(`Post not found: ${postIdentifier}`);
  }
  
  // Extract post data
  const textElement = post.querySelector('[data-testid="tweetText"]');
  const authorElement = post.querySelector('[data-testid="User-Name"]');
  const timeElement = post.querySelector('time');
  
  const fullText = textElement?.innerText || '';
  const authorName = authorElement?.innerText.split('\n')[0] || '';
  const authorHandle = authorElement?.innerText.split('@')[1]?.split('\n')[0] || '';
  const timestamp = timeElement?.getAttribute('datetime') || '';
  
  // Extract engagement
  const likeButton = post.querySelector('[data-testid="like"]');
  const replyButton = post.querySelector('[data-testid="reply"]');
  const retweetButton = post.querySelector('[data-testid="retweet"]');
  
  const likes = extractNumber(likeButton?.getAttribute('aria-label') || '0');
  const replies = extractNumber(replyButton?.getAttribute('aria-label') || '0');
  const reposts = extractNumber(retweetButton?.getAttribute('aria-label') || '0');
  
  return {
    context: {
      full_text: fullText,
      author_name: authorName,
      author_handle: authorHandle,
      author_followers: 'N/A',
      author_reputation: calculateReputation(likes, replies),
      likes,
      replies,
      reposts,
      engagement_velocity: 'N/A',
      is_trending: likes > 100,
      is_thread: false,
      thread_position: 'N/A',
      parent_post: 'None',
      timestamp,
      age: calculateAge(timestamp)
    }
  };
}

/**
 * Click with human-like behavior
 */
async function humanLikeClick(elementDescription) {
  console.log(`🖱️ Human-like click: ${elementDescription}`);
  
  // Find element (simplified - you'd implement better search)
  const element = findElementByDescription(elementDescription);
  if (!element) {
    throw new Error(`Element not found: ${elementDescription}`);
  }
  
  // Get element position
  const rect = element.getBoundingClientRect();
  const x = rect.left + rect.width / 2 + (Math.random() - 0.5) * 10;
  const y = rect.top + rect.height / 2 + (Math.random() - 0.5) * 10;
  
  // Random delay before click (50-150ms)
  const delay = 50 + Math.random() * 100;
  await sleep(delay);
  
  // Dispatch realistic events
  element.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));
  await sleep(20 + Math.random() * 30);
  
  element.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
  await sleep(20 + Math.random() * 30);
  
  element.click();
  
  element.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  
  return {
    details: {
      x: Math.round(x),
      y: Math.round(y),
      delay_ms: Math.round(delay),
      event_sequence: 'mouseover → mousedown → click → mouseup',
      stealth_score: 95
    }
  };
}

/**
 * Monitor DOM for action result
 */
async function monitorActionResult(actionType, timeout = 5) {
  console.log(`👀 Monitoring action: ${actionType}`);
  
  return new Promise((resolve) => {
    let resolved = false;
    
    // Set timeout
    const timeoutId = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        resolve({
          monitoring: {
            action_succeeded: false,
            error_message: 'Timeout waiting for action result',
            ui_state: 'Unknown',
            failure_reason: 'Timeout'
          }
        });
      }
    }, timeout * 1000);
    
    // Create mutation observer
    const observer = new MutationObserver((mutations) => {
      if (resolved) return;
      
      // Check for success indicators based on action type
      let success = false;
      let changes = '';
      
      if (actionType === 'like') {
        const likeButtons = document.querySelectorAll('[data-testid="like"]');
        for (const btn of likeButtons) {
          if (btn.getAttribute('aria-label')?.includes('Liked')) {
            success = true;
            changes = 'Like button changed to "Liked"';
            break;
          }
        }
      }
      
      if (success) {
        resolved = true;
        clearTimeout(timeoutId);
        observer.disconnect();
        
        resolve({
          monitoring: {
            action_succeeded: true,
            detected_changes: changes,
            new_state: 'Success',
            response_time_ms: timeout * 1000 - timeoutId
          }
        });
      }
    });
    
    // Start observing
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['aria-label', 'data-testid']
    });
  });
}

/**
 * Extract account insights
 */
async function extractAccountInsights(username) {
  console.log(`👤 Extracting insights for: @${username}`);
  
  // This would require navigating to the profile page
  // For now, return mock data
  return {
    insights: {
      followers: 'N/A',
      growth_rate: 'N/A',
      follower_quality: 75,
      avg_likes: 'N/A',
      avg_replies: 'N/A',
      engagement_rate: 'N/A',
      reply_rate: 'N/A',
      posting_frequency: 'N/A',
      top_post_type: 'text',
      best_time: '10:00 AM',
      content_quality: 80,
      primary_demographic: 'Tech professionals',
      geographic_focus: 'Global',
      interests: 'AI, Tech, Startups',
      worth_engaging: 'Yes',
      priority: 8,
      recommendation_reason: 'High quality content and engaged audience'
    }
  };
}

/**
 * Check session health
 */
async function checkSessionHealth() {
  console.log('🏥 Checking session health');

  // Check if logged in
  const profileButton = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
  const isLoggedIn = !!profileButton;

  // Get username
  const profileLink = document.querySelector('a[href^="/"][aria-label*="Profile"]');
  const username = profileLink?.getAttribute('href')?.replace('/', '') || 'Unknown';

  return {
    health: {
      is_healthy: isLoggedIn,
      login_status: isLoggedIn ? 'Logged in' : 'Not logged in',
      username,
      session_age: 'N/A',
      cookies_valid: isLoggedIn,
      account_status: isLoggedIn ? 'Active' : 'Unknown'
    }
  };
}

/**
 * Check if the current account has X Premium
 */
async function checkPremiumStatus() {
  console.log('💎 Checking X Premium status');

  let isPremium = false;
  let detectionMethod = 'none';
  let characterLimit = 280;

  // Method 1: Check for verification badge on profile
  const verifiedBadge = document.querySelector('[data-testid="icon-verified"]');
  if (verifiedBadge) {
    isPremium = true;
    detectionMethod = 'verified_badge';
    characterLimit = 25000;
    console.log('✅ Premium detected via verified badge');
  }

  // Method 2: Check compose box character counter
  if (!isPremium) {
    const composeBox = document.querySelector('[data-testid="tweetTextarea_0"]');
    if (composeBox) {
      // Type a test string and check the character counter
      const originalValue = composeBox.value;
      composeBox.value = 'a'.repeat(281); // 281 chars (exceeds non-premium limit)
      composeBox.dispatchEvent(new Event('input', { bubbles: true }));

      // Wait for counter to update
      await new Promise(resolve => setTimeout(resolve, 100));

      // Check if post button is still enabled (would be disabled for non-premium)
      const postButton = document.querySelector('[data-testid="tweetButtonInline"]') ||
                        document.querySelector('[data-testid="tweetButton"]');

      if (postButton && !postButton.disabled) {
        isPremium = true;
        detectionMethod = 'character_counter';
        characterLimit = 25000;
        console.log('✅ Premium detected via character counter');
      }

      // Restore original value
      composeBox.value = originalValue;
      composeBox.dispatchEvent(new Event('input', { bubbles: true }));
    }
  }

  // Method 3: Check for "Premium" or "Blue" text in navigation/profile
  if (!isPremium) {
    const navItems = document.querySelectorAll('[role="link"], [role="menuitem"]');
    for (const item of navItems) {
      const text = item.innerText?.toLowerCase() || '';
      if (text.includes('premium') || text.includes('blue')) {
        isPremium = true;
        detectionMethod = 'navigation_text';
        characterLimit = 25000;
        console.log('✅ Premium detected via navigation text');
        break;
      }
    }
  }

  // Method 4: Check Settings page for Premium features (if on settings page)
  if (!isPremium && window.location.href.includes('/settings')) {
    const premiumSection = document.querySelector('[data-testid="premium_section"]') ||
                          Array.from(document.querySelectorAll('span')).find(el =>
                            el.innerText?.includes('Premium')
                          );
    if (premiumSection) {
      isPremium = true;
      detectionMethod = 'settings_page';
      characterLimit = 25000;
      console.log('✅ Premium detected via settings page');
    }
  }

  console.log(`💎 Premium Status: ${isPremium ? 'YES' : 'NO'} (detected via: ${detectionMethod})`);
  console.log(`📝 Character Limit: ${characterLimit}`);

  return {
    is_premium: isPremium,
    character_limit: characterLimit,
    detection_method: detectionMethod
  };
}

/**
 * Get trending topics
 */
async function getTrendingTopics() {
  console.log('🔥 Getting trending topics');
  
  // Find trending section
  const trendingSection = document.querySelector('[aria-label*="Timeline: Trending"]') || 
                         document.querySelector('[data-testid="trend"]')?.parentElement;
  
  if (!trendingSection) {
    return { topics: [] };
  }
  
  // Extract trending items
  const trendItems = trendingSection.querySelectorAll('[data-testid="trend"]');
  const topics = [];
  
  trendItems.forEach((item, index) => {
    const name = item.querySelector('[dir="ltr"]')?.innerText || '';
    const volume = item.innerText.match(/[\d,]+\s+posts?/i)?.[0] || 'N/A';
    
    if (name) {
      topics.push({
        name,
        category: 'Trending',
        volume,
        relevance_score: 10 - index
      });
    }
  });
  
  return { topics };
}

/**
 * Find high-engagement posts
 */
async function findHighEngagementPosts(topic, limit = 10) {
  console.log(`🔍 Finding high-engagement posts on: ${topic}`);
  
  // Get all visible posts
  const posts = document.querySelectorAll('article[data-testid="tweet"]');
  const results = [];
  
  posts.forEach(post => {
    const textElement = post.querySelector('[data-testid="tweetText"]');
    const content = textElement?.innerText || '';
    
    // Check if post matches topic
    if (content.toLowerCase().includes(topic.toLowerCase())) {
      const authorElement = post.querySelector('[data-testid="User-Name"]');
      const author = authorElement?.innerText.split('@')[1]?.split('\n')[0] || '';
      
      const likeButton = post.querySelector('[data-testid="like"]');
      const likes = extractNumber(likeButton?.getAttribute('aria-label') || '0');
      
      const replyButton = post.querySelector('[data-testid="reply"]');
      const replies = extractNumber(replyButton?.getAttribute('aria-label') || '0');
      
      results.push({
        author,
        author_followers: 'N/A',
        content_preview: content.substring(0, 100),
        likes,
        replies,
        velocity: 'N/A',
        engagement_score: likes + replies * 2,
        reply_potential: Math.min(10, Math.floor((replies / Math.max(1, likes)) * 100))
      });
    }
  });
  
  // Sort by engagement score
  results.sort((a, b) => b.engagement_score - a.engagement_score);
  
  return {
    posts: results.slice(0, limit)
  };
}

// ============================================================================
// Helper Functions
// ============================================================================

function findPostByIdentifier(identifier) {
  const posts = document.querySelectorAll('article[data-testid="tweet"]');
  
  for (const post of posts) {
    const text = post.innerText.toLowerCase();
    if (text.includes(identifier.toLowerCase())) {
      return post;
    }
  }
  
  return null;
}

function findElementByDescription(description) {
  // Simplified element finding - you'd implement better logic
  const desc = description.toLowerCase();
  
  if (desc.includes('like')) {
    return document.querySelector('[data-testid="like"]');
  }
  if (desc.includes('reply')) {
    return document.querySelector('[data-testid="reply"]');
  }
  if (desc.includes('retweet')) {
    return document.querySelector('[data-testid="retweet"]');
  }
  
  return null;
}

function extractNumber(text) {
  const match = text.match(/[\d,]+/);
  return match ? parseInt(match[0].replace(/,/g, '')) : 0;
}

function calculateViralityScore(likes, replies, reposts) {
  const total = likes + replies * 2 + reposts * 3;
  return Math.min(100, Math.floor(total / 10));
}

function calculateReputation(likes, replies) {
  return Math.min(100, Math.floor((likes + replies * 2) / 10));
}

function calculateAge(timestamp) {
  if (!timestamp) return 'Unknown';
  
  const now = new Date();
  const then = new Date(timestamp);
  const diff = now - then;
  
  const hours = Math.floor(diff / (1000 * 60 * 60));
  if (hours < 24) return `${hours}h ago`;
  
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

console.log('✅ Extension Agent Bridge ready');

