"""
Sentiment analysis for app reviews using OpenAI
"""
import logging
import time
from typing import Dict, Any, List, Tuple
import openai
from database.sqlite_db import mark_review_as_processed

logger = logging.getLogger(__name__)

SENTIMENT_PROMPT = """
You are analyzing the sentiment of a mobile app review.
Classify the sentiment as one of: "Positive", "Neutral", or "Negative".
Consider both the rating and the review text in your analysis.

Review text: {review_text}
Rating: {rating} out of 5 stars

Respond with only a single word: Positive, Neutral, or Negative.
"""

def analyze_sentiment(reviews: List[Dict[str, Any]], api_key: str) -> List[Dict[str, Any]]:
    """
    Analyze sentiment of reviews using OpenAI
    
    Args:
        reviews: List of review dictionaries
        api_key: OpenAI API key
        
    Returns:
        List of dictionaries with review_id, sentiment, and confidence
    """
    if not api_key:
        logger.error("OpenAI API key not provided for sentiment analysis")
        return []
        
    # Configure OpenAI client
    client = openai.OpenAI(api_key=api_key)
    
    results = []
    for review in reviews:
        try:
            review_id = review['review_id']
            review_text = review['review_text']
            rating = review['rating']
            
            logger.info(f"Analyzing sentiment for review {review_id}")
            
            # Prepare the prompt
            prompt = SENTIMENT_PROMPT.format(
                review_text=review_text,
                rating=rating
            )
            
            # Call OpenAI API
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a sentiment analysis expert."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.0,  # Use deterministic responses
                max_tokens=10     # We only need a single word
            )
            
            # Extract the sentiment from the response
            sentiment = response.choices[0].message.content.strip()
            
            # Normalize to one of our three categories
            if "positive" in sentiment.lower():
                normalized_sentiment = "Positive"
            elif "negative" in sentiment.lower():
                normalized_sentiment = "Negative"
            else:
                normalized_sentiment = "Neutral"
                
            # For now, use a fixed confidence value
            # In a more advanced implementation, this could be derived from 
            # the model's confidence scores if available
            confidence = 0.9
            
            results.append({
                "review_id": review_id,
                "sentiment": normalized_sentiment,
                "confidence": confidence
            })
            
            # Mark review as processed
            mark_review_as_processed(review_id)
            
            # Be nice to the API with a small delay
            time.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error analyzing sentiment for review {review.get('review_id', 'unknown')}: {e}")
    
    logger.info(f"Completed sentiment analysis for {len(results)} reviews")
    return results

def save_sentiment_results(results: List[Dict[str, Any]], db_conn) -> int:
    """
    Save sentiment analysis results to database
    
    Args:
        results: List of sentiment analysis results
        db_conn: Database connection
        
    Returns:
        Number of results saved
    """
    if not results:
        return 0
        
    try:
        cursor = db_conn.cursor()
        
        for result in results:
            cursor.execute('''
            INSERT OR REPLACE INTO sentiment (
                review_id, sentiment, confidence
            ) VALUES (?, ?, ?)
            ''', (
                result['review_id'],
                result['sentiment'],
                result['confidence']
            ))
        
        db_conn.commit()
        return len(results)
        
    except Exception as e:
        logger.error(f"Error saving sentiment results: {e}")
        db_conn.rollback()
        return 0

def batch_process_reviews(reviews: List[Dict[str, Any]], api_key: str, db_conn) -> Tuple[int, int]:
    """
    Process a batch of reviews for sentiment analysis and save results
    
    Args:
        reviews: List of review dictionaries
        api_key: OpenAI API key
        db_conn: Database connection
        
    Returns:
        Tuple of (processed_count, saved_count)
    """
    if not reviews:
        return 0, 0
        
    # Analyze sentiment
    results = analyze_sentiment(reviews, api_key)
    
    # Save results
    saved_count = save_sentiment_results(results, db_conn)
    
    return len(results), saved_count