import sqlite3

# Define database paths
SOURCE_DB = "trading.db"
TARGET_DB = "spread_trading.db"

def move_affiliations():
    """Move user affiliations from trading.db to spread_trading.db."""
    # Read data from source database
    try:
        source_conn = sqlite3.connect(SOURCE_DB)
        source_cursor = source_conn.cursor()
        
        # Get user affiliations
        source_cursor.execute("SELECT user_id, affiliation FROM user_affiliations")
        affiliations = source_cursor.fetchall()
        
        source_conn.close()
        
        if not affiliations:
            print("No affiliations found in source database.")
            return
        
        print(f"Found {len(affiliations)} user affiliations in source database.")
        
        # Connect to target database
        target_conn = sqlite3.connect(TARGET_DB)
        target_cursor = target_conn.cursor()
        
        # Check if users table exists
        target_cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='users'
        """)
        
        users_table_exists = target_cursor.fetchone()
        
        if not users_table_exists:
            # Create users table if it doesn't exist
            target_cursor.execute("""
                CREATE TABLE users (
                    user_id TEXT PRIMARY KEY,
                    name TEXT,
                    affiliation TEXT,
                    role TEXT
                )
            """)
            print("Created users table in target database.")
        else:
            # Check if affiliation column exists
            target_cursor.execute("PRAGMA table_info(users)")
            columns = [col[1] for col in target_cursor.fetchall()]
            
            if 'affiliation' not in columns:
                # Add affiliation column
                target_cursor.execute("ALTER TABLE users ADD COLUMN affiliation TEXT")
                print("Added affiliation column to existing users table.")
        
        # Insert users with affiliations
        for user_id, affiliation in affiliations:
            # Check if user already exists
            target_cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if target_cursor.fetchone():
                # Update existing user
                target_cursor.execute("""
                    UPDATE users 
                    SET affiliation = ? 
                    WHERE user_id = ?
                """, (affiliation, user_id))
                print(f"Updated user {user_id} with affiliation {affiliation}")
            else:
                # Create new user
                target_cursor.execute("""
                    INSERT INTO users (user_id, name, affiliation)
                    VALUES (?, ?, ?)
                """, (user_id, user_id.capitalize(), affiliation))
                print(f"Added user {user_id} with affiliation {affiliation}")
        
        # Also add the existing users from spreads table who don't have records in the users table
        target_cursor.execute("""
            SELECT DISTINCT user_id FROM spreads 
            WHERE user_id NOT IN (SELECT user_id FROM users)
        """)
        
        missing_users = target_cursor.fetchall()
        for (user_id,) in missing_users:
            target_cursor.execute("""
                INSERT INTO users (user_id, name)
                VALUES (?, ?)
            """, (user_id, user_id.capitalize()))
            print(f"Added existing user {user_id} without affiliation")
        
        # Commit changes and close
        target_conn.commit()
        target_conn.close()
        
        print("Successfully moved user affiliations.")
        
    except Exception as e:
        print(f"Error moving affiliations: {str(e)}")

if __name__ == "__main__":
    move_affiliations() 