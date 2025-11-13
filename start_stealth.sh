#!/bin/bash
set -e

echo "🥷 Starting STEALTH CUA Docker Container"
echo "======================================="

# Start X server
echo "📺 Starting Xvfb..."
Xvfb :98 -screen 0 1280x720x24 -ac +extension RANDR +extension GLX -dpi 96 &
sleep 3

# Start VNC server (simple, working version with quality settings)
echo "🔌 Starting VNC server..."
x11vnc -display :98 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared -q -bg
sleep 3

# Start XFCE session
echo "🖥️ Starting XFCE..."
xfce4-session &
sleep 5

# Start window manager
echo "🪟 Starting window manager..."
xfwm4 &
sleep 2

# Start desktop
echo "🗂️ Starting desktop..."
xfdesktop &
sleep 2

# Note: Chrome/Firefox not started here - Playwright will handle browser with extension
echo "🎭 Browser will be started by Playwright with extension support..."

# Initialize Playwright browsers (required for stealth)
echo "🎭 Initializing Playwright browsers..."
python3 -m playwright install chromium 2>/dev/null || echo "Playwright browsers already installed"
sleep 2

# Start Stealth API server
echo "🥷 Starting Stealth CUA Server..."
cd /app
uvicorn stealth_cua_server:app --host 0.0.0.0 --port 8005 &

# Wait for server to start
sleep 8

# Initialize browser with extension
echo "🎭 Initializing Playwright browser with extension..."
curl -X POST http://localhost:8005/initialize 2>/dev/null
sleep 3

echo "✅ All services started!"
echo "======================================="
echo "📺 VNC Access: vnc://localhost:5900"
echo "🔌 API Server: http://localhost:8005"
echo "🥷 Stealth Mode: ENABLED"
echo "🦊 Traditional Firefox: Available"
echo "🎭 Playwright Stealth: Available"
echo "======================================="
echo ""
echo "🧪 Test the stealth server:"
echo "curl http://localhost:8005/status"
echo ""
echo "🔄 Toggle modes:"
echo "curl -X POST http://localhost:8005/mode -H 'Content-Type: application/json' -d '{\"stealth\": true}'"
echo ""

# Keep container running
tail -f /dev/null
