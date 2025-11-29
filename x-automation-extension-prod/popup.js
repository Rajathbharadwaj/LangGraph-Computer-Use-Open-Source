// Popup script - shows extension status with modern UI

document.addEventListener('DOMContentLoaded', () => {
  checkStatus();

  // Open dashboard button
  document.getElementById('openDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: 'https://app.paralleluniverse.ai' });
  });

  // Refresh status button
  document.getElementById('refreshStatus').addEventListener('click', () => {
    updateStatusUI('connecting', 'Refreshing...', 'Checking connection');
    checkStatus();
  });

  // Disconnect button
  document.getElementById('disconnect').addEventListener('click', () => {
    if (confirm('Are you sure you want to disconnect your account?')) {
      chrome.runtime.sendMessage({ type: 'DISCONNECT' }, (response) => {
        if (response && response.success) {
          checkStatus();
        }
      });
    }
  });
});

function updateStatusUI(status, text, subtext) {
  const indicator = document.getElementById('statusIndicator');
  const statusText = document.getElementById('statusText');
  const statusSubtext = document.getElementById('statusSubtext');

  // Update indicator class
  indicator.className = 'status-indicator ' + status;

  // Update text
  statusText.textContent = text;
  statusSubtext.textContent = subtext;
}

function showAccountInfo(username, displayName) {
  const accountInfo = document.getElementById('accountInfo');
  const accountAvatar = document.getElementById('accountAvatar');
  const accountName = document.getElementById('accountName');
  const accountHandle = document.getElementById('accountHandle');
  const disconnectBtn = document.getElementById('disconnect');

  // Show account section
  accountInfo.classList.remove('hidden');
  disconnectBtn.classList.remove('hidden');

  // Set account details
  accountAvatar.textContent = (displayName || username || '?').charAt(0).toUpperCase();
  accountName.textContent = displayName || username || 'Connected User';
  accountHandle.textContent = username ? '@' + username : '@unknown';
}

function hideAccountInfo() {
  const accountInfo = document.getElementById('accountInfo');
  const disconnectBtn = document.getElementById('disconnect');

  accountInfo.classList.add('hidden');
  disconnectBtn.classList.add('hidden');
}

function checkStatus() {
  // Get connection status from background script
  chrome.runtime.sendMessage({ type: 'GET_CONNECTION_STATUS' }, (response) => {
    if (chrome.runtime.lastError) {
      updateStatusUI('disconnected', 'Extension Error', 'Could not connect to background service');
      hideAccountInfo();
      return;
    }

    if (response && response.connected) {
      // Connected to backend
      updateStatusUI('connected', 'Connected', 'Synced with dashboard');

      // Check for X login status
      checkXLoginStatus();
    } else {
      // Not connected
      updateStatusUI('disconnected', 'Disconnected', 'Unable to reach server');
      hideAccountInfo();
    }
  });
}

function checkXLoginStatus() {
  // Check X login status
  chrome.tabs.query({ url: ['https://x.com/*', 'https://twitter.com/*'] }, (tabs) => {
    if (tabs && tabs.length > 0) {
      // Wait a bit for content script to be ready
      setTimeout(() => {
        chrome.tabs.sendMessage(tabs[0].id, { action: 'CHECK_LOGIN' }, (response) => {
          if (chrome.runtime.lastError) {
            // Content script not ready
            updateStatusUI('connected', 'Connected', 'Open x.com to sync account');
            hideAccountInfo();
            return;
          }

          if (response && response.loggedIn) {
            console.log('🔵 User logged in, updating UI and checking premium');
            updateStatusUI('connected', 'Connected', 'Account synced');
            showAccountInfo(response.username, response.displayName);

            // Check premium status
            console.log('🔵 About to call checkPremiumStatus with tab:', tabs[0].id);
            checkPremiumStatus(tabs[0].id);
          } else {
            updateStatusUI('connected', 'Connected', 'Please log into X');
            hideAccountInfo();
          }
        });
      }, 100); // Give content script 100ms to load
    } else {
      // No X tabs open
      updateStatusUI('connected', 'Connected', 'Open x.com to sync account');
      hideAccountInfo();
    }
  });
}

function checkPremiumStatus(tabId) {
  console.log('💎 checkPremiumStatus called with tabId:', tabId);

  // Send message to content script to check premium status
  chrome.tabs.sendMessage(tabId, { action: 'CHECK_PREMIUM' }, (response) => {
    console.log('💎 Received response from content script:', response);
    console.log('💎 Response details - success:', response?.success, 'is_premium:', response?.is_premium, 'limit:', response?.character_limit);
    if (response?.error) {
      console.log('❌ Error from content script:', response.error);
    }

    const premiumDiv = document.getElementById('premiumStatus');
    const premiumText = document.getElementById('premiumText');
    const charLimit = document.getElementById('charLimit');

    console.log('💎 Found elements:', { premiumDiv, premiumText, charLimit });

    // Check for errors
    if (chrome.runtime.lastError) {
      console.log('❌ Error sending message:', chrome.runtime.lastError.message);
      if (premiumDiv) premiumDiv.style.display = 'none';
      return;
    }

    if (response && response.success) {
      const isPremium = response.is_premium;
      const limit = response.character_limit;
      const method = response.detection_method;

      console.log('✅ Premium status received:', isPremium, limit, method);

      if (isPremium) {
        premiumDiv.className = 'premium-status premium';
        premiumDiv.querySelector('.premium-icon').textContent = '💎';
        premiumText.textContent = 'X Premium Account';
        charLimit.textContent = `Character limit: ${limit.toLocaleString()} chars`;
      } else {
        premiumDiv.className = 'premium-status standard';
        premiumDiv.querySelector('.premium-icon').textContent = '📝';
        premiumText.textContent = 'Standard X Account';
        charLimit.textContent = `Character limit: ${limit} chars`;
      }

      // Add detection method as tooltip
      premiumDiv.title = `Detected via: ${method}`;
    } else {
      // Could not detect - hide the status
      console.log('❌ No valid response from content script:', response);
      if (premiumDiv) premiumDiv.style.display = 'none';
    }
  });
}

// Listen for connection status updates
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'CONNECTION_STATUS') {
    checkStatus();
  }
});
