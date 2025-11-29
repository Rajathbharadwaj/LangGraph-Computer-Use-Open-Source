// Popup script - shows extension status

document.addEventListener('DOMContentLoaded', () => {
  checkStatus();
  
  // Open dashboard button
  document.getElementById('openDashboard').addEventListener('click', () => {
    chrome.tabs.create({ url: 'http://localhost:3000' });
  });
  
  // Disconnect button
  document.getElementById('disconnect').addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'DISCONNECT' }, (response) => {
      if (response.success) {
        checkStatus();
      }
    });
  });
});

function checkStatus() {
  // Get connection status from background script
  chrome.runtime.sendMessage({ type: 'GET_CONNECTION_STATUS' }, (response) => {
    const statusDiv = document.getElementById('status');
    const disconnectBtn = document.getElementById('disconnect');
    
    if (response.connected) {
      // Connected
      statusDiv.className = 'status connected';
      statusDiv.innerHTML = `
        <div class="status-icon">✅</div>
        <div class="status-text">Connected to Dashboard</div>
        ${response.userId ? `<div class="username">User ID: ${response.userId}</div>` : ''}
      `;
      disconnectBtn.style.display = 'block';
    } else {
      // Not connected
      statusDiv.className = 'status disconnected';
      statusDiv.innerHTML = `
        <div class="status-icon">❌</div>
        <div class="status-text">Not Connected</div>
      `;
      disconnectBtn.style.display = 'none';
    }
  });
  
  // Check X login status and premium status
  chrome.tabs.query({ url: ['https://x.com/*', 'https://twitter.com/*'] }, (tabs) => {
    if (tabs.length > 0) {
      chrome.tabs.sendMessage(tabs[0].id, { action: 'CHECK_LOGIN' }, (response) => {
        if (response && response.loggedIn) {
          const statusDiv = document.getElementById('status');
          const currentHTML = statusDiv.innerHTML;
          statusDiv.innerHTML = currentHTML + `
            <div style="margin-top: 10px; font-size: 12px;">
              X Account: <strong>@${response.username}</strong>
            </div>
          `;

          // Check premium status
          checkPremiumStatus(tabs[0].id);
        }
      });
    }
  });
}

function checkPremiumStatus(tabId) {
  // Send message to content script to check premium status
  chrome.tabs.sendMessage(tabId, { action: 'CHECK_PREMIUM' }, (response) => {
    const premiumDiv = document.getElementById('premiumStatus');
    const premiumText = document.getElementById('premiumText');
    const charLimit = document.getElementById('charLimit');

    if (response && response.success) {
      const isPremium = response.is_premium;
      const limit = response.character_limit;
      const method = response.detection_method;

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
      premiumDiv.style.display = 'none';
    }
  });
}

// Listen for connection status updates
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'CONNECTION_STATUS') {
    checkStatus();
  }
});

