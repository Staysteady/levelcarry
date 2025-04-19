import re
import pdfplumber
from datetime import datetime, timedelta
import pandas as pd
from pathlib import Path
from typing import Dict, List, Tuple, Optional


def parse_date(date_str: str) -> datetime:
    """Parse date in the format DD-MM-YY to datetime object."""
    try:
        return datetime.strptime(date_str, '%d-%m-%y')
    except ValueError:
        return None


def extract_spread_data_from_pdf(pdf_path: str, area: Tuple[float, float, float, float] = None) -> Dict:
    """
    Extract spread date ranges and per day valuations from LME PDF files,
    focusing specifically on the C-3M section in the red box.
    
    Args:
        pdf_path: Path to the PDF file
        area: Optional tuple (x0, y0, x1, y1) defining the area to extract from
              Default area focuses on the 'Per Day' section in the red box
    
    Returns:
        Dictionary with spread data in the format:
        {
            "metal": str,  # Metal code (e.g., "AH", "ZS")
            "spreads": [
                {
                    "prompt_name": str,     # The section name (e.g., "Cash-May", "May-Jun")
                    "start_date": datetime,  # First leg of spread
                    "end_date": datetime,    # Second leg of spread
                    "value": float,          # Spread value
                    "per_day": float         # Per day valuation
                },
                ...
            ],
            "c3m_total": float,  # Total C-3M value
            "cash_date": datetime, # The cash date found
            "three_month_date": datetime # The 3M date found
        }
    """
    # Get metal code from filename
    metal = Path(pdf_path).stem[:2].upper()
    
    result = {
        "metal": metal,
        "spreads": [],
        "c3m_total": None,
        "cash_date": None,
        "three_month_date": None
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]  # We only need the first page
            
            # Extract text from the whole page first
            text = page.extract_text()
            
            # Split into lines
            lines = text.split('\n')
            
            # Flag to indicate we've found the "Per Day" section
            in_per_day_section = False
            
            # Find the "Per Day" section first
            per_day_index = -1
            for i, line in enumerate(lines):
                if "Per Day" in line:
                    per_day_index = i
                    break
            
            if per_day_index == -1:
                print("Could not find 'Per Day' section")
                return result
            
            # Now look for the C line (which contains the date format)
            c_line_index = -1
            for i in range(per_day_index, min(per_day_index + 10, len(lines))):
                if lines[i].strip().startswith('C '):
                    c_line_index = i
                    break
            
            # Extract dates from the red box area
            # First find the green box data with start and end dates
            date_pattern = r'(\d{1,2}-\d{1,2}-\d{2})'
            
            # Initialize variables to track the cash date and 3m date
            cash_date = None
            three_m_date = None
            
            # Track any sections we find (Cash-May, May-Jun, Jun-Jul, Jul-3M)
            sections = []
            
            # First, look for Cash - 3s value in the right section
            cash_3s_value = None
            for i, line in enumerate(lines):
                if "Cash - 3s" in line:
                    try:
                        cash_3s_value_match = re.search(r'Cash - 3s\s+(-?\d+\.\d+)', line)
                        if cash_3s_value_match:
                            cash_3s_value = float(cash_3s_value_match.group(1))
                        else:
                            # It might be on the next line
                            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                            if next_line and re.match(r'^-?\d+\.\d+$', next_line):
                                cash_3s_value = float(next_line)
                    except (ValueError, IndexError):
                        pass
            
            if cash_3s_value:
                result["c3m_total"] = cash_3s_value
            
            # Look for date ranges in the red box area
            # We're looking for lines like "17-4-25  21-5-25  -3.5  -0.7  2337.44"
            found_green_box = False
            
            for i in range(per_day_index + 1, len(lines)):
                line = lines[i].strip()
                
                # Stop if we've reached the end of the Per Day section
                if "Outright" in line or "DISCLAIMER" in line:
                    break
                
                # Look for date patterns and capture the per-day value
                date_matches = re.findall(date_pattern, line)
                
                if len(date_matches) >= 2:
                    found_green_box = True
                    
                    # Extract start and end dates
                    start_date_str = date_matches[0]
                    end_date_str = date_matches[1]
                    
                    start_date = parse_date(start_date_str)
                    end_date = parse_date(end_date_str)
                    
                    # Track cash date (first date in green box)
                    if cash_date is None and start_date:
                        cash_date = start_date
                    
                    # Track 3m date (last date in green box)
                    if end_date:
                        three_m_date = end_date
                    
                    # Find the spread value and per-day value
                    # Pattern typically looks like: date date value per_day price
                    # Example: "17-4-25  21-5-25  -3.5  -0.7  2337.44"
                    parts = line.split()
                    
                    value = None
                    per_day = None
                    
                    # Find per-day value (usually the 4th value after the dates)
                    date_indices = []
                    for j, part in enumerate(parts):
                        if re.match(date_pattern, part):
                            date_indices.append(j)
                    
                    if len(date_indices) >= 2:
                        # The value should be right after the second date
                        try:
                            value_index = date_indices[1] + 1
                            per_day_index = date_indices[1] + 2
                            
                            if value_index < len(parts):
                                value = float(parts[value_index])
                            
                            if per_day_index < len(parts):
                                per_day = float(parts[per_day_index])
                        except (ValueError, IndexError):
                            # Try pattern matching instead
                            value_match = re.search(r'{}.*?{}.*?(-?\d+\.?\d*)'.format(
                                re.escape(start_date_str), re.escape(end_date_str)), line)
                            per_day_match = re.search(r'{}.*?{}.*?-?\d+\.?\d*\s+(-?\d+\.?\d*)'.format(
                                re.escape(start_date_str), re.escape(end_date_str)), line)
                            
                            if value_match:
                                try:
                                    value = float(value_match.group(1))
                                except ValueError:
                                    pass
                            
                            if per_day_match:
                                try:
                                    per_day = float(per_day_match.group(1))
                                except ValueError:
                                    pass
                    
                    # If we have valid dates and values, add to spreads
                    if start_date and end_date and (value is not None or per_day is not None):
                        spread = {
                            "start_date": start_date,
                            "end_date": end_date,
                            "value": value if value is not None else 0.0,
                            "per_day": per_day if per_day is not None else 0.0
                        }
                        
                        # Determine which section this is
                        # First date is cash date
                        if start_date.day == cash_date.day and start_date.month == cash_date.month:
                            # Find third Wednesday of the end_date's month
                            year = end_date.year
                            month = end_date.month
                            
                            # Get first day of the month
                            first_day = datetime(year, month, 1)
                            # Find first Wednesday
                            first_wednesday = first_day + timedelta(days=(2 - first_day.weekday()) % 7)
                            # Find third Wednesday
                            third_wednesday = first_wednesday + timedelta(days=14)
                            
                            if end_date.day == third_wednesday.day:
                                # This is Cash-May (or Cash-Jun, etc.)
                                month_name = end_date.strftime('%b')
                                spread["prompt_name"] = f"Cash-{month_name}"
                            else:
                                spread["prompt_name"] = f"Cash-Other"
                        else:
                            # Check if it's month to month (e.g., May-Jun)
                            start_month = start_date.strftime('%b')
                            end_month = end_date.strftime('%b')
                            
                            if start_month != end_month:
                                spread["prompt_name"] = f"{start_month}-{end_month}"
                            else:
                                # Same month, so something like "Early May-Late May"
                                # Just use the dates for clarity
                                spread["prompt_name"] = f"{start_date.strftime('%d-%b')}-{end_date.strftime('%d-%b')}"
                        
                        result["spreads"].append(spread)
            
            # Now look for the Cash-May, May-Jun, Jun-Jul, Jul-3M sections
            # These are typically in the "Dec - Dec Averages" section
            section_names = ["Cash - May", "May - Jun", "Jun - Jul", "Jul - 3m", "Cash - 3s"]
            
            for section_name in section_names:
                for i, line in enumerate(lines):
                    if section_name in line:
                        try:
                            # Value might be on the same line or next line
                            value_match = re.search(r'{}\s+(-?\d+\.?\d*)'.format(re.escape(section_name)), line)
                            if value_match:
                                value = float(value_match.group(1))
                                
                                # For the section breakdown, we don't always have per-day values
                                # So we'll record just the total value
                                if section_name == "Cash - 3s" and result["c3m_total"] is None:
                                    result["c3m_total"] = value
                                elif section_name != "Cash - 3s":
                                    # Add to spreads with placeholder dates
                                    # In a real implementation, we'd need logic to determine the actual dates
                                    # based on cash date and prompt dates
                                    section = {
                                        "prompt_name": section_name.replace(" - ", "-"),
                                        "value": value,
                                        "per_day": None,  # We typically don't have per-day for these sections
                                        "start_date": None,
                                        "end_date": None
                                    }
                                    
                                    # Only add if not a duplicate
                                    if not any(s["prompt_name"] == section["prompt_name"] for s in result["spreads"]):
                                        result["spreads"].append(section)
                            else:
                                # Check next line for the value
                                next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                                if next_line and re.match(r'^-?\d+\.?\d+$', next_line):
                                    value = float(next_line)
                                    
                                    if section_name == "Cash - 3s" and result["c3m_total"] is None:
                                        result["c3m_total"] = value
                                    elif section_name != "Cash - 3s":
                                        section = {
                                            "prompt_name": section_name.replace(" - ", "-"),
                                            "value": value,
                                            "per_day": None,
                                            "start_date": None,
                                            "end_date": None
                                        }
                                        
                                        if not any(s["prompt_name"] == section["prompt_name"] for s in result["spreads"]):
                                            result["spreads"].append(section)
                        except (ValueError, IndexError):
                            pass
            
            # Store the cash date and 3m date
            result["cash_date"] = cash_date
            result["three_month_date"] = three_m_date
            
    except Exception as e:
        print(f"Error extracting data from PDF {pdf_path}: {str(e)}")
    
    return result


def calculate_valuation(spreads: List[Dict], cash_date: datetime, three_month_date: datetime) -> Optional[float]:
    """
    Calculate the valuation for a specific date range using the extracted spread data.
    
    Args:
        spreads: List of spread dictionaries from extract_spread_data_from_pdf
        cash_date: The cash date to use for calculation
        three_month_date: The three month date to use for calculation
        
    Returns:
        Calculated valuation or None if not found
    """
    # Validate dates
    if not cash_date or not three_month_date or cash_date >= three_month_date:
        return None
    
    # Calculate days between the dates
    days_between = (three_month_date - cash_date).days
    
    # Check if we have a direct match for the entire cash to 3m period
    for spread in spreads:
        if "prompt_name" in spread and spread["prompt_name"] == "Cash-3s":
            return spread["value"]
    
    # If we have section data (Cash-May, May-Jun, etc.), try to calculate from that
    section_values = []
    for spread in spreads:
        if "prompt_name" in spread and spread["prompt_name"] in ["Cash-May", "May-Jun", "Jun-Jul", "Jul-3m"]:
            section_values.append((spread["prompt_name"], spread["value"]))
    
    if section_values:
        # Simple sum of sections for now - in reality, you'd need to weight by days
        total = sum(value for _, value in section_values)
        return total
    
    # If we have per-day rates, use those
    total_valuation = 0
    remaining_days = days_between
    
    # Sort spreads by start date to process them in order
    valid_spreads = [s for s in spreads if s["start_date"] and s["end_date"] and s["per_day"] is not None]
    valid_spreads.sort(key=lambda s: s["start_date"])
    
    current_date = cash_date
    while current_date < three_month_date and remaining_days > 0 and valid_spreads:
        for spread in valid_spreads:
            if spread["start_date"] <= current_date and spread["end_date"] > current_date:
                # Found a spread that covers our current date
                days_in_spread = min(remaining_days, (spread["end_date"] - current_date).days)
                total_valuation += spread["per_day"] * days_in_spread
                current_date += timedelta(days=days_in_spread)
                remaining_days -= days_in_spread
                break
        else:
            # No spread found for current date, move to next date
            current_date += timedelta(days=1)
            remaining_days -= 1
    
    if remaining_days < days_between:
        # We were able to calculate at least part of the valuation
        return total_valuation
    
    return None


def extract_spreads_from_all_pdfs(pdf_directory: str) -> Dict[str, Dict]:
    """
    Extract spread data from all PDFs in a directory.
    
    Args:
        pdf_directory: Directory containing PDF files
        
    Returns:
        Dictionary mapping metal codes to their spread data
    """
    result = {}
    
    # Process all PDFs in the directory
    for pdf_path in Path(pdf_directory).glob('*.pdf'):
        extracted_data = extract_spread_data_from_pdf(str(pdf_path))
        
        if extracted_data and (extracted_data["spreads"] or extracted_data["c3m_total"] is not None):
            metal = extracted_data["metal"]
            result[metal] = extracted_data
    
    return result


if __name__ == "__main__":
    # Example usage
    pdf_dir = "data"
    spreads_data = extract_spreads_from_all_pdfs(pdf_dir)
    
    # Example printing the extracted data
    for metal, data in spreads_data.items():
        print(f"Metal: {metal}")
        print(f"C-3M Total: {data['c3m_total']}")
        print(f"Cash Date: {data['cash_date'].strftime('%d-%m-%y') if data['cash_date'] else 'None'}")
        print(f"3M Date: {data['three_month_date'].strftime('%d-%m-%y') if data['three_month_date'] else 'None'}")
        
        print("Spreads:")
        for spread in data["spreads"]:
            prompt_name = spread.get("prompt_name", "Unknown")
            start_date = spread["start_date"].strftime('%d-%m-%y') if spread["start_date"] else "None"
            end_date = spread["end_date"].strftime('%d-%m-%y') if spread["end_date"] else "None"
            value = spread["value"] if spread["value"] is not None else "None"
            per_day = spread["per_day"] if spread["per_day"] is not None else "None"
            
            print(f"  {prompt_name}: {start_date} to {end_date}, Value: {value}, Per Day: {per_day}")
        
        # If we have cash and 3m dates, show a calculation example
        if data['cash_date'] and data['three_month_date']:
            valuation = calculate_valuation(data["spreads"], data['cash_date'], data['three_month_date'])
            print(f"Calculated C-3M Valuation: {valuation}")
            print(f"Reported C-3M Valuation: {data['c3m_total']}")
            if valuation is not None and data['c3m_total'] is not None:
                print(f"Difference: {valuation - data['c3m_total']}")
        
        print() 