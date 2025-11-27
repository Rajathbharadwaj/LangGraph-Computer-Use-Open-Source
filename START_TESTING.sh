#!/bin/bash

echo "================================================================================"
echo "🚀 STARTING IMPORT POSTS FEATURE TEST"
echo "================================================================================"
echo ""

# Check if backend is running
if pgrep -f "test_extension_post_scraper.py" > /dev/null; then
    echo "✅ Backend server already running"
else
    echo "🔄 Starting backend server..."
    cd /home/rajathdb/cua
    python3 test_extension_post_scraper.py &
    sleep 2
    echo "✅ Backend server started"
fi

echo ""
echo "================================================================================"
echo "SERVERS RUNNING:"
echo "================================================================================"
echo "✅ Backend WebSocket: ws://localhost:8765/ws/test"
echo ""

echo "================================================================================"
echo "NEXT STEPS:"
echo "================================================================================"
echo ""
echo "1. Start the frontend:"
echo "   cd /home/rajathdb/cua-frontend"
echo "   npm run dev"
echo ""
echo "2. Open dashboard:"
echo "   http://localhost:3000"
echo ""
echo "3. You'll see the 'Import Your Posts' card!"
echo ""
echo "4. To test scraping:"
echo "   - Open X.com in Chrome"
echo "   - Open DevTools Console (F12)"
echo "   - Paste the code from TEST_IMPORT_POSTS_FEATURE.md"
echo "   - Watch this terminal for scraped posts!"
echo ""
echo "================================================================================"
echo "📖 Full instructions: TEST_IMPORT_POSTS_FEATURE.md"
echo "================================================================================"


