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


class IryoScraperConfig(ScrapeConfig):
    def __init__(self, runConfig: RunConfig, day: str, origin_station: str, destination_station: str, price_change_notification: bool) -> None:
        self.runConfig = runConfig
        self.day = day
        self.origin_station = origin_station
        self.destination_station = destination_station
        self.price_change_notification = price_change_notification


class IryoScrapeResult(ScrapeResult):
    def __init__(self) -> None:
        self.tickets = list()

    def data(self):
        return self.tickets


class IryoScraper(Scraper):

    def __init__(self) -> None:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--window-size=400,1000")
        self.__driver = webdriver.Chrome(options=chrome_options)
        self.__start_url = "https://iryo.eu/es/home"

    def __del__(self):
        try:
            self.__driver.quit()
        except:
            pass

    def scrape(self, cfg: IryoScraperConfig) -> IryoScrapeResult:
        cfg.runConfig.log.info("running IryoScraper")
        cfg.runConfig.log.debug("configuration:")
        cfg.runConfig.log.debug(
            f"day: {cfg.day} | origin_station: {cfg.origin_station} | destination_station: {cfg.destination_station}")
        result = IryoScrapeResult()
        try:
            self.__driver.get(self.__start_url)

            # Waiting for the spage to be loaded
            cfg.runConfig.log.debug(
                "waiting for the page to be loaded")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.presence_of_element_located((By.XPATH, "/html/body/app-root/main/b2c-main-header/ilsa-header/header/div/div/div[2]/div[3]/label")))

            try:
                cfg.runConfig.log.debug("accepting all cookies")
                cookies = self.__driver.find_element(
                    By.XPATH, "/html/body/app-root/main/app-cookies-manager/ilsa-cookies-cta/div/div[2]/ilsa-button[1]/div/button/span")

                cookies.click()
            except NoSuchElementException as ex:
                cfg.runConfig.log.warn(
                    "seems like cookies has been already accepted")

            cfg.runConfig.log.info("filling up input fields")
            cfg.runConfig.log.debug("selecting the origin station")
            origin = self.__driver.find_element(
                By.XPATH, "/html/body/app-root/main/b2c-view-home/div[2]/section/div/div[1]/b2c-main-search/ilsa-main-search/div/div/ilsa-select-route/div/div[2]/div[1]/ilsa-dropdown/div[1]/div")
            text = ""
            option = 1
            while cfg.origin_station.lower() not in text.lower():
                cfg.runConfig.log.debug(f"current origin station: {text}")
                origin.click()
                for _ in range(option):
                    origin.send_keys(Keys.DOWN)
                origin.send_keys(Keys.ENTER)
                origin.send_keys(Keys.ENTER)
                if text == origin.text:
                    raise ValueError(
                        f"origin station {cfg.origin_station} not found")
                text = origin.text
                cfg.runConfig.log.debug(f"origin station: {text}")
                option += 1

            destination = self.__driver.find_element(
                By.XPATH, "/html/body/app-root/main/b2c-view-home/div[2]/section/div/div[1]/b2c-main-search/ilsa-main-search/div/div/ilsa-select-route/div/div[2]/div[2]/ilsa-dropdown/div[1]/div")
            text = ""
            option = 1
            while cfg.destination_station.lower() not in text.lower():
                cfg.runConfig.log.debug(f"current destination station: {text}")
                destination.click()
                for _ in range(option):
                    destination.send_keys(Keys.DOWN)
                destination.send_keys(Keys.ENTER)
                destination.send_keys(Keys.ENTER)
                if text == destination.text:
                    raise ValueError(
                        f"destination station {cfg.destination_station} not found")
                text = destination.text
                cfg.runConfig.log.debug(f"destination station: {text}")
                option += 1

            # Set one way travel
            cfg.runConfig.log.debug("setting one way travel")
            oneway = self.__driver.find_element(
                By.XPATH, "/html/body/app-root/main/b2c-view-home/div[2]/section/div/div[1]/b2c-main-search/ilsa-main-search/div/div/div[1]/div[2]/ilsa-radio/div[1]/label/span[1]")
            oneway.click()

            # Set the date
            cfg.runConfig.log.debug("setting the date")
            dateInput = self.__driver.find_element(
                By.XPATH, "/html/body/app-root/main/b2c-view-home/div[2]/section/div/div[1]/b2c-main-search/ilsa-main-search/div/div/ilsa-datepicker/div[1]/div/div[1]/input")
            dateInput.click()
            dateInput.send_keys(cfg.day)
            dateInput.send_keys(Keys.ENTER)
            oneway.click()

            # Search for the trains
            cfg.runConfig.log.debug("searching for the trains")
            search = self.__driver.find_element(
                By.XPATH, "/html/body/app-root/main/b2c-view-home/div[2]/section/div/div[1]/b2c-main-search/ilsa-main-search/div/div/ilsa-button/div/button")
            search.click()

            # Trains table. Parsing
            cfg.runConfig.log.info("waiting for results")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.presence_of_element_located((By.XPATH, "/html/body/app-root/main/b2c-view-travels/div/ilsa-schedules/section/ilsa-tabs/div/div/div[2]/ilsa-tabs-tab/div/ilsa-schedule/div[1]")))

            soup = BeautifulSoup(self.__driver.page_source, "html.parser")
            resultLists = soup.find_all(class_="ilsa-schedule__row--content")
            if len(resultLists) != 1:
                cfg.runConfig.log.error("No results found")
                raise ValueError("No results found")
            resultList = resultLists[0]
            resultRows = resultList.find_all(class_="ilsa-schedule__row")
            for resultRow in resultRows:
                trayecto = {}
                # Log the train
                cfg.runConfig.log.info("Train found")
                # cfg.runConfig.log.debug(resultRow)
                # The date is in the inner div class ilsa-schedule__group-date
                dateGroup = resultRow.find(class_="ilsa-schedule__group-date")
                times = dateGroup.find_all(
                    class_="ilsa-schedule__group-date-hour")
                # The first time is the departure time
                departureTime = times[0].text.strip()
                # The second time is the arrival time
                arrivalTime = times[1].text.strip()
                cfg.runConfig.log.debug(f"departure time: {departureTime}")
                cfg.runConfig.log.debug(f"arrival time: {arrivalTime}")
                duration = resultRow.find(
                    class_="ilsa-schedule__group-date-total").text.strip()
                cfg.runConfig.log.debug(f"duration: {duration}")
                # prices
                prices = resultRow.find_all(
                    class_="ilsa-schedule__tarrif-wrapper")
                offerings = list()
                for price in prices:
                    # Get the price using a regex, the price format is like this: 12,34 €. Include the €
                    priceText = price.text.strip()
                    cfg.runConfig.log.debug(f"price: {priceText}")
                    priceRegex = re.compile(r"(\d+,\d+)")
                    priceMatch = priceRegex.search(priceText)
                    if priceMatch is None:
                        cfg.runConfig.log.error("No price found")
                        raise ValueError("No price found")
                    price = priceMatch.group(1) + " €"
                    cfg.runConfig.log.debug(f"price: {price}")
                    offerings.append(price)
                cfg.runConfig.log.info("Train parsed")
                cfg.runConfig.log.debug("Offerings:")
                cfg.runConfig.log.debug(offerings)

                trayecto["salida"] = departureTime
                trayecto["duracion"] = duration
                trayecto["llegada"] = arrivalTime
                trayecto["tipo"] = "Iryo"
                trayecto["prices"] = offerings
                cfg.runConfig.log.info(f"trayecto: {trayecto}")
                result.tickets.append(trayecto)

        except WebDriverException as ex:
            # Print the stack trace
            cfg.runConfig.log.error(f"error while parsing Iryo results: {ex}.")
            traceback.print_exc()
            if ex.msg == "invalid session id":
                cfg.runConfig.log.error(
                    "invalid session id. Probably the session has expired. Exiting")
                raise ex
        except Exception as ex:
            cfg.runConfig.log.error(
                f"error while parsing Iryo results: {ex}. Continuing...")
        return result

    def save(self, cfg: IryoScraperConfig, result: IryoScrapeResult) -> None:
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
                        f"⚠️⚠️⚠️⚠️ {targetDateStr} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. No available.")
                elif not oldPrice:
                    cfg.runConfig.notification.send(
                        f"►►►► {targetDateStr} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. {newPrice}€")
                elif priceChanged and newPrice < oldPrice:
                    cfg.runConfig.notification.send(
                        f"↓↓↓↓ {targetDateStr} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. From {oldPrice}€ to {newPrice}€")
                elif priceChanged and newPrice > oldPrice:
                    cfg.runConfig.notification.send(
                        f"↑↑↑↑ {targetDateStr} {cfg.origin_station}-{cfg.destination_station} {salida}-{llegada}. From {oldPrice}€ to {newPrice}€")

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
