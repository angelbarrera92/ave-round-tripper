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
from src.config import RunConfig
from src.db.metadata import update_metadata
from src.db.models import Train
from src.scrapers.scraper import ScrapeConfig, Scraper, ScrapeResult


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
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-infobars")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--window-size=1080,1080")
        self.__driver = webdriver.Chrome(options=chrome_options)
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

            # Waiting for the date picker to appear on screen
            cfg.runConfig.log.debug(
                "waiting for the date picker to appear on screen")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.presence_of_element_located((By.ID, "first-input")))

            try:
                cfg.runConfig.log.debug("accepting all cookies")
                self.__driver.find_element(
                    By.ID, "onetrust-accept-btn-handler").click()
            except NoSuchElementException as ex:
                cfg.runConfig.log.warn(
                    "seems like cookies has been already accepted")
            cfg.runConfig.log.info("filling up input fields")
            cfg.runConfig.log.debug("selecting the origin station")
            # Select the origin station
            origin = self.__driver.find_element(By.XPATH, "/html/body/div[1]/div/div/div[1]/div/div/div/div/div/div/rf-header/rf-header-top/div/div[2]/rf-search/div/div[1]/rf-awesomplete[1]/div/div[1]/input")
            origin.clear()
            origin.send_keys(cfg.origin_station)
            origin.send_keys(Keys.DOWN)
            origin.send_keys(Keys.ENTER)

            # Set one way travel
            cfg.runConfig.log.debug("setting one way travel")
            tripType = self.__driver.find_element(By.ID, "tripType")
            tripTypeButton = tripType.find_element(By.TAG_NAME, "button")
            tripTypeButton.click()

            tripTypeButtonPopUp = tripType.find_element(By.TAG_NAME, "ul")
            tripTypeButtonPopUpButtons = tripTypeButtonPopUp.find_elements(By.TAG_NAME,
                                                                           "button")
            for b in tripTypeButtonPopUpButtons:
                # Solo ida
                if "lo ida" in b.get_attribute("innerText"):
                    b.click()

            # Set the destination station
            cfg.runConfig.log.debug("selecting the destination station")
            destination = self.__driver.find_element(By.XPATH, "/html/body/div[1]/div/div/div[1]/div/div/div/div/div/div/rf-header/rf-header-top/div/div[2]/rf-search/div/div[1]/rf-awesomplete[2]/div/div[1]/input")
            destination.clear()
            destination.send_keys(cfg.destination_station)
            destination.send_keys(Keys.DOWN)
            destination.send_keys(Keys.ENTER)

            # Select the date
            cfg.runConfig.log.debug("selecting the right day")
            staleElement = True
            dayFound = False
            nextMonths = False
            while staleElement or not dayFound:
                try:
                    ini = self.__driver.find_element(By.ID, "datepicker")
                    ini.click()
                    if nextMonths:
                        cfg.runConfig.log.debug("trying next month")
                        nextMonthsButton = self.__driver.find_element(
                            By.CLASS_NAME, "lightpick__next-action")
                        nextMonthsButton.click()
                        nextMonths = False
                    WebDriverWait(self.__driver, 30).until(expected_conditions.presence_of_element_located(
                        (By.CLASS_NAME, "lightpick__months")))
                    months = self.__driver.find_elements(By.CLASS_NAME,
                                                         "lightpick__month")
                    for month in months:
                        lightpick__days = month.find_element(By.CLASS_NAME,
                                                             "lightpick__days")
                        days = lightpick__days.find_elements(By.CLASS_NAME,
                                                             "lightpick__day")
                        for day in days:
                            dt_object = datetime.fromtimestamp(
                                int(day.get_attribute("data-time"))/1000)
                            if dt_object.strftime("%d/%m/%Y") == cfg.day:
                                day.click()
                                self.__driver.find_element(By.CLASS_NAME,
                                                           "lightpick__apply-action-sub").click()
                                cfg.runConfig.log.debug("day found")
                                dayFound = True
                    if not dayFound:
                        nextMonths = True
                except StaleElementReferenceException:
                    staleElement = True
                staleElement = False

            # Submit
            cfg.runConfig.log.info("submitting the form")
            button = self.__driver.find_element(By.CLASS_NAME, "mdc-button")
            button.click()

            # Trains table. Parsing
            cfg.runConfig.log.info("waiting for results")
            WebDriverWait(self.__driver, 30).until(
                expected_conditions.presence_of_element_located((By.CLASS_NAME, "trayectoRow")))

            # NEW WAY
            # ini = datetime.now()
            soup = BeautifulSoup(self.__driver.page_source, "html.parser")
            listaTrenesTBodyIda = soup.find(id="listaTrenesTBodyIda")
            trayectoRows = listaTrenesTBodyIda.find_all(class_="trayectoRow")
            for trayectoRow in trayectoRows:
                trayecto = {}
                prices = list()
                tds = trayectoRow.find_all("td")
                for td in tds:
                    try:
                        salida = td.find(class_="salida").text.strip()
                        trayecto["salida"] = salida
                    except:
                        pass
                    try:
                        duracion = td.find(class_="duracion").text.strip()
                        trayecto["duracion"] = duracion
                    except:
                        pass
                    try:
                        llegada = td.find(class_="llegada").text.strip()
                        trayecto["llegada"] = llegada
                        tipo = td.find_all("div")[-1].text.strip()
                        # if tipo is empty, could be gatthered from an img -.-
                        if tipo == "":
                            tipo = td.find("img").get("alt").strip()
                        trayecto["tipo"] = tipo
                    except:
                        pass
                    try:
                        price = td.find("button").text.strip()
                        if not "No disponible" in price and price != "":
                            prices.append(price)
                            trayecto["prices"] = prices
                    except:
                        pass
                cfg.runConfig.log.info(f"trayecto: {trayecto}")

                # This covers and use case where there are two trains with the same departure and arrival time
                # Example: Zaragoza -> Cordoba. The first train goes after reaching Cordoba to Sevilla, the second one goes to Malaga.
                # Both arrives Cordoba at the same time.
                # TODO: Refactor. Don't know if it could be more than two trains at the same time.
                cfg.runConfig.log.debug(
                    f"checking if the previous trayecto has te same departure and arrival time")
                if len(result.tickets) > 0:
                    if result.tickets[-1]["salida"] == trayecto["salida"] and result.tickets[-1]["llegada"] == trayecto["llegada"]:
                        cfg.runConfig.log.debug(
                            f"found a trayecto that has te same departure and arrival time")
                        cfg.runConfig.log.debug(f"updating prices")
                        # Append the prices to the previous trayecto
                        result.tickets[-1]["prices"].extend(prices)
                    else:
                        result.tickets.append(trayecto)
                else:
                    result.tickets.append(trayecto)

        except WebDriverException as ex:
            cfg.runConfig.log.error(f"error while parsing renfe results")
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
            salida_dt = datetime.strptime(salida, '%H.%M')
            departure_date = date.replace(
                hour=salida_dt.hour, minute=salida_dt.minute, second=0, microsecond=0)
            departure_timestamp = int(datetime.timestamp(departure_date))

            llegada = d.get("llegada")
            llegada_dt = datetime.strptime(llegada, '%H.%M')
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
