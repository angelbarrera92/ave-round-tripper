from datetime import datetime, timedelta
from logging import getLevelName, getLogger
from os import getenv
import sys

from src.config import RunConfig
from src.db.clean import clean_old_timeseries
from src.db.db import MySQL, PostgreSQL, Sqlite
from src.logs.log import log_setup
from src.notifications.telegram import Telegram
from src.notifications.console import ConsoleNotification  # Added import
from src.oportunities.roundtrip import round_trip
from src.scrapers.renfe import RenfeScraper, RenfeScraperConfig
from src.scrapers.ouigo import OuigoScraper, OuigoScraperConfig
from src.utils.timeout import TimeoutHandler, TimeoutError, is_timeout_supported

def clean(runConfig: RunConfig):
    historical_data_days = int(getenv("TRAVEL_HISTORICAL_DATA_DAYS", "30"))
    clean_old_timeseries(runConfig, historical_data_days)


def scrape_with_timeout(scraper, config, scraper_name, timeout_seconds=300):
    """
    Scrape with timeout detection. Exits the program if scraper gets stuck.

    Args:
        scraper: The scraper instance
        config: The scraper configuration
        scraper_name: Name of the scraper for logging
        timeout_seconds: Timeout in seconds (default: 5 minutes)

    Returns:
        Scraping result or None if timeout occurs
    """
    import time
    start_time = time.time()

    try:
        with TimeoutHandler(timeout_seconds):
            log.info(f"🚀 Starting {scraper_name} scraping with {timeout_seconds}s timeout at {time.strftime('%H:%M:%S')}")
            log.info(f"⏰ Will timeout at {time.strftime('%H:%M:%S', time.localtime(start_time + timeout_seconds))}")
            result = scraper.scrape(config)
            elapsed = time.time() - start_time
            log.info(f"✅ {scraper_name} scraping completed successfully in {elapsed:.1f}s")
            return result
    except TimeoutError as e:
        elapsed = time.time() - start_time
        log.error(f"❌ {scraper_name} scraper timed out after {elapsed:.1f}s: {e}")
        log.error(f"🔥 Scraper {scraper_name} got stuck and exceeded {timeout_seconds} seconds timeout")
        log.error(f"💀 Current time: {time.strftime('%H:%M:%S')}")
        log.error("🚨 EXITING PROGRAM TO PREVENT INFINITE HANGING...")

        # Try to cleanup any WebDriver instances
        try:
            if hasattr(scraper, '_RenfeScraper__driver') and scraper._RenfeScraper__driver:
                scraper._RenfeScraper__driver.quit()
        except:
            pass
        try:
            if hasattr(scraper, '__driver') and scraper.__driver:
                scraper.__driver.quit()
        except:
            pass

        sys.exit(1)
    except Exception as e:
        elapsed = time.time() - start_time
        log.error(f"❌ Error in {scraper_name} scraper after {elapsed:.1f}s: {e}")
        raise


import threading
import time


def create_process_watchdog(timeout_minutes=15):
    """Create a watchdog thread that kills the process if it runs too long"""
    def watchdog():
        time.sleep(timeout_minutes * 60)
        import os
        print(f"\n💀 PROCESS WATCHDOG: Program has been running for {timeout_minutes} minutes")
        print("🚨 This suggests a scraper is completely stuck. Forcing exit...")
        os._exit(1)

    watchdog_thread = threading.Thread(target=watchdog, daemon=True)
    watchdog_thread.start()
    return watchdog_thread


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
    round_trip_origin_departure_times = getenv(
        "ROUND_TRIP_ORIGIN_DEPARTURE_TIME", "06:30,07:05")
    round_trip_destination_departure_times = getenv(
        "ROUND_TRIP_DESTINATION_DEPARTURE_TIME", "15:45,17:45,18:26,20:45")

    # Scraper timeout configuration
    scraper_timeout = int(getenv("TRAVEL_SCRAPER_TIMEOUT", "120"))  # Default 2 minutes (aggressive)
    log.info(f"⏱️ Scraper timeout set to {scraper_timeout} seconds ({scraper_timeout/60:.1f} minutes)")

    travel_start_date = getenv("TRAVEL_START_DATE", None)
    if travel_start_date:
        start_date = datetime.strptime(travel_start_date, "%d/%m/%Y")
        if start_date < datetime.now():
            start_date = datetime.now()
    else:
        start_date = datetime.now()

    renfe = RenfeScraper()
    ouigo = OuigoScraper()

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

        # Renfe
        renfeScrapeConfig = RenfeScraperConfig(
            runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
        try:
            result = scrape_with_timeout(renfe, renfeScrapeConfig, "Renfe", scraper_timeout)
        except Exception as e:
            log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
            log.error(e)
            exit(1)
        renfe.save(renfeScrapeConfig, result)

        # Ouigo
        ouigoScraperConfig = OuigoScraperConfig(
            runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
        try:
            result = scrape_with_timeout(ouigo, ouigoScraperConfig, "Ouigo", scraper_timeout)
        except Exception as e:
            log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
            log.error(e)
            exit(1)
        ouigo.save(ouigoScraperConfig, result)


        if round_trip_enabled:
            # Return: Trains From Destination -> To Origin
            origin_station = travel_to
            destination_station = travel_from

            # Renfe
            renfeScrapeConfig = RenfeScraperConfig(
                runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
            try:
                result = scrape_with_timeout(renfe, renfeScrapeConfig, "Renfe (return)", scraper_timeout)
            except Exception as e:
                log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
                log.error(e)
                exit(1)
            renfe.save(renfeScrapeConfig, result)

            # Ouigo
            ouigoScraperConfig = OuigoScraperConfig(
                runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
            try:
                result = scrape_with_timeout(ouigo, ouigoScraperConfig, "Ouigo (return)", scraper_timeout)
            except Exception as e:
                log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
                log.error(e)
                exit(1)
            ouigo.save(ouigoScraperConfig, result)

            # Check Round Trips oportunities
            for round_trip_origin_departure_time in round_trip_origin_departure_times.split(","):
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
    # Check if timeout functionality is supported on this platform
    if not is_timeout_supported():
        print("❌ Error: Timeout protection requires Unix-like system (Linux/macOS)")
        print("This system doesn't support the required signal.alarm() functionality")
        print("The scraper timeout protection will not work on this platform")
        sys.exit(1)

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
    notify_chat_id = getenv("TRAVEL_NOTIFICATION_CHAT_ID") # Changed to getenv

    if notify_token and notify_chat_id: # Added conditional
        notification = Telegram(notify_token, int(notify_chat_id)) # Added int conversion
    else:
        notification = ConsoleNotification(log) # Added ConsoleNotification instantiation

    # Create configuration struct
    runConfig = RunConfig(log, db, notification)

    # Start process watchdog (kills process after 15 minutes)
    watchdog = create_process_watchdog(15)
    log.info("🐕 Process watchdog started (15 minute maximum runtime)")

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
