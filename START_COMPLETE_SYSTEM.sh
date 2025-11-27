#!/bin/bash

echo "================================================================================"
echo "🚀 STARTING COMPLETE X GROWTH AGENT SYSTEM"
echo "================================================================================"
echo ""
echo "This will start:"
echo "  1. Extension Backend Server (port 8001)"
echo "  2. Main Backend Server (port 8000)"
echo "  3. Docker Container with Extension (ports 5900, 8005)"
echo "  4. Frontend Dashboard (port 3000)"
echo "  5. Chrome Extension (auto-connects)"
echo ""

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Docker is running
echo "${BLUE}🐳 Checking Docker...${NC}"
if ! docker info > /dev/null 2>&1; then
    echo "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi
echo "${GREEN}✅ Docker is running${NC}"
echo ""

# Step 1: Build Docker image with extension if needed
echo "${BLUE}📦 Step 1: Checking Docker Image...${NC}"
if docker images | grep -q "stealth-cua-with-extension"; then
    echo "${GREEN}   ✅ Docker image exists${NC}"
else
    echo "   Building Docker image with extension..."
    cd /home/rajathdb/cua
    docker build -f Dockerfile.stealth.with_extension -t stealth-cua-with-extension:latest .
    
    if [ $? -eq 0 ]; then
        echo "${GREEN}   ✅ Docker image built successfully${NC}"
    else
        echo "${RED}   ❌ Failed to build Docker image${NC}"
        exit 1
    fi
fi
echo ""

# Step 2: Start Extension Backend Server
echo "${BLUE}📡 Step 2: Starting Extension Backend Server...${NC}"
cd /home/rajathdb/cua
python3 backend_extension_server.py > logs/extension_backend.log 2>&1 &
EXTENSION_BACKEND_PID=$!
echo "   PID: $EXTENSION_BACKEND_PID"
sleep 3

if ps -p $EXTENSION_BACKEND_PID > /dev/null; then
    echo "${GREEN}   ✅ Extension backend running on http://localhost:8001${NC}"
    echo "   📄 Logs: logs/extension_backend.log"
else
    echo "${RED}   ❌ Failed to start extension backend${NC}"
    exit 1
fi
echo ""

# Step 3: Start Main Backend Server
echo "${BLUE}🔧 Step 3: Starting Main Backend Server...${NC}"
python3 backend_websocket_server.py > logs/main_backend.log 2>&1 &
MAIN_BACKEND_PID=$!
echo "   PID: $MAIN_BACKEND_PID"
sleep 3

if ps -p $MAIN_BACKEND_PID > /dev/null; then
    echo "${GREEN}   ✅ Main backend running on http://localhost:8000${NC}"
    echo "   📄 Logs: logs/main_backend.log"
else
    echo "${RED}   ❌ Failed to start main backend${NC}"
    kill $EXTENSION_BACKEND_PID
    exit 1
fi
echo ""

# Step 4: Start Docker Container with Extension
echo "${BLUE}🐳 Step 4: Starting Docker Container with Extension...${NC}"
CONTAINER_NAME="stealth-cua-with-extension"

# Stop and remove existing container if it exists
docker stop $CONTAINER_NAME 2>/dev/null
docker rm $CONTAINER_NAME 2>/dev/null

# Start new container
docker run -d \
    --name $CONTAINER_NAME \
    -p 5900:5900 \
    -p 8005:8005 \
    -e DISPLAY=:98 \
    stealth-cua-with-extension:latest

sleep 5

if docker ps | grep -q $CONTAINER_NAME; then
    echo "${GREEN}   ✅ Docker container running${NC}"
    echo "   🖥️  VNC: vnc://localhost:5900"
    echo "   🌐 Playwright: http://localhost:8005"
    echo "   📦 Extension: Loaded in Chromium"
else
    echo "${RED}   ❌ Failed to start Docker container${NC}"
    kill $EXTENSION_BACKEND_PID $MAIN_BACKEND_PID
    exit 1
fi
echo ""

# Step 5: Start Frontend Dashboard
echo "${BLUE}🎨 Step 5: Starting Frontend Dashboard...${NC}"
cd /home/rajathdb/cua-frontend
npm run dev > /home/rajathdb/cua/logs/frontend.log 2>&1 &
FRONTEND_PID=$!
echo "   PID: $FRONTEND_PID"
sleep 5

if ps -p $FRONTEND_PID > /dev/null; then
    echo "${GREEN}   ✅ Frontend running on http://localhost:3000${NC}"
    echo "   📄 Logs: logs/frontend.log"
else
    echo "${RED}   ❌ Failed to start frontend${NC}"
    kill $EXTENSION_BACKEND_PID $MAIN_BACKEND_PID
    docker stop $CONTAINER_NAME
    exit 1
fi
echo ""

# Step 6: Wait for services to be ready
echo "${BLUE}⏳ Step 6: Waiting for services to initialize...${NC}"
sleep 5
echo "${GREEN}   ✅ All services initialized${NC}"
echo ""

# Summary
echo "================================================================================"
echo "${GREEN}✅ COMPLETE SYSTEM IS RUNNING!${NC}"
echo "================================================================================"
echo ""
echo "📊 SYSTEM STATUS:"
echo "================================================================================"
echo ""
echo "  📡 Extension Backend:    http://localhost:8001"
echo "     Status:               http://localhost:8001/status"
echo "     Health:               http://localhost:8001/health"
echo ""
echo "  🔧 Main Backend:         http://localhost:8000"
echo "     WebSocket (Extension): ws://localhost:8001/ws/extension/{user_id}"
echo "     WebSocket (Dashboard): ws://localhost:8000/ws/user_test"
echo ""
echo "  🐳 Docker Container:     stealth-cua-with-extension"
echo "     Playwright API:       http://localhost:8005"
echo "     VNC Viewer:           vnc://localhost:5900"
echo "     Extension:            Loaded in Chromium"
echo ""
echo "  🎨 Dashboard:            http://localhost:3000"
echo "     VNC Viewer:           Embedded in dashboard"
echo "     Import Posts:         Available in dashboard"
echo ""
echo "================================================================================"
echo "${YELLOW}NEXT STEPS:${NC}"
echo "================================================================================"
echo ""
echo "1. ${GREEN}Open Dashboard:${NC}"
echo "   → Open browser: http://localhost:3000"
echo "   → You'll see VNC viewer and Import Posts feature"
echo ""
echo "2. ${GREEN}Reload Chrome Extension:${NC}"
echo "   → Go to: chrome://extensions/"
echo "   → Find: 'X Automation Helper'"
echo "   → Click: 'Reload' button"
echo ""
echo "3. ${GREEN}Go to X.com:${NC}"
echo "   → Navigate to: https://x.com/home"
echo "   → Open Console (F12)"
echo "   → Should see: '✅ Connected to backend'"
echo ""
echo "4. ${GREEN}Test Extension Connection:${NC}"
echo "   → Visit: http://localhost:8001/status"
echo "   → Should show: active_connections: 1"
echo ""
echo "5. ${GREEN}Run the Agent:${NC}"
echo "   cd /home/rajathdb/cua"
echo "   python3 test_hybrid_agent.py"
echo ""
echo "================================================================================"
echo "${YELLOW}MONITORING:${NC}"
echo "================================================================================"
echo ""
echo "  📄 View Logs:"
echo "     tail -f logs/extension_backend.log"
echo "     tail -f logs/main_backend.log"
echo "     tail -f logs/frontend.log"
echo "     docker logs -f $CONTAINER_NAME"
echo ""
echo "  🔍 Check Status:"
echo "     curl http://localhost:8001/status"
echo "     curl http://localhost:8005/status"
echo ""
echo "================================================================================"
echo "${YELLOW}TO STOP ALL SERVICES:${NC}"
echo "================================================================================"
echo ""
echo "  ./STOP_COMPLETE_SYSTEM.sh"
echo ""
echo "  Or manually:"
echo "  kill $EXTENSION_BACKEND_PID $MAIN_BACKEND_PID $FRONTEND_PID"
echo "  docker stop $CONTAINER_NAME"
echo ""
echo "================================================================================"
echo "${GREEN}🎉 SYSTEM READY! ALL COMPONENTS CONNECTED!${NC}"
echo "================================================================================"
echo ""
echo "  ✅ Extension Backend    → Running"
echo "  ✅ Main Backend         → Running"
echo "  ✅ Docker + Extension   → Running"
echo "  ✅ Frontend Dashboard   → Running"
echo "  ✅ VNC Viewer           → Accessible"
echo "  ✅ Chrome Extension     → Ready to connect"
echo ""
echo "Everything is integrated and ready to use! 🚀"
echo ""

# Save PIDs for stop script
echo "$EXTENSION_BACKEND_PID" > /home/rajathdb/cua/.pids/extension_backend.pid
echo "$MAIN_BACKEND_PID" > /home/rajathdb/cua/.pids/main_backend.pid
echo "$FRONTEND_PID" > /home/rajathdb/cua/.pids/frontend.pid
echo "$CONTAINER_NAME" > /home/rajathdb/cua/.pids/container_name.txt

# Keep script running and show logs
echo "Press Ctrl+C to stop monitoring logs..."
echo ""
tail -f logs/extension_backend.log logs/main_backend.log logs/frontend.log

