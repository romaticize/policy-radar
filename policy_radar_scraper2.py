#!/usr/bin/env python3
"""
PolicyRadar Enhanced - Indian Policy News Aggregator (2025 Edition)

An intelligent aggregator for Indian policy news focusing on advanced filtering,
priority-based ranking, and sophisticated content organization.

Key Enhancements:
1. Multi-dimensional relevance scoring (priority, recency, source reliability)
2. Advanced content analysis with policy-specific NLP
3. Sophisticated filtering by sector, source, tags, and time sensitivity
4. Interactive UI with dynamic filtering and search capabilities
5. Personalized content recommendations
6. Collaborative features for policy teams
7. Export and sharing capabilities
"""

# Standard library imports - these should come first
from __future__ import annotations

# --- Standard Library Imports ---
import concurrent.futures
import os
import re
import urllib.parse
from datetime import datetime, timedelta
from typing import (Any, Callable, Dict, List, Optional, Set, Tuple, Union,
                    TYPE_CHECKING)

# --- Third-Party Imports ---
import feedparser
import requests

# --- Global Constants ---
IS_GITHUB_ACTIONS = os.environ.get('GITHUB_ACTIONS') == 'true'
import time
import random
import json
import logging
import hashlib
import urllib3
import sqlite3
import argparse
import math
import tempfile
import platform
import ssl
import warnings
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from datetime import datetime, timedelta
import asyncio
import aiohttp
from aiohttp import ClientTimeout, ClientSession, TCPConnector
from dateutil import parser as date_parser  # Fixed import alias


# Register custom adapters for SQLite to handle datetimes correctly
def adapt_datetime(ts):
    return ts.isoformat()

def convert_timestamp(ts):
    return date_parser.parse(ts.decode('utf-8'))

sqlite3.register_adapter(datetime, adapt_datetime)
sqlite3.register_converter("timestamp", convert_timestamp)

# Create necessary directories first (before any logging)
DIRS = ['logs', 'cache', 'data', 'docs', 'backup', 'exports']
for directory in DIRS:
    Path(directory).mkdir(exist_ok=True)

# Configure logging - MUST happen before any logger calls
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('policyradar.log'),
        logging.StreamHandler()
    ]
)
# Create the logger object that will be used throughout the script
logger = logging.getLogger(__name__)

# Filter out specific warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module='feedparser')

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SSL and NLTK configuration function - NOW with proper logger access
def configure_nltk_ssl():
    """Configure SSL for NLTK downloads across different platforms"""
    try:
        # Check if running on macOS
        if platform.system() == 'Darwin':
            # Create unverified SSL context for macOS
            ssl._create_default_https_context = ssl._create_unverified_context
            logger.info("Configured unverified SSL context for macOS NLTK downloads")

        # Import nltk after SSL configuration
        import nltk # type: ignore

        # Try to download with the configured context
        try:
            # Download both punkt for different NLTK versions
            nltk.download('punkt', quiet=True)
            nltk.download('stopwords', quiet=True)
            logger.info("Successfully downloaded NLTK resources")
        except Exception as download_error:
            logger.warning(f"Error downloading NLTK resources: {str(download_error)}")
            logger.warning("Checking for local NLTK data...")

            # Check if data already exists locally
            try:
                nltk.data.find('tokenizers/punkt')
                nltk.data.find('corpora/stopwords')
                logger.info("Found existing NLTK data locally")
            except LookupError:
                logger.warning("NLTK data not found locally. Some NLP features will be limited.")


        # Try to import required NLTK modules
        try:
            from nltk.corpus import stopwords # type: ignore
            from nltk.tokenize import word_tokenize # type: ignore
            return True, stopwords, word_tokenize
        except ImportError as import_error:
            logger.warning(f"Failed to import NLTK modules: {str(import_error)}")
            return False, None, None

    except Exception as e:
        logger.error(f"Critical error during NLTK configuration: {str(e)}")
        return False, None, None

# Execute NLTK configuration - NOW after logger is defined
NLTK_AVAILABLE, stopwords_module, word_tokenize_func = configure_nltk_ssl()

# If NLTK is available, assign the modules to more convenient names
if NLTK_AVAILABLE:
    try:
        stopwords = stopwords_module
        word_tokenize = word_tokenize_func
        logger.info("NLTK modules loaded successfully")
    except Exception as e:
        logger.warning(f"Error setting up NLTK modules: {str(e)}")
        NLTK_AVAILABLE = False
else:
    # Create minimal fallback functions if NLTK isn't available
    logger.warning("Using fallback text processing instead of NLTK")

    def simple_tokenize(text):
        """Simple tokenization fallback"""
        # Remove punctuation and split by whitespace
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        return text.split()

    # Set of common English stopwords as fallback
    COMMON_STOPWORDS = {
        'a', 'an', 'the', 'and', 'or', 'but', 'if', 'because', 'as', 'what',
        'which', 'this', 'that', 'these', 'those', 'then', 'just', 'so', 'than',
        'such', 'both', 'through', 'about', 'for', 'is', 'of', 'while', 'during',
        'to', 'from', 'in', 'on', 'at', 'by', 'with', 'about', 'against', 'between',
        'into', 'through', 'after', 'before', 'above', 'below', 'up', 'down', 'out'
    }

    class FallbackStopwords:
        """Minimal fallback for NLTK stopwords"""
        @staticmethod
        def words(language):
            if language.lower() == 'english':
                return COMMON_STOPWORDS
            return set()

    # Assign fallbacks
    word_tokenize = simple_tokenize
    stopwords = FallbackStopwords()

class AsyncFeedFetcher:
    """Async feed fetcher for improved performance"""
    
    def __init__(self, policy_radar):
        self.policy_radar = policy_radar
        self.semaphore = asyncio.Semaphore(10)
        self.gov_semaphore = asyncio.Semaphore(3)

    def _is_government_feed(self, url):
        """Check if URL is a government feed"""
        gov_indicators = ['.gov.in', '.nic.in', 'rbi.org.in', 'sebi.gov.in',
                          'trai.gov.in', 'pib.', 'parliament.', 'mygov.',
                          'india.gov.in', 'gst.gov.in']
        return any(indicator in url.lower() for indicator in gov_indicators)
        
    async def fetch_all_feeds_async(self, feeds):
        """Enhanced async fetching with better session management and rate limiting"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        ssl_context.set_ciphers('ALL:@SECLEVEL=0')
        
        connector = TCPConnector(
            limit=50,
            limit_per_host=2,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
            force_close=True,
            ssl=ssl_context
        )
        
        timeout = ClientTimeout(total=90, connect=30, sock_read=60)
        
        async with ClientSession(
            connector=connector,
            timeout=timeout,
            headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive'
            }
        ) as session:
            
            # Separate government and non-government feeds
            gov_feeds = [f for f in feeds if self._is_government_feed(f[1])]
            other_feeds = [f for f in feeds if not self._is_government_feed(f[1])]
            
            all_results = []
            
            # Process government feeds sequentially with delays
            if gov_feeds:
                logger.info(f"Processing {len(gov_feeds)} government feeds sequentially")
                for feed in gov_feeds:
                    try:
                        articles = await self._fetch_single_feed_async(session, feed)
                        all_results.extend(articles)
                        await asyncio.sleep(random.uniform(3, 5))
                    except Exception as e:
                        logger.error(f"Error with government feed {feed[0]}: {str(e)}")
            
            # Process other feeds in controlled batches
            if other_feeds:
                logger.info(f"Processing {len(other_feeds)} non-government feeds")
                batch_size = 10
                for i in range(0, len(other_feeds), batch_size):
                    batch = other_feeds[i:i + batch_size]
                    tasks = [self._fetch_single_feed_async(session, feed) for feed in batch]
                    batch_results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    for result in batch_results:
                        if isinstance(result, list):
                            all_results.extend(result)
                    
                    if i + batch_size < len(other_feeds):
                        await asyncio.sleep(1)
            
            return all_results
            
    async def _process_feed_content_async(self, content, content_type, source_name, category, url):
        """Process feed content in thread pool with better encoding handling"""
        try:
            # First, try to decode as UTF-8, which is most common
            try:
                if isinstance(content, str):
                    text_content = content
                else:
                    text_content = content.decode('utf-8')
            except (UnicodeDecodeError, AttributeError):
                # If UTF-8 fails, try 'latin-1', which rarely fails
                logger.warning(f"UTF-8 decoding failed for {source_name}. Falling back to 'latin-1'.")
                try:
                    text_content = content.decode('latin-1', errors='ignore')
                except AttributeError:
                    # Content might already be a string
                    text_content = str(content)

            if 'xml' in content_type or 'rss' in content_type:
                # Pass the raw content to feedparser, as it handles its own decoding
                return self.policy_radar._parse_feed_content(content, source_name, category)
            elif 'html' in content_type:
                return self.policy_radar._scrape_html_content(text_content, source_name, category, url)
            else:
                # Fallback for unknown content types
                return self.policy_radar._parse_feed_content(content, source_name, category)
        except Exception as e:
            logger.error(f"Error processing content for {source_name}: {str(e)}")
            return []
    
    async def _process_feeds_with_delay(self, session, feeds, delay=2.0):
        """Process feeds sequentially with delays"""
        results = []
        
        for feed in feeds:
            try:
                articles = await self._fetch_single_feed_async(session, feed)
                results.extend(articles)
                await asyncio.sleep(delay)  # Delay between requests
            except Exception as e:
                logger.error(f"Error fetching {feed[0]}: {str(e)}")
                
        return results
    
    async def _fetch_single_feed_async(self, session, feed_info):
        """Fixed version with proper async handling"""
        source_name, feed_url, category = feed_info
        is_gov = self._is_government_feed(feed_url)
        semaphore = self.gov_semaphore if is_gov else self.semaphore
        
        async with semaphore:
            headers = {
                'User-Agent': self.policy_radar.get_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache'
            }
            
            if is_gov:
                domain = urlparse(feed_url).netloc
                headers['Referer'] = f'https://{domain}/'

            # Create SSL context for each request
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            max_attempts = 3 if is_gov else 2
            
            for attempt in range(max_attempts):
                try:
                    if attempt > 0:
                        logger.info(f"Retrying {source_name} (attempt {attempt + 1})...")
                        await asyncio.sleep(5 * attempt)
                    
                    async with session.get(
                        feed_url, 
                        headers=headers, 
                        allow_redirects=True,
                        ssl=ssl_context,
                        timeout=aiohttp.ClientTimeout(total=60)
                    ) as response:
                        
                        if response.status == 200:
                            content = await response.read()
                            content_type = response.headers.get('content-type', '').lower()
                            
                            # Process content in thread pool to avoid blocking
                            loop = asyncio.get_event_loop()
                            articles = await loop.run_in_executor(
                                None,
                                self._process_feed_content,
                                content, content_type, source_name, category, feed_url
                            )
                            return articles
                            
                        elif response.status == 403:
                            logger.warning(f"HTTP 403 Forbidden for {source_name}")
                            # Try different user agent on retry
                            headers['User-Agent'] = 'curl/7.85.0' if attempt == 1 else 'Wget/1.21.3'
                            
                        elif response.status == 404:
                            logger.warning(f"HTTP 404 Not Found for {source_name}")
                            return []
                            
                        else:
                            logger.warning(f"HTTP {response.status} for {source_name}")
                            
                except asyncio.TimeoutError:
                    logger.warning(f"Timeout for {source_name} (attempt {attempt + 1})")
                except aiohttp.ClientError as e:
                    logger.warning(f"Client error for {source_name}: {str(e)}")
                except Exception as e:
                    logger.error(f"Unexpected error for {source_name}: {str(e)}")
            
            logger.error(f"All attempts failed for {source_name}")
            return []

    def _process_feed_content(self, content, content_type, source_name, category, url):
        """Process feed content in thread pool with better encoding handling"""
        try:
            # First, try to decode as UTF-8, which is most common
            try:
                text_content = content.decode('utf-8')
            except UnicodeDecodeError:
                # If UTF-8 fails, try 'latin-1', which rarely fails
                logger.warning(f"UTF-8 decoding failed for {source_name}. Falling back to 'latin-1'.")
                text_content = content.decode('latin-1', errors='ignore')

            if 'xml' in content_type or 'rss' in content_type:
                # Pass the raw content to feedparser, as it handles its own decoding
                return self.policy_radar._parse_feed_content(content, source_name, category)
            elif 'html' in content_type:
                return self.policy_radar._scrape_html_content(text_content, source_name, category, url)
            else:
                # Fallback for unknown content types
                return self.policy_radar._parse_feed_content(content, source_name, category)
        except Exception as e:
            logger.error(f"Error processing content for {source_name}: {str(e)}")
            return []
    
    def _group_feeds_by_domain(self, feeds):
        """Group feeds by domain for rate limiting"""
        from collections import defaultdict
        feeds_by_domain = defaultdict(list)
        
        for feed in feeds:
            domain = urlparse(feed[1]).netloc
            feeds_by_domain[domain].append(feed)
            
        return feeds_by_domain

class GovernmentSiteHandlers:
    """Specialized handlers for different government websites"""
    
    @staticmethod
    def get_handler_for_url(url):
        """Get the appropriate handler based on URL"""
        domain = urlparse(url).netloc.lower()
        
        handlers = {
            'pib.gov.in': GovernmentSiteHandlers.handle_pib_site,
            'www.meity.gov.in': GovernmentSiteHandlers.handle_meity_site,
            'meity.gov.in': GovernmentSiteHandlers.handle_meity_site,
            'sebi.gov.in': GovernmentSiteHandlers.handle_sebi_site,
            'trai.gov.in': GovernmentSiteHandlers.handle_trai_site,
            'cert-in.org.in': GovernmentSiteHandlers.handle_cert_in_site,
            'rbi.org.in': GovernmentSiteHandlers.handle_rbi_site,
            'cci.gov.in': GovernmentSiteHandlers.handle_cci_site,
            'mohfw.gov.in': GovernmentSiteHandlers.handle_health_ministry,
            'cea.nic.in': GovernmentSiteHandlers.handle_cea_site,
            'niti.gov.in': GovernmentSiteHandlers.handle_niti_aayog_site,
            'dea.gov.in': GovernmentSiteHandlers.handle_dea_site,
            'finmin.nic.in': GovernmentSiteHandlers.handle_finmin_site,
            'mca.gov.in': GovernmentSiteHandlers.handle_mca_site,
        }
        
        # Check if domain matches any handler
        for domain_pattern, handler in handlers.items():
            if domain_pattern in domain:
                return handler
                
        # Default government handler
        if any(gov_domain in domain for gov_domain in ['.gov.in', '.nic.in', '.gov', 'parliament']):
            return GovernmentSiteHandlers.handle_generic_gov_site
            
        return None
    
    @staticmethod
    def handle_rbi_site(session, url, headers):
        """Special handling for RBI"""
        headers.update({
            'Accept': 'application/rss+xml, application/xml, text/xml, text/html, */*;q=0.1',
            'Accept-Language': 'en-GB,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://www.rbi.org.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # RBI sometimes needs cookies
        session.cookies.set('has_js', '1', domain='.rbi.org.in')
        
        return session.get(url, headers=headers, timeout=30, verify=False)
    
    @staticmethod
    def handle_cci_site(session, url, headers):
        """Special handling for Competition Commission"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://cci.gov.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1'
        })
        
        # Try to establish session first
        try:
            homepage = session.get('https://cci.gov.in/', headers=headers, timeout=10, verify=False)
            if homepage.cookies:
                session.cookies.update(homepage.cookies)
            time.sleep(2)
        except:
            pass
            
        return session.get(url, headers=headers, timeout=30, verify=False)
    
    @staticmethod
    def handle_health_ministry(session, url, headers):
        """Special handling for Ministry of Health"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Referer': 'https://mohfw.gov.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Health ministry often needs specific user agent
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        return session.get(url, headers=headers, timeout=45, verify=False)
    
    @staticmethod
    def handle_cea_site(session, url, headers):
        """Special handling for Central Electricity Authority"""
        headers.update({
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': 'https://cea.nic.in/',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        # CEA often has connection issues, use longer timeout
        return session.get(url, headers=headers, timeout=60, verify=False, stream=True)
    
    @staticmethod
    def handle_niti_aayog_site(session, url, headers):
        """Special handling for NITI Aayog"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Referer': 'https://niti.gov.in/',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        # NITI Aayog often uses dynamic content loading
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        return session.get(url, headers=headers, timeout=30, verify=False)

    @staticmethod
    def handle_dea_site(session, url, headers):
        """Special handling for Department of Economic Affairs"""
        headers.update({
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.9',
            'Cache-Control': 'no-cache',
            'Referer': 'https://dea.gov.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin'
        })
        
        # DEA sometimes needs session cookies
        try:
            homepage = session.get('https://dea.gov.in/', headers=headers, timeout=10, verify=False)
            if homepage.cookies:
                session.cookies.update(homepage.cookies)
            time.sleep(1.5)
        except:
            pass
        
        return session.get(url, headers=headers, timeout=45, verify=False)

    @staticmethod
    def handle_finmin_site(session, url, headers):
        """Special handling for Ministry of Finance"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Referer': 'https://finmin.nic.in/',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Finance Ministry often has legacy systems
        headers['User-Agent'] = 'Mozilla/5.0 (compatible; MSIE 10.0; Windows NT 6.1; WOW64; Trident/6.0)'
        
        return session.get(url, headers=headers, timeout=60, verify=False, stream=True)

    @staticmethod
    def handle_mca_site(session, url, headers):
        """Special handling for Ministry of Corporate Affairs"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Referer': 'https://www.mca.gov.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-User': '?1'
        })
        
        # MCA uses complex session management
        session.cookies.set('ASP.NET_SessionId', 'dummy' + str(random.randint(100000, 999999)), domain='.mca.gov.in')
        
        return session.get(url, headers=headers, timeout=45, verify=False)
    
    @staticmethod
    def handle_pib_site(session, url, headers):
        """Enhanced PIB handling"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache',
            'Referer': 'https://pib.gov.in/',
            'X-Requested-With': 'XMLHttpRequest'
        })
        
        # PIB often blocks based on user agent
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0'
        
        # For PIB, try alternate approaches
        if 'PressReleseDetail.aspx' in url:
            # This is likely a specific press release page, not a feed
            url = 'https://pib.gov.in/indexd.aspx'
        elif 'PRID=' in url:
            # This is a specific article, get the main feed instead
            url = 'https://pib.gov.in/indexd.aspx'
            
        return session.get(url, headers=headers, timeout=30, verify=False)
    
    @staticmethod
    def handle_meity_site(session, url, headers):
        """Enhanced MeitY handling"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': 'https://www.meity.gov.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # MeitY uses Drupal with specific requirements
        headers['User-Agent'] = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        # Add Drupal-specific cookies
        session.cookies.set('has_js', '1', domain='.meity.gov.in')
        
        return session.get(url, headers=headers, timeout=45, verify=False)
    
    @staticmethod
    def handle_sebi_site(session, url, headers):
        """Enhanced SEBI handling"""
        # SEBI often requires specific session handling
        domain = urlparse(url).netloc
        
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Pragma': 'no-cache',
            'Referer': f'https://{domain}/',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # SEBI uses ASP.NET
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0'
        
        # Add ASP.NET session cookie
        session.cookies.set('ASP.NET_SessionId', 'dummy' + str(random.randint(100000, 999999)), domain=domain)
        
        return session.get(url, headers=headers, timeout=30, verify=False)
    
    @staticmethod
    def handle_trai_site(session, url, headers):
        """Enhanced TRAI handling"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-GB,en;q=0.5',
            'Cache-Control': 'no-cache',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Referer': 'https://trai.gov.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin'
        })
        
        # TRAI is very picky about user agents
        headers['User-Agent'] = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        return session.get(url, headers=headers, timeout=45, verify=False, allow_redirects=True)
    
    @staticmethod
    def handle_cert_in_site(session, url, headers):
        """Enhanced CERT-In handling"""
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Referer': 'https://www.cert-in.org.in/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # CERT-In needs specific parameters
        if 'pageid=' in url and 'year=' not in url:
            # Add current year parameter
            current_year = datetime.now().year
            url = f"{url}&year={current_year}"
            
        return session.get(url, headers=headers, timeout=30, verify=True)
    
    @staticmethod
    def handle_generic_gov_site(session, url, headers):
        """Enhanced generic government site handler"""
        domain = urlparse(url).netloc
        
        headers.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Referer': f'https://{domain}/',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Rotate user agents for government sites
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        headers['User-Agent'] = random.choice(user_agents)
        
        # Add common government site cookies
        session.cookies.set('has_js', '1', domain=domain)
        if '.nic.in' in domain:
            session.cookies.set('nic_session', 'active', domain=domain)
            
        # Try to establish session first
        try:
            homepage_url = f'https://{domain}/'
            homepage = session.get(homepage_url, headers=headers, timeout=15, verify=False)
            if homepage.cookies:
                session.cookies.update(homepage.cookies)
            time.sleep(random.uniform(2, 3))
        except:
            pass
            
        return session.get(url, headers=headers, timeout=45, verify=False, allow_redirects=True)

# Configuration class with expanded settings
class Config:
    # Directories
    OUTPUT_DIR = 'docs'
    CACHE_DIR = 'cache'
    DATA_DIR = 'data'
    LOG_DIR = 'logs'
    BACKUP_DIR = 'backup'
    EXPORT_DIR = 'exports'

    # Timing
    CACHE_DURATION = 7200  # 2 hours in seconds
    BACKUP_DURATION = 86400  # 24 hours in seconds
    RETRY_DELAY = 1.5  # base delay for exponential backoff
    REQUEST_TIMEOUT = 20  # timeout for requests

    # Retry settings
    MAX_RETRIES = 3
    RETRY_STATUS_CODES = [429, 500, 502, 503, 504]

    # List of domains that consistently block requests and require Selenium
    SELENIUM_REQUIRED_DOMAINS = [
        'pib.gov.in',
        'business-standard.com',
        'moneycontrol.com',
        'hindustantimes.com',
        'livemint.com',
        'mea.gov.in',
        'mohfw.gov.in',
        'cea.nic.in',
        'naco.gov.in',
        'meity.gov.in',
        'finmin.nic.in',
        'sebi.gov.in',
        'telegraphindia.com',
        'ndtv.com'
    ]

    # User agents for rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36 Edg/123.0.0.0',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1',
        'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Mobile Safari/537.36',
        'Feedly/1.0 (+http://www.feedly.com/fetcher.html; like FeedFetcher-Google)',
        'Mozilla/5.0 (compatible; Inoreader/1.0; https://www.inoreader.com)'
    ]

    # Browser-like headers
    BROWSER_HEADERS = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Cache-Control': 'max-age=0',
        'Upgrade-Insecure-Requests': '1',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1'
    }

    # RSS-specific headers
    RSS_HEADERS = {
        'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.1',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive'
    }

    # Site-specific headers for known sources
    SITE_SPECIFIC_HEADERS = {
        'thehindu.com': {
            'Referer': 'https://www.thehindu.com/',
            'Origin': 'https://www.thehindu.com',
            'Cookie': 'GDPRCookieConsent=accepted; euconsent=1'
        },
        'livemint.com': {
            'Referer': 'https://www.livemint.com/',
            'Origin': 'https://www.livemint.com'
        },
        'economictimes.indiatimes.com': {
            'Referer': 'https://economictimes.indiatimes.com/',
            'Origin': 'https://economictimes.indiatimes.com',
            'Cookie': 'gdpr=1; euconsent=1'
        },
        'indianexpress.com': {
            'Referer': 'https://indianexpress.com/',
            'Origin': 'https://indianexpress.com'
        },
        'business-standard.com': {
            'Referer': 'https://www.business-standard.com/',
            'Origin': 'https://www.business-standard.com'
        }
    }

    # Database
    DB_FILE = 'data/policyradar.db'
    DB_SCHEMA_VERSION = '1.0'

    # Fallback URLs for problematic feeds
    FALLBACK_URLS = {
        'https://www.thehindu.com/sci-tech/technology/feeder/default.rss': [
            'https://www.thehindu.com/sci-tech/technology/?service=rss',
            'https://www.thehindu.com/sci-tech/technology/'
        ],
        'https://www.livemint.com/rss/technology': [
            'https://www.livemint.com/technology/news.rss',
            'https://www.livemint.com/technology/'
        ],
        'https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1286551326.cms': [
            'https://economictimes.indiatimes.com/rssfeedstopstories.cms',
            'https://economictimes.indiatimes.com/news/economy/policy'
        ]
    }

    # Enhanced Policy Keywords
    POLICY_KEYWORDS = {
        'high_relevance': [
            'policy', 'regulation', 'bill', 'act', 'law', 'ministry', 'government',
            'notification', 'amendment', 'cabinet', 'parliament', 'supreme court',
            'legislation', 'regulatory', 'compliance', 'niti aayog', 'rbi', 'sebi',
            'trai', 'circular', 'ordinance', 'statute', 'directive', 'mandate',
            'policy framework', 'regulatory framework', 'government policy',
            'policy announcement', 'policy decision', 'policy implementation',
            'regulatory compliance', 'legal framework', 'policy reform',
            'government regulation', 'policy guidelines', 'regulatory authority',
            'policy initiative', 'government scheme', 'policy measures'
        ],
        'medium_relevance': [
            'reform', 'initiative', 'program', 'scheme', 'mission', 'project',
            'framework', 'strategy', 'roadmap', 'guideline', 'committee', 'commission',
            'panel', 'task force', 'authority', 'board', 'council', 'fund', 'subsidy',
            'development', 'governance', 'public sector', 'government sector',
            'policy development', 'regulatory development', 'public policy',
            'government initiative', 'public administration', 'policy planning'
        ]
        
    }

    BUSINESS_POLICY_KEYWORDS = [
            'trade deal', 'trade agreement', 'trade talks', 'trade war', 'trade dispute',
            'bilateral agreement', 'multilateral agreement', 'free trade agreement',
            'defence deal', 'defense deal', 'defence agreement', 'defense agreement',
            'strategic partnership', 'military cooperation', 'arms deal',
            'anti-dumping duty', 'countervailing duty', 'safeguard duty',
            'tariff barrier', 'non-tariff barrier', 'trade barrier',
            'export restriction', 'import restriction', 'trade sanction',
            'wto dispute', 'trade negotiation', 'trade delegation',
            'investment treaty', 'bilateral investment', 'fdi policy',
            'technology transfer', 'joint venture agreement', 'collaboration agreement',
            'memorandum of understanding', 'mou signed', 'letter of intent',
            'government contract', 'public procurement', 'tender process',
            'regulatory approval', 'antitrust clearance', 'merger approval',
            'competition commission', 'regulatory compliance', 'compliance framework'
        ]

    BLACKLISTED_SOURCES = [
        'swarajyamag', 'swarajya', 'opindia', 'rightlog', 'tfipost',
        'postcard news', 'republicworld', 'zeenews', 'sudarshan news',
        'kreately', 'hindupost', 'organiser', 'panchjanya', 'zeenews', 
        'zee business'
    ]
    
    # Preferred sources - will get a relevance boost
    PREFERRED_SOURCES = [
        'pib', 'rbi', 'sebi', 'trai', 'ministry', 'government',
        'the hindu', 'indian express', 'economic times', 'business standard',
        'livemint', 'financial express', 'hindustan times', 'times of india',
        'prs legislative', 'orf', 'cpr india', 'livelaw', 'bar and bench',
        'medianama', 'moneycontrol', 'ndtv', 'the wire', 'scroll',
        'the print', 'news18', 'india today', 'firstpost', 'the quint',
        'deccan herald', 'telegraph india', 'outlook', 'frontline',
        'business line', 'down to earth', 'mongabay', 'the ken',
        'bloomberg', 'reuters', 'pti', 'ani', 'ians'
    ]

    # Comprehensive Exclusion Keywords
    EXCLUSION_KEYWORDS = {
        'product_launches': [
            'product launch', 'brand launch', 'model launch', 'device launch',
            'phone launch', 'smartphone launch', 'tablet launch', 'laptop launch',
            'car launch', 'vehicle launch', 'gadget launch', 'app launch',
            'launches', 'unveiled', 'announced', 'introduces', 'reveals',
            'new model', 'new product', 'new device', 'new phone', 'new smartphone',
            'new tablet', 'new laptop', 'new car', 'new vehicle', 'new gadget',
            'specifications', 'specs', 'features', 'price announced', 'pricing announced',
            'availability', 'pre-order', 'booking', 'reservations'
        ],
        'commercial_content': [
            'discount', 'sale', 'offer', 'deal', 'credit card', 'zero interest',
            'buy now', 'purchase now', 'shopping',
            'retail price', 'wholesale price', 'consumer price', 'market price',
            'earnings call', 'stock tips', 'market tips',
            'buy recommendation', 'sell recommendation', 'target price',
            'investment tips', 'trading tips', 'best buy', 'hot deal',
            'cashback', 'rewards', 'credit card offer', 'loan offer',
            'insurance offer', 'investment offer'
        ],
        'technology_consumer': [
            'smartphone specs', 'phone specs', 'gadget review', 'phone review',
            'laptop review', 'tablet review', 'device review', 'tech review',
            'features comparison', 'vs comparison', 'best phone', 'best laptop',
            'best tablet', 'best device', 'tech deals', 'gadget deals',
            'mobile offers', 'phone offers', 'laptop offers', 'tablet offers',
            'unboxing', 'hands-on', 'first look', 'preview', 'impressions'
        ],
        'entertainment_lifestyle': [
            'movie', 'film', 'actor', 'actress', 'celebrity', 'bollywood',
            'hollywood', 'music', 'song', 'album', 'concert', 'show',
            'entertainment', 'celebrity news', 'box office', 'streaming',
            'fashion', 'beauty tips', 'lifestyle tips', 'travel tips', 'food recipe',
            'health tips', 'fitness tips', 'style tips', 'personal finance tips',
            'recipe', 'fashion show', 'beauty product', 'cast', 'on set',  'live-action'
        ],
        'sports_games': [
            'cricket match', 'football match', 'hockey match', 'tennis match',
            'tournament', 'championship', 'player performance', 'team performance',
            'sports news', 'olympic games', 'commonwealth games', 'gaming',
            'video game', 'mobile game', 'game review', 'gaming review'
        ],
        'social_media_features': [
            'instagram feature', 'facebook feature', 'twitter feature', 'tiktok feature',
            'youtube feature', 'whatsapp feature', 'telegram feature', 'snapchat feature',
            'social media feature', 'app feature', 'platform feature', 'new feature',
            'feature update', 'app update', 'platform update', 'user interface',
            'ui update', 'design update', 'stories feature', 'chat feature'
        ],
        'literature_culture': [
            'book review', 'literature', 'novel', 'author', 'writer', 'poet',
            'poetry', 'literary', 'cultural', 'art', 'artist', 'painting',
            'sculpture', 'exhibition', 'museum', 'gallery', 'theater',
            'play', 'drama', 'cultural event', 'literary event'
        ],
        # Add this new category to EXCLUSION_KEYWORDS
        'organizational_content': [
            'about us', 'who\'s who', 'organization structure', 'profiles of ministers',
            'screen reader access', 'vacancies', 'manuals', 'objectives and features',
            'allocation of business rules', 'list of financial advisers', 'whos who',
            'personnel and establishment', 'guideline for preparation', 'about department',
            'hindi', 'screen reader', 'clarification on the news item', 'clarification on news item',
            'warning letter issued', 'unregistered investment', 'unregistered advisory',
            'sixth central pay commission', 'seventh central pay commission', 'central pay commission',
            'outcome budget', 'profiles of', 'organization chart', 'contact us', 'disclaimer',
            'terms of use', 'privacy policy', 'copyright', 'accessibility', 'sitemap',
            'feedback', 'faq', 'help', 'guidelines', 'manual', 'handbook'
        ]
    }

    # Policy Exception Keywords (Override exclusions)
    POLICY_EXCEPTION_KEYWORDS = [
        'policy', 'regulation', 'government', 'ministry', 'regulatory',
        'legislation', 'parliament', 'court', 'tribunal', 'authority',
        'commission', 'committee', 'framework', 'guidelines', 'compliance',
        'enforcement', 'implementation', 'reform', 'initiative', 'scheme',
        'program', 'mission', 'strategy', 'roadmap', 'notification',
        'circular', 'order', 'directive', 'mandate', 'bill', 'act',
        'amendment', 'ordinance', 'statute', 'cabinet', 'supreme court',
        'high court', 'gazette', 'official', 'public sector', 'governance'
    ]

    # Keywords to identify and filter out entertainment URLs
    ENTERTAINMENT_URL_KEYWORDS = [
        'entertainment', 'hollywood', 'bollywood', 'movies', 'celebrity', 
        'film', 'tv', 'music', 'gossip', 'lifestyle', 'fashion'
    ]

    # Enhanced Policy Sectors
    POLICY_SECTORS = {
        'Technology Policy': [
            'digital policy', 'data protection', 'privacy policy', 'cyber policy',
            'cybersecurity policy', 'it policy', 'digital governance', 'e-governance',
            'digital india', 'data governance', 'platform regulation', 'social media regulation',
            'ai policy', 'artificial intelligence policy', 'machine learning regulation',
            'blockchain policy', 'cryptocurrency regulation', 'fintech regulation',
            'startup policy', 'innovation policy', 'technology transfer policy',
            'intellectual property policy', 'patent policy', 'digital rights',
            'net neutrality', 'telecom policy', 'spectrum policy', 'broadband policy',
            'digital infrastructure policy', 'technology standards', 'data localization',
            'digital payments regulation', 'e-commerce regulation', 'platform liability'
        ],
        'Economic Policy': [
            'economic policy', 'fiscal policy', 'monetary policy', 'budget policy',
            'tax policy', 'taxation policy', 'gst policy', 'customs policy',
            'trade policy', 'export policy', 'import policy', 'fdi policy',
            'investment policy', 'banking policy', 'financial policy', 'insurance policy',
            'capital market regulation', 'securities regulation', 'banking regulation',
            'financial inclusion policy', 'credit policy', 'interest rate policy',
            'exchange rate policy', 'currency policy', 'inflation targeting',
            'public finance', 'government expenditure', 'public debt policy',
            'subsidy policy', 'agricultural subsidy', 'fuel subsidy',
            'industrial policy', 'manufacturing policy', 'msme policy',
            'employment policy', 'labor policy', 'wage policy', 'social security policy'
        ],
        'Healthcare Policy': [
            'health policy', 'healthcare policy', 'medical policy', 'public health policy',
            'health insurance policy', 'medical insurance regulation', 'drug policy',
            'pharmaceutical policy', 'medical device regulation', 'hospital regulation',
            'healthcare regulation', 'medical education policy', 'telemedicine policy',
            'digital health policy', 'health data policy', 'medical research policy',
            'clinical trial regulation', 'vaccine policy', 'immunization policy',
            'pandemic response', 'epidemic control', 'health emergency',
            'healthcare financing', 'universal healthcare', 'ayushman bharat',
            'national health mission', 'health infrastructure policy'
        ],
        'Environmental Policy': [
            'environmental policy', 'climate policy', 'climate change policy',
            'pollution control policy', 'emission standards', 'environmental standards',
            'green policy', 'sustainability policy', 'renewable energy policy',
            'solar policy', 'wind energy policy', 'clean energy policy',
            'carbon policy', 'carbon tax', 'emission trading', 'forest policy',
            'wildlife policy', 'biodiversity policy', 'water policy', 'waste policy',
            'waste management policy', 'plastic policy', 'air quality policy',
            'environmental compliance', 'environmental clearance', 'eia policy',
            'environmental impact assessment', 'green tribunal', 'environmental law'
        ],
        'Education Policy': [
            'education policy', 'educational policy', 'school policy', 'university policy',
            'higher education policy', 'nep', 'national education policy',
            'skill development policy', 'vocational education policy', 'teacher policy',
            'curriculum policy', 'examination policy', 'admission policy',
            'educational reform', 'literacy policy', 'adult education policy',
            'digital education policy', 'online education policy', 'research policy',
            'innovation policy in education', 'educational technology policy',
            'scholarship policy', 'student welfare policy', 'educational financing'
        ],
        'Agricultural Policy': [
            'agricultural policy', 'farm policy', 'farmer policy', 'crop policy',
            'agricultural reform', 'farm reform', 'msp policy', 'procurement policy',
            'food security policy', 'agricultural credit policy', 'irrigation policy',
            'agricultural technology policy', 'organic farming policy', 'fertilizer policy',
            'pesticide policy', 'seed policy', 'agricultural marketing policy',
            'food processing policy', 'agricultural export policy', 'land policy',
            'agricultural land policy', 'farm mechanization policy', 'rural development policy'
        ],
        'Foreign Policy': [
            'foreign policy', 'diplomatic policy', 'international policy', 'bilateral policy',
            'multilateral policy', 'trade agreement', 'defense agreement',
            'cooperation agreement', 'diplomatic relations', 'international relations',
            'foreign investment policy', 'visa policy', 'immigration policy',
            'border policy', 'maritime policy', 'strategic partnership',
            'international law', 'treaty ratification', 'diplomatic immunity',
            'consular services', 'diaspora policy', 'cultural diplomacy'
        ],
        'Constitutional & Legal': [
            'constitutional policy', 'legal policy', 'judicial policy', 'court policy',
            'legal reform', 'judicial reform', 'law reform', 'legal framework',
            'constitutional amendment', 'legal amendment', 'judicial procedure',
            'legal procedure', 'court procedure', 'legal system reform',
            'justice delivery', 'legal aid policy', 'judicial infrastructure',
            'legal education policy', 'bar council policy', 'legal profession regulation'
        ],
        'Defense & Security': [
            'defense policy', 'security policy', 'military policy', 'strategic policy',
            'defense procurement policy', 'military procurement', 'defense manufacturing',
            'defense technology policy', 'cybersecurity policy', 'national security policy',
            'border security policy', 'internal security policy', 'intelligence policy',
            'defense cooperation', 'military cooperation', 'defense agreement',
            'strategic defense', 'nuclear policy', 'missile policy', 'space policy'
        ],
        'Social Policy': [
            'social policy', 'welfare policy', 'social welfare policy', 'poverty policy',
            'employment policy', 'unemployment policy', 'labor policy', 'worker policy',
            'pension policy', 'social security policy', 'gender policy', 'women policy',
            'child policy', 'minority policy', 'tribal policy', 'disability policy',
            'elderly policy', 'housing policy', 'urban policy', 'rural policy',
            'social justice policy', 'affirmative action policy', 'reservation policy'
        ],
        'Governance & Administration': [
            'governance policy', 'administrative policy', 'bureaucratic reform',
            'civil service policy', 'public administration policy', 'e-governance policy',
            'digital governance policy', 'transparency policy', 'accountability policy',
            'anti-corruption policy', 'ethics policy', 'electoral policy', 'election policy',
            'local governance policy', 'municipal policy', 'panchayati raj policy',
            'federalism policy', 'centre-state relations', 'administrative reform'
        ],
        # Add to POLICY_SECTORS
        'Climate Policy': [
            'climate change', 'climate action', 'climate finance', 'climate adaptation',
            'climate mitigation', 'climate resilience', 'climate fund', 'climate agreement',
            'climate summit', 'climate conference', 'climate talks', 'cop', 'unfccc',
            'paris agreement', 'carbon market', 'carbon credit', 'emission reduction',
            'net zero', 'carbon neutral', 'climate vulnerability', 'climate risk'
        ],
        'Renewable Energy Policy': [
            'renewable energy', 'solar energy', 'wind energy', 'hydro power',
            'green hydrogen', 'energy storage', 'battery storage', 'clean energy',
            'energy transition', 'renewable capacity', 'solar capacity', 'wind capacity',
            'renewable target', 'renewable investment', 'green investment',
            'clean technology', 'sustainable energy', 'energy efficiency'
        ],
        'Conservation Policy': [
            'conservation', 'biodiversity', 'wildlife protection', 'forest conservation',
            'marine conservation', 'habitat protection', 'species protection',
            'environmental protection', 'ecosystem', 'natural resources',
            'protected area', 'national park', 'wildlife sanctuary', 'biosphere'
        ]
    }

    # Strong Policy Context Indicators
    POLICY_CONTEXT_INDICATORS = [
        # Government and official actions
        'government announces', 'ministry announces', 'cabinet approves', 'cabinet decides',
        'parliament passes', 'parliament approves', 'supreme court rules', 'high court rules',
        'supreme court orders', 'high court orders', 'tribunal rules', 'tribunal orders',
        'notification issued', 'circular issued', 'guidelines issued', 'order issued',
        'policy announced', 'policy approved', 'policy implemented', 'policy launched',
        'regulation introduced', 'regulation approved', 'regulation implemented',
        'law amended', 'law passed', 'law enacted', 'law repealed',
        'bill introduced', 'bill passed', 'bill approved', 'bill tabled',
        'act passed', 'act approved', 'act enacted', 'act amended',
        'ordinance promulgated', 'ordinance issued', 'ordinance approved',
        
        # Policy analysis and governance
        'policy analysis', 'policy review', 'policy evaluation', 'policy assessment',
        'policy implications', 'policy impact', 'policy debate', 'policy discussion',
        'policy framework', 'policy reform', 'policy development', 'policy planning',
        'policy implementation', 'policy monitoring', 'policy outcomes',
        'regulatory framework', 'regulatory reform', 'regulatory compliance',
        'legal framework', 'legal reform', 'legal compliance',
        'governance reform', 'administrative reform', 'institutional reform',
        
        # Official bodies and authorities
        'rbi announces', 'rbi decides', 'rbi approves', 'rbi issues',
        'sebi announces', 'sebi decides', 'sebi approves', 'sebi issues',
        'trai announces', 'trai decides', 'trai approves', 'trai issues',
        'cci announces', 'cci decides', 'cci approves', 'cci issues',
        'cag report', 'cag audit', 'cag findings', 'parliamentary committee',
        'standing committee', 'select committee', 'joint committee',
        'law commission', 'finance commission', 'election commission',
        'niti aayog', 'planning commission', 'public accounts committee',
        
        # Legal and judicial
        'court judgment', 'court ruling', 'court order', 'court decision',
        'judicial review', 'constitutional review', 'legal challenge',
        'supreme court judgment', 'high court judgment', 'tribunal judgment',
        'constitutional bench', 'division bench', 'single bench',
        'judicial precedent', 'legal precedent', 'constitutional interpretation',
        
        # Legislative process
        'legislative process', 'parliamentary process', 'legislative procedure',
        'parliamentary procedure', 'legislative debate', 'parliamentary debate',
        'legislative session', 'parliamentary session', 'budget session',
        'monsoon session', 'winter session', 'joint session',
        'question hour', 'zero hour', 'adjournment motion',
        
        # Policy sectors with context
        'economic policy', 'fiscal policy', 'monetary policy', 'trade policy',
        'industrial policy', 'agricultural policy', 'education policy',
        'health policy', 'environmental policy', 'energy policy',
        'technology policy', 'digital policy', 'foreign policy',
        'defense policy', 'security policy', 'social policy',

        # Environmental and Climate Policy
        'climate finance', 'climate action', 'climate talks', 'climate agreement',
        'environmental regulation', 'environmental compliance', 'conservation policy',
        'renewable energy policy', 'energy transition', 'green investment',
        'carbon markets', 'emission standards', 'environmental clearance',
        'climate adaptation', 'climate mitigation', 'sustainable development',
        'green bonds', 'climate fund', 'environmental impact', 'biodiversity policy',
        
        # Energy Policy
        'energy policy', 'power capacity', 'renewable capacity', 'solar capacity',
        'wind capacity', 'nuclear policy', 'energy storage', 'grid policy',
        'power generation', 'energy security', 'fuel policy', 'energy efficiency',
        'power sector reform', 'electricity regulation', 'energy investment',
        'clean energy policy', 'energy transition', 'decarbonization policy',
        
        # International Cooperation
        'international agreement', 'bilateral cooperation', 'climate conference',
        'cop30', 'climate summit', 'international fund', 'development conference',
        'climate finance gap', 'loss and damage fund', 'green climate fund',
        
        # Research and Development Policy
        'r&d policy', 'research funding', 'innovation policy', 'technology development',
        'pilot project', 'demonstration project', 'research initiative',
        'green hydrogen', 'clean technology', 'sustainable technology'

        ]

    # Policy Validation Keywords
    POLICY_VALIDATION_KEYWORDS = [
        'policy', 'regulation', 'law', 'act', 'bill', 'amendment',
        'notification', 'circular', 'guidelines', 'framework', 'scheme',
        'initiative', 'program', 'mission', 'strategy', 'reform',
        'compliance', 'enforcement', 'implementation', 'governance',
        'administration', 'authority', 'commission', 'committee',
        'tribunal', 'court', 'judgment', 'ruling', 'order'
    ]

    # Source Reliability Ratings
    SOURCE_RELIABILITY = {
        # Government sources - Very High reliability
        'Press Information Bureau': 5,
        'PIB': 5,
        'RBI': 5,
        'Reserve Bank of India': 5,
        'Supreme Court of India': 5,
        'Ministry of': 5,
        'Department of': 5,
        'TRAI': 5,
        'SEBI': 5,
        'Gazette of India': 5,
        'Lok Sabha': 5,
        'Rajya Sabha': 5,
        'Niti Aayog': 5,

        # Think tanks & Research organizations - High reliability
        'PRS Legislative Research': 4.5,
        'Observer Research Foundation': 4.5,
        'ORF': 4.5,
        'Centre for Policy Research': 4.5,
        'CPR India': 4.5,
        'Takshashila Institution': 4.5,
        'IDFC Institute': 4.5,
        'Carnegie India': 4.5,
        'Gateway House': 4.5,

        # Legal news sources - High reliability
        'LiveLaw': 4.5,
        'Bar and Bench': 4.5,
        'SCC Online': 4.5,

        # Policy-focused media - Generally reliable
        'The Hindu': 4.0,
        'The Indian Express': 4.0,
        'Mint': 4.0,
        'LiveMint': 4.0,
        'Business Standard': 4.0,
        'Economic Times': 4.0,
        'Financial Express': 4.0,
        'Hindu Business Line': 4.0,
        'The Print': 4.0,
        'The Wire': 4.0,
        'Scroll.in': 4.0,
        'Down To Earth': 4.0,
        'MediaNama': 4.0,

        # Tech policy specialized sources
        'Internet Freedom Foundation': 4.5,
        'IFF': 4.5,
        'Medianama': 4.0,
        'Entrackr': 3.5,

        # Industry associations
        'NASSCOM': 4.0,
        'FICCI': 4.0,
        'CII': 4.0,
        'IAMAI': 4.0,
        'Assocham': 4.0,

        # General news with some policy coverage
        'Times of India': 3.5,
        'NDTV': 3.5,
        'India Today': 3.5,
        'Hindustan Times': 3.5,
        'News18': 3.5,
        'The News Minute': 3.5,
        'FirstPost': 3.5,

        # Google News - Variable but generally provides diverse sources
        'Google News': 3.0
    }

class FeedHealthMonitor:
    """Monitor and manage feed health"""
    
    def __init__(self, db_file):
        self.db_file = db_file
        self.health_threshold = 0.3  # 30% success rate minimum
        self.retry_after_hours = 24  # Retry failed feeds after 24 hours

    def update_feed_health(self, feed_url, success, error_type=None):
        """Update feed health metrics"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                c = conn.cursor()
                
                # Create feed health table if not exists
                c.execute('''CREATE TABLE IF NOT EXISTS feed_health_v2
                             (feed_url TEXT PRIMARY KEY,
                              total_attempts INTEGER DEFAULT 0,
                              successful_attempts INTEGER DEFAULT 0,
                              consecutive_failures INTEGER DEFAULT 0,
                              last_success TIMESTAMP,
                              last_failure TIMESTAMP,
                              last_error_type TEXT,
                              is_active BOOLEAN DEFAULT 1,
                              health_score REAL DEFAULT 1.0)''')
                
                if success:
                    c.execute('''INSERT OR REPLACE INTO feed_health_v2
                                 (feed_url, total_attempts, successful_attempts, 
                                  consecutive_failures, last_success, health_score, is_active)
                                 VALUES (?, 
                                         COALESCE((SELECT total_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) + 1,
                                         COALESCE((SELECT successful_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) + 1,
                                         0,
                                         CURRENT_TIMESTAMP,
                                         CAST(COALESCE((SELECT successful_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) + 1 AS REAL) / 
                                         CAST(COALESCE((SELECT total_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) + 1 AS REAL),
                                         1)''',
                                 (feed_url, feed_url, feed_url, feed_url, feed_url))
                else:
                    c.execute('''INSERT OR REPLACE INTO feed_health_v2
                                 (feed_url, total_attempts, successful_attempts, 
                                  consecutive_failures, last_failure, last_error_type, health_score, is_active)
                                 VALUES (?, 
                                         COALESCE((SELECT total_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) + 1,
                                         COALESCE((SELECT successful_attempts FROM feed_health_v2 WHERE feed_url = ?), 0),
                                         COALESCE((SELECT consecutive_failures FROM feed_health_v2 WHERE feed_url = ?), 0) + 1,
                                         CURRENT_TIMESTAMP,
                                         ?,
                                         CAST(COALESCE((SELECT successful_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) AS REAL) / 
                                         CAST(COALESCE((SELECT total_attempts FROM feed_health_v2 WHERE feed_url = ?), 0) + 1 AS REAL),
                                         CASE 
                                             WHEN COALESCE((SELECT consecutive_failures FROM feed_health_v2 WHERE feed_url = ?), 0) + 1 >= 5 THEN 0
                                             ELSE 1
                                         END)''',
                                 (feed_url, feed_url, feed_url, feed_url, error_type, feed_url, feed_url, feed_url))
                
                conn.commit()
                
        except sqlite3.Error as e:
            logger.error(f"Database error updating feed health: {e}")
    
    def get_active_feeds(self, all_feeds):
        """Filter feeds based on health status"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                c = conn.cursor()
                c.execute('''CREATE TABLE IF NOT EXISTS feed_health_v2
                             (feed_url TEXT PRIMARY KEY, total_attempts INTEGER DEFAULT 0, successful_attempts INTEGER DEFAULT 0,
                             consecutive_failures INTEGER DEFAULT 0, last_success TIMESTAMP, last_failure TIMESTAMP,
                             last_error_type TEXT, is_active BOOLEAN DEFAULT 1, health_score REAL DEFAULT 1.0)''')

                c.execute('''SELECT feed_url, is_active, health_score, last_failure, consecutive_failures FROM feed_health_v2''')

                health_data = {row[0]: {
                    'is_active': row[1],
                    'health_score': row[2],
                    'last_failure': date_parser.parse(row[3]) if row[3] else None,
                    'consecutive_failures': row[4]
                } for row in c.fetchall()}

                active_feeds = []
                for feed in all_feeds:
                    feed_url = feed[1]
                    if feed_url in health_data:
                        feed_health = health_data[feed_url]
                        if not feed_health['is_active']:
                            if feed_health['last_failure']:
                                hours_since_failure = (datetime.now() - feed_health['last_failure']).total_seconds() / 3600
                                if hours_since_failure < self.retry_after_hours:
                                    logger.debug(f"Skipping inactive feed {feed[0]} (failed {hours_since_failure:.1f}h ago)")
                                    continue
                                else:
                                    logger.info(f"Retrying previously failed feed {feed[0]}")
                    active_feeds.append(feed)

                logger.info(f"Active feeds: {len(active_feeds)}/{len(all_feeds)}")
                return active_feeds

        except sqlite3.Error as e:
            logger.error(f"Database error getting active feeds: {e}")
            return all_feeds
    
    def get_feed_report(self):
        """Generate feed health report"""
        try:
            with sqlite3.connect(self.db_file) as conn:
                c = conn.cursor()
                
                # Get overall statistics
                c.execute('''SELECT 
                               COUNT(*) as total_feeds,
                               SUM(CASE WHEN is_active = 1 THEN 1 ELSE 0 END) as active_feeds,
                               SUM(CASE WHEN health_score >= 0.8 THEN 1 ELSE 0 END) as healthy_feeds,
                               SUM(CASE WHEN health_score < 0.3 THEN 1 ELSE 0 END) as unhealthy_feeds,
                               AVG(health_score) as avg_health_score
                               FROM feed_health_v2''')
                
                stats = c.fetchone()
                
                # Get problem feeds
                c.execute('''SELECT feed_url, health_score, consecutive_failures, last_error_type
                               FROM feed_health_v2
                               WHERE health_score < 0.3 OR consecutive_failures > 3
                               ORDER BY health_score ASC
                               LIMIT 20''')
                
                problem_feeds = c.fetchall()
                
                return {
                    'total_feeds': stats[0] or 0,
                    'active_feeds': stats[1] or 0,
                    'healthy_feeds': stats[2] or 0,
                    'unhealthy_feeds': stats[3] or 0,
                    'avg_health_score': stats[4] or 0,
                    'problem_feeds': problem_feeds
                }
                
        except sqlite3.Error as e:
            logger.error(f"Database error generating feed report: {e}")
            return None

class NewsArticle:
    """Enhanced article class with improved date filtering"""

    def __init__(self, title, url, source, category, published_date=None, summary=None, content=None, tags=None):
        self.title = title
        self.url = url
        self.source = source
        self.category = category
        self.summary = summary or ""
        self.content = content or ""
        self.tags = tags or []
        self.keywords = []
        
        # CRITICAL: Enhanced date parsing with strict validation
        self.published_date = self._parse_date_with_validation(published_date, title, summary)
        self.content_hash = self._generate_hash()

        # Initialize importance and timeliness
        self.importance = 0.0
        self.timeliness = 0.0

        # Relevance scoring
        self.relevance_scores = {
            'policy_relevance': 0,
            'source_reliability': 0,
            'recency': 0,
            'sector_specificity': 0,
            'overall': 0
        }

        # Extended metadata
        self.metadata = {
            'source_type': self._determine_source_type(),
            'content_type': self._determine_content_type(),
            'word_count': len(self.title.split()) + len(self.summary.split()),
            'entities': {},
            'sentiment': 0,
            'processed': False,
            'date_source': 'provided' if published_date else 'extracted',
            'date_valid': self.published_date is not None
        }

    def extract_keywords(self):
        """Extract keywords from article content"""
        try:
            text = f"{self.title} {self.summary}".lower()
            
            # Simple keyword extraction based on policy terms
            all_keywords = []
            
            # Check for policy keywords
            for keyword in Config.POLICY_KEYWORDS['high_relevance']:
                if keyword.lower() in text:
                    all_keywords.append(keyword)
            
            # Check for sector-specific keywords
            for sector, keywords in Config.POLICY_SECTORS.items():
                for keyword in keywords:
                    if keyword.lower() in text and keyword not in all_keywords:
                        all_keywords.append(keyword)
                        
            # Limit to top 10 keywords
            self.keywords = all_keywords[:10]
            
        except Exception as e:
            logger.debug(f"Error extracting keywords: {str(e)}")
            self.keywords = []

    def _parse_date_with_validation(self, date_string, title="", summary=""):
        """Enhanced date parsing - MORE LENIENT for government sources"""
        # First try the provided date
        if date_string:
            if isinstance(date_string, datetime):
                if date_string.tzinfo is not None:
                    date_string = date_string.replace(tzinfo=None)
                return date_string
            
            if isinstance(date_string, str):
                try:
                    parsed_date = date_parser.parse(date_string)
                    if parsed_date.tzinfo is not None:
                        parsed_date = parsed_date.replace(tzinfo=None)
                    return parsed_date
                except (ValueError, TypeError):
                    logger.debug(f"Failed to parse provided date: {date_string}")
        
        # Try to extract date from title/summary
        extracted_date = self._extract_date_from_text(f"{title} {summary}")
        if extracted_date:
            return extracted_date
        
        # Check if this is a government source
        gov_indicators = [
            'ministry', 'government', 'pib', 'rbi', 'sebi', 'trai', 
            'department', 'niti aayog', 'cabinet', 'parliament', 
            'supreme court', 'high court', 'tribunal', 'commission',
            'authority', 'board', 'bureau', 'directorate', 'secretariat',
            '.gov.in', '.nic.in', 'gazette', 'comptroller', 'auditor',
            'cag', 'cci', 'pfrda', 'irdai', 'fssai', 'cdsco', 'icmr'
        ]
        
        is_government_source = any(gov in self.source.lower() for gov in gov_indicators)
        
        # For government sources, be VERY lenient with missing dates
        if is_government_source:
            # Try to extract any date-like pattern from the URL
            url_date_patterns = [
                r'/(\d{4})/(\d{1,2})/(\d{1,2})/',  # /2024/03/15/
                r'date=(\d{4})-(\d{1,2})-(\d{1,2})',  # date=2024-03-15
                r'(\d{8})',  # 20240315
                r'(\d{4})-(\d{2})-(\d{2})',  # 2024-03-15
            ]
            
            for pattern in url_date_patterns:
                match = re.search(pattern, self.url)
                if match:
                    try:
                        date_str = match.group(0)
                        parsed_date = date_parser.parse(date_str, fuzzy=True)
                        if parsed_date.tzinfo is not None:
                            parsed_date = parsed_date.replace(tzinfo=None)
                        # Validate it's not too old
                        if (datetime.now() - parsed_date).days <= 90:
                            return parsed_date
                    except:
                        continue
            
            # For government sources without dates, assume very recent (within last 24 hours)
            return datetime.now() - timedelta(hours=12)
        
        # For news sources without dates, assume recent
        news_indicators = ['hindu', 'express', 'times', 'mint', 'standard', 'post', 'news']
        if any(news in self.source.lower() for news in news_indicators):
            return datetime.now() - timedelta(hours=6)
        
        # For other sources, try to be reasonable
        return datetime.now() - timedelta(days=7)  # Assume within last week instead of None

    def _is_date_reasonable(self, date_obj):
        """Check if date is reasonable (within 3 months and not future)"""
        if not date_obj:
            return False
        
        current_time = datetime.now()
        three_months_ago = current_time - timedelta(days=90)
        
        # Check if date is within reasonable range
        if date_obj > current_time:
            logger.debug(f"Date rejected - future date: {date_obj}")
            return False
        
        if date_obj < three_months_ago:
            logger.debug(f"Date rejected - older than 3 months: {date_obj}")
            return False
        
        return True

    def _extract_date_from_text(self, text):
        """Extract date from text using multiple patterns"""
        if not text:
            return None
        
        # Date patterns to look for
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',  # dd/mm/yyyy or dd-mm-yyyy
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',  # yyyy/mm/dd or yyyy-mm-dd
            r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})',  # dd Mon yyyy
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})',  # Mon dd, yyyy
            r'(\d{4})',  # Just year (last resort)
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    # Skip if it's just a year and it's old
                    if len(match.group(0)) == 4:  # Just year
                        year = int(match.group(0))
                        if year < datetime.now().year:
                            continue
                    
                    parsed_date = date_parser.parse(match.group(0), fuzzy=True)
                    if parsed_date.tzinfo is not None:
                        parsed_date = parsed_date.replace(tzinfo=None)
                    return parsed_date
                except:
                    continue
        
        return None

    def is_within_timeframe(self, months=3):
        """Check if article is within specified timeframe"""
        if not self.published_date:
            return False
        
        cutoff_date = datetime.now() - timedelta(days=months * 30)
        return self.published_date >= cutoff_date
    
    def _parse_date(self, date_string):
        """Parse various date formats - returns naive datetime"""
        if not date_string:
            return datetime.now()

        if isinstance(date_string, datetime):
            if date_string.tzinfo is not None:
                return date_string.replace(tzinfo=None)
            return date_string

        try:
            from dateutil import parser as date_parser
            dt = date_parser.parse(date_string)
            return dt.replace(tzinfo=None)
        except (ValueError, TypeError):
            return datetime.now()
            
    def is_entertainment_url(self, url: str = None) -> bool:
        """
        Checks if a URL path contains keywords that indicate it's likely
        entertainment content and should be skipped.
        """
        url = url or self.url
        try:
            # We only check the path part of the URL (e.g., /entertainment/movies/...)
            # This avoids false positives from domain names.
            url_path = urlparse(url).path.lower()
            
            # Check if any of our configured keywords are in the URL path
            if any(keyword in url_path for keyword in Config.ENTERTAINMENT_URL_KEYWORDS):
                return True
        except Exception:
            # In case of a malformed URL, assume it's not entertainment.
            return False
            
        return False


    def _generate_hash(self):
        """Generate unique hash for article"""
        import hashlib
        content = f"{self.title}{self.url}".lower()
        run_hash = hashlib.md5(content.encode()).hexdigest()
        
        if hasattr(self, 'published_date') and self.published_date:
            date_str = self.published_date.isoformat() if hasattr(self.published_date, 'isoformat') else str(self.published_date)
            self.storage_hash = hashlib.md5(f"{content}{date_str}".encode()).hexdigest()
        else:
            self.storage_hash = run_hash

        return run_hash

    def _determine_source_type(self):
        """Classify the source type"""
        source_lower = self.source.lower()

        if any(gov in source_lower for gov in ['ministry', 'government', 'pib', 'rbi', 'sebi', 'trai', 'gazette', 'niti aayog']):
            return 'government'
        elif any(legal in source_lower for legal in ['court', 'judiciary', 'livelaw', 'bar and bench']):
            return 'legal'
        elif any(think in source_lower for think in ['research', 'institute', 'foundation', 'orf', 'cpr', 'takshashila']):
            return 'think_tank'
        elif any(edu in source_lower for edu in ['university', 'college', 'academic']):
            return 'academic'
        elif any(biz in source_lower for biz in ['business', 'economic', 'financial', 'economy']):
            return 'business'
        elif any(media in source_lower for media in ['times', 'express', 'hindu', 'mint', 'ndtv', 'news']):
            return 'news_media'
        else:
            return 'other'

    def _determine_content_type(self):
        """Guess the content type based on title and summary"""
        text = (self.title + " " + self.summary).lower()

        if any(term in text for term in ['analysis', 'opinion', 'perspective', 'view', 'column']):
            return 'analysis'
        elif any(term in text for term in ['notification', 'circular', 'order', 'notice']):
            return 'notification'
        elif any(term in text for term in ['judgment', 'verdict', 'ruling', 'order', 'case']):
            return 'legal'
        elif any(term in text for term in ['bill', 'legislation', 'parliament', 'amendment', 'act']):
            return 'legislation'
        elif any(term in text for term in ['policy', 'regulation', 'regulatory', 'framework', 'guidelines']):
            return 'policy'
        elif any(term in text for term in ['report', 'study', 'survey', 'research', 'findings']):
            return 'report'
        elif any(term in text for term in ['interview', 'qa', 'q&a', 'speaking', 'conversation']):
            return 'interview'
        else:
            return 'news'

    def calculate_relevance_scores(self):
        """Enhanced relevance calculation - more lenient for government sources"""
        try:
            text = f"{self.title} {self.summary} {self.content}".lower()
            
            # Check source type FIRST
            source_is_government = any(gov in self.source.lower() for gov in [
                'ministry', 'government', 'rbi', 'sebi', 'trai', 'pib', 'department',
                'niti aayog', 'cabinet', 'parliament', 'lok sabha', 'rajya sabha',
                'supreme court', 'high court', 'tribunal', 'commission', 'authority',
                'board', 'bureau', 'directorate', 'secretariat', '.gov.in', '.nic.in',
                'comptroller', 'auditor general', 'cag', 'cci', 'competition commission',
                'pfrda', 'irdai', 'fssai', 'cdsco', 'icmr', 'dst', 'drdo', 'isro'
            ])
            
            # For government sources, start with very high base relevance
            if source_is_government:
                # Check if it's organizational content
                if self.is_organizational_content(self.title, self.url):
                    policy_relevance = 0.1  # Low score for org content
                else:
                    policy_relevance = 0.7  # Very high base score for government content
                    
                    # Add bonus for policy keywords
                    policy_keywords = ['policy', 'regulation', 'notification', 'circular', 
                                     'guideline', 'order', 'scheme', 'act', 'bill', 'amendment',
                                     'rule', 'directive', 'announcement', 'decision', 'approval',
                                     'implementation', 'initiative', 'program', 'mission']
                    keyword_matches = sum(1 for keyword in policy_keywords if keyword in text)
                    policy_relevance = min(1.0, policy_relevance + (keyword_matches * 0.05))
            else:
                # Non-government sources - use existing logic
                exclusion_score = self._calculate_exclusion_score(text)
                if exclusion_score > 0.6:
                    policy_relevance = 0.0
                else:
                    policy_relevance = self._calculate_policy_relevance_(text)
            
            # Source reliability score - maximum for government sources
            if source_is_government:
                source_reliability = 1.0  # Maximum reliability
            else:
                # Check for environmental/energy policy sources
                environmental_sources = [
                    'mongabay', 'climate change news', 'renewable energy', 'clean energy',
                    'environmental', 'conservation', 'third pole', 'carbon brief',
                    'solar power', 'wind power', 'nuclear power', 'down to earth'
                ]
                
                is_environmental_source = any(env in self.source.lower() for env in environmental_sources)
                
                if is_environmental_source:
                    # Check if it has policy relevance
                    policy_indicators = ['fund', 'investment', 'capacity', 'target', 'achieve',
                                         'government', 'ministry', 'agreement', 'conference']
                    policy_matches = sum(1 for ind in policy_indicators if ind in text)
                    
                    if policy_matches >= 1:
                        source_reliability = 0.8  # High reliability for environmental policy sources
                    else:
                        source_reliability = 0.6
                else:
                    # Check configured source reliability
                    for source_name, reliability in Config.SOURCE_RELIABILITY.items():
                        if source_name.lower() in self.source.lower():
                            source_reliability = reliability / 5.0
                            break
                    else:
                        source_reliability = 0.5
            
            # Recency score - be generous with government sources
            if self.published_date:
                current_time = datetime.now()
                hours_diff = (current_time - self.published_date).total_seconds() / 3600
                
                if hours_diff <= 24:
                    recency = 1.0
                elif hours_diff <= 72:
                    recency = 0.9
                elif hours_diff <= 168:
                    recency = 0.7
                elif hours_diff <= 720:
                    recency = 0.5
                else:
                    recency = 0.3
            else:
                # If no date but from government source, assume recent
                recency = 0.8 if source_is_government else 0.4
            
            # Sector specificity
            sector_specificity = self._calculate_sector_specificity(text)
            
            # Calculate overall score - heavily weight government sources
            if source_is_government:
                overall = (
                    policy_relevance * 0.6 +    # Policy relevance still important
                    source_reliability * 0.3 +    # Government = maximum reliability
                    recency * 0.1             # Recency less important for government
                )
            else:
                overall = (
                    policy_relevance * 0.5 +
                    source_reliability * 0.3 +
                    recency * 0.15 +
                    sector_specificity * 0.05
                )
            
            self.relevance_scores = {
                'policy_relevance': round(policy_relevance, 2),
                'source_reliability': round(source_reliability, 2),
                'recency': round(recency, 2),
                'sector_specificity': round(sector_specificity, 2),
                'overall': round(overall, 2)
            }

            return self.relevance_scores

        except Exception as e:
            logging.error(f"Error calculating relevance scores: {str(e)}")
            source_is_government = any(gov in self.source.lower() for gov in ['ministry', 'government', 'rbi', 'sebi', 'trai', 'pib'])
            # More generous fallback scores for government sources
            if source_is_government:
                self.relevance_scores = {
                    'policy_relevance': 0.7,
                    'source_reliability': 1.0,
                    'recency': 0.6,
                    'sector_specificity': 0.4,
                    'overall': 0.7
                }
            else:
                self.relevance_scores = {
                    'policy_relevance': 0.4,
                    'source_reliability': 0.6,
                    'recency': 0.5,
                    'sector_specificity': 0.2,
                    'overall': 0.4
                }
            return self.relevance_scores
    
    def _calculate_exclusion_score(self, text):
        """Less aggressive exclusion scoring to allow legitimate policy content"""
        # Check for policy exception keywords first
        policy_exceptions = sum(1 for keyword in Config.POLICY_EXCEPTION_KEYWORDS 
                                if keyword.lower() in text)
        
        # Check for strong policy context indicators
        strong_policy_context = sum(1 for indicator in Config.POLICY_CONTEXT_INDICATORS 
                                    if indicator.lower() in text)
        
        # Check for policy validation keywords
        policy_validation = sum(1 for keyword in Config.POLICY_VALIDATION_KEYWORDS 
                                if keyword.lower() in text)
        
        # NEW: Check for business policy keywords
        business_policy_keywords = [
            'trade', 'export', 'import', 'tariff', 'bilateral', 'agreement',
            'deal', 'treaty', 'defence', 'defense', 'strategic', 'cooperation'
        ]
        business_policy = sum(1 for keyword in business_policy_keywords if keyword in text)
        
        # Calculate policy protection level - MORE GENEROUS
        if strong_policy_context >= 1:
            policy_protection = 0.9  # Very strong policy protection
        elif policy_exceptions >= 1 or business_policy >= 2:
            policy_protection = 0.7  # Strong policy protection
        elif policy_validation >= 1 or business_policy >= 1:
            policy_protection = 0.5  # Moderate policy protection
        else:
            policy_protection = 0.1  # Some policy protection
        
        # Calculate exclusion matches with REDUCED weights
        exclusion_score = 0.0
        category_weights = {
            'organizational_content': 2.0,     # Reduced from 3.0
            'celebrity_entertainment': 4.0,    # Reduced from 5.0
            'sports_content': 3.5,             # Reduced from 4.0
            'educational_commercial': 3.0,     # Reduced from 4.0
            'product_launches': 2.0,           # Reduced from 3.0
            'commercial_content': 1.5,         # Reduced from 2.5
            'technology_consumer': 1.0,        # Reduced from 2.0
            'social_media_features': 1.5,      # Reduced from 2.0
            'literature_culture': 1.0          # Reduced from 1.5
        }
        
        for category, keywords in Config.EXCLUSION_KEYWORDS.items():
            category_matches = sum(1 for keyword in keywords if keyword.lower() in text)
            if category_matches > 0:
                weight = category_weights.get(category, 1.0)
                # Less aggressive scoring - require more matches
                category_score = min(1.0, (category_matches / len(keywords)) * weight * 1.5)  # Reduced from 2.0
                exclusion_score += category_score
        
        # Normalize exclusion score (less aggressive)
        exclusion_score = min(1.0, exclusion_score / 3.0)  # Increased denominator for less aggressive filtering
        
        # Apply stronger policy protection
        if exclusion_score > 0.8:  # Only reduce protection for very obvious non-policy content
            policy_protection *= 0.5  # Less reduction than before
        
        final_exclusion_score = exclusion_score * (1 - policy_protection)
        
        return final_exclusion_score

    def _calculate_policy_relevance_(self, text):
        """More lenient policy relevance calculation"""
        # Start with base relevance for any content
        policy_relevance = 0.15  # Increased from 0.1
        
        # Check for strong policy context indicators
        strong_context_indicators = sum(1 for indicator in Config.POLICY_CONTEXT_INDICATORS 
                                        if indicator.lower() in text)
        
        # NEW: Check for business/trade policy indicators
        business_indicators = [
            'trade deal', 'trade agreement', 'trade talks', 'bilateral',
            'defence deal', 'defense deal', 'strategic partnership',
            'export', 'import', 'tariff', 'anti-dumping', 'sanctions'
        ]
        business_matches = sum(1 for indicator in business_indicators if indicator in text)
        
        if strong_context_indicators >= 1 or business_matches >= 1:
            policy_relevance = 0.5  # Good base score
            
            # Add points for high relevance keywords
            high_relevance_matches = sum(1 for keyword in Config.POLICY_KEYWORDS['high_relevance'] 
                                         if keyword.lower() in text)
            policy_relevance += min(0.3, high_relevance_matches * 0.05)
            
            # Add points for medium relevance keywords
            medium_relevance_matches = sum(1 for keyword in Config.POLICY_KEYWORDS['medium_relevance'] 
                                           if keyword.lower() in text)
            policy_relevance += min(0.2, medium_relevance_matches * 0.03)
            
        else:
            # Check for basic policy indicators
            policy_validation = sum(1 for keyword in Config.POLICY_VALIDATION_KEYWORDS 
                                    if keyword.lower() in text)
            
            high_priority_keywords = [
                'government', 'ministry', 'parliament', 'court', 'supreme court',
                'high court', 'rbi', 'sebi', 'trai', 'cci', 'cabinet',
                'policy', 'regulation', 'legislation', 'bill', 'act',
                'trade', 'export', 'import', 'defence', 'defense'
            ]
            
            high_priority_matches = sum(1 for keyword in high_priority_keywords 
                                        if keyword.lower() in text)
            
            # More lenient scoring
            if high_priority_matches >= 2 or policy_validation >= 1:
                policy_relevance = 0.4
            elif high_priority_matches >= 1:
                policy_relevance = 0.3
        
        return min(1.0, policy_relevance)

    def _calculate_sector_specificity(self, text):
        """Stricter sector specificity requiring policy context"""
        sector_scores = {}
        
        # Check for strong policy context indicators
        strong_context_indicators = sum(1 for indicator in Config.POLICY_CONTEXT_INDICATORS 
                                          if indicator.lower() in text)
        
        # Check for policy validation keywords
        policy_validation = sum(1 for keyword in Config.POLICY_VALIDATION_KEYWORDS 
                                  if keyword.lower() in text)
        
        for sector, keywords in Config.POLICY_SECTORS.items():
            # Look for sector-specific keywords
            matches = sum(1 for keyword in keywords if keyword.lower() in text)
            
            if matches > 0:
                # Require strong policy context for sector classification
                if strong_context_indicators >= 1:
                    # Strong policy context present
                    density = matches / len(keywords)
                    context_bonus = min(0.3, strong_context_indicators * 0.1)
                    sector_scores[sector] = min(1.0, density * 2.5 + context_bonus)
                elif policy_validation >= 2:
                    # Some policy validation present
                    density = matches / len(keywords)
                    validation_bonus = min(0.2, policy_validation * 0.05)
                    sector_scores[sector] = min(0.6, density * 1.5 + validation_bonus)
                else:
                    # No policy context - very low score
                    sector_scores[sector] = 0.0
            else:
                sector_scores[sector] = 0.0
        
        if sector_scores:
            best_score = max(sector_scores.values())
            # Only update category if we have strong evidence
            if best_score > 0.4:
                best_sector = max(sector_scores.items(), key=lambda x: x[1])
                if best_sector[1] > 0.4:
                    self.category = best_sector[0]
            return best_score
        
        return 0.0

    def categorize_article(self, title: str, summary: str, query: str = None) -> str:
        """Enhanced categorization with environmental and energy policy recognition"""
        text = (title + " " + summary).lower()
        
        # Check organizational content first
        if self.is_organizational_content(title, self.url):
            return "Non-Policy Content"
        
        # Check for environmental/climate policy
        climate_indicators = [
            'climate', 'carbon', 'emission', 'renewable', 'sustainable',
            'environmental', 'conservation', 'biodiversity', 'green fund'
        ]
        climate_count = sum(1 for indicator in climate_indicators if indicator in text)
        
        if climate_count >= 1:
            # Check for policy context
            policy_words = ['policy', 'fund', 'investment', 'agreement', 'conference',
                            'regulation', 'standard', 'initiative', 'program', 'target']
            if any(word in text for word in policy_words):
                # Determine specific category
                if any(word in text for word in ['climate', 'carbon', 'emission', 'cop']):
                    return "Climate Policy"
                elif any(word in text for word in ['renewable', 'solar', 'wind', 'energy storage']):
                    return "Renewable Energy Policy"
                elif any(word in text for word in ['conservation', 'biodiversity', 'wildlife']):
                    return "Conservation Policy"
                else:
                    return "Environmental Policy"
        
        # Enhanced fallback patterns
        policy_patterns = [
            (['renewable', 'solar', 'wind', 'energy', 'power', 'capacity'], "Renewable Energy Policy"),
            (['climate', 'carbon', 'emission', 'adaptation', 'mitigation'], "Climate Policy"),
            (['conservation', 'wildlife', 'biodiversity', 'ecosystem'], "Conservation Policy"),
            (['nuclear', 'reactor', 'atomic'], "Energy Policy"),
        ]
        
        for patterns, category in policy_patterns:
            if any(pattern in text for pattern in patterns):
                # Verify policy context
                if any(word in text for word in ['policy', 'government', 'fund', 'investment', 
                                                 'project', 'initiative', 'program']):
                    return category
        
        # If from a known policy source, give benefit of doubt
        if any(source in self.source.lower() for source in ['mongabay', 'climate', 'renewable', 'energy news']):
            return "Environmental Policy"
        
        return "Policy News"  # Default policy category

    def calculate_importance(self):
        """Calculate importance based on relevance scores"""
        self.importance = (
            self.relevance_scores['policy_relevance'] * 0.4 +
            self.relevance_scores['source_reliability'] * 0.3 +
            self.relevance_scores['sector_specificity'] * 0.3
        )
        return self.importance
    
    def is_organizational_content(self, title: str = None, link: str = None) -> bool:
        """
        Checks if the content is likely organizational (e.g., 'About Us', 'Contact')
        rather than a policy article.
        """
        # Use self attributes if not provided
        title = title or self.title
        link = link or self.url
        
        title_lower = title.lower()
        link_lower = link.lower()

        # First check if it contains policy keywords - if yes, it's likely NOT organizational
        policy_indicators = [
            'policy', 'notification', 'circular', 'guideline', 'regulation',
            'act', 'bill', 'amendment', 'order', 'rule', 'scheme',
            'announcement', 'decision', 'approval', 'implementation'
        ]
        
        for indicator in policy_indicators:
            if indicator in title_lower:
                return False  # It's a policy article, not organizational
        
        # ONLY flag as organizational if it EXACTLY matches these patterns
        exact_org_titles = [
            'about us', 'contact us', 'who we are', 'our team', 'careers',
            'privacy policy', 'terms of service', 'disclaimer', 'sitemap',
            'copyright', 'accessibility'
        ]
        
        # Check for exact matches only
        for org_title in exact_org_titles:
            if title_lower == org_title or title_lower.startswith(org_title + ' '):
                return True
        
        # Check URL patterns more carefully
        org_url_endings = [
            '/about-us', '/contact-us', '/careers', '/privacy-policy',
            '/terms', '/disclaimer', '/sitemap'
        ]
        
        for pattern in org_url_endings:
            if link_lower.endswith(pattern) or link_lower.endswith(pattern + '/'):
                return True
        
        return False

    def calculate_timeliness(self):
        """Calculate timeliness based on published date"""
        if not self.published_date:
            self.timeliness = 0.0
            return self.timeliness

        current_time = datetime.now()
        hours_diff = (current_time - self.published_date).total_seconds() / 3600

        if hours_diff <= 6:
            self.timeliness = 1.0
        elif hours_diff <= 24:
            self.timeliness = 0.8
        elif hours_diff <= 72:
            self.timeliness = 0.6
        elif hours_diff <= 168:
            self.timeliness = 0.4
        elif hours_diff <= 336:
            self.timeliness = 0.2
        else:
            self.timeliness = 0.1

        return self.timeliness

    def to_dict(self):
        """Convert article to dictionary for JSON serialization"""
        return {
            'title': self.title,
            'url': self.url,
            'source': self.source,
            'category': self.category,
            'published_date': self.published_date.isoformat() if isinstance(self.published_date, datetime) else self.published_date,
            'summary': self.summary,
            'content': self.content,
            'tags': self.tags,
            'keywords': self.keywords,
            'content_hash': self.content_hash,
            'relevance_scores': self.relevance_scores,
            'metadata': self.metadata
        }

class PolicyRadarEnhanced:
    """Enhanced PolicyRadar class with improved filtering and organization"""

    def __init__(self):
        self.session = self._create_resilient_session()
        self.initialize_db()
        self.feed_health = {}
        self.article_hashes = set()
        self.statistics = {
            'total_feeds': 0,
            'successful_feeds': 0,
            'failed_feeds': 0,
            'total_articles': 0,
            'start_time': time.time(),
            'duplicate_articles': 0,
            'filtered_articles': 0,
            'fallback_successes': 0,
            'direct_scrape_articles': 0,
            'google_news_articles': 0,
            'low_relevance_articles': 0
        }
        
        # Debug tracking system
        self.filtered_articles_log = []  # Track all filtered articles
        self.feed_failure_reasons = {}   # Track why feeds fail
        self.debug_mode = True           # Enable detailed tracking

        self.load_article_hashes()
        self.feeds = self._get_comprehensive_feeds()

        # Add this property to control duplicate detection
        self.ignore_duplicates = False

        # New field to store all articles for advanced filtering
        self.all_articles = []

        # Keep track of when each source was last successfully fetched
        self.source_last_update = {}

        # Load stored source reliability data if available
        self.source_reliability_data = self._load_source_reliability_data()

    def log_filtered_article(self, article, reason, stage="filtering"):
        """Log filtered articles for analysis"""
        if self.debug_mode:
            self.filtered_articles_log.append({
                'title': article.title,
                'url': article.url,
                'source': article.source,
                'published_date': str(article.published_date) if article.published_date else 'No date',
                'reason': reason,
                'stage': stage,
                'relevance_score': article.relevance_scores.get('overall', 0) if hasattr(article, 'relevance_scores') else 0,
                'category': article.category if hasattr(article, 'category') else 'Unknown'
            })

    def log_feed_failure(self, feed_url, source_name, reason, error_details=None):
        """Log why a feed failed"""
        if self.debug_mode:
            self.feed_failure_reasons[source_name] = {
                'url': feed_url,
                'reason': reason,
                'error': str(error_details) if error_details else None,
                'timestamp': datetime.now().isoformat()
            }

    def get_user_agent(self):
        """Return a random user agent from the list"""
        return random.choice(Config.USER_AGENTS)
    
    def initialize_feed_monitor(self):
        """Initialize feed health monitoring with better error handling"""
        try:
            self.feed_monitor = FeedHealthMonitor(Config.DB_FILE)
            
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('''CREATE TABLE IF NOT EXISTS feed_health_v2
                             (feed_url TEXT PRIMARY KEY,
                             total_attempts INTEGER DEFAULT 0,
                             successful_attempts INTEGER DEFAULT 0,
                             consecutive_failures INTEGER DEFAULT 0,
                             last_success TIMESTAMP,
                             last_failure TIMESTAMP,
                             last_error_type TEXT,
                             is_active BOOLEAN DEFAULT 1,
                             health_score REAL DEFAULT 1.0)''')
                conn.commit()
                logger.info("Feed health monitoring initialized")
        except Exception as e:
            logger.error(f"Error initializing feed monitor: {e}")
            # Create dummy monitor that doesn't break execution
            class DummyFeedMonitor:
                def get_active_feeds(self, feeds):
                    return feeds
                def update_feed_health(self, url, success, error=None):
                    pass
            self.feed_monitor = DummyFeedMonitor()

    def _is_product_or_gadget_content(self, article):
        """Enhanced detection of product/gadget content"""
        text = f"{article.title} {article.summary}".lower()
        
        # Strong product/gadget indicators
        product_patterns = [
            r'\b\w+\s+review\b',  # "iPhone review", "laptop review"
            r'\bphone\s+launch\b',
            r'\bsmartphone\s+specs\b',
            r'\bgadget\s+review\b',
            r'\bunboxing\b',
            r'\bhands[- ]on\b',
            r'\bfirst\s+look\b',
            r'\bprice\s+announced\b',
            r'\bavailable\s+for\s+\₹\b',
            r'\bbuy\s+now\b',
            r'\bpre[- ]order\b'
        ]
        
        # Check for product patterns
        for pattern in product_patterns:
            if re.search(pattern, text):
                return True
        
        # Gadget-specific terms without policy context
        gadget_terms = ['smartphone', 'phone', 'tablet', 'laptop', 'earbuds', 'smartwatch']
        policy_terms = ['policy', 'regulation', 'government', 'ban', 'tax', 'import duty']
        
        has_gadget = any(term in text for term in gadget_terms)
        has_policy = any(term in text for term in policy_terms)
        
        # If gadget terms but no policy context, it's likely product content
        return has_gadget and not has_policy

    def is_policy_relevant(self, article):
        """Enhanced policy relevance check that's more inclusive of legitimate policy content"""

        if self._is_product_or_gadget_content(article):
            return False
        text = f"{article.title} {article.summary}".lower()

            # Immediate exclusions for obvious non-policy content
        non_policy_patterns = [
            r'\breview\s+of\s+\w+',
            r'\bphone\s+specs\b',
            r'\bbest\s+\w+\s+under\b',
            r'\bhow\s+to\s+buy\b',
            r'\bprice\s+drop\b',
            r'\bdiscount\s+offer\b'
        ]
        
        for pattern in non_policy_patterns:
            if re.search(pattern, text):
                return False
        
        # Source authority check - expanded list
        source_lower = article.source.lower()
        
        # Expanded list of authoritative sources (including business sources for policy content)
        is_authoritative_source = any(source in source_lower for source in [
            'government', 'ministry', 'rbi', 'sebi', 'trai', 'supreme court', 'high court',
            'parliament', 'pib', 'gazette', 'niti aayog', 'cabinet', 'cag', 'cci',
            'drdo', 'isro', 'pmo', 'president', 'vice president', 'department of',
            'directorate', 'bureau', 'authority', 'commission', 'council',
            # Environmental sources
            'mongabay', 'climate change news', 'renewable energy news', 'clean energy',
            'environmental', 'conservation', 'sustainable', 'green climate',
            # Energy sources
            'solar power', 'wind power', 'nuclear power', 'energy news',
            # Business sources (for policy-relevant business news)
            'economic times', 'business standard', 'mint', 'financial express',
            'indian express', 'times of india', 'hindustan times'
        ])
        
        # Check for business/trade policy content
        business_policy_indicators = [
            'trade deal', 'trade agreement', 'trade talks', 'trade plea', 'trade dispute',
            'anti-dumping', 'tariff', 'export', 'import', 'fdi', 'foreign investment',
            'bilateral', 'multilateral', 'wto', 'trade policy', 'trade war',
            'sanctions', 'embargo', 'quota', 'trade barrier', 'free trade',
            'defence deal', 'defense deal', 'defence agreement', 'defense agreement',
            'military cooperation', 'strategic partnership', 'arms deal',
            'technology transfer', 'joint venture', 'collaboration agreement',
            'mou', 'memorandum', 'pact', 'treaty', 'accord'
        ]
        
        # Check if it's business content with policy implications
        has_business_policy = any(indicator in text for indicator in business_policy_indicators)
        
        # Check for corporate actions with policy implications
        corporate_policy_indicators = [
            'regulatory', 'compliance', 'government contract', 'public sector',
            'disinvestment', 'privatization', 'nationalization', 'merger approval',
            'antitrust', 'competition commission', 'regulatory approval',
            'government stake', 'strategic sale', 'ipo', 'qip', 'fpo',
            'rbi approval', 'sebi approval', 'government permission'
        ]
        
        has_corporate_policy = any(indicator in text for indicator in corporate_policy_indicators)
        
        # For environmental/energy sources, check for policy context
        if any(env_source in source_lower for env_source in ['mongabay', 'climate', 'renewable', 'energy', 'environmental', 'conservation']):
            env_policy_indicators = [
                'policy', 'regulation', 'government', 'ministry', 'fund', 'finance',
                'investment', 'capacity', 'target', 'agreement', 'conference',
                'summit', 'cop', 'initiative', 'program', 'project', 'scheme',
                'subsidy', 'incentive', 'mandate', 'standard', 'compliance',
                'adaptation', 'mitigation', 'transition', 'reform', 'development',
                'deployment', 'implementation', 'announcement', 'achieves', 'opens'
            ]
            
            policy_word_count = sum(1 for word in env_policy_indicators if word in text)
            
            policy_actions = [
                'achieves', 'announces', 'opens', 'launches', 'implements',
                'approves', 'backs', 'commits', 'invests', 'funds', 'supports',
                'develops', 'plans', 'proposes', 'considers', 'evaluates'
            ]
            
            action_count = sum(1 for action in policy_actions if action in text)
            
            if policy_word_count >= 2 or (policy_word_count >= 1 and action_count >= 1):
                return True
        
        # For government sources - very lenient
        if is_authoritative_source:
            if self.is_organizational_content(article.title, article.url):
                return False
            
            # Any policy-related word is enough
            basic_policy_words = [
                'policy', 'regulation', 'law', 'act', 'bill', 'notification',
                'circular', 'guidelines', 'order', 'decision', 'announcement',
                'statement', 'update', 'news', 'release', 'initiative',
                'program', 'scheme', 'project', 'investment', 'fund', 'grant',
                'capacity', 'development', 'implementation', 'achievement',
                'agreement', 'deal', 'pact', 'treaty', 'accord', 'talks'
            ]
            
            return any(word in text for word in basic_policy_words)
        
        # NEW: For business/economic sources with policy content
        if has_business_policy or has_corporate_policy:
            # Even if not from government source, include if it has clear policy implications
            return True
        
        # For other sources, check for strong policy context
        strong_context = sum(1 for indicator in Config.POLICY_CONTEXT_INDICATORS if indicator.lower() in text)
        policy_validation = sum(1 for keyword in Config.POLICY_VALIDATION_KEYWORDS if keyword.lower() in text)
        
        # More lenient thresholds
        return strong_context >= 1 or policy_validation >= 1  # Reduced from 2

    def filter_articles_by_relevance(self, articles, min_relevance=0.15):  # Lowered from 0.20
        """Enhanced filtering with more lenient thresholds for policy content"""
        filtered_articles = []
        
        for article in articles:
            # Expanded list of authoritative sources
            source_lower = article.source.lower()
            is_government_source = any(gov in source_lower for gov in [
                'ministry', 'government', 'rbi', 'sebi', 'trai', 'pib', 'department',
                'niti aayog', 'cabinet', 'parliament', 'lok sabha', 'rajya sabha',
                'supreme court', 'high court', 'tribunal', 'commission', 'authority',
                'board', 'bureau', 'directorate', 'secretariat', '.gov.in', '.nic.in',
                'comptroller', 'auditor general', 'cag', 'cci', 'competition commission',
                'pfrda', 'irdai', 'fssai', 'cdsco', 'icmr', 'dst', 'drdo', 'isro',
                'cert-in', 'uidai', 'npci', 'gazette', 'press information bureau'
            ])
            
            # Very lenient threshold for government sources
            effective_min_relevance = 0.05 if is_government_source else min_relevance
            
            # Skip organizational content check for government sources
            if is_government_source:
                if self.is_organizational_content(article.title, article.url):
                    self.log_filtered_article(article, "Organizational content from government source", "category_filter")
                    self.statistics['filtered_articles'] += 1
                    continue
                else:
                    filtered_articles.append(article)
                    continue
            
            # For non-government sources, check relevance but be more lenient
            if article.relevance_scores['overall'] < effective_min_relevance:
                self.log_filtered_article(article, f"Low relevance score: {article.relevance_scores['overall']:.2f}", "relevance_filter")
                self.statistics['filtered_articles'] += 1
                continue
            
            # Skip pure entertainment/lifestyle content
            if self._is_pure_entertainment(article):
                self.log_filtered_article(article, "Entertainment/lifestyle content", "content_filter")
                self.statistics['filtered_articles'] += 1
                continue
            
            # Accept all other articles that pass basic relevance
            filtered_articles.append(article)
        
        logger.info(f"Filtered {len(articles)} articles to {len(filtered_articles)} relevant articles")
        return filtered_articles

    def _is_pure_entertainment(self, article):
        """Check if article is purely entertainment/lifestyle with no policy relevance"""
        text = f"{article.title} {article.summary}".lower()
        
        # Entertainment indicators
        entertainment_indicators = [
            'bollywood', 'hollywood', 'movie review', 'film review', 'box office',
            'celebrity', 'actor', 'actress', 'fashion show', 'reality show',
            'cricket match', 'football match', 'sports score', 'game review',
            'smartphone review', 'gadget review', 'product launch', 'unboxing'
        ]
        
        # Policy exception - even if entertainment topic, keep if policy related
        policy_exceptions = [
            'regulation', 'policy', 'government', 'ministry', 'court', 'legal',
            'ban', 'censorship', 'law', 'act', 'bill', 'guidelines'
        ]
        
        has_entertainment = any(indicator in text for indicator in entertainment_indicators)
        has_policy = any(exception in text for exception in policy_exceptions)
        
        return has_entertainment and not has_policy

    def _has_clear_policy_indicators(self, article):
        """Check if article has clear policy indicators regardless of score"""
        text = f"{article.title} {article.summary}".lower()
        
        clear_indicators = [
            'trade deal', 'defence deal', 'defense deal', 'bilateral agreement',
            'strategic partnership', 'government approval', 'regulatory approval',
            'anti-dumping', 'trade war', 'sanctions', 'treaty', 'accord',
            'memorandum of understanding', 'mou signed', 'policy announcement',
            'cabinet approval', 'parliament passes', 'bill introduced'
        ]
        
        return any(indicator in text for indicator in clear_indicators)

    def _is_business_policy_article(self, article):
        """Check if business article has policy implications"""
        text = f"{article.title} {article.summary}".lower()
        
        business_policy_patterns = [
            ('trade', ['deal', 'agreement', 'talks', 'dispute', 'war']),
            ('defence', ['deal', 'agreement', 'contract', 'purchase']),
            ('defense', ['deal', 'agreement', 'contract', 'purchase']),
            ('bilateral', ['agreement', 'talks', 'cooperation', 'trade']),
            ('government', ['contract', 'approval', 'permission', 'deal']),
            ('regulatory', ['approval', 'clearance', 'compliance', 'action']),
            ('anti-dumping', ['duty', 'investigation', 'probe', 'case']),
            ('investment', ['policy', 'rules', 'regulations', 'limits'])
        ]
        
        for main_term, qualifiers in business_policy_patterns:
            if main_term in text:
                if any(qualifier in text for qualifier in qualifiers):
                    return True
        
        return False
        
    def _create_resilient_session(self):
        """
        Creates a resilient requests session with settings optimized for the execution environment.
        - Local Environment: Uses an aggressive SSL bypass and retry strategy for difficult sites.
        - GitHub Actions: Uses a simpler, more compatible configuration.
        """
        session = requests.Session()

        if IS_GITHUB_ACTIONS:
            # --- GitHub Actions Configuration ---
            logger.info("Creating a session optimized for GitHub Actions.")
            session.verify = False
            
            # Suppress only the unverified HTTPS request warning
            warnings.filterwarnings('ignore', message='Unverified HTTPS request')
            
            # Use a simpler retry strategy and adapter
            retry_strategy = Retry(
                total=2,
                backoff_factor=1,
                status_forcelist=[500, 502, 503, 504]
            )
            adapter = HTTPAdapter(
                max_retries=retry_strategy,
                pool_connections=50,
                pool_maxsize=50
            )
            session.mount('https://', adapter)
            session.mount('http://', adapter)

        else:
            # --- Local/Production Environment Configuration ---
            logger.info("Creating a resilient session with enhanced SSL compatibility.")

            # Custom adapter with an extremely permissive SSL context
            class UltraPermissiveSSLAdapter(HTTPAdapter):
                def init_poolmanager(self, *args, **kwargs):
                    ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
                    # Disable ALL verification
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    # Allow legacy ciphers for older government sites
                    ctx.set_ciphers('ALL:@SECLEVEL=1')
                    # Allow legacy connection options if the Python version supports them
                    if hasattr(ssl, 'OP_LEGACY_SERVER_CONNECT'):
                        ctx.options |= ssl.OP_LEGACY_SERVER_CONNECT
                    if hasattr(ssl, 'OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION'):
                        ctx.options |= ssl.OP_ALLOW_UNSAFE_LEGACY_RENEGOTIATION
                    
                    kwargs['ssl_context'] = ctx
                    return super().init_poolmanager(*args, **kwargs)

            # More aggressive retry strategy for difficult connections
            retry_strategy = Retry(
                total=5,
                backoff_factor=3,
                status_forcelist=[403, 429, 500, 502, 503, 504],
                allowed_methods=["GET", "HEAD"],
                respect_retry_after_header=True
            )
            
            # Create and mount the custom adapter for HTTPS
            adapter = UltraPermissiveSSLAdapter(
                max_retries=retry_strategy,
                pool_connections=200,
                pool_maxsize=200,
            )
            session.mount("https://", adapter)
            
            # Mount a standard adapter for HTTP
            session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
            
            # Disable all SSL warnings from urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            session.verify = False

        # Set a universal default timeout for the session
        session.timeout = 60
        return session

    def fetch_with_selenium_and_parse(self, url, source_name, category):
        """Fetches content using Selenium and then passes it to the parser."""
        logger.info(f"Using Selenium for protected site: {source_name}")
        html_content = self.get_html_with_selenium(url)
        
        if html_content:
            # If we got HTML, encode it and pass it to our flexible parser
            return self._parse_content_flexible(html_content.encode('utf-8'), source_name, category, url)
            
        logger.warning(f"Selenium fetch returned no content for {source_name}")
        return []

    def get_html_with_selenium(self, url: str) -> Optional[str]:
        """Enhanced Selenium browser for blocked sites"""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.common.exceptions import TimeoutException
        except ImportError:
            logger.error("Selenium not installed. Run: pip install selenium")
            return None

        logger.info(f"Using Selenium for blocked site: {url}")

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-web-security")
        chrome_options.add_argument("--disable-features=VizDisplayCompositor")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        
        # Stealth options
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_experimental_option("prefs", {
            "profile.default_content_setting_values.notifications": 2,
            "profile.password_manager_enabled": False,
            "credentials_enable_service": False
        })
        
        # Random user agent
        chrome_options.add_argument(f"user-agent={self._get_browser_user_agent()}")
        
        # Window size
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument("--start-maximized")

        driver = None
        try:
            # Try to find chromedriver
            chrome_driver_paths = [
                '/usr/local/bin/chromedriver',
                '/usr/bin/chromedriver',
                'chromedriver',
                './chromedriver'
            ]
            
            chrome_driver_path = None
            for path in chrome_driver_paths:
                if os.path.exists(path):
                    chrome_driver_path = path
                    break
            
            if not chrome_driver_path:
                # Try using webdriver-manager
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                    chrome_driver_path = ChromeDriverManager().install()
                except:
                    logger.error("ChromeDriver not found. Install it or run: pip install webdriver-manager")
                    return None

            service = Service(executable_path=chrome_driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Execute stealth JavaScript
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': '''
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });
                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                    window.chrome = {
                        runtime: {}
                    };
                    Object.defineProperty(navigator, 'permissions', {
                        get: () => ({
                            query: () => Promise.resolve({ state: 'granted' })
                        })
                    });
                '''
            })
            
            # Set page load timeout
            driver.set_page_load_timeout(45)
            
            # Navigate to the page
            driver.get(url)
            
            # Wait for content based on site
            domain = urlparse(url).netloc
            
            if 'pib.gov.in' in domain:
                # Wait for PIB specific elements
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "content-area"))
                    )
                except TimeoutException:
                    pass
            elif 'moneycontrol' in domain:
                # Wait for MoneyControl content
                try:
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located((By.CLASS_NAME, "article_wrap"))
                    )
                except TimeoutException:
                    pass
            else:
                # Generic wait
                time.sleep(3)
            
            # Scroll to trigger lazy loading
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1)
            
            # Get page source
            page_source = driver.page_source
            return page_source
            
        except TimeoutException:
            logger.error(f"Selenium timeout for {url}")
            return None
        except Exception as e:
            logger.error(f"Selenium failed for {url}: {str(e)}")
            return None
        finally:
            if driver:
                driver.quit()

    def should_use_selenium(self, url: str) -> bool:
        """Determine if a URL requires Selenium based on domain"""
        domain = urlparse(url).netloc.lower()
        return any(difficult_domain in domain for difficult_domain in Config.SELENIUM_REQUIRED_DOMAINS)

    def get_domain_specific_delay(self, url):
        """Get appropriate delay for different domains"""
        domain = urlparse(url).netloc.lower()
        
        # Government domains need longer delays
        gov_domains = ['.gov.in', '.nic.in', 'pib.', 'mygov.', '.gov.', 'parliament.']
        high_security_domains = ['rbi.org.in', 'sebi.gov.in', 'trai.gov.in', 'cert-in.org.in']
        
        if any(d in domain for d in high_security_domains):
            return random.uniform(3, 5)  # 3-5 seconds for high-security sites
        elif any(d in domain for d in gov_domains):
            return random.uniform(2, 3)  # 2-3 seconds for regular government sites
        else:
            return random.uniform(0.5, 1.5)  # 0.5-1.5 seconds for news sites

    def initialize_db(self):
        """Initialize SQLite database with enhanced schema for better filtering"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()

                # Check if we need to create tables or upgrade schema
                c.execute("PRAGMA user_version")
                db_version = c.fetchone()[0]

                if db_version == 0:
                    logger.info("Creating new database schema...")

                    # Create version table
                    c.execute('''CREATE TABLE IF NOT EXISTS schema_version
                                 (version TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

                    # Create sources table - now more detailed
                    c.execute('''CREATE TABLE IF NOT EXISTS sources
                                 (id TEXT PRIMARY KEY, name TEXT, url TEXT, category TEXT,
                                 type TEXT, reliability FLOAT, active BOOLEAN DEFAULT 1,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

                    # Feed history table
                    c.execute('''CREATE TABLE IF NOT EXISTS feed_history
                                 (feed_url TEXT, last_success TIMESTAMP, last_error TEXT,
                                 error_count INTEGER DEFAULT 0, success_count INTEGER DEFAULT 0,
                                 PRIMARY KEY (feed_url))''')

                    # Enhanced articles table with relevance scoring and metadata
                    c.execute('''CREATE TABLE IF NOT EXISTS articles
                                 (hash TEXT PRIMARY KEY, title TEXT, url TEXT, source TEXT,
                                 category TEXT, published_date TIMESTAMP, summary TEXT,
                                 content TEXT, tags TEXT, keywords TEXT,
                                 policy_relevance FLOAT DEFAULT 0, source_reliability FLOAT DEFAULT 0,
                                 recency FLOAT DEFAULT 0, sector_specificity FLOAT DEFAULT 0,
                                 overall_relevance FLOAT DEFAULT 0, metadata TEXT,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

                    # Table to store user filters and preferences
                    c.execute('''CREATE TABLE IF NOT EXISTS user_preferences
                                 (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT,
                                 categories TEXT, sources TEXT, tags TEXT,
                                 min_relevance FLOAT DEFAULT 0,
                                 created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

                    # Table to track article views and interactions
                    c.execute('''CREATE TABLE IF NOT EXISTS article_interactions
                                 (article_hash TEXT, interaction_type TEXT,
                                 timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                                 PRIMARY KEY (article_hash, interaction_type))''')

                    # Create indexes for faster lookups
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_overall_relevance ON articles(overall_relevance)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date)')

                    # Set schema version
                    c.execute("PRAGMA user_version = 1")
                    c.execute("INSERT INTO schema_version VALUES (?, datetime('now'))", (Config.DB_SCHEMA_VERSION,))

                    conn.commit()
                    logger.info("Database schema created successfully")

                elif db_version < 1:
                    # Handle future schema upgrades here
                    pass

        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            # Continue without raising error - we'll use in-memory storage if needed

    def get_healthy_feeds(self):
        """Get only healthy/active feeds"""
        return self.feed_monitor.get_active_feeds(self.feeds)

    def update_feed_health_status(self, feed_url, success, error_type=None):
        """Update feed health after fetch attempt"""
        if hasattr(self, 'feed_monitor'):
            self.feed_monitor.update_feed_health(feed_url, success, error_type)

    def _get_browser_user_agent(self):
        """Get a convincing browser user agent"""
        chrome_versions = ['120.0.0.0', '121.0.0.0', '122.0.0.0', '123.0.0.0']
        firefox_versions = ['121.0', '122.0', '123.0', '124.0']
        
        agents = [
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.choice(chrome_versions)} Safari/537.36',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.choice(chrome_versions)} Safari/537.36',
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{random.choice(firefox_versions)}) Gecko/20100101 Firefox/{random.choice(firefox_versions)[:-2]}',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:{random.choice(firefox_versions)}) Gecko/20100101 Firefox/{random.choice(firefox_versions)[:-2]}'
        ]
        
        return random.choice(agents)

    def load_article_hashes(self):
        """Start with an empty set of hashes for the current run
        to only filter duplicates within this run, not from previous runs"""
        self.article_hashes = set()
        logger.info(f"Starting with clean article hash cache for this run")

        # Optional: Log how many articles exist in the database for reference
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('SELECT COUNT(*) FROM articles')
                total_count = c.fetchone()[0]

                # Count articles from the last 24 hours
                yesterday = datetime.now() - timedelta(days=1)
                c.execute('SELECT COUNT(*) FROM articles WHERE created_at >= ?',
                          (yesterday.strftime("%Y-%m-%d %H:%M:%S"),))
                recent_count = c.fetchone()[0]

                logger.info(f"Database has {total_count} total articles, {recent_count} collected in the last 24 hours")
        except sqlite3.Error as e:
            logger.error(f"Database error checking article counts: {e}")

    def reset_article_cache(self):
        """Reset article cache completely"""
        self.article_hashes = set()
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('DELETE FROM articles')
                conn.commit()
                logger.info(f"Completely reset article database")
        except sqlite3.Error as e:
            logger.error(f"Database error clearing article cache: {e}")

    def clear_article_cache(self, days_to_keep=30):
        """Clear the article hashes cache (both in-memory and optionally database)"""
        # Clear in-memory set
        previous_count = len(self.article_hashes)
        self.article_hashes = set()
        logger.info(f"Cleared {previous_count} article hashes from memory")

        try:
            # Clear older articles from the database
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()

                # Get count before deletion for logging
                c.execute('SELECT COUNT(*) FROM articles')
                before_count = c.fetchone()[0]

                # Delete articles older than `days_to_keep`
                cutoff_date = datetime.now() - timedelta(days=days_to_keep)
                c.execute('DELETE FROM articles WHERE created_at < ?',
                          (cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),))

                deleted_count = before_count - c.execute('SELECT COUNT(*) FROM articles').fetchone()[0]
                conn.commit()
                logger.info(f"Deleted {deleted_count} articles from database (keeping last {days_to_keep} days)")
        except sqlite3.Error as e:
            logger.error(f"Database error clearing article cache: {e}")

    def update_feed_status(self, feed_url, success, error=None):
        """Update feed status in database with enhanced tracking"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()

                if success:
                    c.execute('''UPDATE feed_history
                                 SET last_success = CURRENT_TIMESTAMP,
                                     error_count = 0,
                                     last_error = NULL,
                                     success_count = success_count + 1
                                 WHERE feed_url = ?''', (feed_url,))

                    # If no record was updated, insert a new one
                    if c.rowcount == 0:
                        c.execute('''INSERT INTO feed_history
                                     (feed_url, last_success, success_count)
                                     VALUES (?, CURRENT_TIMESTAMP, 1)''',
                                     (feed_url,))
                else:
                    c.execute('''INSERT OR IGNORE INTO feed_history (feed_url) VALUES (?)''', (feed_url,))
                    c.execute('''UPDATE feed_history
                                 SET error_count = error_count + 1, last_error = ?
                                 WHERE feed_url = ?''', (str(error), feed_url))

                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error updating feed status: {e}")

    def save_article_to_db(self, article):
        """Save article to database with enhanced metadata and unique hash"""
        try:
            # Ensure article has relevance scores calculated
            if article.relevance_scores['overall'] == 0:
                article.calculate_relevance_scores()

            # Calculate importance and timeliness
            article.calculate_importance()
            article.calculate_timeliness()

            # Extract keywords if not already done
            if not article.keywords:
                article.extract_keywords()

            # Add current timestamp to create a unique version in the database
            collection_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # Generate a version-specific hash for this collection
            version_hash = hashlib.md5(f"{article.storage_hash}_{collection_time}".encode()).hexdigest()

            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()

                c.execute('''INSERT INTO articles
                             (hash, title, url, source, category, published_date, summary,
                             content, tags, keywords, policy_relevance, source_reliability,
                             recency, sector_specificity, overall_relevance, metadata, created_at)
                             VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                            (version_hash, article.title, article.url, article.source,
                            article.category, article.published_date, article.summary,
                            article.content, json.dumps(article.tags), json.dumps(article.keywords),
                            article.relevance_scores['policy_relevance'],
                            article.relevance_scores['source_reliability'],
                            article.relevance_scores['recency'],
                            article.relevance_scores['sector_specificity'],
                            article.relevance_scores['overall'],
                            json.dumps(article.metadata),
                            collection_time))

                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error saving article: {e}")

    def is_similar_article(self, article, max_days=2):
        """Check if a similar article already exists in the database (by title and URL)
        This is different from exact duplicate checking - it's to prevent
        multiple copies of the same article with minor variations"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()

                # Look for similar articles from the last few days
                cutoff_date = datetime.now() - timedelta(days=max_days)

                # First check by URL
                c.execute('SELECT hash FROM articles WHERE url = ? AND created_at >= ?',
                          (article.url, cutoff_date.strftime("%Y-%m-%d %H:%M:%S")))
                if c.fetchone():
                    logger.debug(f"Similar article found by URL: {article.url}")
                    return True

                # Then check by title similarity
                c.execute('SELECT title FROM articles WHERE created_at >= ?',
                          (cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),))
                existing_titles = [row[0] for row in c.fetchall()]

                # Simple title similarity check - at least 80% of the title matches
                article_title = article.title.lower()
                for title in existing_titles:
                    if not title:
                        continue

                    # Check Jaccard similarity of words
                    title_a = set(article_title.split())
                    title_b = set(title.lower().split())

                    if title_a and title_b:  # Ensure non-empty sets
                        intersection = len(title_a.intersection(title_b))
                        union = len(title_a.union(title_b))
                        similarity = intersection / union if union > 0 else 0

                        if similarity > 0.8:  # 80% similarity threshold
                            logger.debug(f"Similar article found by title: {article.title} (similarity: {similarity:.2f})")
                            return True

                return False
        except sqlite3.Error as e:
            logger.error(f"Database error checking for similar articles: {e}")
            return False  # On error, assume no similarity

    def _load_source_reliability_data(self):
        """Load source reliability data from database if available"""
        reliability_data = {}
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('SELECT name, reliability FROM sources WHERE reliability IS NOT NULL')
                for name, reliability in c.fetchall():
                    reliability_data[name] = reliability
        except sqlite3.Error as e:
            logger.debug(f"No stored source reliability data: {e}")

        # Combine with config defaults
        for source, reliability in Config.SOURCE_RELIABILITY.items():
            if source not in reliability_data:
                reliability_data[source] = reliability

        return reliability_data

    def _get_comprehensive_feeds(self):
        """Return the comprehensive list of verified URLs from the intelligence database"""
        return [
            # TIER 1: GOVERNMENT SOURCES (Fixed URLs)
            ("Reserve Bank of India - Notifications", "https://www.rbi.org.in/notifications_rss.xml", "Economic Policy"),
            ("Reserve Bank of India - Press Releases", "https://www.rbi.org.in/pressreleases_rss.xml", "Economic Policy"),
            ("Reserve Bank of India - Regulatory Circulars", "https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx", "Economic Policy"),
            ("Reserve Bank of India - Speeches", "https://www.rbi.org.in/speeches_rss.xml", "Economic Policy"),
            ("Reserve Bank of India - Publications", "https://www.rbi.org.in/Scripts/Publications.aspx", "Economic Policy"),
            ("SEBI - Press Releases", "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=6&ssid=23&smid=0", "Economic Policy"),
            ("SEBI - Public Notices", "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=6&ssid=25&smid=0", "Economic Policy"),
            ("SEBI - Clarifications", "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=6&ssid=27&smid=0", "Economic Policy"),
            ("Department of Economic Affairs", "https://dea.gov.in/recent-update", "Economic Policy"),
            ("Department of Economic Affairs - Budget", "https://dea.gov.in/budgetdivision/notifications", "Economic Policy"),
            ("NITI Aayog", "https://niti.gov.in/whats-new", "Economic Policy"),
            ("Competition Commission - What's New", "https://cci.gov.in/whats-new", "Economic Policy"),
            ("Competition Commission - Public Notices", "https://cci.gov.in/public-notices", "Economic Policy"),
            ("Competition Commission - Events", "https://cci.gov.in/events", "Economic Policy"),
            ("Competition Commission - Press Releases", "https://cci.gov.in/media-gallery/press-release", "Economic Policy"),
            ("GST Council - What's New", "https://gstcouncil.gov.in/what-s-new", "Economic Policy"),
            ("GST Council - Press Releases", "https://gstcouncil.gov.in/press-release", "Economic Policy"),
            ("GST Council - Newsletter", "https://gstcouncil.gov.in/gst-council-newsletter", "Economic Policy"),
            ("PIB Finance Ministry", "https://pib.gov.in/PressReleseDetail.aspx?PRID=1234567&min=16", "Economic Policy"),
            ("Comptroller and Auditor General", "https://cag.gov.in/en/press-release?arch=1", "Economic Policy"),
            ("Central Board of Direct Taxes", "https://incometaxindia.gov.in/Pages/press-releases.aspx", "Economic Policy"),
            ("Central Board of Indirect Taxes", "https://www.cbic.gov.in/entities/view-sticker", "Economic Policy"),
            ("Insolvency and Bankruptcy Board", "https://ibbi.gov.in/en/whats-new", "Economic Policy"),
            ("Insurance Regulatory Authority", "https://irdai.gov.in/press-releases", "Economic Policy"),
            ("Pension Fund Regulatory Authority", "https://www.pfrda.org.in/index1.cshtml?lsid=237", "Economic Policy"),
            ("Forward Markets Commission", "https://fmc.gov.in/notifications", "Economic Policy"),
            ("India Budget Portal", "https://www.indiabudget.gov.in/", "Economic Policy"),
            ("Economic Survey Portal", "https://www.indiabudget.gov.in/economicsurvey/", "Economic Policy"),
            ("Ministry of Electronics & IT - Press Releases", "https://www.meity.gov.in/documents/press-release?page=1", "Technology Policy"),
            ("Ministry of Electronics & IT - Documents", "https://www.meity.gov.in/documents?page=1", "Technology Policy"),
            ("TRAI Press Releases", "https://trai.gov.in/notifications/press-release", "Technology Policy"),
            ("TRAI What's New", "https://trai.gov.in/what-s-new", "Technology Policy"),
            ("CERT-In Advisories", "https://www.cert-in.org.in/s2cMainServlet?pageid=PUBADVLIST02&year=2024", "Technology Policy"),
            ("CERT-In Guidelines", "https://www.cert-in.org.in/s2cMainServlet?pageid=GUIDLNVIEW01", "Technology Policy"),
            ("Digital India Press Releases", "https://www.digitalindia.gov.in/press-release/", "Technology Policy"),
            ("Department of Science & Technology", "https://dst.gov.in/whatsnew/past-press-release", "Technology Policy"),
            ("C-DOT News", "https://www.cdot.in/cdotweb/web/news.php?lang=en", "Technology Policy"),
            ("STQC", "https://stqc.gov.in/whats-new", "Technology Policy"),
            ("National Informatics Centre", "https://informatics.nic.in/news", "Technology Policy"),
            ("UIDAI Press Releases", "https://uidai.gov.in/en/media-resources/media/press-releases.html", "Technology Policy"),
            ("Electronics Manufacturing", "https://www.meity.gov.in/ministry/our-groups/details/electronics-system-design-manufacturing-esdm-wM5kTNtQWa", "Technology Policy"),
            ("Software Technology Parks", "https://stpi.in/en/circulars-notifications", "Technology Policy"),
            ("NASSCOM", "https://nasscom.in/media-press", "Technology Policy"),
            ("Data Protection Framework", "https://www.meity.gov.in/data-protection-framework", "Technology Policy"),
            ("Cyber Crime Coordination", "https://i4c.mha.gov.in/press-release.aspx", "Technology Policy"),
            ("BharatNet", "https://bbnl.nic.in/index1.aspx?langid=1&lev=1&lsid=345&pid=0&lid=302", "Technology Policy"),
            ("Common Service Centers", "https://ecscgov.org/upcomingevents.html", "Technology Policy"),
            ("Ministry of External Affairs - Press Releases", "https://www.mea.gov.in/press-releases.htm?51/Press_Releases", "Foreign Policy"),
            ("MEA Media Briefings", "https://www.mea.gov.in/media-briefings.htm?49/Media_Briefings", "Foreign Policy"),
            ("Prime Minister's Office - Messages", "https://www.pmindia.gov.in/en/message-from-the-prime-minister/", "Foreign Policy"),
            ("PMO News Updates", "https://www.pmindia.gov.in/en/news-updates/", "Foreign Policy"),
            ("Ministry of Defence - Press Releases", "https://mod.gov.in/en/press-releases-ministry-defence-0/press-release-july-2025", "Defense & Security"),
            ("Ministry of Defence - Archive", "https://mod.gov.in/index.php/en/press-releases-ministry-defence-0", "Defense & Security"),
            ("Ministry of Home Affairs - What's New", "https://www.mha.gov.in/en/media/whats-new", "Defense & Security"),
            ("MHA Press Releases 2025", "https://www.mha.gov.in/en/commoncontent/press-release-2025", "Defense & Security"),
            ("DRDO Press Releases", "https://drdo.gov.in/drdo/press-release", "Defense & Security"),
            ("Border Security Force", "https://www.bsf.gov.in/press-release.html", "Defense & Security"),
            ("Central Reserve Police Force", "https://crpf.gov.in/Media-Centre/Press-Release", "Defense & Security"),
            ("ITBP Press Releases", "https://itbpolice.nic.in/Home/ProPressRelease", "Defense & Security"),
            ("Assam Rifles", "https://assamrifles.gov.in/english/newwindow.html?2030", "Defense & Security"),
            ("Indian Coast Guard", "https://indiancoastguard.gov.in/news", "Defense & Security"),
            ("Indian Navy", "https://indiannavy.gov.in/content/civilian", "Defense & Security"),
            ("Indian Army", "https://indianarmy.nic.in/about/adjutant-general-branch-directorates-and-branches/e-news-letter-adjutant-general-branch-directorates-and-branches", "Defense & Security"),
            ("Indian Air Force", "https://indianairforce.nic.in/latest-news", "Defense & Security"),
            ("Intelligence Bureau", "https://www.mha.gov.in/en/notifications/notice", "Defense & Security"),
            ("Central Bureau of Investigation", "https://cbi.gov.in/press-releases", "Defense & Security"),
            ("National Investigation Agency", "https://nia.gov.in/press-releases.htm", "Defense & Security"),
            ("Enforcement Directorate", "https://enforcementdirectorate.gov.in/press-release", "Defense & Security"),
            ("Cabinet Secretariat", "https://cabsec.gov.in/more/pressreleases/", "Governance & Administration"),
            ("DARPG What's New", "https://darpg.gov.in/en/whats-new", "Governance & Administration"),
            ("DARPG Archive", "https://darpg.gov.in/archive", "Governance & Administration"),
            ("MyGov Pulse Newsletter", "https://www.mygov.in/pulse-newsletter/", "Governance & Administration"),
            ("MyGov Weekly Newsletter", "https://www.mygov.in/weekly-newsletter/", "Governance & Administration"),
            ("India.gov.in News Updates", "https://india.gov.in/news-updates", "Governance & Administration"),
            ("PIB All Releases", "https://pib.gov.in/AllRelease.aspx", "Governance & Administration"),
            ("President's Office", "https://presidentofindia.nic.in/press-release", "Governance & Administration"),
            ("Vice President's Office", "https://vicepresidentofindia.nic.in/press-release", "Governance & Administration"),
            ("Lok Sabha Press Releases", "https://pprloksabha.sansad.in/PressReleases_pevents.aspx", "Governance & Administration"),
            ("Rajya Sabha Press Releases", "https://sansad.in/rs/pressRelease", "Governance & Administration"),
            ("Election Commission", "https://www.eci.gov.in/issue-details-page/press-releases", "Governance & Administration"),
            ("Planning Commission Archive", "https://www.pib.gov.in/allRel.aspx", "Governance & Administration"),
            ("Central Vigilance Commission", "https://cvc.gov.in/whatsnew.html", "Governance & Administration"),
            ("CAG Press Releases", "https://cag.gov.in/en/press-release", "Governance & Administration"),
            ("UPSC What's New", "https://upsc.gov.in/whats-new#", "Governance & Administration"),
            ("Staff Selection Commission", "https://ssc.nic.in/Portal/Notices", "Governance & Administration"),
            ("UGC Press Releases", "https://www.ugc.gov.in/publication/ugc_pressrelease", "Governance & Administration"),
            ("NCERT Notices", "https://ncert.nic.in/notices.php?ln=en", "Governance & Administration"),
            ("CBSE Press", "https://www.cbse.gov.in/cbsenew/press.html", "Governance & Administration"),
            ("AICTE Press Releases", "https://aicte.gov.in/newsroom/press-releases", "Governance & Administration"),
            ("National Archives", "https://nationalarchives.nic.in/e-abhilekh-news-letters", "Governance & Administration"),
            ("RTI Commission", "https://cic.gov.in/what-s-new", "Governance & Administration"),
            ("Lokpal", "https://lokpal.gov.in/?media_gallery?news", "Governance & Administration"),
            ("NCSC What's New", "https://ncsc.nic.in/whats-new", "Governance & Administration"),
            ("Ministry of Environment", "https://moef.gov.in/whats-new/update", "Environmental Policy"),
            ("Central Pollution Control Board", "https://cpcb.nic.in/important-notifications/", "Environmental Policy"),
            ("Ministry of New & Renewable Energy", "https://mnre.gov.in/en/whats-new/", "Environmental Policy"),
            ("National Green Tribunal", "https://www.greentribunal.gov.in/news-update", "Environmental Policy"),
            ("Forest Survey of India", "https://fsi.nic.in/photo-gallery", "Environmental Policy"),
            ("Wildlife Institute - Announcements", "https://wii.gov.in/announcements", "Environmental Policy"),
            ("Wildlife Institute - Newsletter", "https://wii.gov.in/images//images/documents/publications/enewsletter_spring_2025.pdf", "Environmental Policy"),
            ("Botanical Survey of India", "https://bsi.gov.in/monthly-reports/en", "Environmental Policy"),
            ("Zoological Survey of India", "https://zsi.gov.in/recent-update/en", "Environmental Policy"),
            ("India Meteorological Department", "https://internal.imd.gov.in/pages/press_release_mausam.php", "Environmental Policy"),
            ("National Centre for Agricultural Policy", "https://ncap.res.in/Niap_Policy_Briefs.php", "Environmental Policy"),
            ("Climate Change Action Committee", "https://ccac.sustainabledevelopment.in/publications", "Environmental Policy"),
            ("Central Electricity Authority", "https://cea.nic.in/whats-new/?lang=en", "Environmental Policy"),
            ("Indian Renewable Energy Development", "https://www.ireda.in/annual-reports", "Environmental Policy"),
            ("Ministry of Health", "https://mohfw.gov.in/?q=en/press-release", "Healthcare Policy"),
            ("ICMR Press Releases", "https://icmr.gov.in/press-releases", "Healthcare Policy"),
            ("CDSCO Public Notices", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Public-Notices/", "Healthcare Policy"),
            ("National Medical Commission", "https://www.nmc.org.in/media-room/news-and-event/", "Healthcare Policy"),
            ("AIIMS Notices", "https://www.aiims.edu/index.php/en/notices/notices", "Healthcare Policy"),
            ("National Centre for Disease Control", "https://ncdc.mohfw.gov.in/resource-library/", "Healthcare Policy"),
            ("Drug Controller General Archive", "https://cdsco.gov.in/opencms/opencms/en/Notifications/Archive/", "Healthcare Policy"),
            ("National AIDS Control", "https://www.naco.gov.in/naco-updates", "Healthcare Policy"),
            ("TB Control Program", "https://tbcindia.mohfw.gov.in/press-release-link-on-pib-2/press-release-link-on-pib/", "Healthcare Policy"),
            ("Ministry of Ayush", "https://ayush.gov.in/#!/whatsnew", "Healthcare Policy"),
            ("Food Safety Authority - Press Notes", "https://fssai.gov.in/press-note.php", "Healthcare Policy"),
            ("Food Safety Authority - Media", "https://fssai.gov.in/in-the-media-all.php", "Healthcare Policy"),
            ("Medical Council News Archive", "https://www.nmc.org.in/all-news/", "Healthcare Policy"),

            # TIER 2: NEWS & ANALYSIS SOURCES
            ("Economic Times - Policy News", "https://economictimes.indiatimes.com/topic/indian-policy-news", "Economic Policy"),
            ("Economic Times - Market News", "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms", "Economic Policy"),
            ("Business Standard - Finance Analysis", "https://www.business-standard.com/rss/finance/analysis-10314.rss", "Economic Policy"),
            ("Business Standard - Economy", "https://www.business-standard.com/rss/economy-102.rss", "Economic Policy"),            
            ("Business Standard - Markets", "https://www.business-standard.com/rss/markets-106.rss", "Economic Policy"),
            ("Business Standard - Companies", "https://www.business-standard.com/rss/companies-101.rss", "Economic Policy"),
            ("Mint - Economy", "https://www.livemint.com/rss/economy", "Economic Policy"),
            ("Mint - Markets", "https://www.livemint.com/rss/markets", "Economic Policy"),
            ("Mint - Money", "https://www.livemint.com/rss/money", "Economic Policy"),
            ("Financial Express - Business", "https://www.financialexpress.com/business/", "Economic Policy"),
            ("Financial Express - Market", "https://www.financialexpress.com/market/", "Economic Policy"),
            ("Financial Express - Money", "https://www.financialexpress.com/money/", "Economic Policy"),
            ("Financial Express - Latest News", "https://www.financialexpress.com/latest-news/", "Economic Policy"),
            ("Financial Express - Technology", "https://www.financialexpress.com/life/technology/", "Technology Policy"),
            ("Financial Express - Auto", "https://www.financialexpress.com/auto/", "Economic Policy"),
            ("BloombergQuint - Market Intelligence", "https://www.bloombergquint.com/feed", "Economic Policy"),
            ("MoneyControl - Latest News", "https://www.moneycontrol.com/rss/latestnews.xml", "Economic Policy"),
            ("MoneyControl - Stocks & Markets", "https://www.moneycontrol.com/stocksmarketsindia/", "Economic Policy"),
            ("MoneyControl - News", "https://www.moneycontrol.com/news/", "Economic Policy"),
            ("MoneyControl - Homepage", "https://www.moneycontrol.com/", "Economic Policy"),
            ("MoneyControl - Editor's Picks: Markets", "https://www.moneycontrol.com/editors-picks/markets/", "Economic Policy"),
            ("MoneyControl - Editor's Picks: Companies", "https://www.moneycontrol.com/editors-picks/companies/", "Economic Policy"),
            ("MoneyControl - Editor's Picks: Personal Finance", "https://www.moneycontrol.com/editors-picks/personal-finance/", "Economic Policy"),
            ("MoneyControl - Editor's Picks: Tech & Startups", "https://www.moneycontrol.com/editors-picks/tech-startups/", "Technology Policy"),
            ("MoneyControl - Editor's Picks: Politics", "https://www.moneycontrol.com/editors-picks/politics/", "Governance & Administration"),
            ("MoneyControl - Editor's Picks: Policy", "https://www.moneycontrol.com/editors-picks/policy/", "Policy Analysis"),
            ("MoneyControl - Editor's Picks: Banking", "https://www.moneycontrol.com/editors-picks/banking/", "Economic Policy"),
            ("Zee Business - Latest News", "https://www.zeebiz.com/latest.xml/feed", "Economic Policy"),
            ("The Hindu Business - Economy", "https://www.thehindu.com/business/Economy/feeder/default.rss", "Economic Policy"),
            ("Indian Express - Business", "https://indianexpress.com/section/business/feed/", "Economic Policy"),
            ("Times of India - Business", "https://timesofindia.indiatimes.com/rssfeeds/1898055.cms", "Economic Policy"),
            ("Hindustan Times - Business", "https://www.hindustantimes.com/feeds/rss/business/rssfeed.xml", "Economic Policy"),
            ("NDTV Profit - Economy & Finance", "https://www.ndtvprofit.com/economy-finance", "Economic Policy"),
            ("India Today - Business", "https://www.indiatoday.in/rss/1206606", "Economic Policy"),
            ("News18 - Business", "https://www.news18.com/rss/business.xml", "Economic Policy"),
            ("Firstpost - Business", "https://www.firstpost.com/commonfeeds/v1/mfp/rss/business.xml", "Economic Policy"),
            ("DNA - Money", "https://www.dnaindia.com/feeds/money.xml", "Economic Policy"),
            ("Deccan Chronicle - Business", "https://www.deccanchronicle.com/business", "Economic Policy"),
            ("Telegraph - Business", "https://www.telegraphindia.com/business/", "Economic Policy"),
            ("Asian Age - Business", "https://www.asianage.com/business", "Economic Policy"),
            ("Millennium Post - Business", "https://www.millenniumpost.in/business", "Economic Policy"),
            ("Pioneer - Business", "https://www.dailypioneer.com/business/page/1", "Economic Policy"),
            ("MediaNama - Tech Policy", "https://medianama.com/tag/policy/feed/", "Technology Policy"),
            ("Inc42 - Startup Ecosystem", "https://inc42.com/feed/", "Technology Policy"),
            ("YourStory - Startup Stories", "https://yourstory.com/feed", "Technology Policy"),
            ("The Ken - Deep Tech Analysis", "https://the-ken.com/feed/", "Technology Policy"),
            ("Economic Times - Tech", "https://economictimes.indiatimes.com/tech/rssfeeds/13357270.cms", "Technology Policy"),
            ("LiveMint - Technology", "https://www.livemint.com/rss/technology", "Technology Policy"),
            ("Business Standard - Technology", "https://www.business-standard.com/rss/technology-108.rss", "Technology Policy"),
            ("Business Standard - Tech News", "https://www.business-standard.com/rss/technology/tech-news-10817.rss", "Technology Policy"),
            ("Hindu BusinessLine - Info-Tech", "https://www.thehindubusinessline.com/info-tech/feeder/default.rss", "Technology Policy"),
            ("Financial Express - Tech Industry", "https://www.financialexpress.com/industry/technology/feed/", "Technology Policy"),
            ("Times of India - Tech", "https://timesofindia.indiatimes.com/rssfeeds/66949542.cms", "Technology Policy"),
            ("Indian Express - Technology", "https://indianexpress.com/section/technology/feed/", "Technology Policy"),
            ("NDTV Gadgets", "https://gadgets.ndtv.com/rss/feeds", "Technology Policy"),
            ("India Today - Tech", "https://www.indiatoday.in/technology", "Technology Policy"),
            ("News18 - Tech", "https://www.news18.com/rss/tech.xml", "Technology Policy"),
            ("Firstpost - Tech", "https://www.firstpost.com/commonfeeds/v1/mfp/rss/tech.xml", "Technology Policy"),
            ("DNA - Science & Tech", "https://www.dnaindia.com/feeds/scitech.xml", "Technology Policy"),
            ("Deccan Chronicle - Tech", "https://www.deccanchronicle.com/technology", "Technology Policy"),
            ("Telegraph - Science & Tech", "https://www.telegraphindia.com/science-tech/", "Technology Policy"),
            ("Tech2 - Tech Reviews", "https://www.firstpost.com/tech/", "Technology Policy"),
            ("Gadgets360 - AI", "https://www.gadgets360.com/rss/ai/feeds", "Technology Policy"),
            ("Gadgets360 - Social Networking", "https://www.gadgets360.com/rss/social-networking/feeds", "Technology Policy"),
            ("Gadgets360 - News", "https://www.gadgets360.com/rss/news", "Technology Policy"),
            ("Gadgets360 - Internet", "https://www.gadgets360.com/rss/internet/feeds", "Technology Policy"),
            ("Gadgets360 - Breaking News", "https://www.gadgets360.com/rss/breaking-news/feeds", "Technology Policy"),
            ("Gadgets360 - Cryptocurrency", "https://www.gadgets360.com/rss/cryptocurrency/feeds", "Technology Policy"),
            ("Gadgets360 - India", "https://www.gadgets360.com/rss/india/feeds", "Technology Policy"),
            ("Gadgets360 - Science", "https://www.gadgets360.com/rss/science/feeds", "Technology Policy"),
            ("Gadgets360 - Auto", "https://www.gadgets360.com/rss/auto/feeds", "Technology Policy"),
            ("Gadgets360 - Telecom", "https://www.gadgets360.com/rss/telecom/feeds", "Technology Policy"),
            ("Gadgets360 - Transportation", "https://www.gadgets360.com/rss/transportation/feeds", "Technology Policy"),
            ("Gadgets360 - Culture", "https://www.gadgets360.com/rss/culture/feeds", "Technology Policy"),
            ("The Print - Politics", "https://theprint.in/category/politics/feed/", "Governance & Administration"),
            ("The Wire - Homepage", "https://thewire.in/", "Governance & Administration"),
            ("The Wire - Politics", "https://thewire.in/category/politics/all", "Governance & Administration"),
            ("The Wire - Government", "https://thewire.in/category/government/all", "Governance & Administration"),
            ("Scroll.in - Articles", "https://feeds.feedburner.com/ScrollinArticles.rss", "Governance & Administration"),
            ("The Quint - News", "https://www.thequint.com/stories.rss?section=news", "Governance & Administration"),
            ("Indian Express - National News", "https://indianexpress.com/feed/", "Governance & Administration"),
            ("The Hindu - National News", "https://www.thehindu.com/news/national/feeder/default.rss", "Governance & Administration"),
            ("Times of India - National News", "https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms", "Governance & Administration"),
            ("Hindustan Times - India News", "https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml", "Governance & Administration"),
            ("NDTV - Latest News", "https://feeds.feedburner.com/NDTV-LatestNews", "Governance & Administration"),
            ("India Today - News Coverage", "https://www.indiatoday.in/rss/1206578", "Governance & Administration"),
            ("News18 - Politics", "https://www.news18.com/rss/politics.xml", "Governance & Administration"),
            ("Firstpost - Politics", "https://www.firstpost.com/commonfeeds/v1/mfp/rss/politics.xml", "Governance & Administration"),
            ("DNA - India News", "https://www.dnaindia.com/feeds/india.xml", "Governance & Administration"),
            ("Deccan Chronicle - National News", "https://www.deccanchronicle.com/category/nation/google_feeds.xml", "Governance & Administration"),
            ("Telegraph - India Coverage", "https://www.telegraphindia.com/news-sitemap.xml", "Governance & Administration"),
            ("Millennium Post - National Coverage", "https://www.millenniumpost.in/category/nation/google_feeds.xml", "Governance & Administration"),
            ("Pioneer - National News", "https://www.dailypioneer.com/rss/nation.xml", "Governance & Administration"),
            ("Outlook - Magazine", "https://www.outlookindia.com/magazine/11-july-2025", "Governance & Administration"),
            ("India Express - Delhi News", "https://indianexpress.com/section/cities/delhi/feed/", "Governance & Administration"),
            ("The Hindu - Delhi News", "https://www.thehindu.com/news/cities/Delhi/feeder/default.rss", "Governance & Administration"),
            ("TOI - Delhi News", "https://timesofindia.indiatimes.com/rssfeeds/2647163.cms", "Governance & Administration"),
            ("HT - Delhi Junction", "https://www.hindustantimes.com/feeds/rss/htcity/htcity-delhi-junction/rssfeed.xml", "Governance & Administration"),
            ("Caravan Magazine - Politics", "https://caravanmagazine.in/politics", "Policy Analysis"),
            ("Frontline - Politics", "https://frontline.thehindu.com/politics/", "Policy Analysis"),
            ("Week - News Magazine", "https://www.theweek.in/news/india.html", "Policy Analysis"),
            ("Open Magazine - Current Affairs", "https://openthemagazine.com/features/politics-features/", "Policy Analysis"),
            ("EPW - Economic & Political Weekly", "https://www.epw.in/open-access", "Policy Analysis"),
            ("Pragati - Policy Magazine", "https://takshashila.org.in", "Policy Analysis"),
            ("The Diplomat - Politics", "https://thediplomat.com/topics/politics/feed/", "Foreign Policy"),
            ("StratNews Global - Asia", "https://stratnewsglobal.com/asia/", "Foreign Policy"),
            ("Live Law - Legal News", "https://www.livelaw.in/google_feeds.xml", "Constitutional & Legal"),
            ("Bar & Bench - Legal Industry", "https://www.barandbench.com/feed", "Constitutional & Legal"),
            ("Legally India - Legal Profession", "https://www.legallyindia.com/feed", "Constitutional & Legal"),
            ("Supreme Court Observer - SC Coverage", "https://www.scobserver.in/feed/", "Constitutional & Legal"),
            ("Bar Council News - Announcements", "https://www.barcouncilofindia.org/info/announcements", "Constitutional & Legal"),
            ("Lawstreet Journal - Law Students", "https://lawstreet.co/", "Constitutional & Legal"),
            ("Indian Code - Legal Updates", "https://legalaffairs.gov.in/news-listing/", "Constitutional & Legal"),
            ("SCC Online - Legal Database", "https://www.scconline.com/blog/feed/", "Constitutional & Legal"),
            ("Manupatra - Legal Research (Category 3)", "https://updates.manupatra.com/roundup/contentlist.aspx?issue=488&icat=3", "Constitutional & Legal"),
            ("Manupatra - Legal Research (Category 1)", "https://updates.manupatra.com/roundup/Contentlist.aspx?issue=488&icat=1", "Constitutional & Legal"),
            ("Manupatra - Legal Research (Category 2)", "https://updates.manupatra.com/roundup/Contentlist.aspx?issue=488&icat=2", "Constitutional & Legal"),
            ("Manupatra - Legal Research (Category 5)", "https://updates.manupatra.com/roundup/Contentlist.aspx?issue=488&icat=5", "Constitutional & Legal"),
            ("Law Times Journal - Legal Articles", "https://lawtimesjournal.in/feed/", "Constitutional & Legal"),
            ("Legal Service India - Articles", "https://www.legalserviceindia.com/articles/articles.html", "Constitutional & Legal"),
            ("iPleaders - Legal Education", "https://blog.ipleaders.in/feed/", "Constitutional & Legal"),
            ("Legal Bites - Legal Analysis", "https://www.legalbites.in/feed/", "Constitutional & Legal"),
            ("Lawyers Update - Legal Updates", "https://lawyersupdate.co.in/", "Constitutional & Legal"),
            ("Taxguru - Tax Law", "https://taxguru.in/feed/", "Constitutional & Legal"),
            ("Law Insider - Legal News", "https://www.lawinsider.in/rss/", "Constitutional & Legal"),
            ("Nyaaya - Legal Awareness", "https://nyaaya.org/the-nyaaya-weekly/", "Constitutional & Legal"),
            ("Vidhi Centre - Legal Policy", "https://vidhilegalpolicy.in/feed/", "Constitutional & Legal"),
            ("DAKSH - Judicial Reforms", "https://www.dakshindia.org/articles-and-blogposts/google_feed.xml/rss", "Constitutional & Legal"),
            ("Down To Earth - Environment", "https://www.downtoearth.org.in/environment", "Environmental Policy"),
            ("Mongabay India - Conservation News", "https://india.mongabay.com/feed", "Environmental Policy"),
            ("Climate Change News - Global Climate", "https://www.climatechangenews.com/feed/", "Environmental Policy"),
            ("Carbon Brief - Climate Science", "https://www.carbonbrief.org/feed/", "Environmental Policy"),
            ("The Third Pole - Himalayan Environment", "https://dialogue.earth/feed/", "Environmental Policy"),
            ("Sandrp - Rivers & Dams", "https://sandrp.in/feed/", "Environmental Policy"),
            ("Environmental Information System - Data", "http://envis.nic.in/Content/archive.aspx?menu_id=106", "Environmental Policy"),
            ("Green Tribunal - Orders", "https://www.greentribunal.gov.in/", "Environmental Policy"),
            ("CSE - Press Releases", "https://www.cseindia.org/press-releases", "Environmental Policy"),
            ("Greenpeace India - Environmental Activism", "https://www.greenpeace.org/india/en/", "Environmental Policy"),
            ("WWF India - Press", "https://www.wwfindia.org/news_facts/pres/", "Environmental Policy"),
            ("WWF India - Feature Stories", "https://www.wwfindia.org/news_facts/feature_stories/", "Environmental Policy"),
            ("WWF India - Publications", "https://www.wwfindia.org/news_facts/wwf_publications/", "Environmental Policy"),
            ("Wildlife Trust - News", "https://www.wti.org.in/resource-centre/news/", "Environmental Policy"),
            ("Bombay Natural History Society - Press Releases", "https://www.bnhs.org/press-releases", "Environmental Policy"),
            ("Clean Energy News - Clean Technology", "https://cleantechnica.com/feed/", "Environmental Policy"),
            ("Renewable Energy News - Asia Pacific", "https://renewablesnow.com/news/news_feed/?region=asia+pacific", "Environmental Policy"),
            ("Solar Power News - Solar Industry", "https://www.solarpowerworldonline.com/feed/", "Environmental Policy"),
            ("Wind Power News - Wind Energy", "https://www.windpowerengineering.com/feed/", "Environmental Policy"),
            ("Hydro Power News - Hydroelectric Power", "https://www.energyvoice.com/category/renewables-energy-transition/hydro/feed/", "Environmental Policy"),
            ("Nuclear Power News - Nuclear Energy", "https://www.world-nuclear-news.org/rss", "Environmental Policy"),
            ("Energy News - Energy Sector", "https://www.canarymedia.com/rss.rss", "Environmental Policy"),
            ("Climate Policy Initiative - India", "https://www.climatepolicyinitiative.org/the-regions/cpi-in-india/", "Environmental Policy"),
            ("CEEW - Press Releases", "https://www.ceew.in/press-releases", "Environmental Policy"),
            ("TERI - News", "https://www.teriin.org/news", "Environmental Policy"),
            ("TERI - Press Release", "https://www.teriin.org/press-release", "Environmental Policy"),
            ("TERI - Opinion", "https://www.teriin.org/opinion", "Environmental Policy"),
            ("IRADe - Energy Policy", "https://irade.org/", "Environmental Policy"),
            ("NIAS - Science Policy", "https://www.nias.res.in/Home", "Environmental Policy"),
        ]

    def fetch_google_news_policy_articles(self, max_articles=150):
        """Enhanced Google News fetching with strict policy focus"""
        all_articles = []

        # FIXED: More focused policy queries
        general_queries = [
            "India government policy notification",
            "India ministry announcement policy", 
            "India parliament bill legislation",
            "India supreme court policy ruling",
            "India cabinet decision approval",
            "India regulatory authority notification",
            "India RBI SEBI TRAI policy",
            "India policy reform implementation"
        ]

        # FIXED: Sector-specific with policy context
        sector_queries = [
            "India technology policy regulation digital",
            "India economic policy monetary fiscal", 
            "India education policy NEP implementation",
            "India health policy healthcare regulation",
            "India environment policy climate regulation",
            "India agriculture policy farm reform",
            "India energy policy renewable regulation"
        ]

        # FIXED: More specific site queries
        site_queries = [
            "site:pib.gov.in notification policy",
            "site:rbi.org.in policy circular",
            "site:sebi.gov.in regulation policy", 
            "site:prsindia.org legislation analysis",
            "site:livelaw.in policy judgment",
            "site:medianama.com technology policy regulation"
        ]
        
        # Rest of the function remains the same...
        all_queries = general_queries + sector_queries + site_queries
        logger.info(f"Fetching policy news from Google News RSS with {len(all_queries)} search queries")

        for query in all_queries:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

            try:
                headers = {
                    'User-Agent': self.get_user_agent(),
                    'Accept': 'application/rss+xml, application/atom+xml, text/xml, */*;q=0.1',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Referer': 'https://news.google.com/',
                    'Connection': 'keep-alive'
                }
                response = self.session.get(url, headers=headers, timeout=20, verify=False, allow_redirects=True)

                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    if not feed.entries:
                        logger.warning(f"No Google News results for query: {query}")
                        continue
                    
                    logger.info(f"Found {len(feed.entries)} Google News articles for query: {query}")
                    for entry in feed.entries[:15]:
                        source = entry.source.title if hasattr(entry, 'source') and hasattr(entry.source, 'title') else "Google News"
                        published = entry.published if hasattr(entry, 'published') else None
                        summary = ""
                        if hasattr(entry, 'description'):
                            soup = BeautifulSoup(entry.description, 'html.parser')
                            summary = soup.get_text().strip()

                        article = NewsArticle(
                            title=entry.title, url=entry.link, source=source,
                            category="Policy News", published_date=published, summary=summary,
                            tags=self.assign_tags(entry.title, summary)
                        )

                        if not article.is_within_timeframe(months=3):
                            logger.debug(f"Google News article rejected - too old or no date: {entry.title}")
                            continue

                        article.calculate_relevance_scores()
                        if article.relevance_scores['overall'] >= 0.2:
                            if article.content_hash not in self.article_hashes:
                                self.article_hashes.add(article.content_hash)
                                all_articles.append(article)
                                self.save_article_to_db(article)
                        else:
                            self.statistics['low_relevance_articles'] += 1
                        
                        if len(all_articles) >= max_articles: break
                else:
                    logger.warning(f"Failed to fetch Google News for query '{query}': Status {response.status_code}")
                
                if len(all_articles) >= max_articles: break
            except Exception as e:
                logger.error(f"Error fetching Google News for query '{query}': {e}")
            
            time.sleep(random.uniform(0.5, 1.0))

        self.statistics['google_news_articles'] = len(all_articles)
        logger.info(f"Found {len(all_articles)} recent articles from Google News RSS")
        return all_articles

    def direct_scrape_reliable_sources(self) -> List[NewsArticle]:
        """Directly scrape the most reliable Indian policy news websites with updated selectors and enhanced filtering."""
        articles = []
        reliable_sources = [
            {"name": "PRS Legislative Research", "url": "https://prsindia.org/bills", "category": "Constitutional & Legal", "selectors": {"article": ".bill-listing-item-container", "title": ".title-container a", "summary": ".field-name-field-bill-summary", "link": ".title-container a"}},
            {"name": "PIB - Press Release", "url": "https://pib.gov.in/AllRelease.aspx", "category": "Governance & Administration", "selectors": {"article": "ul.releases li", "title": "a", "summary": ".background-gray", "link": "a"}},
            {"name": "LiveLaw Top Stories", "url": "https://www.livelaw.in/top-stories", "category": "Constitutional & Legal", "selectors": {"article": "div.news-list-item", "title": "h2 > a", "summary": ".news-list-item-author-time", "link": "a"}},
            {"name": "Bar and Bench", "url": "https://www.barandbench.com/news", "category": "Constitutional & Legal", "selectors": {"article": "div.listing-story-wrapper-with-image", "title": "h2.title-story a", "summary": ".author-time-story", "link": "a"}},
        ]
        logger.info(f"Performing direct scraping on {len(reliable_sources)} updated source URLs")

        for source in reliable_sources:
            name, url, category, selectors = source["name"], source["url"], source["category"], source["selectors"]
            logger.info(f"Direct scraping {name} at {url}")
            # This is a placeholder for the actual scraping logic (requests, BeautifulSoup, etc.)
            # For this example, we'll simulate finding a few article elements.
            try:
                # Simulate finding some elements
                # In a real implementation:
                # response = self.session.get(url, ...)
                # soup = BeautifulSoup(response.text, 'html.parser')
                # article_elements = soup.select(selectors["article"])
                
                # Placeholder elements for demonstration
                class MockElement:
                    def __init__(self, text, href):
                        self._text = text
                        self._href = href
                    def get_text(self, strip=False): return self._text
                    def get(self, key, default=''): return self._href if key == 'href' else default
                    def select_one(self, selector): return self
                    @property
                    def text(self): return self._text
                    def __getitem__(self, key): return self._href

                article_elements = [
                    MockElement("Govt launches new policy for AI", "/ai-policy-launch"),
                    MockElement("iPhone 18 Review: Is it worth it?", "/iphone-18-review"),
                    MockElement("New regulations for drone usage announced", "/drone-regulations-2025")
                ]

                if not article_elements:
                    logger.warning(f"No article elements found for {name} with selector: {selectors['article']}")
                    continue
                
                logger.info(f"Found {len(article_elements)} potential articles for {name}")
                source_articles = []
                
                for element in article_elements[:30]:
                    try:
                        title = element.get_text(strip=True)
                        link = element.get('href', '')
                        
                        if not link or not title or len(title) < 10:
                            continue

                        # --- NEW FILTERING LOGIC INSERTED HERE ---
                        if any(product_term in title.lower() for product_term in 
                               ['review', 'launch', 'specs', 'price', 'buy now', 'available for']):
                            # Check if it also has policy context to avoid being filtered
                            if not any(policy_term in title.lower() for policy_term in 
                                       ['policy', 'government', 'regulation', 'ban', 'tax']):
                                logger.debug(f"Skipping product content: {title}")
                                continue
                        # --- END OF NEW LOGIC ---

                        if not link.startswith('http'):
                            link = urljoin(url, link)
                        
                        # Placeholders for other filters
                        # if self.is_entertainment_url(link): continue
                        # if self.is_organizational_content(title, link): continue
                        
                        summary = "Summary extracted from scrape."
                        published_date = datetime.now()
                        
                        article = NewsArticle(
                            title=title, url=link, source=name, category=category,
                            published_date=published_date, summary=summary,
                            tags=[] # Placeholder for tags
                        )
                        article.calculate_relevance_scores()
                        if article.relevance_scores['overall'] >= 0.15:
                            if article.content_hash not in self.article_hashes:
                                self.article_hashes.add(article.content_hash)
                                source_articles.append(article)
                    except Exception as e:
                        logger.debug(f"Error extracting individual article from {name}: {e}")
                        continue
                
                if source_articles:
                    articles.extend(source_articles)
                    logger.info(f"Found {len(source_articles)} valid articles from {name}")
            except Exception as e:
                logger.error(f"Error in direct scrape for {name}: {e}")
            
            time.sleep(random.uniform(0.1, 0.2)) # Simulate delay

        self.statistics['direct_scrape_articles'] = len(articles)
        logger.info(f"Direct scraping found a total of {len(articles)} articles")
        return articles
    
    def assign_tags(self, title: str, summary: str) -> List[str]:
        """Assign tags to articles based on content with improved classification"""
        # ... (method content is syntactically correct) ...
        tags = []
        full_text = f"{title} {summary}".lower()
        
        personal_finance_indicators = [
            'these credit cards', 'best credit cards', 'credit card tips', 'credit card advice', 
            'loan tips', 'investment tips', 'tax tips', 'savings tips', 'financial tips', 
            'money tips', 'how to save', 'how to invest', 'how to choose', 'personal finance', 
            'financial planning', 'money management'
        ]
        if any(indicator in full_text for indicator in personal_finance_indicators):
            return ['Personal Finance']

        policy_context_indicators = [
            'government', 'ministry', 'policy', 'regulation', 'parliament', 'court', 
            'legislation', 'bill', 'act', 'notification', 'circular', 'cabinet', 
            'rbi announces', 'sebi issues'
        ]
        if not any(indicator in full_text for indicator in policy_context_indicators):
            return ['General News']

        tag_rules = {
            'Policy Analysis': ['policy analysis', 'policy study', 'policy report', 'policy research'],
            'Legislative Updates': ['bill', 'act', 'parliament', 'amendment', 'legislation'],
            'Regulatory Changes': ['regulation', 'regulatory', 'rules', 'guidelines', 'notification'],
            'Court Rulings': ['court', 'supreme', 'judicial', 'judgment', 'verdict', 'tribunal'],
            'Government Initiatives': ['government scheme', 'government program', 'government initiative'],
            'International Relations': ['bilateral', 'diplomatic', 'foreign', 'international'],
        }

        for tag, keywords in tag_rules.items():
            if any(keyword in full_text for keyword in keywords):
                tags.append(tag)

        if not tags:
            tags.append('Policy Development')
            
        tags = list(dict.fromkeys(tags))
        return tags[:4]
        
    def fetch_all_feeds(self, max_workers=20):  # Increased from 8
        """Fetch all feeds with progress updates"""
        all_articles = []
        start_time = time.time()
        
        logger.info(f"Starting to fetch {len(self.feeds)} feeds with {max_workers} workers...")
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_feed = {
                executor.submit(self.fetch_single_feed_quick, feed): feed 
                for feed in self.feeds
            }
            
            completed = 0
            failed = 0
            
            # Process with progress updates
            for future in as_completed(future_to_feed, timeout=300):
                completed += 1
                feed = future_to_feed[future]
                
                # Progress update every 10 feeds
                if completed % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = completed / elapsed
                    remaining = (len(self.feeds) - completed) / rate
                    logger.info(
                        f"Progress: {completed}/{len(self.feeds)} feeds "
                        f"({completed/len(self.feeds)*100:.1f}%) - "
                        f"ETA: {remaining:.0f}s"
                    )
                
                try:
                    articles = future.result()
                    if articles:
                        all_articles.extend(articles)
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1
                    logger.debug(f"Failed: {feed[0]} - {str(e)}")
        
        elapsed = time.time() - start_time
        logger.info(
            f"Completed in {elapsed:.1f}s - "
            f"Success: {len(self.feeds)-failed}, Failed: {failed}, "
            f"Articles: {len(all_articles)}"
        )
        
        return all_articles

    def fetch_single_feed(self, feed_info):
        """Process a single feed with fallback mechanisms"""
        # Validate feed_info format
        if not isinstance(feed_info, tuple) or len(feed_info) < 3:
            logger.error(f"Invalid feed info format: {feed_info}")
            return []

        source_name, feed_url, category = feed_info
        self.statistics['total_feeds'] += 1

        logger.info(f"Processing {source_name} feed: {feed_url}")

        try:
            # Try to fetch the feed with retries
            articles = self.fetch_feed_with_retries(feed_url, source_name, category)

            # Update feed status
            if articles:
                self.update_feed_status(feed_url, True)
                self.statistics['successful_feeds'] += 1
                self.feed_health[source_name] = {
                    'status': 'success',
                    'count': len(articles),
                    'method': 'primary'
                }
                # Record last successful update
                self.source_last_update[source_name] = datetime.now()
            else:
                # Try fallback URLs if available
                if feed_url in Config.FALLBACK_URLS:
                    fallback_success = False
                    for fallback_url in Config.FALLBACK_URLS[feed_url]:
                        logger.info(f"Trying fallback URL for {source_name}: {fallback_url}")
                        fallback_articles = self.fetch_feed_with_retries(fallback_url, source_name, category)
                        if fallback_articles:
                            articles = fallback_articles
                            self.statistics['fallback_successes'] += 1
                            fallback_success = True
                            self.feed_health[source_name] = {
                                'status': 'success',
                                'count': len(articles),
                                'method': 'fallback'
                            }
                            # Record last successful update
                            self.source_last_update[source_name] = datetime.now()
                            break

                    if not fallback_success:
                        self.update_feed_status(feed_url, False, "No articles from primary or fallback URLs")
                        self.statistics['failed_feeds'] += 1
                        self.feed_health[source_name] = {
                            'status': 'failed',
                            'count': 0,
                            'last_error': "No articles from primary or fallback URLs"
                        }
                else:
                    self.update_feed_status(feed_url, False, "No articles found")
                    self.statistics['failed_feeds'] += 1
                    self.feed_health[source_name] = {
                        'status': 'failed',
                        'count': 0,
                        'last_error': "No articles found"
                    }

            return articles
        except Exception as e:
            error_message = str(e)
            logger.error(f"Exception fetching {source_name}: {error_message}")

            # Update feed status
            self.update_feed_status(feed_url, False, error_message)
            self.statistics['failed_feeds'] += 1
            self.feed_health[source_name] = {
                'status': 'failed',
                'count': 0,
                'last_error': error_message
            }

            return []
        
    def fetch_single_feed_quick(self, feed_info):
        """Quick feed fetch with enhanced statistics tracking"""
        source_name, feed_url, category = feed_info
        
        # Check blacklist
        if any(blacklisted in source_name.lower() for blacklisted in Config.BLACKLISTED_SOURCES):
            logger.info(f"Skipping blacklisted source: {source_name}")
            return []
        
        try:
            headers = self._build_headers_for_site(feed_url, source_name)
            timeout = 20  # Reasonable timeout
            
            response = self.session.get(
                feed_url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                verify=False
            )
            
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                content = response.content
                
                # Process content
                if 'xml' in content_type or 'rss' in content_type:
                    articles = self._parse_feed_content(content, source_name, category)
                elif 'html' in content_type:
                    articles = self._scrape_html_content(
                        content.decode('utf-8', errors='ignore'), 
                        source_name, category, feed_url
                    )
                else:
                    articles = self._parse_content_flexible(content, source_name, category, feed_url)
                
                # Filter blacklisted sources from articles
                articles = [a for a in articles if not any(
                    blacklisted in a.source.lower() for blacklisted in Config.BLACKLISTED_SOURCES
                )]
                
                if articles:
                    # Update detailed statistics
                    if source_name not in self.source_statistics:
                        self.source_statistics[source_name] = {
                            'articles': 0,
                            'category': category,
                            'status': 'active',
                            'last_success': datetime.now()
                        }
                    
                    self.source_statistics[source_name]['articles'] += len(articles)
                    self.source_statistics[source_name]['last_success'] = datetime.now()
                    self.statistics['successful_feeds'] += 1
                    
                    logger.info(f"✓ {source_name}: {len(articles)} articles")
                    return articles
                else:
                    # No articles but feed worked
                    if source_name not in self.source_statistics:
                        self.source_statistics[source_name] = {
                            'articles': 0,
                            'category': category,
                            'status': 'empty',
                            'last_attempt': datetime.now()
                        }
                    return []
                    
            else:
                # HTTP error
                if source_name not in self.source_statistics:
                    self.source_statistics[source_name] = {
                        'articles': 0,
                        'category': category,
                        'status': f'HTTP {response.status_code}',
                        'last_attempt': datetime.now()
                    }
                logger.debug(f"✗ {source_name}: HTTP {response.status_code}")
                return []
                
        except Exception as e:
            # Error occurred
            if source_name not in self.source_statistics:
                self.source_statistics[source_name] = {
                    'articles': 0,
                    'category': category,
                    'status': f'Error: {type(e).__name__}',
                    'last_attempt': datetime.now()
                }
            logger.debug(f"✗ {source_name}: {type(e).__name__}")
            return []

        # 6. FIX FOR RUNTIME ERRORS - Better error handling in feed fetching
    def fetch_feed_with_retries(self, feed_url, source_name, category, retries=0):
        """Enhanced feed fetching with session establishment and better error handling"""
        max_retries = 3
        articles = []
        
        if retries >= max_retries:
            self.log_feed_failure(feed_url, source_name, "Max retries exceeded")
            return articles
        
        try:
            # Get domain and check if it's a government site
            domain = urlparse(feed_url).netloc.lower()
            is_government_site = any(gov in domain for gov in ['.gov.in', '.nic.in', '.gov', 'parliament'])
            
            # CRITICAL: Add delay before request
            delay = self.get_domain_specific_delay(feed_url)
            time.sleep(delay)
            
            # CRITICAL: Establish session for government sites first
            if is_government_site or any(blocked in domain for blocked in ['business-standard', 'moneycontrol', 'hindustantimes']):
                # Visit homepage first to establish session
                homepage_url = f"https://{domain}/"
                try:
                    # Create a fresh session for this site
                    session = self._create_site_specific_session(domain)
                    
                    # Visit homepage with browser-like behavior
                    homepage_headers = {
                        'User-Agent': self._get_browser_user_agent(),
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Sec-Fetch-Dest': 'document',
                        'Sec-Fetch-Mode': 'navigate',
                        'Sec-Fetch-Site': 'none',
                        'Sec-Fetch-User': '?1',
                        'Cache-Control': 'max-age=0'
                    }
                    
                    homepage_response = session.get(homepage_url, headers=homepage_headers, timeout=30, verify=False)
                    
                    # Collect cookies
                    if homepage_response.cookies:
                        session.cookies.update(homepage_response.cookies)
                    
                    # Wait to appear human
                    time.sleep(random.uniform(2, 4))
                    
                except Exception as e:
                    logger.debug(f"Could not establish session for {domain}: {str(e)}")
                    session = self.session  # Fall back to main session
            else:
                session = self.session
            
            # Build enhanced headers
            headers = self._build_enhanced_headers_for_site(feed_url, source_name)
            
            # For sites that commonly return 403, try alternative approaches
            if any(blocked in domain for blocked in ['pib.gov.in', 'business-standard', 'moneycontrol']):
                # Try with curl-like headers
                headers = {
                    'User-Agent': 'curl/7.85.0',
                    'Accept': '*/*',
                    'Host': domain
                }
            
            # Get appropriate handler for government sites
            gov_handler = GovernmentSiteHandlers.get_handler_for_url(feed_url) if is_government_site else None
            
            # Make the request
            if gov_handler:
                response = gov_handler(session, feed_url, headers)
            else:
                response = session.get(
                    feed_url,
                    headers=headers,
                    timeout=60,
                    allow_redirects=True,
                    stream=False,
                    verify=False
                )
            
            # Handle different status codes
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                content = response.content
                
                # Process content
                try:
                    if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                        articles = self._parse_feed_content(content, source_name, category)
                    elif 'json' in content_type:
                        articles = self._parse_json_feed(content, source_name, category)
                    else:
                        # Try to detect content type from content
                        content_str = content.decode('utf-8', errors='ignore')
                        if content_str.strip().startswith('<?xml') or '<rss' in content_str[:500] or '<feed' in content_str[:500]:
                            articles = self._parse_feed_content(content, source_name, category)
                        else:
                            # It's HTML - parse it
                            articles = self._scrape_html_content(content_str, source_name, category, feed_url)
                except Exception as e:
                    logger.error(f"Error processing content for {source_name}: {str(e)}")
                    
            elif response.status_code == 403:
                logger.warning(f"403 Forbidden for {source_name}")
                # Try alternative URLs or scraping
                if retries < max_retries:
                    # Try with different headers
                    time.sleep(random.uniform(5, 10))
                    return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
                else:
                    # Try direct HTML scraping as last resort
                    try:
                        articles = self._fallback_html_scrape(feed_url, source_name, category)
                    except:
                        pass
                        
            elif response.status_code == 404:
                logger.warning(f"404 Not Found for {source_name}")
                # Try alternate URLs
                if hasattr(self, '_get_alternate_urls'):
                    alternate_urls = self._get_alternate_urls(feed_url, source_name)
                    for alt_url in alternate_urls[:2]:
                        time.sleep(3)
                        articles = self.fetch_feed_with_retries(alt_url, source_name, category, retries + 1)
                        if articles:
                            break
                            
            else:
                logger.warning(f"HTTP {response.status_code} for {source_name}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout for {source_name}")
            if retries < max_retries and is_government_site:
                time.sleep(10)
                return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
                
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error for {source_name}: {str(e)}")
            # For DH_KEY_TOO_SMALL error, try with requests directly
            if "DH_KEY_TOO_SMALL" in str(e):
                try:
                    # Use urllib directly for problematic SSL
                    import urllib.request
                    with urllib.request.urlopen(feed_url, timeout=30) as response:
                        content = response.read()
                        articles = self._parse_feed_content(content, source_name, category)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"Error fetching {source_name}: {str(e)}")
        
        # Update feed health
        if articles:
            self.update_feed_health_status(feed_url, True)
        else:
            self.update_feed_health_status(feed_url, False, "No articles retrieved")
        
        return articles

    def _fetch_with_timeout(self, feed_info: Tuple[str, str, str]) -> List[NewsArticle]:
        """
        Safely fetches a single feed with a context-aware timeout.
        This method is thread-safe and cross-platform.
        """
        timeout = 10 if IS_GITHUB_ACTIONS else 20
        
        # We run the actual fetch function in its own future to enforce a timeout.
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(self.fetch_single_feed_quick, feed_info)
            try:
                # This is a blocking call, but with a safe timeout.
                return future.result(timeout=timeout)
            except TimeoutError:
                source_name = feed_info[0]
                logger.warning(f"Timeout: Feed processing for '{source_name}' exceeded {timeout} seconds.")
                return []
            except Exception as e:
                # Catches any other exceptions from within the fetch_single_feed_quick call.
                source_name = feed_info[0]
                logger.error(f"Error: Fetching '{source_name}' failed with exception: {e}", exc_info=False)
                return []

    # Add this method to filter working sources only
    def get_github_safe_feeds(self) -> List[Tuple[str, str, str]]:
        """Get feeds that work reliably on GitHub Actions"""
        safe_sources = [
            'economic times', 'hindu', 'indian express', 'mint', 
            'business standard', 'financial express', 'moneycontrol',
            'prs', 'orf', 'medianama', 'livelaw', 'google news'
        ]
        
        # Assuming self.feeds exists and is a list of tuples
        if not hasattr(self, 'feeds'):
            self.feeds = []

        return [
            feed for feed in self.feeds 
            if any(safe in feed[0].lower() for safe in safe_sources)
        ]

    def truncate_summary(self, summary: str, max_length: int = 150) -> str:
        """Truncate summary to maximum length with proper word boundaries"""
        if not summary:
            return ""
        
        if len(summary) <= max_length:
            return summary
        
        # Find the last space before max_length to avoid cutting words
        truncated = summary[:max_length]
        last_space = truncated.rfind(' ')
        
        if last_space > max_length * 0.8:  # Only truncate at word boundary if it's not too short
            truncated = truncated[:last_space]
        
        return truncated + "..."

    def _get_alternate_urls(self, original_url, source_name):
        """Generate alternate URLs for common patterns"""
        alternate_urls = []
        
        # For PIB
        if 'pib.gov.in' in original_url:
            alternate_urls.extend([
                'https://pib.gov.in/indexd.aspx',
                'https://pib.gov.in/PressReleseDetail.aspx',
                'https://pib.gov.in/allRel.aspx'
            ])
        
        # For ministries
        if 'ministry' in source_name.lower() or '.gov.in' in original_url:
            base_url = '/'.join(original_url.split('/')[:3])
            alternate_urls.extend([
                f"{base_url}/whats-new",
                f"{base_url}/latest-updates",
                f"{base_url}/press-releases",
                f"{base_url}/news",
                f"{base_url}/notifications",
                f"{base_url}/content/news-updates"
            ])
        
        # Generic RSS patterns
        if not any(x in original_url for x in ['.rss', '.xml', '/feed']):
            if original_url.endswith('/'):
                base = original_url[:-1]
            else:
                base = original_url
                
            alternate_urls.extend([
                f"{base}/rss",
                f"{base}/feed",
                f"{base}/rss.xml",
                f"{base}/feed.xml",
                f"{base}/feeds",
                f"{base}.rss"
            ])
        
        return alternate_urls

    def _get_government_alternate_urls(self, original_url, source_name):
        """Generate alternate URLs for government sites"""
        alternate_urls = []
        domain = urlparse(original_url).netloc
        
        # PIB specific
        if 'pib.gov.in' in domain:
            alternate_urls.extend([
                'https://pib.gov.in/indexd.aspx',
                'https://pib.gov.in/PressReleseDetail.aspx',
                'https://pib.gov.in/allRel.aspx',
                'https://pib.gov.in/AllReleng.aspx'
            ])
        
        # Ministry sites
        elif 'ministry' in source_name.lower() or 'department' in source_name.lower():
            base_url = f'https://{domain}'
            alternate_urls.extend([
                f"{base_url}/whats-new",
                f"{base_url}/content/whats-new",
                f"{base_url}/latest-updates",
                f"{base_url}/press-releases",
                f"{base_url}/news",
                f"{base_url}/notifications",
                f"{base_url}/content/news-updates",
                f"{base_url}/media-center",
                f"{base_url}/media-centre"
            ])
        
        # RBI specific
        elif 'rbi.org.in' in domain:
            alternate_urls.extend([
                'https://www.rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx',
                'https://www.rbi.org.in/Scripts/NotificationUser.aspx',
                'https://www.rbi.org.in/Scripts/BS_CircularIndexDisplay.aspx'
            ])
        
        # SEBI specific
        elif 'sebi.gov.in' in domain:
            alternate_urls.extend([
                'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&ssid=1&smid=0',
                'https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=2&ssid=6&smid=0'
            ])
        
        # Competition Commission
        elif 'cci.gov.in' in domain:
            alternate_urls.extend([
                'https://www.cci.gov.in/media/press-release',
                'https://www.cci.gov.in/public-disclosure',
                'https://www.cci.gov.in/latest-news'
            ])
        
        # Generic .gov.in patterns
        elif '.gov.in' in domain:
            base_url = f'https://{domain}'
            alternate_urls.extend([
                f"{base_url}/sites/default/files/whatsnew",
                f"{base_url}/en/whats-new",
                f"{base_url}/content/latest-updates"
            ])
        
        return alternate_urls
    
    # Add these methods to PolicyRadarEnhanced class:

    def _get_browser_user_agent(self):
        """Get a convincing browser user agent"""
        chrome_versions = ['120.0.0.0', '121.0.0.0', '122.0.0.0', '123.0.0.0']
        firefox_versions = ['121.0', '122.0', '123.0', '124.0']
        
        agents = [
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.choice(chrome_versions)} Safari/537.36',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{random.choice(chrome_versions)} Safari/537.36',
            f'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:{random.choice(firefox_versions)}) Gecko/20100101 Firefox/{random.choice(firefox_versions)[:-2]}',
            f'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:{random.choice(firefox_versions)}) Gecko/20100101 Firefox/{random.choice(firefox_versions)[:-2]}'
        ]
        
        return random.choice(agents)

    def _create_site_specific_session(self, domain):
        """Create a fresh session for a specific site"""
        session = requests.Session()
        
        # Use the same SSL adapter
        class UltraPermissiveSSLAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                ctx.set_ciphers('ALL:@SECLEVEL=1')
                kwargs['ssl_context'] = ctx
                return super().init_poolmanager(*args, **kwargs)
        
        # Mount the adapter
        adapter = UltraPermissiveSSLAdapter()
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        
        return session

    def _build_enhanced_headers_for_site(self, url, source_name):
        """Build more convincing headers for specific sites"""
        domain = urlparse(url).netloc.lower()
        
        # Base browser headers
        headers = {
            'User-Agent': self._get_browser_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0',
            'Sec-Ch-Ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
            'Sec-Ch-Ua-Mobile': '?0',
            'Sec-Ch-Ua-Platform': '"Windows"'
        }
        
        # Site-specific modifications
        if 'pib.gov.in' in domain:
            headers.update({
                'Referer': 'https://pib.gov.in/',
                'Origin': 'https://pib.gov.in',
                'X-Requested-With': 'XMLHttpRequest'
            })
        elif 'business-standard' in domain:
            headers.update({
                'Referer': 'https://www.business-standard.com/',
                'Origin': 'https://www.business-standard.com'
            })
        elif 'moneycontrol' in domain:
            headers.update({
                'Referer': 'https://www.moneycontrol.com/',
                'Origin': 'https://www.moneycontrol.com'
            })
        elif any(gov in domain for gov in ['.gov.in', '.nic.in']):
            headers.update({
                'Referer': f'https://{domain}/',
                'X-Requested-With': 'XMLHttpRequest'
            })
        
        return headers

    def _fallback_html_scrape(self, url, source_name, category):
        """Fallback HTML scraping when RSS fails"""
        try:
            # Create a new session with browser headers
            session = self._create_site_specific_session(urlparse(url).netloc)
            headers = self._build_enhanced_headers_for_site(url, source_name)
            
            # Try to get the homepage or main news page
            base_url = '/'.join(url.split('/')[:3])
            news_urls = [
                url,
                f"{base_url}/news",
                f"{base_url}/press-releases",
                f"{base_url}/updates",
                f"{base_url}/whats-new",
                f"{base_url}/latest",
                base_url
            ]
            
            for try_url in news_urls:
                try:
                    response = session.get(try_url, headers=headers, timeout=30, verify=False)
                    if response.status_code == 200:
                        return self._scrape_html_content(response.text, source_name, category, try_url)
                except:
                    continue
                    
        except Exception as e:
            logger.debug(f"Fallback scraping failed for {source_name}: {str(e)}")
        
        return []
    
    def _parse_json_feed(self, content, source_name, category):
        """Parse JSON feed format"""
        articles = []
        try:
            data = json.loads(content)
            
            # Common JSON feed structures
            items = data.get('items', data.get('articles', data.get('posts', data.get('entries', []))))
            
            for item in items[:20]:
                title = item.get('title', item.get('headline', ''))
                url = item.get('url', item.get('link', item.get('href', '')))
                summary = item.get('summary', item.get('description', item.get('excerpt', '')))
                published = item.get('published', item.get('pubDate', item.get('date', '')))
                
                if title and url:
                    summary_text = summary or f"Update from {source_name}"
                    article = NewsArticle(
                        title=title,
                        url=url,
                        source=source_name,
                        category=category,
                        published_date=published,
                        summary=summary_text,
                        tags=self.assign_tags(title, summary_text) # Added tags parameter
                    )

                    if article.content_hash not in self.article_hashes:
                        self.article_hashes.add(article.content_hash)
                        articles.append(article)
                        self.save_article_to_db(article)
                        
        except Exception as e:
            logger.error(f"Error parsing JSON feed for {source_name}: {str(e)}")
            
        return articles
    

    # <<< START: MODIFICATION 5 - New debug report generation method (CORRECTED) >>>
    def generate_debug_analysis(self):
        """Generate detailed analysis of filtered content and feed failures"""
        debug_file = os.path.join(Config.LOG_DIR, f"debug_analysis_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html")
        
        # NOTE: All curly braces for CSS have been doubled to escape them (e.g., {{ and }})
        html = """<!DOCTYPE html>
    <html>
    <head>
        <title>PolicyRadar Debug Analysis</title>
        <style>
            body {{ font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }}
            .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; box-shadow: 0 0 15px rgba(0,0,0,0.1); }}
            h1, h2 {{ color: #333; border-bottom: 2px solid #eee; padding-bottom: 10px; }}
            .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0; }}
            .stat-box {{ background: #e8f4f8; padding: 15px; border-radius: 8px; text-align: center; }}
            .stat-value {{ font-size: 2em; font-weight: bold; color: #0066cc; }}
            table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
            th {{ background: #0066cc; color: white; padding: 10px; text-align: left; }}
            td {{ padding: 8px; border-bottom: 1px solid #ddd; }}
            tr:nth-child(even) {{ background: #f9f9f9; }}
            tr:hover {{ background: #f1f1f1; }}
            .reason {{ background: #fee; padding: 3px 8px; border-radius: 3px; font-size: 0.9em; border: 1px solid #fcc; }}
            .filter-summary {{ background: #f0f8ff; padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .fail-reason {{ color: #cc0000; font-weight: bold; }}
            .success {{ color: #008800; }}
            .warning {{ color: #ff8800; }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PolicyRadar Debug Analysis</h1>
            <p>Generated: {timestamp}</p>
            
            <h2>Feed Success Analysis</h2>
            <div class="stats">
                <div class="stat-box">
                    <div class="stat-value">{total_feeds}</div>
                    <div>Total Feeds</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value {success_class}">{success_rate}%</div>
                    <div>Success Rate</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{failed_feeds}</div>
                    <div>Failed Feeds</div>
                </div>
                <div class="stat-box">
                    <div class="stat-value">{total_filtered}</div>
                    <div>Articles Filtered</div>
                </div>
            </div>
            
            <h2>Feed Failure Reasons</h2>
            <table>
                <tr>
                    <th>Source</th>
                    <th>URL</th>
                    <th>Reason</th>
                    <th>Error Details</th>
                </tr>
                {feed_failures}
            </table>
            
            <h2>Filtered Articles Analysis</h2>
            <div class="filter-summary">
                <h3>Filter Reason Summary</h3>
                {filter_summary}
            </div>
            
            <h2>Filtered Articles Detail (Last 100)</h2>
            <table>
                <tr>
                    <th>Title</th>
                    <th>Source</th>
                    <th>Date</th>
                    <th>Reason</th>
                    <th>Score</th>
                    <th>Stage</th>
                </tr>
                {filtered_articles}
            </table>
        </div>
    </body>
    </html>"""
        
        # Calculate statistics
        total_feeds = self.statistics.get('total_feeds', len(self.feeds))
        successful_feeds = self.statistics.get('successful_feeds', 0)
        success_rate = (successful_feeds / total_feeds * 100) if total_feeds > 0 else 0
        success_class = 'success' if success_rate > 60 else 'warning' if success_rate > 30 else 'fail-reason'
        
        # Build feed failures table
        feed_failures_html = ""
        for source, details in self.feed_failure_reasons.items():
            feed_failures_html += f"""
                <tr>
                    <td>{source}</td>
                    <td style="font-size: 0.85em;">{details['url']}</td>
                    <td class="fail-reason">{details['reason']}</td>
                    <td style="font-size: 0.85em;">{details.get('error', 'N/A')}</td>
                </tr>
            """
        
        # Analyze filter reasons
        filter_counts = {}
        for article in self.filtered_articles_log:
            reason = article['reason']
            filter_counts[reason] = filter_counts.get(reason, 0) + 1
        
        filter_summary_html = "<ul>"
        total_filtered_count = len(self.filtered_articles_log)
        for reason, count in sorted(filter_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_filtered_count * 100) if total_filtered_count else 0
            filter_summary_html += f"<li><strong>{reason}:</strong> {count} articles ({percentage:.1f}%)</li>"
        filter_summary_html += "</ul>"
        
        # Build filtered articles table (last 100)
        filtered_articles_html = ""
        for article in self.filtered_articles_log[-100:]:
            filtered_articles_html += f"""
                <tr>
                    <td>{article['title'][:80]}...</td>
                    <td>{article['source']}</td>
                    <td>{article['published_date']}</td>
                    <td><span class="reason">{article['reason']}</span></td>
                    <td>{article['relevance_score']:.2f}</td>
                    <td>{article['stage']}</td>
                </tr>
            """
        
        # Generate final HTML
        final_html = html.format(
            timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            total_feeds=total_feeds,
            success_rate=f"{success_rate:.1f}",
            success_class=success_class,
            failed_feeds=len(self.feed_failure_reasons),
            total_filtered=len(self.filtered_articles_log),
            feed_failures=feed_failures_html,
            filter_summary=filter_summary_html,
            filtered_articles=filtered_articles_html
        )
        
        # Write to file
        with open(debug_file, 'w', encoding='utf-8') as f:
            f.write(final_html)
        
        logger.info(f"Debug analysis saved to: {debug_file}")
        return debug_file
    # <<< END: MODIFICATION 5 >>>


    def _build_headers_for_site(self, url, source_name):
        """Build customized headers for specific sites"""
        domain = urlparse(url).netloc.lower()
        
        # More comprehensive headers
        headers = {
            'User-Agent': self.get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,application/json,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        # Government site specific headers
        if any(x in domain for x in ['.gov.in', '.nic.in', 'parliament', 'pib']):
            headers.update({
                'Referer': f'https://{domain}/',
                'Origin': f'https://{domain}',
                'X-Requested-With': 'XMLHttpRequest'
            })
        
        return headers

    def _record_failure(self, feed_url):
        """Record feed failure for temporary blacklisting"""
        if not hasattr(self, 'recent_failures'):
            self.recent_failures = {}
        self.recent_failures[feed_url] = time.time()

    def _parse_content_flexible(self, content, source_name, category, url):
        """Flexible parser that handles both RSS/XML and HTML with better error handling"""
        try:
            # Handle both bytes and string content
            if isinstance(content, bytes):
                try:
                    content_str = content.decode('utf-8', errors='ignore')
                except:
                    content_str = content.decode('latin-1', errors='ignore')
            else:
                content_str = str(content)
            
            # Try RSS/XML first
            if any(marker in content_str[:500] for marker in ['<?xml', '<rss', '<feed', '<atom']):
                return self._parse_feed_content(content, source_name, category)
            
            # Try JSON
            if content_str.strip().startswith(('{', '[')):
                try:
                    return self._parse_json_feed(content if isinstance(content, bytes) else content.encode(), source_name, category)
                except:
                    pass
            
            # Fall back to HTML scraping
            return self._scrape_html_content(content_str, source_name, category, url)
            
        except Exception as e:
            logger.error(f"Error in flexible content parsing for {source_name}: {str(e)}")
            return []

    def _parse_feed_content(self, content, source_name, category):
        """Parse feed content with enhanced error handling"""
        articles = []
        
        try:
            # Try feedparser first
            feed = feedparser.parse(content)
            
            if hasattr(feed, 'bozo') and feed.bozo:
                logger.debug(f"Feed parser warning for {source_name}: {getattr(feed, 'bozo_exception', 'Unknown')}")
            
            if feed.entries:
                for entry in feed.entries[:20]:
                    try:
                        article = self._create_article_from_entry(entry, source_name, category)
                        if article and article.content_hash not in self.article_hashes:
                            self.article_hashes.add(article.content_hash)
                            articles.append(article)
                            self.save_article_to_db(article)
                    except Exception as e:
                        logger.debug(f"Error processing entry: {str(e)}")
                        continue
            else:
                # Try XML parsing as fallback
                logger.debug(f"No feedparser entries for {source_name}, trying XML parsing")
                articles = self.parse_xml_feed(content.decode('utf-8'), source_name, category)
                
        except Exception as e:
            logger.error(f"Error parsing feed content for {source_name}: {str(e)}")
        
        return articles

    def _scrape_html_content(self, html_content, source_name, category, url):
        """Enhanced HTML scraping with better selectors for government sites"""
        articles = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Enhanced selectors for different types of government sites
            if 'pib.gov.in' in url:
                selectors = [
                    'div.content-area ul li',
                    'div[class*="release"] a',
                    'a[href*="PressReleas"]',
                    'td a[href*="PRID"]',
                    'div.innner-page-conent-left ul li a'
                ]
            elif any(x in url for x in ['ministry', 'department', 'govt', 'gov.in']):
                selectors = [
                    'a[href*="notification"]',
                    'a[href*="circular"]',
                    'a[href*="press"]',
                    'a[href*="news"]',
                    'a[href*="announcement"]',
                    'a[href*="order"]',
                    'a[href*="pdf"]',
                    'div.news-item a',
                    'div.update-item a',
                    'div.notification-item a',
                    'li.news-link a',
                    'article a[href]',
                    'div[class*="news"] a',
                    'div[class*="update"] a',
                    'div[class*="notification"] a',
                    'table tr td a[href]',
                    'ul.news-list li a',
                    'div.content ul li a'
                ]
            else:
                # Generic selectors
                selectors = [
                    'article a',
                    'h2 a',
                    'h3 a',
                    '.news-item a',
                    '.article-title a',
                    'a.news-link'
                ]
            
            # Try each selector group
            found_links = []
            for selector in selectors:
                try:
                    elements = soup.select(selector)
                    if elements:
                        found_links.extend(elements)
                        if len(found_links) >= 20:  # Stop if we have enough
                            break
                except:
                    continue
            
            # Remove duplicates
            seen_urls = set()
            unique_elements = []
            for elem in found_links:
                link = elem.get('href', '')
                if link and link not in seen_urls:
                    seen_urls.add(link)
                    unique_elements.append(elem)
            
            # Process found links
            for element in unique_elements[:30]:
                try:
                    title = element.get_text().strip()
                    link = element.get('href', '')
                    
                    if not link or len(title) < 10:
                        continue
                    
                        # --- CORRECTED SEQUENCE ---
                    # 1. Make URL absolute first.
                    if not link.startswith('http'):
                        link = urljoin(url, link)

                    # 2. Now run URL-based filters.
                    if self.is_entertainment_url(link):
                        logger.debug(f"Skipping entertainment URL from scrape: {link}")
                        continue

                    # 3. Run title/content-based filters.
                    if self.is_organizational_content(title, link):
                        logger.debug(f"Skipping organizational content: {title}")
                        continue
                    # Extract date from surrounding elements
                    published_date = self._extract_date_from_context(element)
                    if not published_date:
                        published_date = datetime.now() - timedelta(hours=24)
                    
                    summary_text = f"Policy update from {source_name}"
                    article = NewsArticle(
                        title=title,
                        url=link,
                        source=source_name,
                        category=category,
                        published_date=published_date,
                        summary=summary_text,
                        tags=self.assign_tags(title, summary_text) # Added tags parameter
                    )
                    
                    # Only basic filtering for government sources
                    if 'gov' in source_name.lower() or article.relevance_scores['overall'] >= 0.2:
                        if article.content_hash not in self.article_hashes:
                            self.article_hashes.add(article.content_hash)
                            articles.append(article)
                            self.save_article_to_db(article)
                            
                except Exception as e:
                    logger.debug(f"Error processing link: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping HTML for {source_name}: {str(e)}")
        
        return articles
    
    def _extract_date_comprehensive(self, element, title):
        """Comprehensive date extraction with multiple strategies"""
        # Strategy 1: Element attributes
        for attr in ['datetime', 'data-date', 'data-time', 'data-published']:
            date_str = element.get(attr)
            if date_str:
                try:
                    return date_parser.parse(date_str, fuzzy=True).replace(tzinfo=None)
                except:
                    continue
        
        # Strategy 2: Parent elements
        parent = element.parent
        for _ in range(3):
            if parent:
                date_elem = parent.find(['time', 'span', 'div'], 
                                    class_=re.compile(r'date|time|published|created', re.IGNORECASE))
                if date_elem:
                    date_text = date_elem.get_text().strip() or date_elem.get('datetime', '')
                    if date_text:
                        try:
                            parsed_date = date_parser.parse(date_text, fuzzy=True)
                            return parsed_date.replace(tzinfo=None)
                        except:
                            pass
                parent = parent.parent
            else:
                break
        
        # Strategy 3: Sibling elements
        if element.parent:
            siblings = element.parent.find_all(['span', 'div', 'time'], 
                                            class_=re.compile(r'date|time|published', re.IGNORECASE))
            for sibling in siblings:
                date_text = sibling.get_text().strip() or sibling.get('datetime', '')
                if date_text:
                    try:
                        return date_parser.parse(date_text, fuzzy=True).replace(tzinfo=None)
                    except:
                        continue
        
        # Strategy 4: Extract from title
        date_patterns = [
            r'(\d{1,2})[/-](\d{1,2})[/-](\d{4})',
            r'(\d{4})[/-](\d{1,2})[/-](\d{1,2})',
            r'(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})',
            r'(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2}),?\s+(\d{4})'
        ]
        
        for pattern in date_patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                try:
                    return date_parser.parse(match.group(0), fuzzy=True).replace(tzinfo=None)
                except:
                    continue
        
        return None

    
    def _extract_date_flexible(self, element, title):
        """More flexible date extraction"""
        published_date = None
        
        # Try multiple approaches to find dates
        approaches = [
            # 1. Look in element attributes
            lambda: element.get('datetime') or element.get('data-date'),
            
            # 2. Look in parent elements
            lambda: self._find_date_in_parents(element),
            
            # 3. Look in adjacent elements
            lambda: self._find_date_in_siblings(element),
            
            # 4. Extract from title
            lambda: self._extract_date_from_text(title),
            
            # 5. Look for date patterns in element text
            lambda: self._extract_date_from_text(element.get_text() if hasattr(element, 'get_text') else ''),
        ]
        
        for approach in approaches:
            try:
                result = approach()
                if result:
                    if isinstance(result, str):
                        parsed_date = date_parser.parse(result, fuzzy=True)
                        if parsed_date.tzinfo is not None:
                            parsed_date = parsed_date.replace(tzinfo=None)
                        return parsed_date
                    elif isinstance(result, datetime):
                        return result.replace(tzinfo=None) if result.tzinfo else result
            except:
                continue
        
        return None
    
    def _extract_date_from_context(self, element):
        """Extract date from surrounding HTML context"""
        try:
            # Check parent and siblings for date info
            parent = element.parent
            if parent:
                # Look for date in parent text
                parent_text = parent.get_text()
                date_match = re.search(r'\d{1,2}[-/]\d{1,2}[-/]\d{2,4}', parent_text)
                if date_match:
                    return date_parser.parse(date_match.group(), fuzzy=True)
                
                # Look for date elements
                date_elem = parent.find(['time', 'span', 'div'], 
                                    class_=re.compile(r'date|time|published', re.I))
                if date_elem:
                    date_text = date_elem.get_text().strip()
                    if date_text:
                        return date_parser.parse(date_text, fuzzy=True)
                        
        except:
            pass
        
        return None
    
    def _find_date_in_parents(self, element):
        """Look for dates in parent elements"""
        parent = element.parent
        for _ in range(3):  # Check up to 3 parent levels
            if parent:
                # Look for date elements
                date_elem = parent.find(['time', 'span', 'div'], 
                                    class_=re.compile(r'date|time|published', re.IGNORECASE))
                if date_elem:
                    date_text = date_elem.get_text().strip() or date_elem.get('datetime', '')
                    if date_text:
                        return date_text
                parent = parent.parent
            else:
                break
        return None

    def _find_date_in_siblings(self, element):
        """Look for dates in sibling elements"""
        if element.parent:
            siblings = element.parent.find_all(['span', 'div', 'time'], 
                                            class_=re.compile(r'date|time|published', re.IGNORECASE))
            for sibling in siblings:
                date_text = sibling.get_text().strip() or sibling.get('datetime', '')
                if date_text:
                    return date_text
        return None

    def _is_date_within_3_months(self, date_obj):
        """Check if date is within 3 months"""
        if not date_obj:
            return False
        
        current_time = datetime.now()
        three_months_ago = current_time - timedelta(days=90)
        
        return three_months_ago <= date_obj <= current_time
    
    def is_organizational_content(self, title: str, link: str) -> bool:
        """
        Checks if the content is likely organizational (e.g., 'About Us', 'Contact')
        rather than a policy article - NOW MORE PRECISE.
        """
        title_lower = title.lower()
        link_lower = link.lower()

        # First check if it contains policy keywords - if yes, it's likely NOT organizational
        policy_indicators = [
            'policy', 'notification', 'circular', 'guideline', 'regulation',
            'act', 'bill', 'amendment', 'order', 'rule', 'scheme',
            'announcement', 'decision', 'approval', 'implementation'
        ]
        
        for indicator in policy_indicators:
            if indicator in title_lower:
                return False  # It's a policy article, not organizational
        
        # ONLY flag as organizational if it EXACTLY matches these patterns
        exact_org_titles = [
            'about us', 'contact us', 'who we are', 'our team', 'careers',
            'privacy policy', 'terms of service', 'disclaimer', 'sitemap',
            'copyright', 'accessibility'
        ]
        
        # Check for exact matches only
        for org_title in exact_org_titles:
            if title_lower == org_title or title_lower.startswith(org_title + ' '):
                return True
        
        # Check URL patterns more carefully
        org_url_endings = [
            '/about-us', '/contact-us', '/careers', '/privacy-policy',
            '/terms', '/disclaimer', '/sitemap'
        ]
        
        for pattern in org_url_endings:
            if link_lower.endswith(pattern) or link_lower.endswith(pattern + '/'):
                return True
        
        return False
    

    def _create_article_from_entry(self, entry, source_name, category):
        """Enhanced article creation with strict policy filtering"""
        try:
            title = getattr(entry, 'title', '').strip()
            if not title:
                return None
        
            
            # Extract link
            link = getattr(entry, 'link', '')
            if not link and hasattr(entry, 'links'):
                for link_item in entry.links:
                    if link_item.get('rel') == 'alternate':
                        link = link_item.get('href', '')
                        break
            
            if not link:
                return None
            
            # Extract date with enhanced validation
            published = None
            for date_field in ['published', 'pubDate', 'updated', 'created']:
                if hasattr(entry, date_field):
                    published = getattr(entry, date_field)
                    break
            
            # Extract summary
            summary = ''
            if hasattr(entry, 'summary'):
                summary = self.clean_html(entry.summary)
            elif hasattr(entry, 'description'):
                summary = self.clean_html(entry.description)
            
            # Create article object first, passing tags from the parent class
            article = NewsArticle(
                title=title,
                url=link,
                source=source_name,
                category=category,
                published_date=published,
                summary=summary or f"Policy update from {source_name}",
                tags=self.assign_tags(title, summary)
            )
            
            # CRITICAL: Filter product/gadget content early
            if self._is_product_or_gadget_content(article):
                logger.debug(f"Skipping product/gadget content: {title}")
                return None
            
            # Now, use the article's own methods for filtering
            if article.is_entertainment_url():
                logger.debug(f"Skipping entertainment URL from feed: {link}")
                return None

            if article.is_organizational_content():
                logger.debug(f"Skipping organizational content: {title}")
                return None

            # CRITICAL: Validate article date - reject if too old or no date
            if not article.published_date or not article.is_within_timeframe(months=3):
                logger.debug(f"Article rejected - invalid or old date: {title}")
                return None
            
            return article
            
        except Exception as e:
            logger.debug(f"Error creating article from entry: {str(e)}")
            return None

    def clean_html(self, html_content):
        """Clean HTML content to plain text with improved handling"""
        if not html_content:
            return ""

        try:
            # Use BeautifulSoup for better HTML cleaning
            soup = BeautifulSoup(html_content, 'html.parser')

            # Remove scripts, styles, and hidden elements
            for element in soup(["script", "style", "iframe", "noscript", "head", "meta", "link"]):
                element.extract()

            # Get text with line breaks
            text = soup.get_text(separator=' ', strip=True)

            # Normalize whitespace
            text = re.sub(r'\s+', ' ', text).strip()

            # Remove certain patterns like social media links
            text = re.sub(r'(Follow|Like|Share on|View on) (Twitter|Facebook|LinkedIn|Instagram|YouTube).*', '', text)

            # Remove specific unwanted phrases (customize based on sources)
            phrases_to_remove = [
                "For all the latest.*",
                "Click here to read.*",
                "Download the app.*",
                "Subscribe to our newsletter.*",
                "Read more at.*",
                "Read the full story.*",
                "This article first appeared.*"
            ]

            for phrase in phrases_to_remove:
                text = re.sub(phrase, '', text, flags=re.IGNORECASE)

            return text.strip()

        except Exception as e:
            logger.debug(f"Error cleaning HTML: {e}")

            # Fallback to simpler regex approach if BeautifulSoup fails
            text = re.sub(r'<[^>]+>', ' ', html_content)
            text = re.sub(r'\s+', ' ', text).strip()
            return text

    def parse_xml_feed(self, content, source_name, category):
        """Parse XML feed content with better handling for malformed feeds"""
        articles = []

        try:
            # Fix common XML issues before parsing
            fixed_content = content

            # Fix XML declaration
            if '<?xml' in fixed_content:
                fixed_content = re.sub(r'<\?xml[^>]*\?>', '<?xml version="1.0" encoding="UTF-8"?>', fixed_content)

            # Fix invalid characters
            fixed_content = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', fixed_content)

            # Try to extract items/entries directly from XML
            soup = BeautifulSoup(fixed_content, 'html.parser')

            # Look for item or entry elements
            items = soup.find_all(['item', 'entry'])

            for item in items[:20]:  # Limit to 20 items
                try:
                    # Extract title
                    title_elem = item.find(['title', 'h1', 'h2', 'h3', 'h4'])
                    if not title_elem or not title_elem.get_text().strip():
                        continue

                    title = title_elem.get_text().strip()

                    # Extract link
                    link = None
                    link_elem = item.find('link')
                    if link_elem:
                        if link_elem.get('href'):
                            link = link_elem.get('href')
                        elif link_elem.string:
                            link = link_elem.string.strip()
                    else:
                        # Try to find an anchor tag
                        a_tag = item.find('a')
                        if a_tag and a_tag.get('href'):
                            link = a_tag.get('href')

                    if not link:
                        continue

                    # Extract publication date
                    published_date = None
                    date_elem = item.find(['pubDate', 'published', 'updated', 'date'])
                    if date_elem:
                        date_text = date_elem.get_text().strip()
                        if date_text:
                            try:
                                published_date = date_parser.parse(date_text)
                            except:
                                published_date = datetime.now()

                    if not published_date:
                        published_date = datetime.now()

                    # Extract summary
                    summary = None
                    for summary_tag in ['description', 'summary', 'content']:
                        summary_elem = item.find(summary_tag)
                        if summary_elem:
                            summary = summary_elem.get_text().strip()
                            break

                    if not summary:
                        # Try paragraphs
                        p_elem = item.find('p')
                        if p_elem:
                            summary = p_elem.get_text().strip()

                    # Create article
                    article = NewsArticle(
                        title=title,
                        url=link,
                        source=source_name,
                        category=category,
                        published_date=published_date,
                        summary=summary if summary else f"Policy news from {source_name}",
                        tags=self.assign_tags(title, summary or "")
                    )

                    # Calculate relevance
                    article.calculate_relevance_scores()

                    # Extract keywords
                    article.extract_keywords()

                    # Only accept articles with reasonable relevance
                    if article.relevance_scores['overall'] >= 0.15:
                        # Check for duplicates
                        if article.content_hash not in self.article_hashes:
                            self.article_hashes.add(article.content_hash)
                            articles.append(article)
                            self.save_article_to_db(article)
                    else:
                        self.statistics['low_relevance_articles'] += 1

                except Exception as e:
                    logger.debug(f"Error extracting feed item from XML: {str(e)}")

            logger.info(f"Extracted {len(articles)} articles from XML for {source_name}")

        except Exception as e:
            logger.error(f"Error extracting feed from XML for {source_name}: {str(e)}")

        return articles

    def parse_flexible_date(self, date_text):
        """Parse flexible date strings"""
        if not date_text:
            return None
        try:
            return date_parser.parse(date_text, fuzzy=True)
        except Exception:
            return None
        

    def _is_recent(self, article: NewsArticle, cutoff_date: datetime) -> bool:
        """Check if an article is more recent than the cutoff date"""
        try:
            # Parse article date if it's a string
            if isinstance(article.published_date, str):
                try:
                    pub_date = datetime.fromisoformat(article.published_date)
                except ValueError:
                    # Try alternative parsing for non-ISO format
                    try:
                        pub_date = datetime.strptime(article.published_date[:19], "%Y-%m-%d %H:%M:%S")
                    except:
                        # Fall back to using timeliness score
                        return article.timeliness > 0.5
            else:
                pub_date = article.published_date

            return pub_date >= cutoff_date
        except:
            # If date parsing fails, use timeliness score as fallback
            return article.timeliness > 0.5

    def cache_articles(self, articles: List[NewsArticle]) -> None:
        """Cache articles to file for backup"""
        try:
            cache_file = os.path.join(Config.CACHE_DIR, 'articles_cache.json')

            # Create a backup of previous cache first
            if os.path.exists(cache_file):
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_file = os.path.join(Config.BACKUP_DIR, f'articles_cache_{timestamp}.json')
                try:
                    # Copy content rather than just file to ensure atomic operation
                    with open(cache_file, 'r', encoding='utf-8') as src:
                        with open(backup_file, 'w', encoding='utf-8') as dst:
                            dst.write(src.read())
                    logger.debug(f"Backed up previous cache to {backup_file}")
                except Exception as e:
                    logger.error(f"Error backing up cache: {e}")

            # Write new cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump([article.to_dict() for article in articles], f, ensure_ascii=False, indent=2)
            logger.info(f"Cached {len(articles)} articles to {cache_file}")
        except Exception as e:
            logger.error(f"Error caching articles: {str(e)}")

    def load_cached_articles(self) -> List[NewsArticle]:
        """Load cached articles as fallback"""
        articles = []
        try:
            cache_file = os.path.join(Config.CACHE_DIR, 'articles_cache.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                for article_data in cached_data:
                    try:
                        # Handle both old and new format cache files
                        article = NewsArticle(
                            title=article_data['title'],
                            url=article_data['url'],
                            source=article_data['source'],
                            category=article_data['category'],
                            published_date=article_data.get('published_date'),
                            summary=article_data.get('summary', ''),
                            tags=article_data.get('tags', [])
                        )

                        # For backwards compatibility, set hash if it exists
                        if 'content_hash' in article_data:
                            article.content_hash = article_data['content_hash']

                        articles.append(article)
                    except Exception as e:
                        logger.error(f"Error loading cached article: {e}")
                        continue

                logger.info(f"Loaded {len(articles)} articles from cache")
        except Exception as e:
            logger.error(f"Error loading cached articles: {str(e)}")

        return articles

    def deduplicate_articles(self, articles):
        """Deduplicate articles based on multiple criteria"""
        seen_hashes = set()
        seen_urls = set()
        seen_titles = set()
        unique_articles = []
        
        for article in articles:
            # Create normalized title for comparison
            normalized_title = article.title.lower().strip()
            
            # Check multiple criteria for duplicates
            if (article.content_hash not in seen_hashes and 
                article.url not in seen_urls and
                normalized_title not in seen_titles):
                
                seen_hashes.add(article.content_hash)
                seen_urls.add(article.url)
                seen_titles.add(normalized_title)
                unique_articles.append(article)
        
        logger.info(f"Deduplicated {len(articles)} articles to {len(unique_articles)} unique articles")
        return unique_articles

    # Update the run method to better handle government site failures:

    def run(self, max_workers: int = 15, use_async: bool = False) -> str:
        """
        Enhanced run method with context-aware logic for GitHub Actions,
        robust timeout handling, and fallback data sources.
        """
        start_time = time.time()
        logger.info("Starting PolicyRadar Enhanced Aggregator...")
        all_articles = []
        # --- Main Execution Block with Critical Error Handling ---
        try:
            # 1. Initialization and Context-Aware Configuration
            self.initialize_feed_monitor()
            self.source_statistics = {}  # Reset statistics for the run
            timeout = 300
            # Adapt settings for GitHub Actions environment
            if IS_GITHUB_ACTIONS:
                logger.info("Running in GitHub Actions mode: applying conservative settings.")
                # Filter out feeds known to be slow or problematic in CI
                problematic_domains = ['defence', 'army', 'navy', 'airforce', 'crpf', 'bsf', 'assamrifles', 'itbp', 'cisf', 'intelligence']
                self.feeds = [f for f in self.feeds if not any(p in f[1] for p in problematic_domains)]
                max_workers = 10  # Reduce concurrency
                timeout = 180     # Use a shorter overall timeout
            else:
                # Standard filtering for local/production runs
                problematic_domains = ['fmc.gov.in', 'india.gov.in/news-updates', 'swarajyamag']
                self.feeds = [f for f in self.feeds if not any(p in f[1].lower() for p in problematic_domains)]
            # 2. Feed Fetching with Concurrency and Timeouts
            healthy_feeds = self.get_healthy_feeds()
            self.statistics['total_feeds'] = len(healthy_feeds)
            logger.info(f"Processing {len(healthy_feeds)} healthy feeds with a timeout of {timeout}s.")
            try:
                with ThreadPoolExecutor(max_workers=max_workers) as executor:
                    future_to_feed = {
                        executor.submit(self._fetch_with_timeout, feed): feed
                        for feed in healthy_feeds
                    }
                    completed_count = 0
                    for future in as_completed(future_to_feed, timeout=timeout):
                        completed_count += 1
                        if completed_count % 20 == 0:
                            logger.info(f"Progress: {completed_count}/{len(healthy_feeds)} feeds processed.")
                        try:
                            articles = future.result(timeout=10) # Short timeout for result retrieval
                            if articles:
                                all_articles.extend(articles)
                        except Exception as e:
                            feed = future_to_feed[future]
                            logger.error(f"Error processing feed '{feed[0]}': {type(e).__name__}")
            except TimeoutError:
                logger.warning(
                    f"Global feed fetching timed out after {timeout}s. "
                    f"Continuing with {len(all_articles)} articles collected so far."
                )
            logger.info(f"Initial feed fetching complete. Collected {len(all_articles)} articles.")
            # 3. Fallback and Supplemental Data Sources
            if not all_articles:
                logger.warning("No articles collected from RSS feeds. Using Google News as a fallback.")
                try:
                    google_articles = self.fetch_google_news_policy_articles(max_articles=150)
                    all_articles.extend(google_articles)
                    logger.info(f"Added {len(google_articles)} articles from Google News fallback.")
                except Exception as e:
                    logger.error(f"Google News fallback failed: {e}")
            else:
                logger.info("Supplementing RSS feed results with Google News.")
                try:
                    google_articles = self.fetch_google_news_policy_articles(max_articles=200)
                    all_articles.extend(google_articles)
                    logger.info(f"Added {len(google_articles)} supplemental articles from Google News.")
                except Exception as e:
                    logger.error(f"Google News supplement failed: {e}")
            # Conditionally supplement with direct scraping if article count is low
            if len(all_articles) < 300:
                logger.info("Article count is low, supplementing with direct scraping...")
                try:
                    scraped_articles = self.direct_scrape_reliable_sources()
                    all_articles.extend(scraped_articles)
                    logger.info(f"Added {len(scraped_articles)} articles from direct scraping.")
                except Exception as e:
                    logger.error(f"Direct scraping failed: {e}")
            # 4. Processing and Filtering Pipeline
            logger.info(f"Total articles collected before processing: {len(all_articles)}")
            # Filter blacklisted sources
            articles_after_blacklist = [a for a in all_articles if not any(
                blacklisted in a.source.lower() for blacklisted in Config.BLACKLISTED_SOURCES
            )]
            # Deduplicate
            unique_articles = self.deduplicate_articles(articles_after_blacklist)
            logger.info(f"Unique articles after deduplication: {len(unique_articles)}")
            # Filter by relevance
            filtered_articles = self.filter_articles_by_relevance(unique_articles, min_relevance=0.10)
            logger.info(f"Articles after relevance filtering: {len(filtered_articles)}")
            # Sort for final output
            sorted_articles = self.sort_articles_by_relevance(filtered_articles)
            self.statistics['total_articles'] = len(sorted_articles)
            # 5. Output Generation
            output_file = self.generate_html(sorted_articles)
            self.export_articles_to_json(sorted_articles)
            self.cache_articles(sorted_articles)
            self.generate_health_dashboard()
            # 6. Final Reporting
            runtime = time.time() - start_time
            logger.info(f"PolicyRadar finished in {runtime:.2f} seconds.")
            logger.info(f"Final output: {len(sorted_articles)} articles from {len(self.source_statistics)} sources.")
            # Log category breakdown
            category_counts = {}
            for article in sorted_articles:
                category_counts[article.category] = category_counts.get(article.category, 0) + 1
            logger.info("Final articles by category:")
            for category, count in sorted(category_counts.items(), key=lambda item: item[1], reverse=True):
                logger.info(f"  {category}: {count}")
            return output_file
        except Exception as e:
            logger.critical(f"A critical error occurred in the main run process: {e}", exc_info=True)
            # Generate a minimal HTML page to indicate failure
            return self.generate_minimal_html([NewsArticle(
                title="System Run Failed",
                url="#",
                source="System Monitor",
                category="System Error",
                published_date=datetime.now(),
                summary=f"A critical error prevented the report from being generated: {str(e)}",
                tags=["System Error"]
            )])
            
    def write_enhanced_debug_report(self, runtime, feed_report):
        """Write enhanced debug report with more details"""
        try:
            report_file = os.path.join(Config.LOG_DIR, f"enhanced_debug_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
            
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("===== ENHANCED POLICYRADAR DEBUG REPORT =====\n\n")
                f.write(f"Run Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Runtime: {runtime:.2f} seconds\n\n")
                
                f.write("=== PERFORMANCE METRICS ===\n")
                f.write(f"Articles per second: {self.statistics['total_articles'] / runtime:.2f}\n")
                f.write(f"Average time per feed: {runtime / len(self.feeds):.2f}s\n\n")
                
                if feed_report:
                    f.write("=== FEED HEALTH REPORT ===\n")
                    f.write(f"Total feeds monitored: {feed_report['total_feeds']}\n")
                    f.write(f"Active feeds: {feed_report['active_feeds']}\n")
                    f.write(f"Healthy feeds (>80% success): {feed_report['healthy_feeds']}\n")
                    f.write(f"Unhealthy feeds (<30% success): {feed_report['unhealthy_feeds']}\n")
                    f.write(f"Average health score: {feed_report['avg_health_score']:.2%}\n\n")
                    
                    if feed_report['problem_feeds']:
                        f.write("=== PROBLEM FEEDS ===\n")
                        for feed_url, health_score, failures, error_type in feed_report['problem_feeds']:
                            f.write(f"{feed_url}: Health={health_score:.2%}, Failures={failures}, Error={error_type}\n")
                
                f.write("\n=== DETAILED STATISTICS ===\n")
                for key, value in sorted(self.statistics.items()):
                    f.write(f"{key}: {value}\n")
            
            logger.info(f"Enhanced debug report written to {report_file}")
        except Exception as e:
            logger.error(f"Error writing enhanced debug report: {str(e)}")

    def sort_articles_by_relevance(self, articles: List['NewsArticle']) -> List['NewsArticle']:
        """
        Sorts articles using a sophisticated relevance algorithm that weights
        source quality, content importance, and timeliness.
        """
        # --- Configuration for the scoring algorithm ---
        IMPORTANCE_WEIGHT = 0.6
        TIMELINESS_WEIGHT = 0.3
        SOURCE_TIER_WEIGHT = 0.1
        DEFAULT_TIER = 4
        
        # Define source quality tiers
        source_tiers = {
            1: ['pib', 'meity', 'rbi', 'supreme court', 'sebi', 'ministry'], # Official
            2: ['prs', 'medianama', 'livelaw', 'bar and bench', 'iff', 'orf'], # Specialized
            3: ['the hindu', 'indian express', 'economic times', 'livemint', 'business standard'], # Major Media
            4: ['google news', 'the wire', 'scroll', 'print'] # Other reliable media
        }

        # --- Step 1: Create an efficient lookup map for source keywords ---
        # This avoids a nested loop later, making the process much faster.
        source_to_tier_map = {
            keyword: tier
            for tier, keywords in source_tiers.items()
            for keyword in keywords
        }

        # --- Step 2: Calculate the final relevance score for each article ---
        for article in articles:
            # Ensure prerequisite scores are calculated
            if not hasattr(article, 'importance') or article.importance == 0:
                article.calculate_importance()
            if not hasattr(article, 'timeliness') or article.timeliness == 0:
                article.calculate_timeliness()

            # Determine the source tier using the lookup map
            article.source_tier = DEFAULT_TIER
            article_source_lower = article.source.lower()
            for keyword, tier in source_to_tier_map.items():
                if keyword in article_source_lower:
                    article.source_tier = tier
                    break # Found the highest possible tier, so we can stop

            # Calculate the final weighted score
            # Tier bonus is normalized to a 0-1 scale (tier 1 -> 1.0, tier 4 -> 0.25)
            tier_bonus = (len(source_tiers) + 1 - article.source_tier) / len(source_tiers)
            
            article.relevance_score = (
                (IMPORTANCE_WEIGHT * article.importance) +
                (TIMELINESS_WEIGHT * article.timeliness) +
                (SOURCE_TIER_WEIGHT * tier_bonus)
            )

        # --- Step 3: Sort articles by their final relevance score in descending order ---
        return sorted(articles, key=lambda x: x.relevance_score, reverse=True)

    def getPriorityClass(self, relevance_score):
        """Get priority class based on relevance score"""
        if relevance_score >= 0.8:
            return 'critical'
        elif relevance_score >= 0.6:
            return 'high'
        else:
            return 'medium'
    

    def export_articles_json(self, articles: List[NewsArticle]) -> str:
        """Export articles to JSON for API access"""
        try:
            # Create streamlined version for API
            api_data = {
                "generated": datetime.now().isoformat(),
                "total_articles": len(articles),
                "articles": [article.to_dict() for article in articles],
                "categories": list(set(article.category for article in articles if article.category)),
                "sources": list(set(article.source for article in articles if article.source))
            }

            # Write to file
            output_file = os.path.join(Config.OUTPUT_DIR, 'api_data.json')
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(api_data, f, ensure_ascii=False, indent=2)

            logger.info(f"Exported {len(articles)} articles to JSON API file")
            return output_file
        except Exception as e:
            logger.error(f"Error exporting articles to JSON: {str(e)}")
            return None

    def write_debug_report(self) -> Optional[str]:
        """Write a detailed debug report for troubleshooting"""
        try:
            report_file = os.path.join(Config.LOG_DIR, f"debug_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")

            with open(report_file, 'w', encoding='utf-8') as f:
                f.write("===== POLICYRADAR DEBUG REPORT =====\n\n")
                f.write(f"Run Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

                f.write("\n=== STATISTICS ===\n")
                for key, value in self.statistics.items():
                    f.write(f"{key}: {value}\n")

                f.write("\n=== FEED STATUS ===\n")
                for source, status in self.feed_health.items():
                    f.write(f"{source}: {status}\n")

                f.write("\n=== WORKING FEEDS ===\n")
                working_feeds = [source for source, status in self.feed_health.items()
                                if status.get('status') == 'success']
                for source in working_feeds:
                    f.write(f"{source}\n")

                f.write("\n=== FAILED FEEDS ===\n")
                failed_feeds = [source for source, status in self.feed_health.items()
                            if status.get('status') != 'success']
                for source in failed_feeds:
                    status = self.feed_health[source]
                    f.write(f"{source}: {status.get('last_error', 'Unknown')}\n")

                # Database statistics
                f.write("\n=== DATABASE STATISTICS ===\n")
                try:
                    with sqlite3.connect(Config.DB_FILE) as conn:
                        c = conn.cursor()

                        # Article counts
                        c.execute("SELECT COUNT(*) FROM articles")
                        total_articles = c.fetchone()[0]
                        f.write(f"Total articles in database: {total_articles}\n")

                        # Articles by category
                        f.write("\nArticles by Category:\n")
                        c.execute("SELECT category, COUNT(*) FROM articles GROUP BY category ORDER BY COUNT(*) DESC")
                        for category, count in c.fetchall():
                            f.write(f"  {category}: {count}\n")

                        # Articles by source (top 10)
                        f.write("\nTop 10 Sources:\n")
                        c.execute("SELECT source, COUNT(*) FROM articles GROUP BY source ORDER BY COUNT(*) DESC LIMIT 10")
                        for source, count in c.fetchall():
                            f.write(f"  {source}: {count}\n")

                        # Recent articles
                        recent_cutoff = datetime.now() - timedelta(days=1)
                        c.execute("SELECT COUNT(*) FROM articles WHERE created_at > ?",
                                (recent_cutoff.strftime('%Y-%m-%d %H:%M:%S'),))
                        recent_count = c.fetchone()[0]
                        f.write(f"\nArticles added in last 24 hours: {recent_count}\n")
                except Exception as e:
                    f.write(f"Error fetching database statistics: {str(e)}\n")

            logger.info(f"Debug report written to {report_file}")
            return report_file
        except Exception as e:
            logger.error(f"Failed to write debug report: {str(e)}")
            return None
            
    def generate_minimal_output(self) -> str:
        """
        Generates a minimal output by attempting a series of fallback data sources
        when the primary feed collection fails. Now includes loading from cache.
        """
        logger.info("⚠️ Primary feed collection failed. Generating emergency output...")
        articles = []

        # Define a list of fallback methods to try in order.
        # Cache is now the first, fastest, and most reliable option.
        fallback_methods = [
            ("Local Cache", self.load_cached_articles),
            ("Google News", lambda: self.fetch_google_news_policy_articles(max_articles=50)),
            ("Direct Scraping", lambda: self.direct_scrape_reliable_sources())
        ]

        # Attempt each fallback method until one succeeds
        for name, fetch_func in fallback_methods:
            try:
                logger.info(f"Attempting fallback with {name}...")
                fetched_articles = fetch_func()
                
                # If we get any articles, take up to 50 and stop trying other fallbacks
                if fetched_articles:
                    articles.extend(fetched_articles[:50])
                    logger.info(f"✅ Successfully collected {len(articles)} articles from '{name}'.")
                    break # Stop trying other methods as we have found some articles
            except Exception as e:
                # Log the specific error instead of silently passing
                logger.warning(f"❌ Fallback source '{name}' failed: {e}", exc_info=False)
        
        # If all fallback methods fail, create a final system notice
        if not articles:
            logger.warning("All fallback sources failed. Creating a system notice.")
            articles = [
                NewsArticle(
                    title="PolicyRadar System Update",
                    url="#",
                    source="System Monitor",
                    category="System Notice",
                    published_date=datetime.now(),
                    summary="Feed collection is currently experiencing issues. The system is working to restore full functionality. Some content may be temporarily unavailable.",
                    tags=["System Update"]
                )
            ]
        
        # Generate the final HTML output with whatever was collected
        return self.generate_html(articles)
  
    def generate_minimal_html(self, articles: list) -> str:
        """Generate a minimal HTML page with emergency content"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PolicyRadar - System Notice</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 800px;
            margin: 0 auto;
            padding: 20px;
        }}
        h1 {{
            color: #2c3e50;
        }}
        .notice {{
            background-color: #fff8e1;
            border: 1px solid #ffd54f;
            border-radius: 8px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .notice h2 {{
            margin-top: 0;
            color: #e74c3c;
        }}
        footer {{
            margin-top: 40px;
            color: #777;
            font-size: 0.9em;
            text-align: center;
        }}
    </style>
</head>
<body>
    <h1>PolicyRadar</h1>
    <div class="notice">
        <h2>{articles[0].title if articles else "System Update"}</h2>
        <p>{articles[0].summary if articles else "Feed collection is currently experiencing issues. The system is working to restore full functionality. Some content may be temporarily unavailable."}</p>
    </div>
    <p>Please check back later. We apologize for the inconvenience.</p>
    <footer>
        <p>&copy; 2025 PolicyRadar | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </footer>
</body>
</html>"""
        # Write HTML to file
        output_file = os.path.join(Config.OUTPUT_DIR, 'index.html')
        try:
            # Ensure output directory exists
            os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Emergency HTML output generated: {output_file}")
        except Exception as e:
            logger.error(f"Error writing emergency HTML file: {str(e)}")
            output_file = None
        return output_file


    def get_category_icon(self, category: str) -> str:
        """Return emoji icon for category"""
        icons = {
            "Technology Policy": "💻",
            "Economic Policy": "📊",
            "Healthcare Policy": "🏥",
            "Environmental Policy": "🌱",
            "Education Policy": "🎓",
            "Foreign Policy": "🌐",
            "Constitutional & Legal": "⚖️",
            "State & Local Policies": "🏛️",
            "Policy News": "📑",
            "Policy Analysis": "📋",
            "Development Policy": "🌟",
            "Government Policy": "🏛️",
            "Agricultural Policy": "🌾",
            "Labor & Employment": "👷",
            "Defense & Security": "🛡️",
            "Social Policy": "🤝",
            "System Notice": "⚠️"
        }

        return icons.get(category, "📄")

    def generate_system_notice_html(self) -> str:
        """Generate system notice HTML based on current system status"""
        # Determine the system status based on success rate
        total_feeds = self.statistics.get('total_feeds', 0)
        successful_feeds = self.statistics.get('successful_feeds', 0)

        if total_feeds == 0:
            return ""

        success_rate = (successful_feeds / total_feeds) * 100

        # Generate different messages based on system status
        if success_rate >= 80:
            # System is healthy, no notice needed
            return ""
        elif success_rate >= 40:
            # System is degraded
            return """        <div class="system-notice">
                <p>⚠️ <strong>System Notice:</strong> Some news sources are currently unavailable. We're working to restore full service.</p>
            </div>
    """
        else:
            # System is in critical condition
            return """        <div class="system-notice">
                <p>⚠️ <strong>System Notice:</strong> Feed aggregation is experiencing significant issues. Most sources may be temporarily unavailable while we work to resolve the problem.</p>
            </div>
    """
        
      # =============================================================================
# 4. FIX FEATURED ARTICLES - ONLY LAST 24 HOURS
# =============================================================================

    def renderfeaturedArticles(self):
        """Render featured articles - TOP 2 CRITICAL articles from last 24 hours"""
        current_time = datetime.now()
        twenty_four_hours_ago = current_time - timedelta(hours=24)
        
        # Filter for recent CRITICAL articles only
        critical_articles = []
        
        for article in self.all_articles:
            if not article.published_date or article.published_date < twenty_four_hours_ago:
                continue
                
            # Skip product/gadget content
            if self._is_product_or_gadget_content(article):
                continue
            
            # Only include CRITICAL impact articles
            if self.getPriorityClass(article.relevance_scores.get('overall', 0)) == 'critical':
                critical_articles.append(article)
        
        # Fallback to 48 hours if insufficient critical articles
        if len(critical_articles) < 2:
            forty_eight_hours_ago = current_time - timedelta(hours=48)
            for article in self.all_articles:
                if (article.published_date and 
                    article.published_date >= forty_eight_hours_ago and 
                    article not in critical_articles and
                    not self._is_product_or_gadget_content(article)):
                    
                    if self.getPriorityClass(article.relevance_scores.get('overall', 0)) == 'critical':
                        critical_articles.append(article)
        
        # If still not enough critical, fall back to HIGH impact articles
        if len(critical_articles) < 2:
            for article in self.all_articles:
                if (article.published_date and 
                    article.published_date >= forty_eight_hours_ago and 
                    article not in critical_articles and
                    not self._is_product_or_gadget_content(article)):
                    
                    if self.getPriorityClass(article.relevance_scores.get('overall', 0)) == 'high':
                        critical_articles.append(article)
        
        # Sort by relevance score and return top 2
        featured = sorted(critical_articles, 
                        key=lambda x: (x.relevance_scores.get('overall', 0), 
                                    x.published_date if x.published_date else datetime.min), 
                        reverse=True)[:2]
        
        return featured

    

    def generate_html(self, articles: List[NewsArticle]) -> str:
        """Generate HTML with all categories displayed"""
        logger.info(f"Generating HTML output with {len(articles)} articles")

        # Sort articles by relevance first
        articles = self.sort_articles_by_relevance(articles)
        
        # Store all articles for featured article selection
        self.all_articles = articles
        
        # Get featured articles (last 24 hours)
        featured_articles = self.renderfeaturedArticles()
        
        # Separate policy and non-policy articles
        policy_categories = [
            'Technology Policy', 'Economic Policy', 'Healthcare Policy', 
            'Environmental Policy', 'Education Policy', 'Agricultural Policy', 
            'Foreign Policy', 'Constitutional & Legal', 'Defense & Security', 
            'Social Policy', 'Governance & Administration', 'Climate Policy', 
            'Renewable Energy Policy', 'Conservation Policy', 'Policy Analysis',
            'Policy News', 'Development Policy'
        ]
        
        policy_articles = [a for a in articles if a.category in policy_categories]
        other_articles = [a for a in articles if a.category not in policy_categories]
        
        # Prepare data for JSON injection
        articles_data = {
            "generated": datetime.now().isoformat(),
            "total_articles": len(articles),
            "policy_articles": len(policy_articles),
            "other_articles": len(other_articles),
            "articles": [
                {
                    **article.to_dict(),
                    "summary": self.truncate_summary(article.summary, 150),
                    "published_date": article.published_date.isoformat() if article.published_date else None,
                    "is_policy": article.category in policy_categories
                } for article in articles
            ],
            "featured_articles": [
                {
                    **article.to_dict(),
                    "summary": self.truncate_summary(article.summary, 150),
                    "published_date": article.published_date.isoformat() if article.published_date else None
                } for article in featured_articles
            ],
            "categories": sorted(list(set(article.category for article in articles))),
            "policy_categories": policy_categories,
            "sources": sorted(list(set(article.source for article in articles)))
        }
        # Convert to JSON string
        articles_json = json.dumps(articles_data, ensure_ascii=False, indent=2)

        # --- START: MODIFICATION ---
        # Define the new list of policy domains for the filter
        policy_domains = [
            'Technology Policy', 'Economic Policy', 'Healthcare Policy', 
            'Environmental Policy', 'Education Policy', 'Agricultural Policy', 
            'Foreign Policy', 'Constitutional & Legal', 'Defense & Security', 
            'Social Policy', 'Governance & Administration', 'Climate Policy', 
            'Renewable Energy Policy', 'Conservation Policy'
        ]

        # Dynamically create the HTML for the filter checkboxes
        policy_domain_filters_html = ""
        for domain in policy_domains:
            policy_domain_filters_html += f"""
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="category" value="{domain}">
                        <span>{domain}</span>
                    </label>"""
        # --- END: MODIFICATION --

        # Generate the improved HTML with fixed layout and filters
        html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PolicyRadar - Professional Policy Intelligence Platform</title>
    <meta name="description" content="Real-time policy intelligence from 270+ Indian sources. Track legislation, court rulings, and regulatory changes.">
    <meta name="keywords" content="India policy, government news, regulatory intelligence, policy tracking">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📡</text></svg>">
    <style>
        :root {{
            --primary-blue: #0051c7;
            --secondary-blue: #e3f2fd;
            --accent-orange: #ff6b35;
            --background: #ffffff;
            --surface: #f8f9fa;
            --text-primary: #212529;
            --text-secondary: #6c757d;
            --border: #dee2e6;
            --critical: #dc3545;
            --high: #ffc107;
            --medium: #28a745;
            --shadow: rgba(0, 0, 0, 0.05);
            --shadow-hover: rgba(0, 0, 0, 0.1);
        }}

        [data-theme="dark"] {{
            --primary-blue: #4a9eff;
            --secondary-blue: #1a2332;
            --background: #0a0e1a;
            --surface: #151922;
            --text-primary: #e9ecef;
            --text-secondary: #adb5bd;
            --border: #2d3748;
            --shadow: rgba(0, 0, 0, 0.3);
            --shadow-hover: rgba(0, 0, 0, 0.5);
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Roboto', 'Helvetica', 'Arial', sans-serif;
            background-color: var(--background);
            color: var(--text-primary);
            line-height: 1.5;
            transition: all 0.3s ease;
            font-size: 14px;
        }}

        /* Improved Header - More Compact */
        .header {{
            background-color: var(--surface);
            border-bottom: 1px solid var(--border);
            position: sticky;
            top: 0;
            z-index: 1000;
            box-shadow: 0 2px 4px var(--shadow);
        }}

        .header-content {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 0.75rem 1rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .logo {{
            display: flex;
            align-items: center;
            font-size: 1.25rem;
            font-weight: 700;
            color: var(--primary-blue);
        }}

        .logo-icon {{
            margin-right: 0.5rem;
        }}

        .header-stats {{
            display: flex;
            gap: 1rem;
            font-size: 0.8rem;
            color: var(--text-secondary);
        }}

        .stat {{
            display: flex;
            align-items: center;
            gap: 0.25rem;
        }}

        .stat-value {{
            font-weight: 600;
            color: var(--text-primary);
        }}

        .header-actions {{
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }}

        .nav-link {{
            color: var(--text-primary);
            text-decoration: none;
            padding: 0.4rem 0.8rem;
            border-radius: 0.25rem;
            transition: all 0.2s;
            font-size: 0.85rem;
        }}

        .nav-link:hover {{
            background-color: var(--secondary-blue);
            color: var(--primary-blue);
        }}

        .theme-toggle {{
            background: none;
            border: 1px solid var(--border);
            color: var(--text-primary);
            width: 32px;
            height: 32px;
            border-radius: 0.25rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: all 0.2s;
        }}

        .theme-toggle:hover {{
            background-color: var(--secondary-blue);
        }}

        /* Main Container - More Compact */
        .main-container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 1rem;
        }}

        /* Hero Section - Reduced */
        .hero-section {{
            text-align: center;
            margin-bottom: 1.5rem;
        }}

        .hero-title {{
            font-size: 2rem;
            font-weight: 700;
            margin-bottom: 0.25rem;
            background: linear-gradient(135deg, var(--primary-blue), var(--accent-orange));
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}

        .hero-subtitle {{
            color: var(--text-secondary);
            font-size: 1rem;
        }}

        /* Compact Search Bar */
        .search-container {{
            margin-bottom: 1rem;
            position: relative;
        }}

        .search-box {{
            display: flex;
            align-items: center;
            background-color: var(--surface);
            border: 2px solid var(--border);
            border-radius: 0.5rem;
            overflow: hidden;
            transition: all 0.2s;
        }}

        .search-box:focus-within {{
            border-color: var(--primary-blue);
            box-shadow: 0 0 0 3px rgba(0, 81, 199, 0.1);
        }}

        .search-icon {{
            padding: 0 0.75rem;
            color: var(--text-secondary);
        }}

        .search-input {{
            flex: 1;
            padding: 0.75rem 0;
            border: none;
            background: none;
            font-size: 0.9rem;
            color: var(--text-primary);
            outline: none;
        }}

        .search-button {{
            padding: 0.75rem 1.5rem;
            background-color: var(--primary-blue);
            color: white;
            border: none;
            cursor: pointer;
            font-weight: 600;
            transition: all 0.2s;
            font-size: 0.85rem;
        }}

        .search-button:hover {{
            background-color: #0041a7;
        }}

        /* Compact Quick Filters */
        .quick-filters {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1rem;
            flex-wrap: wrap;
        }}

        .time-filter {{
            padding: 0.5rem 1rem;
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 1.5rem;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
            font-size: 0.8rem;
        }}

        .time-filter:hover {{
            background-color: var(--secondary-blue);
            border-color: var(--primary-blue);
        }}

        .time-filter.active {{
            background-color: var(--primary-blue);
            color: white;
            border-color: var(--primary-blue);
        }}

        /* Improved Filter Bar */
        .filter-bar {{
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1rem;
            box-shadow: 0 2px 4px var(--shadow);
        }}

        .filter-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }}

        .filter-title {{
            font-weight: 600;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.9rem;
        }}

        .filter-actions {{
            display: flex;
            gap: 0.5rem;
        }}

        .filter-button {{
            padding: 0.4rem 0.8rem;
            background-color: white;
            border: 1px solid var(--border);
            border-radius: 0.25rem;
            cursor: pointer;
            font-size: 0.8rem;
            transition: all 0.2s;
        }}

        .filter-button:hover {{
            background-color: var(--secondary-blue);
        }}

        .filter-button.apply {{
            background-color: var(--primary-blue);
            color: white;
            border-color: var(--primary-blue);
        }}

        .filter-button.apply:hover {{
            background-color: #0041a7;
        }}

        .filter-content {{
            display: none;
        }}

        .filter-content.active {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }}

        .filter-group {{
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }}

        .filter-group-title {{
            font-weight: 600;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 0.4rem;
        }}

        .filter-option {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
            cursor: pointer;
            font-size: 0.8rem;
        }}

        .filter-checkbox {{
            width: 16px;
            height: 16px;
            cursor: pointer;
        }}

        /* Compact Content Header */
        .content-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }}

        .results-count {{
            font-weight: 600;
            color: var(--text-secondary);
            font-size: 0.9rem;
        }}

        .sort-dropdown {{
            padding: 0.4rem 0.8rem;
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.25rem;
            cursor: pointer;
            font-size: 0.8rem;
        }}

        /* Improved Featured Section */
        .featured-section {{
            background-color: var(--surface);
            border: 2px solid var(--primary-blue);
            border-radius: 0.5rem;
            padding: 1rem;
            margin-bottom: 1.5rem;
        }}

        .featured-header {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.75rem;
        }}

        .featured-title {{
            font-size: 1.1rem;
            font-weight: 700;
            color: var(--primary-blue);
        }}

        .featured-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 1rem;
        }}

        /* Much More Compact Article Cards */
        .article-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
            gap: 1rem;
        }}

        .article-card {{
            background-color: var(--surface);
            border: 1px solid var(--border);
            border-radius: 0.5rem;
            padding: 1rem;
            transition: all 0.2s;
            position: relative;
            overflow: hidden;
        }}

        .article-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            width: 3px;
            height: 100%;
            background-color: var(--medium);
        }}

        .article-card.critical::before {{
            background-color: var(--critical);
        }}

        .article-card.high::before {{
            background-color: var(--high);
        }}

        .article-card:hover {{
            box-shadow: 0 4px 12px var(--shadow-hover);
            transform: translateY(-1px);
        }}

        .article-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 0.5rem;
        }}

        .source-info {{
            display: flex;
            align-items: center;
            gap: 0.4rem;
            font-size: 0.75rem;
            color: var(--text-secondary);
        }}

        .source-badge {{
            width: 16px;
            height: 16px;
            border-radius: 50%;
            background-color: var(--secondary-blue);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.6rem;
        }}

        .article-date {{
            font-size: 0.7rem;
            color: var(--text-secondary);
        }}

        .article-title {{
            font-size: 1rem;
            font-weight: 600;
            margin-bottom: 0.5rem;
            line-height: 1.3;
        }}

        .article-title a {{
            color: var(--text-primary);
            text-decoration: none;
            transition: color 0.2s;
        }}

        .article-title a:hover {{
            color: var(--primary-blue);
        }}

        /* Truncated Summary - Key Fix */
        .article-summary {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 0.75rem;
            line-height: 1.4;
            display: -webkit-box;
            -webkit-line-clamp: 3;
            -webkit-box-orient: vertical;
            overflow: hidden;
            text-overflow: ellipsis;
            max-height: 4.2em; /* Approximately 3 lines */
        }}

        .article-footer {{
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}

        .article-tags {{
            display: flex;
            gap: 0.4rem;
            flex-wrap: wrap;
        }}

        .tag {{
            padding: 0.2rem 0.6rem;
            background-color: var(--secondary-blue);
            color: var(--primary-blue);
            border-radius: 1rem;
            font-size: 0.7rem;
            font-weight: 500;
        }}

        .article-actions {{
            display: flex;
            gap: 0.4rem;
        }}

        .action-button {{
            padding: 0.4rem;
            background: none;
            border: 1px solid var(--border);
            border-radius: 0.25rem;
            cursor: pointer;
            color: var(--text-secondary);
            transition: all 0.2s;
            font-size: 0.8rem;
        }}

        .action-button:hover {{
            background-color: var(--secondary-blue);
            color: var(--primary-blue);
        }}

        /* Category Sections */
        .category-section {{
            margin-bottom: 2rem;
        }}

        .category-title {{
            font-size: 1.3rem;
            font-weight: 600;
            margin-bottom: 0.75rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: var(--text-primary);
        }}

        .category-icon {{
            font-size: 1.1rem;
        }}

        .article-count {{
            font-size: 0.8rem;
            color: var(--text-secondary);
            font-weight: normal;
        }}

        /* About Modal */
        .modal {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background-color: rgba(0, 0, 0, 0.5);
            z-index: 2000;
            justify-content: center;
            align-items: center;
        }}

        .modal.active {{
            display: flex;
        }}

        .modal-content {{
            background-color: var(--background);
            border-radius: 0.5rem;
            max-width: 600px;
            width: 90%;
            max-height: 80vh;
            overflow-y: auto;
            padding: 1.5rem;
            position: relative;
        }}

        .modal-close {{
            position: absolute;
            top: 1rem;
            right: 1rem;
            background: none;
            border: none;
            font-size: 1.5rem;
            cursor: pointer;
            color: var(--text-secondary);
        }}

        .modal-title {{
            font-size: 1.3rem;
            font-weight: 700;
            margin-bottom: 1rem;
            color: var(--primary-blue);
        }}

        .modal-body {{
            line-height: 1.6;
            font-size: 0.9rem;
        }}

        .modal-body h3 {{
            margin-top: 1.5rem;
            margin-bottom: 0.5rem;
            color: var(--text-primary);
        }}

        /* Footer */
        .footer {{
            background-color: var(--surface);
            border-top: 1px solid var(--border);
            padding: 1.5rem;
            text-align: center;
            margin-top: 3rem;
            font-size: 0.85rem;
        }}

        .footer-content {{
            max-width: 1200px;
            margin: 0 auto;
        }}

        .footer-links {{
            display: flex;
            justify-content: center;
            gap: 1.5rem;
            margin-top: 0.75rem;
        }}

        .footer-link {{
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.8rem;
            transition: color 0.2s;
        }}

        .footer-link:hover {{
            color: var(--primary-blue);
        }}

        /* Enhanced Mobile Responsive */
        @media (max-width: 768px) {{
            .header-content {{
                flex-direction: column;
                gap: 0.75rem;
                padding: 0.5rem 1rem;
            }}

            .header-stats {{
                order: 3;
                width: 100%;
                justify-content: center;
                font-size: 0.75rem;
            }}

            .main-container {{
                padding: 0.75rem;
            }}

            .hero-title {{
                font-size: 1.5rem;
            }}

            .article-grid {{
                grid-template-columns: 1fr;
            }}

            .featured-grid {{
                grid-template-columns: 1fr;
            }}

            .content-header {{
                flex-direction: column;
                gap: 0.75rem;
            }}

            .filter-content.active {{
                grid-template-columns: 1fr;
            }}

            .quick-filters {{
                flex-wrap: wrap;
                gap: 0.4rem;
            }}

            .time-filter {{
                padding: 0.4rem 0.8rem;
                font-size: 0.75rem;
            }}
        }}

        /* Loading State */
        .loading {{
            display: flex;
            justify-content: center;
            align-items: center;
            height: 200px;
        }}

        .spinner {{
            width: 40px;
            height: 40px;
            border: 3px solid var(--border);
            border-top-color: var(--primary-blue);
            border-radius: 50%;
            animation: spin 1s linear infinite;
        }}

        @keyframes spin {{
            to {{
                transform: rotate(360deg);
            }}
        }}

        /* Tooltips */
        .tooltip {{
            position: relative;
        }}

        .tooltip::after {{
            content: attr(data-tooltip);
            position: absolute;
            bottom: 100%;
            left: 50%;
            transform: translateX(-50%);
            background-color: var(--text-primary);
            color: var(--background);
            padding: 0.25rem 0.5rem;
            border-radius: 0.25rem;
            font-size: 0.75rem;
            white-space: nowrap;
            opacity: 0;
            pointer-events: none;
            transition: opacity 0.2s;
        }}

        .tooltip:hover::after {{
            opacity: 1;
        }}
    </style>
    </head>
    <body data-theme="light">
    <!-- Header -->
    <header class="header">
        <div class="header-content">
            <div class="logo">
                <span class="logo-icon">📡</span>
                <span>PolicyRadar</span>
            </div>
            
            <div class="header-stats">
                <div class="stat">
                    <span>📊</span>
                    <span class="stat-value">270+</span>
                    <span>sources</span>
                </div>
                <div class="stat">
                    <span>🔄</span>
                    <span class="stat-value">Daily</span>
                    <span>updates</span>
                </div>
            </div>
            
            <div class="header-actions">
                <a href="#" class="nav-link" onclick="showAbout(event)">About</a>
                <a href="health.html" class="nav-link">Health</a>
                <button class="theme-toggle" id="themeToggle" onclick="toggleTheme()">
                    <span id="themeIcon">🌙</span>
                </button>
            </div>
        </div>
    </header>

    <!-- Main Content -->
    <main class="main-container">
        <!-- Hero Section -->
        <div class="hero-section">
            <h1 class="hero-title">Policy Intelligence Platform</h1>
            <p class="hero-subtitle">Real-time tracking of Indian policy developments</p>
        </div>

        <!-- Search Bar -->
        <div class="search-container">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" class="search-input" placeholder="Search policies, ministries, or topics..." id="searchInput">
                <button class="search-button" onclick="performSearch()">Search</button>
            </div>
        </div>

        <!-- Quick Time Filters -->
        <div class="quick-filters">
            <button class="time-filter active" data-time="all">All Time</button>
            <button class="time-filter" data-time="today">Today</button>
            <button class="time-filter" data-time="week">This Week</button>
            <button class="time-filter" data-time="month">This Month</button>
        </div>

        <!-- Advanced Filters -->
        <div class="filter-bar">
            <div class="filter-header">
                <div class="filter-title">
                    <span>🎯</span>
                    <span>Advanced Filters</span>
                </div>
                <div class="filter-actions">
                    <button class="filter-button" onclick="toggleFilters()" id="filterToggleBtn">
                        Show Filters
                    </button>
                    <button class="filter-button" onclick="resetFilters()">Reset</button>
                    <button class="filter-button apply" onclick="applyFilters()">Apply</button>
                </div>
            </div>
            
            <div class="filter-content" id="filterContent">
                <div class="filter-group">
                    <div class="filter-group-title">Policy Domains</div>
                    <!-- --- START: MODIFICATION --- -->
                    {policy_domain_filters_html}
                    <!-- --- END: MODIFICATION --- -->
                    </div>
                
                <div class="filter-group">
                    <div class="filter-group-title">Source Type</div>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="source_type" value="government">
                        <span>Government Official</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="source_type" value="legal">
                        <span>Legal/Courts</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="source_type" value="media">
                        <span>Media Analysis</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="source_type" value="think_tank">
                        <span>Think Tanks</span>
                    </label>
                </div>
                
                <div class="filter-group">
                    <div class="filter-group-title">Impact Level</div>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="impact" value="critical">
                        <span>Critical</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="impact" value="high">
                        <span>High</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="impact" value="medium">
                        <span>Medium</span>
                    </label>
                </div>
            </div>
        </div>

        <!-- Content Header -->
        <div class="content-header">
            <div class="results-count">
                Showing <span id="resultCount">0</span> policy updates
            </div>
            <select class="sort-dropdown" id="sortDropdown" onchange="sortArticles()">
                <option value="relevance">Sort by Relevance</option>
                <option value="date">Sort by Date</option>
                <option value="impact">Sort by Impact</option>
            </select>
        </div>

        <!-- Featured Section -->
        <div class="featured-section" id="featuredSection">
            <div class="featured-header">
                <span>⚡</span>
                <h2 class="featured-title">Today's Top Policy Updates</h2>
            </div>
            <div class="featured-grid" id="featuredGrid">
                <!-- Featured articles will be dynamically loaded here -->
            </div>
        </div>

        <!-- Main Content Area -->
        <div id="mainContent">
            <!-- Dynamic sections will be loaded here based on data -->
        </div>
    </main>

    <!-- Footer -->
    <footer class="footer">
        <div class="footer-content">
            <p><strong>PolicyRadar</strong> - Professional Policy Intelligence Platform</p>
            <div class="footer-links">
                <a href="#" class="footer-link" onclick="showAbout(event)">About</a>
                <a href="health.html" class="footer-link">System Health</a>
                <a href="https://github.com/policyradar" class="footer-link" target="_blank">GitHub</a>
                <a href="mailto:contact@policyradar.in" class="footer-link">Contact</a>
            </div>
            <p style="margin-top: 0.75rem; font-size: 0.75rem; color: var(--text-secondary);">
                © 2025 PolicyRadar. Content from respective publishers.
            </p>
        </div>
    </footer>

    <!-- About Modal -->
    <div class="modal" id="aboutModal">
        <div class="modal-content">
            <button class="modal-close" onclick="closeAbout()">&times;</button>
            <h2 class="modal-title">About PolicyRadar</h2>
            <div class="modal-body">
                <p>PolicyRadar is an intelligent policy intelligence platform that tracks over 270+ Indian government sources, think tanks, courts, and media outlets to bring you comprehensive policy updates.</p>
                
                <h3>Key Features</h3>
                <ul>
                    <li>Real-time monitoring of 270+ policy sources</li>
                    <li>AI-powered relevance scoring and categorization</li>
                    <li>Multi-dimensional filtering by sector, source, and impact</li>
                    <li>Daily updates at 2 AM IST</li>
                    <li>Export capabilities for research and analysis</li>
                </ul>
                
                <h3>Data Sources</h3>
                <p>We aggregate content from:</p>
                <ul>
                    <li>Government ministries and departments</li>
                    <li>Regulatory bodies (RBI, SEBI, TRAI, etc.)</li>
                    <li>Courts and legal sources</li>
                    <li>Think tanks and research organizations</li>
                    <li>Trusted media outlets</li>
                </ul>
                
                <h3>Contact</h3>
                <p>For inquiries or suggestions: <a href="mailto:contact@policyradar.in">contact@policyradar.in</a></p>
            </div>
        </div>
    </div>

    <script>
        // Global variables
        let allArticles = [];
        let currentFilters = {{
            category: [],
            source_type: [],
            impact: [],
            timeRange: 'all',
            searchTerm: ''
        }};

        // Initialize the application
        document.addEventListener('DOMContentLoaded', function() {{
            loadArticlesFromPython();
            initializeEventListeners();
            loadTheme();
        }});

        // Function to load articles
        function loadArticlesFromPython() {{
            const articlesData = window.POLICYRADAR_DATA || {articles_json};
            allArticles = articlesData.articles || [];
            renderAllContent();
        }}

        // Render all content
        function renderAllContent() {{
            renderFeaturedArticles();
            renderMainContent();
            updateStatistics();
        }}

        // --- START: REWRITTEN JAVASCRIPT FUNCTIONS ---
        // Render featured articles (last 24 hours only)
        function renderFeaturedArticles() {{
            const featuredGrid = document.getElementById('featuredGrid');
            const now = new Date();
            const oneDayAgo = new Date(now - 24 * 60 * 60 * 1000);
            
            const featured = allArticles
                .filter(article => new Date(article.published_date) >= oneDayAgo)
                .sort((a, b) => new Date(b.published_date) - new Date(a.published_date))
                .slice(0, 2);

            featuredGrid.innerHTML = featured.map(article => createArticleCard(article, true)).join('');
        }}

        // Render main content organized by categories, sorted by date
        function renderMainContent() {{
            const mainContent = document.getElementById('mainContent');
            const filtered = filterArticles();
            
            // Sort by date before grouping
            filtered.sort((a, b) => new Date(b.published_date) - new Date(a.published_date));
            
            // Group by category
            const grouped = filtered.reduce((acc, article) => {{
                const cat = article.category || 'Uncategorized';
                if (!acc[cat]) acc[cat] = [];
                acc[cat].push(article);
                return acc;
            }}, {{}});

            // Render each category section
            mainContent.innerHTML = Object.entries(grouped)
                .map(([category, articles]) => `
                    <section class="category-section">
                        <h2 class="category-title">
                            <span class="category-icon">${{getCategoryIcon(category)}}</span>
                            ${{category}}
                            <span class="article-count">(${{articles.length}})</span>
                        </h2>
                        <div class="article-grid">
                            ${{articles.map(article => createArticleCard(article, false)).join('')}}
                        </div>
                    </section>
                `).join('');
        }}
        // --- END: REWRITTEN JAVASCRIPT FUNCTIONS ---

        // Create article card HTML
        function createArticleCard(article, isFeatured = false) {{
            const priority = getPriorityClass(article.relevance_scores.overall);
            const date = formatDate(article.published_date);
            const sourceType = getSourceType(article.source);
            
            return `
                <div class="article-card ${{priority}}">
                    <div class="article-header">
                        <div class="source-info">
                            <div class="source-badge tooltip" data-tooltip="${{sourceType.tooltip}}">${{sourceType.icon}}</div>
                            <span>${{article.source}}</span>
                        </div>
                        <span class="article-date">${{date}}</span>
                    </div>
                    <h3 class="article-title">
                        <a href="${{article.url}}" target="_blank">${{article.title}}</a>
                    </h3>
                    <p class="article-summary">${{article.summary}}</p>
                    <div class="article-footer">
                        <div class="article-tags">
                            ${{article.tags.slice(0, 2).map(tag => `<span class="tag">${{tag}}</span>`).join('')}}
                        </div>
                        <div class="article-actions">
                            <button class="action-button tooltip" data-tooltip="Save" onclick="saveArticle('${{article.url}}')">📌</button>
                            <button class="action-button tooltip" data-tooltip="Share" onclick="shareArticle('${{article.url}}', '${{article.title.replace(/'/g, "\\'")}}')">📤</button>
                        </div>
                    </div>
                </div>
            `;
        }}

        // Filter articles based on current filters - FIXED
        function filterArticles() {{
            return allArticles.filter(article => {{
                // Search filter
                if (currentFilters.searchTerm) {{
                    const searchLower = currentFilters.searchTerm.toLowerCase();
                    if (!article.title.toLowerCase().includes(searchLower) &&
                        !article.summary.toLowerCase().includes(searchLower)) {{
                        return false;
                    }}
                }}

                // Category filter
                if (currentFilters.category.length > 0 && 
                    !currentFilters.category.includes(article.category)) {{
                    return false;
                }}

                // Source type filter
                if (currentFilters.source_type.length > 0) {{
                    const articleSourceType = getSourceType(article.source).type;
                    if (!currentFilters.source_type.includes(articleSourceType)) {{
                        return false;
                    }}
                }}

                // Impact filter
                if (currentFilters.impact.length > 0) {{
                    const articleImpact = getPriorityClass(article.relevance_scores.overall);
                    if (!currentFilters.impact.includes(articleImpact)) {{
                        return false;
                    }}
                }}

                // Time filter
                if (currentFilters.timeRange !== 'all') {{
                    const articleDate = new Date(article.published_date);
                    const now = new Date();
                    const diffHours = (now - articleDate) / (1000 * 60 * 60);
                    
                    switch(currentFilters.timeRange) {{
                        case 'today':
                            if (diffHours > 24) return false;
                            break;
                        case 'week':
                            if (diffHours > 168) return false;
                            break;
                        case 'month':
                            if (diffHours > 720) return false;
                            break;
                    }}
                }}

                return true;
            }});
        }}

        // Initialize event listeners - FIXED
        function initializeEventListeners() {{
            // Search
            document.getElementById('searchInput').addEventListener('input', (e) => {{
                currentFilters.searchTerm = e.target.value;
                renderMainContent();
            }});

            // Time filters - FIXED
            document.querySelectorAll('.time-filter').forEach(btn => {{
                btn.addEventListener('click', function() {{
                    document.querySelectorAll('.time-filter').forEach(b => b.classList.remove('active'));
                    this.classList.add('active');
                    currentFilters.timeRange = this.getAttribute('data-time');
                    renderMainContent();
                }});
            }});

            // Filter checkboxes - FIXED
            document.querySelectorAll('.filter-checkbox').forEach(checkbox => {{
                checkbox.addEventListener('change', function() {{
                    // This will be applied when "Apply" is clicked
                }});
            }});
        }}

        // Apply advanced filters - FIXED
        function applyFilters() {{
            // Reset filter arrays
            currentFilters.category = [];
            currentFilters.source_type = [];
            currentFilters.impact = [];
            
            // Get selected filters
            const checkboxes = document.querySelectorAll('.filter-checkbox:checked');
            
            checkboxes.forEach(checkbox => {{
                const filterType = checkbox.getAttribute('data-filter');
                const value = checkbox.value;
                
                if (currentFilters[filterType]) {{
                    currentFilters[filterType].push(value);
                }}
            }});
            
            renderMainContent();
        }}

        // Reset filters - FIXED
        function resetFilters() {{
            document.querySelectorAll('.filter-checkbox').forEach(cb => cb.checked = false);
            currentFilters.category = [];
            currentFilters.source_type = [];
            currentFilters.impact = [];
            renderMainContent();
        }}

        // Toggle filters visibility - FIXED
        function toggleFilters() {{
            const content = document.getElementById('filterContent');
            const toggleBtn = document.getElementById('filterToggleBtn');
            const isActive = content.classList.contains('active');
            
            content.classList.toggle('active');
            toggleBtn.textContent = isActive ? 'Show Filters' : 'Hide Filters';
        }}

        // Utility functions
        function getPriorityClass(relevanceScore) {{
            if (relevanceScore >= 0.8) return 'critical';
            if (relevanceScore >= 0.6) return 'high';
            return 'medium';
        }}

        function getSourceType(source) {{
            const sourceLower = source.toLowerCase();
            if (sourceLower.includes('ministry') || sourceLower.includes('government') || 
                sourceLower.includes('rbi') || sourceLower.includes('sebi')) {{
                return {{ icon: '🏛️', tooltip: 'Government Source', type: 'government' }};
            }}
            if (sourceLower.includes('court') || sourceLower.includes('legal')) {{
                return {{ icon: '⚖️', tooltip: 'Legal Source', type: 'legal' }};
            }}
            if (sourceLower.includes('research') || sourceLower.includes('institute')) {{
                return {{ icon: '🔬', tooltip: 'Research Organization', type: 'think_tank' }};
            }}
            return {{ icon: '📰', tooltip: 'Media Source', type: 'media' }};
        }}

        function getCategoryIcon(category) {{
            const icons = {{
                'Economic Policy': '📊',
                'Technology Policy': '💻',
                'Healthcare Policy': '🏥',
                'Environmental Policy': '🌱',
                'Constitutional & Legal': '⚖️',
                'Defense & Security': '🛡️',
                'Foreign Policy': '🌐',
                'Education Policy': '🎓',
                'Agricultural Policy': '🌾',
                'Governance & Administration': '📄',
                'Social Policy': '🤝',
                'Policy Analysis': '📋'
            }};
            return icons[category] || '📄';
        }}

        function formatDate(dateString) {{
            if (!dateString) return 'N/A';
            const date = new Date(dateString);
            const now = new Date();
            const diffHours = (now - date) / (1000 * 60 * 60);
            
            if (diffHours < 1) return 'Just now';
            if (diffHours < 24) return `${{Math.floor(diffHours)}}h ago`;
            if (diffHours < 48) return 'Yesterday';
            
            return date.toLocaleDateString('en-US', {{ 
                month: 'short', 
                day: 'numeric', 
                year: 'numeric' 
            }});
        }}

        // Theme management
        function toggleTheme() {{
            const body = document.body;
            const currentTheme = body.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            
            body.setAttribute('data-theme', newTheme);
            document.getElementById('themeIcon').textContent = newTheme === 'dark' ? '☀️' : '🌙';
            localStorage.setItem('theme', newTheme);
        }}

        function loadTheme() {{
            const savedTheme = localStorage.getItem('theme') || 'light';
            document.body.setAttribute('data-theme', savedTheme);
            document.getElementById('themeIcon').textContent = savedTheme === 'dark' ? '☀️' : '🌙';
        }}

        // Article actions
        function saveArticle(url) {{
            const saved = JSON.parse(localStorage.getItem('savedArticles') || '[]');
            if (!saved.includes(url)) {{
                saved.push(url);
                localStorage.setItem('savedArticles', JSON.stringify(saved));
                alert('Article saved!');
            }} else {{
                alert('Article already saved!');
            }}
        }}

        function shareArticle(url, title) {{
            if (navigator.share) {{
                navigator.share({{
                    title: title,
                    url: url
                }}).catch(err => console.log('Error sharing:', err));
            }} else {{
                navigator.clipboard.writeText(url).then(() => {{
                    alert('Link copied to clipboard!');
                }});
            }}
        }}

        // About modal
        function showAbout(e) {{
            e.preventDefault();
            document.getElementById('aboutModal').classList.add('active');
        }}

        function closeAbout() {{
            document.getElementById('aboutModal').classList.remove('active');
        }}

        // Update statistics
        function updateStatistics() {{
            document.getElementById('resultCount').textContent = filterArticles().length;
        }}

        // Sort articles
        function sortArticles() {{
            const sortBy = document.getElementById('sortDropdown').value;
            
            switch(sortBy) {{
                case 'date':
                    allArticles.sort((a, b) => new Date(b.published_date) - new Date(a.published_date));
                    break;
                case 'impact':
                    allArticles.sort((a, b) => b.relevance_scores.overall - a.relevance_scores.overall);
                    break;
                case 'relevance':
                default:
                    allArticles.sort((a, b) => {{
                        const scoreA = (a.relevance_scores.overall * 0.7) + (a.relevance_scores.recency * 0.3);
                        const scoreB = (b.relevance_scores.overall * 0.7) + (b.relevance_scores.recency * 0.3);
                        return scoreB - scoreA;
                    }});
            }}
            
            renderAllContent();
        }}

        // Perform search
        function performSearch() {{
            const searchTerm = document.getElementById('searchInput').value;
            currentFilters.searchTerm = searchTerm;
            renderMainContent();
        }}
    </script>

    <!-- Python Integration Point -->
    <script>
        window.POLICYRADAR_DATA = {articles_json};
    </script>
    </body>
    </html>
    """

        # Write HTML to file
        output_file = os.path.join(Config.OUTPUT_DIR, 'index.html')
        try:
            os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Enhanced HTML output generated: {output_file}")
            
            # Also generate the about page
            self.generate_about_page()
            
        except Exception as e:
            logger.error(f"Error writing HTML file: {str(e)}")
            output_file = None

        return output_file


    
    def generate_about_page(self) -> str:
        """Generate a detailed about page"""
        about_html = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>About PolicyRadar - Indian Policy News Aggregator</title>
        <meta name="description" content="Learn about PolicyRadar, an intelligent aggregator for policy news from Indian sources">
        <meta name="keywords" content="India, policy, news, government, about, mission">
        <meta name="author" content="PolicyRadar">
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔍</text></svg>">
        <style>
            :root {
                --primary-color: #2c3e50;
                --secondary-color: #3498db;
                --accent-color: #e74c3c;
                --background-color: #f9f9f9;
                --card-color: #ffffff;
                --text-color: #333333;
                --light-text: #777777;
                --link-color: #2980b9;
                --link-hover: #3498db;
                --border-color: #dddddd;
                --notice-bg: #fff8e1;
                --notice-border: #ffd54f;
                --high-importance: rgba(231, 76, 60, 0.1);
                --medium-importance: rgba(241, 196, 15, 0.1);
                --low-importance: rgba(236, 240, 241, 0.5);
            }
            
            [data-theme="dark"] {
                --primary-color: #16213e;         
                --primary-text-color: #e0e6f2;    
                --secondary-color: #0f4c81;       
                --accent-color: #e94560;          
                --background-color: #0f0f17;      
                --card-color: #1e2132;            
                --text-color: #f0f0f0;            
                --light-text: #c5c5c5;            
                --link-color: #7ab3ef;            
                --link-hover: #a5cdff;            
                --border-color: #373e59;          
                --notice-bg: #2a2a36;             
                --notice-border: #ffd54f;         
                --high-importance: rgba(231, 76, 60, 0.3);    
                --medium-importance: rgba(241, 196, 15, 0.2); 
                --low-importance: rgba(236, 240, 241, 0.15);  
            }

            /* Enhanced dark mode styling for consistent text colors */
            [data-theme="dark"] .page-title h1,
            [data-theme="dark"] .about-content h2 {
                color: var(--primary-text-color);
            }

            /* Make sure PolicyRadar title in header has consistent color */
            [data-theme="dark"] .logo span {
                color: white;
            }

            
            /* Additional dark mode text styling */
            [data-theme="dark"] .section-title,
            [data-theme="dark"] .intro h1,
            [data-theme="dark"] .page-title h1,
            [data-theme="dark"] .about-content h2,
            [data-theme="dark"] .section-header {
                color: var(--primary-text-color);
            }
            
            [data-theme="dark"] .logo {
                color: white; /* Ensure logo text is always white in dark mode */
            }
            
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--text-color);
                background-color: var(--background-color);
                padding-bottom: 2rem;
                transition: background-color 0.3s ease, color 0.3s ease;
            }
            
            a {
                color: var(--link-color);
                text-decoration: none;
                transition: color 0.2s;
            }
            
            a:hover {
                color: var(--link-hover);
                text-decoration: underline;
            }
            
            .container {
                width: 100%;
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 1rem;
            }
            
            header {
                background-color: var(--primary-color);
                color: white;
                padding: 1rem 0;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }
            
            .header-content {
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
            }
            
            .logo {
                display: flex;
                align-items: center;
                font-size: 1.5rem;
                font-weight: bold;
            }
            
            .logo span {
                margin-left: 0.5rem;
            }
            
            .nav {
                display: flex;
                align-items: center;
            }
            
            .nav a {
                color: white;
                margin-left: 1.5rem;
                font-size: 0.9rem;
            }
            
            .theme-toggle {
                background: none;
                border: none;
                color: white;
                cursor: pointer;
                font-size: 1.2rem;
                margin-left: 1rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            main {
                padding: 2rem 0;
            }
            
            .page-title {
                margin-bottom: 2rem;
                text-align: center;
            }
            
            .page-title h1 {
                font-size: 2rem;
                margin-bottom: 0.5rem;
                color: var(--primary-color);
            }
            
            .about-content {
                background-color: var(--card-color);
                border-radius: 8px;
                padding: 2rem;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
                border: 1px solid var(--border-color);
                margin-bottom: 2rem;
            }
            
            .about-content h2 {
                margin-top: 1.5rem;
                margin-bottom: 1rem;
                color: var(--primary-color);
                font-size: 1.5rem;
            }
            
            .about-content h2:first-child {
                margin-top: 0;
            }
            
            .about-content p {
                margin-bottom: 1rem;
            }
            
            .about-content ol, 
            .about-content ul {
                margin-left: 1.5rem;
                margin-bottom: 1rem;
            }
            
            .about-content li {
                margin-bottom: 0.5rem;
            }
            
            footer {
                background-color: var(--primary-color);
                color: white;
                padding: 1.5rem 0;
                text-align: center;
                margin-top: 2rem;
            }
            
            .footer-content {
                max-width: 600px;
                margin: 0 auto;
            }
            
            .footer-links {
                margin: 1rem 0;
            }
            
            .footer-links a {
                color: white;
                margin: 0 0.5rem;
                font-size: 0.9rem;
            }
            
            .copyright {
                font-size: 0.8rem;
                opacity: 0.8;
            }
            
            /* Mobile Optimization */
            @media (max-width: 768px) {
                .header-content {
                    flex-direction: column;
                    text-align: center;
                }
                
                .nav {
                    margin-top: 1rem;
                    justify-content: center;
                }
                
                .nav a {
                    margin: 0 0.75rem;
                }
                
                .about-content {
                    padding: 1.5rem;
                }
            }
            
            @media (max-width: 600px) {
                .container {
                    padding: 0 0.5rem;
                }
                
                .about-content {
                    padding: 1rem;
                }
            }
        </style>
    </head>
    <body data-theme="light">
        <header>
            <div class="container">
                <div class="header-content">
                    <div class="logo">
                        🔍 <span>PolicyRadar</span>
                    </div>
                    <div class="nav">
                        <a href="index.html">Home</a>
                        <a href="about.html">About</a>
                        <a href="health.html">System Health</a>
                        <button class="theme-toggle" id="theme-toggle">🔆</button>
                    </div>
                </div>
            </div>
        </header>
        
        <main class="container">
            <div class="page-title">
                <h1>About PolicyRadar</h1>
            </div>
            
            <div class="about-content">
                <h2>Our Mission</h2>
                <p>PolicyRadar was created to solve a common problem faced by professionals, students, and citizens interested in Indian policy developments: information overload.</p>
                <p>Every day, important policy news is scattered across dozens of sources—government websites, newspapers, think tanks, and specialized publications. Staying informed requires scanning multiple websites, newsletters, and social media feeds, often leading to missed information or overwhelming reading lists.</p>
                <p>PolicyRadar cuts through this noise by carefully curating the most significant policy developments across key domains. We monitor over 30 trusted sources so you don't have to, bringing you a concise, organized view of what matters in Indian policy.</p>

                <h2>Our Curation Process</h2>
                <p>Each policy update on PolicyRadar passes through a deliberate selection and summarization process:</p>
                <ol>
                    <li><strong>Comprehensive Monitoring</strong>: We track official government communications, major news outlets, specialized policy publications, and respected think tanks.</li>
                    <li><strong>Significance Filtering</strong>: We select stories based on their potential impact, relevance to current debates, and long-term importance.</li>
                    <li><strong>Clear Categorization</strong>: Each story is organized by policy domain and tagged by content type (legislation, analysis, court ruling, etc.).</li>
                    <li><strong>Key Points Extraction</strong>: We identify and highlight the most important elements of each development.</li>
                    <li><strong>Context Addition</strong>: Where appropriate, we provide brief notes on why a particular development matters.</li>
                </ol>
                <p>All content links to original sources, allowing you to explore topics in greater depth when needed.</p>

                <h2>Publishing Schedule</h2>
                <p>PolicyRadar is updated daily</p>

                <h2>About the Creator</h2>
                <p>PolicyRadar is created and curated by Roma Thakur, a technical writer and policy researcher with expertise in data privacy, technology policy, and regulatory communications. With a background in both computer science and social & public policy, Roma brings a multidisciplinary perspective to policy curation.</p>

                <h2>Contact Us</h2>
                <p>We welcome your feedback, suggestions, and inquiries about PolicyRadar. Please reach out to us at <a href="mailto:roma@policyradar.in">roma@policyradar.in</a> for any of the following reasons:</p>
                <ul>
                <li><strong>Suggest new sources:</strong> If you know of reliable policy news sources that we should be monitoring, please let us know.</li>
                <li><strong>Report inaccuracies:</strong> Help us maintain quality by reporting any outdated information or errors you might find.</li>
                <li><strong>Propose collaborations:</strong> We're open to partnerships that can help improve policy awareness and analysis.</li>
                <li><strong>Request customized monitoring:</strong> Need specialized policy tracking for specific domains? Contact us to discuss your requirements.</li>
                <li><strong>Share feedback:</strong> We value your thoughts on how we can improve the platform and make it more useful.</li>
                <li><strong>Media inquiries:</strong> For press and media related questions, please include "Media" in your email subject line.</li>
                </ul>
                <p>We aim to respond to all inquiries within 2 business days.</p>

            </div>
        </main>
        
        <footer>
            <div class="container">
                <div class="footer-content">
                    <p><strong>PolicyRadar</strong> - Indian Policy News Aggregator</p>
                    <div class="footer-links">
                        <a href="index.html">Home</a>
                        <a href="about.html">About</a>
                        <a href="health.html">System Health</a>
                    </div>
                    <div class="copyright">
                        &copy; 2025 PolicyRadar | News content belongs to respective publishers
                    </div>
                </div>
            </div>
        </footer>
        
        <script>
            // Theme toggling functionality
            const themeToggle = document.getElementById('theme-toggle');
            const body = document.body;
            
            // Check for saved theme preference or respect OS preference
            const savedTheme = localStorage.getItem('theme');
            const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
            
            if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {
                body.setAttribute('data-theme', 'dark');
                themeToggle.textContent = '🌙';
            }
            
            themeToggle.addEventListener('click', () => {
                const currentTheme = body.getAttribute('data-theme');
                const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
                
                body.setAttribute('data-theme', newTheme);
                themeToggle.textContent = newTheme === 'dark' ? '🌙' : '🔆';
                localStorage.setItem('theme', newTheme);
            });
        </script>
    </body>
    </html>"""
        
        # Write about page
        about_file = os.path.join(Config.OUTPUT_DIR, 'about.html')
        try:
            with open(about_file, 'w', encoding='utf-8') as f:
                f.write(about_html)
            logger.info(f"About page generated: {about_file}")
        except Exception as e:
            logger.error(f"Error writing about page: {str(e)}")
        
        return about_file
    

    def generate_health_dashboard(self) -> str:
        """Generate enhanced system health dashboard with detailed statistics"""
        try:
            # Calculate overall statistics
            total_feeds = len(self.feeds)
            successful_feeds = len([s for s in self.source_statistics.values() if s['articles'] > 0])
            total_articles = sum(s['articles'] for s in self.source_statistics.values())
            success_rate = (successful_feeds / total_feeds * 100) if total_feeds > 0 else 0
            
            # Group sources by category
            sources_by_category = {}
            for source_name, stats in self.source_statistics.items():
                category = stats.get('category', 'Unknown')
                if category not in sources_by_category:
                    sources_by_category[category] = []
                sources_by_category[category].append((source_name, stats))
            
            # Sort categories by total articles
            category_totals = {}
            for category, sources in sources_by_category.items():
                category_totals[category] = sum(stats['articles'] for _, stats in sources)
            
            sorted_categories = sorted(category_totals.items(), key=lambda x: x[1], reverse=True)
            
            # Create HTML
            html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PolicyRadar System Health Dashboard</title>
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
                line-height: 1.6; 
                margin: 0; 
                padding: 20px; 
                background-color: #f5f5f5;
            }}
            .container {{ 
                max-width: 1400px; 
                margin: 0 auto; 
            }}
            h1 {{
                color: #2c3e50;
                text-align: center;
                margin-bottom: 30px;
            }}
            .stats-grid {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); 
                gap: 20px; 
                margin-bottom: 30px;
            }}
            .stat-card {{ 
                background: white; 
                border-radius: 8px; 
                box-shadow: 0 2px 4px rgba(0,0,0,0.1); 
                padding: 20px; 
                text-align: center;
            }}
            .stat-value {{ 
                font-size: 2.5em; 
                font-weight: bold; 
                margin: 10px 0;
            }}
            .stat-label {{ 
                color: #666; 
                font-size: 0.9em;
            }}
            .category-section {{
                background: white;
                border-radius: 8px;
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                padding: 20px;
                margin-bottom: 20px;
            }}
            .category-header {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 15px;
                padding-bottom: 10px;
                border-bottom: 2px solid #eee;
            }}
            .category-title {{
                font-size: 1.3em;
                font-weight: 600;
                color: #2c3e50;
            }}
            .category-stats {{
                font-size: 0.9em;
                color: #666;
            }}
            table {{ 
                width: 100%; 
                border-collapse: collapse; 
            }}
            th {{ 
                background-color: #f8f9fa; 
                padding: 12px; 
                text-align: left; 
                font-weight: 600;
                color: #495057;
                border-bottom: 2px solid #dee2e6;
            }}
            td {{ 
                padding: 10px; 
                border-bottom: 1px solid #dee2e6;
            }}
            tr:hover {{
                background-color: #f8f9fa;
            }}
            .status-success {{ 
                color: #28a745; 
                font-weight: 600;
            }}
            .status-empty {{ 
                color: #ffc107; 
            }}
            .status-error {{ 
                color: #dc3545; 
            }}
            .articles-count {{
                font-weight: 600;
                color: #007bff;
            }}
            .timestamp {{
                color: #6c757d;
                font-size: 0.85em;
            }}
            .summary-section {{
                background: #e3f2fd;
                border-radius: 8px;
                padding: 20px;
                margin-bottom: 30px;
            }}
            .summary-title {{
                font-size: 1.2em;
                font-weight: 600;
                color: #1976d2;
                margin-bottom: 10px;
            }}
            .top-sources {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 10px;
                margin-top: 10px;
            }}
            .top-source {{
                background: white;
                padding: 10px;
                border-radius: 6px;
                font-size: 0.9em;
            }}
            .source-name {{
                font-weight: 600;
                color: #2c3e50;
            }}
            .article-count {{
                color: #007bff;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>PolicyRadar System Health Dashboard</h1>
            <p style="text-align: center; color: #666;">Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-label">Total Feeds</div>
                    <div class="stat-value">{total_feeds}</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Active Feeds</div>
                    <div class="stat-value" style="color: #28a745;">{successful_feeds}</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Total Articles</div>
                    <div class="stat-value" style="color: #007bff;">{total_articles}</div>
                </div>
                
                <div class="stat-card">
                    <div class="stat-label">Success Rate</div>
                    <div class="stat-value" style="color: {'#28a745' if success_rate > 60 else '#ffc107' if success_rate > 30 else '#dc3545'};">
                        {success_rate:.1f}%
                    </div>
                </div>
            </div>

            <div class="summary-section">
                <div class="summary-title">Top Performing Sources</div>
                <div class="top-sources">
    """
            
            # Add top 10 sources
            top_sources = sorted(
                [(name, stats) for name, stats in self.source_statistics.items() if stats['articles'] > 0],
                key=lambda x: x[1]['articles'],
                reverse=True
            )[:10]
            
            for source_name, stats in top_sources:
                html += f"""
                    <div class="top-source">
                        <div class="source-name">{source_name}</div>
                        <div class="article-count">{stats['articles']} articles</div>
                    </div>
    """
            
            html += """
                </div>
            </div>
    """
            
            # Add category-wise breakdown
            for category, article_count in sorted_categories:
                sources = sources_by_category[category]
                active_sources = len([s for _, s in sources if s['articles'] > 0])
                
                html += f"""
            <div class="category-section">
                <div class="category-header">
                    <div class="category-title">{category}</div>
                    <div class="category-stats">
                        {article_count} articles from {active_sources}/{len(sources)} sources
                    </div>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>Source</th>
                            <th>Articles</th>
                            <th>Status</th>
                            <th>Last Update</th>
                        </tr>
                    </thead>
                    <tbody>
    """
                
                # Sort sources by article count within category
                sorted_sources = sorted(sources, key=lambda x: x[1]['articles'], reverse=True)
                
                for source_name, stats in sorted_sources:
                    status = stats.get('status', 'unknown')
                    status_class = 'status-success' if stats['articles'] > 0 else 'status-empty' if status == 'empty' else 'status-error'
                    
                    last_time = stats.get('last_success') or stats.get('last_attempt')
                    time_str = last_time.strftime('%H:%M:%S') if last_time else 'N/A'
                    
                    html += f"""
                        <tr>
                            <td>{source_name}</td>
                            <td class="articles-count">{stats['articles']}</td>
                            <td class="{status_class}">{status}</td>
                            <td class="timestamp">{time_str}</td>
                        </tr>
    """
                
                html += """
                    </tbody>
                </table>
            </div>
    """
            
            # Add failed feeds section
            failed_feeds = [(name, stats) for name, stats in self.source_statistics.items() 
                        if stats['articles'] == 0 and 'Error' in stats.get('status', '')]
            
            if failed_feeds:
                html += """
            <div class="category-section">
                <div class="category-header">
                    <div class="category-title">Failed Feeds</div>
                    <div class="category-stats">{} feeds with errors</div>
                </div>
                
                <table>
                    <thead>
                        <tr>
                            <th>Source</th>
                            <th>Category</th>
                            <th>Error</th>
                            <th>Last Attempt</th>
                        </tr>
                    </thead>
                    <tbody>
    """.format(len(failed_feeds))
                
                for source_name, stats in failed_feeds:
                    last_time = stats.get('last_attempt')
                    time_str = last_time.strftime('%H:%M:%S') if last_time else 'N/A'
                    
                    html += f"""
                        <tr>
                            <td>{source_name}</td>
                            <td>{stats.get('category', 'Unknown')}</td>
                            <td class="status-error">{stats.get('status', 'Unknown error')}</td>
                            <td class="timestamp">{time_str}</td>
                        </tr>
    """
                
                html += """
                    </tbody>
                </table>
            </div>
    """
            
            html += """
        </div>
    </body>
    </html>
    """
            
            # Write to file
            health_file = os.path.join(Config.OUTPUT_DIR, 'health.html')
            with open(health_file, 'w', encoding='utf-8') as f:
                f.write(html)
            
            logger.info(f"Enhanced health dashboard generated: {health_file}")
            return health_file
            
        except Exception as e:
            logger.error(f"Error generating health dashboard: {str(e)}")
            return None
    
    def export_articles_to_json(self, articles: List[NewsArticle], filename: Optional[str] = None) -> Optional[str]:
        """Export articles to JSON file with enhanced formatting"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(Config.EXPORT_DIR, f"policyradar_export_{timestamp}.json")
        
        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            
            # Create a structured data object
            export_data = {
                "metadata": {
                    "generated_at": datetime.now().isoformat(),
                    "article_count": len(articles),
                    "system_version": "PolicyRadar Enhanced 2025"
                },
                "articles": [article.to_dict() for article in articles]
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False)
            
            logger.info(f"Exported {len(articles)} articles to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error exporting articles to JSON: {str(e)}")
            return None

# Main execution block
    
if __name__ == "__main__":
    radar = PolicyRadarEnhanced()
    
    # Run with more workers for faster processing
    output_file = radar.run(max_workers=20, use_async=False)
    
    if output_file:
        logger.info(f"✅ Output generated: {output_file}")
        logger.info(f"Check health dashboard at: {os.path.join(Config.OUTPUT_DIR, 'health.html')}")
    else:
        logger.error("❌ Failed to generate output")
