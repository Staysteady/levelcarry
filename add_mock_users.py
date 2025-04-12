import sqlite3
import json
from datetime import datetime, timedelta
import random

from src.core_engine import submit_spread_interest, price_spread

# Define the database path
DB_PATH = "spread_trading.db"

# New users to add
NEW_USERS = [
    "bernie",    # Koch
    "morph",     # Koch
    "tom",       # Glencore
    "mark",      # Clear st
    "danny",     # Sigma
    "bloggsy",   # Sucden
    "sam",       # Tavira
    "persil",    # Clear St
    "wattsy",    # MDT
    "giles"      # FCS
]

# User affiliations for display
USER_AFFILIATIONS = {
    "bernie": "Koch",
    "morph": "Koch",
    "tom": "Glencore",
    "mark": "Clear st",
    "danny": "Sigma",
    "bloggsy": "Sucden",
    "sam": "Tavira",
    "persil": "Clear St",
    "wattsy": "MDT",
    "giles": "FCS"
}

# Available metals
METALS = ["Aluminum", "Copper", "Lead", "Nickel", "Tin", "Zinc"]

# Generate trading days (weekdays only) in 2025 (from April to July)
def generate_trading_days(start_date, days_needed):
    trading_days = []
    current_date = start_date
    
    # UK Bank Holidays in 2025
    uk_holidays = [
        datetime(2025, 4, 18),  # Good Friday
        datetime(2025, 4, 21),  # Easter Monday
        datetime(2025, 5, 5),   # Early May Bank Holiday
        datetime(2025, 5, 26),  # Spring Bank Holiday
        datetime(2025, 8, 25),  # Summer Bank Holiday
    ]
    
    while len(trading_days) < days_needed:
        # Skip weekends (5 = Saturday, 6 = Sunday)
        if current_date.weekday() < 5 and current_date not in uk_holidays:
            trading_days.append(current_date)
        current_date += timedelta(days=1)
    
    return trading_days

# Create different leg patterns for spread trades
def generate_leg_patterns():
    patterns = [
        # Pattern 1: Lend 5 days, Borrow 5 days
        [("Lend", 5), ("Borrow", 5)],
        
        # Pattern 2: Borrow 5 days, Lend 5 days
        [("Borrow", 5), ("Lend", 5)],
        
        # Pattern 3: Lend 2 days, Borrow 2 days, Lend 2 days
        [("Lend", 2), ("Borrow", 2), ("Lend", 2)],
        
        # Pattern 4: Borrow 3 days, Lend 7 days
        [("Borrow", 3), ("Lend", 7)],
        
        # Pattern 5: Lend 10 days
        [("Lend", 10)],
        
        # Pattern 6: Borrow 10 days
        [("Borrow", 10)],
        
        # Pattern 7: Lend 3 days, Borrow 3 days, Lend 4 days
        [("Lend", 3), ("Borrow", 3), ("Lend", 4)],
        
        # Pattern 8: Borrow 4 days, Lend 2 days, Borrow 4 days
        [("Borrow", 4), ("Lend", 2), ("Borrow", 4)]
    ]
    return patterns

def create_mock_spread_interest(user_id, metal, start_date):
    # Random pattern selection
    patterns = generate_leg_patterns()
    pattern = random.choice(patterns)
    
    # Generate trading days starting from the provided start date
    total_days_needed = sum(days for _, days in pattern)
    trading_days = generate_trading_days(start_date, total_days_needed + 5)  # Add buffer days
    
    # Create legs based on the pattern
    legs = []
    day_index = 0
    
    for direction, days in pattern:
        leg_start = trading_days[day_index]
        leg_end = trading_days[day_index + days - 1]  # -1 because we count the start day
        
        # Random lots between 20 and 200, in increments of 10
        lots = random.randrange(2, 21) * 10
        
        legs.append({
            "metal": metal,
            "direction": direction,
            "start_date": leg_start.isoformat(),
            "end_date": leg_end.isoformat(),
            "lots": lots
        })
        
        day_index += days
    
    # Add valuation constraints
    # 70% chance of max loss, 30% chance of at valuation only
    constraint_type = random.choices(["max_loss", "at_val_only"], weights=[70, 30])[0]
    
    spread_data = {
        "metal": metal,
        "legs": legs,
        "status": "Pending",
    }
    
    # Pricing the spread to get a reasonable valuation
    total_pnl, _ = price_spread(legs)
    spread_data["valuation_pnl"] = total_pnl
    
    # Add cost constraints
    if constraint_type == "max_loss":
        # Random max loss between $250 and $5000
        max_loss = random.randint(250, 5000)
        spread_data["max_loss"] = max_loss
        spread_data["at_val_only"] = False
    else:
        spread_data["at_val_only"] = True
        spread_data["max_loss"] = 0
    
    return spread_data

def main():
    # Generate data for all new users
    print(f"Adding data for {len(NEW_USERS)} new users across {len(METALS)} metals...")
    
    # Start dates spread across April and May 2025
    base_start_date = datetime(2025, 4, 1)
    
    # Counters
    total_spreads = 0
    
    for user_id in NEW_USERS:
        # Each user will have interests in 3-6 different metals
        num_metals = random.randint(3, 6)
        selected_metals = random.sample(METALS, num_metals)
        
        for metal in selected_metals:
            # Each user will have 2-5 spread interests per selected metal
            num_spreads = random.randint(2, 5)
            
            for i in range(num_spreads):
                # Randomize start date (between April 1 and May 15, 2025)
                days_offset = random.randint(0, 45)
                start_date = base_start_date + timedelta(days=days_offset)
                
                # Create and submit the spread interest
                spread_data = create_mock_spread_interest(user_id, metal, start_date)
                spread_id = submit_spread_interest(user_id, spread_data)
                
                # Increment counter and print progress
                total_spreads += 1
                print(f"Added spread {total_spreads}: User={user_id}, Metal={metal}, ID={spread_id}")
                
                # Add affiliation data to separate table if it doesn't exist yet
                conn = sqlite3.connect(DB_PATH)
                cursor = conn.cursor()
                
                # Check if user_affiliations table exists
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name='user_affiliations'
                """)
                if not cursor.fetchone():
                    cursor.execute("""
                        CREATE TABLE user_affiliations (
                            user_id TEXT PRIMARY KEY,
                            affiliation TEXT
                        )
                    """)
                
                # Add or update affiliation
                if user_id in USER_AFFILIATIONS:
                    cursor.execute("""
                        INSERT OR REPLACE INTO user_affiliations (user_id, affiliation)
                        VALUES (?, ?)
                    """, (user_id, USER_AFFILIATIONS[user_id]))
                
                conn.commit()
                conn.close()
    
    print(f"Successfully added {total_spreads} mock spread interests for {len(NEW_USERS)} users.")

if __name__ == "__main__":
    main() 