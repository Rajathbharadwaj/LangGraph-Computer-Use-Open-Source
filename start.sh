#!/bin/bash
set -e

echo "🚀 Starting CUA Docker Container"
echo "================================="

# Start X server
echo "📺 Starting Xvfb..."
Xvfb :98 -screen 0 1280x720x24 -ac +extension RANDR +extension GLX -dpi 96 &
sleep 3

# Start VNC server
echo "🔌 Starting VNC server..."
x11vnc -display :98 -forever -nopw -listen 0.0.0.0 -rfbport 5900 -shared &
sleep 3

# Start XFCE session
echo "🖥️ Starting XFCE..."
xfce4-session &
sleep 5

# Start window manager
echo "🪟 Starting window manager..."
xfwm4 --daemon &
sleep 2

# Start desktop
echo "🗂️ Starting desktop..."
xfdesktop &
sleep 2

# Start Firefox
echo "🦊 Starting Firefox..."
firefox --remote-debugging-port=9222 --remote-allow-hosts=localhost --remote-allow-origins=* --no-sandbox --disable-dev-shm-usage &
sleep 5

# Start API server
echo "🔌 Starting API server..."
cd /app
python3 cua_server.py &

echo "✅ All services started!"
echo "📺 VNC: vnc://localhost:5900"
echo "🔌 API: http://localhost:8001"
echo "🦊 Firefox should be visible in VNC"

# Keep container running
tail -f /dev/null
