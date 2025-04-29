"""
Categorization of app reviews using OpenAI
"""
import logging
import time
from typing import Dict, Any, List, Tuple
import openai
import sqlite3

logger = logging.getLogger(__name__)

# Define standard categories for app reviews
STANDARD_CATEGORIES = [
    "UI/UX", 
    "Performance", 
    "Bugs/Crashes",
    "Feature Request",
    "Account/Login",
    "Pricing",
    "Customer Support",
    "Notifications",
    "Privacy/Security",
    "Payments/Billing",
    "Content",
    "Update Issues",
    "Installation Issues",
    "General Feedback"
]

CATEGORY_PROMPT = """
You are categorizing a mobile app review into relevant topics.
Review each comment carefully and assign relevant categories from the following list:
{categories}

A review can belong to multiple categories if it mentions multiple issues.
Pick a maximum of 3 most relevant categories.

Review: "{review_text}"
Rating: {rating} out of 5 stars

Respond with ONLY the category names, separated by commas.
Example: "UI/UX, Performance, Bugs/Crashes"
"""

def categorize_review(review: Dict[str, Any], client, categories: List[str] = STANDARD_CATEGORIES) -> List[str]:
    """
    Categorize a single review using OpenAI
    
    Args:
        review: Review dictionary
        client: OpenAI client
        categories: List of categories to choose from
        
    Returns:
        List of assigned categories
    """
    try:
        # Prepare the prompt
        prompt = CATEGORY_PROMPT.format(
            categories=", ".join(categories),
            review_text=review['review_text'],
            rating=review['rating']
        )
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are an expert at categorizing app reviews."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.0,  # Use deterministic responses
            max_tokens=50     # Enough for several categories
        )
        
        # Extract categories from the response
        categories_text = response.choices[0].message.content.strip()
        
        # Split by comma and clean up whitespace
        assigned_categories = [cat.strip() for cat in categories_text.split(',')]
        
        # Validate against our standard categories (case-insensitive matching)
        valid_categories = []
        for assigned_cat in assigned_categories:
            for standard_cat in categories:
                if assigned_cat.lower() == standard_cat.lower():
                    valid_categories.append(standard_cat)  # Use the standard formatting
                    break
                    
        return valid_categories
        
    except Exception as e:
        logger.error(f"Error categorizing review {review.get('review_id', 'unknown')}: {e}")
        return []

def categorize_reviews(reviews: List[Dict[str, Any]], api_key: str) -> Dict[str, List[str]]:
    """
    Categorize a batch of reviews using OpenAI
    
    Args:
        reviews: List of review dictionaries
        api_key: OpenAI API key
        
    Returns:
        Dictionary mapping review_id to list of categories
    """
    if not api_key or not reviews:
        return {}
        
    # Configure OpenAI client
    client = openai.OpenAI(api_key=api_key)
    
    results = {}
    for review in reviews:
        try:
            review_id = review['review_id']
            
            logger.info(f"Categorizing review {review_id}")
            
            # Get categories for this review
            categories = categorize_review(review, client)
            
            if categories:
                results[review_id] = categories
                
            # Be nice to the API with a small delay
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error in categorization for review {review.get('review_id', 'unknown')}: {e}")
    
    logger.info(f"Completed categorization for {len(results)} reviews")
    return results

def save_category_results(results: Dict[str, List[str]], db_conn) -> int:
    """
    Save categorization results to database
    
    Args:
        results: Dictionary mapping review_id to categories
        db_conn: Database connection
        
    Returns:
        Number of category associations saved
    """
    if not results:
        return 0
        
    try:
        cursor = db_conn.cursor()
        
        # First delete any existing categories for these reviews
        for review_id in results.keys():
            cursor.execute('''
            DELETE FROM categories WHERE review_id = ?
            ''', (review_id,))
        
        # Then insert new categories
        count = 0
        for review_id, categories in results.items():
            for category in categories:
                cursor.execute('''
                INSERT INTO categories (review_id, category)
                VALUES (?, ?)
                ''', (review_id, category))
                count += 1
        
        db_conn.commit()
        return count
        
    except Exception as e:
        logger.error(f"Error saving category results: {e}")
        db_conn.rollback()
        return 0

def batch_process_categories(reviews: List[Dict[str, Any]], api_key: str, db_conn) -> Tuple[int, int]:
    """
    Process a batch of reviews for categorization and save results
    
    Args:
        reviews: List of review dictionaries
        api_key: OpenAI API key
        db_conn: Database connection
        
    Returns:
        Tuple of (processed_review_count, saved_category_count)
    """
    if not reviews:
        return 0, 0
        
    # Categorize reviews
    results = categorize_reviews(reviews, api_key)
    
    # Save results
    saved_count = save_category_results(results, db_conn)
    
    return len(results), saved_count