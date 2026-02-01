#!/usr/bin/env python3
"""
Run the Music AI Agent Telegram Bot.

This script starts the bot and keeps it running.
For 24/7 operation, deploy to a cloud service or run as a system service.

Usage:
    python run_bot.py

Deployment options:
    1. Local background: nohup python run_bot.py &
    2. Screen/tmux: screen -S musicbot python run_bot.py
    3. Systemd service: See deploy/musicbot.service
    4. Cloud: Deploy to Railway, Render, Heroku, or any VPS
"""

import os
import sys
import logging
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables
from dotenv import load_dotenv
load_dotenv()

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("bot.log"),
    ]
)
logger = logging.getLogger(__name__)


def check_config():
    """Check required configuration."""
    errors = []

    if not os.getenv("TELEGRAM_BOT_TOKEN"):
        errors.append("TELEGRAM_BOT_TOKEN not set")

    # Check for LLM (optional but recommended)
    if not (os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("LLM_API_KEY")):
        logger.warning("No LLM API key found. Bot will use basic fallback responses.")
        logger.warning("Get a free key from https://console.groq.com/keys for better conversations!")

    if errors:
        for error in errors:
            logger.error(f"Configuration error: {error}")
        logger.error("\nPlease set up your .env file. See .env.example for reference.")
        return False

    return True


def main():
    """Start the bot."""
    logger.info("=" * 50)
    logger.info("Music AI Agent - Telegram Bot")
    logger.info("=" * 50)

    if not check_config():
        sys.exit(1)

    logger.info("Starting bot...")

    try:
        from telegram_bot import main as run_bot
        run_bot()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.exception(f"Bot crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
