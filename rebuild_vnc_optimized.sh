STDIN
#!/bin/bash

echo "🔄 Rebuilding Docker with optimized VNC settings..."
echo ""

# Stop existing container
echo "⏹️ Stopping existing container..."
docker stop stealth-cua 2>/dev/null || true
docker rm stealth-cua 2>/dev/null || true

# Rebuild image
echo "🏗️ Building new image..."
docker build -f Dockerfile.stealth -t stealth-cua:latest .

# Start new container
echo "🚀 Starting optimized container..."
docker run -d \
  --name stealth-cua \
  -p 5900:5900 \
  -p 8005:8005 \
  --shm-size=2gb \
  stealth-cua:latest

echo ""
echo "✅ Container rebuilt with VNC optimizations!"
echo ""
echo "📋 VNC Optimizations Applied:"
echo "  • Quality: 9 (maximum)"
echo "  • Compression: 0 (minimum)"
echo "  • Cache: Enabled (10 levels)"
echo "  • Speed: LAN optimized"
echo "  • Threading: Enabled"
echo ""
echo "🔗 Access:"
echo "  VNC: localhost:5900"
echo "  API: http://localhost:8005"
echo ""
echo "⏳ Waiting for services to start..."
sleep 10

curl -s http://localhost:8005/status | python3 -m json.tool || echo "Server starting..."

