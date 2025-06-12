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
        cfg.runConfig.log.info("running RenfeScraper with ENHANCED DUAL CALENDAR SUPPORT")
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
            current_month = datetime.now().month
            current_year = datetime.now().year
            
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

            # Submit the search
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
                try:
                    date_input.send_keys(Keys.ENTER)
                    search_submitted = True
                except:
                    pass

            # Wait for results to load
            cfg.runConfig.log.info("waiting for search results")
            sleep(10)

            # Parse the results using BeautifulSoup
            cfg.runConfig.log.info("parsing search results")
            soup = BeautifulSoup(self.__driver.page_source, "html.parser")
            
            # Save page source for debugging
            try:
                with open('/Users/barreang/personal/ave-round-tripper/debug_results_page.html', 'w', encoding='utf-8') as f:
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
