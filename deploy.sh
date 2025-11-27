#!/bin/bash

# LangGraph CUA Agent Deployment Script

set -e

echo "🤖 LangGraph Computer Use Agent Deployment"
echo "=========================================="

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if langgraph CLI is installed
if ! command -v langgraph &> /dev/null; then
    echo -e "${RED}❌ LangGraph CLI not found${NC}"
    echo "Install with: pip install langgraph-cli"
    exit 1
fi

# Check if Docker is running (for production mode)
check_docker() {
    if ! docker info &> /dev/null; then
        echo -e "${RED}❌ Docker is not running${NC}"
        echo "Please start Docker and try again"
        exit 1
    fi
}

# Validate configuration
validate_config() {
    echo -e "${BLUE}🔍 Validating configuration...${NC}"
    if [ -f "validate_config.py" ]; then
        python validate_config.py
    else
        echo -e "${YELLOW}⚠️ Configuration validator not found, skipping validation${NC}"
    fi
}

# Development mode
dev_mode() {
    echo -e "${BLUE}🚀 Starting development server...${NC}"
    
    # Install dev dependencies if needed
    if ! python -c "import langgraph.cli" &> /dev/null; then
        echo -e "${YELLOW}📦 Installing development dependencies...${NC}"
        pip install -U "langgraph-cli[inmem]"
    fi
    
    echo -e "${GREEN}✅ Starting LangGraph dev server on http://localhost:2024${NC}"
    echo -e "${YELLOW}💡 Use --tunnel for public access, --debug-port 5678 for debugging${NC}"
    
    langgraph dev --host 0.0.0.0 --port 2024
}

# Production mode
prod_mode() {
    echo -e "${BLUE}🏭 Starting production server...${NC}"
    
    check_docker
    
    echo -e "${YELLOW}📦 Building Docker image...${NC}"
    langgraph build -t cua-agent --pull
    
    echo -e "${GREEN}✅ Starting LangGraph production server on http://localhost:8123${NC}"
    echo -e "${YELLOW}💡 Access logs with: docker logs <container_id>${NC}"
    
    langgraph up --port 8123
}

# Build only
build_mode() {
    echo -e "${BLUE}🔨 Building Docker image...${NC}"
    
    check_docker
    
    langgraph build -t cua-agent --pull
    echo -e "${GREEN}✅ Docker image 'cua-agent' built successfully${NC}"
    echo "Run with: docker run -p 8123:8000 cua-agent"
}

# Generate Dockerfile
dockerfile_mode() {
    echo -e "${BLUE}📄 Generating Dockerfile...${NC}"
    
    langgraph dockerfile Dockerfile
    echo -e "${GREEN}✅ Dockerfile generated${NC}"
    echo "Build with: docker build -t cua-agent ."
}

# Show usage
show_usage() {
    echo "Usage: $0 [MODE]"
    echo ""
    echo "Modes:"
    echo "  dev        Start development server (recommended for testing)"
    echo "  prod       Start production server with Docker"
    echo "  build      Build Docker image only"
    echo "  dockerfile Generate Dockerfile"
    echo "  validate   Validate configuration only"
    echo ""
    echo "Examples:"
    echo "  $0 dev         # Quick development server"
    echo "  $0 prod        # Full production deployment"
    echo "  $0 validate    # Check configuration"
}

# Main logic
case "${1:-dev}" in
    "dev")
        validate_config
        dev_mode
        ;;
    "prod")
        validate_config
        prod_mode
        ;;
    "build")
        validate_config
        build_mode
        ;;
    "dockerfile")
        validate_config
        dockerfile_mode
        ;;
    "validate")
        validate_config
        ;;
    "help"|"-h"|"--help")
        show_usage
        ;;
    *)
        echo -e "${RED}❌ Unknown mode: $1${NC}"
        show_usage
        exit 1
        ;;
esac
