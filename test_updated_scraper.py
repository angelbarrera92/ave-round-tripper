#!/usr/bin/env python3

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from datetime import datetime, timedelta
import logging
from src.scrapers.renfe import RenfeScraper, RenfeScraperConfig
from src.config import RunConfig
from src.logs.log import log_setup

def test_renfe_scraper():
    """Test the updated Renfe scraper"""
    print("🚂 Testing updated Renfe scraper...")
    
    # Set up logging
    logger = logging.getLogger("test_renfe")
    log_setup(logger, logging.INFO)
    
    # Set up basic configuration
    class MockDB:
        def __init__(self):
            self.session = None
    
    class MockNotificationService:
        def send(self, message):
            print(f"📧 Notification: {message}")
    
    # Create a mock run config
    run_config = RunConfig(
        log=logger,
        db=MockDB(),
        notification=MockNotificationService()
    )
    
    # Set up scraper config
    tomorrow = datetime.now() + timedelta(days=7)  # Search 7 days ahead
    day = tomorrow.strftime("%d/%m/%Y")
    
    scraper_config = RenfeScraperConfig(
        runConfig=run_config,
        day=day,
        origin_station="Madrid",
        destination_station="Barcelona",
        price_change_notification=True
    )
    
    print(f"🔍 Searching for trains from {scraper_config.origin_station} to {scraper_config.destination_station} on {day}")
    
    # Test the scraper
    scraper = RenfeScraper()
    
    try:
        result = scraper.scrape(scraper_config)
        
        print(f"✅ Scraping completed!")
        print(f"📊 Found {len(result.tickets)} train options:")
        
        for i, ticket in enumerate(result.tickets, 1):
            print(f"  {i}. {ticket.get('salida', 'N/A')} → {ticket.get('llegada', 'N/A')}")
            print(f"     Type: {ticket.get('tipo', 'N/A')}")
            print(f"     Duration: {ticket.get('duracion', 'N/A')}")
            print(f"     Prices: {ticket.get('prices', [])}")
            print()
        
        if len(result.tickets) == 0:
            print("⚠️  No trains found. This might indicate:")
            print("   - Website structure has changed further")
            print("   - No trains available for the selected route/date")
            print("   - Anti-bot measures are blocking the scraper")
            print("   - Search form submission didn't work correctly")
        
    except Exception as e:
        print(f"❌ Error during scraping: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # Clean up
        try:
            del scraper
        except:
            pass

if __name__ == "__main__":
    test_renfe_scraper()
