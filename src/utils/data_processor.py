import pandas as pd
import pdfplumber
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..models.trading_card import Position, TradingCard

def parse_trading_card_csv(file_path: str, owner: str) -> TradingCard:
    """Parse a trading card CSV file into a TradingCard object."""
    try:
        # Read CSV with explicit dayfirst=True for date parsing
        df = pd.read_csv(file_path)
        
        # Convert Date column with UK format
        df['Date'] = pd.to_datetime(df['Date'], dayfirst=True)
        
        # Convert Far Date if present
        if 'Far Date' in df.columns:
            df['Far Date'] = pd.to_datetime(df['Far Date'], dayfirst=True)
            
        # Ensure position columns are numeric
        if 'Short Position' in df.columns:
            df['Short Position'] = pd.to_numeric(df['Short Position'], errors='coerce')
        if 'Long Position' in df.columns:
            df['Long Position'] = pd.to_numeric(df['Long Position'], errors='coerce')
    except Exception as e:
        raise ValueError(f"Error parsing CSV: {str(e)}. Ensure dates are in DD/MM/YYYY format.")
    
    positions = []
    for _, row in df.iterrows():
        # Handle short positions
        if pd.notna(row.get('Short Position', pd.NA)) and not pd.isna(row.get('Short Position', pd.NA)):
            far_date = row.get('Far Date', row['Date'] + timedelta(days=90))
            lots = float(row['Short Position'])  # Convert to float to ensure numeric
            positions.append(Position(
                near_date=row['Date'],
                far_date=far_date,
                lots=-abs(lots),  # Ensure negative for shorts
                daily_rate=None  # Will be populated from LME data
            ))
        
        # Handle long positions
        if pd.notna(row.get('Long Position', pd.NA)) and not pd.isna(row.get('Long Position', pd.NA)):
            far_date = row.get('Far Date', row['Date'] + timedelta(days=90))
            lots = float(row['Long Position'])  # Convert to float to ensure numeric
            positions.append(Position(
                near_date=row['Date'],
                far_date=far_date,
                lots=abs(lots),  # Ensure positive for longs
                daily_rate=None  # Will be populated from LME data
            ))
    
    return TradingCard(owner=owner, positions=positions)

def extract_c3m_rates_from_pdf(file_path: str) -> Dict[str, float]:
    """Extract Cash-to-3M rates from an LME PDF file."""
    rates = {}
    
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                
                # Focus on the Cash-to-3M section (red box in the PDF)
                # Look for "Per Day" and "C" headers
                if "Per Day" in text and "C" in text:
                    lines = text.split('\n')
                    for i, line in enumerate(lines):
                        # Look for the Cash-to-3M header section
                        if "Per Day" in line and i < len(lines) - 1:
                            # The next few lines should contain the C-3M data
                            for j in range(i+1, min(i+10, len(lines))):
                                line_data = lines[j].split()
                                # Look for lines that match the typical Cash-to-3M pattern
                                if len(line_data) >= 2:
                                    # Check if it has a rate pattern like "-3", "-2", "-1"
                                    if any(item in ["-3", "-2", "-1"] for item in line_data):
                                        # The daily rate is typically in this format
                                        for k, item in enumerate(line_data):
                                            if item in ["-3", "-2", "-1"]:
                                                # Try to get the daily rate, which should be a few items after
                                                rate_index = k + 1  # The rate is typically after the days indicator
                                                if rate_index < len(line_data):
                                                    try:
                                                        rate = float(line_data[rate_index].replace(',', '.'))
                                                        days = int(item)  # -3, -2, or -1
                                                        rates[days] = rate
                                                    except ValueError:
                                                        # If conversion fails, try the next item
                                                        continue
                    
                    # If we found rates, break out of the loop
                    if rates:
                        break
    except Exception as e:
        print(f"Error extracting rates from PDF: {str(e)}")
    
    return rates

def update_position_rates(card: TradingCard, rates: Dict[datetime, float]) -> None:
    """Update position daily rates based on LME data."""
    for position in card.positions:
        rate_date = position.near_date.date()
        if rate_date in rates:
            position.daily_rate = rates[rate_date]

def find_tidy_opportunities(cards: List[TradingCard], min_lots: int = 0, max_payment: float = float('inf')) -> List[Dict]:
    """Find opportunities to tidy positions across trading cards."""
    opportunities = []
    
    # Collect all positions
    positions = []
    for card in cards:
        for pos in card.positions:
            positions.append((card.owner, pos))
    
    # Find matching opportunities
    for i, (owner1, pos1) in enumerate(positions):
        for j, (owner2, pos2) in enumerate(positions[i+1:], i+1):
            # Skip if same owner
            if owner1 == owner2:
                continue
            
            # Skip if both positions are long or both are short
            if (pos1.lots > 0 and pos2.lots > 0) or (pos1.lots < 0 and pos2.lots < 0):
                continue
            
            # Ensure pos1 is short and pos2 is long for consistent processing
            if pos1.lots > 0:
                owner1, pos1, owner2, pos2 = owner2, pos2, owner1, pos1
            
            # Check for overlapping date ranges
            overlap_start = max(pos1.near_date, pos2.near_date)
            overlap_end = min(pos1.far_date, pos2.far_date)
            
            if overlap_start <= overlap_end:
                # Calculate overlapping days
                overlap_days = (overlap_end - overlap_start).days + 1
                
                # Calculate matchable lots (minimum of absolute values)
                matchable_lots = min(abs(pos1.lots), abs(pos2.lots))
                
                # Skip if below minimum lots threshold
                if matchable_lots < min_lots:
                    continue
                
                # Determine if this is a level carry (exact date match)
                is_level_carry = (pos1.near_date == pos2.near_date) and (pos1.far_date == pos2.far_date)
                
                # Calculate payment
                daily_rate = pos1.daily_rate if pos1.daily_rate is not None else (
                    pos2.daily_rate if pos2.daily_rate is not None else None
                )
                
                payment = None
                if daily_rate is not None:
                    # For partial matches, payment is based on overlapping period
                    payment = matchable_lots * daily_rate * overlap_days
                    
                    # Skip if above maximum payment threshold
                    if payment > max_payment:
                        continue
                
                # Create opportunity entry
                opportunity = {
                    "short_owner": owner1,
                    "short_position": pos1,
                    "long_owner": owner2,
                    "long_position": pos2,
                    "matchable_lots": matchable_lots,
                    "is_level_carry": is_level_carry,
                    "overlap_start": overlap_start,
                    "overlap_end": overlap_end,
                    "overlap_days": overlap_days,
                    "daily_rate": daily_rate,
                    "payment": payment
                }
                
                opportunities.append(opportunity)
    
    return opportunities 