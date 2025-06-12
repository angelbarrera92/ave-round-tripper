from datetime import datetime
import re

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (NoSuchElementException,
                                        StaleElementReferenceException,
                                        WebDriverException)
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
        chrome_options = Options()
        # chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1080,1080")
        
        # Use webdriver-manager for automatic ChromeDriver management
        service = Service(ChromeDriverManager().install())
        self.__driver = webdriver.Chrome(service=service, options=chrome_options)
        self.__start_url = "https://www.renfe.com/es/es"

    def __del__(self):
        try:
            self.__driver.quit()
        except:
            pass

    def scrape(self, cfg: RenfeScraperConfig) -> RenfeScrapeResult:
        cfg.runConfig.log.info("running RenfeScraper")
        cfg.runConfig.log.debug("configuration:")
        cfg.runConfig.log.debug(
            f"day: {cfg.day} | origin_station: {cfg.origin_station} | destination_station: {cfg.destination_station}")
        result = RenfeScrapeResult()
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

            # SECOND: Now select the date (the main focus)
            cfg.runConfig.log.debug("selecting the travel date")
            
            # Re-find the date input to ensure we have fresh reference
            date_input = WebDriverWait(self.__driver, 10).until(
                expected_conditions.element_to_be_clickable((By.ID, "first-input")))
            
            # Check current value before any changes
            initial_value = date_input.get_attribute('value')
            cfg.runConfig.log.debug(f"initial date input value: '{initial_value}'")
            
            # Parse the target date
            from datetime import datetime
            try:
                target_date_obj = datetime.strptime(cfg.day, "%d/%m/%Y")
                target_day = target_date_obj.day
                target_month = target_date_obj.month
                target_year = target_date_obj.year
                cfg.runConfig.log.debug(f"parsed target date: day={target_day}, month={target_month}, year={target_year}")
            except ValueError as e:
                cfg.runConfig.log.error(f"could not parse date format {cfg.day}: {e}")
                raise
            
            # Click to open the calendar
            cfg.runConfig.log.debug("clicking date input to open calendar")
            date_input.click()
            sleep(2)
            
            # Wait for calendar to appear
            try:
                calendar = WebDriverWait(self.__driver, 10).until(
                    expected_conditions.visibility_of_element_located((By.CSS_SELECTOR, ".lightpick")))
                cfg.runConfig.log.debug("calendar opened successfully")
            except Exception as e:
                cfg.runConfig.log.error(f"calendar did not open: {e}")
                raise
            
            # NEW DUAL CALENDAR HANDLING LOGIC
            current_month = datetime.now().month
            current_year = datetime.now().year
            
            # Calculate months difference accounting for year changes
            months_diff = (target_year - current_year) * 12 + (target_month - current_month)
            
            cfg.runConfig.log.debug(f"navigating from {current_month}/{current_year} to {target_month}/{target_year} (diff: {months_diff} months)")
            
            # Spanish month names for matching
            spanish_months = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 
                            'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']
            target_month_spanish = spanish_months[target_month - 1]
            
            # Get current displayed months (dual calendar shows 2 months)
            def get_displayed_months():
                """Returns info about the two displayed months in the dual calendar"""
                month_info = []
                try:
                    # Look for all month title elements (should be 2 in dual calendar)
                    month_selectors = [
                        ".lightpick__month-title-text", 
                        ".lightpick__month-title", 
                        ".lightpick .lightpick__month"
                    ]
                    
                    for selector in month_selectors:
                        month_elements = self.__driver.find_elements(By.CSS_SELECTOR, selector)
                        if len(month_elements) >= 1:
                            for elem in month_elements:
                                if elem.text.strip():
                                    month_info.append({
                                        'text': elem.text.strip(),
                                        'element': elem
                                    })
                            break
                    
                    # If we didn't get 2 months, try to find calendar containers
                    if len(month_info) < 2:
                        cfg.runConfig.log.debug("looking for individual calendar containers")
                        calendar_containers = self.__driver.find_elements(By.CSS_SELECTOR, ".lightpick__months-container .lightpick__month")
                        for container in calendar_containers:
                            title_elem = container.find_element(By.CSS_SELECTOR, ".lightpick__month-title-text, .lightpick__month-title")
                            if title_elem and title_elem.text.strip():
                                month_info.append({
                                    'text': title_elem.text.strip(),
                                    'element': title_elem,
                                    'container': container
                                })
                    
                except Exception as e:
                    cfg.runConfig.log.debug(f"error getting displayed months: {e}")
                
                return month_info
            
            # Navigate to target month if needed
            max_navigation_attempts = 12  # Prevent infinite loops
            navigation_attempts = 0
            
            while navigation_attempts < max_navigation_attempts:
                displayed_months = get_displayed_months()
                cfg.runConfig.log.debug(f"displayed months: {[m['text'] for m in displayed_months]}")
                
                # Check if target month is visible in either of the two calendars
                target_month_visible = False
                target_calendar_index = None
                
                for i, month_info in enumerate(displayed_months):
                    month_text = month_info['text'].lower()
                    if target_month_spanish.lower() in month_text and str(target_year) in month_text:
                        target_month_visible = True
                        target_calendar_index = i
                        cfg.runConfig.log.debug(f"✅ target month {target_month_spanish} {target_year} found in calendar {i}: {month_text}")
                        break
                
                if target_month_visible:
                    break
                
                # Determine navigation direction
                if len(displayed_months) >= 1:
                    first_month_text = displayed_months[0]['text'].lower()
                    
                    # Extract month from first displayed month to compare
                    first_month_num = None
                    for i, spanish_month in enumerate(spanish_months):
                        if spanish_month.lower() in first_month_text:
                            first_month_num = i + 1
                            break
                    
                    if first_month_num is not None:
                        # Calculate if we need to go forward or backward
                        # Note: dual calendar shows 2 consecutive months, so navigation jumps by 2
                        if target_month > first_month_num + 1:  # +1 because dual calendar shows current+1
                            # Navigate forward
                            cfg.runConfig.log.debug(f"navigating forward: target month {target_month} > first displayed {first_month_num}")
                            try:
                                next_button = self.__driver.find_element(By.CSS_SELECTOR, ".lightpick__next-action")
                                next_button.click()
                                sleep(2)
                            except Exception as e:
                                cfg.runConfig.log.debug(f"error clicking next button: {e}")
                                break
                        elif target_month < first_month_num:
                            # Navigate backward
                            cfg.runConfig.log.debug(f"navigating backward: target month {target_month} < first displayed {first_month_num}")
                            try:
                                prev_button = self.__driver.find_element(By.CSS_SELECTOR, ".lightpick__previous-action")
                                prev_button.click()
                                sleep(2)
                            except Exception as e:
                                cfg.runConfig.log.debug(f"error clicking previous button: {e}")
                                break
                        else:
                            # We should be able to see the target month, but didn't find it
                            cfg.runConfig.log.debug(f"target month {target_month} should be visible but wasn't found")
                            break
                    else:
                        cfg.runConfig.log.debug("could not determine current month from display")
                        break
                else:
                    cfg.runConfig.log.debug("no displayed months found")
                    break
                
                navigation_attempts += 1
            
            if navigation_attempts >= max_navigation_attempts:
                cfg.runConfig.log.warning("reached maximum navigation attempts, proceeding with current view")
            
            
            # ENHANCED DAY SELECTION FOR DUAL CALENDAR
            cfg.runConfig.log.debug(f"looking for day {target_day} in dual calendar")
            
            # Get all day elements from both calendars
            day_elements = self.__driver.find_elements(By.CSS_SELECTOR, ".lightpick__day")
            cfg.runConfig.log.debug(f"found {len(day_elements)} day elements in dual calendar")
            
            day_clicked = False
            
            # Strategy 1: Look for target day in the correct month calendar
            # First, identify which calendar contains our target month
            target_calendar_days = []
            
            try:
                # Find the calendar containers
                calendar_containers = self.__driver.find_elements(By.CSS_SELECTOR, ".lightpick__months-container .lightpick__month")
                
                for container_index, container in enumerate(calendar_containers):
                    try:
                        # Get the month title for this container
                        title_elem = container.find_element(By.CSS_SELECTOR, ".lightpick__month-title-text, .lightpick__month-title")
                        month_title = title_elem.text.strip().lower()
                        
                        cfg.runConfig.log.debug(f"calendar {container_index} shows: {month_title}")
                        
                        # Check if this is our target month
                        if target_month_spanish.lower() in month_title and str(target_year) in month_title:
                            cfg.runConfig.log.debug(f"✅ found target month calendar at index {container_index}")
                            
                            # Get day elements from this specific calendar container
                            container_days = container.find_elements(By.CSS_SELECTOR, ".lightpick__day")
                            
                            for day_elem in container_days:
                                day_text = day_elem.text.strip()
                                day_classes = day_elem.get_attribute('class')
                                is_enabled = 'is-disabled' not in day_classes
                                is_current_month = 'is-previous-month' not in day_classes and 'is-next-month' not in day_classes
                                
                                if day_text == str(target_day) and is_enabled and is_current_month:
                                    cfg.runConfig.log.debug(f"found target day {target_day} in correct calendar, classes: {day_classes}")
                                    try:
                                        # Scroll into view if needed
                                        self.__driver.execute_script("arguments[0].scrollIntoView(true);", day_elem)
                                        sleep(0.5)
                                        
                                        # Try clicking
                                        day_elem.click()
                                        sleep(2)
                                        day_clicked = True
                                        cfg.runConfig.log.debug(f"✅ successfully clicked on day {target_day} in correct calendar")
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
            
            # Strategy 2: Fallback - look through all day elements with better logic
            if not day_clicked:
                cfg.runConfig.log.debug("fallback: searching all day elements with improved logic")
                
                # Group day elements by their parent calendar
                day_groups = {}
                for i, day_elem in enumerate(day_elements):
                    try:
                        # Find the parent calendar container
                        parent_calendar = day_elem.find_element(By.XPATH, "./ancestor::div[contains(@class, 'lightpick__month')]")
                        parent_title_elem = parent_calendar.find_element(By.CSS_SELECTOR, ".lightpick__month-title-text, .lightpick__month-title")
                        parent_title = parent_title_elem.text.strip().lower()
                        
                        if parent_title not in day_groups:
                            day_groups[parent_title] = []
                        day_groups[parent_title].append((i, day_elem))
                        
                    except:
                        # If we can't determine parent, add to a generic group
                        if 'unknown' not in day_groups:
                            day_groups['unknown'] = []
                        day_groups['unknown'].append((i, day_elem))
                
                cfg.runConfig.log.debug(f"grouped days by calendar: {list(day_groups.keys())}")
                
                # Look for target day in the correct month group first
                for group_title, day_list in day_groups.items():
                    if target_month_spanish.lower() in group_title and str(target_year) in group_title:
                        cfg.runConfig.log.debug(f"searching in target month group: {group_title}")
                        
                        for day_index, day_elem in day_list:
                            day_text = day_elem.text.strip()
                            day_classes = day_elem.get_attribute('class')
                            is_enabled = 'is-disabled' not in day_classes
                            is_current_month = 'is-previous-month' not in day_classes and 'is-next-month' not in day_classes
                            
                            if day_text == str(target_day) and is_enabled:
                                cfg.runConfig.log.debug(f"found target day {target_day} in correct group at index {day_index}, classes: {day_classes}")
                                try:
                                    # Scroll into view
                                    self.__driver.execute_script("arguments[0].scrollIntoView(true);", day_elem)
                                    sleep(0.5)
                                    
                                    # Try clicking
                                    day_elem.click()
                                    sleep(2)
                                    day_clicked = True
                                    cfg.runConfig.log.debug(f"✅ successfully clicked day {target_day} from grouped search")
                                    break
                                except Exception as e:
                                    cfg.runConfig.log.debug(f"failed to click day {target_day} from grouped search: {e}")
                        
                        if day_clicked:
                            break
            
            # Strategy 3: Last resort - try any enabled day with target number
            if not day_clicked:
                cfg.runConfig.log.debug("last resort: trying any enabled day with target number")
                for i, day_elem in enumerate(day_elements):
                    day_text = day_elem.text.strip()
                    day_classes = day_elem.get_attribute('class')
                    is_enabled = 'is-disabled' not in day_classes
                    
                    if day_text == str(target_day) and is_enabled:
                        cfg.runConfig.log.debug(f"trying any enabled day {target_day} at index {i}, classes: {day_classes}")
                        try:
                            self.__driver.execute_script("arguments[0].scrollIntoView(true);", day_elem)
                            sleep(0.5)
                            day_elem.click()
                            sleep(2)
                            day_clicked = True
                            cfg.runConfig.log.debug(f"✅ clicked day {target_day} as last resort")
                            break
                        except Exception as e:
                            cfg.runConfig.log.debug(f"failed to click day {target_day} as last resort: {e}")
            
            # Final fallback: JavaScript direct date setting
            if not day_clicked:
                cfg.runConfig.log.debug("all day clicking strategies failed, using JavaScript fallback")
                try:
                    self.__driver.execute_script("""
                        arguments[0].value = arguments[1];
                        arguments[0].dispatchEvent(new Event('input', { bubbles: true }));
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        arguments[0].blur();
                    """, date_input, cfg.day)
                    cfg.runConfig.log.debug("set date using JavaScript fallback")
                    day_clicked = True  # Consider this successful for continuation
                except Exception as e:
                    cfg.runConfig.log.warning(f"JavaScript fallback also failed: {e}")
            
            # Report final status
            if day_clicked:
                cfg.runConfig.log.debug(f"✅ day selection completed for {target_day}")
            else:
                cfg.runConfig.log.warning(f"⚠️ could not select day {target_day} in calendar")
            
            # Now look for and click the "Aceptar" button to confirm the date selection
            cfg.runConfig.log.debug("looking for 'Aceptar' button to confirm date selection")
            accept_button_found = False
            
            # Try multiple selectors for the accept button
            accept_selectors = [
                "button:contains('Aceptar')",
                ".lightpick__apply",
                ".lightpick__apply-action",
                "[class*='apply']",
                "button[class*='apply']",
                ".calendar-apply",
                ".date-apply",
                ".rf-daterange-alternative button",
                "button:contains('Accept')",
                "button:contains('OK')"
            ]
            
            for selector in accept_selectors:
                try:
                    # For :contains selector, we need to use XPath
                    if ":contains(" in selector:
                        text = selector.split("'")[1]  # Extract text from :contains('text')
                        element_type = selector.split(":")[0]
                        xpath = f"//{element_type}[contains(text(), '{text}')]"
                        accept_buttons = self.__driver.find_elements(By.XPATH, xpath)
                    else:
                        accept_buttons = self.__driver.find_elements(By.CSS_SELECTOR, selector)
                    
                    for button in accept_buttons:
                        if button.is_displayed() and button.is_enabled():
                            cfg.runConfig.log.debug(f"found accept button with selector: {selector}, text: '{button.text}'")
                            try:
                                button.click()
                                sleep(2)
                                accept_button_found = True
                                cfg.runConfig.log.debug("successfully clicked accept button")
                                break
                            except Exception as e:
                                cfg.runConfig.log.debug(f"failed to click accept button: {e}")
                    
                    if accept_button_found:
                        break
                        
                except Exception as e:
                    cfg.runConfig.log.debug(f"error with selector {selector}: {e}")
                    continue
            
            if not accept_button_found:
                cfg.runConfig.log.debug("could not find accept button, trying to close calendar by clicking outside")
                try:
                    # Click outside the calendar to close it
                    self.__driver.find_element(By.TAG_NAME, "body").click()
                    sleep(1)
                except:
                    pass
            
            # Verify the date was set correctly
            final_value = date_input.get_attribute('value')
            cfg.runConfig.log.debug(f"final date input value: '{final_value}'")
            
            # Enhanced date validation
            date_validation_passed = False
            
            # Check if the final value contains our target day
            if str(target_day) in final_value:
                cfg.runConfig.log.debug(f"✅ date contains target day {target_day}")
                
                # More rigorous validation: check if it contains target month and year
                target_month_str = f"{target_month:02d}"  # e.g., "09" for September
                target_year_str = str(target_year)[-2:]   # e.g., "25" for 2025
                
                if target_month_str in final_value and target_year_str in final_value:
                    cfg.runConfig.log.debug(f"✅ date appears correct: contains {target_day}, {target_month_str}, {target_year_str}")
                    date_validation_passed = True
                elif target_month_str in final_value:
                    cfg.runConfig.log.debug(f"✅ date contains correct month {target_month_str}")
                    date_validation_passed = True
                else:
                    cfg.runConfig.log.warning(f"⚠️ date might be wrong: expected month {target_month_str}, year {target_year_str} in '{final_value}'")
            else:
                cfg.runConfig.log.warning(f"⚠️ date selection may have failed: expected day {target_day}, got '{final_value}'")
            
            # If validation failed, try one more time with direct JavaScript
            if not date_validation_passed:
                cfg.runConfig.log.debug("attempting emergency date correction with JavaScript")
                try:
                    self.__driver.execute_script("""
                        var dateInput = arguments[0];
                        var targetDate = arguments[1];
                        dateInput.value = targetDate;
                        dateInput.dispatchEvent(new Event('input', { bubbles: true }));
                        dateInput.dispatchEvent(new Event('change', { bubbles: true }));
                        dateInput.blur();
                    """, date_input, cfg.day)
                    
                    sleep(1)
                    emergency_value = date_input.get_attribute('value')
                    cfg.runConfig.log.debug(f"emergency correction result: '{emergency_value}'")
                except Exception as e:
                    cfg.runConfig.log.debug(f"emergency correction failed: {e}")

            # Submit the search - try multiple possible search button selectors
            cfg.runConfig.log.info("submitting the search form")
            search_button_selectors = [
                "button[type='submit']",
                ".search-button", 
                ".rf-button",
                "button.mdc-button",
                "button[data-testid*='search']"
            ]
            
            search_submitted = False
            for selector in search_button_selectors:
                try:
                    buttons = self.__driver.find_elements(By.CSS_SELECTOR, selector)
                    for button in buttons:
                        if button.is_displayed() and button.is_enabled():
                            button_text = button.text.lower()
                            if any(word in button_text for word in ['buscar', 'search', 'consultar']):
                                button.click()
                                search_submitted = True
                                cfg.runConfig.log.debug(f"clicked search button: {selector}")
                                break
                    if search_submitted:
                        break
                except Exception as e:
                    cfg.runConfig.log.debug(f"selector {selector} failed: {e}")
            
            if not search_submitted:
                # Fallback: try pressing Enter on the date field
                cfg.runConfig.log.debug("trying Enter key as fallback")
                date_input.send_keys(Keys.ENTER)
                search_submitted = True

            # Wait for results to load
            cfg.runConfig.log.info("waiting for search results")
            sleep(10)  # Give time for navigation and loading
            
            # Check if we're on a results page or if results loaded
            current_url = self.__driver.current_url
            page_source = self.__driver.page_source.lower()
            
            if "resultado" in current_url or "result" in current_url or "train" in page_source or "tren" in page_source:
                cfg.runConfig.log.info("search results page detected")
            else:
                cfg.runConfig.log.warning("may not be on results page, will attempt to parse anyway")

            # Parse the results using BeautifulSoup
            cfg.runConfig.log.info("parsing search results")
            soup = BeautifulSoup(self.__driver.page_source, "html.parser")
            
            # Save page source for debugging
            with open('/Users/barreang/personal/ave-round-tripper/debug_results_page.html', 'w', encoding='utf-8') as f:
                f.write(self.__driver.page_source)
            
            # Look for train entries - updated to match current RENFE structure
            train_elements = soup.find_all('div', class_='selectedTren')
            
            cfg.runConfig.log.info(f"found {len(train_elements)} train entries")
            
            for train_element in train_elements:
                trayecto = {}
                
                # Extract departure and arrival times from h5 elements
                time_elements = train_element.find_all('h5', {'aria-hidden': 'true'})
                if len(time_elements) >= 2:
                    # First h5 is departure, last h5 is arrival
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
                    # Extract train type from alt text like "Imagen de Tren. Tipo de tren AVE"
                    train_type_match = re.search(r'Tipo de tren (\w+)', alt_text, re.IGNORECASE)
                    if train_type_match:
                        trayecto["tipo"] = train_type_match.group(1).upper()
                
                # Extract duration from aria-label
                duration_span = train_element.find('span', {'aria-label': re.compile(r'Duración', re.IGNORECASE)})
                if duration_span:
                    duration_text = duration_span.get('aria-label', '')
                    # Extract duration from text like "Duración 2 horas 37 minutos."
                    duration_match = re.search(r'(\d+)\s+horas?\s+(\d+)\s+minutos?', duration_text, re.IGNORECASE)
                    if duration_match:
                        hours = duration_match.group(1)
                        minutes = duration_match.group(2)
                        trayecto["duracion"] = f"{hours}h {minutes}min"
                    else:
                        # Try simpler pattern
                        duration_match = re.search(r'(\d+)\s+horas?', duration_text, re.IGNORECASE)
                        if duration_match:
                            trayecto["duracion"] = f"{duration_match.group(1)}h"
                
                # Extract price from precio-final span
                price_element = train_element.find('span', class_='precio-final')
                if price_element:
                    price_text = price_element.get_text().strip()
                    # Extract price from text like "Precio desde 104,20 €"
                    price_match = re.search(r'([\d,]+(?:\.\d{2})?)\s*€', price_text)
                    if price_match:
                        price_str = price_match.group(1).replace(',', '.')
                        trayecto["prices"] = [price_str + ' €']
                
                # Only add if we have at least departure time
                if "salida" in trayecto:
                    cfg.runConfig.log.info(f"parsed train: {trayecto}")
                    result.tickets.append(trayecto)
                else:
                    cfg.runConfig.log.debug(f"skipping train element - no departure time found: {train_element.get_text()[:100]}...")
            
            # Fallback: if no trains found with new method, try old method
            if not result.tickets:
                cfg.runConfig.log.warning("no trains found with new parser, trying fallback method")
                
                # Look for any elements containing train time patterns
                all_elements = soup.find_all(string=lambda text: text and ':' in text)
                parent_elements = set()
                for element in all_elements:
                    if element.parent and ':' in element and len(element.strip()) <= 6:
                        # This looks like a time, add its parent container
                        parent_elements.add(element.parent.parent if element.parent.parent else element.parent)
                train_elements = list(parent_elements)
                
                cfg.runConfig.log.info(f"fallback method found {len(train_elements)} potential train entries")
                
                for train_element in train_elements:
                    trayecto = {}
                    
                    element_text = train_element.get_text()
                    
                    # Extract times (departure and arrival)
                    time_pattern = r'\b\d{1,2}[:\.]\d{2}\b'
                    times = re.findall(time_pattern, element_text)
                    
                    if len(times) >= 2:
                        trayecto["salida"] = times[0].replace('.', ':')
                        trayecto["llegada"] = times[-1].replace('.', ':')
                    
                    # Extract train type
                    train_types = ['AVE', 'AVLO', 'ALVIA', 'INTERCITY', 'CERCANIAS']
                    for train_type in train_types:
                        if train_type.lower() in element_text.lower():
                            trayecto["tipo"] = train_type
                            break
                    
                    # Extract duration
                    duration_pattern = r'\b\d+h\s*\d*m?i?n?\b'
                    duration_match = re.search(duration_pattern, element_text)
                    if duration_match:
                        trayecto["duracion"] = duration_match.group()
                    
                    # Extract prices
                    price_pattern = r'\b\d+[,\.]\d{0,2}\s*€'
                    price_matches = re.findall(price_pattern, element_text)
                    if price_matches:
                        trayecto["prices"] = [price.strip() for price in price_matches]
                    
                    # Only add if we have at least departure time
                    if "salida" in trayecto:
                        cfg.runConfig.log.info(f"fallback parsed train: {trayecto}")
                        
                        # Check for duplicate times
                        if len(result.tickets) > 0:
                            last_ticket = result.tickets[-1]
                            if (last_ticket.get("salida") == trayecto.get("salida") and 
                                last_ticket.get("llegada") == trayecto.get("llegada")):
                                cfg.runConfig.log.debug("found duplicate departure/arrival times, merging prices")
                                if "prices" in trayecto:
                                    last_ticket.setdefault("prices", []).extend(trayecto["prices"])
                            else:
                                result.tickets.append(trayecto)
                        else:
                            result.tickets.append(trayecto)

        except WebDriverException as ex:
            cfg.runConfig.log.error(f"error while parsing renfe results. {ex}.")
            if ex.msg == "invalid session id":
                cfg.runConfig.log.error(
                    "invalid session id. Probably the session has expired. Exiting")
                raise ex
        except Exception as ex:
            cfg.runConfig.log.error(f"error while parsing renfe results: {ex}. Continuing...")
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
            price_as_float = "".join(
                i for i in price if i.isdigit() or i == ",")
            if price_as_float:
                price_as_float = float(price_as_float.replace(",", "."))
                prices_as_floats.append(price_as_float)
    if len(prices_as_floats) > 0:
        return sorted(prices_as_floats)[0]
    return None
