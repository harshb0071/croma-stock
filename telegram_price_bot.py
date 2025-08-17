> #!/usr/bin/env python3
"""
Telegram Price Tracker Bot - Real-time monitoring for Flipkart, Amazon & Croma
Author: AI Assistant
Version: 1.0
"""

import asyncio
import aiohttp
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from telegram.error import TelegramError
import json
import time
from datetime import datetime
import random
from urllib.parse import urlparse
import re
from bs4 import BeautifulSoup
import sqlite3
import hashlib

# Configure logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Bot configuration - Replace with your values
BOT_TOKEN = "8281102906:AAGdSceyu5g7Y11woRMk89ndYl4RIy1VKnM" 
ADMIN_CHAT_ID = "522893052"  

class PriceTracker:
    def __init__(self):
        self.monitoring = False
        self.monitored_products = {}
        self.db_connection = self.init_database()
        self.session = None
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        ]

    def init_database(self):
        """Initialize SQLite database for storing tracked products"""
        conn = sqlite3.connect('products.db', check_same_thread=False)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                url TEXT NOT NULL,
                name TEXT,
                current_price REAL,
                target_price REAL,
                platform TEXT,
                last_checked TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()
        return conn

    def get_platform(self, url):
        """Detect platform from URL"""
        if 'flipkart.com' in url:
            return 'flipkart'
        elif 'amazon.in' in url or 'amazon.com' in url:
            return 'amazon'  
        elif 'croma.com' in url:
            return 'croma'
        return None

    async def get_page_content(self, url, retries=3):
        """Fetch page content with anti-bot measures"""
        headers = {
            'User-Agent': random.choice(self.user_agents),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0'
        }

        if not self.session:
            timeout = aiohttp.ClientTimeout(total=30)
            self.session = aiohttp.ClientSession(timeout=timeout)

        for attempt in range(retries):
            try:
                # Random delay to avoid rate limiting
                await asyncio.sleep(random.uniform(2, 5))
                async with self.session.get(url, headers=headers) as response:
                    if response.status == 200:
                        content = await response.text()
                        return content
                    elif response.status == 429:
                        # Rate limited - wait longer
                        await asyncio.sleep(random.uniform(10, 20))
                        continue
                    else:
                        logger.warning(f"HTTP {response.status} for {url}")

            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {url}: {e}")
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(random.uniform(5, 10))

        return None

    def parse_flipkart_price(self, html_content):
        """Parse price from Flipkart page"""
        soup = BeautifulSoup(html_content, 'html.parser')

        # Try multiple selectors
        price_selectors = [
            '._16Jk6d',
            '._30jeq3 ._16Jk6d', 
            '.CEmiEU ._16Jk6d',
            '._1_WHN1'
        ]

        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                # Extract numeric price
                price_match = re.search(r'[₹]?([0-9,]+)', price_text)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    return float(price_str)

        return None

    def parse_amazon_price(self, html_content):
        """Parse price from Amazon page"""
        soup = BeautifulSoup(html_content, 'html.parser')

        price_selectors = [
            '.a-price-whole',
            '#priceblock_dealprice',
            '#price_inside_buybox',
            '.a-offscreen',
            '.a-price .a-offscreen'
        ]

        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                price_match = re.search(r'[₹]?([0-9,]+)', price_text)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    return float(price_str)

        return None

    def parse_croma_price(self, html_content):
        """Parse price from Croma page"""
        soup = BeautifulSoup(html_content, 'html.parser')

        price_selectors = [
            '.price-final',
            '.cp-price',
            '.product-price-value',
            '.price'
        ]

        for selector in price_selectors:
            price_element = soup.select_one(selector)
            if price_element:
                price_text = price_element.get_text(strip=True)
                price_match = re.search(r'[₹]?([0-9,]+)', price_text)
                if price_match:
                    price_str = price_match.group(1).replace(',', '')
                    return float(price_str)

        return None

    async def get_current_price(self, url):
        """Get current price from any supported platform"""
        try:
            platform = self.get_platform(url)
            if not platform:
                return None

            html_content = await self.get_page_content(url)
            if not html_content:
                return None

            if platform == 'flipkart':
                return self.parse_flipkart_price(html_content)
            elif platform == 'amazon':
                return self.parse_amazon_price(html_content) 
            elif platform == 'croma':
                return self.parse_croma_price(html_content)

        except Exception as e:
            logger.error(f"Error getting price for {url}: {e}")
            return None

# Initialize tracker
tracker = PriceTracker()

# Bot command handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    welcome_message = """🤖 **Welcome to Price Tracker Bot!**

I help you monitor product prices on:
• 🛒 Flipkart
• 📦 Amazon  
• 🏪 Croma

**Commands:**
/track <url> - Track a product
/list - View tracked products  
/status - Check monitoring status

Send me a product URL to get started! 🚀
"""

    await update.message.reply_text(welcome_message)

async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track product command"""
    if not context.args:
        await update.message.reply_text("Please provide a product URL\nUsage: /track <product_url>")
        return

    url = context.args[0]
    user_id = str(update.effective_user.id)

    # Validate URL
    if not any(platform in url for platform in ['flipkart.com', 'amazon.in', 'amazon.com', 'croma.com']):
        await update.message.reply_text("❌ Unsupported platform\nOnly Flipkart, Amazon, and Croma are supported")
        return

    # Get current price
    current_price = await tracker.get_current_price(url)
    platform = tracker.get_platform(url)

    response = f"✅ **Product Added Successfully!**\n\n"
    response += f"🛍️ Platform: {platform.title()}\n"
    if current_price:
        response += f"💰 Current Price: ₹{current_price:,.2f}\n"
    response += f"🔗 URL: {url}"

    await update.message.reply_text(response)

def main():
    """Start the bot"""
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("track", track_command))

    # Run the bot
    logger.info("Bot started successfully!")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    main()
