#!/bin/bash

# 📊 Check Status of All X Growth Automation Services

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
PURPLE='\033[0;35m'
NC='\033[0m'

echo -e "${CYAN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║                                                            ║${NC}"
echo -e "${CYAN}║         📊 X GROWTH AUTOMATION SYSTEM STATUS 📊            ║${NC}"
echo -e "${CYAN}║                                                            ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Function to check port
check_service() {
    local port=$1
    local name=$2
    local url=$3
    
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "   ${GREEN}✅ $name${NC} - Port $port ${GREEN}RUNNING${NC}"
        if [ ! -z "$url" ]; then
            echo -e "      ${CYAN}→ $url${NC}"
        fi
        return 0
    else
        echo -e "   ${RED}❌ $name${NC} - Port $port ${RED}NOT RUNNING${NC}"
        return 1
    fi
}

echo -e "${PURPLE}🔍 Checking Services:${NC}"
echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

SERVICES_OK=0
SERVICES_TOTAL=6

check_service 3001 "Frontend Dashboard" "http://localhost:3001" && ((SERVICES_OK++))
check_service 8000 "Main Backend" "http://localhost:8000" && ((SERVICES_OK++))
check_service 8001 "Extension Backend" "http://localhost:8001" && ((SERVICES_OK++))
check_service 8123 "LangGraph Server" "http://localhost:8123" && ((SERVICES_OK++))
check_service 8005 "Docker Browser API" "http://localhost:8005" && ((SERVICES_OK++))
check_service 3000 "Docker VNC" "http://localhost:3000" && ((SERVICES_OK++))

echo ""
echo -e "${PURPLE}🐳 Docker Container:${NC}"
echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if docker ps | grep -q stealth-browser; then
    echo -e "   ${GREEN}✅ stealth-browser${NC} - ${GREEN}RUNNING${NC}"
    CONTAINER_ID=$(docker ps -q -f name=stealth-browser)
    echo -e "      ${CYAN}Container ID: $CONTAINER_ID${NC}"
else
    echo -e "   ${RED}❌ stealth-browser${NC} - ${RED}NOT RUNNING${NC}"
fi

echo ""
echo -e "${PURPLE}📊 Summary:${NC}"
echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"

if [ $SERVICES_OK -eq $SERVICES_TOTAL ]; then
    echo -e "   ${GREEN}✅ All services operational ($SERVICES_OK/$SERVICES_TOTAL)${NC}"
    echo ""
    echo -e "${GREEN}🎯 System is ready to use!${NC}"
else
    echo -e "   ${YELLOW}⚠️  Some services not running ($SERVICES_OK/$SERVICES_TOTAL)${NC}"
    echo ""
    echo -e "${YELLOW}💡 To start all services, run:${NC}"
    echo -e "   ${CYAN}./START_EVERYTHING.sh${NC}"
fi

echo ""
echo -e "${PURPLE}📋 Quick Actions:${NC}"
echo -e "${PURPLE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "   View logs:      ${CYAN}ls -lht ~/cua/logs/ | head${NC}"
echo -e "   Stop all:       ${CYAN}./STOP_EVERYTHING.sh${NC}"
echo -e "   Restart:        ${CYAN}./STOP_EVERYTHING.sh && ./START_EVERYTHING.sh${NC}"
echo ""

