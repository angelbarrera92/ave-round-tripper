#!/usr/bin/env python3

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
import time

def analyze_renfe_website():
    """Analyze the current structure of the Renfe website"""
    
    # Set up Chrome options
    chrome_options = Options()
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--window-size=1080,1080")
    
    # Use webdriver-manager to automatically handle ChromeDriver
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=chrome_options)
    
    try:
        print("🚂 Analyzing Renfe website structure...")
        driver.get("https://www.renfe.com/es/es")
        
        # Wait for page to load
        time.sleep(5)
        
        print("✅ Page loaded successfully")
        print(f"📄 Page title: {driver.title}")
        
        # Check for cookie banner
        try:
            cookie_elements = driver.find_elements(By.CSS_SELECTOR, "[id*='cookie'], [id*='onetrust'], [class*='cookie']")
            if cookie_elements:
                print(f"🍪 Found {len(cookie_elements)} cookie-related elements:")
                for elem in cookie_elements[:3]:  # Show first 3
                    print(f"   - ID: {elem.get_attribute('id')}, Class: {elem.get_attribute('class')}")
            else:
                print("🍪 No obvious cookie elements found")
        except Exception as e:
            print(f"❌ Error checking cookies: {e}")
        
        # Look for search form elements
        print("\n🔍 Looking for search form elements...")
        
        # Common selectors to try
        selectors_to_check = [
            "input[placeholder*='Origen']",
            "input[placeholder*='origen']", 
            "input[name*='origin']",
            "input[id*='origin']",
            "#origin",
            "input[placeholder*='Destino']",
            "input[placeholder*='destino']",
            "input[name*='destination']", 
            "input[id*='destination']",
            "#destination",
            "input[type='date']",
            "input[placeholder*='fecha']",
            "input[placeholder*='Fecha']"
        ]
        
        found_elements = {}
        for selector in selectors_to_check:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                if elements:
                    found_elements[selector] = len(elements)
                    print(f"   ✅ Found {len(elements)} elements for: {selector}")
                    # Show attributes of first element
                    elem = elements[0]
                    print(f"      - ID: {elem.get_attribute('id')}")
                    print(f"      - Name: {elem.get_attribute('name')}")
                    print(f"      - Placeholder: {elem.get_attribute('placeholder')}")
                    print(f"      - Class: {elem.get_attribute('class')}")
            except Exception as e:
                pass
        
        if not found_elements:
            print("❌ No search form elements found with common selectors")
            
        # Try to find any input elements
        print("\n📝 All input elements on page:")
        inputs = driver.find_elements(By.TAG_NAME, "input")
        print(f"Found {len(inputs)} input elements total")
        
        for i, inp in enumerate(inputs[:10]):  # Show first 10
            print(f"   {i+1}. Type: {inp.get_attribute('type')}, "
                  f"ID: {inp.get_attribute('id')}, "
                  f"Name: {inp.get_attribute('name')}, "
                  f"Placeholder: {inp.get_attribute('placeholder')}")
        
        # Check for any form elements
        print("\n📋 Form elements:")
        forms = driver.find_elements(By.TAG_NAME, "form")
        print(f"Found {len(forms)} form elements")
        
        # Look for buttons
        print("\n🔘 Button elements:")
        buttons = driver.find_elements(By.TAG_NAME, "button")
        print(f"Found {len(buttons)} button elements")
        
        for i, btn in enumerate(buttons[:5]):  # Show first 5
            text = btn.text.strip()
            if text:
                print(f"   {i+1}. Text: '{text}', ID: {btn.get_attribute('id')}, Class: {btn.get_attribute('class')}")
        
        # Save page source for further analysis
        with open('/Users/barreang/personal/ave-round-tripper/renfe_page_source.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"\n💾 Page source saved to renfe_page_source.html")
        
    except Exception as e:
        print(f"❌ Error analyzing website: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    analyze_renfe_website()
