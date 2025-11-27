#!/bin/bash

echo "================================================================================"
echo "🚀 STARTING INTEGRATED X GROWTH AGENT SYSTEM"
echo "================================================================================"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

echo "${GREEN}✅ Docker is running${NC}"
echo ""

# Step 1: Start Extension Backend Server
echo "${BLUE}📡 Step 1: Starting Extension Backend Server...${NC}"
cd /home/rajathdb/cua
python3 backend_extension_server.py &
BACKEND_PID=$!
echo "   Backend PID: $BACKEND_PID"
sleep 3

# Check if backend started
if ps -p $BACKEND_PID > /dev/null; then
    echo "${GREEN}   ✅ Extension backend running on http://localhost:8001${NC}"
else
    echo "   ❌ Failed to start extension backend"
    exit 1
fi
echo ""

# Step 2: Start Main Backend (Cookie injection, etc.)
echo "${BLUE}🔧 Step 2: Starting Main Backend Server...${NC}"
python3 backend_websocket_server.py &
MAIN_BACKEND_PID=$!
echo "   Main Backend PID: $MAIN_BACKEND_PID"
sleep 3

if ps -p $MAIN_BACKEND_PID > /dev/null; then
    echo "${GREEN}   ✅ Main backend running on http://localhost:8000${NC}"
else
    echo "   ❌ Failed to start main backend"
    kill $BACKEND_PID
    exit 1
fi
echo ""

# Step 3: Check if Docker container is running
echo "${BLUE}🐳 Step 3: Checking Docker Container...${NC}"
CONTAINER_NAME="stealth-cua"

if docker ps | grep -q $CONTAINER_NAME; then
    echo "${GREEN}   ✅ Docker container already running${NC}"
else
    echo "   Starting Docker container..."
    docker start $CONTAINER_NAME 2>/dev/null || \
    docker run -d \
        --name $CONTAINER_NAME \
        -p 5900:5900 \
        -p 8005:8005 \
        stealth-cua:latest
    
    sleep 5
    
    if docker ps | grep -q $CONTAINER_NAME; then
        echo "${GREEN}   ✅ Docker container started${NC}"
    else
        echo "   ❌ Failed to start Docker container"
        kill $BACKEND_PID $MAIN_BACKEND_PID
        exit 1
    fi
fi
echo ""

# Step 4: Start Frontend Dashboard
echo "${BLUE}🎨 Step 4: Starting Frontend Dashboard...${NC}"
cd /home/rajathdb/cua-frontend
npm run dev &
FRONTEND_PID=$!
echo "   Frontend PID: $FRONTEND_PID"
sleep 5

if ps -p $FRONTEND_PID > /dev/null; then
    echo "${GREEN}   ✅ Frontend running on http://localhost:3000${NC}"
else
    echo "   ❌ Failed to start frontend"
    kill $BACKEND_PID $MAIN_BACKEND_PID
    docker stop $CONTAINER_NAME
    exit 1
fi
echo ""

# Summary
echo "================================================================================"
echo "${GREEN}✅ ALL SYSTEMS RUNNING!${NC}"
echo "================================================================================"
echo ""
echo "📡 Extension Backend:  http://localhost:8001"
echo "🔧 Main Backend:       http://localhost:8000"
echo "🐳 Docker (Playwright): http://localhost:8005"
echo "🖥️  VNC Viewer:         vnc://localhost:5900"
echo "🎨 Dashboard:          http://localhost:3000"
echo ""
echo "================================================================================"
echo "${YELLOW}NEXT STEPS:${NC}"
echo "================================================================================"
echo ""
echo "1. Open Chrome and go to: chrome://extensions/"
echo "2. Reload the 'X Automation Helper' extension"
echo "3. Go to https://x.com/home"
echo "4. Extension will auto-connect to backend"
echo "5. Open dashboard: http://localhost:3000"
echo "6. Start using the agent!"
echo ""
echo "================================================================================"
echo "${YELLOW}TO STOP ALL SERVICES:${NC}"
echo "================================================================================"
echo ""
echo "kill $BACKEND_PID $MAIN_BACKEND_PID $FRONTEND_PID"
echo "docker stop $CONTAINER_NAME"
echo ""
echo "Or run: ./STOP_INTEGRATED_SYSTEM.sh"
echo ""
echo "================================================================================"
echo "${GREEN}🎉 SYSTEM READY!${NC}"
echo "================================================================================"

# Keep script running
wait

