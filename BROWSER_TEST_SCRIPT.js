// ============================================================================
// PASTE THIS IN CHROME CONSOLE ON X.COM TO TEST POST SCRAPING
// ============================================================================

console.log('🚀 Loading X Post Scraper...');

// Step 1: Load the scraper script
const script = document.createElement('script');
script.src = 'http://localhost:8888/x_post_scraper_extension.js';
document.head.appendChild(script);

script.onload = () => {
    console.log('✅ Scraper loaded!');
    
    // Step 2: Get your username (auto-detect from page)
    const getCurrentUsername = () => {
        const profileLink = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
        if (profileLink) {
            const href = profileLink.getAttribute('href');
            const match = href.match(/\/([^\/]+)$/);
            if (match) return match[1];
        }
        const urlMatch = window.location.pathname.match(/\/([^\/]+)/);
        return urlMatch ? urlMatch[1] : null;
    };
    
    const username = getCurrentUsername();
    
    if (!username) {
        console.error('❌ Could not detect username. Please navigate to your profile first!');
        return;
    }
    
    console.log(`📍 Detected username: @${username}`);
    
    // Step 3: Connect to backend
    console.log('🔌 Connecting to backend...');
    const ws = new WebSocket('ws://localhost:8765/ws/test');
    
    ws.onopen = () => {
        console.log('✅ Connected to backend!');
        
        // Notify backend that scraping is starting
        ws.send(JSON.stringify({
            type: 'SCRAPING_STARTED',
            username: username,
            targetCount: 50
        }));
        
        // Step 4: Start scraping
        console.log(`🔍 Starting to scrape posts from @${username}...`);
        console.log('⏳ This will take about 30-60 seconds...');
        
        const scraper = new XPostScraper();
        
        scraper.scrapeUserPosts(username, 50)
            .then(posts => {
                console.log(`✅ Scraping complete! Found ${posts.length} posts`);
                
                // Show sample posts
                console.log('\n📝 Sample posts:');
                posts.slice(0, 3).forEach((post, i) => {
                    console.log(`\n${i + 1}. ${post.content.substring(0, 80)}...`);
                    console.log(`   Engagement: ❤️ ${post.engagement.likes} 💬 ${post.engagement.replies} 🔄 ${post.engagement.reposts}`);
                });
                
                if (posts.length > 3) {
                    console.log(`\n... and ${posts.length - 3} more posts`);
                }
                
                // Send to backend
                console.log('\n📤 Sending posts to backend...');
                ws.send(JSON.stringify({
                    type: 'POSTS_SCRAPED',
                    posts: posts,
                    username: username
                }));
            })
            .catch(error => {
                console.error('❌ Scraping failed:', error);
                ws.send(JSON.stringify({
                    type: 'SCRAPING_FAILED',
                    error: error.message
                }));
            });
    };
    
    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        console.log('📨 Backend response:', data);
        
        if (data.type === 'ACK' && data.success) {
            console.log('✅ Backend received posts successfully!');
            console.log('🎉 Check your terminal and dashboard for results!');
        }
    };
    
    ws.onerror = (error) => {
        console.error('❌ WebSocket error:', error);
        console.error('Make sure the backend is running: python3 test_extension_post_scraper.py');
    };
    
    ws.onclose = () => {
        console.log('🔌 Disconnected from backend');
    };
};

script.onerror = () => {
    console.error('❌ Failed to load scraper script');
    console.error('Make sure the file server is running on http://localhost:8888');
};

console.log('⏳ Loading scraper...');


