#!/bin/bash

echo "🔄 Rebuilding Stealth Docker with Session Management"
echo "====================================================="

# Stop existing container
echo "🛑 Stopping existing container..."
docker stop cua-stealth 2>/dev/null || true
docker rm cua-stealth 2>/dev/null || true

# Rebuild with no cache to ensure fresh build
echo "🔨 Building fresh Docker image..."
docker build --no-cache -f Dockerfile.stealth -t cua-stealth .

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
    echo ""
    echo "🚀 Starting container..."
    
    docker run -d \
        --name cua-stealth \
        -p 5900:5900 \
        -p 8005:8005 \
        --shm-size=2g \
        cua-stealth
    
    echo "✅ Container started!"
    echo ""
    echo "⏳ Waiting for services to start..."
    sleep 10
    
    echo ""
    echo "🧪 Testing new session endpoints..."
    echo ""
    
    echo "1️⃣ Testing status endpoint:"
    curl -s http://localhost:8005/status | python3 -m json.tool
    echo ""
    
    echo "2️⃣ Testing root endpoint (should show new features):"
    curl -s http://localhost:8005/ | python3 -m json.tool
    echo ""
    
    echo "✅ NEW SESSION MANAGEMENT ENDPOINTS:"
    echo "   POST /session/save   - Capture cookies after login"
    echo "   POST /session/load   - Load saved cookies"
    echo "   POST /session/check  - Check if logged in"
    echo ""
    echo "🔗 Access Points:"
    echo "   📺 VNC: vnc://localhost:5900"
    echo "   🔌 API: http://localhost:8005"
    echo ""
    echo "📖 Usage Guide:"
    echo "   See: SAAS_AUTH_GUIDE.md"
    echo "   See: x_auth_strategies.md"
    
else
    echo "❌ Build failed!"
    exit 1
fi

