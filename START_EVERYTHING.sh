#!/bin/bash

# 🚀 Complete X Growth Automation System Startup Script
# This starts ALL components in the correct order

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Log file
LOG_DIR="$HOME/cua/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                            ║${NC}"
echo -e "${CYAN}║         🚀 X GROWTH AUTOMATION SYSTEM LAUNCHER 🚀          ║${NC}"
echo -e "${CYAN}║                                                            ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to check if port is in use
check_port() {
    local port=$1
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to wait for service
wait_for_service() {
    local port=$1
    local name=$2
    local max_wait=60
    local waited=0
    
    echo -e "${YELLOW}⏳ Waiting for $name on port $port...${NC}"
    while ! check_port $port; do
        sleep 1
        waited=$((waited + 1))
        if [ $waited -ge $max_wait ]; then
            echo -e "${RED}❌ Timeout waiting for $name${NC}"
            return 1
        fi
    done
    echo -e "${GREEN}✅ $name is ready!${NC}"
    return 0
}

# Function to cleanup on exit
cleanup() {
    echo -e "\n${YELLOW}🛑 Shutting down all services...${NC}"
    
    # Kill all background jobs
    jobs -p | xargs -r kill 2>/dev/null || true
    
    # Stop Docker container
    docker stop stealth-browser 2>/dev/null || true
    
    echo -e "${GREEN}✅ Cleanup complete${NC}"
    exit 0
}

trap cleanup EXIT INT TERM

# Step 1: Check if Docker is running
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}📦 Step 1/7: Checking Docker${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker is not running. Please start Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker is running${NC}"
echo ""

# Step 2: Stop any existing containers
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🧹 Step 2/7: Cleaning up existing containers${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

docker stop stealth-browser 2>/dev/null || true
docker rm stealth-browser 2>/dev/null || true
echo -e "${GREEN}✅ Cleanup complete${NC}"
echo ""

# Step 3: Start Docker Stealth Browser
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🌐 Step 3/7: Starting Docker Stealth Browser${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

echo -e "${YELLOW}   Building Docker image (if needed)...${NC}"
docker build -f Dockerfile.stealth.with_extension -t stealth-browser-with-extension . > "$LOG_DIR/docker_build_$TIMESTAMP.log" 2>&1 &
BUILD_PID=$!

# Show progress
while kill -0 $BUILD_PID 2>/dev/null; do
    echo -n "."
    sleep 2
done
wait $BUILD_PID
BUILD_EXIT=$?

if [ $BUILD_EXIT -ne 0 ]; then
    echo -e "\n${RED}❌ Docker build failed. Check $LOG_DIR/docker_build_$TIMESTAMP.log${NC}"
    exit 1
fi
echo -e "\n${GREEN}✅ Docker image built${NC}"

echo -e "${YELLOW}   Starting container...${NC}"
docker run -d \
    --name stealth-browser \
    --network host \
    -p 8005:8005 \
    -p 3000:3000 \
    stealth-browser-with-extension > "$LOG_DIR/docker_run_$TIMESTAMP.log" 2>&1

if ! wait_for_service 8005 "Docker Stealth Browser"; then
    echo -e "${RED}❌ Failed to start Docker browser${NC}"
    exit 1
fi
echo ""

# Step 4: Start Extension Backend (port 8001)
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🔌 Step 4/7: Starting Extension Backend (WebSocket)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if check_port 8001; then
    echo -e "${YELLOW}⚠️  Port 8001 already in use, killing existing process...${NC}"
    lsof -ti:8001 | xargs -r kill -9 2>/dev/null || true
    sleep 2
fi

cd /home/rajathdb/cua
python backend_extension_server.py > "$LOG_DIR/extension_backend_$TIMESTAMP.log" 2>&1 &
EXTENSION_PID=$!
echo -e "${YELLOW}   PID: $EXTENSION_PID${NC}"

if ! wait_for_service 8001 "Extension Backend"; then
    echo -e "${RED}❌ Failed to start Extension Backend${NC}"
    exit 1
fi
echo ""

# Step 5: Start Main Backend (port 8000)
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🖥️  Step 5/7: Starting Main Backend (WebSocket + API)${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if check_port 8000; then
    echo -e "${YELLOW}⚠️  Port 8000 already in use, killing existing process...${NC}"
    lsof -ti:8000 | xargs -r kill -9 2>/dev/null || true
    sleep 2
fi

python backend_websocket_server.py > "$LOG_DIR/main_backend_$TIMESTAMP.log" 2>&1 &
BACKEND_PID=$!
echo -e "${YELLOW}   PID: $BACKEND_PID${NC}"

if ! wait_for_service 8000 "Main Backend"; then
    echo -e "${RED}❌ Failed to start Main Backend${NC}"
    exit 1
fi
echo ""

# Step 6: Start LangGraph Server (port 8123)
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🤖 Step 6/7: Starting LangGraph Deep Agent Server${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if check_port 8123; then
    echo -e "${YELLOW}⚠️  Port 8123 already in use, killing existing process...${NC}"
    lsof -ti:8123 | xargs -r kill -9 2>/dev/null || true
    sleep 2
fi

# Check if langgraph.json exists
if [ ! -f "langgraph.json" ]; then
    echo -e "${RED}❌ langgraph.json not found${NC}"
    exit 1
fi

langgraph dev --port 8123 > "$LOG_DIR/langgraph_$TIMESTAMP.log" 2>&1 &
LANGGRAPH_PID=$!
echo -e "${YELLOW}   PID: $LANGGRAPH_PID${NC}"

if ! wait_for_service 8123 "LangGraph Server"; then
    echo -e "${RED}❌ Failed to start LangGraph Server${NC}"
    echo -e "${YELLOW}📋 Check logs: $LOG_DIR/langgraph_$TIMESTAMP.log${NC}"
    exit 1
fi
echo ""

# Step 7: Start Frontend Dashboard (port 3001)
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}🎨 Step 7/7: Starting Frontend Dashboard${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if check_port 3001; then
    echo -e "${YELLOW}⚠️  Port 3001 already in use, killing existing process...${NC}"
    lsof -ti:3001 | xargs -r kill -9 2>/dev/null || true
    sleep 2
fi

cd /home/rajathdb/cua/cua-frontend
npm run dev > "$LOG_DIR/frontend_$TIMESTAMP.log" 2>&1 &
FRONTEND_PID=$!
echo -e "${YELLOW}   PID: $FRONTEND_PID${NC}"

if ! wait_for_service 3001 "Frontend Dashboard"; then
    echo -e "${RED}❌ Failed to start Frontend Dashboard${NC}"
    exit 1
fi
echo ""

# All services started!
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}║              ✅ ALL SYSTEMS OPERATIONAL! ✅                 ║${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${CYAN}📍 Service URLs:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "   ${PURPLE}🎨 Dashboard:${NC}           http://localhost:3001"
echo -e "   ${PURPLE}🌐 Docker VNC:${NC}          http://localhost:3000"
echo -e "   ${PURPLE}🖥️  Main Backend:${NC}       http://localhost:8000"
echo -e "   ${PURPLE}🔌 Extension Backend:${NC}   http://localhost:8001"
echo -e "   ${PURPLE}🤖 LangGraph API:${NC}       http://localhost:8123"
echo -e "   ${PURPLE}🌐 Docker Browser API:${NC}  http://localhost:8005"
echo ""

echo -e "${CYAN}📊 Process IDs:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "   Extension Backend:  ${EXTENSION_PID}"
echo -e "   Main Backend:       ${BACKEND_PID}"
echo -e "   LangGraph Server:   ${LANGGRAPH_PID}"
echo -e "   Frontend:           ${FRONTEND_PID}"
echo -e "   Docker Container:   $(docker ps -q -f name=stealth-browser)"
echo ""

echo -e "${CYAN}📋 Log Files:${NC}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "   Location: $LOG_DIR/"
echo -e "   Timestamp: $TIMESTAMP"
echo ""

echo -e "${YELLOW}💡 Quick Commands:${NC}"
echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "   View logs:          tail -f $LOG_DIR/*_$TIMESTAMP.log"
echo -e "   Stop all:           Press Ctrl+C"
echo -e "   Check status:       ps aux | grep -E 'backend|langgraph|npm'"
echo ""

echo -e "${GREEN}🎯 Next Steps:${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "   1. Open Dashboard:     ${CYAN}http://localhost:3001${NC}"
echo -e "   2. Load Chrome Extension (host browser)"
echo -e "   3. Log into X.com with extension"
echo -e "   4. Import your posts from Dashboard"
echo -e "   5. Start the X Growth Agent!"
echo ""

echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${PURPLE}         Press Ctrl+C to stop all services${NC}"
echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# Keep script running and monitor services
while true; do
    # Check if any service died
    if ! kill -0 $EXTENSION_PID 2>/dev/null; then
        echo -e "${RED}❌ Extension Backend died! Check logs.${NC}"
        exit 1
    fi
    
    if ! kill -0 $BACKEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Main Backend died! Check logs.${NC}"
        exit 1
    fi
    
    if ! kill -0 $LANGGRAPH_PID 2>/dev/null; then
        echo -e "${RED}❌ LangGraph Server died! Check logs.${NC}"
        exit 1
    fi
    
    if ! kill -0 $FRONTEND_PID 2>/dev/null; then
        echo -e "${RED}❌ Frontend died! Check logs.${NC}"
        exit 1
    fi
    
    if ! docker ps | grep -q stealth-browser; then
        echo -e "${RED}❌ Docker container died! Check logs.${NC}"
        exit 1
    fi
    
    sleep 5
done
