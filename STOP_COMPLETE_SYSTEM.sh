#!/bin/bash

echo "================================================================================"
echo "🛑 STOPPING COMPLETE X GROWTH AGENT SYSTEM"
echo "================================================================================"
echo ""

GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# Read PIDs from files
if [ -f /home/rajathdb/cua/.pids/extension_backend.pid ]; then
    EXTENSION_BACKEND_PID=$(cat /home/rajathdb/cua/.pids/extension_backend.pid)
fi

if [ -f /home/rajathdb/cua/.pids/main_backend.pid ]; then
    MAIN_BACKEND_PID=$(cat /home/rajathdb/cua/.pids/main_backend.pid)
fi

if [ -f /home/rajathdb/cua/.pids/frontend.pid ]; then
    FRONTEND_PID=$(cat /home/rajathdb/cua/.pids/frontend.pid)
fi

if [ -f /home/rajathdb/cua/.pids/container_name.txt ]; then
    CONTAINER_NAME=$(cat /home/rajathdb/cua/.pids/container_name.txt)
fi

# Stop Extension Backend
echo "📡 Stopping Extension Backend..."
if [ ! -z "$EXTENSION_BACKEND_PID" ]; then
    kill $EXTENSION_BACKEND_PID 2>/dev/null
fi
lsof -ti:8001 | xargs kill -9 2>/dev/null
echo "${GREEN}✅ Extension backend stopped${NC}"

# Stop Main Backend
echo "🔧 Stopping Main Backend..."
if [ ! -z "$MAIN_BACKEND_PID" ]; then
    kill $MAIN_BACKEND_PID 2>/dev/null
fi
lsof -ti:8000 | xargs kill -9 2>/dev/null
echo "${GREEN}✅ Main backend stopped${NC}"

# Stop Frontend
echo "🎨 Stopping Frontend..."
if [ ! -z "$FRONTEND_PID" ]; then
    kill $FRONTEND_PID 2>/dev/null
fi
lsof -ti:3000 | xargs kill -9 2>/dev/null
echo "${GREEN}✅ Frontend stopped${NC}"

# Stop Docker Container
echo "🐳 Stopping Docker Container..."
if [ ! -z "$CONTAINER_NAME" ]; then
    docker stop $CONTAINER_NAME 2>/dev/null
    docker rm $CONTAINER_NAME 2>/dev/null
fi
echo "${GREEN}✅ Docker container stopped${NC}"

# Clean up PID files
rm -rf /home/rajathdb/cua/.pids/*.pid
rm -rf /home/rajathdb/cua/.pids/*.txt

echo ""
echo "================================================================================"
echo "${GREEN}✅ ALL SERVICES STOPPED!${NC}"
echo "================================================================================"
echo ""
echo "To start again, run: ./START_COMPLETE_SYSTEM.sh"
echo ""

