import sqlite3
import json
from datetime import datetime, timedelta
import random
import fakeredis

# Database path
DB_PATH = "spread_trading.db"

# Get a fake Redis client for testing
def get_fake_redis_client():
    print("Using fakeredis for testing")
    return fakeredis.FakeStrictRedis()

# Sample user IDs
USER_IDS = ["trader1", "trader2", "trader3", "trader4", "hedger1", "producer1"]

# Metals
METALS = ["Aluminum", "Copper", "Zinc", "Nickel", "Lead", "Tin"]

def clear_redis_queue():
    """Clear the Redis queue of all pending interests."""
    r = get_fake_redis_client()
    r.delete('spread_requests')
    print("Cleared Redis spread_requests queue")

def load_existing_spreads_to_redis():
    """Load existing pending spreads from database to Redis."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Get all pending spreads
    cursor.execute(
        """
        SELECT id, user_id, metal, legs_json, submit_time, valuation_pnl, at_val_only, max_loss, status
        FROM spreads
        WHERE status = 'Pending'
        """
    )
    
    rows = cursor.fetchall()
    conn.close()
    
    # Clear existing Redis queue
    clear_redis_queue()
    
    # Add each spread to Redis
    r = get_fake_redis_client()
    
    count = 0
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
        
        r.rpush('spread_requests', json.dumps(spread_data))
        count += 1
    
    print(f"Loaded {count} existing pending spreads into Redis queue")
    
if __name__ == "__main__":
    print("Loading existing pending spreads to Redis...")
    load_existing_spreads_to_redis()
    print("Done! You can now view these in the Market Maker interface by clicking 'Refresh Interests'.") 