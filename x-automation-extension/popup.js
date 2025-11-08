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
  
  // Check X login status
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
        }
      });
    }
  });
}

// Listen for connection status updates
chrome.runtime.onMessage.addListener((message) => {
  if (message.type === 'CONNECTION_STATUS') {
    checkStatus();
  }
});

