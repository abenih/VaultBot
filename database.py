import sqlite3
import bcrypt
from typing import Optional

def init_db():
    """Initialize the database with required tables"""
    conn = sqlite3.connect('vaultbot.db', check_same_thread=False)
    cursor = conn.cursor()
    
    # Create users table if it doesn't exist
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            master_password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

def get_db_connection():
    """Get a database connection"""
    return sqlite3.connect('vaultbot.db', check_same_thread=False)

def user_exists(user_id: int) -> bool:
    """Check if a user exists in the database"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
    exists = cursor.fetchone() is not None
    
    conn.close()
    return exists

def set_master_password(user_id: int, password: str):
    """Set or update master password for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Hash the password with bcrypt
    password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
    
    cursor.execute(
        'INSERT OR REPLACE INTO users (user_id, master_password_hash) VALUES (?, ?)',
        (user_id, password_hash)
    )
    
    conn.commit()
    conn.close()

def verify_master_password(user_id: int, password: str) -> bool:
    """Verify the master password for a user"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute(
        'SELECT master_password_hash FROM users WHERE user_id = ?', 
        (user_id,)
    )
    
    result = cursor.fetchone()
    conn.close()
    
    if result is None:
        return False
    
    stored_hash = result[0]
    return bcrypt.checkpw(password.encode('utf-8'), stored_hash)