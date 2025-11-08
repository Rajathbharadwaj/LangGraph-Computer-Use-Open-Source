
// Playwright connection to CUA Firefox instance
const { firefox } = require('playwright');

async function connectToCUAFirefox() {
    try {
        // Connect to the existing Firefox instance via CDP
        const browser = await firefox.connectOverCDP('http://localhost:9222');
        
        console.log('✅ Connected to CUA Firefox instance via Playwright!');
        
        // Get existing contexts and pages
        const contexts = browser.contexts();
        let context, page;
        
        if (contexts.length > 0) {
            context = contexts[0];
            const pages = context.pages();
            page = pages.length > 0 ? pages[0] : await context.newPage();
        } else {
            context = await browser.newContext();
            page = await context.newPage();
        }
        
        console.log('📄 Ready for Playwright automation!');
        
        // Example automation
        await page.goto('https://example.com');
        const title = await page.title();
        console.log(`📖 Page title: ${title}`);
        
        // Take screenshot
        await page.screenshot({ path: 'playwright-screenshot.png' });
        console.log('📸 Screenshot saved!');
        
        return { browser, context, page };
        
    } catch (error) {
        console.error('❌ Playwright connection failed:', error);
        throw error;
    }
}

// Usage
connectToCUAFirefox()
    .then(({ browser, context, page }) => {
        console.log('🚀 Playwright ready for automation!');
        // Your automation code here...
    })
    .catch(console.error);

module.exports = { connectToCUAFirefox };
