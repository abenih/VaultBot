# database.py - This should ONLY contain database functions
import sqlite3
import bcrypt
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def init_db():
    """Initialize the database with required tables"""
    try:
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
        logger.info("Database initialized successfully")
        return True
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        return False

def get_db_connection():
    """Get a database connection"""
    return sqlite3.connect('vaultbot.db', check_same_thread=False)

def user_exists(user_id: int) -> bool:
    """Check if a user exists in the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT user_id FROM users WHERE user_id = ?', (user_id,))
        exists = cursor.fetchone() is not None
        
        conn.close()
        logger.info(f"User existence check for {user_id}: {exists}")
        return exists
    except Exception as e:
        logger.error(f"Error checking user existence: {e}")
        return False

def set_master_password(user_id: int, password: str) -> bool:
    """Set or update master password for a user"""
    try:
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
        logger.info(f"Password set successfully for user {user_id}")
        return True
    except Exception as e:
        logger.error(f"Error setting password: {e}")
        return False

def verify_master_password(user_id: int, password: str) -> bool:
    """Verify the master password for a user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT master_password_hash FROM users WHERE user_id = ?', 
            (user_id,)
        )
        
        result = cursor.fetchone()
        conn.close()
        
        if result is None:
            logger.warning(f"No password found for user {user_id}")
            return False
        
        stored_hash = result[0]
        is_valid = bcrypt.checkpw(password.encode('utf-8'), stored_hash)
        logger.info(f"Password verification for user {user_id}: {is_valid}")
        return is_valid
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False