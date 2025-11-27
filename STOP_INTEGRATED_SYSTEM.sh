#!/bin/bash

echo "🛑 Stopping Integrated X Growth Agent System..."
echo ""

# Kill processes by port
echo "📡 Stopping Extension Backend (port 8001)..."
lsof -ti:8001 | xargs kill -9 2>/dev/null
echo "✅ Extension backend stopped"

echo "🔧 Stopping Main Backend (port 8000)..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
echo "✅ Main backend stopped"

echo "🎨 Stopping Frontend (port 3000)..."
lsof -ti:3000 | xargs kill -9 2>/dev/null
echo "✅ Frontend stopped"

echo "🐳 Stopping Docker Container..."
docker stop stealth-cua 2>/dev/null
echo "✅ Docker container stopped"

echo ""
echo "✅ All services stopped!"

