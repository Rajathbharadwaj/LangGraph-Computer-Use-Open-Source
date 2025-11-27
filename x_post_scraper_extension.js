/**
 * X Post Scraper for Chrome Extension
 * 
 * This script scrapes the user's own X posts from their profile page
 * and sends them to the backend for writing style analysis.
 * 
 * NO X API NEEDED - Just DOM scraping!
 */

// ============================================================================
// POST SCRAPER
// ============================================================================

class XPostScraper {
    constructor() {
        this.scrapedPosts = [];
        this.isScrapingInProgress = false;
    }

    /**
     * Scrape user's posts from their profile page
     * @param {string} username - X username (e.g., "Rajath_DB")
     * @param {number} targetCount - Number of posts to scrape (default: 50)
     * @returns {Promise<Array>} - Array of scraped posts
     */
    async scrapeUserPosts(username, targetCount = 50) {
        console.log(`🔍 Starting to scrape ${targetCount} posts from @${username}...`);
        
        this.isScrapingInProgress = true;
        this.scrapedPosts = [];

        try {
            // 1. Navigate to user's profile if not already there
            const currentUrl = window.location.href;
            const profileUrl = `https://x.com/${username}`;
            
            if (!currentUrl.includes(username)) {
                console.log(`📍 Navigating to ${profileUrl}...`);
                window.location.href = profileUrl;
                // Wait for page load
                await this.sleep(3000);
            }

            // 2. Scroll and scrape posts
            let scrollAttempts = 0;
            const maxScrollAttempts = 20; // Prevent infinite scrolling

            while (this.scrapedPosts.length < targetCount && scrollAttempts < maxScrollAttempts) {
                // Scrape visible posts
                const newPosts = this.scrapeVisiblePosts();
                console.log(`📝 Found ${newPosts.length} new posts (Total: ${this.scrapedPosts.length}/${targetCount})`);

                // Scroll down to load more
                window.scrollBy(0, 1000);
                await this.sleep(2000); // Wait for new posts to load

                scrollAttempts++;
            }

            console.log(`✅ Scraping complete! Collected ${this.scrapedPosts.length} posts`);
            return this.scrapedPosts;

        } catch (error) {
            console.error('❌ Error scraping posts:', error);
            throw error;
        } finally {
            this.isScrapingInProgress = false;
        }
    }

    /**
     * Scrape posts currently visible on the page
     * @returns {Array} - Array of new posts
     */
    scrapeVisiblePosts() {
        const newPosts = [];

        // X uses article elements for tweets
        const tweetElements = document.querySelectorAll('article[data-testid="tweet"]');

        tweetElements.forEach(tweetEl => {
            try {
                // Extract post data
                const postData = this.extractPostData(tweetEl);

                // Check if we already scraped this post (by content hash)
                const contentHash = this.hashString(postData.content);
                const alreadyScraped = this.scrapedPosts.some(
                    p => this.hashString(p.content) === contentHash
                );

                if (!alreadyScraped && postData.content) {
                    this.scrapedPosts.push(postData);
                    newPosts.push(postData);
                }
            } catch (error) {
                console.warn('⚠️ Failed to extract post data:', error);
            }
        });

        return newPosts;
    }

    /**
     * Extract post data from a tweet element
     * @param {Element} tweetEl - Tweet article element
     * @returns {Object} - Post data
     */
    extractPostData(tweetEl) {
        // Get post text
        const textEl = tweetEl.querySelector('[data-testid="tweetText"]');
        const content = textEl ? textEl.innerText : '';

        // Get timestamp
        const timeEl = tweetEl.querySelector('time');
        const timestamp = timeEl ? timeEl.getAttribute('datetime') : new Date().toISOString();

        // Get engagement metrics
        const engagement = this.extractEngagementMetrics(tweetEl);

        // Get post URL (for reference)
        const linkEl = tweetEl.querySelector('a[href*="/status/"]');
        const postUrl = linkEl ? `https://x.com${linkEl.getAttribute('href')}` : '';

        return {
            content,
            timestamp,
            engagement,
            postUrl,
            contentType: 'post', // vs 'reply' or 'retweet'
            scrapedAt: new Date().toISOString()
        };
    }

    /**
     * Extract engagement metrics (likes, replies, reposts)
     * @param {Element} tweetEl - Tweet element
     * @returns {Object} - Engagement metrics
     */
    extractEngagementMetrics(tweetEl) {
        const engagement = {
            likes: 0,
            replies: 0,
            reposts: 0,
            views: 0
        };

        try {
            // Reply count
            const replyButton = tweetEl.querySelector('[data-testid="reply"]');
            if (replyButton) {
                const replyText = replyButton.getAttribute('aria-label') || '';
                const replyMatch = replyText.match(/(\d+)/);
                engagement.replies = replyMatch ? parseInt(replyMatch[1]) : 0;
            }

            // Repost count
            const repostButton = tweetEl.querySelector('[data-testid="retweet"]');
            if (repostButton) {
                const repostText = repostButton.getAttribute('aria-label') || '';
                const repostMatch = repostText.match(/(\d+)/);
                engagement.reposts = repostMatch ? parseInt(repostMatch[1]) : 0;
            }

            // Like count
            const likeButton = tweetEl.querySelector('[data-testid="like"]');
            if (likeButton) {
                const likeText = likeButton.getAttribute('aria-label') || '';
                const likeMatch = likeText.match(/(\d+)/);
                engagement.likes = likeMatch ? parseInt(likeMatch[1]) : 0;
            }

            // View count (if available)
            const viewsEl = tweetEl.querySelector('[href$="/analytics"]');
            if (viewsEl) {
                const viewsText = viewsEl.innerText || '';
                const viewsMatch = viewsText.match(/([\d.]+)([KMB])?/);
                if (viewsMatch) {
                    let views = parseFloat(viewsMatch[1]);
                    const suffix = viewsMatch[2];
                    if (suffix === 'K') views *= 1000;
                    if (suffix === 'M') views *= 1000000;
                    if (suffix === 'B') views *= 1000000000;
                    engagement.views = Math.floor(views);
                }
            }
        } catch (error) {
            console.warn('⚠️ Failed to extract engagement metrics:', error);
        }

        return engagement;
    }

    /**
     * Simple string hash function
     */
    hashString(str) {
        let hash = 0;
        for (let i = 0; i < str.length; i++) {
            const char = str.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash; // Convert to 32bit integer
        }
        return hash;
    }

    /**
     * Sleep utility
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

// ============================================================================
// INTEGRATION WITH EXTENSION
// ============================================================================

/**
 * Add to content.js message handler
 */
function handleScrapePostsAction(message) {
    console.log('📨 Received SCRAPE_POSTS action');

    const scraper = new XPostScraper();
    const username = message.username || getCurrentUsername();
    const targetCount = message.targetCount || 50;

    scraper.scrapeUserPosts(username, targetCount)
        .then(posts => {
            console.log(`✅ Scraped ${posts.length} posts`);

            // Send to background script
            chrome.runtime.sendMessage({
                type: 'POSTS_SCRAPED',
                posts: posts,
                username: username
            }, response => {
                console.log('📤 Posts sent to background script:', response);
            });
        })
        .catch(error => {
            console.error('❌ Scraping failed:', error);
            chrome.runtime.sendMessage({
                type: 'SCRAPING_FAILED',
                error: error.message
            });
        });
}

/**
 * Get current logged-in username
 */
function getCurrentUsername() {
    // Try to get username from profile link
    const profileLink = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]');
    if (profileLink) {
        const href = profileLink.getAttribute('href');
        const match = href.match(/\/([^\/]+)$/);
        if (match) {
            return match[1];
        }
    }

    // Fallback: get from URL if on profile page
    const urlMatch = window.location.pathname.match(/\/([^\/]+)/);
    return urlMatch ? urlMatch[1] : null;
}

// ============================================================================
// EXPORT
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { XPostScraper };
}

