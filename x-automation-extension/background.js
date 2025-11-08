// Background service worker - manages WebSocket connection to your backend

let ws = null;
let userId = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Connect to your backend
function connectToBackend() {
  // Get user ID from storage
  chrome.storage.local.get(['userId'], (result) => {
    if (result.userId) {
      userId = result.userId;
      initWebSocket();
    } else {
      // Auto-generate a user ID for now (in production, this comes from dashboard)
      userId = 'user_' + Math.random().toString(36).substr(2, 9);
      chrome.storage.local.set({ userId }, () => {
        console.log('Generated user ID:', userId);
        initWebSocket();
      });
    }
  });
}

function initWebSocket() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.log('WebSocket already connected');
    return;
  }

  // Backend WebSocket URL
  const wsUrl = `ws://localhost:8001/ws/extension/${userId}`;
  
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

// Listen for messages from popup or content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CONNECT_WITH_USER_ID') {
    // Dashboard sent user ID - save and connect
    userId = message.userId;
    chrome.storage.local.set({ userId }, () => {
      initWebSocket();
      sendResponse({ success: true });
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

