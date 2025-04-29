"""
Google Play Store review scraper functionality
"""
import logging
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
    cutoff_timestamp = cutoff_date.timestamp()
    
    logger.info(f"Using cutoff date: {cutoff_date.isoformat()}")
    
    new_reviews_count = 0
    total_fetched = 0
    
    try:
        # Initial fetch
        result, continuation_token = reviews(
            app_id,
            lang='en',
            country='us',
            sort=Sort.NEWEST,
            count=100
        )
        
        if not result:
            logger.info("No reviews returned from initial fetch")
            return 0
            
        total_fetched += len(result)
        logger.info(f"Initial fetch: {len(result)} reviews retrieved")
        
        # Process first batch
        for review in result:
            # Check if review is within our date range
            if review['at'] >= cutoff_timestamp:
                # Convert to datetime for storage
                review_date = datetime.fromtimestamp(review['at'])
                
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
                    new_reviews_count += 1
            else:
                # If we've found a review older than our cutoff, we'll stop after this batch
                logger.info(f"Found review older than cutoff date")
                continuation_token = None
                break
                
        # Continue fetching if needed
        while continuation_token and total_fetched < max_reviews:
            try:
                # Fetch next batch
                more_reviews, continuation_token = reviews(
                    app_id,
                    continuation_token=continuation_token
                )
                
                if not more_reviews:
                    logger.info("No more reviews returned")
                    break
                    
                total_fetched += len(more_reviews)
                logger.info(f"Additional fetch: {len(more_reviews)} more reviews retrieved")
                
                # Process this batch
                batch_count = 0
                for review in more_reviews:
                    # Check if review is within our date range
                    if review['at'] >= cutoff_timestamp:
                        # Convert to datetime for storage
                        review_date = datetime.fromtimestamp(review['at'])
                        
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
                            new_reviews_count += 1
                            batch_count += 1
                    else:
                        # If we've found a review older than our cutoff, we'll stop
                        logger.info(f"Found review older than cutoff date")
                        continuation_token = None
                        break
                
                # If we got no new reviews in this batch, stop
                if batch_count == 0:
                    logger.info("No new reviews in this batch, stopping fetch")
                    break
                
                # If we've reached max reviews, stop
                if total_fetched >= max_reviews:
                    logger.info(f"Reached max reviews limit: {max_reviews}")
                    break
                    
            except Exception as e:
                logger.error(f"Error fetching additional reviews: {e}")
                break
        
        logger.info(f"Review fetch complete. Total new reviews saved: {new_reviews_count}")
        return new_reviews_count
        
    except Exception as e:
        logger.error(f"Failed to fetch reviews: {e}")
        return 0