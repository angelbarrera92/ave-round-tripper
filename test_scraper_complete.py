#!/usr/bin/env python3
"""
Test script for the updated RENFE scraper.
This tests the actual scraper functionality with a sample configuration.
"""

import sys
import os
sys.path.append('/Users/barreang/personal/ave-round-tripper')

from src.config import RunConfig
from src.scrapers.renfe import RenfeScraper, RenfeScraperConfig
from datetime import datetime, timedelta

def test_renfe_scraper():
    """Test the RENFE scraper with a sample configuration."""
    
    print("Testing RENFE Scraper...")
    
    # Create a test configuration
    # We'll use tomorrow's date for testing
    tomorrow = datetime.now() + timedelta(days=1)
    test_date = tomorrow.strftime("%d/%m/%Y")
    
    print(f"Test date: {test_date}")
    
    # Create minimal run configuration for testing
    class TestRunConfig:
        def __init__(self):
            self.log = self
            
        def info(self, msg):
            print(f"INFO: {msg}")
            
        def debug(self, msg):
            print(f"DEBUG: {msg}")
            
        def error(self, msg):
            print(f"ERROR: {msg}")
            
        def warning(self, msg):
            print(f"WARNING: {msg}")
    
    run_config = TestRunConfig()
    
    # Create scraper configuration
    scraper_config = RenfeScraperConfig(
        runConfig=run_config,
        day=test_date,
        origin_station="Madrid",
        destination_station="Zaragoza",
        price_change_notification=False
    )
    
    # Create and run scraper
    scraper = RenfeScraper()
    
    try:
        print("Starting scrape...")
        result = scraper.scrape(scraper_config)
        
        print(f"\n=== SCRAPE RESULTS ===")
        print(f"Total trains found: {len(result.tickets)}")
        
        for i, train in enumerate(result.tickets):
            print(f"Train {i+1}: {train.get('salida', '?')} -> {train.get('llegada', '?')} "
                  f"({train.get('tipo', '?')}) - Duration: {train.get('duracion', '?')} - "
                  f"Price: {train.get('prices', ['?'])[0] if train.get('prices') else '?'}")
        
        return result
        
    except Exception as e:
        print(f"Error during scraping: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        # Clean up the scraper
        try:
            scraper.__del__()
        except:
            pass

if __name__ == "__main__":
    test_renfe_scraper()
