#!/usr/bin/env python3
"""
App Review Telegram Bot - Main Entry Point
"""
import logging
import os
from bot.telegram_bot import setup_bot
from database.sqlite_db import setup_database
from utils.config import load_config
from utils.logger import setup_logger

def main():
    """Main function to start the bot"""
    # Set up logging
    setup_logger()
    logger = logging.getLogger(__name__)
    logger.info("Starting App Review Telegram Bot...")
    
    # Create necessary directories if they don't exist
    for directory in ['logs', 'data']:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
    
    # Load configuration
    config = load_config()
    
    # Validate required configuration
    if not config.get('TELEGRAM_TOKEN'):
        logger.error("TELEGRAM_TOKEN is not set in .env file")
        print("Error: TELEGRAM_TOKEN is required. Please set it in your .env file.")
        return
    
    if not config.get('APP_ID'):
        logger.warning("APP_ID is not set in .env file. You'll need to set it before using /process command.")
    
    if not config.get('OPENAI_API_KEY'):
        logger.warning("OPENAI_API_KEY is not set in .env file. Analysis features will be disabled.")
    
    logger.info("Configuration loaded successfully")
    
    # Set up database
    setup_database()
    logger.info("Database initialized successfully")
    
    # Start the Telegram bot
    bot = setup_bot(config)
    logger.info("Bot initialized, starting polling...")
    
    # Print startup message
    print(f"✅ App Review Bot started successfully!")
    print(f"🤖 Bot is now active on Telegram")
    print(f"📱 Configured to scrape reviews for app: {config.get('APP_ID', 'Not configured')}")
    print(f"⌛ Will fetch reviews from the last {config.get('DAYS_TO_SCRAPE', 7)} days")
    print(f"🔢 Maximum reviews to fetch: {config.get('MAX_REVIEWS', 100)}")
    
    # Print OpenAI configuration info
    api_key = config.get('OPENAI_API_KEY')
    if api_key:
        model = config.get('OPENAI_MODEL', 'gpt-3.5-turbo')
        print(f"🧠 OpenAI analysis enabled using model: {model}")
    else:
        print(f"⚠️  OpenAI analysis disabled (no API key)")
    
    print(f"📊 Log files are stored in the 'logs' directory")
    print(f"Ctrl+C to stop the bot")
    
    # Start polling
    bot.run_polling()
    
if __name__ == "__main__":
    main()