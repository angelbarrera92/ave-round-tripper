#!/usr/bin/env python3
"""
Quick test of the updated RENFE scraper parsing logic using existing HTML.
This simulates the scraper but uses the saved HTML instead of browsing.
"""

import sys
sys.path.append('/Users/barreang/personal/ave-round-tripper')

from src.scrapers.renfe import RenfeScrapeResult
from bs4 import BeautifulSoup
import re

def test_parsing_logic():
    """Test just the parsing logic with the saved HTML."""
    
    print("Testing RENFE parsing logic...")
    
    # Read the saved HTML file
    with open('/Users/barreang/personal/ave-round-tripper/debug_results_page.html', 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # Create result object
    result = RenfeScrapeResult()
    
    # Parse using BeautifulSoup (same as in the scraper)
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Look for train entries - same logic as updated scraper
    train_elements = soup.find_all('div', class_='selectedTren')
    
    print(f"Found {len(train_elements)} train entries")
    
    for train_element in train_elements:
        trayecto = {}
        
        # Extract departure and arrival times from h5 elements
        time_elements = train_element.find_all('h5', {'aria-hidden': 'true'})
        if len(time_elements) >= 2:
            # First h5 is departure, last h5 is arrival
            departure_text = time_elements[0].get_text().strip()
            arrival_text = time_elements[-1].get_text().strip()
            
            # Extract time from text like "17:57 h"
            dep_match = re.search(r'(\d{1,2}:\d{2})', departure_text)
            arr_match = re.search(r'(\d{1,2}:\d{2})', arrival_text)
            
            if dep_match and arr_match:
                trayecto["salida"] = dep_match.group(1)
                trayecto["llegada"] = arr_match.group(1)
        
        # Extract train type from image alt text
        train_img = train_element.find('img', alt=re.compile(r'Tipo de tren', re.IGNORECASE))
        if train_img:
            alt_text = train_img.get('alt', '')
            # Extract train type from alt text like "Imagen de Tren. Tipo de tren AVE"
            train_type_match = re.search(r'Tipo de tren (\w+)', alt_text, re.IGNORECASE)
            if train_type_match:
                trayecto["tipo"] = train_type_match.group(1).upper()
        
        # Extract duration from aria-label
        duration_span = train_element.find('span', {'aria-label': re.compile(r'Duración', re.IGNORECASE)})
        if duration_span:
            duration_text = duration_span.get('aria-label', '')
            # Extract duration from text like "Duración 2 horas 37 minutos."
            duration_match = re.search(r'(\d+)\s+horas?\s+(\d+)\s+minutos?', duration_text, re.IGNORECASE)
            if duration_match:
                hours = duration_match.group(1)
                minutes = duration_match.group(2)
                trayecto["duracion"] = f"{hours}h {minutes}min"
            else:
                # Try simpler pattern
                duration_match = re.search(r'(\d+)\s+horas?', duration_text, re.IGNORECASE)
                if duration_match:
                    trayecto["duracion"] = f"{duration_match.group(1)}h"
        
        # Extract price from precio-final span
        price_element = train_element.find('span', class_='precio-final')
        if price_element:
            price_text = price_element.get_text().strip()
            # Extract price from text like "Precio desde 104,20 €"
            price_match = re.search(r'([\d,]+(?:\.\d{2})?)\s*€', price_text)
            if price_match:
                price_str = price_match.group(1).replace(',', '.')
                trayecto["prices"] = [price_str + ' €']
        
        # Only add if we have at least departure time
        if "salida" in trayecto:
            result.tickets.append(trayecto)
    
    print(f"\n=== PARSING RESULTS ===")
    print(f"Total trains parsed: {len(result.tickets)}")
    
    # Group by train type for summary
    by_type = {}
    for train in result.tickets:
        train_type = train.get('tipo', 'Unknown')
        if train_type not in by_type:
            by_type[train_type] = []
        by_type[train_type].append(train)
    
    for train_type, trains in by_type.items():
        print(f"\n{train_type} trains: {len(trains)}")
        for train in trains[:3]:  # Show first 3 of each type
            price = train.get('prices', ['No price'])[0]
            print(f"  {train.get('salida')} -> {train.get('llegada')} ({train.get('duracion', '?')}) - {price}")
        if len(trains) > 3:
            print(f"  ... and {len(trains) - 3} more")
    
    # Test price extraction and conversion
    print(f"\n=== PRICE ANALYSIS ===")
    prices = []
    for train in result.tickets:
        if train.get('prices'):
            price_str = train['prices'][0]
            # Convert to float for analysis
            price_float = float(price_str.replace(' €', '').replace(',', '.'))
            prices.append(price_float)
    
    if prices:
        print(f"Price range: {min(prices):.2f}€ - {max(prices):.2f}€")
        print(f"Average price: {sum(prices)/len(prices):.2f}€")
        print(f"Trains with prices: {len(prices)}/{len(result.tickets)}")
    
    return result

if __name__ == "__main__":
    test_parsing_logic()
