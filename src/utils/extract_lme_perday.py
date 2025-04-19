"""
LME Per-Day Value Extractor

A focused utility for extracting per-day values from the red box area in LME forward curve PDFs.
This utility specifically extracts the C-3M section between cash date and 3-month date.
"""

import re
import pdfplumber
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple, Optional
import holidays


def parse_date(date_str: str) -> Optional[datetime]:
    """Parse date in the format DD-MM-YY to datetime object."""
    try:
        return datetime.strptime(date_str, '%d-%m-%y')
    except ValueError:
        return None


def get_third_wednesday(year: int, month: int) -> datetime:
    """Return the third Wednesday of the given month and year."""
    # Get first day of the month
    first_day = datetime(year, month, 1)
    # Find first Wednesday (weekday 2)
    first_wednesday = first_day + timedelta(days=(2 - first_day.weekday()) % 7)
    # Find third Wednesday
    third_wednesday = first_wednesday + timedelta(days=14)
    
    return third_wednesday


def extract_lme_perday(pdf_path: str) -> Dict:
    """
    Extract per-day values from the red box section in LME PDF.
    
    Args:
        pdf_path: Path to the PDF file
        
    Returns:
        Dictionary with extracted data:
        {
            "c3m_value": float,            # Total C-3M value from PDF
            "cash_date": datetime,         # Cash date found in PDF
            "three_month_date": datetime,  # 3M date found in PDF
            "per_day_values": [            # List of per-day values for date ranges
                {
                    "start_date": datetime,
                    "end_date": datetime,
                    "value": float,        # Spread value
                    "per_day": float,      # Per day valuation
                    "prompt_name": str,    # Name of the spread (e.g., "Cash-May")
                    "is_summary": bool     # Whether this is a summary section or detailed range
                },
                ...
            ],
            "sections": [                  # Breakdown of sections if available
                {
                    "name": str,           # Section name (e.g., "Cash-May")
                    "value": float         # Section value
                },
                ...
            ],
            "daily_curve": {               # Day-by-day per-day values
                "YYYY-MM-DD": float,       # Per-day value for each date
                ...
            }
        }
    """
    result = {
        "c3m_value": None,
        "cash_date": None,
        "three_month_date": None,
        "per_day_values": [],
        "sections": [],
        "daily_curve": {}
    }
    
    try:
        with pdfplumber.open(pdf_path) as pdf:
            page = pdf.pages[0]  # We only need the first page
            text = page.extract_text()
            lines = text.split('\n')
            
            # Find the "Per Day" section
            per_day_index = -1
            for i, line in enumerate(lines):
                if "Per Day" in line:
                    per_day_index = i
                    break
            
            if per_day_index == -1:
                print("Could not find 'Per Day' section")
                return result
            
            # Debug: print Per Day section and surrounding lines
            print("==== Per Day Section ====")
            for i in range(max(0, per_day_index-1), min(len(lines), per_day_index+20)):
                print(f"Line {i}: {lines[i]}")
            
            # Look for Cash-3s value
            cash_3s_value = None
            for i, line in enumerate(lines):
                if "Cash - 3s" in line or "Cash-3s" in line:
                    try:
                        # Try to extract value from same line
                        cash_3s_match = re.search(r'Cash[ -]+3s\s+(-?\d+\.?\d*)', line)
                        if cash_3s_match:
                            cash_3s_value = float(cash_3s_match.group(1))
                            print(f"Found Cash-3s value: {cash_3s_value}")
                        else:
                            # Try next line for value
                            next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
                            if next_line and re.match(r'^-?\d+\.?\d*$', next_line):
                                cash_3s_value = float(next_line)
                                print(f"Found Cash-3s value on next line: {cash_3s_value}")
                    except (ValueError, IndexError) as e:
                        print(f"Error extracting Cash-3s value: {e}")
            
            if cash_3s_value is not None:
                result["c3m_value"] = cash_3s_value
            
            # Extract dates and per-day values from the red box
            date_pattern = r'(\d{1,2}-\d{1,2}-\d{2})'
            cash_date = None
            three_m_date = None
            
            # UNIVERSAL DATA EXTRACTION APPROACH
            # This approach treats all PDFs consistently regardless of metal type
            
            # STEP 1: Detect all date pairs anywhere in the document
            print("Scanning entire document for all date pairs...")
            date_containing_lines = []
            
            # First collect all lines with date patterns
            for i, line in enumerate(lines):
                if re.search(date_pattern, line):
                    date_containing_lines.append((i, line))
            
            # Next extract all valid date pairs and their associated values
            all_date_pairs = []
            
            for i, line in date_containing_lines:
                date_matches = re.findall(date_pattern, line)
                if len(date_matches) >= 2:
                    # Split the line into parts
                    parts = line.split()
                    
                    # Find positions of all dates in the line
                    date_positions = []
                    for j, part in enumerate(parts):
                        if re.match(date_pattern, part):
                            date_positions.append(j)
                    
                    # For each pair of adjacent dates
                    for d in range(len(date_positions) - 1):
                        try:
                            start_pos = date_positions[d]
                            end_pos = date_positions[d+1]
                            
                            start_date_str = parts[start_pos]
                            end_date_str = parts[end_pos]
                            
                            start_date = parse_date(start_date_str)
                            end_date = parse_date(end_date_str)
                            
                            if not start_date or not end_date:
                                continue
                            
                            # Look for value after the end date
                            value = None
                            per_day = None
                            
                            # Look for a value after the end date
                            if end_pos + 1 < len(parts):
                                try:
                                    value_str = parts[end_pos + 1]
                                    if re.match(r'^-?\d+\.?\d*$', value_str):
                                        value = float(value_str)
                                except ValueError:
                                    pass
                            
                            # Look for per_day value
                            if end_pos + 2 < len(parts):
                                try:
                                    per_day_str = parts[end_pos + 2]
                                    if re.match(r'^-?\d+\.?\d*$', per_day_str):
                                        per_day = float(per_day_str)
                                except ValueError:
                                    pass
                            
                            # If we found at least a value, this is a valid date pair
                            if value is not None:
                                all_date_pairs.append({
                                    "start_date": start_date,
                                    "end_date": end_date,
                                    "value": value,
                                    "per_day": per_day,
                                    "line_index": i
                                })
                                print(f"Found date pair: {start_date_str} to {end_date_str}, value: {value}, per_day: {per_day}")
                        except Exception as e:
                            print(f"Error processing date pair on line {i}: {e}")
            
            # STEP 2: Also handle single dates that might be part of date ranges
            for i, line in date_containing_lines:
                date_matches = re.findall(date_pattern, line)
                if len(date_matches) == 1:
                    # This line contains exactly one date - might be part of a range
                    # Look at nearby lines for potential matches
                    date_str = date_matches[0]
                    date = parse_date(date_str)
                    
                    if not date:
                        continue
                    
                    # Extract numbers from current line
                    numbers = [float(n) for n in re.findall(r'-?\d+\.?\d*', line) 
                              if n != date_str and re.match(r'^-?\d+\.?\d*$', n)]
                    
                    # Look at nearby lines for additional dates
                    for j in range(max(0, i-2), min(len(lines), i+3)):
                        if j == i:
                            continue  # Skip current line
                            
                        nearby_line = lines[j]
                        nearby_dates = re.findall(date_pattern, nearby_line)
                        
                        for nearby_date_str in nearby_dates:
                            nearby_date = parse_date(nearby_date_str)
                            if not nearby_date or nearby_date == date:
                                continue
                            
                            # See if we can determine a valid pair
                            valid_pair = False
                            value = None
                            
                            # Check if there's a plausible value
                            if numbers and len(numbers) > 0:
                                value = numbers[0]  # Use first number as value
                                valid_pair = True
                            else:
                                # Try to extract numbers from nearby line
                                nearby_numbers = [float(n) for n in re.findall(r'-?\d+\.?\d*', nearby_line) 
                                               if n != nearby_date_str and re.match(r'^-?\d+\.?\d*$', n)]
                                if nearby_numbers and len(nearby_numbers) > 0:
                                    value = nearby_numbers[0]
                                    valid_pair = True
                            
                            if valid_pair and value is not None:
                                # Determine which is start/end date
                                if date < nearby_date:
                                    start_date, end_date = date, nearby_date
                                else:
                                    start_date, end_date = nearby_date, date
                                
                                # Calculate per_day if not found
                                days = (end_date - start_date).days
                                per_day = value / days if days > 0 else 0
                                
                                all_date_pairs.append({
                                    "start_date": start_date,
                                    "end_date": end_date,
                                    "value": value,
                                    "per_day": per_day,
                                    "line_index": i
                                })
                                print(f"Found cross-line date pair: {start_date.strftime('%d-%m-%y')} to {end_date.strftime('%d-%m-%y')}, value: {value}")
            
            # STEP 3: Find dedicated section blocks with multiple date pairs
            section_starts = []
            for i, line in date_containing_lines:
                # Check if this line might be a section header
                if line.count('-') >= 2 and not any(c.isalpha() for c in line):
                    # This line contains only dates and possibly other non-alphabetic symbols 
                    # Could be a section header
                    section_starts.append(i)
            
            # Process each potential section
            for start_idx in section_starts:
                # Look for date pairs in following lines
                for j in range(start_idx + 1, min(len(lines), start_idx + 10)):
                    line = lines[j]
                    date_matches = re.findall(date_pattern, line)
                    if len(date_matches) >= 2:
                        parts = line.split()
                        date_positions = []
                        for k, part in enumerate(parts):
                            if re.match(date_pattern, part):
                                date_positions.append(k)
                        
                        if len(date_positions) >= 2:
                            start_date_str = parts[date_positions[0]]
                            end_date_str = parts[date_positions[1]]
                            
                            start_date = parse_date(start_date_str)
                            end_date = parse_date(end_date_str)
                            
                            if not start_date or not end_date:
                                continue
                            
                            # Look for value
                            value = None
                            
                            # Check if there's a value after the second date
                            if date_positions[1] + 1 < len(parts):
                                try:
                                    value_str = parts[date_positions[1] + 1]
                                    if re.match(r'^-?\d+\.?\d*$', value_str):
                                        value = float(value_str)
                                except ValueError:
                                    pass
                            
                            if value is not None:
                                days = (end_date - start_date).days
                                per_day = value / days if days > 0 else 0
                                
                                all_date_pairs.append({
                                    "start_date": start_date,
                                    "end_date": end_date,
                                    "value": value,
                                    "per_day": per_day,
                                    "line_index": j
                                })
                                print(f"Found section date pair: {start_date_str} to {end_date_str}, value: {value}")
            
            # STEP 4: Extract standard sections like Cash-May, May-Jun, etc.
            section_names = [
                "Cash-May", "Cash - May", 
                "May-Jun", "May - Jun", 
                "Jun-Jul", "Jun - Jul", 
                "Jul-3m", "Jul - 3m", 
                "May-3s", "May - 3s",
                "Jun-3s", "Jun - 3s"
            ]
            
            sections_found = []
            for section_name in section_names:
                for i, line in enumerate(lines):
                    if section_name in line:
                        value = None
                        
                        # Try to find value in this line
                        pattern = r'{}\s+(-?\d+\.?\d*)'.format(re.escape(section_name))
                        value_match = re.search(pattern, line)
                        if value_match:
                            try:
                                value = float(value_match.group(1))
                                print(f"Found section {section_name}: {value}")
                            except ValueError:
                                pass
                        
                        # Try next line for value
                        if value is None and i + 1 < len(lines):
                            next_line = lines[i + 1].strip()
                            if re.match(r'^-?\d+\.?\d+$', next_line):
                                try:
                                    value = float(next_line)
                                    print(f"Found section {section_name} on next line: {value}")
                                except ValueError:
                                    pass
                        
                        if value is not None:
                            # Add this section to our results
                            sections_found.append({
                                "name": section_name.replace(" - ", "-"),
                                "value": value,
                                "line_index": i
                            })
                            result["sections"].append({
                                "name": section_name.replace(" - ", "-"),
                                "value": value
                            })
                            break
            
            # STEP 5: Determine cash_date and three_m_date
            # First look near the beginning for cash date
            for pair in all_date_pairs:
                if cash_date is None:
                    cash_date = pair["start_date"]
                    break
            
            # Then find the furthest date as the 3M date
            for pair in all_date_pairs:
                if three_m_date is None or pair["end_date"] > three_m_date:
                    three_m_date = pair["end_date"]
            
            # STEP 6: Create per_day_values from the date pairs we found
            processed_pairs = set()  # Track processed pairs to avoid duplicates
            
            # First add all the date pairs we found directly
            for pair in all_date_pairs:
                pair_key = (pair["start_date"], pair["end_date"])
                if pair_key in processed_pairs:
                    continue
                
                processed_pairs.add(pair_key)
                
                # Determine if this might be a summary section
                is_summary = False
                # Check if this pair spans a longer range
                for other_pair in all_date_pairs:
                    if (pair["start_date"] == other_pair["start_date"] and 
                        pair["end_date"] > other_pair["end_date"]):
                        is_summary = True
                        break
                
                # Create prompt name
                prompt_name = determine_prompt_name(pair["start_date"], pair["end_date"])
                
                # Add to result
                entry = {
                    "start_date": pair["start_date"],
                    "end_date": pair["end_date"],
                    "value": pair["value"],
                    "per_day": pair["per_day"],
                    "prompt_name": prompt_name,
                    "is_summary": is_summary
                }
                result["per_day_values"].append(entry)
            
            # STEP 7: Create date pair entries from section data if not already present
            for section in sections_found:
                section_name = section["name"]
                
                # Handle Cash-May section
                if section_name == "Cash-May" and cash_date:
                    # Look for May date
                    may_date = None
                    for date in [pair["end_date"] for pair in all_date_pairs]:
                        if date.month == 5 and (may_date is None or date > may_date):
                            may_date = date
                    
                    if may_date:
                        pair_key = (cash_date, may_date)
                        if pair_key not in processed_pairs:
                            processed_pairs.add(pair_key)
                            days = (may_date - cash_date).days
                            per_day = section["value"] / days if days > 0 else 0
                            
                            entry = {
                                "start_date": cash_date,
                                "end_date": may_date,
                                "value": section["value"],
                                "per_day": per_day,
                                "prompt_name": "Cash-May",
                                "is_summary": True
                            }
                            result["per_day_values"].append(entry)
                            print(f"Created Cash-May entry from section: {cash_date} to {may_date}, value: {section['value']}")
                
                # Handle May-Jun section
                elif section_name == "May-Jun":
                    # Find May and June dates
                    may_date = None
                    jun_date = None
                    
                    for date in [pair["end_date"] for pair in all_date_pairs]:
                        if date.month == 5 and (may_date is None or date > may_date):
                            may_date = date
                        elif date.month == 6 and (jun_date is None or date > jun_date):
                            jun_date = date
                    
                    if may_date and jun_date:
                        pair_key = (may_date, jun_date)
                        if pair_key not in processed_pairs:
                            processed_pairs.add(pair_key)
                            days = (jun_date - may_date).days
                            per_day = section["value"] / days if days > 0 else 0
                            
                            entry = {
                                "start_date": may_date,
                                "end_date": jun_date,
                                "value": section["value"],
                                "per_day": per_day,
                                "prompt_name": "May-Jun",
                                "is_summary": True
                            }
                            result["per_day_values"].append(entry)
                            print(f"Created May-Jun entry from section: {may_date} to {jun_date}, value: {section['value']}")
                
                # Handle Jun-Jul section
                elif section_name == "Jun-Jul":
                    # Find June and July dates
                    jun_date = None
                    jul_date = None
                    
                    for date in [pair["end_date"] for pair in all_date_pairs]:
                        if date.month == 6 and (jun_date is None or date > jun_date):
                            jun_date = date
                        elif date.month == 7 and (jul_date is None or date > jul_date):
                            jul_date = date
                    
                    if jun_date and jul_date:
                        pair_key = (jun_date, jul_date)
                        if pair_key not in processed_pairs:
                            processed_pairs.add(pair_key)
                            days = (jul_date - jun_date).days
                            per_day = section["value"] / days if days > 0 else 0
                            
                            entry = {
                                "start_date": jun_date,
                                "end_date": jul_date,
                                "value": section["value"],
                                "per_day": per_day,
                                "prompt_name": "Jun-Jul",
                                "is_summary": True
                            }
                            result["per_day_values"].append(entry)
                            print(f"Created Jun-Jul entry from section: {jun_date} to {jul_date}, value: {section['value']}")
            
            # STEP 8: If we have Cash-3s section and cash_date/three_m_date, add the Cash-3M entry
            if cash_date and three_m_date and cash_3s_value is not None:
                pair_key = (cash_date, three_m_date)
                if pair_key not in processed_pairs:
                    processed_pairs.add(pair_key)
                    days = (three_m_date - cash_date).days
                    per_day = cash_3s_value / days if days > 0 else 0
                    
                    entry = {
                        "start_date": cash_date,
                        "end_date": three_m_date,
                        "value": cash_3s_value,
                        "per_day": per_day,
                        "prompt_name": "Cash-3M",
                        "is_summary": True
                    }
                    result["per_day_values"].append(entry)
                    print(f"Created Cash-3M entry: {cash_date} to {three_m_date}, value: {cash_3s_value}")
            
            # STEP 9: Final updates to the result
            result["cash_date"] = cash_date
            result["three_month_date"] = three_m_date
            
            # STEP 10: Ensure we have the most recent end date from all date pairs
            latest_date = None
            for entry in result["per_day_values"]:
                if entry["end_date"] and (latest_date is None or entry["end_date"] > latest_date):
                    latest_date = entry["end_date"]
            
            if latest_date and (three_m_date is None or latest_date > three_m_date):
                print(f"Updating final three_month_date to {latest_date}")
                three_m_date = latest_date
                result["three_month_date"] = three_m_date
            
            # STEP 11: Build the daily curve based on all the data we've collected
            if cash_date and three_m_date:
                result["daily_curve"] = build_daily_curve(result["per_day_values"], cash_date, three_m_date)
    
    except Exception as e:
        print(f"Error extracting data from PDF {pdf_path}: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return result


def determine_prompt_name(start_date: datetime, end_date: datetime) -> str:
    """Determine the prompt name for a date range."""
    # Check if start date is a month start
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", 
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    start_month = month_names[start_date.month - 1]
    end_month = month_names[end_date.month - 1]
    
    start_date_str = start_date.strftime('%d-%m-%y')
    end_date_str = end_date.strftime('%d-%m-%y')
    
    # If start date looks like a cash date (e.g., 17-04-25)
    if start_date.day < 28 and start_date.month >= 4 and start_date.month <= 7:
        # And end date is in a different month
        if start_month != end_month:
            return f"Cash-{end_month}"
    
    # If different months, use Month-Month format
    if start_month != end_month:
        return f"{start_month}-{end_month}"
    
    # Otherwise, use specific dates
    return f"{start_date.strftime('%d-%b')}-{end_date.strftime('%d-%b')}"


def build_daily_curve(per_day_values: List[Dict], 
                     cash_date: datetime, 
                     three_month_date: datetime) -> Dict:
    """
    Build a day-by-day curve of per-day values for the entire range.
    For each spread, assign the exact per-day value (from per_day_values, already using correct logic) to each day in the range (start date inclusive, end date exclusive).
    """
    daily_curve = {}

    # Build a list of (start_date, end_date, per_day) for all detailed ranges
    detailed_ranges = []
    for pv in per_day_values:
        if pv["start_date"] and pv["end_date"] and pv["per_day"] is not None:
            days = (pv["end_date"] - pv["start_date"]).days
            if days > 0:
                per_day = pv["per_day"]
                detailed_ranges.append((pv["start_date"], pv["end_date"], per_day))

    # Sort ranges by start_date
    detailed_ranges.sort(key=lambda x: x[0])

    # Assign per-day values to each day in the range (start inclusive, end exclusive)
    for start, end, per_day in detailed_ranges:
        current_date = start
        while current_date < end:
            date_key = current_date.strftime('%Y-%m-%d')
            daily_curve[date_key] = per_day
            current_date += timedelta(days=1)

    # Print a summary of the curve
    print("\nDaily curve summary (sample of days):")
    dates = sorted(list(daily_curve.keys()))
    for i, date in enumerate(dates):
        if i % 7 == 0 or i == len(dates) - 1:  # Show every 7th day and the last day
            print(f"  {date}: {daily_curve[date]}")

    return daily_curve


def get_per_day_value(data: Dict, start_date: datetime, end_date: datetime) -> Optional[float]:
    """
    Get the per-day value for a specific date range using the daily curve.
    
    Args:
        data: Extracted data from extract_lme_perday
        start_date: Start date of the range
        end_date: End date of the range
        
    Returns:
        Per-day value for the range or None if not found
    """
    if start_date == end_date:
        return 0.0  # No carry for same day
    
    # First check for exact match with summary sections from PDF
    # These values are the most accurate as they're directly from the PDF
    for entry in data["per_day_values"]:
        if (entry.get("is_summary", False) and
            entry["start_date"] == start_date and 
            entry["end_date"] == end_date):
            
            # If we have a per-day value, use it
            if entry["per_day"] is not None:
                return entry["per_day"]
            # Otherwise calculate from the exact total value
            elif entry["value"] is not None:
                days = (entry["end_date"] - entry["start_date"]).days
                if days > 0:
                    return entry["value"] / days
    
    # Check for exact matches in specific section values from the PDF
    for section in data["sections"]:
        # Try to match section name with date range
        section_name = section["name"].lower()
        
        # Handle specific cases like "Cash-May"
        if section_name == "cash-may":
            # Find May prompt date
            may_date = None
            for entry in data["per_day_values"]:
                if "May" in entry.get("prompt_name", "") and entry.get("is_summary", False):
                    may_date = entry["end_date"]
                    break
            
            if may_date and start_date == data["cash_date"] and end_date == may_date:
                return section["value"] / (may_date - data["cash_date"]).days
        
        elif section_name == "may-jun":
            # Find May and June prompt dates
            may_date = None
            jun_date = None
            for entry in data["per_day_values"]:
                if "May" in entry.get("prompt_name", "") and entry.get("is_summary", False):
                    may_date = entry["end_date"]
                elif "Jun" in entry.get("prompt_name", "") and entry.get("is_summary", False):
                    jun_date = entry["end_date"]
            
            if may_date and jun_date and start_date == may_date and end_date == jun_date:
                return section["value"] / (jun_date - may_date).days
    
    # For Cash-3M value, use the exact value from the PDF
    if data["c3m_value"] is not None and data["cash_date"] and data["three_month_date"]:
        if start_date == data["cash_date"] and end_date == data["three_month_date"]:
            days = (data["three_month_date"] - data["cash_date"]).days
            if days > 0:
                return data["c3m_value"] / days
    
    # If we have a daily curve, use it for accurate day-by-day calculation
    if data.get("daily_curve") and len(data["daily_curve"]) > 0:
        # Sum up all the per-day values for each day in the range
        total_value = 0.0
        date_count = 0
        
        current_date = start_date
        while current_date < end_date:
            date_key = current_date.strftime('%Y-%m-%d')
            if date_key in data["daily_curve"]:
                total_value += data["daily_curve"][date_key]
                date_count += 1
            
            current_date += timedelta(days=1)
        
        if date_count > 0:
            # Return the average per-day value
            return total_value / date_count
    
    # Fallback: Check for exact match in per_day_values
    # Prioritize detailed ranges over summary sections
    detailed_matches = []
    summary_matches = []
    
    for entry in data["per_day_values"]:
        if (entry["start_date"] == start_date and 
            entry["end_date"] == end_date and 
            entry["per_day"] is not None):
            
            if entry.get("is_summary", False):
                summary_matches.append(entry)
            else:
                detailed_matches.append(entry)
    
    # Prefer detailed matches
    if detailed_matches:
        return detailed_matches[0]["per_day"]
    elif summary_matches:
        return summary_matches[0]["per_day"]
    
    # If no exact match, check for range that contains our dates
    for entry in data["per_day_values"]:
        if (entry["start_date"] <= start_date and 
            entry["end_date"] >= end_date and 
            entry["per_day"] is not None):
            return entry["per_day"]
    
    # Check for range that starts on the same date
    for entry in data["per_day_values"]:
        if (entry["start_date"] == start_date and 
            entry["per_day"] is not None):
            return entry["per_day"]
    
    return None


def count_trading_days(start_date: datetime, end_date: datetime) -> int:
    """Count trading days (Mon-Fri, excluding UK holidays) between two dates (start inclusive, end exclusive)."""
    uk_holidays = holidays.country_holidays('GB', years=range(start_date.year, end_date.year + 1))
    count = 0
    current = start_date
    while current < end_date:
        if current.weekday() < 5 and current not in uk_holidays:
            count += 1
        current += timedelta(days=1)
    return count


if __name__ == "__main__":
    # Example usage
    import sys
    
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        print("Please provide a PDF file path.")
        sys.exit(1)
    
    data = extract_lme_perday(pdf_path)
    
    print(f"C-3M Value: {data['c3m_value']}")
    print(f"Cash Date: {data['cash_date'].strftime('%d-%m-%y') if data['cash_date'] else 'None'}")
    print(f"3M Date: {data['three_month_date'].strftime('%d-%m-%y') if data['three_month_date'] else 'None'}")
    
    print("\nPer Day Values:")
    for entry in data["per_day_values"]:
        start_str = entry["start_date"].strftime('%d-%m-%y')
        end_str = entry["end_date"].strftime('%d-%m-%y')
        summary_tag = " (Summary)" if entry.get("is_summary", False) else ""
        print(f"  {entry['prompt_name']}{summary_tag}: {start_str} to {end_str}: {entry['value']} ({entry['per_day']} per day)")
    
    print("\nSection Breakdown:")
    for section in data["sections"]:
        print(f"  {section['name']}: {section['value']}")
    
    # Example of calculating a per-day value for a custom date range
    if data["cash_date"] and data["three_month_date"]:
        cash_date = data["cash_date"]
        three_m_date = data["three_month_date"]
        
        per_day = get_per_day_value(data, cash_date, three_m_date)
        print(f"\nPer day value from {cash_date.strftime('%d-%m-%y')} to {three_m_date.strftime('%d-%m-%y')}: {per_day}")
        
        # Show a few example day ranges
        if cash_date:
            # 1-day range
            next_day = cash_date + timedelta(days=1)
            per_day_1d = get_per_day_value(data, cash_date, next_day)
            print(f"Per day value for 1 day ({cash_date.strftime('%d-%m-%y')} to {next_day.strftime('%d-%m-%y')}): {per_day_1d}")
            
            # 7-day range
            week_later = cash_date + timedelta(days=7)
            per_day_7d = get_per_day_value(data, cash_date, week_later)
            print(f"Per day value for 7 days ({cash_date.strftime('%d-%m-%y')} to {week_later.strftime('%d-%m-%y')}): {per_day_7d}")
    
    # Show some values from the daily curve
    print("\nSample of Daily Curve Values:")
    daily_keys = sorted(list(data["daily_curve"].keys()))
    for i, key in enumerate(daily_keys):
        if i % 7 == 0:  # Show every 7th day
            print(f"  {key}: {data['daily_curve'][key]}")
    print(f"  (Total of {len(daily_keys)} days in the curve)") 