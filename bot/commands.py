
"""
Implementation of Telegram bot commands
"""
import logging
import sqlite3
import json
from telegram import Update
from telegram.ext import ContextTypes

from utils.config import load_config
from scraper.google_play_scraper import fetch_reviews
from database.sqlite_db import get_unprocessed_reviews, get_recent_reviews, get_reviews_by_priority, DB_PATH
from analysis.analyze_reviews import analyze_app_reviews
from analysis.action_plans import get_action_plans, generate_action_plans, get_high_priority_reviews, save_action_plans

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
        
        # Get top categories
        try:
            cursor.execute('''
            SELECT c.category, COUNT(*) FROM reviews r
            JOIN categories c ON r.review_id = c.review_id
            WHERE r.date_added >= ?
            GROUP BY c.category
            ORDER BY COUNT(*) DESC
            LIMIT 5
            ''', (one_week_ago,))
            top_categories = cursor.fetchall()
        except sqlite3.OperationalError:
            # If categories table doesn't exist yet
            top_categories = []
        
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
                emoji = "😊" if sentiment == "Positive" else "😐" if sentiment == "Neutral" else "😞"
                percentage = (count / total_reviews) * 100
                report += f"{emoji} {sentiment}: {count} ({percentage:.1f}%)\n"
            report += "\n"
        
        # Add top categories if available
        if top_categories:
            report += "*Top Categories:*\n"
            for category, count in top_categories:
                percentage = (count / total_reviews) * 100
                report += f"• {category}: {count} ({percentage:.1f}%)\n"
            report += "\n"
        
        # Add priority distribution if available
        if priorities:
            report += "*Priority Distribution:*\n"
            priority_labels = {
                1: "🔴 Critical", 
                2: "🟠 High", 
                3: "🟡 Medium", 
                4: "🟢 Low", 
                5: "🔵 Minimal"
            }
            for priority, count in priorities:
                percentage = (count / total_reviews) * 100
                label = priority_labels.get(priority, f"Priority {priority}")
                report += f"{label}: {count} ({percentage:.1f}%)\n"
        
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
            sentiment_emoji = ""
            if sentiment == "Positive":
                sentiment_emoji = "😊 "
            elif sentiment == "Negative":
                sentiment_emoji = "😞 "
            elif sentiment == "Neutral":
                sentiment_emoji = "😐 "
            
            # Format priority if available
            priority = review.get('priority_level')
            if priority == 1:
                priority_text = "🔴 Critical"
            elif priority == 2:
                priority_text = "🟠 High"
            elif priority == 3:
                priority_text = "🟡 Medium"
            elif priority == 4:
                priority_text = "🟢 Low"
            elif priority == 5:
                priority_text = "🔵 Minimal"
            else:
                priority_text = "Priority: Not set"
            
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
                f"{sentiment_emoji}_{sentiment}_ | {priority_text}\n"
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
    from utils.config import load_config
    
    try:
        # Indicate processing has started
        processing_message = await update.message.reply_text(
            "🔍 Analyzing high-priority issues and generating action plans..."
        )
        
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        
        # Get action plans from database
        action_plans = get_action_plans(conn)
        
        # If no action plans, get high priority reviews to give context
        if not action_plans:
            # Load configuration to get OpenAI API key
            config = load_config()
            api_key = config.get('OPENAI_API_KEY')
            
            if not api_key:
                await processing_message.edit_text(
                    "⚠️ OpenAI API key not configured. Cannot generate action plans.\n"
                    "Please set OPENAI_API_KEY in your .env file."
                )
                return
                
            # Get high priority reviews
            high_priority_reviews = get_high_priority_reviews(conn)
            
            if not high_priority_reviews:
                await processing_message.edit_text(
                    "ℹ️ No high-priority issues found. Either there are no critical issues, "
                    "or reviews need to be processed first with /process."
                )
                return
                
            # Update status
            await processing_message.edit_text(
                f"🧩 Found {len(high_priority_reviews)} high-priority reviews. "
                f"Clustering into themes and generating action plans..."
            )
            
            # Generate action plans
            action_plans = generate_action_plans(conn, api_key)
            
            # Save action plans to database
            if action_plans:
                save_action_plans(conn, action_plans)
            else:
                # Just list some high priority reviews if we couldn't generate plans
                limited_reviews = high_priority_reviews[:5]  # Limit to 5 reviews
                
                message = "🚨 *High Priority Issues*\n\n"
                message += "Could not generate themed action plans. Here are the current high priority issues:\n\n"
                
                for i, review in enumerate(limited_reviews, 1):
                    # Format categories
                    categories = review.get('categories', [])
                    categories_text = ", ".join(categories) if categories else "Not categorized"
                    
                    # Priority emoji
                    priority_emoji = "🔴" if review.get('priority_level', 0) == 1 else "🟠"
                    
                    # Format review preview - Ensure proper escaping for markdown
                    review_text = review['review_text']
                    # Escape markdown special characters
                    review_text = review_text.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
                    if len(review_text) > 100:
                        review_text = review_text[:97] + "..."
                        
                    # Add to message
                    message += (
                        f"*Issue {i}:* {priority_emoji} {categories_text}\n"
                        f"Rating: {'⭐' * review['rating']}\n"
                        f"_{review_text}_\n\n"
                    )
                
                try:
                    await processing_message.edit_text(message, parse_mode='Markdown')
                except Exception as e:
                    # If markdown parsing fails, send without formatting
                    logger.error(f"Error with markdown formatting: {e}")
                    simple_message = "🚨 High Priority Issues\n\n" + "\n".join([r['review_text'][:100] for r in limited_reviews])
                    await processing_message.edit_text(simple_message)
                return
        
        # Build the themes report
        header = "🚨 *Action Plans for High Priority Issues*\n\n"
        header += f"Found {len(action_plans)} issue themes:\n\n"
        
        try:
            await processing_message.edit_text(header, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error with header markdown: {e}")
            await processing_message.edit_text("Action Plans for High Priority Issues:")
        
        # Send each action plan as a separate message to avoid length issues
        for i, plan in enumerate(action_plans, 1):
            title = plan['title']
            summary = plan.get('summary', 'No summary available')
            
            # Handle action_steps - could be JSON string or list
            action_steps = plan.get('action_steps', [])
            if isinstance(action_steps, str):
                try:
                    action_steps = json.loads(action_steps)
                except:
                    # If parsing fails, treat as a single item
                    action_steps = [action_steps]
            
            # Ensure proper escaping for markdown
            title = title.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
            summary = summary.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
            
            # Format action steps with proper escaping
            steps_text = ""
            for step in action_steps:
                # Escape markdown special characters in each step
                safe_step = str(step).replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
                steps_text += f"• {safe_step}\n"
            
            # Get user response with proper escaping
            user_response = plan.get('user_response', 'No suggested response available')
            user_response = user_response.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
            
            review_count = plan.get('review_count', 0)
            
            # Try to get review samples from JSON if available
            review_samples = []
            if isinstance(plan.get('review_samples'), str):
                try:
                    review_samples = json.loads(plan.get('review_samples', '[]'))
                except:
                    review_samples = []
            else:
                review_samples = plan.get('review_samples', [])
            
            # Format sample reviews with proper escaping
            samples_text = ""
            if review_samples:
                samples_text = "\n*Sample Reviews:*\n"
                for j, sample in enumerate(review_samples, 1):
                    # Escape markdown special characters
                    safe_sample = str(sample).replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
                    if len(safe_sample) > 100:
                        safe_sample = safe_sample[:97] + "..."
                    samples_text += f"_{j}. \"{safe_sample}\"_\n"
            
            # Build the message
            plan_message = (
                f"*Theme {i}: {title}* ({review_count} reports)\n"
                f"*Summary:* {summary}\n\n"
                f"*Action Plan:*\n{steps_text}\n"
                f"*Suggested User Response:*\n{user_response}\n"
                f"{samples_text}"
            )
            
            # Send message with fallback for formatting issues
            try:
                await update.message.reply_markdown(plan_message)
            except Exception as e:
                # If markdown fails, try plain text
                logger.error(f"Error with markdown in plan {i}: {e}")
                simple_message = f"Theme {i}: {title}\n\nSummary: {summary}\n\nAction Plan:\n{steps_text}\n"
                await update.message.reply_text(simple_message)
        
        # Final message with tips - use simpler formatting
        tips_message = (
            "💡 *Tips:*\n"
            "• Action plans are automatically generated based on current issues\n"
            "• To create workflow reference files, add text files to the 'workflows' directory\n"
            "• Name workflow files to match common issues (e.g., 'login\\_problems.txt')\n"
            "• Run /process regularly to keep analysis current"
        )
        
        try:
            await update.message.reply_markdown(tips_message)
        except Exception as e:
            # Fallback to plain text
            logger.error(f"Error with markdown in tips: {e}")
            simple_tips = "💡 Tips:\n• Action plans are automatically generated based on current issues\n• Run /process regularly to keep analysis current"
            await update.message.reply_text(simple_tips)
        
    except Exception as e:
        logger.error(f"Error in steps command: {e}")
        await update.message.reply_text(f"Error retrieving action plans: {str(e)}")

async def process_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Process new app reviews."""
    from utils.config import load_config
    from scraper.google_play_scraper import fetch_reviews
    from database.sqlite_db import get_unprocessed_reviews
    
    # Indicate processing has started
    processing_message = await update.message.reply_text("🔍 Fetching new reviews from Google Play Store...")
    
    # Load configuration
    config = load_config()
    app_id = config['APP_ID']
    days = config['DAYS_TO_SCRAPE']
    max_reviews = config['MAX_REVIEWS']
    
    if not app_id:
        await processing_message.edit_text("❌ Error: No app ID configured. Please set APP_ID in .env file.")
        return
    
    # Fetch reviews
    try:
        new_reviews_count = fetch_reviews(app_id, days, max_reviews)
        
        if new_reviews_count > 0:
            await processing_message.edit_text(f"✅ Successfully fetched {new_reviews_count} new reviews!")
            
            # Get count of unprocessed reviews
            unprocessed_reviews = get_unprocessed_reviews()
            
            # Check if OpenAI API key is configured
            if not config.get('OPENAI_API_KEY'):
                await update.message.reply_text(
                    "⚠️ Warning: OpenAI API key not configured. Cannot proceed with analysis.\n"
                    "Please set OPENAI_API_KEY in your .env file."
                )
                return
                
            # Indicate that analysis is starting
            analysis_message = await update.message.reply_text(
                f"🧠 Analyzing {len(unprocessed_reviews)} reviews...\n"
                f"This may take a minute..."
            )
            
            # Run analysis
            results = analyze_app_reviews(config)
            
            if results['success']:
                # Format success message
                reviews_processed = results['reviews_processed']
                sentiment_processed = results.get('sentiment_processed', 0)
                categories_processed = results.get('categories_processed', 0)
                priorities_processed = results.get('priorities_processed', 0)
                action_plans = results.get('action_plans_generated', 0)
                processing_time = results.get('processing_time_seconds', 0)
                
                success_message = (
                    f"✅ Analysis complete!\n\n"
                    f"📊 *Analysis Results:*\n"
                    f"• Reviews processed: {reviews_processed}\n"
                    f"• Sentiment analyzed: {sentiment_processed}\n"
                    f"• Categories assigned: {categories_processed}\n"
                    f"• Priorities assigned: {priorities_processed}\n"
                    f"• Action plans generated: {action_plans}\n"
                    f"• Processing time: {processing_time} seconds\n\n"
                    f"Use /reviews to see analyzed reviews or /report for a summary."
                )
                
                await analysis_message.edit_text(success_message, parse_mode='Markdown')
            else:
                # Format error message
                error = results.get('error', 'Unknown error')
                await analysis_message.edit_text(f"❌ Error during analysis: {error}")
        else:
            await processing_message.edit_text("ℹ️ No new reviews found for the specified time period.")
    
    except Exception as e:
        logger.error(f"Error in process command: {e}")
        await processing_message.edit_text(f"❌ Error fetching or processing reviews: {str(e)}")