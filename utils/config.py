"""
Configuration handling for the App Review Bot
"""
import os
import json
import logging
from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Default configuration
DEFAULT_CONFIG = {
    'APP_ID': '',              # Google Play app ID to scrape reviews from
    'DAYS_TO_SCRAPE': 7,       # Number of days in the past to scrape reviews
    'MAX_REVIEWS': 50,        # Maximum number of reviews to scrape
    'OPENAI_MODEL': 'gpt-3.5-turbo',  # OpenAI model to use for analysis
}

def load_config():
    """Load configuration from .env file and create config if it doesn't exist"""
    # Load environment variables from .env file
    load_dotenv()
    
    config = DEFAULT_CONFIG.copy()
    
    # Override with environment variables
    config['TELEGRAM_TOKEN'] = os.getenv('TELEGRAM_TOKEN', '')
    config['OPENAI_API_KEY'] = os.getenv('OPENAI_API_KEY', '')
    config['APP_ID'] = os.getenv('APP_ID', config['APP_ID'])
    
    # Try to parse numeric values from environment variables
    try:
        if os.getenv('DAYS_TO_SCRAPE'):
            config['DAYS_TO_SCRAPE'] = int(os.getenv('DAYS_TO_SCRAPE'))
        if os.getenv('MAX_REVIEWS'):
            config['MAX_REVIEWS'] = int(os.getenv('MAX_REVIEWS'))
    except ValueError as e:
        logger.warning(f"Error parsing numeric config values: {e}")
    
    # Check for required configuration
    if not config['TELEGRAM_TOKEN']:
        logger.error("TELEGRAM_TOKEN is required but not set")
        raise ValueError("TELEGRAM_TOKEN is required")
    
    # Create config.json if it doesn't exist
    if not os.path.exists('config.json'):
        with open('config.json', 'w') as f:
            json.dump(config, f, indent=4)
        logger.info("Created default config.json file")
    
    return config