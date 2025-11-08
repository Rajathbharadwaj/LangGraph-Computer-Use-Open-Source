#!/bin/bash

# X Growth Automation - Quick Start Script
# This script helps you get started with the production-ready system

set -e

echo "╔════════════════════════════════════════════════════════════╗"
echo "║     🚀 X Growth Automation - Quick Start Setup 🚀         ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo ""

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Check if running in correct directory
if [ ! -f "Makefile" ]; then
    echo -e "${RED}❌ Error: Please run this script from the cua directory${NC}"
    exit 1
fi

echo -e "${CYAN}📋 Pre-flight Checks${NC}"
echo ""

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker not found. Please install Docker first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker installed${NC}"

# Check Docker Compose
if ! command -v docker-compose &> /dev/null; then
    echo -e "${RED}❌ Docker Compose not found. Please install Docker Compose first.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose installed${NC}"

# Check Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 not found. Please install Python 3.12+${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Python 3 installed${NC}"

# Check Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js not found. Please install Node.js 20+${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Node.js installed${NC}"

echo ""
echo -e "${CYAN}🔧 Setup Options${NC}"
echo ""
echo "1) Development Setup (Quick, local testing)"
echo "2) Production Setup (Full deployment)"
echo ""
read -p "Choose setup type (1 or 2): " setup_type

if [ "$setup_type" = "1" ]; then
    echo ""
    echo -e "${CYAN}🚀 Starting Development Setup...${NC}"
    echo ""
    
    # Check if .env exists
    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}⚠️  No .env file found. Creating from example...${NC}"
        cp .env.example .env
        echo -e "${GREEN}✅ Created .env file${NC}"
        echo -e "${YELLOW}💡 Please edit .env and add your API keys${NC}"
        echo ""
    fi
    
    # Check if frontend .env.local exists
    if [ ! -f "../cua-frontend/.env.local" ]; then
        echo -e "${YELLOW}⚠️  No frontend .env.local found. Creating from example...${NC}"
        cp ../cua-frontend/.env.local.example ../cua-frontend/.env.local 2>/dev/null || true
        echo -e "${GREEN}✅ Created frontend .env.local${NC}"
        echo -e "${YELLOW}💡 Please edit cua-frontend/.env.local and add Clerk keys${NC}"
        echo ""
    fi
    
    # Start development services
    echo -e "${CYAN}🐳 Starting development services...${NC}"
    make start
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║              ✅ Development Setup Complete! ✅             ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}📍 Service URLs:${NC}"
    echo "   🎨 Dashboard:         http://localhost:3000"
    echo "   🖥️  Backend API:      http://localhost:8000"
    echo "   🔌 Extension Backend: http://localhost:8001"
    echo "   🤖 LangGraph:         http://localhost:8124"
    echo "   🔍 OmniParser:        http://localhost:8003"
    echo ""
    echo -e "${YELLOW}📝 Next Steps:${NC}"
    echo "   1. Setup Clerk: Read CLERK_SETUP.md"
    echo "   2. Add API keys to .env"
    echo "   3. Install Chrome extension"
    echo "   4. Open http://localhost:3000"
    echo ""
    echo -e "${CYAN}💡 Useful Commands:${NC}"
    echo "   make status  - Check service status"
    echo "   make logs    - View logs"
    echo "   make stop    - Stop all services"
    echo ""

elif [ "$setup_type" = "2" ]; then
    echo ""
    echo -e "${CYAN}🚀 Starting Production Setup...${NC}"
    echo ""
    
    # Run production setup
    make prod-setup
    
    echo ""
    echo -e "${YELLOW}📝 Configuration Required:${NC}"
    echo ""
    echo "1. Edit .env file with your values:"
    echo "   - Database password"
    echo "   - Clerk secret key"
    echo "   - API keys (Anthropic, OpenAI)"
    echo "   - Encryption key (generated in .env.prod.key)"
    echo ""
    echo "2. Edit cua-frontend/.env.local:"
    echo "   - Clerk publishable key"
    echo "   - Clerk secret key"
    echo ""
    
    read -p "Have you configured all environment variables? (yes/no): " configured
    
    if [ "$configured" != "yes" ]; then
        echo ""
        echo -e "${YELLOW}⚠️  Please configure environment variables first${NC}"
        echo ""
        echo "Edit these files:"
        echo "   nano .env"
        echo "   nano ../cua-frontend/.env.local"
        echo ""
        echo "Then run: make prod-up"
        exit 0
    fi
    
    # Start production services
    echo ""
    echo -e "${CYAN}🐳 Starting production services...${NC}"
    make prod-up
    
    # Initialize database
    echo ""
    echo -e "${CYAN}🗄️  Initializing database...${NC}"
    sleep 5  # Wait for PostgreSQL to be ready
    make prod-db-init
    
    echo ""
    echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║             ✅ Production Setup Complete! ✅              ║${NC}"
    echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
    echo ""
    echo -e "${CYAN}📍 Production URLs:${NC}"
    echo "   🎨 Dashboard:    http://localhost:3000"
    echo "   🖥️  Backend API: http://localhost:8000"
    echo "   🤖 LangGraph:    http://localhost:8124"
    echo ""
    echo -e "${YELLOW}📝 Next Steps:${NC}"
    echo "   1. Setup domain and SSL certificate"
    echo "   2. Configure Nginx reverse proxy"
    echo "   3. Setup monitoring (Sentry)"
    echo "   4. Configure backups"
    echo "   5. Test the full user flow"
    echo ""
    echo -e "${CYAN}💡 Useful Commands:${NC}"
    echo "   make prod-status  - Check service status"
    echo "   make prod-logs    - View logs"
    echo "   make prod-restart - Restart services"
    echo ""
    echo -e "${CYAN}📚 Documentation:${NC}"
    echo "   • PRODUCTION_DEPLOYMENT.md - Full deployment guide"
    echo "   • CLERK_SETUP.md           - Authentication setup"
    echo "   • ARCHITECTURE.md          - System architecture"
    echo "   • SCALABILITY_SUMMARY.md   - Scalability overview"
    echo ""
else
    echo -e "${RED}❌ Invalid option. Please choose 1 or 2.${NC}"
    exit 1
fi

echo -e "${GREEN}🎉 Setup complete! Happy automating! 🚀${NC}"
echo ""

