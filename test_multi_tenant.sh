#!/bin/bash

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🧪 Testing Multi-Tenant Container System"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

# Test 1: Build container image
echo "📦 Step 1: Building user container image..."
docker build -f Dockerfile.user-container -t xgrowth-automation:latest . > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "   ✅ Container image built successfully"
else
    echo "   ❌ Failed to build container image"
    exit 1
fi

# Test 2: Start main API
echo ""
echo "🚀 Step 2: Starting multi-tenant API..."
python multi_tenant_backend.py > /tmp/api.log 2>&1 &
API_PID=$!
sleep 5

if ps -p $API_PID > /dev/null; then
    echo "   ✅ API started (PID: $API_PID)"
else
    echo "   ❌ API failed to start"
    cat /tmp/api.log
    exit 1
fi

# Test 3: Health check
echo ""
echo "💚 Step 3: Checking API health..."
HEALTH=$(curl -s http://localhost:8000/health)

if echo "$HEALTH" | grep -q "healthy"; then
    echo "   ✅ API is healthy"
else
    echo "   ❌ API health check failed"
    kill $API_PID
    exit 1
fi

# Test 4: Create test user container
echo ""
echo "👤 Step 4: Creating test user container..."
ONBOARD_RESULT=$(curl -s -X POST http://localhost:8000/api/users/onboard \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user_test123",
    "email": "test@example.com",
    "plan": "starter"
  }')

if echo "$ONBOARD_RESULT" | grep -q "success"; then
    echo "   ✅ Test user container created"
    echo "$ONBOARD_RESULT" | jq .container 2>/dev/null || echo "$ONBOARD_RESULT"
else
    echo "   ❌ Failed to create user container"
    echo "$ONBOARD_RESULT"
    kill $API_PID
    exit 1
fi

# Test 5: Check container status
echo ""
echo "🔍 Step 5: Checking container status..."
sleep 3
STATUS=$(curl -s http://localhost:8000/api/containers/user_test123/status)

if echo "$STATUS" | grep -q "running"; then
    echo "   ✅ Container is running"
    echo "$STATUS" | jq . 2>/dev/null || echo "$STATUS"
else
    echo "   ⚠️  Container status: $STATUS"
fi

# Test 6: List containers
echo ""
echo "📋 Step 6: Listing all containers..."
docker ps | grep xgrowth

# Test 7: Test automation start
echo ""
echo "▶️  Step 7: Testing automation start..."
START_RESULT=$(curl -s -X POST http://localhost:8000/api/automation/user_test123/start \
  -H "Content-Type: application/json" \
  -d '{
    "workflow": "engagement",
    "config": {"test_mode": true}
  }')

if echo "$START_RESULT" | grep -q "success"; then
    echo "   ✅ Automation started"
else
    echo "   ⚠️  Automation start result: $START_RESULT"
fi

# Summary
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Multi-Tenant System Test Complete!"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
echo "📊 Results:"
echo "   - API running on: http://localhost:8000"
echo "   - Test user: user_test123"
echo "   - Container status: $(docker ps | grep user_test123 | wc -l) running"
echo ""
echo "🔗 Try these:"
echo "   - View status: curl http://localhost:8000/api/containers/user_test123/status"
echo "   - View logs: curl http://localhost:8000/api/containers/user_test123/logs"
echo "   - Stop container: docker stop xgrowth-user-user_tes"
echo "   - Stop API: kill $API_PID"
echo ""
echo "📚 Read MULTI_TENANT_SETUP.md for full documentation"
echo ""
