"""
Main module for analyzing app reviews
Ties together sentiment analysis, categorization, and priority assignment
"""
import logging
import sqlite3
from typing import Dict, Any, List, Tuple
import time

from database.sqlite_db import get_unprocessed_reviews, DB_PATH
from analysis.sentiment_analysis import batch_process_reviews
from analysis.categorization import batch_process_categories
from analysis.priority_assignment import process_priorities
from analysis.action_plans import generate_action_plans, save_action_plans

logger = logging.getLogger(__name__)

def analyze_app_reviews(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Analyze unprocessed app reviews
    
    Args:
        config: Application configuration containing API keys
        
    Returns:
        Dictionary with analysis results and statistics
    """
    start_time = time.time()
    
    # Get OpenAI API key
    api_key = config.get('OPENAI_API_KEY')
    if not api_key:
        logger.error("OpenAI API key not found in configuration")
        return {
            "success": False,
            "error": "OpenAI API key not found in configuration",
            "reviews_processed": 0
        }
    
    # Get unprocessed reviews
    unprocessed_reviews = get_unprocessed_reviews()
    if not unprocessed_reviews:
        logger.info("No unprocessed reviews found")
        return {
            "success": True,
            "reviews_processed": 0,
            "message": "No unprocessed reviews found"
        }
    
    logger.info(f"Found {len(unprocessed_reviews)} unprocessed reviews")
    
    # Connect to database
    try:
        conn = sqlite3.connect(DB_PATH)
        
        # Process sentiment
        sentiment_processed, sentiment_saved = batch_process_reviews(
            unprocessed_reviews, api_key, conn
        )
        logger.info(f"Processed sentiment for {sentiment_processed} reviews, saved {sentiment_saved}")
        
        # Process categories
        categories_processed, categories_saved = batch_process_categories(
            unprocessed_reviews, api_key, conn
        )
        logger.info(f"Processed categories for {categories_processed} reviews, saved {categories_saved} category associations")
        
        # Assign priorities
        priorities_processed, priority_counts = process_priorities(
            unprocessed_reviews, conn
        )
        logger.info(f"Assigned priorities to {priorities_processed} reviews")
        
        # Generate action plans for high-priority issues using our new clustered approach
        action_plans = generate_action_plans(conn, api_key)
        logger.info(f"Generated {len(action_plans)} action plans")
        
        # Save generated action plans to database
        if action_plans:
            save_action_plans(conn, action_plans)
        
        conn.close()
        
        end_time = time.time()
        processing_time = round(end_time - start_time, 2)
        
        return {
            "success": True,
            "reviews_processed": len(unprocessed_reviews),
            "sentiment_processed": sentiment_processed,
            "categories_processed": categories_processed,
            "categories_saved": categories_saved,
            "priorities_processed": priorities_processed,
            "priority_counts": priority_counts,
            "action_plans_generated": len(action_plans),
            "processing_time_seconds": processing_time
        }
        
    except Exception as e:
        logger.error(f"Error in review analysis pipeline: {e}")
        return {
            "success": False,
            "error": str(e),
            "reviews_processed": 0
        }