#!/usr/bin/env python3
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add parent directory to sys.path to import our module
sys.path.append(str(Path(__file__).parent))

from utils.extract_pdf_data import extract_spread_data_from_pdf, calculate_valuation

def main():
    """Test extraction from an LME PDF file."""
    # Get the PDF file path from command line argument or use a default
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Look in the data directory for any PDF files
        data_dir = Path(__file__).parent / "data"
        pdf_files = list(data_dir.glob("*.pdf"))
        
        if not pdf_files:
            print(f"No PDF files found in {data_dir}. Please provide a PDF file path.")
            return
        
        # Use the first PDF file found
        pdf_path = str(pdf_files[0])
    
    print(f"Extracting data from {pdf_path}")
    
    # Extract the spread data
    data = extract_spread_data_from_pdf(pdf_path)
    
    # Print basic information
    print(f"\nMetal: {data['metal']}")
    print(f"C-3M Total: {data['c3m_total']}")
    print(f"Cash Date: {data['cash_date'].strftime('%d-%m-%y') if data['cash_date'] else 'None'}")
    print(f"3M Date: {data['three_month_date'].strftime('%d-%m-%y') if data['three_month_date'] else 'None'}")
    
    # Print spread details focusing on the red box section
    print("\nSpread Details:")
    for spread in data["spreads"]:
        prompt_name = spread.get("prompt_name", "Unknown")
        start_date = spread["start_date"].strftime('%d-%m-%y') if spread["start_date"] else "None"
        end_date = spread["end_date"].strftime('%d-%m-%y') if spread["end_date"] else "None"
        value = spread["value"] if spread["value"] is not None else "None"
        per_day = spread["per_day"] if spread["per_day"] is not None else "None"
        
        print(f"  {prompt_name}: {start_date} to {end_date}, Value: {value}, Per Day: {per_day}")
    
    # Calculate valuation based on provided dates if available
    if data['cash_date'] and data['three_month_date']:
        calc_val = calculate_valuation(data["spreads"], data['cash_date'], data['three_month_date'])
        print(f"\nCalculated C-3M Valuation: {calc_val}")
        print(f"Reported C-3M Valuation: {data['c3m_total']}")
        
        if calc_val is not None and data['c3m_total'] is not None:
            print(f"Difference: {calc_val - data['c3m_total']}")
    
    # Print section-by-section breakdown if available
    print("\nSection Breakdown:")
    sections = ["Cash-May", "May-Jun", "Jun-Jul", "Jul-3m", "Cash-3s"]
    for section in sections:
        found = False
        for spread in data["spreads"]:
            if spread.get("prompt_name") == section:
                found = True
                value = spread["value"] if spread["value"] is not None else "None"
                per_day = spread["per_day"] if spread["per_day"] is not None else "None"
                print(f"  {section}: Value: {value}, Per Day: {per_day}")
                break
        
        if not found:
            print(f"  {section}: Not found")
    
    # Get per_day values for specific date ranges (only from red box area)
    print("\nPer Day Values for Date Ranges:")
    date_ranges = []
    
    # Only include spreads with both start and end dates and per_day values
    valid_spreads = [s for s in data["spreads"] 
                    if s["start_date"] and s["end_date"] and s["per_day"] is not None]
    
    # Sort by start date
    valid_spreads.sort(key=lambda s: s["start_date"])
    
    for spread in valid_spreads:
        start = spread["start_date"]
        end = spread["end_date"]
        per_day = spread["per_day"]
        
        start_str = start.strftime('%d-%m-%y')
        end_str = end.strftime('%d-%m-%y')
        
        print(f"  {start_str} to {end_str}: {per_day} per day")

if __name__ == "__main__":
    main() 