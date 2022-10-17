from datetime import datetime, timedelta
from logging import getLevelName, getLogger
from os import getenv

from src.config import RunConfig
from src.db.clean import clean_old_timeseries
from src.db.db import MySQL, PostgreSQL, Sqlite
from src.logs.log import log_setup
from src.notifications.telegram import Telegram
from src.oportunities.roundtrip import round_trip
from src.scrapers.renfe import RenfeScraper, RenfeScraperConfig


def clean(runConfig: RunConfig):
    historical_data_days = int(getenv("TRAVEL_HISTORICAL_DATA_DAYS", "30"))
    clean_old_timeseries(runConfig, historical_data_days)


def run(runConfig: RunConfig):
    init_time = datetime.now()
    log.debug(f"loop started at {init_time.strftime('%H:%M:%S')}")

    # Travel input parameters
    travel_from = getenv("TRAVEL_FROM", "Madrid")
    travel_to = getenv("TRAVEL_TO", "Zaragoza")
    travel_days = int(getenv("TRAVEL_DAYS", "30"))
    renfe_price_change_notification = to_bool(
        getenv("TRAVEL_RENFE_PRICE_CHANGE_NOTIFICATION", "False"))
    round_trip_enabled = to_bool(
        getenv("ROUND_TRIP_ENABLED", "True"))
    round_trip_notification_max_price = float(
        getenv("ROUND_TRIP_NOTIFICATION_MAX_PRICE", "40"))
    round_trip_origin_departure_time = getenv(
        "ROUND_TRIP_ORIGIN_DEPARTURE_TIME", "06:30")
    round_trip_destination_departure_times = getenv(
        "ROUND_TRIP_DESTINATION_DEPARTURE_TIME", "15:45,17:45,18:26,20:45")
    travel_start_date = getenv("TRAVEL_START_DATE", None)
    if travel_start_date:
        start_date = datetime.strptime(travel_start_date, "%d/%m/%Y")
        if start_date < datetime.now():
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    renfe = RenfeScraper()

    processed = 0
    while processed < travel_days:
        inner_init_time = datetime.now()
        log.debug(
            f"inner loop started at {inner_init_time.strftime('%H:%M:%S')}")

        currentDateFormatted = start_date.strftime("%d/%m/%Y")
        log.info(f"processing {currentDateFormatted}")

        # Trains From Origin -> To Destination
        origin_station = travel_from
        destination_station = travel_to
        renfeScrapeConfig = RenfeScraperConfig(
            runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
        try:
            result = renfe.scrape(renfeScrapeConfig)
        except Exception as e:
            log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
            log.error(e)
            exit(1)
        renfe.save(renfeScrapeConfig, result)

        if round_trip_enabled:
            # Return: Trains From Destination -> To Origin
            origin_station = travel_to
            destination_station = travel_from
            renfeScrapeConfig = RenfeScraperConfig(
                runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
            try:
                result = renfe.scrape(renfeScrapeConfig)
            except Exception as e:
                log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
                log.error(e)
                exit(1)
            renfe.save(renfeScrapeConfig, result)

            # Check Round Trips oportunities
            for round_trip_destination_departure_time in round_trip_destination_departure_times.split(","):
                round_trip(runConfig, start_date, travel_from, round_trip_origin_departure_time, travel_to,
                           round_trip_destination_departure_time, round_trip_notification_max_price)

        processed += 1
        start_date += timedelta(days=1)
        log.info(f"{processed}/{travel_days} days processed")

        inner_end_time = datetime.now()
        log.debug(
            f"inner loop finished at {inner_end_time.strftime('%H:%M:%S')}")
        log.info(
            f"inner loop toke: {abs((inner_end_time-inner_init_time).seconds)} seconds")

    end_time = datetime.now()
    log.debug(f"loop finished at {end_time.strftime('%H:%M:%S')}")
    log.info(f"loop toke: {abs((end_time-init_time).seconds)/60} minutes")


def to_bool(value):
    """
       Converts 'something' to boolean. Raises exception for invalid formats
           Possible True  values: 1, True, "1", "TRue", "yes", "y", "t"
           Possible False values: 0, False, None, [], {}, "", "0", "faLse", "no", "n", "f", 0.0, ...
    """
    if str(value).lower() in ("yes", "y", "true",  "t", "1"):
        return True
    if str(value).lower() in ("no",  "n", "false", "f", "0", "0.0", "", "none", "[]", "{}"):
        return False
    raise Exception(f"Invalid value for boolean conversion: {str(value)}")


if __name__ == "__main__":
    # Init log
    log_level_cfg = getenv("TRAVEL_LOG_LEVEL", "info")
    log = log_setup(getLogger(__file__),
                    getLevelName(log_level_cfg.upper()))

    # Init DB
    db = None
    db_file_path = getenv(
        "TRAVEL_DB_PATH")
    if db_file_path:
        log.info(f"db mode is: sqlite. Path: {db_file_path}")
        db = Sqlite(db_file_path)
    else:
        db_engine = getenv("TRAVEL_DB_ENGINE")
        if not db_engine:
            raise Exception("db engine is not specified")
        # Check db engine is mysql or postgres
        if db_engine not in ["mysql", "postgres"]:
            raise Exception(f"db engine is not supported: {db_engine}")
        db_host = getenv("TRAVEL_DB_HOST")
        db_port = getenv("TRAVEL_DB_PORT")
        db_user = getenv("TRAVEL_DB_USER")
        db_pass = getenv("TRAVEL_DB_PASSWORD")
        db_name = getenv("TRAVEL_DB_NAME")
        if db_engine == "mysql":
            log.info(f"db mode is: mysql/mariadb")
            db = MySQL(db_user, db_pass, db_host, db_port, db_name)
        elif db_engine == "postgres":
            log.info(f"db mode is: postgres")
            db = PostgreSQL(db_user, db_pass, db_host, db_port, db_name)

    # Init Telegram Notification service
    notify_token = getenv("TRAVEL_NOTIFICATION_TOKEN")
    notify_chat_id = int(getenv("TRAVEL_NOTIFICATION_CHAT_ID"))
    notification = Telegram(notify_token, notify_chat_id)

    # Create configuration struct
    runConfig = RunConfig(log, db, notification)

    # Execute once
    run(runConfig)
    clean(runConfig)

    debug = getenv("TRAVEL_DEBUG", "no")
    log.info(f"debug mode is: {debug}")
    if debug == "no":
        # Execute forever if no debug mode
        while True:
            run(runConfig)
            clean(runConfig)
