
// Puppeteer connection to CUA Firefox instance
const puppeteer = require('puppeteer-core');

async function connectToCUAFirefox() {
    try {
        // Connect to the existing Firefox instance
        const browser = await puppeteer.connect({
            browserWSEndpoint: 'ws://localhost:9222',  // WebSocket endpoint
            defaultViewport: null
        });
        
        console.log('✅ Connected to CUA Firefox instance!');
        
        // Get existing pages or create new one
        const pages = await browser.pages();
        let page;
        
        if (pages.length > 0) {
            page = pages[0];  // Use existing page
            console.log('📄 Using existing page');
        } else {
            page = await browser.newPage();  // Create new page
            console.log('📄 Created new page');
        }
        
        // Example automation
        console.log('🎯 Starting automation...');
        await page.goto('https://example.com');
        
        const title = await page.title();
        console.log(`📖 Page title: ${title}`);
        
        // Take screenshot
        await page.screenshot({ path: 'puppeteer-screenshot.png' });
        console.log('📸 Screenshot saved!');
        
        // The browser stays connected - don't close it
        // await browser.disconnect();  // Use disconnect() instead of close()
        
        return { browser, page };
        
    } catch (error) {
        console.error('❌ Connection failed:', error);
        throw error;
    }
}

// Usage
connectToCUAFirefox()
    .then(({ browser, page }) => {
        console.log('🚀 Ready for automation!');
        // Your automation code here...
    })
    .catch(console.error);

module.exports = { connectToCUAFirefox };
