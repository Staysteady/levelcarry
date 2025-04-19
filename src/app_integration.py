#!/usr/bin/env python3
"""
Example of integrating LME per-day extraction utility into an application.

This script demonstrates how to:
1. Extract per-day values from LME PDF files
2. Use the extracted values in calculations with user-specified cash and 3M dates
"""

import sys
import os
from datetime import datetime, timedelta
from utils.extract_lme_perday import extract_lme_perday, get_per_day_value, get_third_wednesday

# Sample app code to demonstrate integration
class LMEApp:
    def __init__(self):
        self.pdf_data = {}
        self.cash_date = None
        self.three_month_date = None
    
    def load_pdf(self, pdf_path):
        """Load data from an LME PDF file."""
        if not os.path.exists(pdf_path):
            print(f"Error: PDF file not found: {pdf_path}")
            return False
        
        try:
            print(f"Loading PDF: {pdf_path}")
            self.pdf_data = extract_lme_perday(pdf_path)
            
            # Print summary of extracted data
            print(f"\nExtracted data:")
            print(f"C-3M Value: {self.pdf_data['c3m_value']}")
            print(f"PDF Cash Date: {self.pdf_data['cash_date'].strftime('%d-%m-%y') if self.pdf_data['cash_date'] else 'None'}")
            print(f"PDF 3M Date: {self.pdf_data['three_month_date'].strftime('%d-%m-%y') if self.pdf_data['three_month_date'] else 'None'}")
            
            # If no cash/3m dates were found in PDF, use default values
            if not self.cash_date and self.pdf_data['cash_date']:
                self.cash_date = self.pdf_data['cash_date']
            
            if not self.three_month_date and self.pdf_data['three_month_date']:
                self.three_month_date = self.pdf_data['three_month_date']
            
            return True
        except Exception as e:
            print(f"Error loading PDF: {str(e)}")
            return False
    
    def set_cash_date(self, date_str):
        """Set the cash date manually."""
        try:
            self.cash_date = datetime.strptime(date_str, '%d-%m-%y')
            print(f"Cash date set to: {self.cash_date.strftime('%d-%m-%y')}")
            return True
        except ValueError:
            print(f"Error: Invalid date format. Use DD-MM-YY")
            return False
    
    def set_three_month_date(self, date_str):
        """Set the 3M date manually."""
        try:
            self.three_month_date = datetime.strptime(date_str, '%d-%m-%y')
            print(f"3M date set to: {self.three_month_date.strftime('%d-%m-%y')}")
            return True
        except ValueError:
            print(f"Error: Invalid date format. Use DD-MM-YY")
            return False
    
    def calculate_value(self):
        """Calculate the value for current cash and 3M dates."""
        if not self.pdf_data:
            print("Error: No PDF data loaded.")
            return None
        
        if not self.cash_date or not self.three_month_date:
            print("Error: Cash date and 3M date must be set.")
            return None
        
        if self.cash_date >= self.three_month_date:
            print("Error: Cash date must be before 3M date.")
            return None
        
        # Calculate the per-day value for the date range
        per_day = get_per_day_value(self.pdf_data, self.cash_date, self.three_month_date)
        
        if per_day is None:
            print("Error: Could not determine per-day value for the specified date range.")
            return None
        
        # Calculate total days between dates
        days = (self.three_month_date - self.cash_date).days
        
        # Calculate total value
        total_value = per_day * days
        
        return {
            "cash_date": self.cash_date,
            "three_month_date": self.three_month_date,
            "days": days,
            "per_day": per_day,
            "total_value": total_value
        }
    
    def print_sections(self):
        """Print the section breakdown from the PDF."""
        if not self.pdf_data or not self.pdf_data.get("sections"):
            print("No section data available.")
            return
        
        print("\nSection Breakdown:")
        for section in self.pdf_data["sections"]:
            print(f"  {section['name']}: {section['value']}")
    
    def find_prompt_dates(self, year=None, month=None):
        """Find prompt dates (3rd Wednesday) for specified year/month or current."""
        if not year:
            year = datetime.now().year
        
        prompt_dates = []
        
        # Get prompt dates for specified months or all months
        if month:
            months = [month]
        else:
            months = range(1, 13)
        
        for m in months:
            prompt_date = get_third_wednesday(year, m)
            prompt_dates.append(prompt_date)
        
        return prompt_dates


def main():
    """Main function to demonstrate app integration."""
    app = LMEApp()
    
    # Check command line arguments for PDF path
    if len(sys.argv) > 1:
        pdf_path = sys.argv[1]
    else:
        # Default PDF path if none provided
        data_dir = os.path.join(os.path.dirname(__file__), "data")
        pdf_files = [f for f in os.listdir(data_dir) if f.endswith('.pdf')]
        
        if not pdf_files:
            print(f"No PDF files found in {data_dir}. Please provide a PDF file path.")
            return
        
        pdf_path = os.path.join(data_dir, pdf_files[0])
    
    # Load the PDF
    if not app.load_pdf(pdf_path):
        return
    
    # Example: Show available prompt dates for the current year
    print("\nPrompt Dates (3rd Wednesdays):")
    prompt_dates = app.find_prompt_dates()
    for date in prompt_dates:
        print(f"  {date.strftime('%d-%m-%y')} ({date.strftime('%B')})")
    
    # Example: Manual setting of cash and 3M dates
    print("\nManual date setting example:")
    
    # Use detected dates from PDF if available, otherwise use defaults
    cash_date = app.pdf_data['cash_date'] if app.pdf_data['cash_date'] else datetime.now()
    three_m_date = app.pdf_data['three_month_date'] if app.pdf_data['three_month_date'] else (datetime.now() + timedelta(days=90))
    
    # Format dates for display and setting
    cash_date_str = cash_date.strftime('%d-%m-%y')
    three_m_date_str = three_m_date.strftime('%d-%m-%y')
    
    print(f"Setting cash date to: {cash_date_str}")
    app.set_cash_date(cash_date_str)
    
    print(f"Setting 3M date to: {three_m_date_str}")
    app.set_three_month_date(three_m_date_str)
    
    # Calculate and display results
    result = app.calculate_value()
    
    if result:
        print("\nCalculation Result:")
        print(f"  Cash Date: {result['cash_date'].strftime('%d-%m-%y')}")
        print(f"  3M Date: {result['three_month_date'].strftime('%d-%m-%y')}")
        print(f"  Days: {result['days']}")
        print(f"  Per Day Value: {result['per_day']}")
        print(f"  Total Value: {result['total_value']}")
    
    # Show section breakdown
    app.print_sections()


if __name__ == "__main__":
    main() 