# database.py - Database functions for VaultBot
import sqlite3
import bcrypt
import logging
from datetime import datetime
from typing import Optional, List, Dict

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
        
        # Create memos table if it doesn't exist
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                file_id TEXT NOT NULL,
                date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
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

def save_voice_memo(user_id: int, file_id: str) -> bool:
    """Save a voice memo to the database"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO memos (user_id, file_id) VALUES (?, ?)',
            (user_id, file_id)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"Voice memo saved for user {user_id} with file_id {file_id}")
        return True
    except Exception as e:
        logger.error(f"Error saving voice memo: {e}")
        return False

def get_user_memos(user_id: int) -> List[Dict]:
    """Get all memos for a user"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, file_id, date FROM memos WHERE user_id = ? ORDER BY date DESC',
            (user_id,)
        )
        
        memos = []
        for row in cursor.fetchall():
            memos.append({
                'id': row[0],
                'file_id': row[1],
                'date': row[2]
            })
        
        conn.close()
        logger.info(f"Retrieved {len(memos)} memos for user {user_id}")
        return memos
    except Exception as e:
        logger.error(f"Error retrieving memos: {e}")
        return []

def delete_memo(memo_id: int, user_id: int) -> bool:
    """Delete a specific memo"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute(
            'DELETE FROM memos WHERE id = ? AND user_id = ?',
            (memo_id, user_id)
        )
        
        conn.commit()
        conn.close()
        logger.info(f"Deleted memo {memo_id} for user {user_id}")
        return cursor.rowcount > 0
    except Exception as e:
        logger.error(f"Error deleting memo: {e}")
        return False