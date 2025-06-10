#!/usr/bin/env python3

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.keys import Keys
import time

def analyze_search_form():
    """Analyze the search form to understand how to properly interact with it"""
    
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
        print("🚂 Analyzing Renfe search form interaction...")
        driver.get("https://www.renfe.com/es/es")
        
        # Wait for page to load
        time.sleep(5)
        
        # Handle cookies
        try:
            cookie_button = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler"))
            )
            cookie_button.click()
            print("✅ Cookies accepted")
            time.sleep(2)
        except Exception as e:
            print(f"🍪 No cookie banner or already accepted: {e}")
        
        # Wait for and interact with origin field
        print("🔍 Testing origin field interaction...")
        try:
            origin = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "origin"))
            )
            print(f"   Origin field found, enabled: {origin.is_enabled()}, displayed: {origin.is_displayed()}")
            
            # Clear and type
            origin.clear()
            origin.send_keys("Madrid")
            time.sleep(1)
            
            # Check if dropdown appears
            try:
                dropdown = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".rf-input-autocomplete-alternative__dropdown, ul[role='listbox'], .autocomplete-dropdown"))
                )
                print("   ✅ Dropdown appeared")
                
                # Try to select first option
                first_option = dropdown.find_element(By.CSS_SELECTOR, "li:first-child, .option:first-child")
                first_option.click()
                print("   ✅ Selected first option from dropdown")
            except Exception as e:
                print(f"   ⚠️ No dropdown found, trying Keys.DOWN + Keys.ENTER: {e}")
                origin.send_keys(Keys.DOWN)
                origin.send_keys(Keys.ENTER)
                
        except Exception as e:
            print(f"❌ Error with origin field: {e}")
        
        time.sleep(2)
        
        # Test destination field
        print("🎯 Testing destination field interaction...")
        try:
            destination = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "destination"))
            )
            print(f"   Destination field found, enabled: {destination.is_enabled()}, displayed: {destination.is_displayed()}")
            
            destination.clear()
            destination.send_keys("Barcelona")
            time.sleep(1)
            
            # Check if dropdown appears
            try:
                dropdown = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".rf-input-autocomplete-alternative__dropdown, ul[role='listbox'], .autocomplete-dropdown"))
                )
                print("   ✅ Dropdown appeared")
                
                # Try to select first option
                first_option = dropdown.find_element(By.CSS_SELECTOR, "li:first-child, .option:first-child")
                first_option.click()
                print("   ✅ Selected first option from dropdown")
            except Exception as e:
                print(f"   ⚠️ No dropdown found, trying Keys.DOWN + Keys.ENTER: {e}")
                destination.send_keys(Keys.DOWN)
                destination.send_keys(Keys.ENTER)
                
        except Exception as e:
            print(f"❌ Error with destination field: {e}")
        
        time.sleep(2)
        
        # Test date field
        print("📅 Testing date field interaction...")
        try:
            date_field = WebDriverWait(driver, 20).until(
                EC.element_to_be_clickable((By.ID, "first-input"))
            )
            print(f"   Date field found, enabled: {date_field.is_enabled()}, displayed: {date_field.is_displayed()}")
            
            date_field.clear()
            date_field.send_keys("17/06/2025")
            time.sleep(2)
            print("   ✅ Date entered")
                
        except Exception as e:
            print(f"❌ Error with date field: {e}")
        
        # Test trip type (one way vs round trip)
        print("🎫 Testing trip type selection...")
        try:
            trip_go = driver.find_element(By.ID, "trip-go")
            print(f"   One-way radio found, selected: {trip_go.is_selected()}")
            if not trip_go.is_selected():
                trip_go.click()
                print("   ✅ Selected one-way trip")
        except Exception as e:
            print(f"❌ Error with trip type: {e}")
        
        # Look for search button
        print("🔍 Looking for search button...")
        search_selectors = [
            "button[type='submit']",
            ".search-button",
            ".rf-button",
            "button.mdc-button",
            "input[type='submit']",
            "button[data-testid='search']"
        ]
        
        search_button = None
        for selector in search_selectors:
            try:
                buttons = driver.find_elements(By.CSS_SELECTOR, selector)
                for btn in buttons:
                    if btn.is_displayed() and btn.is_enabled():
                        text = btn.text.lower()
                        if any(word in text for word in ['buscar', 'search', 'consultar']):
                            search_button = btn
                            print(f"   ✅ Found search button: {selector} - '{btn.text}'")
                            break
                if search_button:
                    break
            except Exception as e:
                pass
        
        if not search_button:
            print("   ⚠️ No obvious search button found. Looking for any button...")
            all_buttons = driver.find_elements(By.TAG_NAME, "button")
            for btn in all_buttons:
                try:
                    if btn.is_displayed() and btn.is_enabled():
                        text = btn.text.strip().lower()
                        if text and len(text) < 20:  # Reasonable button text length
                            print(f"      Button found: '{btn.text}' - Class: {btn.get_attribute('class')}")
                except:
                    pass
        
        # Try to submit if we found a button
        if search_button:
            print("🚀 Attempting to submit search...")
            try:
                search_button.click()
                time.sleep(5)
                print("   ✅ Search submitted, waiting for results...")
                
                # Look for results or error messages
                if "result" in driver.current_url.lower() or "train" in driver.page_source.lower():
                    print("   ✅ Appears to have navigated to results page")
                else:
                    print("   ⚠️ May not have reached results page")
                    
            except Exception as e:
                print(f"   ❌ Error submitting search: {e}")
        
        # Save final page source for analysis
        with open('/Users/barreang/personal/ave-round-tripper/renfe_search_analysis.html', 'w', encoding='utf-8') as f:
            f.write(driver.page_source)
        print(f"\n💾 Final page source saved to renfe_search_analysis.html")
        
    except Exception as e:
        print(f"❌ Error during analysis: {e}")
    finally:
        driver.quit()

if __name__ == "__main__":
    analyze_search_form()
