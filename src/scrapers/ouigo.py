import traceback
from datetime import datetime

import requests

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
        super().__init__()
        self.__username = "ouigo.web"
        self.__password = "SquirelWeb!2020"
        self.__login_url = "https://mdw02.api-es.ouigo.com/api/Token/login"
        self.__stations_url = "https://mdw02.api-es.ouigo.com/api/Data/GetStations"
        self.__journey_url = "https://mdw02.api-es.ouigo.com/api/Sale/journeysearch"

    def __del__(self):
        pass

    def scrape(self, cfg: OuigoScraperConfig) -> OuigoScrapeResult:
        cfg.runConfig.log.info("running OuigoScraper")
        cfg.runConfig.log.debug("configuration:")
        cfg.runConfig.log.debug(
            f"day: {cfg.day} | origin_station: {cfg.origin_station} | destination_station: {cfg.destination_station}")
        result = OuigoScrapeResult()
        try:
            token = requests.post(self.__login_url, json={
                "username": self.__username,
                "password": self.__password
            }).json()["token"]
            cfg.runConfig.log.debug(f"token: {token}")

            stations = requests.get(self.__stations_url).json()
            origin_station_code = ""
            destination_station_code = ""
            for station in stations:
                if not station["hidden"]:
                    if cfg.origin_station in station["synonyms"]:
                        cfg.runConfig.log.debug(f"origin station found: {station['name']}")
                        origin_station_code = station["_u_i_c_station_code"]
                    if cfg.destination_station in station["synonyms"]:
                        cfg.runConfig.log.debug(f"destination station found: {station['name']}")
                        destination_station_code = station["_u_i_c_station_code"]
            cfg.runConfig.log.debug(f"origin station code: {origin_station_code}")
            cfg.runConfig.log.debug(f"destination station code: {destination_station_code}")
            if origin_station_code == "" or destination_station_code == "":
                cfg.runConfig.log.error("origin or destination station not found")
                return result
            # cfg.day looks like 15/06/2023 and we need 2023-06-15
            outbound_date = datetime.strptime(cfg.day, "%d/%m/%Y").strftime("%Y-%m-%d")
            journeys = requests.post(self.__journey_url, json={
                "destination": destination_station_code,
                "origin": origin_station_code,
                "outbound_date": outbound_date,
                "passengers": [{
                    "discount_cards": [],
                    "disability_type": "NH",
                    "type": "A"
                }]
            }, headers={
                "Authorization": f"Bearer {token}"
            }).json()
            cfg.runConfig.log.debug(f"journeys: {journeys}")

            for journey in journeys["outbound"]:
                trayecto = {}
                price = journey["price"]
                # Price should be a string in the format x,xx (e.g. 10,50€)
                price = f"{price:.2f}€"
                departureTime = journey["departure_station"]["departure_timestamp"]
                # This is an example of departureTime 2023-06-15T07:05:00+02:00. We need 07:05. Parse it using datetime
                departureTime = datetime.strptime(departureTime, "%Y-%m-%dT%H:%M:%S%z").strftime("%H:%M")
                arrivalTime = journey["arrival_station"]["arrival_timestamp"]
                # This is an example of arrivalTime 2023-06-15T09:22:00+02:00. We need 09:22. Parse it using datetime
                arrivalTime = datetime.strptime(arrivalTime, "%Y-%m-%dT%H:%M:%S%z").strftime("%H:%M")
                # Calculate duration from departureTime and arrivalTime
                duration = datetime.strptime(arrivalTime, "%H:%M") - datetime.strptime(departureTime, "%H:%M")
                # Represent the duration as a string in the format xh:xm (e.g. 1h:30m)
                duration = f"{duration.seconds // 3600}h:{(duration.seconds // 60) % 60}m"
                trayecto["salida"] = departureTime
                trayecto["duracion"] = duration
                trayecto["llegada"] = arrivalTime
                trayecto["tipo"] = "Ouigo"
                trayecto["prices"] = [price]
                cfg.runConfig.log.info(f"trayecto: {trayecto}")
                result.tickets.append(trayecto)
        except Exception as ex:
            cfg.runConfig.log.error("error while scraping")
            cfg.runConfig.log.error(ex)
            cfg.runConfig.log.error(traceback.format_exc())
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
