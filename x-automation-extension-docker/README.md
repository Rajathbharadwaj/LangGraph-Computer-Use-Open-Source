STDIN
# X Automation Chrome Extension

This extension connects your X account to the automation dashboard.

## 🚀 How It Works

1. User installs this extension
2. Extension detects if user is logged into X
3. Extension connects to your backend via WebSocket
4. User controls everything from your Next.js dashboard
5. Extension performs actions on X automatically

## 📦 Installation (Development)

1. Open Chrome and go to `chrome://extensions/`
2. Enable "Developer mode" (top right)
3. Click "Load unpacked"
4. Select this folder (`x-automation-extension`)
5. Extension is now installed!

## 🔧 Files

- `manifest.json` - Extension configuration
- `background.js` - Background service worker (WebSocket connection)
- `content.js` - Runs on x.com pages (performs automation)
- `popup.html` - Extension popup UI
- `popup.js` - Popup logic
- `icon*.png` - Extension icons

## 🔌 Backend Integration

The extension connects to your backend at:
```
ws://localhost:8000/ws/extension/{userId}
```

Update this URL in `background.js` line 25.

## 📡 Message Protocol

### From Backend → Extension:
```json
{
  "action": "LIKE_POST",
  "postUrl": "https://x.com/username/status/123"
}
```

### From Extension → Backend:
```json
{
  "success": true,
  "message": "Post liked successfully"
}
```

## 🎯 Supported Actions

- `CHECK_LOGIN` - Check if user is logged into X
- `GET_DOM` - Extract DOM elements for LangGraph agent
- `LIKE_POST` - Like a post
- `FOLLOW_USER` - Follow a user
- `COMMENT_ON_POST` - Comment on a post

## 🔐 Security

- Extension only runs on x.com and twitter.com
- WebSocket connection requires user ID
- All actions require user to be logged into X
- No passwords or credentials stored

## 📝 Next Steps

1. Create icons (icon16.png, icon48.png, icon128.png)
2. Update WebSocket URL in background.js
3. Build backend WebSocket endpoint
4. Update Next.js UI to detect extension
5. Test end-to-end flow

