import sqlite3
import json
from datetime import datetime, timedelta
import random

from src.core_engine import respond_to_interest, price_spread

# Define the database path
DB_PATH = "spread_trading.db"

def get_pending_interests_from_db():
    """Load pending interests directly from the database."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute(
            """
            SELECT id, user_id, metal, legs_json, submit_time, valuation_pnl, at_val_only, max_loss, status
            FROM spreads
            WHERE status = 'Pending' AND id > 62
            """
        )
        
        rows = cursor.fetchall()
        conn.close()
        
        interests = []
        for row in rows:
            spread_data = {
                "spread_id": row['id'],
                "user_id": row['user_id'],
                "metal": row['metal'],
                "legs": json.loads(row['legs_json']),
                "submit_time": row['submit_time'],
                "valuation_pnl": row['valuation_pnl'],
                "at_val_only": row['at_val_only'], 
                "max_loss": row['max_loss'],
                "status": row['status']
            }
            interests.append(spread_data)
        
        print(f"Loaded {len(interests)} pending interests from database")
        return interests
    except Exception as e:
        print(f"Database error: {str(e)}")
        return []

def create_responses():
    """Create responses to some of the pending interests."""
    pending_interests = get_pending_interests_from_db()
    
    # We'll respond to about 25% of the interests
    num_to_respond = min(len(pending_interests) // 4, 40)
    interests_to_respond = random.sample(pending_interests, num_to_respond)
    
    print(f"Creating responses for {num_to_respond} interests...")
    
    for i, interest in enumerate(interests_to_respond):
        spread_id = interest["spread_id"]
        
        # 80% will be accepted, 20% will be countered
        response_type = random.choices(["accept", "counter"], weights=[80, 20])[0]
        
        if response_type == "accept":
            response = {
                "status": "Accepted",
                "response_time": datetime.now().isoformat(),
                "responder_id": "marketmaker",
                "note": "Trade accepted"
            }
        else:
            # For counters, adjust the PnL slightly
            original_pnl = interest["valuation_pnl"]
            counter_pnl = original_pnl * random.uniform(0.9, 1.1)  # Adjust up to 10% in either direction
            
            response = {
                "status": "Countered",
                "response_time": datetime.now().isoformat(),
                "responder_id": "marketmaker",
                "counter_pnl": counter_pnl,
                "note": "Counter offer proposed"
            }
        
        # Submit the response
        success = respond_to_interest(spread_id, response)
        
        if success:
            print(f"{i+1}/{num_to_respond}: {response_type.title()}ed spread ID {spread_id}")
        else:
            print(f"{i+1}/{num_to_respond}: Failed to respond to spread ID {spread_id}")

if __name__ == "__main__":
    create_responses() 