
# Selenium connection to CUA Firefox instance
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities

def connect_to_cua_firefox():
    """Connect Selenium to the existing CUA Firefox instance"""
    
    try:
        # Set up Firefox options for remote connection
        options = Options()
        options.add_argument('--remote-debugging-port=9222')
        
        # Set up desired capabilities
        caps = DesiredCapabilities.FIREFOX.copy()
        caps['marionette'] = True
        
        # Connect to existing Firefox via remote WebDriver
        driver = webdriver.Remote(
            command_executor='http://localhost:4444/wd/hub',  # Selenium Grid
            desired_capabilities=caps,
            options=options
        )
        
        print('✅ Connected to CUA Firefox via Selenium!')
        
        # Example automation
        driver.get('https://example.com')
        title = driver.title
        print(f'📖 Page title: {title}')
        
        # Take screenshot
        driver.save_screenshot('selenium-screenshot.png')
        print('📸 Screenshot saved!')
        
        return driver
        
    except Exception as e:
        print(f'❌ Selenium connection failed: {e}')
        raise

# Alternative: Direct Firefox profile connection
def connect_via_firefox_profile():
    """Connect using Firefox profile (shared session)"""
    
    # Set up Firefox profile path
    profile_path = '/tmp/firefox-debug'  # Same as CUA Firefox
    
    options = Options()
    options.add_argument(f'--profile={profile_path}')
    options.add_argument('--remote-debugging-port=9222')
    
    # Use existing profile
    driver = webdriver.Firefox(options=options)
    
    return driver

# Usage
if __name__ == "__main__":
    driver = connect_to_cua_firefox()
    # Your automation here...
    # driver.quit()  # Don't quit if you want to keep CUA running
