"""
Google Play Store review scraper functionality
"""
import logging
import time
from datetime import datetime, timedelta
from google_play_scraper import Sort, reviews
from database.sqlite_db import save_review

logger = logging.getLogger(__name__)

def fetch_reviews(app_id, days=7, max_reviews=100):
    """
    Fetch recent reviews from Google Play for the specified app
    
    Args:
        app_id (str): The Google Play app ID (e.g., 'com.example.app')
        days (int): Number of days in the past to fetch reviews for
        max_reviews (int): Maximum number of reviews to fetch
        
    Returns:
        int: Number of new reviews fetched and saved
    """
    logger.info(f"Fetching reviews for app {app_id} from the last {days} days (max: {max_reviews})")
    
    # Calculate date threshold as timestamp (seconds since epoch)
    cutoff_date = datetime.now() - timedelta(days=days)
    cutoff_timestamp = time.mktime(cutoff_date.timetuple())
    
    logger.info(f"Using cutoff date: {cutoff_date.isoformat()}")
    
    new_reviews_count = 0
    total_fetched = 0
    continuation_token = None
    
    try:
        # Keep fetching reviews in batches until we have enough or run out
        while total_fetched < max_reviews:
            # Fetch a batch of reviews
            try:
                if continuation_token is None:
                    # Initial fetch
                    result, continuation_token = reviews(
                        app_id,
                        lang='en', 
                        country='us',
                        sort=Sort.NEWEST,
                        count=min(100, max_reviews - total_fetched)
                    )
                    logger.info(f"Initial fetch: {len(result)} reviews retrieved")
                else:
                    # Subsequent fetch using continuation token
                    result, continuation_token = reviews(
                        app_id,
                        continuation_token=continuation_token
                    )
                    logger.info(f"Additional fetch: {len(result)} reviews retrieved")
                
                if not result:
                    logger.info("No reviews returned from fetch")
                    break
                    
                total_fetched += len(result)
                
                # Process reviews in this batch
                batch_count = process_reviews(result, app_id, cutoff_timestamp)
                new_reviews_count += batch_count
                
                # If we've reached our limit or found older reviews, stop
                if batch_count == 0 or continuation_token is None:
                    break
                
            except Exception as e:
                logger.error(f"Error during review fetch: {e}")
                break
        
        logger.info(f"Review fetch complete. Total new reviews saved: {new_reviews_count}")
        return new_reviews_count
        
    except Exception as e:
        logger.error(f"Failed to fetch reviews: {e}")
        return 0


def process_reviews(reviews_batch, app_id, cutoff_timestamp):
    """
    Process a batch of reviews, saving those that meet the date criteria
    
    Args:
        reviews_batch (list): List of review dictionaries from Google Play
        app_id (str): App ID string for creating review data
        cutoff_timestamp (float): Timestamp for filtering older reviews
        
    Returns:
        int: Number of reviews processed and saved from this batch
    """
    processed_count = 0
    
    for review in reviews_batch:
        try:
            # Check if review timestamp exists
            if 'at' not in review:
                continue
            
            # Handle the 'at' field which could be either a timestamp or datetime
            review_at = review['at']
            
            # Convert to timestamp if it's a datetime object
            if isinstance(review_at, datetime):
                review_timestamp = time.mktime(review_at.timetuple())
            else:
                review_timestamp = review_at
            
            # Check if review is within our date range
            if review_timestamp >= cutoff_timestamp:
                # Get the proper datetime for storage
                if isinstance(review_at, datetime):
                    review_date = review_at
                else:
                    review_date = datetime.fromtimestamp(review_timestamp)
                
                # Prepare review data
                review_data = {
                    'review_id': str(review['reviewId']),
                    'app_id': app_id,
                    'username': review['userName'],
                    'review_text': review['content'],
                    'rating': review['score'],
                    'timestamp': review_date.isoformat()
                }
                
                # Save to database
                if save_review(review_data):
                    processed_count += 1
            else:
                # Found a review older than our cutoff
                logger.info(f"Found review older than cutoff date")
                return processed_count
                
        except Exception as e:
            logger.error(f"Error processing review: {e}")
            continue
            
    return processed_count