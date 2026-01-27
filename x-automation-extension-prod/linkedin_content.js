// LinkedIn Content Script - Detects login status and captures profile info

console.log('🔗 LinkedIn content script loaded');

// Check if user is logged into LinkedIn
function checkLinkedInLoginStatus() {
  // LinkedIn shows feed content only when logged in
  const feedContainer = document.querySelector('.scaffold-finite-scroll__content');
  const profileMenu = document.querySelector('[data-control-name="nav.settings"]');
  const navProfileLink = document.querySelector('a[href*="/in/"]');

  // Try to get username from profile link
  let username = null;
  if (navProfileLink) {
    const href = navProfileLink.getAttribute('href');
    if (href) {
      const match = href.match(/\/in\/([^/?]+)/);
      if (match) {
        username = match[1];
      }
    }
  }

  // Also check the nav bar for profile photo link
  if (!username) {
    const profilePhotoLink = document.querySelector('img.global-nav__me-photo');
    if (profilePhotoLink) {
      const container = profilePhotoLink.closest('a');
      if (container) {
        const href = container.getAttribute('href');
        if (href) {
          const match = href.match(/\/in\/([^/?]+)/);
          if (match) {
            username = match[1];
          }
        }
      }
    }
  }

  // Check for authenticated elements
  const isLoggedIn = !!(feedContainer || profileMenu || navProfileLink);

  return {
    loggedIn: isLoggedIn,
    username: username,
    platform: 'linkedin'
  };
}

// Extract profile info if on a profile page
function extractProfileInfo() {
  const profileName = document.querySelector('.text-heading-xlarge');
  const profileHeadline = document.querySelector('.text-body-medium.break-words');
  const profileLocation = document.querySelector('.text-body-small.inline.t-black--light');
  const profileImage = document.querySelector('.pv-top-card-profile-picture__image');

  return {
    name: profileName?.textContent?.trim() || null,
    headline: profileHeadline?.textContent?.trim() || null,
    location: profileLocation?.textContent?.trim() || null,
    imageUrl: profileImage?.src || null,
  };
}

// Send login status to background script
function notifyLoginStatus() {
  const status = checkLinkedInLoginStatus();

  if (status.loggedIn) {
    console.log('✅ LinkedIn login detected:', status.username || 'username not found');

    chrome.runtime.sendMessage({
      type: 'LINKEDIN_LOGIN_STATUS',
      loggedIn: true,
      username: status.username,
      platform: 'linkedin'
    });
  }
}

// Listen for messages from background script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === 'CHECK_LINKEDIN_LOGIN') {
    const status = checkLinkedInLoginStatus();
    sendResponse(status);
    return true;
  }

  if (message.action === 'GET_LINKEDIN_PROFILE') {
    const profile = extractProfileInfo();
    sendResponse(profile);
    return true;
  }
});

// Initial login check after page loads
setTimeout(() => {
  notifyLoginStatus();
}, 2000);

// Also check on navigation (LinkedIn is a SPA)
let lastUrl = location.href;
new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(notifyLoginStatus, 1000);
  }
}).observe(document.body, { childList: true, subtree: true });

// Notify background that content script is ready
chrome.runtime.sendMessage({
  type: 'LINKEDIN_CONTENT_SCRIPT_READY',
  url: window.location.href
});
