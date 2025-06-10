from datetime import datetime

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

            # Set one way travel (if not already selected)
            cfg.runConfig.log.debug("ensuring one way travel is selected")
            try:
                trip_go = self.__driver.find_element(By.ID, "trip-go")
                if not trip_go.is_selected():
                    trip_go.click()
                    sleep(1)
                    cfg.runConfig.log.debug("selected one-way travel")
            except Exception as e:
                cfg.runConfig.log.debug(f"could not set one-way travel: {e}")

            # Select the date
            cfg.runConfig.log.debug("selecting the travel date")
            date_input = WebDriverWait(self.__driver, 10).until(
                expected_conditions.element_to_be_clickable((By.ID, "first-input")))
            
            # Clear and enter date
            self.__driver.execute_script("arguments[0].value = '';", date_input)
            date_input.send_keys(cfg.day)
            sleep(2)

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
            
            import re
            
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
