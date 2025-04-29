"""
SQLite database operations for storing and retrieving app review data
"""
import sqlite3
import logging
import os

logger = logging.getLogger(__name__)
DB_PATH = "app_reviews.db"

def setup_database():
    """Initialize the SQLite database with necessary tables"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Create reviews table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT UNIQUE,
            app_id TEXT,
            username TEXT,
            review_text TEXT,
            rating INTEGER,
            timestamp TEXT,
            date_added TEXT,
            processed BOOLEAN DEFAULT FALSE
        )
        ''')
        
        # Create sentiment table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS sentiment (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT UNIQUE,
            sentiment TEXT,
            confidence REAL,
            FOREIGN KEY (review_id) REFERENCES reviews (review_id)
        )
        ''')
        
        # Create categories table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT,
            category TEXT,
            FOREIGN KEY (review_id) REFERENCES reviews (review_id)
        )
        ''')
        
        # Create priorities table
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS priorities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id TEXT UNIQUE,
            priority_level INTEGER,
            FOREIGN KEY (review_id) REFERENCES reviews (review_id)
        )
        ''')
        
        # Create action_plans table - Updated to support the new theme-based structure
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS action_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            summary TEXT,
            action_steps TEXT,  -- JSON array of steps
            user_response TEXT,
            review_count INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
        ''')
        
        conn.commit()
        logger.info("Database tables created successfully")
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Database error: {e}")
        return False

def save_review(review_data):
    """Save a new review to the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
        INSERT OR IGNORE INTO reviews (
            review_id, app_id, username, review_text, 
            rating, timestamp, date_added, processed
        ) VALUES (?, ?, ?, ?, ?, ?, datetime('now'), FALSE)
        ''', (
            review_data['review_id'],
            review_data['app_id'],
            review_data['username'],
            review_data['review_text'],
            review_data['rating'],
            review_data['timestamp']
        ))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error saving review: {e}")
        return False

def get_unprocessed_reviews():
    """Get all unprocessed reviews from the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT * FROM reviews WHERE processed = FALSE
        ''')
        
        reviews = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return reviews
    except sqlite3.Error as e:
        logger.error(f"Error retrieving unprocessed reviews: {e}")
        return []
        
def mark_review_as_processed(review_id):
    """Mark a review as processed in the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        cursor.execute('''
        UPDATE reviews SET processed = TRUE WHERE review_id = ?
        ''', (review_id,))
        
        conn.commit()
        conn.close()
        return True
    except sqlite3.Error as e:
        logger.error(f"Error marking review as processed: {e}")
        return False
        
def get_recent_reviews(limit=10):
    """Get the most recent reviews from the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT r.*, 
               s.sentiment,
               p.priority_level
        FROM reviews r
        LEFT JOIN sentiment s ON r.review_id = s.review_id
        LEFT JOIN priorities p ON r.review_id = p.review_id
        ORDER BY r.date_added DESC
        LIMIT ?
        ''', (limit,))
        
        reviews = [dict(row) for row in cursor.fetchall()]
        
        # Get categories for each review
        for review in reviews:
            cursor.execute('''
            SELECT category FROM categories
            WHERE review_id = ?
            ''', (review['review_id'],))
            
            categories = [row[0] for row in cursor.fetchall()]
            review['categories'] = categories
            
        conn.close()
        return reviews
    except sqlite3.Error as e:
        logger.error(f"Error retrieving recent reviews: {e}")
        return []
        
def get_reviews_by_priority(priority_level, limit=10):
    """Get reviews with a specific priority level"""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        cursor.execute('''
        SELECT r.*, 
               s.sentiment,
               p.priority_level
        FROM reviews r
        JOIN priorities p ON r.review_id = p.review_id
        LEFT JOIN sentiment s ON r.review_id = s.review_id
        WHERE p.priority_level = ?
        ORDER BY r.date_added DESC
        LIMIT ?
        ''', (priority_level, limit))
        
        reviews = [dict(row) for row in cursor.fetchall()]
        
        # Get categories for each review
        for review in reviews:
            cursor.execute('''
            SELECT category FROM categories
            WHERE review_id = ?
            ''', (review['review_id'],))
            
            categories = [row[0] for row in cursor.fetchall()]
            review['categories'] = categories
            
        conn.close()
        return reviews
    except sqlite3.Error as e:
        logger.error(f"Error retrieving reviews by priority: {e}")
        return []