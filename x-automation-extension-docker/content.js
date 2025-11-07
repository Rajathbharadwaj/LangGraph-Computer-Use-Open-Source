// Content script - runs on x.com pages, performs actual automation

console.log('🚀 X Automation Extension loaded on', window.location.href);

// Check if user is logged into X
function checkLoginStatus() {
  // Look for profile button (only visible when logged in)
  const profileButton = document.querySelector('[data-testid="SideNav_AccountSwitcher_Button"]');
  
  if (profileButton) {
    // Extract username
    const profileLink = document.querySelector('a[href^="/"][aria-label*="Profile"]');
    const username = profileLink ? profileLink.getAttribute('href').replace('/', '') : 'unknown';
    
    return {
      loggedIn: true,
      username: username
    };
  }
  
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

// Create a new post
async function createPost(postText) {
  try {
    console.log('📝 Creating post:', postText);
    
    // Navigate to home if not already there
    if (!window.location.href.includes('x.com/home')) {
      window.location.href = 'https://x.com/home';
      await new Promise(resolve => setTimeout(resolve, 2000));
    }
    
    // Find the "What's happening?" compose box
    // X has multiple textareas, we want the main one at the top
    const composeBox = document.querySelector('[data-testid="tweetTextarea_0"]');
    
    if (!composeBox) {
      return { success: false, error: 'Compose box not found. Make sure you are on the home timeline.' };
    }
    
    // Click to focus (in case it's not already focused)
    composeBox.click();
    await new Promise(resolve => setTimeout(resolve, 300));
    
    // Type the post text
    composeBox.focus();
    composeBox.textContent = postText;
    
    // Trigger input event to enable the Post button
    const inputEvent = new Event('input', { bubbles: true });
    composeBox.dispatchEvent(inputEvent);
    
    // Wait a bit for X's UI to process
    await new Promise(resolve => setTimeout(resolve, 800));
    
    // Find and click the "Post" button
    // The main post button has data-testid="tweetButtonInline" or "tweetButton"
    let postButton = document.querySelector('[data-testid="tweetButtonInline"]');
    if (!postButton) {
      postButton = document.querySelector('[data-testid="tweetButton"]');
    }
    
    if (!postButton) {
      return { success: false, error: 'Post button not found. Text may be too long or empty.' };
    }
    
    // Check if button is disabled
    if (postButton.disabled || postButton.getAttribute('aria-disabled') === 'true') {
      return { success: false, error: 'Post button is disabled. Check text length (max 280 chars).' };
    }
    
    // Click the Post button
    postButton.click();
    
    console.log('✅ Post button clicked!');
    
    // Wait for post to be published
    await new Promise(resolve => setTimeout(resolve, 2000));
    
    // Verify post was published by checking if compose box is cleared
    const verifyBox = document.querySelector('[data-testid="tweetTextarea_0"]');
    const isCleared = !verifyBox || verifyBox.textContent.trim() === '';
    
    if (isCleared) {
      return { 
        success: true, 
        message: 'Post created successfully!',
        postText: postText,
        timestamp: new Date().toISOString()
      };
    } else {
      return { 
        success: false, 
        error: 'Post may not have been published. Compose box still has content.',
        warning: 'Check VNC viewer to verify'
      };
    }
    
  } catch (error) {
    console.error('❌ Error creating post:', error);
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
  
  if (message.action === 'CREATE_POST') {
    createPost(message.postText).then(result => {
      sendResponse(result);
    });
    return true;
  }
  
  // Unknown action
  sendResponse({ success: false, error: 'Unknown action' });
  return true;
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

