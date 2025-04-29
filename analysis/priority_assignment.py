"""
Priority assignment for app reviews based on sentiment and categories
"""
import logging
import sqlite3
from typing import Dict, Any, List, Tuple

logger = logging.getLogger(__name__)

# Priority levels:
# 1 - Critical (needs immediate attention)
# 2 - High (should be addressed soon)
# 3 - Medium (worth addressing but not urgent)
# 4 - Low (minor issues or enhancements)
# 5 - Minimal (positive feedback or resolved issues)

# High-priority categories
HIGH_PRIORITY_CATEGORIES = [
    "Bugs/Crashes",
    "Account/Login", 
    "Payments/Billing",
    "Privacy/Security"
]

def assign_review_priority(review: Dict[str, Any], sentiment: str, categories: List[str]) -> int:
    """
    Assign a priority level to a review based on rating, sentiment, and categories
    
    Args:
        review: Review dictionary containing rating
        sentiment: Sentiment classification (Positive, Neutral, Negative)
        categories: List of categories assigned to the review
        
    Returns:
        Priority level (1-5, with 1 being highest priority)
    """
    rating = review.get('rating', 3)
    
    # Start with default priority
    priority = 3  # Medium
    
    # Adjust based on rating
    if rating <= 1:
        priority = 1  # Critical for 1-star reviews
    elif rating == 2:
        priority = 2  # High for 2-star reviews
    elif rating == 3:
        priority = 3  # Medium for 3-star reviews
    elif rating == 4:
        priority = 4  # Low for 4-star reviews
    else:  # rating == 5
        priority = 5  # Minimal for 5-star reviews
    
    # Further adjust based on sentiment
    if sentiment == "Negative" and priority > 1:
        priority -= 1  # Increase priority for negative sentiment
    elif sentiment == "Positive" and priority < 5:
        priority += 1  # Decrease priority for positive sentiment
    
    # Finally, adjust based on categories
    # Critical categories can override to increase priority
    for category in categories:
        if category in HIGH_PRIORITY_CATEGORIES and priority > 1:
            priority -= 1
            break  # Only decrease priority once
    
    # Ensure priority is in range 1-5
    return max(1, min(5, priority))

def process_priorities(reviews: List[Dict[str, Any]], db_conn) -> Tuple[int, Dict[int, int]]:
    """
    Process and assign priorities to reviews based on their sentiment and categories
    
    Args:
        reviews: List of review dictionaries
        db_conn: Database connection
        
    Returns:
        Tuple of (number of reviews processed, dictionary of priority counts)
    """
    if not reviews:
        return 0, {}
    
    processed_count = 0
    priority_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0}
    
    try:
        cursor = db_conn.cursor()
        
        for review in reviews:
            review_id = review['review_id']
            
            # Get sentiment
            cursor.execute('''
            SELECT sentiment FROM sentiment WHERE review_id = ?
            ''', (review_id,))
            result = cursor.fetchone()
            sentiment = result[0] if result else "Neutral"
            
            # Get categories
            cursor.execute('''
            SELECT category FROM categories WHERE review_id = ?
            ''', (review_id,))
            categories = [row[0] for row in cursor.fetchall()]
            
            # Assign priority
            priority = assign_review_priority(review, sentiment, categories)
            
            # Save priority
            cursor.execute('''
            INSERT OR REPLACE INTO priorities (review_id, priority_level)
            VALUES (?, ?)
            ''', (review_id, priority))
            
            # Update counts
            priority_counts[priority] = priority_counts.get(priority, 0) + 1
            processed_count += 1
            
        db_conn.commit()
        logger.info(f"Assigned priorities to {processed_count} reviews")
        
    except Exception as e:
        logger.error(f"Error assigning priorities: {e}")
        db_conn.rollback()
    
    return processed_count, priority_counts