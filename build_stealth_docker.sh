#!/bin/bash

echo "🥷 Building Stealth CUA Docker Container"
echo "======================================="

# Stop any existing container
echo "🛑 Stopping existing containers..."
docker stop cua-stealth 2>/dev/null || true
docker rm cua-stealth 2>/dev/null || true

# Build the image
echo "🔨 Building stealth Docker image..."
docker build -f Dockerfile.stealth -t cua-stealth .

if [ $? -eq 0 ]; then
    echo "✅ Build successful!"
    echo ""
    echo "🚀 Starting stealth container..."
    
    # Run the container
    docker run -d \
        --name cua-stealth \
        -p 5900:5900 \
        -p 8005:8005 \
        --shm-size=2g \
        cua-stealth
    
    echo "✅ Container started!"
    echo ""
    echo "🔗 Access Points:"
    echo "📺 VNC: vnc://localhost:5900"
    echo "🔌 API: http://localhost:8005"
    echo ""
    echo "🧪 Test the stealth server:"
    echo "curl http://localhost:8005/status"
    echo ""
    echo "📊 Container logs:"
    echo "docker logs -f cua-stealth"
    echo ""
    echo "🔄 To test with LangGraph agent:"
    echo "python3 langgraph_cua_agent.py"
    
else
    echo "❌ Build failed!"
    exit 1
fi
