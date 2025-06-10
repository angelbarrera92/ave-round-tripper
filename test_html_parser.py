#!/usr/bin/env python3
"""
Test script to validate the HTML parser against the saved debug results page.
This allows us to test the parser logic without running the full scraper.
"""

import re
from bs4 import BeautifulSoup


def test_html_parsing():
    """Test the HTML parsing logic against the saved debug page."""
    
    print("Starting HTML parsing test...")
    
    # Read the saved HTML file
    try:
        with open('/Users/barreang/personal/ave-round-tripper/debug_results_page.html', 'r', encoding='utf-8') as f:
            html_content = f.read()
        print(f"Successfully read HTML file: {len(html_content)} characters")
    except Exception as e:
        print(f"Error reading HTML file: {e}")
        return []
    
    soup = BeautifulSoup(html_content, "html.parser")
    print("Created BeautifulSoup object")
    
    # Look for train entries - updated to match current RENFE structure
    train_elements = soup.find_all('div', class_='selectedTren')
    
    print(f"Found {len(train_elements)} train entries with class 'selectedTren'")
    
    # If no elements found, let's search for what we have
    if not train_elements:
        # Let's search for any div that might contain train data
        print("No 'selectedTren' elements found, searching for alternative patterns...")
        
        # Search for divs containing time patterns
        all_divs = soup.find_all('div')
        print(f"Total divs in page: {len(all_divs)}")
        
        potential_train_divs = []
        for div in all_divs:
            text = div.get_text()
            if re.search(r'\d{1,2}:\d{2}', text):
                potential_train_divs.append(div)
        
        print(f"Found {len(potential_train_divs)} divs containing time patterns")
        
        # Check for specific train-related classes
        train_related_classes = ['tren', 'train', 'viaje', 'journey', 'selectedTren']
        for class_name in train_related_classes:
            elements = soup.find_all(class_=re.compile(class_name, re.IGNORECASE))
            print(f"Elements with class containing '{class_name}': {len(elements)}")
            if elements and class_name == 'selectedTren':
                train_elements = elements
        
        return []
    
    parsed_trains = []
    
    for i, train_element in enumerate(train_elements):
        print(f"\n--- Train {i+1} ---")
        trayecto = {}
        
        # Extract departure and arrival times from h5 elements
        time_elements = train_element.find_all('h5', {'aria-hidden': 'true'})
        print(f"Found {len(time_elements)} time elements")
        
        if len(time_elements) >= 2:
            # First h5 is departure, last h5 is arrival
            departure_text = time_elements[0].get_text().strip()
            arrival_text = time_elements[-1].get_text().strip()
            
            print(f"Departure text: '{departure_text}'")
            print(f"Arrival text: '{arrival_text}'")
            
            # Extract time from text like "17:57 h"
            dep_match = re.search(r'(\d{1,2}:\d{2})', departure_text)
            arr_match = re.search(r'(\d{1,2}:\d{2})', arrival_text)
            
            if dep_match and arr_match:
                trayecto["salida"] = dep_match.group(1)
                trayecto["llegada"] = arr_match.group(1)
                print(f"Extracted times: {trayecto['salida']} -> {trayecto['llegada']}")
        
        # Extract train type from image alt text
        train_img = train_element.find('img', alt=re.compile(r'Tipo de tren', re.IGNORECASE))
        if train_img:
            alt_text = train_img.get('alt', '')
            print(f"Train image alt text: '{alt_text}'")
            # Extract train type from alt text like "Imagen de Tren. Tipo de tren AVE"
            train_type_match = re.search(r'Tipo de tren (\w+)', alt_text, re.IGNORECASE)
            if train_type_match:
                trayecto["tipo"] = train_type_match.group(1).upper()
                print(f"Extracted train type: {trayecto['tipo']}")
        
        # Extract duration from aria-label
        duration_span = train_element.find('span', {'aria-label': re.compile(r'Duración', re.IGNORECASE)})
        if duration_span:
            duration_text = duration_span.get('aria-label', '')
            print(f"Duration aria-label: '{duration_text}'")
            # Extract duration from text like "Duración 2 horas 37 minutos."
            duration_match = re.search(r'(\d+)\s+horas?\s+(\d+)\s+minutos?', duration_text, re.IGNORECASE)
            if duration_match:
                hours = duration_match.group(1)
                minutes = duration_match.group(2)
                trayecto["duracion"] = f"{hours}h {minutes}min"
                print(f"Extracted duration: {trayecto['duracion']}")
            else:
                # Try simpler pattern
                duration_match = re.search(r'(\d+)\s+horas?', duration_text, re.IGNORECASE)
                if duration_match:
                    trayecto["duracion"] = f"{duration_match.group(1)}h"
                    print(f"Extracted simple duration: {trayecto['duracion']}")
        
        # Extract price from precio-final span
        price_element = train_element.find('span', class_='precio-final')
        if price_element:
            price_text = price_element.get_text().strip()
            print(f"Price text: '{price_text}'")
            # Extract price from text like "Precio desde 104,20 €"
            price_match = re.search(r'([\d,]+(?:\.\d{2})?)\s*€', price_text)
            if price_match:
                price_str = price_match.group(1).replace(',', '.')
                trayecto["prices"] = [price_str + ' €']
                print(f"Extracted price: {trayecto['prices']}")
        
        # Only add if we have at least departure time
        if "salida" in trayecto:
            print(f"✅ Successfully parsed train: {trayecto}")
            parsed_trains.append(trayecto)
        else:
            print("❌ Skipping train element - no departure time found")
            print(f"Element text preview: {train_element.get_text()[:200]}...")
    
    print(f"\n=== SUMMARY ===")
    print(f"Total trains parsed: {len(parsed_trains)}")
    for i, train in enumerate(parsed_trains):
        print(f"Train {i+1}: {train.get('salida', '?')} -> {train.get('llegada', '?')} "
              f"({train.get('tipo', '?')}) - {train.get('prices', ['?'])[0] if train.get('prices') else '?'}")
    
    return parsed_trains


if __name__ == "__main__":
    test_html_parsing()
