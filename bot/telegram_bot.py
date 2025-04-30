"""
Telegram bot setup and command handlers
"""
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
from bot.commands import (
    start_command, help_command, report_command, 
    steps_command, process_command, reset_command, export_command,
    handle_reset_confirmation, handle_theme_selection
)

logger = logging.getLogger(__name__)

def setup_bot(config):
    """Set up the Telegram bot with all command handlers"""
    # Create the Application
    app = Application.builder().token(config['TELEGRAM_TOKEN']).build()
    
    # Add command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("report", report_command))
    app.add_handler(CommandHandler("steps", steps_command))
    app.add_handler(CommandHandler("process", process_command))
    app.add_handler(CommandHandler("reset", reset_command))
    app.add_handler(CommandHandler("export", export_command))
    
    # Create a handler for text messages
    text_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    app.add_handler(text_handler)
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    logger.info("Telegram bot setup complete")
    return app

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages based on conversation state."""
    # Check what the user is currently doing
    if context.user_data.get('awaiting_reset_confirmation'):
        # If waiting for reset confirmation, handle that
        await handle_reset_confirmation(update, context)
    elif context.user_data.get('awaiting_theme_selection'):
        # If waiting for theme selection, handle that
        await handle_theme_selection(update, context)
    # Add more handlers as needed for other conversation states
    # else:
    #     # Default handler for messages without context
    #     await update.message.reply_text("I'm not sure what you want. Try using a command like /help.")

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle errors in the bot"""
    logger.error(f"Update {update} caused error {context.error}")
    if update:
        await update.message.reply_text("Sorry, something went wrong. Please try again later.")