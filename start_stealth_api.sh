#!/bin/bash
# Startup script for stealth API service (without VNC streaming)
# This runs the stealth_cua_server API for browser automation

echo "🥷 Starting STEALTH API Service"
echo "================================"

# Start X server (needed for browser)
echo "📺 Starting Xvfb..."
Xvfb :98 -screen 0 1280x720x24 -ac +extension RANDR +extension GLX -dpi 96 &
sleep 3

# Start XFCE session (needed for browser window management)
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

# Initialize Playwright browsers (required for stealth)
echo "🎭 Initializing Playwright browsers..."
python3 -m playwright install chromium 2>/dev/null || echo "Playwright browsers already installed"
sleep 2

# Start Stealth API server on PORT (Cloud Run default is 8080)
echo "🥷 Starting Stealth CUA Server on port ${PORT:-8080}..."
cd /app
uvicorn stealth_cua_server:app --host 0.0.0.0 --port ${PORT:-8080} &

# Wait for server to start
sleep 8

# Initialize browser with extension
echo "🎭 Initializing Playwright browser with extension..."
curl -X POST http://localhost:${PORT:-8080}/initialize 2>/dev/null
sleep 3

echo "✅ Stealth API Service started!"
echo "================================"
echo "🔌 API Server: http://localhost:${PORT:-8080}"
echo "🥷 Stealth Mode: ENABLED"
echo "================================"

# Keep container running
tail -f /dev/null
