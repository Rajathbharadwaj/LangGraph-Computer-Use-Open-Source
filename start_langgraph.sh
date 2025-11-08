#!/bin/bash

# Start LangGraph with PostgreSQL persistence using docker-compose
# This ensures chat history persists across reboots
#
# NOTE: We now use docker-compose instead of 'langgraph up' because:
# 1. Docker-compose manages all services (API, PostgreSQL, Redis) together
# 2. Services are on the same network and can communicate
# 3. Easier to manage and restart
# 4. Follows official LangGraph standalone server deployment guide

cd /home/rajathdb/cua

# Start LangGraph services (includes PostgreSQL and Redis)
docker-compose -f docker-compose.langgraph.yml up -d

echo "✅ LangGraph started with PostgreSQL persistence on port 8124"
echo "📊 Check status: docker ps | grep langgraph"
echo "📝 View logs: docker-compose -f docker-compose.langgraph.yml logs -f langgraph-api"
