"""
Generation of action plans for app reviews using OpenAI
"""
import logging
import sqlite3
from typing import Dict, Any, List, Tuple
import openai

logger = logging.getLogger(__name__)

ACTION_PLAN_PROMPT = """
You are an app product manager. Based on user reviews, create a concise action plan to address the issues raised.

Category: {category}
Issue summary: Multiple users report issues related to {category} with an average rating of {avg_rating}/5 stars.

Here are some example reviews:
{review_examples}

Create a brief action plan with 2-3 specific steps to address these issues. Be concise but specific.
Format your response as a bulleted list with a brief title. Don't include any introduction or conclusion text.
"""

def generate_action_plan(category: str, reviews: List[Dict[str, Any]], client) -> str:
    """
    Generate an action plan for a specific category based on review samples
    
    Args:
        category: The category to generate an action plan for
        reviews: List of review dictionaries in this category
        client: OpenAI client
        
    Returns:
        Generated action plan text
    """
    try:
        # Calculate average rating
        total_rating = sum(review.get('rating', 0) for review in reviews)
        avg_rating = round(total_rating / len(reviews), 1) if reviews else 0
        
        # Get up to 3 sample reviews for this category
        sample_reviews = reviews[:3]
        review_examples = "\n".join([
            f"- \"{review['review_text']}\" (Rating: {review['rating']}/5)" 
            for review in sample_reviews
        ])
        
        # Prepare the prompt
        prompt = ACTION_PLAN_PROMPT.format(
            category=category,
            avg_rating=avg_rating,
            review_examples=review_examples
        )
        
        # Call OpenAI API
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a product manager creating action plans from app reviews."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,  # Some creativity is good for action plans
            max_tokens=200    # Keep it concise
        )
        
        # Extract action plan from the response
        action_plan = response.choices[0].message.content.strip()
        
        return action_plan
        
    except Exception as e:
        logger.error(f"Error generating action plan for category {category}: {e}")
        return f"Error generating action plan: {str(e)}"

def get_high_priority_categories(db_conn) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """
    Get categories with high-priority reviews and sample reviews for each
    
    Args:
        db_conn: Database connection
        
    Returns:
        List of tuples with (category, list of review dictionaries)
    """
    try:
        cursor = db_conn.cursor()
        
        # Get all categories that have high-priority reviews (priority 1-2)
        cursor.execute('''
        SELECT DISTINCT c.category
        FROM categories c
        JOIN priorities p ON c.review_id = p.review_id
        WHERE p.priority_level <= 2
        ''')
        
        categories = [row[0] for row in cursor.fetchall()]
        result = []
        
        for category in categories:
            # Get sample reviews for this category
            cursor.execute('''
            SELECT r.review_id, r.username, r.review_text, r.rating, 
                   s.sentiment, p.priority_level
            FROM reviews r
            JOIN categories c ON r.review_id = c.review_id
            JOIN priorities p ON r.review_id = p.review_id
            LEFT JOIN sentiment s ON r.review_id = s.review_id
            WHERE c.category = ? AND p.priority_level <= 2
            ORDER BY p.priority_level ASC, r.date_added DESC
            LIMIT 5
            ''', (category,))
            
            reviews = [
                {
                    'review_id': row[0],
                    'username': row[1],
                    'review_text': row[2],
                    'rating': row[3],
                    'sentiment': row[4],
                    'priority_level': row[5]
                }
                for row in cursor.fetchall()
            ]
            
            if reviews:
                result.append((category, reviews))
        
        return result
        
    except Exception as e:
        logger.error(f"Error getting high-priority categories: {e}")
        return []

def generate_action_plans(db_conn, api_key: str) -> Dict[str, str]:
    """
    Generate action plans for high-priority categories
    
    Args:
        db_conn: Database connection
        api_key: OpenAI API key
        
    Returns:
        Dictionary mapping categories to action plans
    """
    if not api_key:
        logger.error("OpenAI API key not provided for action plan generation")
        return {}
    
    try:
        # Configure OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Get high-priority categories with sample reviews
        category_reviews = get_high_priority_categories(db_conn)
        
        if not category_reviews:
            logger.info("No high-priority categories found for action plans")
            return {}
        
        action_plans = {}
        cursor = db_conn.cursor()
        
        for category, reviews in category_reviews:
            logger.info(f"Generating action plan for category: {category}")
            
            # Generate action plan
            action_plan = generate_action_plan(category, reviews, client)
            
            if action_plan:
                # Save to database
                cursor.execute('''
                INSERT OR REPLACE INTO action_plans (category, priority_level, action_plan)
                VALUES (?, ?, ?)
                ''', (category, 1, action_plan))
                
                action_plans[category] = action_plan
        
        db_conn.commit()
        logger.info(f"Generated {len(action_plans)} action plans")
        
        return action_plans
        
    except Exception as e:
        logger.error(f"Error generating action plans: {e}")
        if 'cursor' in locals() and 'db_conn' in locals():
            db_conn.rollback()
        return {}

def get_action_plans(db_conn) -> List[Dict[str, Any]]:
    """
    Get all action plans from the database
    
    Args:
        db_conn: Database connection
        
    Returns:
        List of action plan dictionaries
    """
    try:
        cursor = db_conn.cursor()
        
        cursor.execute('''
        SELECT category, priority_level, action_plan
        FROM action_plans
        ORDER BY priority_level, category
        ''')
        
        return [
            {
                'category': row[0],
                'priority_level': row[1],
                'action_plan': row[2]
            }
            for row in cursor.fetchall()
        ]
        
    except Exception as e:
        logger.error(f"Error retrieving action plans: {e}")
        return []