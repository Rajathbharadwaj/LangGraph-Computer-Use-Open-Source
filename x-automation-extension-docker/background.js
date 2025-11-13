// Background service worker - manages WebSocket connection to your backend

console.log('🚀 [DOCKER EXTENSION] Background script loaded!');

let ws = null;
let userId = null;
let reconnectAttempts = 0;
const MAX_RECONNECT_ATTEMPTS = 5;

// Connect to your backend
function connectToBackend() {
  console.log('🔌 [DOCKER EXTENSION] connectToBackend() called');
  // Get user ID from storage
  chrome.storage.local.get(['userId'], (result) => {
    console.log('📦 [DOCKER EXTENSION] Storage result:', result);
    if (result.userId) {
      userId = result.userId;
      console.log('✅ [DOCKER EXTENSION] Using existing userId:', userId);
      initWebSocket();
    } else {
      // Auto-generate a user ID for now (in production, this comes from dashboard)
      userId = 'user_docker_' + Math.random().toString(36).substr(2, 9);
      console.log('🆕 [DOCKER EXTENSION] Generated new userId:', userId);
      chrome.storage.local.set({ userId }, () => {
        console.log('💾 [DOCKER EXTENSION] Saved userId to storage');
        initWebSocket();
      });
    }
  });
}

function initWebSocket() {
  console.log('🌐 [DOCKER EXTENSION] initWebSocket() called, userId:', userId);
  if (ws && ws.readyState === WebSocket.OPEN) {
    console.log('⚠️ [DOCKER EXTENSION] WebSocket already connected');
    return;
  }

  // Backend WebSocket URL
  // Use localhost since container runs in host network mode
  const wsUrl = `ws://localhost:8001/ws/extension/${userId}`;
  
  console.log('🔗 [DOCKER EXTENSION] Connecting to backend:', wsUrl);
  try {
    ws = new WebSocket(wsUrl);
    console.log('✅ [DOCKER EXTENSION] WebSocket object created');
  } catch (error) {
    console.error('❌ [DOCKER EXTENSION] Failed to create WebSocket:', error);
    return;
  }

  ws.onopen = () => {
    console.log('✅ [DOCKER EXTENSION] Connected to backend!');
    reconnectAttempts = 0;
    
    // Send keepalive ping every 20 seconds to keep service worker alive
    if (ws.pingInterval) clearInterval(ws.pingInterval);
    ws.pingInterval = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'PING' }));
        console.log('💓 [DOCKER EXTENSION] Sent keepalive ping');
      }
    }, 20000);
    
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
    console.log('📨 [DOCKER EXTENSION] Received from backend:', message);

    // Handle backend messages (not for content script)
    if (message.type === 'CONNECTED') {
      console.log('✅ [DOCKER EXTENSION] Backend acknowledged connection');
      return;
    }
    
    if (message.type === 'ACK') {
      console.log('✅ [DOCKER EXTENSION] Backend acknowledged message');
      return;
    }
    
    if (message.type === 'COOKIES_RECEIVED') {
      console.log('✅ [DOCKER EXTENSION] Backend received cookies:', message.message);
      return;
    }
    
    if (message.type === 'PING') {
      console.log('💓 [DOCKER EXTENSION] Received ping from backend');
      return;
    }

    // Forward automation commands to content script
    // Backend sends 'type', content script expects 'action'
    if (message.type && message.type !== 'CONNECTED' && message.type !== 'ACK' && message.type !== 'COOKIES_RECEIVED' && message.type !== 'PING') {
      console.log('🔀 [DOCKER EXTENSION] Forwarding command to content script:', message.type);
      
      const tabs = await chrome.tabs.query({ 
        url: ['https://x.com/*', 'https://twitter.com/*'] 
      });
      
      console.log('🔍 [DOCKER EXTENSION] Found X tabs:', tabs.length);
      
      if (tabs.length > 0) {
        const tab = tabs[0];
        console.log('📤 [DOCKER EXTENSION] Sending to tab:', tab.id, tab.url);
        
        // Convert 'type' to 'action' for content script
        const contentMessage = {
          ...message,
          action: message.type,
          postText: message.post_text,  // Map post_text to postText for content script
          postUrl: message.post_url,
          commentText: message.comment_text,
          username: message.username
        };
        
        console.log('📦 [DOCKER EXTENSION] Content message:', contentMessage);
        
        try {
          chrome.tabs.sendMessage(tab.id, contentMessage, (response) => {
            console.log('📬 [DOCKER EXTENSION] Got response from content script:', response);
            // Send response back to backend with request_id
            if (response) {
              response.request_id = message.request_id;
              ws.send(JSON.stringify(response));
              console.log('✅ [DOCKER EXTENSION] Sent response to backend');
            } else {
              console.error('❌ [DOCKER EXTENSION] No response from content script');
              ws.send(JSON.stringify({
                request_id: message.request_id,
                success: false,
                error: 'Content script did not respond'
              }));
            }
          });
        } catch (error) {
          console.error('❌ [DOCKER EXTENSION] Error sending message to tab:', error);
          ws.send(JSON.stringify({
            request_id: message.request_id,
            success: false,
            error: error.message
          }));
        }
      } else {
        // No X tab open - send error
        console.error('❌ [DOCKER EXTENSION] No X tabs found');
        ws.send(JSON.stringify({
          request_id: message.request_id,
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
    console.log('✅ [DOCKER EXTENSION] Content script ready on:', message.url);
    sendResponse({ success: true, message: 'Background script is alive!' });
    return true;
  }
});

// Start connection when extension loads
chrome.runtime.onInstalled.addListener(() => {
  console.log('🎉 [DOCKER EXTENSION] X Automation Extension installed!');
  connectToBackend();
  
  // Create alarm to keep service worker alive
  chrome.alarms.create('keepalive', { periodInMinutes: 0.5 });
});

// Reconnect when browser starts
chrome.runtime.onStartup.addListener(() => {
  console.log('🔄 [DOCKER EXTENSION] Browser startup detected');
  connectToBackend();
  
  // Create alarm to keep service worker alive
  chrome.alarms.create('keepalive', { periodInMinutes: 0.5 });
});

// Handle alarm to keep service worker alive
chrome.alarms.onAlarm.addListener((alarm) => {
  if (alarm.name === 'keepalive') {
    console.log('💓 [DOCKER EXTENSION] Keepalive alarm triggered');
    // Check if WebSocket is still connected
    if (!ws || ws.readyState !== WebSocket.OPEN) {
      console.log('⚠️ [DOCKER EXTENSION] WebSocket not connected, reconnecting...');
      connectToBackend();
    }
  }
});

// Initial connection
console.log('⚡ [DOCKER EXTENSION] Service worker starting, calling connectToBackend()...');

// Test if we can even make HTTP requests
fetch('http://localhost:8001/status')
  .then(res => res.json())
  .then(data => {
    console.log('✅ [DOCKER EXTENSION] HTTP test successful! Backend is reachable:', data);
    connectToBackend();
  })
  .catch(err => {
    console.error('❌ [DOCKER EXTENSION] HTTP test FAILED! Cannot reach backend:', err);
    console.error('❌ [DOCKER EXTENSION] This means network requests are blocked or backend is down');
    // Try anyway
    connectToBackend();
  });

