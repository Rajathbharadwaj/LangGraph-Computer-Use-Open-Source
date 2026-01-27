// Background service worker - manages WebSocket connection to your backend

let ws = null;
let userId = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Connect to your backend - only if we have a valid Clerk user ID
function connectToBackend() {
  chrome.storage.local.get(['userId'], (result) => {
    if (result.userId && result.userId.startsWith('user_') && result.userId.length > 20) {
      // We have a valid Clerk user ID (they're long like user_35sAy5DRwouHPOUOk3okhywCGXN)
      userId = result.userId;
      console.log('✅ Found stored Clerk user ID:', userId);
      initWebSocket();
    } else {
      // No valid Clerk user ID - wait for dashboard to send it
      // Don't auto-generate a random ID anymore
      console.log('⏳ Waiting for Clerk user ID from dashboard...');
      console.log('💡 User needs to open app.paralleluniverse.ai to connect');
    }
  });
}

function initWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.log('WebSocket already connected');
    return;
  }

  // Backend WebSocket URL - Production
  const wsUrl = `wss://extension-backend-service-644185288504.us-central1.run.app/ws/extension/${userId}`;
  
  console.log('Connecting to backend:', wsUrl);
  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log('✅ Connected to backend!');
    reconnectAttempts = 0;
    
    // Notify popup and content script
    chrome.runtime.sendMessage({ 
      type: 'CONNECTION_STATUS', 
      connected: true 
    }).catch(() => {
      // Popup might not be open, that's okay
    });
    
    // Send initial status (but don't crash if no X tab is open)
    checkXLoginStatus().catch(err => {
      console.log('Could not check X login status:', err);
    });
  };

  ws.onmessage = async (event) => {
    const message = JSON.parse(event.data);
    console.log('📨 Received from backend:', message);

    // Handle backend messages (not for content script)
    if (message.type === 'CONNECTED') {
      console.log('✅ Backend acknowledged connection');
      return;
    }
    
    if (message.type === 'ACK') {
      console.log('✅ Backend acknowledged message');
      return;
    }
    
    if (message.type === 'COOKIES_RECEIVED') {
      console.log('✅ Backend received cookies:', message.message);
      return;
    }

    // Only forward automation commands to content script
    if (message.action) {
      const [tab] = await chrome.tabs.query({ 
        url: ['https://x.com/*', 'https://twitter.com/*'] 
      });

      if (tab) {
        chrome.tabs.sendMessage(tab.id, message, (response) => {
          // Send response back to backend
          if (response) {
            ws.send(JSON.stringify(response));
          }
        });
      } else {
        // No X tab open - send error
        ws.send(JSON.stringify({
          success: false,
          error: 'No X tab open'
        }));
      }
    }
  };

  ws.onclose = () => {
    console.log('❌ Disconnected from backend');
    chrome.runtime.sendMessage({ 
      type: 'CONNECTION_STATUS', 
      connected: false 
    });

    // Attempt to reconnect
    if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
      reconnectAttempts++;
      console.log(`Reconnecting... (attempt ${reconnectAttempts})`);
      setTimeout(initWebSocket, 3000);
    }
  };

  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
}

// Check if user is logged into X
async function checkXLoginStatus() {
  try {
    const tabs = await chrome.tabs.query({ 
      url: ['https://x.com/*', 'https://twitter.com/*'] 
    });

    if (tabs.length > 0 && tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: 'CHECK_LOGIN' }, async (response) => {
        // Check for chrome runtime errors
        if (chrome.runtime.lastError) {
          console.log('Content script not ready:', chrome.runtime.lastError.message);
          return;
        }
        
        if (response && response.loggedIn) {
          // User is logged in! Capture cookies and send to backend
          console.log('✅ User logged into X as @' + response.username);
          await captureCookiesAndSend(response.username);
          
          // Also send login status via WebSocket
          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'LOGIN_STATUS',
              loggedIn: true,
              username: response.username
            }));
          }
        }
      });
    } else {
      console.log('No X tabs open - user needs to visit x.com');
    }
  } catch (error) {
    console.log('Error checking X login status:', error);
  }
}

// Capture X cookies and send to backend
async function captureCookiesAndSend(username) {
  try {
    // Get all cookies for X domains
    const xCookies = await chrome.cookies.getAll({
      domain: '.x.com'
    });

    const twitterCookies = await chrome.cookies.getAll({
      domain: '.twitter.com'
    });

    const allCookies = [...xCookies, ...twitterCookies];

    console.log(`🍪 Captured ${allCookies.length} X cookies for @${username}`);

    // Send cookies to backend via WebSocket
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'COOKIES_CAPTURED',
        userId: userId,
        username: username,
        cookies: allCookies,
        timestamp: Date.now()
      }));
      console.log('📤 Sent cookies to backend');
    }
  } catch (error) {
    console.error('❌ Error capturing cookies:', error);
  }
}

// Check if user is logged into LinkedIn
async function checkLinkedInLoginStatus() {
  try {
    const tabs = await chrome.tabs.query({
      url: ['https://www.linkedin.com/*', 'https://linkedin.com/*']
    });

    if (tabs.length > 0 && tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, { action: 'CHECK_LINKEDIN_LOGIN' }, async (response) => {
        if (chrome.runtime.lastError) {
          console.log('LinkedIn content script not ready:', chrome.runtime.lastError.message);
          return;
        }

        if (response && response.loggedIn) {
          console.log('✅ User logged into LinkedIn as:', response.username || 'unknown');
          await captureLinkedInCookiesAndSend(response.username);

          if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
              type: 'LINKEDIN_LOGIN_STATUS',
              loggedIn: true,
              username: response.username,
              platform: 'linkedin'
            }));
          }
        }
      });
    } else {
      console.log('No LinkedIn tabs open');
    }
  } catch (error) {
    console.log('Error checking LinkedIn login status:', error);
  }
}

// Capture LinkedIn cookies and send to backend
async function captureLinkedInCookiesAndSend(username) {
  try {
    const linkedinCookies = await chrome.cookies.getAll({
      domain: '.linkedin.com'
    });

    console.log(`🍪 Captured ${linkedinCookies.length} LinkedIn cookies for ${username || 'user'}`);

    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'LINKEDIN_COOKIES_CAPTURED',
        userId: userId,
        username: username,
        cookies: linkedinCookies,
        platform: 'linkedin',
        timestamp: Date.now()
      }));
      console.log('📤 Sent LinkedIn cookies to backend');
    }
  } catch (error) {
    console.error('❌ Error capturing LinkedIn cookies:', error);
  }
}

// Listen for messages from popup or content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CONNECT_WITH_USER_ID') {
    // Dashboard sent user ID - save, connect, and immediately capture cookies
    const newUserId = message.userId;
    console.log('📥 Received Clerk user ID from dashboard:', newUserId);

    // Check if this is a new/different user ID
    const isNewUser = userId !== newUserId;
    userId = newUserId;

    chrome.storage.local.set({ userId }, async () => {
      // Connect to WebSocket with this user ID
      initWebSocket();

      // Immediately try to capture and send cookies
      // This makes the flow seamless - user just needs to be logged into X
      console.log('🔄 Auto-capturing cookies after receiving user ID...');
      setTimeout(async () => {
        await checkXLoginStatus();
      }, 500); // Small delay to let WebSocket connect first

      sendResponse({ success: true, userId: userId });
    });
    return true;
  }

  if (message.type === 'CAPTURE_COOKIES_NOW') {
    // Dashboard explicitly requesting cookie capture
    console.log('🔄 Dashboard requested cookie capture');
    checkXLoginStatus().then(() => {
      sendResponse({ success: true });
    }).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true;
  }

  if (message.type === 'GET_CONNECTION_STATUS') {
    sendResponse({ 
      connected: ws && ws.readyState === WebSocket.OPEN,
      userId: userId
    });
    return true;
  }

  if (message.type === 'DISCONNECT') {
    if (ws) {
      ws.close();
      ws = null;
    }
    userId = null;
    chrome.storage.local.remove(['userId']);
    sendResponse({ success: true });
    return true;
  }
  
  if (message.type === 'LOGIN_STATUS_UPDATE') {
    // Content script detected login status!
    console.log('📨 Login status update from content script:', message);
    
    if (message.loggedIn && message.username) {
      console.log('✅ User logged into X as @' + message.username);
      captureCookiesAndSend(message.username);
      
      // Also send to backend via WebSocket
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'LOGIN_STATUS',
          loggedIn: true,
          username: message.username
        }));
      }
    }
    return true;
  }
  
  if (message.type === 'CONTENT_SCRIPT_READY') {
    console.log('✅ Content script ready on:', message.url);
    return true;
  }

  // LinkedIn-specific messages
  if (message.type === 'LINKEDIN_LOGIN_STATUS') {
    console.log('📨 LinkedIn login status update:', message);

    if (message.loggedIn && message.username) {
      console.log('✅ User logged into LinkedIn as:', message.username);
      captureLinkedInCookiesAndSend(message.username);

      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
          type: 'LINKEDIN_LOGIN_STATUS',
          loggedIn: true,
          username: message.username,
          platform: 'linkedin'
        }));
      }
    }
    return true;
  }

  if (message.type === 'LINKEDIN_CONTENT_SCRIPT_READY') {
    console.log('✅ LinkedIn content script ready on:', message.url);
    // Auto-check login status when content script loads
    setTimeout(() => {
      checkLinkedInLoginStatus();
    }, 1000);
    return true;
  }

  if (message.type === 'CAPTURE_LINKEDIN_COOKIES_NOW') {
    console.log('🔄 Dashboard requested LinkedIn cookie capture');
    checkLinkedInLoginStatus().then(() => {
      sendResponse({ success: true });
    }).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true;
  }
});

// Start connection when extension loads
chrome.runtime.onInstalled.addListener(() => {
  console.log('X Automation Extension installed!');
  connectToBackend();
});

// Reconnect when browser starts
chrome.runtime.onStartup.addListener(() => {
  connectToBackend();
});

// Initial connection
connectToBackend();

