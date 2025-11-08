#!/bin/bash

# 🛑 Stop All X Growth Automation Services

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                            ║${NC}"
echo -e "${CYAN}║         🛑 STOPPING X GROWTH AUTOMATION SYSTEM 🛑          ║${NC}"
echo -e "${CYAN}║                                                            ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Stop Docker container
echo -e "${YELLOW}🐳 Stopping Docker container...${NC}"
docker stop stealth-browser 2>/dev/null && echo -e "${GREEN}✅ Docker stopped${NC}" || echo -e "${YELLOW}⚠️  No Docker container running${NC}"
docker rm stealth-browser 2>/dev/null

# Kill processes on specific ports
echo -e "${YELLOW}🔌 Stopping Extension Backend (8001)...${NC}"
lsof -ti:8001 | xargs -r kill -9 2>/dev/null && echo -e "${GREEN}✅ Stopped${NC}" || echo -e "${YELLOW}⚠️  Not running${NC}"

echo -e "${YELLOW}🖥️  Stopping Main Backend (8000)...${NC}"
lsof -ti:8000 | xargs -r kill -9 2>/dev/null && echo -e "${GREEN}✅ Stopped${NC}" || echo -e "${YELLOW}⚠️  Not running${NC}"

echo -e "${YELLOW}🤖 Stopping LangGraph Server (8123)...${NC}"
lsof -ti:8123 | xargs -r kill -9 2>/dev/null && echo -e "${GREEN}✅ Stopped${NC}" || echo -e "${YELLOW}⚠️  Not running${NC}"

echo -e "${YELLOW}🎨 Stopping Frontend (3001)...${NC}"
lsof -ti:3001 | xargs -r kill -9 2>/dev/null && echo -e "${GREEN}✅ Stopped${NC}" || echo -e "${YELLOW}⚠️  Not running${NC}"

echo -e "${YELLOW}🌐 Stopping Docker Browser API (8005)...${NC}"
lsof -ti:8005 | xargs -r kill -9 2>/dev/null && echo -e "${GREEN}✅ Stopped${NC}" || echo -e "${YELLOW}⚠️  Not running${NC}"

echo -e "${YELLOW}🌐 Stopping VNC (3000)...${NC}"
lsof -ti:3000 | xargs -r kill -9 2>/dev/null && echo -e "${GREEN}✅ Stopped${NC}" || echo -e "${YELLOW}⚠️  Not running${NC}"

# Kill any remaining Python/Node processes related to the project
echo -e "${YELLOW}🧹 Cleaning up remaining processes...${NC}"
pkill -f "backend_extension_server.py" 2>/dev/null
pkill -f "backend_websocket_server.py" 2>/dev/null
pkill -f "langgraph dev" 2>/dev/null
pkill -f "npm run dev" 2>/dev/null

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}║              ✅ ALL SERVICES STOPPED! ✅                    ║${NC}"
echo -e "${GREEN}║                                                            ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${CYAN}💡 To start again, run:${NC}"
echo -e "   ${YELLOW}./START_EVERYTHING.sh${NC}"
echo ""
