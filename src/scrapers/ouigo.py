import re
import traceback
from datetime import datetime
from time import sleep

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

from src.config import RunConfig
from src.db.metadata import update_metadata
from src.db.models import Train
from src.scrapers.scraper import ScrapeConfig, Scraper, ScrapeResult


class OuigoScraperConfig(ScrapeConfig):
    def __init__(self, runConfig: RunConfig, day: str, origin_station: str, destination_station: str, price_change_notification: bool) -> None:
        self.runConfig = runConfig
        self.day = day
        self.origin_station = origin_station
        self.destination_station = destination_station
        self.price_change_notification = price_change_notification


class OuigoScrapeResult(ScrapeResult):
    def __init__(self) -> None:
        self.tickets = list()

    def data(self):
        return self.tickets


class OuigoScraper(Scraper):

    def __init__(self) -> None:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=400,1000")
        chrome_options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64; rv:109.0) Gecko/20100101 Firefox/109.0")
        self.__driver = webdriver.Chrome(options=chrome_options)
        self.__start_url = "https://www.ouigo.com/es/"

    def __del__(self):
        try:
            self.__driver.quit()
        except:
            pass

    def scrape(self, cfg: OuigoScraperConfig) -> OuigoScrapeResult:
        cfg.runConfig.log.info("running OuigoScraper")
        cfg.runConfig.log.debug("configuration:")
        cfg.runConfig.log.debug(
            f"day: {cfg.day} | origin_station: {cfg.origin_station} | destination_station: {cfg.destination_station}")
        result = OuigoScrapeResult()
        try:
            self.__driver.get(self.__start_url)

            # Waiting for the spage to be loaded
            cfg.runConfig.log.debug(
                "waiting for the page to be loaded")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.presence_of_element_located((By.ID, "search_submit")))

            try:
                cfg.runConfig.log.debug("accepting all cookies")
                cookies = self.__driver.find_element(By.ID, "didomi-notice-agree-button")

                cookies.click()
            except NoSuchElementException as ex:
                cfg.runConfig.log.warn(
                    "seems like cookies has been already accepted")

            cfg.runConfig.log.info("filling up input fields")
            cfg.runConfig.log.debug("selecting the origin station")
            origin = self.__driver.find_element(By.ID, "select2-edit-departure-station-container")
            origin.click()
            originInput = self.__driver.find_element(By.CLASS_NAME, "select2-search__field")
            originInput.send_keys(cfg.origin_station)
            originInput.send_keys(Keys.ENTER)

            destination = self.__driver.find_element(By.ID, "select2-edit-arrival-station-container")
            destination.click()
            destinationInput = self.__driver.find_element(By.CLASS_NAME, "select2-search__field")
            destinationInput.send_keys(cfg.destination_station)
            destinationInput.send_keys(Keys.ENTER)


            # Set the date
            cfg.runConfig.log.debug(f"setting the date to {cfg.day}")
            # Execute document.getElementById("edit-start-date").value = "02/03/2023"
            self.__driver.execute_script(f"document.getElementById('edit-start-date').value = '{cfg.day}';")

            # Scroll a few pixels to make the button visible
            self.__driver.execute_script("window.scrollBy(0, 150);")


            # Search for the trains
            cfg.runConfig.log.debug("searching for the trains")
            search = self.__driver.find_element(
                By.ID, "search_submit")
            search.click()

            # Trains table. Parsing
            cfg.runConfig.log.info("waiting for results")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.presence_of_element_located((By.XPATH, "/html/body/div[2]/div/main/div/section/div[4]/div/section/div/div/ul[2]")))

            soup = BeautifulSoup(self.__driver.page_source, "html.parser")
            # Get the ul element with the attribute role=tabpanel
            searchResults = soup.find_all(role="tabpanel")
            if len(searchResults) != 1:
                cfg.runConfig.log.error("No results found")
                raise ValueError("No results found")

            searchResults = searchResults[0]
            # Every train info is in a button element
            trainButtons = searchResults.find_all("button")
            for trainButton in trainButtons:
                # An example textContent for a trainButton is: '10:05Madrid - Puerta de Atocha - Almudena Grandes11:22Zaragoza - Delicias15€1h17Mejor precio'
                # Parse the textContent. The time is always specified as hh:mm. There are two times, the departure and the arrival
                # Scrape it using regex
                trayecto = {}
                timePattern = re.compile(r"(\d{2}:\d{2})")
                times = timePattern.findall(trainButton.text)
                if len(times) != 2:
                    cfg.runConfig.log.error("Error parsing the times")
                    raise ValueError("Error parsing the times")
                departureTime = times[0]
                arrivalTime = times[1]
                cfg.runConfig.log.info(f"Train found: {departureTime} - {arrivalTime}")
                # The price is always specified as a number followed by €
                pricePattern = re.compile(r"(\d+)€")
                price = pricePattern.findall(trainButton.text)
                if len(price) != 1:
                    cfg.runConfig.log.error("Error parsing the price")
                    raise ValueError("Error parsing the price")
                price = f"{price[0]}€"
                cfg.runConfig.log.info(f"Price: {price}")
                # We can calculate the duration by subtracting the arrival time from the departure time
                duration = datetime.strptime(arrivalTime, "%H:%M") - datetime.strptime(departureTime, "%H:%M")
                # Represent the duration as a string in the format xh:xm (e.g. 1h:30m)
                duration = f"{duration.seconds // 3600}h:{(duration.seconds // 60) % 60}m"
                cfg.runConfig.log.info(f"Duration: {duration}")

                trayecto["salida"] = departureTime
                trayecto["duracion"] = duration
                trayecto["llegada"] = arrivalTime
                trayecto["tipo"] = "Ouigo"
                trayecto["prices"] = [price]
                cfg.runConfig.log.info(f"trayecto: {trayecto}")
                result.tickets.append(trayecto)
        except WebDriverException as ex:
            # Print the stack trace
            cfg.runConfig.log.error(f"error while parsing Ouigo results: {ex}.")
            traceback.print_exc()
            if ex.msg == "invalid session id":
                cfg.runConfig.log.error(
                    "invalid session id. Probably the session has expired. Exiting")
                raise ex
        except Exception as ex:
            cfg.runConfig.log.error(
                f"error while parsing Ouigo results: {ex}. Continuing...")
        return result

    def save(self, cfg: OuigoScraperConfig, result: OuigoScrapeResult) -> None:
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
