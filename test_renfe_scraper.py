#!/usr/bin/env python3
"""
Test script to debug and update the Renfe scraper
"""
import time
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

def test_renfe_website():
    """Test the current state of Renfe website and identify elements"""
    
    # Setup Chrome driver with automatic driver management
    chrome_options = Options()
    # Remove headless for debugging
    # chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1200,1000")
    
    # Use webdriver-manager to automatically manage ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("🚀 Opening Renfe website...")
        driver.get("https://www.renfe.com/es/es")
        
        # Wait for page to load
        time.sleep(5)
        
        print("📄 Page title:", driver.title)
        print("🔗 Current URL:", driver.current_url)
        
        # Check for cookie banner
        print("\n🍪 Checking for cookie banner...")
        try:
            cookie_banner = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.ID, "onetrust-group-container"))
            )
            print("✅ Cookie banner found!")
            
            # Try to find and click accept button
            try:
                accept_button = driver.find_element(By.ID, "onetrust-accept-btn-handler")
                accept_button.click()
                print("✅ Cookies accepted!")
                time.sleep(3)
            except NoSuchElementException:
                print("❌ Cookie accept button not found")
                
        except TimeoutException:
            print("❌ No cookie banner found or timeout")
        
        # Look for search form elements
        print("\n🔍 Looking for search form elements...")
        
        # Check for origin input
        origin_selectors = [
            "input[data-testid='origin-input']",
            "input[placeholder*='Origen']",
            "#origin",
            "input[name='origin']",
            ".search-form input:first-of-type"
        ]
        
        origin_found = False
        for selector in origin_selectors:
            try:
                if selector.startswith("#") or selector.startswith("."):
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                else:
                    element = driver.find_element(By.CSS_SELECTOR, selector)
                print(f"✅ Origin input found with selector: {selector}")
                origin_found = True
                break
            except NoSuchElementException:
                continue
        
        if not origin_found:
            print("❌ Origin input not found with any selector")
            # Let's see what inputs are available
            inputs = driver.find_elements(By.TAG_NAME, "input")
            print(f"📝 Found {len(inputs)} input elements:")
            for i, inp in enumerate(inputs[:10]):  # Show first 10
                try:
                    print(f"  {i}: type='{inp.get_attribute('type')}' placeholder='{inp.get_attribute('placeholder')}' id='{inp.get_attribute('id')}' name='{inp.get_attribute('name')}'")
                except:
                    print(f"  {i}: Could not get attributes")
        
        # Save page source for analysis
        with open("/Users/barreang/personal/ave-round-tripper/renfe_page_source.html", "w", encoding="utf-8") as f:
            f.write(driver.page_source)
        print("\n💾 Page source saved to renfe_page_source.html")
        
        # Take a screenshot
        driver.save_screenshot("/Users/barreang/personal/ave-round-tripper/renfe_screenshot.png")
        print("📸 Screenshot saved to renfe_screenshot.png")
        
        print("\n⏱️  Waiting 10 seconds for manual inspection...")
        time.sleep(10)
        
    except Exception as e:
        print(f"❌ Error: {e}")
    
    finally:
        driver.quit()
        print("🔚 Browser closed")

if __name__ == "__main__":
    test_renfe_website()
