"""
Implementation of Telegram bot commands
"""
import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    user = update.effective_user
    logger.info(f"User {user.id} started the bot")
    
    welcome_message = (
        f"👋 Hello {user.mention_html()}!\n\n"
        f"Welcome to the App Review Bot. I help you monitor and analyze app reviews from Google Play Store.\n\n"
        f"Here are the commands you can use:\n"
        f"• /process - Scrape and analyze new app reviews\n"
        f"• /report - Get a weekly summary of reviews\n"
        f"• /reviews - List analyzed reviews with details\n"
        f"• /steps - Get action plans for high-priority issues\n"
        f"• /help - Show this help message\n\n"
        f"To get started, use /process to collect and analyze app reviews."
    )
    
    await update.message.reply_html(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_message = (
        "📋 *App Review Bot Commands*\n\n"
        "*/process* - Scrape new reviews from Google Play, analyze sentiment, categorize, and assign priorities\n\n"
        "*/report* - Get a weekly summary of reviews including sentiment breakdown and common issues\n\n"
        "*/reviews* - List recently analyzed reviews with their sentiment, categories, and priorities\n\n"
        "*/steps* - Generate action plans for high-priority issues\n\n"
        "*/help* - Show this help message"
    )
    
    await update.message.reply_markdown(help_message)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a weekly report of app reviews."""
    import sqlite3
    from database.sqlite_db import DB_PATH
    from datetime import datetime, timedelta
    
    try:
        # Connect to the database
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Calculate the date one week ago
        one_week_ago = (datetime.now() - timedelta(days=7)).isoformat()
        
        # Get total number of reviews in the last week
        cursor.execute('''
        SELECT COUNT(*) FROM reviews 
        WHERE date_added >= ?
        ''', (one_week_ago,))
        total_reviews = cursor.fetchone()[0]
        
        if total_reviews == 0:
            await update.message.reply_text(
                "No reviews found from the past week. Use /process to fetch reviews first."
            )
            return
            
        # Get rating distribution
        cursor.execute('''
        SELECT rating, COUNT(*) FROM reviews 
        WHERE date_added >= ?
        GROUP BY rating
        ORDER BY rating DESC
        ''', (one_week_ago,))
        ratings = cursor.fetchall()
        
        # Get sentiment distribution (if any reviews have been analyzed)
        cursor.execute('''
        SELECT s.sentiment, COUNT(*) FROM reviews r
        JOIN sentiment s ON r.review_id = s.review_id
        WHERE r.date_added >= ?
        GROUP BY s.sentiment
        ''', (one_week_ago,))
        sentiments = cursor.fetchall()
        
        # Get priority distribution (if any reviews have been prioritized)
        cursor.execute('''
        SELECT p.priority_level, COUNT(*) FROM reviews r
        JOIN priorities p ON r.review_id = p.review_id
        WHERE r.date_added >= ?
        GROUP BY p.priority_level
        ORDER BY p.priority_level
        ''', (one_week_ago,))
        priorities = cursor.fetchall()
        
        # Close connection
        conn.close()
        
        # Format and send report
        report = f"📊 *Weekly Review Report*\n\n"
        report += f"Total reviews in the past week: {total_reviews}\n\n"
        
        # Add rating distribution
        report += "*Rating Distribution:*\n"
        for rating, count in ratings:
            stars = "⭐" * rating
            percentage = (count / total_reviews) * 100
            report += f"{stars}: {count} ({percentage:.1f}%)\n"
        
        report += "\n"
        
        # Add sentiment distribution if available
        if sentiments:
            report += "*Sentiment Distribution:*\n"
            for sentiment, count in sentiments:
                percentage = (count / total_reviews) * 100
                report += f"{sentiment}: {count} ({percentage:.1f}%)\n"
            report += "\n"
        
        # Add priority distribution if available
        if priorities:
            report += "*Priority Distribution:*\n"
            for priority, count in priorities:
                percentage = (count / total_reviews) * 100
                report += f"Priority {priority}: {count} ({percentage:.1f}%)\n"
        
        # Add note if sentiment analysis hasn't been done yet
        if not sentiments:
            report += "\n_Note: Sentiment analysis has not been performed yet. Use /process to analyze reviews._"
            
        await update.message.reply_markdown(report)
        
    except Exception as e:
        logger.error(f"Error in report command: {e}")
        await update.message.reply_text(f"Error generating report: {str(e)}")

async def reviews_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show a list of analyzed reviews."""
    from database.sqlite_db import get_recent_reviews
    
    try:
        # Get limit from arguments if provided, default to 5
        limit = 5
        if context.args and len(context.args) > 0:
            try:
                limit = int(context.args[0])
                # Cap at reasonable limit to avoid message size issues
                limit = min(limit, 10)
            except ValueError:
                pass
        
        # Get recent reviews
        reviews = get_recent_reviews(limit)
        
        if not reviews:
            await update.message.reply_text(
                "No reviews found. Use /process to fetch reviews first."
            )
            return
            
        # Format and send review list
        message = f"📱 *Recent {len(reviews)} Reviews*\n\n"
        
        for i, review in enumerate(reviews, 1):
            # Format review details
            rating = "⭐" * review['rating']
            
            # Format sentiment if available
            sentiment = review.get('sentiment', 'Not analyzed')
            
            # Format priority if available
            priority = review.get('priority_level')
            priority_text = f"Priority: {priority}" if priority else "Priority: Not set"
            
            # Format categories if available
            categories = review.get('categories', [])
            categories_text = ", ".join(categories) if categories else "Not categorized"
            
            # Add review text (truncate if too long)
            review_text = review['review_text']
            if len(review_text) > 100:
                review_text = review_text[:97] + "..."
                
            # Build review entry
            review_entry = (
                f"*{i}. {review['username']}* - {rating}\n"
                f"_{sentiment}_ | {priority_text}\n"
                f"Categories: {categories_text}\n"
                f"{review_text}\n\n"
            )
            
            message += review_entry
            
        # Add note about sentiment analysis if not done yet
        if all(review.get('sentiment') is None for review in reviews):
            message += "\n_Note: Reviews have not been analyzed yet. Use /process to analyze them._"
            
        await update.message.reply_markdown(message)
        
    except Exception as e:
        logger.error(f"Error in reviews command: {e}")
        await update.message.reply_text(f"Error retrieving reviews: {str(e)}")

async def steps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate action plans for high-priority issues."""
    from database.sqlite_db import get_reviews_by_priority
    
    try:
        # Get high priority reviews (priority level 1)
        high_priority_reviews = get_reviews_by_priority(1, limit=5)
        
        if not high_priority_reviews:
            await update.message.reply_text(
                "No high-priority issues found. Either there are no critical issues, or reviews need to be processed first with /process."
            )
            return
            
        # For now, just list the high-priority reviews
        # Action plan generation will be implemented in Phase 3 with OpenAI
        message = f"🚨 *High Priority Issues*\n\n"
        message += "_Note: Detailed action plans will be implemented in Phase 3 with OpenAI._\n\n"
        
        for i, review in enumerate(high_priority_reviews, 1):
            # Format categories
            categories = review.get('categories', [])
            categories_text = ", ".join(categories) if categories else "Not categorized"
            
            # Format review preview
            review_text = review['review_text']
            if len(review_text) > 100:
                review_text = review_text[:97] + "..."
                
            # Add to message
            message += (
                f"*Issue {i}:* {categories_text}\n"
                f"Rating: {'⭐' * review['rating']}\n"
                f"_{review_text}_\n\n"
            )
            
        await update.message.reply_markdown(message)
        
    except Exception as e:
        logger.error(f"Error in steps command: {e}")
        await update.message.reply_text(f"Error retrieving action plans: {str(e)}")

async def process_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process new app reviews."""
    from utils.config import load_config
    from scraper.google_play_scraper import fetch_reviews
    from database.sqlite_db import get_unprocessed_reviews
    
    await update.message.reply_text("🔍 Fetching new reviews from Google Play Store...")
    
    # Load configuration
    config = load_config()
    app_id = config['APP_ID']
    days = config['DAYS_TO_SCRAPE']
    max_reviews = config['MAX_REVIEWS']
    
    if not app_id:
        await update.message.reply_text("❌ Error: No app ID configured. Please set APP_ID in .env file.")
        return
    
    # Fetch reviews as a background task to avoid blocking the bot
    try:
        # For now, run synchronously since we haven't implemented proper async handling yet
        new_reviews_count = fetch_reviews(app_id, days, max_reviews)
        
        if new_reviews_count > 0:
            await update.message.reply_text(f"✅ Successfully fetched {new_reviews_count} new reviews!")
            
            # Get count of unprocessed reviews
            unprocessed_reviews = get_unprocessed_reviews()
            await update.message.reply_text(
                f"📊 You have {len(unprocessed_reviews)} reviews ready for analysis.\n"
                f"Sentiment analysis will be implemented in Phase 3."
            )
        else:
            await update.message.reply_text("ℹ️ No new reviews found for the specified time period.")
    
    except Exception as e:
        logger.error(f"Error in process command: {e}")
        await update.message.reply_text(f"❌ Error fetching reviews: {str(e)}")