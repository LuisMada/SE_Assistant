"""
Export functionality for the App Review Bot
"""
import csv
import os
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

def generate_reviews_csv(db_path: str, days: int = 7) -> Optional[str]:
    """
    Generate a CSV file with the latest analyzed reviews
    
    Args:
        db_path: Path to the SQLite database
        days: Number of days to include in the export (default: 7)
        
    Returns:
        Path to the generated CSV file, or None if an error occurred
    """
    try:
        # Calculate the date cutoff
        cutoff_date = (datetime.now() - timedelta(days=days)).isoformat()
        
        # Connect to the database
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Fetch the reviews with all related data
        cursor.execute('''
        SELECT 
            r.review_id, r.username, r.review_text, r.rating, r.timestamp,
            s.sentiment, p.priority_level
        FROM reviews r
        LEFT JOIN sentiment s ON r.review_id = s.review_id
        LEFT JOIN priorities p ON r.review_id = p.review_id
        WHERE r.date_added >= ?
        ORDER BY r.date_added DESC
        ''', (cutoff_date,))
        
        reviews = [dict(row) for row in cursor.fetchall()]
        
        # If no reviews found, return None
        if not reviews:
            logger.info("No reviews found for export")
            return None
        
        # Get categories for each review
        for review in reviews:
            cursor.execute('''
            SELECT category FROM categories
            WHERE review_id = ?
            ''', (review['review_id'],))
            
            categories = [row[0] for row in cursor.fetchall()]
            review['categories'] = ", ".join(categories) if categories else ""
            
        # Get themes from action_plans
        cursor.execute('''
        SELECT title FROM action_plans
        ORDER BY created_at DESC
        LIMIT 10
        ''')
        themes = [row[0] for row in cursor.fetchall()]
        
        # Try to match reviews to themes (simplified approach)
        # In a more complex implementation, we would have a direct mapping
        for review in reviews:
            review['themes'] = ""  # Default to empty
            
            # Simple heuristic: if categories match words in theme titles, associate them
            if review['categories']:
                for theme in themes:
                    for category in review['categories'].split(", "):
                        if category.lower() in theme.lower():
                            review['themes'] = theme
                            break
                    if review['themes']:
                        break
        
        # Create a timestamped filename
        timestamp = datetime.now().strftime('%Y-%m-%d')
        filename = f"reviews_export_{timestamp}.csv"
        
        # Write the CSV file
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = [
                'Reviewer Name', 'Star Rating', 'Sentiment', 'Priority',
                'Categories', 'Themes', 'Review Text', 'Date'
            ]
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            for review in reviews:
                writer.writerow({
                    'Reviewer Name': review['username'],
                    'Star Rating': review['rating'],
                    'Sentiment': review.get('sentiment', 'Not analyzed'),
                    'Priority': review.get('priority_level', 'Not set'),
                    'Categories': review['categories'],
                    'Themes': review['themes'],
                    'Review Text': review['review_text'],
                    'Date': review.get('timestamp', 'Unknown')
                })
        
        conn.close()
        return filename
        
    except Exception as e:
        logger.error(f"Error generating CSV export: {e}")
        return None