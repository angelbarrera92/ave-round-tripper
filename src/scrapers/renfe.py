from datetime import datetime
import re

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from src.config import RunConfig
from src.db.metadata import update_metadata
from src.db.models import Train
from src.scrapers.scraper import ScrapeConfig, Scraper, ScrapeResult

from time import sleep


class RenfeScraperConfig(ScrapeConfig):
    def __init__(self, runConfig: RunConfig, day: str, origin_station: str, destination_station: str, price_change_notification: bool) -> None:
        self.runConfig = runConfig
        self.day = day
        self.origin_station = origin_station
        self.destination_station = destination_station
        self.price_change_notification = price_change_notification


class RenfeScrapeResult(ScrapeResult):
    def __init__(self) -> None:
        self.tickets = list()

    def data(self):
        return self.tickets


class RenfeScraper(Scraper):

    def __init__(self) -> None:
        # Don't create driver in __init__ - create it fresh for each scrape
        self.__start_url = "https://www.renfe.com/es/es"
        self.__driver = None

    def __del__(self):
        try:
            self._cleanup_driver()
        except:
            pass

    def _cleanup_driver(self):
        """Safely cleanup the WebDriver instance"""
        if self.__driver:
            try:
                # Close all windows first
                for handle in self.__driver.window_handles:
                    self.__driver.switch_to.window(handle)
                    self.__driver.close()
            except:
                pass
            
            try:
                # Quit the driver
                self.__driver.quit()
            except:
                pass
            
            try:
                # Force close any remaining browser processes from this driver
                if hasattr(self.__driver, 'service') and hasattr(self.__driver.service, 'process'):
                    process = self.__driver.service.process
                    if process and process.poll() is None:
                        process.terminate()
                        # Wait a moment for graceful shutdown
                        import time
                        time.sleep(1)
                        if process.poll() is None:
                            process.kill()
            except:
                pass
            
            finally:
                self.__driver = None

    def _create_driver(self):
        """Create a fresh Chrome driver instance"""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1080,1080")
        chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        
        # Use webdriver-manager for automatic ChromeDriver management
        service = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=chrome_options)

    def scrape(self, cfg: RenfeScraperConfig) -> RenfeScrapeResult:
        cfg.runConfig.log.info("running RenfeScraper with ENHANCED DUAL CALENDAR SUPPORT")
        cfg.runConfig.log.debug("configuration:")
        cfg.runConfig.log.debug(
            f"day: {cfg.day} | origin_station: {cfg.origin_station} | destination_station: {cfg.destination_station}")
        result = RenfeScrapeResult()
        
        # Create a fresh driver for each scrape to avoid session issues
        cfg.runConfig.log.debug("creating fresh browser instance")
        if self.__driver:
            try:
                self.__driver.quit()
            except:
                pass
        self.__driver = self._create_driver()
        
        try:
            self.__driver.get(self.__start_url)
            cfg.runConfig.log.info("waiting for the page to load")
            sleep(5)

            # Handle cookies consent
            cfg.runConfig.log.debug("handling cookie consent")
            try:
                cookie_button = WebDriverWait(self.__driver, 10).until(
                    expected_conditions.element_to_be_clickable((By.ID, "onetrust-accept-btn-handler")))
                cookie_button.click()
                cfg.runConfig.log.debug("cookies accepted")
                sleep(2)
            except Exception as e:
                cfg.runConfig.log.debug(f"no cookie banner found or already accepted: {e}")

            # Wait for the search form to be ready
            cfg.runConfig.log.info("waiting for the search form to appear")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.element_to_be_clickable((By.ID, "origin")))

            cfg.runConfig.log.info("filling up input fields")
            
            # Select the origin station
            cfg.runConfig.log.debug("selecting the origin station")
            origin = WebDriverWait(self.__driver, 10).until(
                expected_conditions.element_to_be_clickable((By.ID, "origin")))
            
            # Clear field and enter origin
            self.__driver.execute_script("arguments[0].value = '';", origin)
            origin.send_keys(cfg.origin_station)
            sleep(2)
            
            # Try to select from dropdown
            try:
                dropdown_option = WebDriverWait(self.__driver, 5).until(
                    expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, ".rf-input-autocomplete-alternative__dropdown li:first-child")))
                dropdown_option.click()
                cfg.runConfig.log.debug("selected origin from dropdown")
            except:
                cfg.runConfig.log.debug("no dropdown found, using keyboard navigation")
                origin.send_keys(Keys.DOWN)
                origin.send_keys(Keys.ENTER)
            
            sleep(1)

            # Select the destination station
            cfg.runConfig.log.debug("selecting the destination station")
            destination = WebDriverWait(self.__driver, 10).until(
                expected_conditions.element_to_be_clickable((By.ID, "destination")))
            
            # Clear field and enter destination
            self.__driver.execute_script("arguments[0].value = '';", destination)
            destination.send_keys(cfg.destination_station)
            sleep(2)
            
            # Try to select from dropdown
            try:
                dropdown_option = WebDriverWait(self.__driver, 5).until(
                    expected_conditions.element_to_be_clickable((By.CSS_SELECTOR, ".rf-input-autocomplete-alternative__dropdown li:first-child")))
                dropdown_option.click()
                cfg.runConfig.log.debug("selected destination from dropdown")
            except:
                cfg.runConfig.log.debug("no dropdown found, using keyboard navigation")
                destination.send_keys(Keys.DOWN)
                destination.send_keys(Keys.ENTER)
            
            sleep(1)

            # SKIP Solo IDA selection - testing shows it's not required for departure trains
            cfg.runConfig.log.debug("skipping Solo IDA selection - not required for departure trains")

            # ENHANCED DUAL CALENDAR DATE SELECTION
            cfg.runConfig.log.info("🗓️ STARTING ENHANCED DUAL CALENDAR DATE SELECTION")
            
            # Re-find the date input to ensure we have fresh reference
            date_input = WebDriverWait(self.__driver, 10).until(
                expected_conditions.element_to_be_clickable((By.ID, "first-input")))
            
            # Check current value before any changes
            initial_value = date_input.get_attribute('value')
            cfg.runConfig.log.debug(f"initial date input value: '{initial_value}'")
            
            # Parse the target date
            try:
                target_date_obj = datetime.strptime(cfg.day, "%d/%m/%Y")
                target_day = target_date_obj.day
                target_month = target_date_obj.month
                target_year = target_date_obj.year
                cfg.runConfig.log.info(f"🎯 target date: day={target_day}, month={target_month}, year={target_year}")
            except ValueError as e:
                cfg.runConfig.log.error(f"could not parse date format {cfg.day}: {e}")
                raise
            
            # Click to open the calendar
            cfg.runConfig.log.debug("clicking date input to open calendar")
            date_input.click()
            sleep(3)  # Increased wait time for calendar to fully load
            
            # Wait for calendar to appear
            try:
                calendar = WebDriverWait(self.__driver, 15).until(
                    expected_conditions.visibility_of_element_located((By.CSS_SELECTOR, ".lightpick")))
                cfg.runConfig.log.debug("✅ calendar opened successfully")
                sleep(2)  # Additional wait for calendar to stabilize
            except Exception as e:
                cfg.runConfig.log.error(f"❌ calendar did not open: {e}")
                raise
            
            # DUAL CALENDAR NAVIGATION LOGIC
            # Spanish month names for matching
            spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                            'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            target_month_spanish = spanish_months[target_month - 1]
            
            cfg.runConfig.log.info(f"🔍 looking for month: {target_month_spanish} {target_year}")
            
            def get_displayed_months():
                """Returns info about the two displayed months in the dual calendar"""
                month_info = []
                try:
                    # Try multiple selectors to find month titles
                    month_selectors = [
                        ".lightpick__month-title-text", 
                        ".lightpick__month-title", 
                        ".lightpick .lightpick__month .lightpick__month-title"
                    ]
                    
                    for selector in month_selectors:
                        month_elements = self.__driver.find_elements(By.CSS_SELECTOR, selector)
                        cfg.runConfig.log.debug(f"found {len(month_elements)} elements with selector: {selector}")
                        
                        if len(month_elements) >= 1:
                            for elem in month_elements:
                                text = elem.text.strip()
                                if text:
                                    month_info.append({
                                        'text': text,
                                        'element': elem
                                    })
                                    cfg.runConfig.log.debug(f"found month: {text}")
                            break
                    
                    # Alternative: look for calendar containers
                    if len(month_info) < 2:
                        cfg.runConfig.log.debug("trying alternative calendar container search")
                        containers = self.__driver.find_elements(By.CSS_SELECTOR, ".lightpick__months .lightpick__month")
                        for container in containers:
                            try:
                                title_elem = container.find_element(By.CSS_SELECTOR, ".lightpick__month-title-text, .lightpick__month-title")
                                if title_elem and title_elem.text.strip():
                                    month_info.append({
                                        'text': title_elem.text.strip(),
                                        'element': title_elem,
                                        'container': container
                                    })
                            except:
                                continue
                    
                except Exception as e:
                    cfg.runConfig.log.debug(f"error getting displayed months: {e}")
                
                return month_info
            
            # Navigate to target month if needed
            max_navigation_attempts = 15  # Prevent infinite loops
            navigation_attempts = 0
            
            while navigation_attempts < max_navigation_attempts:
                displayed_months = get_displayed_months()
                month_texts = [m['text'] for m in displayed_months]
                cfg.runConfig.log.debug(f"📅 displayed months: {month_texts}")
                
                # Check if target month is visible in either of the two calendars
                target_month_visible = False
                
                for i, month_info in enumerate(displayed_months):
                    month_text = month_info['text'].lower()
                    if target_month_spanish.lower() in month_text and str(target_year) in month_text:
                        target_month_visible = True
                        cfg.runConfig.log.info(f"✅ target month {target_month_spanish} {target_year} found in calendar {i}: {month_text}")
                        break
                
                if target_month_visible:
                    break
                
                # Determine navigation direction
                # Dual calendar shows 2 consecutive months side by side
                # Navigation buttons move by 2 months at a time
                if len(displayed_months) >= 1:
                    first_month_text = displayed_months[0]['text'].lower()
                    
                    # Extract month number from first displayed month
                    first_month_num = None
                    for i, spanish_month in enumerate(spanish_months):
                        if spanish_month.lower() in first_month_text:
                            first_month_num = i + 1
                            break
                    
                    if first_month_num is not None:
                        # If we have 2 months displayed, second month is first_month_num + 1
                        second_month_num = first_month_num + 1 if first_month_num < 12 else 1
                        
                        cfg.runConfig.log.debug(f"current view shows months {first_month_num} and {second_month_num}, target is {target_month}")
                        
                        # Check if target month is in the range of currently displayed months
                        if target_month == first_month_num or target_month == second_month_num:
                            cfg.runConfig.log.debug("target month should be visible, but wasn't found - continuing anyway")
                            break
                        elif target_month > second_month_num:
                            # Navigate forward
                            cfg.runConfig.log.debug(f"➡️ navigating forward: target {target_month} > displayed {second_month_num}")
                            try:
                                next_button = self.__driver.find_element(By.CSS_SELECTOR, ".lightpick__next-action")
                                next_button.click()
                                sleep(2)
                            except Exception as e:
                                cfg.runConfig.log.debug(f"error clicking next button: {e}")
                                break
                        elif target_month < first_month_num:
                            # Navigate backward
                            cfg.runConfig.log.debug(f"⬅️ navigating backward: target {target_month} < displayed {first_month_num}")
                            try:
                                prev_button = self.__driver.find_element(By.CSS_SELECTOR, ".lightpick__previous-action")
                                prev_button.click()
                                sleep(2)
                            except Exception as e:
                                cfg.runConfig.log.debug(f"error clicking previous button: {e}")
                                break
                        else:
                            cfg.runConfig.log.debug("target month should be visible but search failed")
                            break
                    else:
                        cfg.runConfig.log.debug("could not determine current month from display")
                        break
                else:
                    cfg.runConfig.log.debug("no displayed months found")
                    break
                
                navigation_attempts += 1
            
            if navigation_attempts >= max_navigation_attempts:
                cfg.runConfig.log.warning("⚠️ reached maximum navigation attempts, proceeding with current view")
            
            # ENHANCED DAY SELECTION FOR DUAL CALENDAR
            cfg.runConfig.log.info(f"🎯 looking for day {target_day} in dual calendar")
            
            # Get all day elements from both calendars
            day_elements = self.__driver.find_elements(By.CSS_SELECTOR, ".lightpick__day")
            cfg.runConfig.log.debug(f"found {len(day_elements)} day elements in dual calendar")
            
            day_clicked = False
            
            # Strategy 1: Look for target day in the correct month calendar
            try:
                # Find the calendar containers
                calendar_containers = self.__driver.find_elements(By.CSS_SELECTOR, ".lightpick__months .lightpick__month")
                cfg.runConfig.log.debug(f"found {len(calendar_containers)} calendar containers")
                
                for container_index, container in enumerate(calendar_containers):
                    try:
                        # Get the month title for this container
                        title_selectors = [".lightpick__month-title-text", ".lightpick__month-title"]
                        title_elem = None
                        
                        for selector in title_selectors:
                            try:
                                title_elem = container.find_element(By.CSS_SELECTOR, selector)
                                break
                            except:
                                continue
                        
                        if not title_elem:
                            continue
                            
                        month_title = title_elem.text.strip().lower()
                        cfg.runConfig.log.debug(f"calendar {container_index} shows: {month_title}")
                        
                        # Check if this is our target month
                        if target_month_spanish.lower() in month_title and str(target_year) in month_title:
                            cfg.runConfig.log.info(f"✅ found target month calendar at index {container_index}")
                            
                            # Get day elements from this specific calendar container
                            container_days = container.find_elements(By.CSS_SELECTOR, ".lightpick__day")
                            cfg.runConfig.log.debug(f"found {len(container_days)} days in target calendar")
                            
                            for day_elem in container_days:
                                day_text = day_elem.text.strip()
                                day_classes = day_elem.get_attribute('class')
                                is_enabled = 'is-disabled' not in day_classes
                                is_current_month = 'is-previous-month' not in day_classes and 'is-next-month' not in day_classes
                                
                                if day_text == str(target_day) and is_enabled and is_current_month:
                                    cfg.runConfig.log.info(f"🎯 found target day {target_day} in correct calendar, classes: {day_classes}")
                                    try:
                                        # Scroll into view if needed
                                        self.__driver.execute_script("arguments[0].scrollIntoView(true);", day_elem)
                                        sleep(0.5)
                                        
                                        # Try clicking
                                        day_elem.click()
                                        sleep(2)
                                        day_clicked = True
                                        cfg.runConfig.log.info(f"✅ successfully clicked on day {target_day} in correct calendar")
                                        break
                                    except Exception as e:
                                        cfg.runConfig.log.debug(f"failed to click day {target_day} in correct calendar: {e}")
                            
                            if day_clicked:
                                break
                            
                    except Exception as e:
                        cfg.runConfig.log.debug(f"error processing calendar container {container_index}: {e}")
                        continue
                        
            except Exception as e:
                cfg.runConfig.log.debug(f"error with calendar container approach: {e}")
            
            # Strategy 2: Fallback - try any enabled day with target number
            if not day_clicked:
                cfg.runConfig.log.debug("🔄 fallback: trying any enabled day with target number")
                for i, day_elem in enumerate(day_elements):
                    day_text = day_elem.text.strip()
                    day_classes = day_elem.get_attribute('class')
                    is_enabled = 'is-disabled' not in day_classes
                    
                    if day_text == str(target_day) and is_enabled:
                        cfg.runConfig.log.debug(f"trying enabled day {target_day} at index {i}, classes: {day_classes}")
                        try:
                            self.__driver.execute_script("arguments[0].scrollIntoView(true);", day_elem)
                            sleep(0.5)
                            day_elem.click()
                            sleep(2)
                            day_clicked = True
                            cfg.runConfig.log.info(f"✅ clicked day {target_day} as fallback")
                            break
                        except Exception as e:
                            cfg.runConfig.log.debug(f"failed to click day {target_day} as fallback: {e}")
            
            # Strategy 3: JavaScript direct date setting
            if not day_clicked:
                cfg.runConfig.log.debug("🔧 using JavaScript fallback to set date")
                try:
                    self.__driver.execute_script("""
                        arguments[0].value = arguments[1];
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        arguments[0].blur();
                    """, date_input, cfg.day)
                    cfg.runConfig.log.info("✅ set date using JavaScript fallback")
                    day_clicked = True
                except Exception as e:
                    cfg.runConfig.log.warning(f"❌ JavaScript fallback also failed: {e}")
            
            # Try to close calendar by clicking apply button or outside
            cfg.runConfig.log.debug("attempting to close calendar")
            try:
                # Look for apply/accept buttons
                apply_selectors = [
                    ".lightpick__apply-action",
                    ".lightpick__apply",
                    "button[class*='apply']"
                ]
                
                apply_button_found = False
                for selector in apply_selectors:
                    try:
                        buttons = self.__driver.find_elements(By.CSS_SELECTOR, selector)
                        for button in buttons:
                            if button.is_displayed() and button.is_enabled():
                                button.click()
                                apply_button_found = True
                                cfg.runConfig.log.debug("clicked apply button")
                                break
                        if apply_button_found:
                            break
                    except:
                        continue
                
                if not apply_button_found:
                    # Click outside to close
                    self.__driver.find_element(By.TAG_NAME, "body").click()
                    cfg.runConfig.log.debug("clicked outside to close calendar")
                
                sleep(2)
            except:
                pass
            
            # Verify the date was set correctly
            final_value = date_input.get_attribute('value')
            cfg.runConfig.log.info(f"📅 final date input value: '{final_value}'")
            
            # Report final status
            if day_clicked:
                cfg.runConfig.log.info(f"✅ DUAL CALENDAR DATE SELECTION COMPLETED for {target_day}")
            else:
                cfg.runConfig.log.warning(f"⚠️ could not select day {target_day} in calendar")

            # Scroll to the top of the page to ensure submit button is visible
            cfg.runConfig.log.debug("scrolling to the top of the page")
            self.__driver.execute_script("window.scrollTo(0, 0);")
            sleep(1) # Give a moment for the scroll to complete

            # Save screenshot before attempting to submit
            self.__driver.save_screenshot("debug_before_submit.png")
            cfg.runConfig.log.info("Saved screenshot: debug_before_submit.png")

            # Submit the search - ENHANCED SEARCH BUTTON DETECTION
            cfg.runConfig.log.info("submitting the search form - ENHANCED DETECTION")
            
            # First, let's find ALL buttons and log them for debugging
            all_buttons = self.__driver.find_elements(By.TAG_NAME, "button")
            cfg.runConfig.log.info(f"Found {len(all_buttons)} buttons on the page")
            
            for i, btn in enumerate(all_buttons):
                try:
                    btn_text = btn.text.strip()
                    btn_id = btn.get_attribute('id')
                    btn_class = btn.get_attribute('class')
                    btn_type = btn.get_attribute('type')
                    is_displayed = btn.is_displayed()
                    is_enabled = btn.is_enabled()
                    cfg.runConfig.log.debug(f"Button {i}: text='{btn_text}', id='{btn_id}', class='{btn_class}', type='{btn_type}', displayed={is_displayed}, enabled={is_enabled}")
                except Exception as e:
                    cfg.runConfig.log.debug(f"Error inspecting button {i}: {e}")
            
            # Enhanced search button selectors
            search_button_selectors = [
                "button[type='submit']",
                "button:contains('Buscar')",
                "button:contains('BUSCAR')",
                "*[class*='search']",
                "*[class*='buscar']",
                "*[id*='search']",
                "*[id*='buscar']",
                ".rf-button",
                "button.mdc-button",
                "button[data-testid*='search']",
                "[role='button']",
                "input[type='submit']"
            ]
            
            search_submitted = False
            
            # Strategy 1: Try enhanced selectors
            for selector in search_button_selectors:
                try:
                    elements = self.__driver.find_elements(By.CSS_SELECTOR, selector)
                    cfg.runConfig.log.debug(f"Selector '{selector}' found {len(elements)} elements")
                    
                    for element in elements:
                        try:
                            if element.is_displayed() and element.is_enabled():
                                element_text = element.text.lower().strip()
                                element_value = element.get_attribute('value')
                                if element_value:
                                    element_value = element_value.lower().strip()
                                
                                cfg.runConfig.log.debug(f"Checking element: text='{element_text}', value='{element_value}'")
                                
                                # Check if this looks like a search button
                                search_keywords = ['buscar', 'search', 'consultar', 'enviar', 'submit']
                                if (any(word in element_text for word in search_keywords) or 
                                    (element_value and any(word in element_value for word in search_keywords))):
                                    
                                    cfg.runConfig.log.info(f"Attempting to click search element with text='{element_text}', value='{element_value}'")
                                    
                                    # Scroll into view and click
                                    self.__driver.execute_script("arguments[0].scrollIntoView(true);", element)
                                    sleep(0.5)
                                    
                                    # Try multiple click methods
                                    try:
                                        element.click()
                                        cfg.runConfig.log.info("✅ Successfully clicked with standard click")
                                        search_submitted = True
                                        break
                                    except:
                                        try:
                                            self.__driver.execute_script("arguments[0].click();", element)
                                            cfg.runConfig.log.info("✅ Successfully clicked with JavaScript click")
                                            search_submitted = True
                                            break
                                        except Exception as e:
                                            cfg.runConfig.log.debug(f"Both click methods failed: {e}")
                        except Exception as e:
                            cfg.runConfig.log.debug(f"Error checking element: {e}")
                    
                    if search_submitted:
                        break
                        
                except Exception as e:
                    cfg.runConfig.log.debug(f"Selector '{selector}' failed: {e}")
            
            # Strategy 2: Try clicking any button that looks like search
            if not search_submitted:
                cfg.runConfig.log.debug("🔄 Strategy 2: Trying any button that looks like search")
                for i, btn in enumerate(all_buttons):
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            btn_text = btn.text.lower().strip()
                            btn_value = btn.get_attribute('value') or ""
                            btn_value = btn_value.lower().strip()
                            
                            search_keywords = ['buscar', 'search', 'consultar', 'enviar']
                            if (any(word in btn_text for word in search_keywords) or 
                                any(word in btn_value for word in search_keywords)):
                                
                                cfg.runConfig.log.info(f"Strategy 2: Attempting button {i} with text='{btn_text}'")
                                try:
                                    self.__driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                                    sleep(0.5)
                                    btn.click()
                                    search_submitted = True
                                    cfg.runConfig.log.info("✅ Strategy 2 successful")
                                    break
                                except:
                                    try:
                                        self.__driver.execute_script("arguments[0].click();", btn)
                                        search_submitted = True
                                        cfg.runConfig.log.info("✅ Strategy 2 successful with JS click")
                                        break
                                    except Exception as e:
                                        cfg.runConfig.log.debug(f"Strategy 2 button {i} failed: {e}")
                    except Exception as e:
                        cfg.runConfig.log.debug(f"Strategy 2 error with button {i}: {e}")
            
            # Strategy 3: Try form submission
            if not search_submitted:
                cfg.runConfig.log.debug("🔄 Strategy 3: Trying form submission")
                try:
                    forms = self.__driver.find_elements(By.TAG_NAME, "form")
                    cfg.runConfig.log.debug(f"Found {len(forms)} forms")
                    
                    for i, form in enumerate(forms):
                        try:
                            cfg.runConfig.log.debug(f"Trying to submit form {i}")
                            form.submit()
                            search_submitted = True
                            cfg.runConfig.log.info("✅ Strategy 3: Form submission successful")
                            break
                        except Exception as e:
                            cfg.runConfig.log.debug(f"Form {i} submission failed: {e}")
                except Exception as e:
                    cfg.runConfig.log.debug(f"Strategy 3 failed: {e}")
            
            # Strategy 4: Try pressing Enter on various form fields
            if not search_submitted:
                cfg.runConfig.log.debug("🔄 Strategy 4: Trying Enter key on form fields")
                field_ids = ["first-input", "origin", "destination"]
                
                for field_id in field_ids:
                    try:
                        field = self.__driver.find_element(By.ID, field_id)
                        if field.is_displayed() and field.is_enabled():
                            cfg.runConfig.log.debug(f"Trying Enter on field: {field_id}")
                            field.send_keys(Keys.ENTER)
                            search_submitted = True
                            cfg.runConfig.log.info(f"✅ Strategy 4: Enter successful on {field_id}")
                            break
                    except Exception as e:
                        cfg.runConfig.log.debug(f"Strategy 4 failed on {field_id}: {e}")
            
            if not search_submitted:
                cfg.runConfig.log.error("All attempts to submit the search form failed.")
                # Save screenshot and page source if submission failed
                self.__driver.save_screenshot("debug_submit_failed.png")
                with open('debug_submit_failed.html', 'w', encoding='utf-8') as f:
                    f.write(self.__driver.page_source)
                cfg.runConfig.log.info("Saved screenshot: debug_submit_failed.png and page source: debug_submit_failed.html")
                # Return empty result (cleanup will happen in finally block)
            else:
                # Wait for results to load and verify navigation
                cfg.runConfig.log.info("waiting for search results and verifying navigation")
                
                # Check current URL to see if we've navigated away from the search page
                current_url = self.__driver.current_url
                cfg.runConfig.log.info(f"Current URL after submit attempt: {current_url}")
                
                # Wait for potential page navigation or results to load
                initial_wait = 5
                cfg.runConfig.log.debug(f"Initial wait of {initial_wait} seconds for navigation")
                sleep(initial_wait)
                
                # Check if URL changed (indicating navigation to results page)
                new_url = self.__driver.current_url
                if new_url != current_url:
                    cfg.runConfig.log.info(f"✅ Page navigated! New URL: {new_url}")
                    # Give more time for results to load after navigation
                    sleep(8)
                else:
                    cfg.runConfig.log.warning(f"⚠️ No navigation detected. Still on: {new_url}")
                    # Try waiting a bit more in case it's a slow response
                    cfg.runConfig.log.debug("Waiting additional time in case of slow response")
                    sleep(10)
                    
                    # Check URL again
                    final_url = self.__driver.current_url
                    if final_url != current_url:
                        cfg.runConfig.log.info(f"✅ Late navigation detected! Final URL: {final_url}")
                    else:
                        cfg.runConfig.log.error(f"❌ No navigation occurred. Form submission likely failed.")
                
                # Look for indicators that we're on a results page
                results_indicators = [
                    ".selectedTren",  # Train results
                    "[class*='result']",  # Generic results
                    "[class*='tren']",  # Spanish for train
                    "[class*='viaje']",  # Spanish for journey
                    ".train-option",
                    ".journey-option"
                ]
                
                results_found = False
                for indicator in results_indicators:
                    try:
                        elements = self.__driver.find_elements(By.CSS_SELECTOR, indicator)
                        if elements:
                            cfg.runConfig.log.info(f"✅ Found {len(elements)} result elements with selector: {indicator}")
                            results_found = True
                            break
                    except:
                        continue
                
                if not results_found:
                    cfg.runConfig.log.warning("⚠️ No result indicators found on current page")
                
                self.__driver.save_screenshot("debug_after_submit_attempt.png")
                cfg.runConfig.log.info("Saved screenshot: debug_after_submit_attempt.png")
                with open('debug_after_submit_attempt.html', 'w', encoding='utf-8') as f:
                    f.write(self.__driver.page_source)
                cfg.runConfig.log.info("Saved page source: debug_after_submit_attempt.html")


                # Parse the results using BeautifulSoup
                cfg.runConfig.log.info("parsing search results")
                soup = BeautifulSoup(self.__driver.page_source, "html.parser")
                
                # Save page source for debugging
                try:
                    with open('debug_results_page_renfe.html', 'w', encoding='utf-8') as f:
                        f.write(self.__driver.page_source)
                except:
                    pass
                
                # Look for train entries
                train_elements = soup.find_all('div', class_='selectedTren')
                cfg.runConfig.log.info(f"found {len(train_elements)} train entries")
                
                for train_element in train_elements:
                    trayecto = {}
                    
                    # Extract departure and arrival times from h5 elements
                    time_elements = train_element.find_all('h5', {'aria-hidden': 'true'})
                    if len(time_elements) >= 2:
                        departure_text = time_elements[0].get_text().strip()
                        arrival_text = time_elements[-1].get_text().strip()
                        
                        # Extract time from text like "17:57 h"
                        dep_match = re.search(r'(\d{1,2}:\d{2})', departure_text)
                        arr_match = re.search(r'(\d{1,2}:\d{2})', arrival_text)
                        
                        if dep_match and arr_match:
                            trayecto["salida"] = dep_match.group(1)
                            trayecto["llegada"] = arr_match.group(1)
                    
                    # Extract train type from image alt text
                    train_img = train_element.find('img', alt=re.compile(r'Tipo de tren', re.IGNORECASE))
                    if train_img:
                        alt_text = train_img.get('alt', '')
                        train_type_match = re.search(r'Tipo de tren (\w+)', alt_text, re.IGNORECASE)
                        if train_type_match:
                            trayecto["tipo"] = train_type_match.group(1).upper()
                    
                    # Extract price from precio-final span
                    price_element = train_element.find('span', class_='precio-final')
                    if price_element:
                        price_text = price_element.get_text().strip()
                        price_match = re.search(r'([\d,]+(?:\.\d{2})?)\s*€', price_text)
                        if price_match:
                            price_str = price_match.group(1).replace(',', '.')
                            trayecto["prices"] = [price_str + ' €']
                    
                    # Only add if we have at least departure time
                    if "salida" in trayecto:
                        cfg.runConfig.log.info(f"parsed train: {trayecto}")
                        result.tickets.append(trayecto)

        except WebDriverException as ex:
            cfg.runConfig.log.error(f"error while parsing renfe results. {ex}.")
            if ex.msg == "invalid session id":
                cfg.runConfig.log.error("invalid session id. Probably the session has expired. Exiting")
                raise ex
        except Exception as ex:
            cfg.runConfig.log.error(f"error while parsing renfe results: {ex}. Continuing...")
        finally:
            # Clean up driver after each scrape to prevent session issues
            cfg.runConfig.log.debug("cleaning up browser instance")
            try:
                self._cleanup_driver()
            except:
                pass
        return result

    def save(self, cfg: RenfeScraperConfig, result: RenfeScrapeResult) -> None:
        date = datetime.strptime(cfg.day, "%d/%m/%Y")
        for d in result.data():
            alert = False
            priceChanged = False
            oldPrice = 0
            newPrice = 0

            salida = d.get("salida")
            salida_dt = datetime.strptime(salida, '%H:%M')
            departure_date = date.replace(
                hour=salida_dt.hour, minute=salida_dt.minute, second=0, microsecond=0)
            departure_timestamp = int(datetime.timestamp(departure_date))

            llegada = d.get("llegada")
            llegada_dt = datetime.strptime(llegada, '%H:%M')
            arrival_date = date.replace(
                hour=llegada_dt.hour, minute=llegada_dt.minute, second=0, microsecond=0)
            arrival_timestamp = int(datetime.timestamp(arrival_date))

            kind = d.get("tipo")

            prices = d.get("prices", list())
            price = lower_price(prices)

            t = cfg.runConfig.db.session.query(Train).get(
                (cfg.origin_station, departure_timestamp, cfg.destination_station, arrival_timestamp))
            if t:
                if t.price != price:
                    alert = True
                    priceChanged = True
                    oldPrice = t.price
                    newPrice = price
                t.price = price
            else:
                t = Train(departure_timestamp, cfg.origin_station,
                          cfg.destination_station, price, arrival_timestamp, kind)
                t.departure_date = departure_date
                t.arrival_date = arrival_date
                alert = True
                newPrice = price
                priceChanged = False

            if alert and cfg.price_change_notification:
                targetDateStr = datetime.strftime(date, "%A %d/%m/%Y")
                if not newPrice:
                    cfg.runConfig.notification.send(
                        f"⚠️⚠️⚠️⚠️ {targetDateStr} {kind} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. No available.")
                elif not oldPrice:
                    cfg.runConfig.notification.send(
                        f"►►►► {targetDateStr} {kind} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. {newPrice}€")
                elif priceChanged and newPrice < oldPrice:
                    cfg.runConfig.notification.send(
                        f"↓↓↓↓ {targetDateStr} {kind} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. From {oldPrice}€ to {newPrice}€")
                elif priceChanged and newPrice > oldPrice:
                    cfg.runConfig.notification.send(
                        f"↑↑↑↑ {targetDateStr} {kind} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. From {oldPrice}€ to {newPrice}€")

            cfg.runConfig.db.session.add(t)
        cfg.runConfig.db.session.commit()
        update_metadata(cfg.runConfig.db, Train.__tablename__)


def lower_price(prices):
    prices_as_floats = list()
    if len(prices) > 0:
        for price in prices:
            # Keep digits, commas, and decimal points
            price_as_float = "".join(
                i for i in price if i.isdigit() or i == "," or i == ".")
            if price_as_float:
                # Handle both European (comma) and US (dot) decimal formats
                # If there's both comma and dot, assume comma is thousands separator
                if "," in price_as_float and "." in price_as_float:
                    # Format like "1,234.56" - remove comma (thousands separator)
                    price_as_float = price_as_float.replace(",", "")
                else:
                    # Format like "24,23" - replace comma with dot for decimal
                    price_as_float = price_as_float.replace(",", ".")
                
                price_as_float = float(price_as_float)
                prices_as_floats.append(price_as_float)
    if len(prices_as_floats) > 0:
        return sorted(prices_as_floats)[0]
    return None
