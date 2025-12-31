// Content script - runs on x.com pages, performs actual automation

console.log('🚀 X Automation Extension loaded on', window.location.href);

// Check if we're on the dashboard page and send Clerk user ID to background script
(function checkForClerkUserId() {
  const currentUrl = window.location.href;

  // Check if we're on the dashboard domain
  if (currentUrl.includes('app.paralleluniverse.ai') || currentUrl.includes('localhost:3000')) {
    console.log('📍 On dashboard page, checking for Clerk user ID...');

    // Try to read the Clerk user ID from meta tag
    const metaTag = document.querySelector('meta[name="clerk-user-id"]');

    if (metaTag && metaTag.content) {
      const clerkUserId = metaTag.content;
      console.log('✅ Found Clerk user ID in meta tag:', clerkUserId);

      // Send to background script
      chrome.runtime.sendMessage({
        type: 'CONNECT_WITH_USER_ID',
        userId: clerkUserId
      }, (response) => {
        if (chrome.runtime.lastError) {
          console.error('❌ Failed to send Clerk user ID:', chrome.runtime.lastError);
        } else {
          console.log('✅ Successfully sent Clerk user ID to background script');
        }
      });
    } else {
      console.log('⚠️ Clerk user ID meta tag not found yet, will retry...');

      // Meta tag might not be added yet, retry after a short delay
      setTimeout(checkForClerkUserId, 1000);
    }
  }
})();

// Check if user is logged into X
function checkLoginStatus() {
  // Multiple methods to detect login status

  // Method 1: Look for profile button (account switcher)
  const profileButton = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');

  // Method 2: Look for compose box (only visible when logged in)
  const composeBox = document.querySelector('[data-testid="tweetTextarea_0"]') ||
                     document.querySelector('[data-testid="tweetTextarea_0_label"]') ||
                     document.querySelector('[aria-label="Post text"]');

  // Method 3: Look for "What's happening?" placeholder
  const whatHappeningText = document.querySelector('[data-testid="primaryColumn"]')?.innerText?.includes("What's happening");

  // Method 4: Look for the home timeline feed
  const homeFeed = document.querySelector('[data-testid="primaryColumn"] [aria-label*="Timeline"]');

  const isLoggedIn = !!(profileButton || composeBox || whatHappeningText || homeFeed);

  if (isLoggedIn) {
    // Extract username - multiple methods
    let username = 'unknown';

    // Method 1: From profile link in sidebar
    const profileLink = document.querySelector('a[href^="/"][aria-label*="Profile"]');
    if (profileLink) {
      username = profileLink.getAttribute('href').replace('/', '');
    }

    // Method 2: From account switcher button
    if (username === 'unknown' && profileButton) {
      const buttonText = profileButton.innerText || '';
      const handleMatch = buttonText.match(/@([a-zA-Z0-9_]+)/);
      if (handleMatch) {
        username = handleMatch[1];
      }
    }

    // Method 3: From any visible @handle in the sidebar
    if (username === 'unknown') {
      const sidebarHandles = document.querySelectorAll('nav [dir="ltr"] span');
      for (const span of sidebarHandles) {
        const text = span.innerText || '';
        if (text.startsWith('@')) {
          username = text.substring(1);
          break;
        }
      }
    }

    console.log('✅ Login detected, username:', username);
    return {
      loggedIn: true,
      username: username
    };
  }

  console.log('❌ Not logged in');
  return {
    loggedIn: false,
    username: null
  };
}

// Extract DOM elements (for your LangGraph agent)
function extractDOMElements() {
  const elements = [];
  
  // Get all interactive elements
  const selectors = [
    'button',
    'a',
    'input',
    '[role="button"]',
    '[data-testid="like"]',
    '[data-testid="retweet"]',
    '[data-testid="reply"]'
  ];
  
  document.querySelectorAll(selectors.join(',')).forEach((el, index) => {
    const rect = el.getBoundingClientRect();
    
    elements.push({
      index,
      tagName: el.tagName.toLowerCase(),
      text: el.textContent?.trim().substring(0, 100) || '',
      testId: el.getAttribute('data-testid') || '',
      ariaLabel: el.getAttribute('aria-label') || '',
      x: Math.round(rect.x + rect.width / 2),
      y: Math.round(rect.y + rect.height / 2),
      visible: rect.width > 0 && rect.height > 0
    });
  });
  
  return elements.filter(el => el.visible);
}

// Like a post
async function likePost(postUrl) {
  try {
    // If not on the post page, navigate to it
    if (window.location.href !== postUrl) {
      window.location.href = postUrl;
      // Wait for navigation
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    // Find like button
    const likeButton = document.querySelector('[data-testid="like"]');
    
    if (!likeButton) {
      return { success: false, error: 'Like button not found' };
    }
    
    // Check if already liked
    const isLiked = likeButton.getAttribute('data-testid') === 'unlike';
    
    if (isLiked) {
      return { success: true, message: 'Post already liked' };
    }
    
    // Click like button
    likeButton.click();
    
    return { success: true, message: 'Post liked successfully' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Follow a user
async function followUser(username) {
  try {
    // Navigate to user profile
    const profileUrl = `https://x.com/${username}`;
    if (window.location.href !== profileUrl) {
      window.location.href = profileUrl;
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    // Find follow button
    const followButton = document.querySelector('[data-testid*="follow"]');
    
    if (!followButton) {
      return { success: false, error: 'Follow button not found' };
    }
    
    // Check if already following
    if (followButton.textContent.includes('Following')) {
      return { success: true, message: 'Already following user' };
    }
    
    // Click follow button
    followButton.click();
    
    return { success: true, message: 'User followed successfully' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Comment on a post
async function commentOnPost(postUrl, commentText) {
  try {
    // Navigate to post
    if (window.location.href !== postUrl) {
      window.location.href = postUrl;
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    // Find reply button
    const replyButton = document.querySelector('[data-testid="reply"]');
    if (!replyButton) {
      return { success: false, error: 'Reply button not found' };
    }
    
    // Click reply button
    replyButton.click();
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Find text input
    const textInput = document.querySelector('[data-testid="tweetTextarea_0"]');
    if (!textInput) {
      return { success: false, error: 'Text input not found' };
    }
    
    // Type comment
    textInput.focus();
    textInput.textContent = commentText;
    
    // Trigger input event
    const inputEvent = new Event('input', { bubbles: true });
    textInput.dispatchEvent(inputEvent);
    
    await new Promise(resolve => setTimeout(resolve, 500));
    
    // Find and click post button
    const postButton = document.querySelector('[data-testid="tweetButton"]');
    if (!postButton) {
      return { success: false, error: 'Post button not found' };
    }
    
    postButton.click();
    
    return { success: true, message: 'Comment posted successfully' };
  } catch (error) {
    return { success: false, error: error.message };
  }
}

// Listen for commands from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  console.log('📨 Content script received:', message);
  
  // Handle different actions
  if (message.action === 'CHECK_LOGIN') {
    const status = checkLoginStatus();
    sendResponse(status);
    return true;
  }
  
  if (message.action === 'GET_DOM') {
    const elements = extractDOMElements();
    sendResponse({ success: true, elements });
    return true;
  }
  
  if (message.action === 'LIKE_POST') {
    likePost(message.postUrl).then(result => {
      sendResponse(result);
    });
    return true; // Keep channel open for async response
  }
  
  if (message.action === 'FOLLOW_USER') {
    followUser(message.username).then(result => {
      sendResponse(result);
    });
    return true;
  }
  
  if (message.action === 'COMMENT_ON_POST') {
    commentOnPost(message.postUrl, message.commentText).then(result => {
      sendResponse(result);
    });
    return true;
  }

  // Don't respond to unknown actions - let other listeners handle them
  return false;
});

// Notify background script that content script is ready
chrome.runtime.sendMessage({ 
  type: 'CONTENT_SCRIPT_READY',
  url: window.location.href
});

// Auto-check login status on page load
setTimeout(() => {
  const status = checkLoginStatus();
  chrome.runtime.sendMessage({
    type: 'LOGIN_STATUS_UPDATE',
    ...status
  });
}, 2000);

