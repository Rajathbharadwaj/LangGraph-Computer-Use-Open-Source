.PHONY: help start stop status restart logs clean build docker-build docker-stop install

# Colors
RED := \033[0;31m
GREEN := \033[0;32m
YELLOW := \033[1;33m
CYAN := \033[0;36m
NC := \033[0m

# Directories
LOG_DIR := $(HOME)/cua/logs
FRONTEND_DIR := $(HOME)/cua-frontend

help: ## Show this help message
	@echo "$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(CYAN)║                                                            ║$(NC)"
	@echo "$(CYAN)║         🚀 X GROWTH AUTOMATION SYSTEM MAKEFILE 🚀          ║$(NC)"
	@echo "$(CYAN)║                                                            ║$(NC)"
	@echo "$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(YELLOW)Available commands:$(NC)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(CYAN)%-15s$(NC) %s\n", $$1, $$2}'
	@echo ""

install: ## Install dependencies for all components
	@echo "$(YELLOW)📦 Installing Python dependencies...$(NC)"
	@pip install -q aiohttp fastapi uvicorn websockets requests python-multipart
	@echo "$(GREEN)✅ Python dependencies installed$(NC)"
	@echo ""
	@echo "$(YELLOW)📦 Installing Frontend dependencies...$(NC)"
	@cd $(FRONTEND_DIR) && npm install
	@echo "$(GREEN)✅ Frontend dependencies installed$(NC)"
	@echo ""
	@echo "$(YELLOW)📦 Installing LangGraph...$(NC)"
	@pip install -q -U langgraph-cli langgraph deepagents
	@echo "$(GREEN)✅ LangGraph installed$(NC)"

build: docker-build ## Build all components

docker-build: ## Build Docker image
	@echo "$(YELLOW)🐳 Building Docker image...$(NC)"
	@docker build -f Dockerfile.stealth.with_extension -t stealth-cua . > /dev/null 2>&1
	@echo "$(GREEN)✅ Docker image built$(NC)"

start: ## Start all services
	@echo "$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(CYAN)║         🚀 STARTING X GROWTH AUTOMATION SYSTEM 🚀          ║$(NC)"
	@echo "$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@mkdir -p $(LOG_DIR)
	@$(MAKE) -s docker-start
	@$(MAKE) -s extension-backend
	@$(MAKE) -s main-backend
	@$(MAKE) -s langgraph
	@$(MAKE) -s omniserver
	@$(MAKE) -s frontend
	@echo ""
	@echo "$(GREEN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(GREEN)║              ✅ ALL SYSTEMS OPERATIONAL! ✅                 ║$(NC)"
	@echo "$(GREEN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(CYAN)📍 Service URLs:$(NC)"
	@echo "   🎨 Dashboard:           http://localhost:3000"
	@echo "   🖥️  Main Backend:       http://localhost:8002"
	@echo "   🔌 Extension Backend:   http://localhost:8001"
	@echo "   🔍 OmniParser Server:   http://localhost:8003"
	@echo "   🤖 LangGraph API:       http://localhost:8124"
	@echo "   🌐 Docker Browser API:  http://localhost:8005"
	@echo ""
	@echo "$(YELLOW)💡 Run 'make logs' to view logs$(NC)"
	@echo "$(YELLOW)💡 Run 'make stop' to stop all services$(NC)"
	@echo ""

docker-start: ## Start Docker container
	@echo "$(YELLOW)🐳 Starting Docker container...$(NC)"
	@docker stop stealth-browser 2>/dev/null || true
	@docker rm stealth-browser 2>/dev/null || true
	@docker run -d --name stealth-browser --network host -p 8005:8005 -p 3000:3000 stealth-cua > /dev/null 2>&1
	@sleep 5
	@echo "$(GREEN)✅ Docker container started$(NC)"

extension-backend: ## Start Extension Backend (port 8001)
	@echo "$(YELLOW)🔌 Starting Extension Backend...$(NC)"
	@lsof -ti:8001 | xargs -r kill -9 2>/dev/null || true
	@bash -c "source $(HOME)/miniconda3/etc/profile.d/conda.sh && conda activate newat && (python backend_extension_server.py > $(LOG_DIR)/extension_backend.log 2>&1 &); sleep 1"
	@echo "$(GREEN)✅ Extension Backend started (port 8001)$(NC)"

main-backend: ## Start Main Backend (port 8002)
	@echo "$(YELLOW)🖥️  Starting Main Backend...$(NC)"
	@lsof -ti:8002 | xargs -r kill -9 2>/dev/null || true
	@bash -c "source $(HOME)/miniconda3/etc/profile.d/conda.sh && conda activate newat && (python backend_websocket_server.py > $(LOG_DIR)/main_backend.log 2>&1 &); sleep 1"
	@echo "$(GREEN)✅ Main Backend started (port 8002)$(NC)"

langgraph: ## Start LangGraph Server with PostgreSQL (port 8124)
	@echo "$(YELLOW)🤖 Starting LangGraph Server with PostgreSQL...$(NC)"
	@docker-compose -f docker-compose.langgraph.yml up -d > /dev/null 2>&1
	@sleep 8
	@echo "$(GREEN)✅ LangGraph Server started with persistent storage (port 8124)$(NC)"

omniserver: ## Start OmniParser Server (port 8003)
	@echo "$(YELLOW)🔍 Starting OmniParser Server...$(NC)"
	@lsof -ti:8003 | xargs -r kill -9 2>/dev/null || true
	@sleep 1
	@bash -c "source $(HOME)/miniconda3/etc/profile.d/conda.sh && conda activate omni && cd /home/rajathdb/OmniParser/omnitool/omniparserserver && (python omniparserserver.py --port 8003 > $(LOG_DIR)/omniserver.log 2>&1 &); sleep 1"
	@sleep 2
	@echo "$(GREEN)✅ OmniParser Server started (port 8003)$(NC)"

frontend: ## Start Frontend Dashboard (port 3000)
	@echo "$(YELLOW)🎨 Starting Frontend Dashboard...$(NC)"
	@lsof -ti:3000 | xargs -r kill -9 2>/dev/null || true
	@bash -c "cd $(FRONTEND_DIR) && (npm run dev > $(LOG_DIR)/frontend.log 2>&1 &); sleep 1"
	@sleep 3
	@echo "$(GREEN)✅ Frontend Dashboard started (port 3000)$(NC)"

stop: docker-stop ## Stop all services
	@echo "$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(CYAN)║         🛑 STOPPING X GROWTH AUTOMATION SYSTEM 🛑          ║$(NC)"
	@echo "$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(YELLOW)🔌 Stopping Extension Backend...$(NC)"
	@lsof -ti:8001 | xargs -r kill -9 2>/dev/null && echo "$(GREEN)✅ Stopped$(NC)" || echo "$(YELLOW)⚠️  Not running$(NC)"
	@echo "$(YELLOW)🖥️  Stopping Main Backend...$(NC)"
	@lsof -ti:8002 | xargs -r kill -9 2>/dev/null && echo "$(GREEN)✅ Stopped$(NC)" || echo "$(YELLOW)⚠️  Not running$(NC)"
	@echo "$(YELLOW)🤖 Stopping LangGraph Server...$(NC)"
	@docker-compose -f docker-compose.langgraph.yml down > /dev/null 2>&1 && echo "$(GREEN)✅ Stopped$(NC)" || echo "$(YELLOW)⚠️  Not running$(NC)"
	@echo "$(YELLOW)🔍 Stopping OmniParser Server...$(NC)"
	@lsof -ti:8003 | xargs -r kill -9 2>/dev/null && echo "$(GREEN)✅ Stopped$(NC)" || echo "$(YELLOW)⚠️  Not running$(NC)"
	@echo "$(YELLOW)🎨 Stopping Frontend...$(NC)"
	@lsof -ti:3000 | xargs -r kill -9 2>/dev/null && echo "$(GREEN)✅ Stopped$(NC)" || echo "$(YELLOW)⚠️  Not running$(NC)"
	@true
	@echo ""
	@echo "$(GREEN)✅ All services stopped$(NC)"

docker-stop: ## Stop Docker container
	@echo "$(YELLOW)🐳 Stopping Docker container...$(NC)"
	@docker stop stealth-browser 2>/dev/null && echo "$(GREEN)✅ Docker stopped$(NC)" || echo "$(YELLOW)⚠️  Not running$(NC)"
	@docker rm stealth-browser 2>/dev/null || true

status: ## Check status of all services
	@echo "$(CYAN)╔════════════════════════════════════════════════════════════╗$(NC)"
	@echo "$(CYAN)║         📊 X GROWTH AUTOMATION SYSTEM STATUS 📊            ║$(NC)"
	@echo "$(CYAN)╚════════════════════════════════════════════════════════════╝$(NC)"
	@echo ""
	@echo "$(YELLOW)🔍 Checking Services:$(NC)"
	@ss -tlnp 2>/dev/null | grep -q ":3000 " && echo "   $(GREEN)✅ Frontend Dashboard (3000)$(NC)" || echo "   $(RED)❌ Frontend Dashboard (3000)$(NC)"
	@ss -tlnp 2>/dev/null | grep -q ":8002 " && echo "   $(GREEN)✅ Main Backend (8002)$(NC)" || echo "   $(RED)❌ Main Backend (8002)$(NC)"
	@ss -tlnp 2>/dev/null | grep -q ":8001 " && echo "   $(GREEN)✅ Extension Backend (8001)$(NC)" || echo "   $(RED)❌ Extension Backend (8001)$(NC)"
	@ss -tlnp 2>/dev/null | grep -q ":8003 " && echo "   $(GREEN)✅ OmniParser Server (8003)$(NC)" || echo "   $(RED)❌ OmniParser Server (8003)$(NC)"
	@ss -tlnp 2>/dev/null | grep -q ":8124 " && echo "   $(GREEN)✅ LangGraph Server (8124)$(NC)" || echo "   $(RED)❌ LangGraph Server (8124)$(NC)"
	@ss -tlnp 2>/dev/null | grep -q ":8005 " && echo "   $(GREEN)✅ Docker Browser API (8005)$(NC)" || echo "   $(RED)❌ Docker Browser API (8005)$(NC)"
	@echo ""
	@echo "$(YELLOW)🐳 Docker Containers:$(NC)"
	@docker ps | grep -q stealth-browser && echo "   $(GREEN)✅ stealth-browser (running)$(NC)" || echo "   $(RED)❌ stealth-browser (not running)$(NC)"
	@docker ps | grep -q cua-langgraph-api && echo "   $(GREEN)✅ cua-langgraph-api (running)$(NC)" || echo "   $(RED)❌ cua-langgraph-api (not running)$(NC)"
	@docker ps | grep -q cua-langgraph-postgres && echo "   $(GREEN)✅ cua-langgraph-postgres (running)$(NC)" || echo "   $(RED)❌ cua-langgraph-postgres (not running)$(NC)"
	@docker ps | grep -q cua-langgraph-redis && echo "   $(GREEN)✅ cua-langgraph-redis (running)$(NC)" || echo "   $(RED)❌ cua-langgraph-redis (not running)$(NC)"
	@echo ""

restart: stop start ## Restart all services

logs: ## View logs (tail -f all logs)
	@echo "$(CYAN)📋 Viewing logs (Ctrl+C to exit)...$(NC)"
	@tail -f $(LOG_DIR)/*.log

logs-extension: ## View Extension Backend logs
	@tail -f $(LOG_DIR)/extension_backend.log

logs-backend: ## View Main Backend logs
	@tail -f $(LOG_DIR)/main_backend.log

logs-langgraph: ## View LangGraph logs
	@docker-compose -f docker-compose.langgraph.yml logs -f langgraph-api

logs-frontend: ## View Frontend logs
	@tail -f $(LOG_DIR)/frontend.log

logs-omniserver: ## View OmniParser Server logs
	@tail -f $(LOG_DIR)/omniserver.log

logs-docker: ## View Docker logs
	@docker logs -f stealth-browser

clean: stop ## Stop all services and clean logs
	@echo "$(YELLOW)🧹 Cleaning logs...$(NC)"
	@rm -rf $(LOG_DIR)/*.log
	@echo "$(GREEN)✅ Logs cleaned$(NC)"

dev: ## Start in development mode (with live logs)
	@$(MAKE) start
	@$(MAKE) logs

quick: ## Quick restart (stop + start without rebuild)
	@$(MAKE) stop
	@sleep 2
	@$(MAKE) start

full-restart: stop clean docker-build start ## Full restart (rebuild Docker + clean logs)

# ============================================================================
# Production Commands
# ============================================================================

prod-setup: ## Setup production environment
	@echo "$(CYAN)🚀 Setting up production environment...$(NC)"
	@echo ""
	@echo "$(YELLOW)1. Installing production dependencies...$(NC)"
	@pip install -r requirements-prod.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"
	@echo ""
	@echo "$(YELLOW)2. Generating encryption key...$(NC)"
	@python -c "from cryptography.fernet import Fernet; print('COOKIE_ENCRYPTION_KEY=' + Fernet.generate_key().decode())" > .env.prod.key
	@echo "$(GREEN)✅ Encryption key generated in .env.prod.key$(NC)"
	@echo ""
	@echo "$(YELLOW)3. Copy .env.example to .env and fill in values$(NC)"
	@echo "$(YELLOW)4. Sign up for Clerk at https://clerk.com$(NC)"
	@echo "$(YELLOW)5. Add Clerk keys to .env$(NC)"

prod-db-init: ## Initialize production database
	@echo "$(YELLOW)🗄️  Initializing production database...$(NC)"
	@python -c "from database import init_db; init_db()"
	@echo "$(GREEN)✅ Database initialized$(NC)"

prod-up: ## Start production services with docker-compose
	@echo "$(CYAN)🚀 Starting production services...$(NC)"
	@docker-compose -f docker-compose.prod.yml up -d
	@echo "$(GREEN)✅ Production services started$(NC)"
	@echo ""
	@echo "$(CYAN)📍 Production URLs:$(NC)"
	@echo "   🎨 Dashboard:         http://localhost:3000"
	@echo "   🖥️  Backend API:      http://localhost:8002"
	@echo "   🤖 LangGraph:         http://localhost:8124"
	@echo "   🔍 OmniParser:        http://localhost:8003"

prod-down: ## Stop production services
	@echo "$(YELLOW)🛑 Stopping production services...$(NC)"
	@docker-compose -f docker-compose.prod.yml down
	@echo "$(GREEN)✅ Services stopped$(NC)"

prod-logs: ## View production logs
	@docker-compose -f docker-compose.prod.yml logs -f

prod-status: ## Check production service status
	@docker-compose -f docker-compose.prod.yml ps

prod-restart: ## Restart production services
	@$(MAKE) prod-down
	@$(MAKE) prod-up

prod-clean: ## Clean production data (WARNING: deletes database!)
	@echo "$(RED)⚠️  WARNING: This will delete all production data!$(NC)"
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ]
	@docker-compose -f docker-compose.prod.yml down -v
	@echo "$(GREEN)✅ Production data cleaned$(NC)"

