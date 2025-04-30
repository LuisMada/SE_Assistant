"""
Implementation of Telegram bot commands
"""
import logging
import sqlite3
import json
import os
from telegram import Update
from telegram.ext import ContextTypes, filters

from utils.config import load_config
from utils.export import generate_reviews_csv
from scraper.google_play_scraper import fetch_reviews
from database.sqlite_db import get_unprocessed_reviews, get_recent_reviews, get_reviews_by_priority, DB_PATH
from analysis.analyze_reviews import analyze_app_reviews
from analysis.action_plans import get_action_plans, generate_action_plans, get_high_priority_reviews, save_action_plans

logger = logging.getLogger(__name__)

# Ensure all handlers are exposed
__all__ = [
    'start_command', 'help_command', 'report_command', 
    'steps_command', 'process_command', 'reset_command', 
    'handle_reset_confirmation', 'handle_theme_selection', 'export_command'
]

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
        f"• /steps - Get action plans for high-priority issues\n"
        f"• /export - Download reviews as a CSV file\n"
        f"• /help - Show this help message\n\n"
        f"To get started, use /process to collect and analyze app reviews."
    )
    
    await update.message.reply_html(welcome_message)

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reset the database by clearing all tables."""
    try:
        # Ask for confirmation
        confirm_message = await update.message.reply_text(
            "⚠️ Are you sure you want to reset the database? "
            "This will delete ALL reviews and analysis data.\n\n"
            "Reply with 'yes' to confirm or 'no' to cancel."
        )
        
        # Store the original user's ID to check replies
        context.user_data['awaiting_reset_confirmation'] = True
        context.user_data['reset_request_user_id'] = update.effective_user.id
        
    except Exception as e:
        logger.error(f"Error in reset command: {e}")
        await update.message.reply_text(f"Error: {str(e)}")

# Add a message handler to process the confirmation
async def handle_reset_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the confirmation for database reset."""
    # Only process if we're awaiting confirmation
    if not context.user_data.get('awaiting_reset_confirmation'):
        return
    
    # Verify it's the same user who requested the reset
    if update.effective_user.id != context.user_data.get('reset_request_user_id'):
        return
    
    # Clear the flag
    context.user_data['awaiting_reset_confirmation'] = False
    
    response = update.message.text.lower()
    
    if response == 'yes':
        try:
            # Connect to the database
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # Get a list of all tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            
            # Clear all tables
            for table in tables:
                table_name = table[0]
                if table_name != 'sqlite_sequence':  # Skip the SQLite internal table
                    cursor.execute(f"DELETE FROM {table_name}")
            
            # Commit the changes
            conn.commit()
            conn.close()
            
            await update.message.reply_text(
                "✅ Database has been reset. All reviews and analysis data have been deleted.\n"
                "Use /process to fetch and analyze new reviews."
            )
            
        except Exception as e:
            logger.error(f"Error resetting database: {e}")
            await update.message.reply_text(f"Error resetting database: {str(e)}")
    
    elif response == 'no':
        await update.message.reply_text("Database reset cancelled.")
    
    else:
        await update.message.reply_text(
            "I didn't understand your response. Database reset cancelled.\n"
            "Please reply with 'yes' or 'no' next time."
        )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /help is issued."""
    help_message = (
        "📋 *App Review Bot Commands*\n\n"
        "*/process* - Scrape new reviews from Google Play, analyze sentiment, categorize, and assign priorities\n\n"
        "*/report* - Get a weekly summary of reviews including sentiment breakdown and common issues\n\n"
        "*/steps* - Generate action plans for high-priority issues\n\n"
        "*/export* - Download analyzed reviews as a CSV file (last 7 days)\n\n"
        "*/reset* - Clear the database and start fresh (use with caution)\n\n"
        "*/help* - Show this help message"
    )
    
    await update.message.reply_markdown(help_message)

async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate a weekly report of app reviews."""
    import sqlite3
    from database.sqlite_db import DB_PATH
    from datetime import datetime, timedelta
    
    try:
        # Indicate processing has started
        processing_message = await update.message.reply_text(
            "📊 Generating weekly report, please wait..."
        )
        
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
            await processing_message.edit_text(
                "No reviews found from the past week. Use /process to fetch reviews first."
            )
            return
            
        # Get rating distribution and calculate average
        cursor.execute('''
        SELECT rating, COUNT(*) FROM reviews 
        WHERE date_added >= ?
        GROUP BY rating
        ORDER BY rating DESC
        ''', (one_week_ago,))
        ratings = cursor.fetchall()
        
        # Calculate average rating
        total_rating_points = sum(rating * count for rating, count in ratings)
        average_rating = total_rating_points / total_reviews if total_reviews > 0 else 0
        
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
            
        # Get current action plan themes
        try:
            cursor.execute('''
            SELECT title, review_count FROM action_plans
            ORDER BY review_count DESC
            ''')
            themes = cursor.fetchall()
        except sqlite3.OperationalError:
            # If action_plans table doesn't exist or has issues
            themes = []
        
        # Close connection
        conn.close()
        
        # Format and send report in the new format
        report = f"📊 *Weekly Review Summary*\n"
        report += f"📝 Total Reviews: {total_reviews}  \n"
        report += f"⭐ Average Rating: {average_rating:.1f}  \n\n"
        
        # Add rating breakdown
        report += "*Rating Breakdown:*\n"
        for rating, count in ratings:
            # Create aligned star ratings
            stars = "⭐ " + str(rating) + " stars"
            if rating == 1:
                stars = "⭐ 1 star "  # Extra space for alignment
                
            percentage = (count / total_reviews) * 100
            report += f"{stars} — {count} ({percentage:.0f}%)\n"
        
        report += "\n"
        
        # Add sentiment distribution if available
        if sentiments:
            report += "*Sentiment:*\n"
            for sentiment, count in sentiments:
                emoji = "😊" if sentiment == "Positive" else "😐" if sentiment == "Neutral" else "😞"
                percentage = (count / total_reviews) * 100
                report += f"{emoji} {sentiment} — {count} ({percentage:.0f}%)\n"
            report += "\n"
        
        # Add top categories if available
        if top_categories:
            report += "*Top Categories:*\n"
            for category, count in top_categories:
                percentage = (count / total_reviews) * 100
                report += f"• {category} — {count} ({percentage:.0f}%)\n"
            report += "\n"
        
        # Add priority distribution if available
        if priorities:
            report += "*Priority Levels:*\n"
            priority_labels = {
                1: "🔴 Critical",
                2: "🟠 High   ",
                3: "🟡 Medium ",
                4: "🟢 Low    ",
                5: "🔵 Minimal"
            }
            for priority, count in priorities:
                percentage = (count / total_reviews) * 100
                label = priority_labels.get(priority, f"Priority {priority}")
                report += f"{label} — {count} ({percentage:.0f}%)\n"
            report += "\n"
            
        # Add current themes if available
        if themes:
            report += "*Key Issue Themes:*\n"
            for title, count in themes:
                report += f"• {title} — {count} reviews\n"
            report += "\n"
            report += "→ Use /steps to view action plans for these issues\n"
            report += "→ Use /export to download reviews as CSV"
        
        # Add note if sentiment analysis hasn't been done yet
        if not sentiments:
            report += "\n_Note: Sentiment analysis has not been performed yet. Use /process to analyze reviews._"
            
        # Try to send with Markdown, fallback to plain text if needed
        try:
            await processing_message.edit_text(report, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error sending report with markdown: {e}")
            # Send without formatting
            plain_report = report.replace("*", "").replace("_", "")
            await processing_message.edit_text(plain_report)
        
    except Exception as e:
        logger.error(f"Error in report command: {e}")
        await update.message.reply_text(f"Error generating report: {str(e)}")

async def export_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Export analyzed reviews as a CSV file."""
    try:
        # Indicate processing has started
        message = await update.message.reply_text("📤 Exporting latest analyzed reviews...")
        
        # Generate the CSV file
        csv_file = generate_reviews_csv(DB_PATH)
        
        if not csv_file:
            await message.edit_text(
                "No reviews found to export. Use /process to fetch and analyze reviews first."
            )
            return
        
        # Send the file
        with open(csv_file, 'rb') as file:
            await context.bot.send_document(
                chat_id=update.effective_chat.id,
                document=file,
                filename=os.path.basename(csv_file)
            )
            
        # Delete the temporary file
        try:
            os.remove(csv_file)
            logger.info(f"Temporary CSV file {csv_file} deleted successfully")
        except Exception as e:
            logger.error(f"Error deleting temporary CSV file: {e}")
        
    except Exception as e:
        logger.error(f"Error in export command: {e}")
        await update.message.reply_text(f"Error exporting reviews: {str(e)}")

async def steps_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generate action plans for high-priority issues and let user select a theme."""
    from utils.config import load_config
    
    try:
        # Indicate processing has started
        processing_message = await update.message.reply_text(
            "🔍 Analyzing high-priority issues and identifying themes..."
        )
        
        # Connect to database
        conn = sqlite3.connect(DB_PATH)
        
        # Get action plans from database
        action_plans = get_action_plans(conn)
        
        # If no action plans, generate them
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
        
        # Display the list of themes for selection
        themes_list = "🚨 *Action Plan Themes Identified*\n\n"
        themes_list += "Select a theme number to see the detailed action plan:\n\n"
        
        # Store action plans in user data for later reference
        context.user_data['action_plans'] = action_plans
        context.user_data['awaiting_theme_selection'] = True
        context.user_data['theme_selection_user_id'] = update.effective_user.id
        
        for i, plan in enumerate(action_plans, 1):
            title = plan['title']
            review_count = plan.get('review_count', 0)
            
            # Escape markdown special characters
            safe_title = title.replace("*", "\\*").replace("_", "\\_").replace("`", "\\`").replace("[", "\\[")
            
            themes_list += f"*{i}.* {safe_title} ({review_count} reviews)\n"
        
        themes_list += "\nReply with the number of the theme you want to explore."
        
        try:
            await processing_message.edit_text(themes_list, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error with markdown in themes list: {e}")
            # Fallback to plain text
            simple_list = "Action Plan Themes Identified:\n\n"
            for i, plan in enumerate(action_plans, 1):
                simple_list += f"{i}. {plan['title']} ({plan.get('review_count', 0)} reviews)\n"
            simple_list += "\nReply with the number of the theme you want to explore."
            await processing_message.edit_text(simple_list)
        
    except Exception as e:
        logger.error(f"Error in steps command: {e}")
        await update.message.reply_text(f"Error retrieving action plans: {str(e)}")

async def handle_theme_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle theme selection after the /steps command."""
    # Only process if we're awaiting theme selection
    if not context.user_data.get('awaiting_theme_selection'):
        return
    
    # Verify it's the same user who requested the themes
    if update.effective_user.id != context.user_data.get('theme_selection_user_id'):
        return
    
    # Get the text and try to parse it as a number
    selection_text = update.message.text.strip()
    
    try:
        selection = int(selection_text)
        
        # Get the action plans from user data
        action_plans = context.user_data.get('action_plans', [])
        
        # Check if the selection is valid
        if selection < 1 or selection > len(action_plans):
            await update.message.reply_text(
                f"Please select a valid theme number between 1 and {len(action_plans)}."
            )
            return
        
        # Get the selected action plan
        plan = action_plans[selection - 1]
        
        # Format the detailed action plan
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
        
        # Build the detailed message
        detailed_message = (
            f"*Action Plan for Theme: {title}* ({review_count} reports)\n\n"
            f"*Summary:* {summary}\n\n"
            f"*Action Steps:*\n{steps_text}\n"
            f"*Suggested User Response:*\n{user_response}\n"
            f"{samples_text}\n\n"
            f"Type /steps to see all themes again.\n"
            f"Use /export to download all reviews as CSV."
        )
        
        # Clear the selection flag
        context.user_data['awaiting_theme_selection'] = False
        
        # Send the detailed action plan
        try:
            await update.message.reply_markdown(detailed_message)
        except Exception as e:
            # If markdown fails, try plain text
            logger.error(f"Error with markdown in detailed plan: {e}")
            simple_message = f"Action Plan for Theme: {title}\n\nSummary: {summary}\n\nAction Steps:\n{steps_text}\n"
            await update.message.reply_text(simple_message)
            
    except ValueError:
        await update.message.reply_text(
            "Please enter a valid number to select a theme. Type /steps to see the list again."
        )
    except Exception as e:
        logger.error(f"Error handling theme selection: {e}")
        await update.message.reply_text(
            "Something went wrong processing your selection. Type /steps to try again."
        )

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
                    f"Use /report for a summary or /export to download reviews as CSV."
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