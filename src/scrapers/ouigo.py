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
        # Reverted to older, potentially working API endpoints
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
            # Reverted login mechanism
            cfg.runConfig.log.debug(f"Attempting login to {self.__login_url}")
            token_response = requests.post(self.__login_url, json={
                "username": self.__username,
                "password": self.__password
            })
            token_response.raise_for_status() 
            token_data = token_response.json()

            if "token" not in token_data:
                cfg.runConfig.log.error(f"Login failed: 'token' not in response. Response: {token_data}")
                return result
            token = token_data["token"]
            cfg.runConfig.log.debug(f"Token obtained: {token[:20]}...")

            # Fetch stations using the older endpoint (no token usually required for this specific old endpoint)
            cfg.runConfig.log.debug(f"Fetching stations from {self.__stations_url}")
            stations_response = requests.get(self.__stations_url)
            stations_response.raise_for_status()
            stations_json = stations_response.json()
            cfg.runConfig.log.debug(f"Stations response (first 500 chars): {str(stations_json)[:500]}")

            origin_station_code = ""
            destination_station_code = ""

            # Restored original station parsing logic
            for station in stations_json:
                if not station.get("hidden", True): # Default to hidden if key missing
                    # Check if synonyms exist and is a list before iterating
                    synonyms = station.get("synonyms", [])
                    if isinstance(synonyms, list):
                        if cfg.origin_station in synonyms:
                            cfg.runConfig.log.debug(f"Origin station found: {station.get('name')}")
                            origin_station_code = station.get("_u_i_c_station_code")
                        if cfg.destination_station in synonyms:
                            cfg.runConfig.log.debug(f"Destination station found: {station.get('name')}")
                            destination_station_code = station.get("_u_i_c_station_code")
            
            if not origin_station_code:
                 cfg.runConfig.log.warning(f"Origin station '{cfg.origin_station}' not found using original parsing logic.")
            if not destination_station_code:
                 cfg.runConfig.log.warning(f"Destination station '{cfg.destination_station}' not found using original parsing logic.")

            cfg.runConfig.log.debug(f"Origin station code: {origin_station_code}")
            cfg.runConfig.log.debug(f"Destination station code: {destination_station_code}")

            if not origin_station_code or not destination_station_code:
                cfg.runConfig.log.error("Origin or destination station code not found. Halting.")
                return result
            
            outbound_date = datetime.strptime(cfg.day, "%d/%m/%Y").strftime("%Y-%m-%d")

            # Restored original journey search payload structure
            journey_payload = {
                "destination": destination_station_code,
                "origin": origin_station_code,
                "outbound_date": outbound_date,
                "passengers": [{
                    "discount_cards": [],
                    "disability_type": "NH", # Assuming "NH" is a default or common value
                    "type": "A" # Assuming "A" for Adult
                }]
            }
            cfg.runConfig.log.debug(f"Searching journeys with payload: {journey_payload} to {self.__journey_url}")
            
            journeys_response = requests.post(self.__journey_url, json=journey_payload, headers={
                "Authorization": f"Bearer {token}"
            })
            journeys_response.raise_for_status()
            journeys_json = journeys_response.json()
            cfg.runConfig.log.debug(f"Journeys response (first 500 chars): {str(journeys_json)[:500]}")

            # Restored original journey parsing logic
            if "outbound" in journeys_json and isinstance(journeys_json["outbound"], list):
                for journey in journeys_json["outbound"]:
                    trayecto = {}
                    price = journey.get("price")
                    
                    departure_station_info = journey.get("departure_station", {})
                    arrival_station_info = journey.get("arrival_station", {})

                    departure_timestamp_str = departure_station_info.get("departure_timestamp")
                    arrival_timestamp_str = arrival_station_info.get("arrival_timestamp")

                    if not price or not departure_timestamp_str or not arrival_timestamp_str:
                        cfg.runConfig.log.warning(f"Skipping journey due to missing data: price={price}, departure={departure_timestamp_str}, arrival={arrival_timestamp_str}")
                        continue

                    try:
                        # Example: 2023-06-15T07:05:00+02:00
                        departure_dt_obj = datetime.strptime(departure_timestamp_str, "%Y-%m-%dT%H:%M:%S%z")
                        arrival_dt_obj = datetime.strptime(arrival_timestamp_str, "%Y-%m-%dT%H:%M:%S%z")

                        departure_time_str = departure_dt_obj.strftime("%H:%M")
                        arrival_time_str = arrival_dt_obj.strftime("%H:%M")
                        
                        duration_delta = arrival_dt_obj - departure_dt_obj
                        duration_hours = duration_delta.seconds // 3600
                        duration_minutes = (duration_delta.seconds // 60) % 60
                        duration_str = f"{duration_hours}h:{duration_minutes:02d}m"

                        trayecto["salida"] = departure_time_str
                        trayecto["duracion"] = duration_str
                        trayecto["llegada"] = arrival_time_str
                        trayecto["tipo"] = "Ouigo" # Hardcoded as per original
                        trayecto["prices"] = [price] # Original logic stored price in a list
                        
                        cfg.runConfig.log.info(f"Trayecto found: {trayecto}")
                        result.tickets.append(trayecto)
                    except ValueError as ve:
                        cfg.runConfig.log.error(f"Error parsing date/time for journey: {ve}. Data: dep='{departure_timestamp_str}', arr='{arrival_timestamp_str}'")
                        continue
            else:
                cfg.runConfig.log.warning(f"No 'outbound' journeys found or not in expected format in response. Keys: {journeys_json.keys()}")

        except requests.exceptions.HTTPError as http_err:
            cfg.runConfig.log.error(f"HTTP error occurred: {http_err}")
            if http_err.response is not None:
                cfg.runConfig.log.error(f"Response status code: {http_err.response.status_code}")
                cfg.runConfig.log.error(f"Response content: {http_err.response.text}")
            cfg.runConfig.log.error(traceback.format_exc())
        except Exception as ex:
            cfg.runConfig.log.error(f"An error occurred while scraping Ouigo: {ex}")
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
    if len(prices) > 0:
        return sorted(prices)[0]
    return None
