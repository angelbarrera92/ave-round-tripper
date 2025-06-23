from datetime import datetime, timedelta
from logging import getLevelName, getLogger
from os import getenv
import sys
import os
import subprocess
import time

from src.config import RunConfig
from src.db.clean import clean_old_timeseries
from src.db.db import MySQL, PostgreSQL, Sqlite
from src.logs.log import log_setup
from src.notifications.telegram import Telegram
from src.notifications.console import ConsoleNotification  # Added import
from src.oportunities.roundtrip import round_trip
from src.scrapers.renfe import RenfeScraper, RenfeScraperConfig
from src.scrapers.ouigo import OuigoScraper, OuigoScraperConfig
from src.utils.aggressive_timeout import TimeoutHandler, TimeoutError, is_timeout_supported, check_timeout_recovery
from src.utils.recovery import RecoveryManager, RecoveryState, create_recovery_config

def clean(runConfig: RunConfig):
    historical_data_days = int(getenv("TRAVEL_HISTORICAL_DATA_DAYS", "30"))
    clean_old_timeseries(runConfig, historical_data_days)


def scrape_with_timeout(scraper, config, scraper_name, timeout_seconds=120, recovery_manager=None, recovery_state=None):
    """
    Scrape with timeout detection. Saves recovery state and exits the program if scraper gets stuck.

    Args:
        scraper: The scraper instance
        config: The scraper configuration
        scraper_name: Name of the scraper for logging
        timeout_seconds: Timeout in seconds (default: 2 minutes)
        recovery_manager: RecoveryManager instance for saving state
        recovery_state: Current recovery state to update

    Returns:
        Scraping result or None if timeout occurs
    """
    start_time = time.time()

    try:
        # Save state before starting risky operation
        if recovery_manager and recovery_state:
            recovery_state.last_completed_operation = f"Starting {scraper_name}"
            recovery_state.timestamp = datetime.now().isoformat()
            recovery_manager.save_state(recovery_state)

        with TimeoutHandler(timeout_seconds):
            log.info(f"🚀 Starting {scraper_name} scraping with {timeout_seconds}s timeout at {time.strftime('%H:%M:%S')}")
            log.info(f"⏰ Will timeout at {time.strftime('%H:%M:%S', time.localtime(start_time + timeout_seconds))}")
            result = scraper.scrape(config)
            elapsed = time.time() - start_time
            log.info(f"✅ {scraper_name} scraping completed successfully in {elapsed:.1f}s")

            # Update recovery state after successful completion
            if recovery_manager and recovery_state:
                recovery_state.last_completed_operation = f"Completed {scraper_name}"
                recovery_state.timestamp = datetime.now().isoformat()
                recovery_manager.save_state(recovery_state)

            return result
    except TimeoutError as e:
        elapsed = time.time() - start_time
        log.error(f"❌ {scraper_name} scraper timed out after {elapsed:.1f}s: {e}")
        log.error(f"🔥 Scraper {scraper_name} got stuck and exceeded {timeout_seconds} seconds timeout")
        log.error(f"💀 Current time: {time.strftime('%H:%M:%S')}")
        log.error("🚨 EXITING PROGRAM TO PREVENT INFINITE HANGING...")        # Save final recovery state before exit
        if recovery_manager and recovery_state:
            recovery_state.last_completed_operation = f"TIMEOUT in {scraper_name}"
            recovery_state.timestamp = datetime.now().isoformat()
            recovery_manager.save_state(recovery_state)
            log.info(f"💾 Recovery state saved - will resume from {recovery_state.current_date}")

        # Note: Browser cleanup is now handled by the AggressiveTimeoutHandler
        log.error("🚨 Timeout handler has killed browser processes")
        log.error("🔄 Program will exit - recovery state saved")
        sys.exit(1)
    except Exception as e:
        elapsed = time.time() - start_time
        log.error(f"❌ Error in {scraper_name} scraper after {elapsed:.1f}s: {e}")
        raise


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

    # Initialize recovery system
    recovery_manager = RecoveryManager()

    # Create configuration for recovery detection
    recovery_config = create_recovery_config(
        travel_from, travel_to, travel_days, travel_start_date,
        round_trip_enabled, renfe_price_change_notification
    )

    # Check if we should recover from previous timeout
    should_recover, recovery_state = recovery_manager.should_recover(recovery_config)

    # Determine starting point
    if should_recover and recovery_state:
        log.info("🔄 RECOVERY MODE: Detected timeout restart with same configuration")
        log.info(f"📅 Resuming from date: {recovery_state.current_date}")
        log.info(f"📊 Progress: {recovery_state.processed_days}/{recovery_state.total_days} days completed")
        log.info(f"🕐 Last operation: {recovery_state.last_completed_operation}")

        # Resume from where we left off
        start_date = datetime.strptime(recovery_state.current_date, "%d/%m/%Y")
        processed = recovery_state.processed_days

        # If the last operation was starting something, we need to redo that day
        if "Starting" in recovery_state.last_completed_operation or "TIMEOUT" in recovery_state.last_completed_operation:
            log.info(f"🔁 Last operation was incomplete - redoing {recovery_state.current_date}")
            # Don't increment processed, redo this day
        else:
            # Last operation completed successfully, move to next day
            log.info(f"✅ Last operation completed successfully - moving to next day")
            start_date += timedelta(days=1)
            processed += 1
    else:
        log.info("🚀 NORMAL MODE: Starting fresh scraping process")
        processed = 0

        # Initialize recovery state
        recovery_state = RecoveryState(
            current_date=start_date.strftime("%d/%m/%Y"),
            processed_days=0,
            total_days=travel_days,
            last_completed_operation="Starting fresh",
            timestamp=datetime.now().isoformat(),
            config_hash=recovery_manager._calculate_config_hash(recovery_config),
            travel_from=travel_from,
            travel_to=travel_to,
            round_trip_enabled=round_trip_enabled
        )

    # Update config hash for this run
    recovery_manager.update_config_hash(recovery_config)

    # Clear any old timeout flags
    try:
        if os.path.exists('.timeout_occurred'):
            os.remove('.timeout_occurred')
    except:
        pass

    renfe = RenfeScraper()
    ouigo = OuigoScraper()

    while processed < travel_days:
        inner_init_time = datetime.now()
        log.debug(
            f"inner loop started at {inner_init_time.strftime('%H:%M:%S')}")

        currentDateFormatted = start_date.strftime("%d/%m/%Y")
        log.info(f"processing {currentDateFormatted}")

        # Update recovery state for current date
        recovery_state.current_date = currentDateFormatted
        recovery_state.processed_days = processed
        recovery_state.last_completed_operation = f"Processing date {currentDateFormatted}"
        recovery_state.timestamp = datetime.now().isoformat()
        recovery_manager.save_state(recovery_state)

        # Trains From Origin -> To Destination
        origin_station = travel_from
        destination_station = travel_to

        # Renfe
        renfeScrapeConfig = RenfeScraperConfig(
            runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
        try:
            result = scrape_with_timeout(renfe, renfeScrapeConfig, "Renfe", scraper_timeout, recovery_manager, recovery_state)
        except Exception as e:
            log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
            log.error(e)
            exit(1)
        renfe.save(renfeScrapeConfig, result)

        # Update recovery state after Renfe completion
        recovery_state.last_completed_operation = f"Completed Renfe for {currentDateFormatted}"
        recovery_state.timestamp = datetime.now().isoformat()
        recovery_manager.save_state(recovery_state)

        # Ouigo
        ouigoScraperConfig = OuigoScraperConfig(
            runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
        try:
            result = scrape_with_timeout(ouigo, ouigoScraperConfig, "Ouigo", scraper_timeout, recovery_manager, recovery_state)
        except Exception as e:
            log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
            log.error(e)
            exit(1)
        ouigo.save(ouigoScraperConfig, result)

        # Update recovery state after Ouigo completion
        recovery_state.last_completed_operation = f"Completed Ouigo for {currentDateFormatted}"
        recovery_state.timestamp = datetime.now().isoformat()
        recovery_manager.save_state(recovery_state)


        if round_trip_enabled:
            # Return: Trains From Destination -> To Origin
            origin_station = travel_to
            destination_station = travel_from

            # Renfe
            renfeScrapeConfig = RenfeScraperConfig(
                runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
            try:
                result = scrape_with_timeout(renfe, renfeScrapeConfig, "Renfe (return)", scraper_timeout, recovery_manager, recovery_state)
            except Exception as e:
                log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
                log.error(e)
                exit(1)
            renfe.save(renfeScrapeConfig, result)

            # Update recovery state after Renfe return completion
            recovery_state.last_completed_operation = f"Completed Renfe return for {currentDateFormatted}"
            recovery_state.timestamp = datetime.now().isoformat()
            recovery_manager.save_state(recovery_state)

            # Ouigo
            ouigoScraperConfig = OuigoScraperConfig(
                runConfig, currentDateFormatted, origin_station, destination_station, renfe_price_change_notification)
            try:
                result = scrape_with_timeout(ouigo, ouigoScraperConfig, "Ouigo (return)", scraper_timeout, recovery_manager, recovery_state)
            except Exception as e:
                log.error(f"Error scraping {currentDateFormatted} from {origin_station} to {destination_station}")
                log.error(e)
                exit(1)
            ouigo.save(ouigoScraperConfig, result)

            # Update recovery state after Ouigo return completion
            recovery_state.last_completed_operation = f"Completed Ouigo return for {currentDateFormatted}"
            recovery_state.timestamp = datetime.now().isoformat()
            recovery_manager.save_state(recovery_state)

            # Check Round Trips oportunities
            for round_trip_origin_departure_time in round_trip_origin_departure_times.split(","):
                for round_trip_destination_departure_time in round_trip_destination_departure_times.split(","):
                    round_trip(runConfig, start_date, travel_from, round_trip_origin_departure_time, travel_to,
                            round_trip_destination_departure_time, round_trip_notification_max_price)

        # Mark day as fully completed
        processed += 1
        start_date += timedelta(days=1)

        # Update recovery state after day completion
        recovery_state.processed_days = processed
        recovery_state.last_completed_operation = f"Completed all scrapers for {currentDateFormatted}"
        recovery_state.timestamp = datetime.now().isoformat()
        recovery_manager.save_state(recovery_state)

        log.info(f"{processed}/{travel_days} days processed")

        inner_end_time = datetime.now()
        log.debug(
            f"inner loop finished at {inner_end_time.strftime('%H:%M:%S')}")
        log.info(
            f"inner loop toke: {abs((inner_end_time-inner_init_time).seconds)} seconds")

    # Clear recovery state when all processing is complete
    recovery_manager.clear_state()
    log.info("🏁 All scraping completed successfully - recovery state cleared")

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
    # Check for previous timeout and recovery info
    if check_timeout_recovery():
        print("🔄 Continuing after previous timeout...")
        
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
