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
      chrome.tabs.sendMessage(tabs[0].id, { action: 'CHECK_LOGIN' }, (response) => {
        if (chrome.runtime.lastError) {
          // Content script not ready
          updateStatusUI('connected', 'Connected', 'Open x.com to sync account');
          hideAccountInfo();
          return;
        }

        if (response && response.loggedIn) {
          updateStatusUI('connected', 'Connected', 'Account synced');
          showAccountInfo(response.username, response.displayName);
        } else {
          updateStatusUI('connected', 'Connected', 'Please log into X');
          hideAccountInfo();
        }
      });
    } else {
      // No X tabs open
      updateStatusUI('connected', 'Connected', 'Open x.com to sync account');
      hideAccountInfo();
    }
  });
}

// Listen for connection status updates
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'CONNECTION_STATUS') {
    checkStatus();
  }
});
