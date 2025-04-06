import sqlite3
import json
from datetime import datetime, timedelta
import random

# Database path
DB_PATH = "spread_trading.db"

# For Redis integration
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False

# Try to import fakeredis if real redis is not available
if not REDIS_AVAILABLE:
    try:
        import fakeredis
        FAKEREDIS_AVAILABLE = True
    except ImportError:
        FAKEREDIS_AVAILABLE = False

def get_redis_client():
    """Get a Redis client - real or fake based on availability."""
    if REDIS_AVAILABLE:
        try:
            return redis.Redis(host='localhost', port=6379, db=0)
        except:
            print("Could not connect to real Redis, falling back to fakeredis")
    
    if FAKEREDIS_AVAILABLE:
        print("Using fakeredis for testing")
        return fakeredis.FakeStrictRedis()
    
    print("WARNING: Neither redis nor fakeredis is available. Interest refresh will not work.")
    return None

# Sample user IDs
USER_IDS = ["trader1", "trader2", "trader3", "trader4", "hedger1", "producer1"]

# Metals
METALS = ["Aluminum", "Copper", "Zinc", "Nickel", "Lead", "Tin"]

# Sample spread configurations
def generate_sample_spread():
    """Generate a random sample spread with 1-3 legs."""
    metal = random.choice(METALS)
    num_legs = random.randint(1, 3)
    
    # Start with a date between 1-30 days from now
    base_date = datetime.now() + timedelta(days=random.randint(1, 30))
    
    legs = []
    for i in range(num_legs):
        # Each leg starts 0-30 days from base date and lasts 15-90 days
        start_offset = random.randint(0, 30)
        start_date = base_date + timedelta(days=start_offset)
        duration = random.randint(15, 90)
        end_date = start_date + timedelta(days=duration)
        
        # Direction is either Borrow or Lend
        direction = random.choice(["Borrow", "Lend"])
        
        # Lots between 5 and 50
        lots = random.randint(5, 50)
        
        legs.append({
            "id": i + 1,
            "direction": direction,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "lots": lots
        })
    
    # Generate random valuation PnL between -500 and 500
    valuation_pnl = round(random.uniform(-500, 500), 2)
    
    # Randomly decide if it's "at valuation only"
    at_val_only = random.choice([True, False])
    
    # If not at valuation only, set max loss between 0 and 1000
    max_loss = round(random.uniform(0, 1000), 2) if not at_val_only else 0
    
    return {
        "user_id": random.choice(USER_IDS),
        "metal": metal,
        "legs": legs,
        "submit_time": datetime.now().isoformat(),
        "valuation_pnl": valuation_pnl,
        "at_val_only": at_val_only,
        "max_loss": max_loss,
        "status": "Pending"
    }

def insert_user_if_not_exists(cursor, user_id):
    """Insert user if not exists in the users table."""
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        # Role is "user" for all sample users
        cursor.execute(
            "INSERT INTO users (user_id, name, role) VALUES (?, ?, ?)",
            (user_id, f"Sample {user_id.capitalize()}", "user")
        )

def insert_spread_interest(spread_data):
    """Insert a spread interest into the database and Redis."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Ensure user exists
    insert_user_if_not_exists(cursor, spread_data["user_id"])
    
    # Insert spread
    cursor.execute(
        """
        INSERT INTO spreads 
        (user_id, metal, legs_json, submit_time, valuation_pnl, at_val_only, max_loss, status, response_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            spread_data["user_id"],
            spread_data["metal"],
            json.dumps(spread_data["legs"]),
            spread_data["submit_time"],
            spread_data["valuation_pnl"],
            spread_data["at_val_only"],
            spread_data["max_loss"],
            spread_data["status"],
            None
        )
    )
    
    # Get the inserted ID
    spread_id = cursor.lastrowid
    
    # Update the spread_data with the ID
    spread_data["spread_id"] = spread_id
    
    conn.commit()
    conn.close()
    
    # Add to Redis for real-time availability
    r = get_redis_client()
    if r:
        try:
            r.rpush('spread_requests', json.dumps(spread_data))
            print(f"  Added to Redis queue")
        except Exception as e:
            print(f"  Redis error: {str(e)}")
    
    return spread_id

def clear_redis_queue():
    """Clear the Redis queue of all pending interests."""
    r = get_redis_client()
    if r:
        try:
            r.delete('spread_requests')
            print("Cleared Redis spread_requests queue")
        except Exception as e:
            print(f"Redis error: {str(e)}")

def generate_sample_data(num_spreads=10, clear_existing=True):
    """Generate sample data and insert into database and Redis."""
    # Clear Redis queue if requested
    if clear_existing:
        clear_redis_queue()
    
    # Ensure the marketmaker user exists
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    insert_user_if_not_exists(cursor, "marketmaker")
    conn.commit()
    conn.close()
    
    # Generate and insert spreads
    for _ in range(num_spreads):
        spread_data = generate_sample_spread()
        spread_id = insert_spread_interest(spread_data)
        print(f"Inserted spread interest #{spread_id}: {spread_data['metal']} from {spread_data['user_id']}")

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
    r = get_redis_client()
    if not r:
        print("Redis client not available, can't load spreads")
        return
    
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
        
        try:
            r.rpush('spread_requests', json.dumps(spread_data))
            count += 1
        except Exception as e:
            print(f"Redis error on spread {row['id']}: {str(e)}")
    
    print(f"Loaded {count} existing pending spreads into Redis queue")

if __name__ == "__main__":
    action = input("Choose action:\n1. Generate new sample data\n2. Load existing spreads to Redis\nEnter choice (1/2): ")
    
    if action == "1":
        num = int(input("How many sample spread interests to generate? "))
        print(f"Generating {num} sample spread interests...")
        generate_sample_data(num)
        print("Done! You can now view these in the Market Maker interface.")
    elif action == "2":
        print("Loading existing pending spreads to Redis...")
        load_existing_spreads_to_redis()
        print("Done! You can now view these in the Market Maker interface.")
    else:
        print("Invalid choice") 