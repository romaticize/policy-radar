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
from typing import List, Dict, Optional, Tuple, Set, Union, Any, Callable, TYPE_CHECKING
import urllib.parse
import requests
import feedparser
import datetime
import os
import re
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
        self.semaphore = asyncio.Semaphore(10)  # Limit concurrent requests
        self.gov_semaphore = asyncio.Semaphore(3)  # Stricter limit for government sites
        
    async def fetch_all_feeds_async(self, feeds):
        """Fetch all feeds asynchronously with proper rate limiting"""
        # Create custom connector with connection pooling
        connector = TCPConnector(
            limit=30,  # Total connection limit
            limit_per_host=5,  # Per-host connection limit
            ttl_dns_cache=300,
            enable_cleanup_closed=True
        )
        
        # Configure timeouts
        timeout = ClientTimeout(total=60, connect=10, sock_read=30)
        
        # Create session with custom settings
        async with ClientSession(
            connector=connector,
            timeout=timeout,
            headers={'User-Agent': self.policy_radar.get_user_agent()}
        ) as session:
            
            # Group feeds by domain for better rate limiting
            feeds_by_domain = self._group_feeds_by_domain(feeds)
            
            # Process feeds with controlled concurrency
            all_results = []
            
            # Process government feeds first with strict rate limiting
            gov_feeds = []
            other_feeds = []
            
            for feed in feeds:
                if self._is_government_feed(feed[1]):
                    gov_feeds.append(feed)
                else:
                    other_feeds.append(feed)
            
            # Process government feeds with delays
            logger.info(f"Processing {len(gov_feeds)} government feeds with rate limiting")
            gov_results = await self._process_feeds_with_delay(session, gov_feeds, delay=3.0)
            all_results.extend(gov_results)
            
            # Process other feeds concurrently
            logger.info(f"Processing {len(other_feeds)} news feeds concurrently")
            tasks = [self._fetch_single_feed_async(session, feed) for feed in other_feeds]
            other_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Filter out exceptions and combine results
            for result in other_results:
                if isinstance(result, list):
                    all_results.extend(result)
                elif isinstance(result, Exception):
                    logger.error(f"Async fetch error: {str(result)}")
            
            return all_results
    
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
        """Fetch a single feed asynchronously"""
        source_name, feed_url, category = feed_info
        
        # Choose appropriate semaphore
        if self._is_government_feed(feed_url):
            semaphore = self.gov_semaphore
        else:
            semaphore = self.semaphore
        
        async with semaphore:
            try:
                headers = self.policy_radar._build_headers_for_site(feed_url, source_name)
                
                async with session.get(feed_url, headers=headers, ssl=False) as response:
                    if response.status == 200:
                        content = await response.read()
                        content_type = response.headers.get('content-type', '').lower()
                        
                        # Process in thread pool to avoid blocking
                        loop = asyncio.get_event_loop()
                        articles = await loop.run_in_executor(
                            None,
                            self._process_feed_content,
                            content,
                            content_type,
                            source_name,
                            category,
                            feed_url
                        )
                        
                        return articles
                    else:
                        logger.warning(f"HTTP {response.status} for {source_name}")
                        return []
                        
            except asyncio.TimeoutError:
                logger.error(f"Timeout fetching {source_name}")
                return []
            except Exception as e:
                logger.error(f"Error fetching {source_name}: {str(e)}")
                return []
    
    def _process_feed_content(self, content, content_type, source_name, category, url):
        """Process feed content in thread pool"""
        try:
            if 'xml' in content_type or 'rss' in content_type:
                return self.policy_radar._parse_feed_content(content, source_name, category)
            elif 'html' in content_type:
                return self.policy_radar._scrape_html_content(
                    content.decode('utf-8'), source_name, category, url
                )
            else:
                return self.policy_radar._parse_feed_content(content, source_name, category)
        except Exception as e:
            logger.error(f"Error processing content for {source_name}: {str(e)}")
            return []
    
    def _is_government_feed(self, url):
        """Check if URL is a government feed"""
        gov_indicators = ['.gov.in', '.nic.in', 'rbi.org.in', 'sebi.gov.in', 
                         'trai.gov.in', 'pib.', 'parliament.']
        return any(indicator in url.lower() for indicator in gov_indicators)
    
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
    def handle_pib_site(session, url, headers):
        """Special handling for PIB (Press Information Bureau)"""
        # PIB requires specific approach
        headers.update({
            'Referer': 'https://pib.gov.in/',
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': 'text/html, */*; q=0.01'
        })
        
        # For PIB RSS, try multiple endpoints
        if 'rss' in url.lower():
            alternate_urls = [
                'https://pib.gov.in/RssFiles/PIBReleases.xml',
                'https://pib.gov.in/AllReleasem.aspx',
                'https://pib.gov.in/PressReleseDetail.aspx'
            ]
            
            for alt_url in alternate_urls:
                try:
                    response = session.get(alt_url, headers=headers, timeout=20)
                    if response.status_code == 200:
                        return response
                except:
                    continue
        
        return session.get(url, headers=headers, timeout=30)
    
    @staticmethod
    def handle_meity_site(session, url, headers):
        """Special handling for Ministry of Electronics & IT"""
        headers.update({
            'Referer': 'https://www.meity.gov.in/',
            'Cookie': 'has_js=1; _ga=GA1.3.1234567890.1234567890'
        })
        
        # MeitY often uses Drupal, which needs session establishment
        homepage = 'https://www.meity.gov.in/'
        try:
            # Visit homepage first
            session.get(homepage, headers=headers, timeout=10)
            time.sleep(1)
        except:
            pass
        
        return session.get(url, headers=headers, timeout=30)
    
    @staticmethod
    def handle_sebi_site(session, url, headers):
        """Special handling for SEBI"""
        # SEBI uses ASP.NET with session state
        headers.update({
            'Referer': 'https://www.sebi.gov.in/',
            'Cookie': 'ASP.NET_SessionId=dummy123; has_js=1',
            'X-MicrosoftAjax': 'Delta=true'
        })
        
        # Try to get initial session
        try:
            homepage_response = session.get('https://www.sebi.gov.in/', headers=headers, timeout=15)
            # Extract any session cookies
            if homepage_response.cookies:
                session.cookies.update(homepage_response.cookies)
            time.sleep(1.5)
        except:
            pass
        
        return session.get(url, headers=headers, timeout=30)
    
    @staticmethod
    def handle_trai_site(session, url, headers):
        """Special handling for TRAI"""
        headers.update({
            'Referer': 'https://www.trai.gov.in/',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
        })
        
        # TRAI sometimes blocks based on user agent
        headers['User-Agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        
        return session.get(url, headers=headers, timeout=30, allow_redirects=True)
    
    @staticmethod
    def handle_cert_in_site(session, url, headers):
        """Special handling for CERT-In"""
        # CERT-In has strict security
        headers.update({
            'Referer': 'https://www.cert-in.org.in/',
            'Origin': 'https://www.cert-in.org.in',
            'Sec-Fetch-Site': 'same-origin',
            'Sec-Fetch-Mode': 'navigate'
        })
        
        # CERT-In uses parameter-based URLs
        if 'pageid=' in url:
            # Ensure proper encoding
            from urllib.parse import quote
            url = url.replace(' ', '%20')
        
        return session.get(url, headers=headers, timeout=30, verify=True)
    
    @staticmethod
    def handle_generic_gov_site(session, url, headers):
        """Generic handler for government sites"""
        domain = urlparse(url).netloc
        
        headers.update({
            'Referer': f'https://{domain}/',
            'Origin': f'https://{domain}',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        })
        
        # Try to establish session first
        try:
            homepage = f'https://{domain}/'
            session.get(homepage, headers=headers, timeout=10)
            time.sleep(1)
        except:
            pass
        
        return session.get(url, headers=headers, timeout=30)

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

    # Difficult domains that need Selenium
    SELENIUM_REQUIRED_DOMAINS = [
        'business-standard.com',
        'moneycontrol.com',
        'financialexpress.com',
        'zeebiz.com'
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
        # The Hindu feeds
        'https://www.thehindu.com/sci-tech/technology/feeder/default.rss': [
            'https://www.thehindu.com/sci-tech/technology/?service=rss',
            'https://www.thehindu.com/sci-tech/technology/'
        ],
        # LiveMint feeds
        'https://www.livemint.com/rss/technology': [
            'https://www.livemint.com/technology/news.rss',
            'https://www.livemint.com/technology/'
        ],
        # Economic Times feeds
        'https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1286551326.cms': [
            'https://economictimes.indiatimes.com/rssfeedstopstories.cms',
            'https://economictimes.indiatimes.com/news/economy/policy'
        ]
    }

    # Policy keywords for relevance boosting
    POLICY_KEYWORDS = {
        'high_relevance': [
            'policy', 'regulation', 'bill', 'act', 'law', 'ministry', 'government',
            'notification', 'amendment', 'cabinet', 'parliament', 'supreme court',
            'legislation', 'regulatory', 'compliance', 'niti aayog', 'rbi', 'sebi',
            'trai', 'circular', 'ordinance', 'statute', 'directive', 'mandate'
        ],
        'medium_relevance': [
            'reform', 'initiative', 'program', 'scheme', 'mission', 'project',
            'framework', 'strategy', 'roadmap', 'guideline', 'committee', 'commission',
            'panel', 'task force', 'authority', 'board', 'council', 'fund', 'subsidy',
            'tax', 'budget', 'fiscal', 'monetary', 'development', 'governance'
        ]
    }

    # Policy sectors for classification
    POLICY_SECTORS = {
        'Technology Policy': [
            'technology', 'digital', 'it', 'telecom', 'telecommunications', 'data',
            'privacy', 'cyber', 'cybersecurity', 'internet', 'ecommerce', 'e-commerce',
            'social media', 'ai', 'artificial intelligence', 'ml', 'machine learning',
            'blockchain', 'crypto', 'cryptocurrency', 'fintech', 'startup', 'innovation'
        ],
        'Economic Policy': [
            'economy', 'economic', 'finance', 'financial', 'banking', 'investment',
            'trade', 'commerce', 'business', 'industry', 'industrial', 'manufacturing',
            'msme', 'gdp', 'inflation', 'fiscal', 'monetary', 'budget', 'tax', 'taxation',
            'subsidy', 'export', 'import', 'customs', 'tariff', 'rbi', 'sebi', 'market'
        ],
        'Healthcare Policy': [
            'health', 'healthcare', 'medical', 'medicine', 'hospital', 'doctor', 'patient',
            'disease', 'vaccination', 'vaccine', 'pandemic', 'epidemic', 'pharma',
            'pharmaceutical', 'insurance', 'ayushman', 'nhm', 'drug', 'ayush', 'wellness'
        ],
        'Environmental Policy': [
            'environment', 'environmental', 'climate', 'climate change', 'pollution',
            'sustainable', 'sustainability', 'green', 'renewable', 'solar', 'wind',
            'emission', 'carbon', 'forest', 'wildlife', 'biodiversity', 'water',
            'conservation', 'waste', 'ecology', 'ecological', 'clean energy'
        ],
        'Education Policy': [
            'education', 'educational', 'school', 'college', 'university', 'academic',
            'student', 'teacher', 'teaching', 'learning', 'pedagogy', 'curriculum',
            'nep', 'skill', 'scholarship', 'ugc', 'aicte', 'research', 'literacy'
        ],
        'Agricultural Policy': [
            'agriculture', 'agricultural', 'farmer', 'farming', 'crop', 'msp',
            'rural', 'irrigation', 'fertilizer', 'pesticide', 'seed', 'food',
            'security', 'fci', 'organic', 'horticulture', 'livestock'
        ],
        'Foreign Policy': [
            'foreign', 'diplomatic', 'diplomacy', 'international', 'bilateral',
            'multilateral', 'global', 'regional', 'treaty', 'pact', 'agreement',
            'cooperation', 'relation', 'embassy', 'ambassador', 'consul', 'visa',
            'border', 'territory', 'dispute', 'un', 'united nations'
        ],
        'Constitutional & Legal': [
            'constitution', 'constitutional', 'judiciary', 'judicial', 'court',
            'supreme court', 'high court', 'judge', 'justice', 'legal', 'law',
            'legislation', 'amendment', 'right', 'fundamental', 'directive',
            'principle', 'verdict', 'judgment', 'statute', 'writ', 'petition'
        ],
        'Defense & Security': [
            'defense', 'defence', 'security', 'military', 'army', 'navy', 'air force',
            'strategic', 'weapon', 'warfare', 'terrorist', 'terrorism', 'intelligence',
            'border', 'sovereignty', 'territorial', 'nuclear', 'missile', 'warfare'
        ],
        'Social Policy': [
            'social', 'welfare', 'scheme', 'poverty', 'employment', 'unemployment',
            'labor', 'labour', 'worker', 'pension', 'retirement', 'gender', 'women',
            'child', 'minority', 'scheduled caste', 'scheduled tribe', 'obc',
            'backward', 'disability', 'senior', 'elderly', 'housing', 'urban'
        ],
        'Governance & Administration': [
            'governance', 'administration', 'bureaucracy', 'civil service',
            'reform', 'transparency', 'accountability', 'corruption', 'ethics',
            'electoral', 'election', 'e-governance', 'local', 'municipal',
            'panchayat', 'state government', 'centre-state', 'federalism'
        ],
        'Policy Analysis': [ # Added for think tank and opinion pieces
            'analysis', 'opinion', 'research', 'report', 'study', 'think tank',
            'commentary', 'editorial', 'perspective', 'deep dive', 'explainer'
        ]
    }

    # Source reliability ratings
    SOURCE_RELIABILITY = {
        # Government sources - Very High reliability for policy content
        'Press Information Bureau': 5,
        'PIB': 5,
        'RBI': 5,
        'Reserve Bank of India': 5,
        'Supreme Court of India': 5,
        'Ministry of': 5,  # Any ministry
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

        # Legal news sources - High reliability for legal policy
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

    def initialize_feed_monitor(self):
        """Initialize feed health monitoring"""
        self.feed_monitor = FeedHealthMonitor(Config.DB_FILE)
        
        # Ensure the feed_health_v2 table exists
        try:
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
                logger.info("Feed health monitoring table initialized")
        except sqlite3.Error as e:
            logger.error(f"Error creating feed health table: {e}")
        
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
    """Enhanced article class with improved metadata and relevance scoring"""

    def __init__(self, title, url, source, category, published_date=None, summary=None, content=None, tags=None):
        self.title = title
        self.url = url
        self.source = source
        self.category = category
        self.published_date = self._parse_date(published_date)
        self.summary = summary or ""
        self.content = content or ""
        self.tags = tags or []
        self.keywords = []
        self.content_hash = self._generate_hash()

        # Initialize importance and timeliness
        self.importance = 0.0
        self.timeliness = 0.0

        # Relevance scoring - initialized at 0 and calculated later
        self.relevance_scores = {
            'policy_relevance': 0,  # Based on policy keywords
            'source_reliability': 0,  # Based on source reputation
            'recency': 0,  # Based on how recent the article is
            'sector_specificity': 0,  # How strongly it matches a specific sector
            'overall': 0  # Weighted combination of above scores
        }

        # Extended metadata
        self.metadata = {
            'source_type': self._determine_source_type(),
            'content_type': self._determine_content_type(),
            'word_count': len(self.title.split()) + len(self.summary.split()),
            'entities': {},  # To be populated with named entity recognition
            'sentiment': 0,  # Neutral by default
            'processed': False  # Flag to indicate if NLP processing is done
        }

    def calculate_importance(self):
        """Calculate importance based on relevance scores"""
        # This is a weighted combination of various factors
        self.importance = (
            self.relevance_scores['policy_relevance'] * 0.4 +
            self.relevance_scores['source_reliability'] * 0.3 +
            self.relevance_scores['sector_specificity'] * 0.3
        )
        return self.importance

    def calculate_timeliness(self):
        """Calculate timeliness based on published date"""
        if not self.published_date:
            self.timeliness = 0.0
            return self.timeliness

        current_time = datetime.now()
        hours_diff = (current_time - self.published_date).total_seconds() / 3600

        # Timeliness score decreases with age
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

    def _generate_hash(self):
        """Generate unique hash for article to prevent duplicates within a single run
        but allow the same article to be collected in future runs if it has updates"""
        # Base content for hash - title and URL are usually unique identifiers
        content = f"{self.title}{self.url}".lower()

        # Create a unique hash for this run only
        run_hash = hashlib.md5(content.encode()).hexdigest()

        # For database storage, add a more unique identifier with publication date
        if hasattr(self, 'published_date') and self.published_date:
            # Try to convert to ISO format if it's a datetime
            date_str = self.published_date.isoformat() if hasattr(self.published_date, 'isoformat') else str(self.published_date)
            self.storage_hash = hashlib.md5(f"{content}{date_str}".encode()).hexdigest()
        else:
            # Fall back to regular hash if no date
            self.storage_hash = run_hash

        return run_hash  # Return only the run hash for in-memory duplicate detection

    def _parse_date(self, date_string):
        """Parse various date formats - returns naive datetime"""
        if not date_string:
            return datetime.now()

        if isinstance(date_string, datetime):
            if date_string.tzinfo is not None:
                return date_string.replace(tzinfo=None)
            return date_string

        try:
            # dateutil.parser is very robust and can replace the manual loop.
            dt = date_parser.parse(date_string)
            return dt.replace(tzinfo=None) # Return naive datetime
        except (ValueError, TypeError):
            logger.warning(f"Could not parse date string: {date_string}. Using current time.")
            return datetime.now()

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
        """Calculate various relevance scores for the article"""
        # Initialize all variables at the start
        policy_relevance = 0.0
        source_reliability = 0.0
        recency = 0.0
        sector_specificity = 0.0
        overall = 0.0

        try:
            # Get the combined text for analysis
            text = f"{self.title} {self.summary} {self.content}".lower()

            # 1. Policy relevance score (0-1)
            # Check for high relevance keywords
            high_relevance_matches = sum(1 for keyword in Config.POLICY_KEYWORDS['high_relevance'] if keyword.lower() in text)
            if high_relevance_matches > 0:
                policy_relevance += min(0.7, high_relevance_matches * 0.1)  # Up to 0.7 from high relevance terms

            # Check for medium relevance keywords
            medium_relevance_matches = sum(1 for keyword in Config.POLICY_KEYWORDS['medium_relevance'] if keyword.lower() in text)
            if medium_relevance_matches > 0:
                policy_relevance += min(0.3, medium_relevance_matches * 0.05)  # Up to 0.3 from medium relevance terms

            # Cap at 1.0
            policy_relevance = min(1.0, policy_relevance)

            # 2. Source reliability score (0-1)
            for source_name, reliability in Config.SOURCE_RELIABILITY.items():
                if source_name.lower() in self.source.lower():
                    source_reliability = reliability / 5.0  # Normalize to 0-1 scale
                    break

            # Default reliability if not found
            if source_reliability == 0:
                source_reliability = 0.5  # Moderate reliability by default

            # 3. Recency score (0-1)
            current_time = datetime.now()
            if hasattr(self, 'published_date') and self.published_date:
                # Ensure both datetimes are naive
                if isinstance(self.published_date, datetime):
                    if hasattr(self.published_date, 'tzinfo') and self.published_date.tzinfo is not None:
                        pub_date = self.published_date.replace(tzinfo=None)
                    else:
                        pub_date = self.published_date
                else:
                    pub_date = current_time

                hours_diff = (current_time - pub_date).total_seconds() / 3600

                if hours_diff <= 24:
                    recency = 1.0  # Last 24 hours - maximum recency
                elif hours_diff <= 72:
                    recency = 0.8  # 1-3 days
                elif hours_diff <= 168:
                    recency = 0.6  # 3-7 days
                elif hours_diff <= 336:
                    recency = 0.4  # 7-14 days
                elif hours_diff <= 720:
                    recency = 0.2  # 14-30 days
                else:
                    recency = 0.1  # Older than 30 days
            else:
                recency = 0.5  # Default if no date available

            # 4. Sector specificity score (0-1)
            sector_scores = {}
            for sector, keywords in Config.POLICY_SECTORS.items():
                matches = sum(1 for keyword in keywords if keyword.lower() in text)
                density = matches / len(keywords)
                sector_scores[sector] = min(1.0, density * 2)  # Scale up but cap at 1.0

            # Get the highest sector match
            if sector_scores:
                sector_specificity = max(sector_scores.values())
                # Update category if we found a better match than the original classification
                best_sector = max(sector_scores.items(), key=lambda x: x[1])
                if best_sector[1] > 0.3 and best_sector[0] != self.category:
                    self.category = best_sector[0]
            else:
                sector_specificity = 0.3  # Default value if no sectors matched

            # 5. Calculate overall score with weighted components
            overall = (
                policy_relevance * 0.4 +  # Policy relevance is most important
                source_reliability * 0.3 +  # Source reliability is second
                recency * 0.2 +  # Recency is third
                sector_specificity * 0.1  # Sector specificity is fourth
            )

            # Update the article's relevance scores
            self.relevance_scores = {
                'policy_relevance': round(policy_relevance, 2),
                'source_reliability': round(source_reliability, 2),
                'recency': round(recency, 2),
                'sector_specificity': round(sector_specificity, 2),
                'overall': round(overall, 2)
            }

            return self.relevance_scores

        except Exception as e:
            logger.error(f"Error calculating relevance scores: {str(e)}", exc_info=True)
            # Return default scores on error
            self.relevance_scores = {
                'policy_relevance': 0.0,
                'source_reliability': 0.5,
                'recency': 0.5,
                'sector_specificity': 0.3,
                'overall': 0.3
            }
            return self.relevance_scores

    def extract_keywords(self, max_keywords: int = 10) -> List[str]:
        """Extract important keywords from the article with fallback mechanism"""
        if not self.content and not self.summary:
            self.keywords = []
            return self.keywords

        # Combine title and summary for small articles, otherwise use full content
        text = f"{self.title} {self.summary}" if not self.content else f"{self.title} {self.content}"

        try:
            if NLTK_AVAILABLE:
                # Tokenize and convert to lowercase
                tokens = word_tokenize(text.lower())

                # Remove stopwords and short words
                stop_words = set(stopwords.words('english'))
                tokens = [word for word in tokens if word.isalpha() and word not in stop_words and len(word) > 3]

                # Get frequency distribution
                freq_dist = Counter(tokens)

                # Get the most common keywords
                self.keywords = [word for word, freq in freq_dist.most_common(max_keywords)]
            else:
                # Fallback to simple word splitting if NLTK not available
                words = text.lower().split()
                # Remove very short words and duplicates
                words = list(set([w for w in words if len(w) > 3]))
                self.keywords = words[:max_keywords]

        except Exception as e:
            logger.warning(f"Error extracting keywords: {str(e)}")
            # Fallback to simple word splitting
            words = text.lower().split()
            # Remove very short words and duplicates
            words = list(set([w for w in words if len(w) > 3]))
            self.keywords = words[:max_keywords]

        return self.keywords

    def categorize_article(self, title: str, summary: str, query: str = None) -> str:
        """Categorize article based on content using enhanced classification"""
        text = (title + " " + summary).lower()

        # First check if query provides a hint
        if query:
            query = query.lower()
            # Use Config.POLICY_SECTORS instead of Config.SECTOR_KEYWORDS
            for sector, keywords in Config.POLICY_SECTORS.items():
                if any(keyword.lower() in query for keyword in keywords):
                    return sector

        # Check for direct sector matches
        sector_scores = {}
        # Use Config.POLICY_SECTORS instead of Config.SECTOR_KEYWORDS
        for sector, keywords in Config.POLICY_SECTORS.items():
            score = sum(1 for keyword in keywords if keyword.lower() in text)
            sector_scores[sector] = score

        # Find sector with highest score
        max_score = 0
        best_sector = "Policy News"  # Default

        for sector, score in sector_scores.items():
            if score > max_score:
                max_score = score
                best_sector = sector

        # Require a minimum match score for specific categorization
        if max_score < 2:
            # If low match confidence, use broader categories based on patterns
            if any(word in text for word in ['court', 'legal', 'judge', 'judgment', 'supreme', 'high court']):
                return "Constitutional & Legal"
            elif any(word in text for word in ['economy', 'economic', 'finance', 'fiscal', 'monetary', 'tax']):
                return "Economic Policy"
            elif any(word in text for word in ['technology', 'digital', 'it ', 'cyber', 'tech', 'internet']):
                return "Technology Policy"
            elif any(word in text for word in ['environment', 'climate', 'pollution', 'green', 'sustainable']):
                return "Environmental Policy"
            elif any(word in text for word in ['health', 'hospital', 'medical', 'disease', 'treatment', 'patient']):
                return "Healthcare Policy"
            elif any(word in text for word in ['education', 'school', 'university', 'student', 'teacher']):
                return "Education Policy"
            elif any(word in text for word in ['agriculture', 'farm', 'crop', 'rural', 'farmer']):
                return "Agricultural Policy"
            elif any(word in text for word in ['labor', 'labour', 'employment', 'job', 'worker', 'workforce']):
                return "Social Policy"
            elif any(word in text for word in ['defense', 'defence', 'security', 'military', 'armed forces']):
                return "Defense & Security"
            else:
                return "Policy News"  # Default catch-all

        return best_sector

    def assign_tags(self, title, summary):
        """Assign tags to articles based on content with improved classification"""
        tags = []
        full_text = f"{title} {summary}".lower()

        # Tag rules with clearer patterns
        tag_rules = {
            'Policy Analysis': [
                'analysis', 'study', 'report', 'research', 'survey', 'findings',
                'data analysis', 'impact assessment', 'evaluation', 'review'
            ],
            'Legislative Updates': [
                'bill', 'act', 'parliament', 'amendment', 'legislation',
                'rajya sabha', 'lok sabha', 'ordinance', 'draft bill'
            ],
            'Regulatory Changes': [
                'regulation', 'rules', 'guidelines', 'notification', 'circular',
                'compliance', 'enforcement', 'regulatory', 'mandate'
            ],
            'Court Rulings': [
                'court', 'supreme', 'judicial', 'judgment', 'verdict', 'tribunal',
                'hearing', 'petition', 'bench', 'justice', 'order'
            ],
            'Government Initiatives': [
                'scheme', 'program', 'initiative', 'launch', 'implementation',
                'project', 'mission', 'flagship', 'campaign'
            ],
            'Policy Debate': [
                'debate', 'discussion', 'consultation', 'feedback', 'opinion',
                'perspective', 'stakeholder', 'controversy', 'criticism'
            ],
            'International Relations': [
                'bilateral', 'diplomatic', 'foreign', 'international', 'global',
                'relation', 'cooperation', 'treaty', 'agreement', 'pact'
            ],
            'Digital Governance': [
                'digital', 'online', 'internet', 'tech', 'platform', 'data',
                'privacy', 'cyber', 'algorithm', 'ai', 'artificial intelligence'
            ],
            'Budget & Finance': [
                'budget', 'fiscal', 'finance', 'tax', 'taxation', 'revenue',
                'expenditure', 'subsidy', 'financial', 'funding'
            ],
            'Development & Reforms': [
                'reform', 'development', 'modernization', 'transformation',
                'improvement', 'upgrade', 'overhaul', 'restructuring'
            ]
        }

        # Advanced tag assignment with weighted approach
        for tag, keywords in tag_rules.items():
            # Count how many keywords match
            matches = sum(1 for keyword in keywords if keyword in full_text)

            # Add tag if sufficient matches
            if matches >= 2:
                tags.append(tag)
            # Also add if single strong match found (full keyword present)
            elif matches == 1 and any(f" {keyword} " in f" {full_text} " for keyword in keywords):
                tags.append(tag)

        # Add policy area tags if appropriate
        if 'budget' in full_text or 'economic' in full_text or 'economy' in full_text:
            tags.append('Economic Policy')

        if 'technology' in full_text or 'digital' in full_text or 'tech' in full_text:
            tags.append('Technology Policy')

        if 'health' in full_text or 'healthcare' in full_text or 'medical' in full_text:
            tags.append('Healthcare Policy')

        # Ensure at least one tag
        if not tags:
            # Add a default tag based on keywords
            if any(word in full_text for word in ['policy', 'government', 'ministry', 'official']):
                tags.append('Policy Development')
            else:
                tags.append('Policy News')  # Generic fallback

        # Remove duplicates and limit to 4 tags maximum
        tags = list(dict.fromkeys(tags))  # Remove duplicates while preserving order
        return tags[:4]

    def cache_articles(self, articles):
        """Cache articles to file for backup"""
        try:
            cache_file = os.path.join(Config.CACHE_DIR, 'articles_cache.json')
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump([article.to_dict() for article in articles], f)
            logger.info(f"Cached {len(articles)} articles to {cache_file}")
        except Exception as e:
            logger.error(f"Error caching articles: {str(e)}")

    def load_cached_articles(self):
        """Load cached articles as fallback"""
        articles = []
        try:
            cache_file = os.path.join(Config.CACHE_DIR, 'articles_cache.json')
            if os.path.exists(cache_file):
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)

                for article_data in cached_data:
                    # Create article from cached data
                    article = NewsArticle(
                        title=article_data['title'],
                        url=article_data['url'],
                        source=article_data['source'],
                        category=article_data['category'],
                        published_date=article_data['published_date'],
                        summary=article_data['summary'],
                        content=article_data.get('content', ''),
                        tags=article_data['tags']
                    )

                    # Set additional properties
                    article.content_hash = article_data['content_hash']
                    article.keywords = article_data.get('keywords', [])
                    article.relevance_scores = article_data.get('relevance_scores', {
                        'policy_relevance': 0,
                        'source_reliability': 0,
                        'recency': 0,
                        'sector_specificity': 0,
                        'overall': 0
                    })
                    article.metadata = article_data.get('metadata', {})

                    articles.append(article)

                logger.info(f"Loaded {len(articles)} articles from cache")
        except Exception as e:
            logger.error(f"Error loading cached articles: {str(e)}")

        return articles

    def export_articles_to_json(self, articles: List[NewsArticle], filename: Optional[str] = None) -> Optional[str]:
        """Export articles to JSON file"""
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(Config.EXPORT_DIR, f"policyradar_export_{timestamp}.json")

        try:
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump([article.to_dict() for article in articles], f, indent=2)
            logger.info(f"Exported {len(articles)} articles to {filename}")
            return filename
        except Exception as e:
            logger.error(f"Error exporting articles to JSON: {str(e)}")
            return None

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

    def get_user_agent(self):
        """Return a random user agent from the list"""
        return random.choice(Config.USER_AGENTS)

    def is_policy_relevant(self, article):
        """Check if an article is policy-relevant based on keywords and title/summary"""
        # Combine title and summary for analysis
        text = f"{article.title} {article.summary}".lower()

        # Check for policy keywords
        policy_keywords = ['policy', 'regulation', 'law', 'ministry', 'government',
                          'notification', 'amendment', 'cabinet', 'parliament',
                          'legislation', 'regulatory', 'compliance']

        # Count matches
        matches = sum(1 for keyword in policy_keywords if keyword in text)

        # Consider relevant if has at least 1 match
        return matches > 0

    def sort_articles_by_relevance(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Sort articles using a sophisticated relevance algorithm"""
        # Define source quality tiers
        source_tiers = {
            'tier1': ['pib', 'meity', 'rbi', 'supreme court', 'sebi', 'ministry'],  # Official sources
            'tier2': ['prs', 'medianama', 'livelaw', 'bar and bench', 'iff', 'orf'],  # Specialized policy sources
            'tier3': ['the hindu', 'indian express', 'economic times', 'livemint', 'business standard'],  # Major publications
            'tier4': ['google news', 'the wire', 'scroll', 'print']  # Aggregators and smaller publications
        }

        # Calculate source tier bonus for each article
        for article in articles:
            # Ensure article has relevance scores calculated
            if article.relevance_scores['overall'] == 0:
                article.calculate_relevance_scores()

            # Calculate importance and timeliness if not already done
            if not hasattr(article, 'importance') or article.importance == 0:
                article.calculate_importance()
            if not hasattr(article, 'timeliness') or article.timeliness == 0:
                article.calculate_timeliness()

            # Default to lowest tier
            article.source_tier = 4
            article_source = article.source.lower()

            # Check for source in each tier
            for tier, sources in source_tiers.items():
                if any(source in article_source for source in sources):
                    article.source_tier = int(tier[-1])  # Extract tier number
                    break

            # Calculate combined relevance score (0-1 scale)
            # Formula: 60% importance + 30% timeliness + 10% source tier bonus
            tier_bonus = (5 - article.source_tier) / 4  # Convert to 0-1 scale (tier1=1, tier4=0.25)
            article.relevance_score = (0.6 * article.importance) + (0.3 * article.timeliness) + (0.1 * tier_bonus)

        # Sort by combined relevance score
        return sorted(articles, key=lambda x: x.relevance_score, reverse=True)

    def _create_resilient_session(self):
        """Create a requests session with maximum compatibility for older government sites."""
        logger.info("Creating resilient session with enhanced SSL compatibility")
        
        session = requests.Session()
        
        # Enhanced SSL adapter to handle weak ciphers and old protocols
        class SSLAdapter(HTTPAdapter):
            def init_poolmanager(self, *args, **kwargs):
                ctx = ssl.create_default_context()
                
                # Completely disable SSL verification
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                # Allow ALL ciphers including weak ones (needed for old government sites)
                ctx.set_ciphers('ALL:@SECLEVEL=0')
                
                # Allow old SSL/TLS versions
                ctx.options &= ~ssl.OP_NO_SSLv3
                ctx.options &= ~ssl.OP_NO_TLSv1
                ctx.options &= ~ssl.OP_NO_TLSv1_1
                
                # Set minimum protocol version to SSLv3
                ctx.minimum_version = ssl.TLSVersion.SSLv3
                
                kwargs['ssl_context'] = ctx
                return super().init_poolmanager(*args, **kwargs)

        retry_strategy = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "HEAD"],
            raise_on_status=False
        )
        
        # Mount the custom adapter to handle all HTTPS requests
        adapter = SSLAdapter(max_retries=retry_strategy)
        session.mount("https://", adapter)
        session.mount("http://", HTTPAdapter(max_retries=retry_strategy))
        
        # Set default headers
        session.headers.update({
            'User-Agent': self.get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
        
        # Disable SSL verification at session level as well
        session.verify = False
        
        return session

    def get_html_with_selenium(self, url: str) -> Optional[str]:
        """Uses a headless Selenium browser to fetch page source for protected sites."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.service import Service
            from selenium.webdriver.chrome.options import Options
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError:
            logger.error("Selenium not installed. Run: pip install selenium")
            return None

        logger.info(f"Using Selenium for protected site: {url}")

        # Try to find chromedriver in common locations
        chrome_driver_paths = [
            '/usr/local/bin/chromedriver',
            '/usr/bin/chromedriver',
            './chromedriver',
            'chromedriver',
            # Add your specific path here if needed
        ]
        
        chrome_driver_path = None
        for path in chrome_driver_paths:
            if os.path.exists(path):
                chrome_driver_path = path
                break
        
        if not chrome_driver_path:
            logger.error("ChromeDriver not found. Please install it and update the path.")
            return None

        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument(f"user-agent={self.get_user_agent()}")
        
        # Additional options for stability
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)

        driver = None
        try:
            service = Service(executable_path=chrome_driver_path)
            driver = webdriver.Chrome(service=service, options=chrome_options)
            
            # Set page load timeout
            driver.set_page_load_timeout(30)
            
            # Navigate to the page
            driver.get(url)
            
            # Wait for content to load
            WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Additional wait for dynamic content
            time.sleep(3)
            
            # Get page source
            page_source = driver.page_source
            return page_source
            
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

    def initialize_feed_monitor(self):
        """Initialize feed health monitoring"""
        self.feed_monitor = FeedHealthMonitor(Config.DB_FILE)
    
    def get_healthy_feeds(self):
        """Get only healthy/active feeds"""
        return self.feed_monitor.get_active_feeds(self.feeds)

    def update_feed_health_status(self, feed_url, success, error_type=None):
        """Update feed health after fetch attempt"""
        if hasattr(self, 'feed_monitor'):
            self.feed_monitor.update_feed_health(feed_url, success, error_type)

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
            ("Ministry of Finance - Orders", "https://doe.gov.in/orders-circulars", "Economic Policy"),
            ("Department of Economic Affairs", "https://dea.gov.in/recent-update", "Economic Policy"),
            ("Department of Economic Affairs - Budget", "https://dea.gov.in/budgetdivision/notifications", "Economic Policy"),
            # ("Ministry of Corporate Affairs", "https://www.mca.gov.in/MinistryV2/rss.html", "Economic Policy"), # Removed - MCA RSS not working
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
            ("India Budget Portal", "https://www.indiabudget.gov.in/", "Economic Policy"),  # Fixed - now points to HTML page
            ("Economic Survey Portal", "https://www.indiabudget.gov.in/economicsurvey/", "Economic Policy"),  # Fixed URL
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
            # Removed dead URLs: NSC Secretariat, RAW
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
            ("Lawctopus - Law Careers", "https://www.lawctopus.com/feed/", "Constitutional & Legal"),
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
        """Fetch Indian policy news from Google News RSS with more targeted queries"""
        all_articles = []

        # Policy-focused search queries (general)
        general_queries = [
            "India policy government",
            "India legislation law regulation",
            "India policy reform",
            "India policy implementation",
            "India policy impact",
            "India regulation compliance",
            "India budget policy fiscal",
            "India ministry notification",
            "India cabinet decision",
            "India supreme court judgement policy",
            "India parliamentary proceedings",
            "India policy directive guideline"
        ]

        # Sector-specific policy queries
        sector_queries = [
            "India technology policy digital",
            "India economic policy financial",
            "India education policy",
            "India health policy healthcare",
            "India environment policy climate",
            "India agriculture policy farm",
            "India energy policy",
            "India foreign policy diplomatic",
            "India defense policy security",
            "India transportation policy infrastructure",
            "India social welfare policy",
            "India labor policy employment"
        ]

        # Site-specific policy queries (targeting quality sources)
        site_queries = [
            "site:thehindu.com India policy",
            "site:indianexpress.com India policy",
            "site:economictimes.indiatimes.com policy",
            "site:livemint.com policy regulation",
            "site:business-standard.com policy",
            "site:pib.gov.in policy",
            "site:prsindia.org policy legislation",
            "site:orfonline.org policy analysis",
            "site:cprindia.org policy research",
            "site:livelaw.in policy legal",
            "site:barandbench.com policy judgment",
            "site:medianama.com technology policy"
        ]

        # Combine all queries
        all_queries = general_queries + sector_queries + site_queries

        logger.info(f"Fetching policy news from Google News RSS with {len(all_queries)} search queries")

        # Process each query
        for query in all_queries:
            encoded_query = urllib.parse.quote_plus(query)
            url = f"https://news.google.com/rss/search?q={encoded_query}&hl=en-IN&gl=IN&ceid=IN:en"

            try:
                # Use a browser-like request
                headers = {
                    'User-Agent': self.get_user_agent(),
                    'Accept': 'application/rss+xml, application/atom+xml, text/xml, */*;q=0.1',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Referer': 'https://news.google.com/',
                    'Connection': 'keep-alive'
                }

                response = self.session.get(
                    url,
                    headers=headers,
                    timeout=20,
                    verify=False,
                    allow_redirects=True
                )

                if response.status_code == 200:
                    feed = feedparser.parse(response.content)

                    if feed.entries:
                        logger.info(f"Found {len(feed.entries)} Google News articles for query: {query}")

                        # Process entries
                        for entry in feed.entries[:15]:  # Increased limit per query for better coverage
                            title = entry.title
                            link = entry.link

                            # Extract source and date
                            source = entry.source.title if hasattr(entry, 'source') and hasattr(entry.source, 'title') else "Google News"
                            published = entry.published if hasattr(entry, 'published') else None

                            # Create summary from description
                            summary = ""
                            if hasattr(entry, 'description'):
                                # Clean HTML from description
                                soup = BeautifulSoup(entry.description, 'html.parser')
                                summary = soup.get_text().strip()

                            # Create a preliminary article with a default category.
                            article = NewsArticle(
                                title=title,
                                url=link,
                                source=source,
                                category="Policy News", # Default category
                                published_date=published,
                                summary=summary
                            )

                            # Now, use the article's own method to determine the best category.
                            article.category = article.categorize_article(title, summary, query)
                            article.tags = article.assign_tags(title, summary)
                            
                            article.calculate_relevance_scores()

                            # Only accept articles with reasonable relevance
                            if article.relevance_scores['overall'] >= 0.2:
                                # Add if not duplicate and has sufficient relevance
                                if article.content_hash not in self.article_hashes:
                                    self.article_hashes.add(article.content_hash)
                                    all_articles.append(article)
                                    self.save_article_to_db(article)

                                    # Stop if we reached the limit
                                    if len(all_articles) >= max_articles:
                                        break
                            else:
                                self.statistics['low_relevance_articles'] += 1

                        # Stop if we reached the limit
                        if len(all_articles) >= max_articles:
                            break
                    else:
                        logger.warning(f"No Google News results for query: {query}")

                else:
                    logger.warning(f"Failed to fetch Google News for query '{query}': Status {response.status_code}")

            except Exception as e:
                logger.error(f"Error fetching Google News for query '{query}': {e}")

            # Add a short delay between queries to avoid rate limiting
            time.sleep(random.uniform(0.5, 1.0))

        self.statistics['google_news_articles'] = len(all_articles)
        logger.info(f"Found {len(all_articles)} articles from Google News RSS")
        return all_articles

    def direct_scrape_reliable_sources(self):
        """Directly scrape the most reliable Indian policy news websites with updated selectors."""
        articles = []

        reliable_sources = [
            {
                "name": "PRS Legislative Research",
                "url": "https://prsindia.org/bills",
                "category": "Constitutional & Legal",
                "selectors": {
                    "article": ".bill-listing-item-container",
                    "title": ".title-container a",
                    "summary": ".field-name-field-bill-summary",
                    "link": ".title-container a"
                }
            },
            {
                "name": "PIB - Press Release",
                "url": "https://pib.gov.in/AllRelease.aspx",
                "category": "Governance & Administration",
                "selectors": {
                    "article": "ul.releases li",
                    "title": "a",
                    "summary": ".background-gray",
                    "link": "a"
                }
            },
            {
                "name": "TRAI Press Releases",
                "url": "https://trai.gov.in/notifications/press-release",
                "category": "Technology Policy",
                "selectors": {
                    "article": ".views-row",
                    "title": "a",
                    "summary": ".views-field-field-creation-date",
                    "link": "a"
                }
            },
            {
                "name": "Centre for Policy Research",
                "url": "https://cprindia.org/",
                "category": "Policy Analysis",
                "selectors": {
                    "article": ".featured-insight, .insights-card, article",
                    "title": "h2, h3, .card-title",
                    "summary": "p, .card-text",
                    "link": "a"
                }
            },
            {
                "name": "Observer Research Foundation",
                "url": "https://www.orfonline.org/research/",
                "category": "Policy Analysis",
                "selectors": {
                    "article": ".post-listing .post-item, .research-item",
                    "title": "h2, h3, .title",
                    "summary": "p, .excerpt",
                    "link": "a"
                }
            },
            {
                "name": "The Hindu - Policy & Issues",
                "url": "https://www.thehindu.com/news/national/",
                "category": "Governance & Administration",
                "selectors": {
                    "article": ".element.story-card, .element.also-read-card, .story-card-cover",
                    "title": "h2.title > a, h3.title-story > a, a.story-card-cover-story__title",
                    "summary": "p, .story-card-summary",
                    "link": "a"
                }
            },
            {
                "name": "Indian Express - Governance",
                "url": "https://indianexpress.com/section/india/politics/",
                "category": "Governance & Administration",
                "selectors": {
                    "article": "article, .articles > div, .ie-first-story",
                    "title": "h2, h3, .title, .heading",
                    "summary": "p, .synopsis, .excerpt",
                    "link": "a"
                }
            },
            {
                "name": "Economic Times Policy",
                "url": "https://economictimes.indiatimes.com/news/economy/policy",
                "category": "Economic Policy",
                "selectors": {
                    "article": "div.eachStory",
                    "title": "h3 > a",
                    "summary": "p",
                    "link": "a"
                }
            },
            {
                "name": "LiveMint Economy",
                "url": "https://www.livemint.com/economy",
                "category": "Economic Policy",
                "selectors": {
                    "article": ".cardHolder, article.card, div.list-view-card",
                    "title": "h2 a, h6 a",
                    "summary": ".summary, p",
                    "link": "a"
                }
            },
            {
                "name": "MediaNama",
                "url": "https://www.medianama.com/category/policy/",
                "category": "Technology Policy",
                "selectors": {
                    "article": "article, .post, .grid-post",
                    "title": "h2, h3, .entry-title",
                    "summary": "p, .entry-content p:first-of-type",
                    "link": "a"
                }
            },
            {
                "name": "Internet Freedom Foundation",
                "url": "https://internetfreedom.in/category/updates/",
                "category": "Technology Policy",
                "selectors": {
                    "article": "article.post",
                    "title": "h2.entry-title a",
                    "summary": ".entry-content p",
                    "link": "a.more-link"
                }
            },
            {
                "name": "Economic Times Healthcare",
                "url": "https://health.economictimes.indiatimes.com/news/policy",
                "category": "Healthcare Policy",
                "selectors": {
                    "article": ".article-list article, .article-box",
                    "title": "h3, .title, a",
                    "summary": "p, .summary, .excerpt",
                    "link": "a"
                }
            },
            {
                "name": "Down To Earth",
                "url": "https://www.downtoearth.org.in/news",
                "category": "Environmental Policy",
                "selectors": {
                    "article": ".news-item-container, .list-item",
                    "title": "h3, a",
                    "summary": "p",
                    "link": "a"
                }
            },
            {
                "name": "LiveLaw Top Stories",
                "url": "https://www.livelaw.in/top-stories",
                "category": "Constitutional & Legal",
                "selectors": {
                    "article": "div.news-list-item",
                    "title": "h2 > a",
                    "summary": ".news-list-item-author-time",
                    "link": "a"
                }
            },
            {
                "name": "Bar and Bench",
                "url": "https://www.barandbench.com/news",
                "category": "Constitutional & Legal",
                "selectors": {
                    "article": "div.listing-story-wrapper-with-image, div.listing-story-wrapper-without-image",
                    "title": "h2.title-story a",
                    "summary": ".author-time-story",
                    "link": "a"
                }
            }
        ]

        logger.info(f"Performing direct scraping on {len(reliable_sources)} updated source URLs")

        for source in reliable_sources:
            name = source["name"]
            url = source["url"]
            category = source["category"]
            selectors = source["selectors"]

            logger.info(f"Direct scraping {name} at {url}")

            try:
                # Check if this domain requires Selenium
                if self.should_use_selenium(url):
                    html_content = self.get_html_with_selenium(url)
                    if not html_content:
                        logger.warning(f"Selenium failed for {name}, falling back to requests")
                        response = self.session.get(url, timeout=30, verify=False)
                        html_content = response.text
                else:
                    # Use regular requests for normal sites
                    headers = {
                        'User-Agent': self.get_user_agent(),
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Referer': f'https://www.google.com/search?q={name.replace(" ", "+")}+india+policy',
                        'Sec-Fetch-Site': 'cross-site',
                        'Cache-Control': 'max-age=0',
                        'Upgrade-Insecure-Requests': '1'
                    }
                    cookies = {
                        'gdpr': 'true',
                        'euconsent': 'true',
                        'cookieconsent_status': 'accept',
                        'GDPRCookieConsent': 'true'
                    }
                    response = self.session.get(
                        url,
                        headers=headers,
                        cookies=cookies,
                        timeout=30,
                        verify=False,
                        allow_redirects=True
                    )
                    
                    if response.status_code != 200:
                        logger.warning(f"Failed to fetch {name} (Status: {response.status_code})")
                        continue
                        
                    html_content = response.text

                # Parse the HTML content
                soup = BeautifulSoup(html_content, 'html.parser')
                article_elements = soup.select(selectors["article"])

                if article_elements:
                    logger.info(f"Found {len(article_elements)} potential articles using selector: {selectors['article']}")
                    source_articles = []
                    for element in article_elements[:15]:
                        try:
                            title_elem = element.select_one(selectors["title"])
                            if not title_elem:
                                continue
                            title = title_elem.get_text().strip()

                            link = None
                            if title_elem.name == 'a' and title_elem.has_attr('href'):
                                link = title_elem['href']
                            else:
                                link_elem = element.select_one(selectors["link"])
                                if link_elem and link_elem.has_attr('href'):
                                    link = link_elem['href']
                            if not link:
                                continue
                            if not link.startswith('http'):
                                link = urljoin(url, link)

                            summary = ""
                            summary_elem = element.select_one(selectors["summary"])
                            if summary_elem:
                                summary = summary_elem.get_text().strip()
                            
                            published_date = datetime.now()
                            date_elem = element.select_one('.date, .time, .timestamp, [datetime]')
                            if date_elem:
                                date_text = date_elem.get_text().strip() or date_elem.get('datetime', '')
                                if date_text:
                                    try:
                                        published_date = date_parser.parse(date_text, fuzzy=True)
                                    except:
                                        published_date = datetime.now()

                            if title and link:
                                article = NewsArticle(
                                    title=title,
                                    url=link,
                                    source=name,
                                    category=category,
                                    published_date=published_date,
                                    summary=summary if summary else f"Policy news from {name}",
                                    tags=self.assign_tags(title, summary)
                                )
                                article.calculate_relevance_scores()
                                if article.relevance_scores['overall'] >= 0.15:
                                    if article.content_hash not in self.article_hashes:
                                        self.article_hashes.add(article.content_hash)
                                        source_articles.append(article)
                                        self.save_article_to_db(article)
                                else:
                                    self.statistics['low_relevance_articles'] += 1
                        except Exception as e:
                            logger.debug(f"Error extracting individual article from {name}: {e}")
                            continue

                    if source_articles:
                        articles.extend(source_articles)
                        logger.info(f"Found {len(source_articles)} articles from {name} via direct scraping")
                    else:
                        logger.warning(f"No articles found from {name} via direct scraping")
                else:
                    logger.warning(f"No article elements found for {name} with selector: {selectors['article']}")
                    
            except Exception as e:
                logger.error(f"Error in direct scrape for {name}: {e}")
                
            time.sleep(random.uniform(1, 2))

        self.statistics['direct_scrape_articles'] = len(articles)
        logger.info(f"Direct scraping found {len(articles)} articles")
        return articles

    def assign_tags(self, title: str, summary: str) -> List[str]:
        """Assign tags to articles based on content with improved classification"""
        tags = []
        full_text = f"{title} {summary}".lower()

        # Tag rules with clearer patterns
        tag_rules = {
            'Policy Analysis': [
                'analysis', 'study', 'report', 'research', 'survey', 'findings',
                'data analysis', 'impact assessment', 'evaluation', 'review'
            ],
            'Legislative Updates': [
                'bill', 'act', 'parliament', 'amendment', 'legislation',
                'rajya sabha', 'lok sabha', 'ordinance', 'draft bill'
            ],
            'Regulatory Changes': [
                'regulation', 'rules', 'guidelines', 'notification', 'circular',
                'compliance', 'enforcement', 'regulatory', 'mandate'
            ],
            'Court Rulings': [
                'court', 'supreme', 'judicial', 'judgment', 'verdict', 'tribunal',
                'hearing', 'petition', 'bench', 'justice', 'order'
            ],
            'Government Initiatives': [
                'scheme', 'program', 'initiative', 'launch', 'implementation',
                'project', 'mission', 'flagship', 'campaign'
            ],
            'Policy Debate': [
                'debate', 'discussion', 'consultation', 'feedback', 'opinion',
                'perspective', 'stakeholder', 'controversy', 'criticism'
            ],
            'International Relations': [
                'bilateral', 'diplomatic', 'foreign', 'international', 'global',
                'relation', 'cooperation', 'treaty', 'agreement', 'pact'
            ],
            'Digital Governance': [
                'digital', 'online', 'internet', 'tech', 'platform', 'data',
                'privacy', 'cyber', 'algorithm', 'ai', 'artificial intelligence'
            ],
            'Budget & Finance': [
                'budget', 'fiscal', 'finance', 'tax', 'taxation', 'revenue',
                'expenditure', 'subsidy', 'financial', 'funding'
            ],
            'Development & Reforms': [
                'reform', 'development', 'modernization', 'transformation',
                'improvement', 'upgrade', 'overhaul', 'restructuring'
            ]
        }

        # Advanced tag assignment with weighted approach
        for tag, keywords in tag_rules.items():
            # Count how many keywords match
            matches = sum(1 for keyword in keywords if keyword in full_text)

            # Add tag if sufficient matches
            if matches >= 2:
                tags.append(tag)
            # Also add if single strong match found (full keyword present)
            elif matches == 1 and any(f" {keyword} " in f" {full_text} " for keyword in keywords):
                tags.append(tag)

        # Add policy area tags if appropriate
        if 'budget' in full_text or 'economic' in full_text or 'economy' in full_text:
            tags.append('Economic Policy')

        if 'technology' in full_text or 'digital' in full_text or 'tech' in full_text:
            tags.append('Technology Policy')

        if 'health' in full_text or 'healthcare' in full_text or 'medical' in full_text:
            tags.append('Healthcare Policy')

        # Ensure at least one tag
        if not tags:
            # Add a default tag based on keywords
            if any(word in full_text for word in ['policy', 'government', 'ministry', 'official']):
                tags.append('Policy Development')
            else:
                tags.append('Policy News')  # Generic fallback

        # Remove duplicates and limit to 4 tags maximum
        tags = list(dict.fromkeys(tags))  # Remove duplicates while preserving order
        return tags[:4]

    def fetch_all_feeds(self, max_workers=8):
        """
        Fetch all feeds with a hybrid strategy: sequential for sensitive government
        sites and concurrent for all others to maximize speed and avoid blocks.
        """
        all_articles = []
        start_time = time.time()

        # Ensure feeds list is valid
        if not self.feeds:
            logger.error("Feeds list is empty or not initialized properly.")
            return all_articles

        valid_feeds = [feed for feed in self.feeds if feed]
        if not valid_feeds:
            logger.error("No valid feeds found after filtering.")
            return all_articles
        
        # Separate government and non-government feeds for different handling
        gov_feeds = [f for f in valid_feeds if self._is_government_feed(f[1])]
        other_feeds = [f for f in valid_feeds if not self._is_government_feed(f[1])]

        logger.info(f"Processing {len(gov_feeds)} government feeds sequentially to avoid rate-limiting...")
        
        # --- Process Government Feeds Sequentially ---
        for feed in gov_feeds:
            try:
                articles = self.fetch_single_feed(feed)
                all_articles.extend(articles)
                # Respectful delay between requests to the same or different government servers
                time.sleep(self.get_domain_specific_delay(feed[1]))
            except Exception as e:
                logger.error(f"Error during sequential fetch of {feed[0]}: {e}", exc_info=True)

        logger.info(f"Processing {len(other_feeds)} other news feeds concurrently with {max_workers} workers...")

        # --- Process Other Feeds Concurrently ---
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_feed = {executor.submit(self.fetch_single_feed, feed): feed for feed in other_feeds}
            
            try:
                # Increased timeout from 300 to 1800 seconds (30 minutes)
                for future in as_completed(future_to_feed, timeout=1800):
                    feed = future_to_feed[future]
                    try:
                        articles = future.result()
                        all_articles.extend(articles)
                    except Exception as exc:
                        logger.error(f"Exception for feed '{feed[0]}': {exc}", exc_info=True)
                        self.update_feed_status(feed[1], False, str(exc))
                        self.statistics['failed_feeds'] += 1

            except TimeoutError:
                # This will now only trigger after 30 minutes
                pending_futures = len(future_to_feed) - self.statistics['successful_feeds'] - self.statistics['failed_feeds']
                logger.error(
                    f"Main thread pool timed out after 30 minutes. "
                    f"{pending_futures} (of {len(other_feeds)}) futures remain unfinished.",
                    exc_info=True
                )

        # Log final summary
        end_time = time.time()
        self.statistics['runtime'] = round(end_time - start_time, 2)
        logger.info(f"Feed fetching completed in {self.statistics['runtime']:.2f} seconds")
        logger.info(f"Successful feeds: {self.statistics['successful_feeds']}/{self.statistics['total_feeds']}")
        logger.info(f"Total articles collected: {len(all_articles)}")

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

    def fetch_feed_with_retries(self, feed_url, source_name, category, retries=0):
        """Enhanced feed fetching with government site compatibility"""
        max_retries = 3
        articles = []
        
        if retries >= max_retries:
            logger.warning(f"Max retries exceeded for {source_name}")
            return articles
        
        try:
            # Check if this feed failed recently (within last hour)
            if hasattr(self, 'recent_failures'):
                last_failure = self.recent_failures.get(feed_url)
                if last_failure and (time.time() - last_failure) < 3600:
                    logger.debug(f"Skipping recently failed feed: {source_name}")
                    return articles
            
            # Parse domain for site-specific handling
            domain = urlparse(feed_url).netloc.lower()
            
            # Delay before request (rate limiting)
            delay = self.get_domain_specific_delay(feed_url)
            time.sleep(delay)
            
            # Build headers with site-specific customization
            headers = self._build_headers_for_site(feed_url, source_name)
            
            # For government sites, establish session cookies first
            if any(d in domain for d in ['.gov.in', '.nic.in', 'rbi.org.in']):
                # Visit homepage first to establish session
                homepage = f"https://{domain}"
                try:
                    logger.debug(f"Establishing session with {homepage}")
                    homepage_response = self.session.get(
                        homepage,
                        headers=headers,
                        timeout=15,
                        allow_redirects=True
                    )
                    # Small delay after homepage visit
                    time.sleep(0.5)
                except:
                    pass  # Continue even if homepage visit fails
            
            # Make the actual feed request
            logger.debug(f"Fetching {source_name} from {feed_url}")
            
            response = self.session.get(
                feed_url,
                headers=headers,
                timeout=30,
                allow_redirects=True,
                stream=True  # Use streaming for large responses
            )
            
            # Check response
            if response.status_code == 200:
                content_type = response.headers.get('content-type', '').lower()
                
                # Parse based on content type
                if 'xml' in content_type or 'rss' in content_type or 'atom' in content_type:
                    articles = self._parse_feed_content(response.content, source_name, category)
                elif 'html' in content_type:
                    # Try HTML scraping for non-RSS pages
                    articles = self._scrape_html_content(response.text, source_name, category, feed_url)
                else:
                    # Try parsing as feed anyway
                    articles = self._parse_feed_content(response.content, source_name, category)
                
                if articles:
                    logger.info(f"Successfully fetched {len(articles)} articles from {source_name}")
                    # Clear any failure record
                    if hasattr(self, 'recent_failures') and feed_url in self.recent_failures:
                        del self.recent_failures[feed_url]
                else:
                    logger.warning(f"No articles extracted from {source_name}")
                    
            elif response.status_code == 403:
                logger.warning(f"Access denied (403) for {source_name}, trying alternate approach")
                # Try with different headers
                if retries < max_retries:
                    time.sleep(delay * 2)  # Double delay before retry
                    return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
            else:
                logger.warning(f"HTTP {response.status_code} for {source_name}")
                
        except requests.exceptions.Timeout:
            logger.error(f"Timeout fetching {source_name}")
            self._record_failure(feed_url)
        except requests.exceptions.SSLError as e:
            logger.error(f"SSL Error for {source_name}: {str(e)}")
            # Try without SSL verification as last resort
            if retries < max_retries:
                try:
                    response = self.session.get(feed_url, headers=headers, timeout=30, verify=False)
                    if response.status_code == 200:
                        articles = self._parse_feed_content(response.content, source_name, category)
                except:
                    self._record_failure(feed_url)
        except Exception as e:
            logger.error(f"Error fetching {source_name}: {str(e)}")
            self._record_failure(feed_url)
        
        return articles

    def _build_headers_for_site(self, url, source_name):
        """Build customized headers for specific sites"""
        domain = urlparse(url).netloc.lower()
        
        # Start with base browser headers
        headers = {
            'User-Agent': self.get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9,hi;q=0.8',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'no-cache',
            'Pragma': 'no-cache'
        }
        
        # Add referer for government sites
        if '.gov.in' in domain or '.nic.in' in domain:
            headers['Referer'] = f'https://{domain}/'
            headers['Origin'] = f'https://{domain}'
            
        # Special handling for specific government sites
        if 'pib.gov.in' in domain:
            headers['Referer'] = 'https://pib.gov.in/'
            headers['X-Requested-With'] = 'XMLHttpRequest'
        elif 'rbi.org.in' in domain:
            headers['Referer'] = 'https://www.rbi.org.in/'
        elif 'sebi.gov.in' in domain:
            headers['Referer'] = 'https://www.sebi.gov.in/'
            headers['Cookie'] = 'has_js=1'
        elif 'trai.gov.in' in domain:
            headers['Referer'] = 'https://www.trai.gov.in/'
        
        # For RSS/XML feeds, adjust Accept header
        if 'rss' in url or 'feed' in url or 'xml' in url:
            headers['Accept'] = 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*'
        
        return headers

    def _record_failure(self, feed_url):
        """Record feed failure for temporary blacklisting"""
        if not hasattr(self, 'recent_failures'):
            self.recent_failures = {}
        self.recent_failures[feed_url] = time.time()

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
        """Enhanced HTML scraping for government sites"""
        articles = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Government site specific selectors
            if 'pib.gov.in' in url:
                # PIB specific selectors
                article_elements = soup.select('.content-area ul li a, .releases-div a, .col-md-9 a[href*="PressRelease"]')
            elif 'meity.gov.in' in url:
                # MeitY specific selectors
                article_elements = soup.select('.view-content .views-row a, .item-list ul li a')
            elif 'trai.gov.in' in url:
                # TRAI specific selectors
                article_elements = soup.select('table tr td a, .view-content a')
            elif 'sebi.gov.in' in url:
                # SEBI specific selectors
                article_elements = soup.select('.table-responsive a, .pressrelease a, ul.press_list li a')
            else:
                # Generic government site selectors
                article_elements = soup.select('a[href*="press"], a[href*="news"], a[href*="notification"], .news-item a, .press-release a')
            
            for element in article_elements[:15]:
                try:
                    title = element.get_text().strip()
                    link = element.get('href', '')
                    
                    if not link or len(title) < 10:
                        continue
                    
                    # Make relative URLs absolute
                    if not link.startswith('http'):
                        link = urljoin(url, link)
                    
                    # Skip non-relevant links
                    if any(skip in link.lower() for skip in ['javascript:', 'mailto:', '#', '.jpg', '.png', '.pdf']):
                        continue
                    
                    article = NewsArticle(
                        title=title,
                        url=link,
                        source=source_name,
                        category=category,
                        published_date=datetime.now(),
                        summary=f"Latest update from {source_name}",
                        tags=self.assign_tags(title, "")
                    )
                    
                    article.calculate_relevance_scores()
                    
                    if article.relevance_scores['overall'] >= 0.15:
                        if article.content_hash not in self.article_hashes:
                            self.article_hashes.add(article.content_hash)
                            articles.append(article)
                            self.save_article_to_db(article)
                            
                except Exception as e:
                    logger.debug(f"Error extracting article: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error scraping HTML for {source_name}: {str(e)}")
        
        return articles

    def _create_article_from_entry(self, entry, source_name, category):
        """Create article from feed entry with better error handling"""
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
            
            # Extract date
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
            
            # Create article
            article = NewsArticle(
                title=title,
                url=link,
                source=source_name,
                category=category,
                published_date=published,
                summary=summary or f"Policy update from {source_name}",
                tags=self.assign_tags(title, summary)
            )
            
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

    def _is_government_feed(self, url):
        """Check if URL is a government feed"""
        gov_indicators = ['.gov.in', '.nic.in', 'rbi.org.in', 'sebi.gov.in', 
                        'trai.gov.in', 'pib.', 'parliament.', 'mygov.', 
                        'india.gov.in', 'gst.gov.in']
        return any(indicator in url.lower() for indicator in gov_indicators)

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

    def run(self, max_workers: int = 10, use_async: bool = False) -> str:
        """Main execution method with a multi-stage fetching and fallback strategy."""
        start_time = time.time()
        logger.info("Starting PolicyRadar Enhanced Aggregator...")
        
        try:
            # Initialize components
            self.initialize_feed_monitor()
            
            # Stage 1: Fetch from healthy RSS/Atom feeds
            healthy_feeds = self.get_healthy_feeds()
            self.feeds = healthy_feeds
            logger.info(f"Processing {len(healthy_feeds)} healthy feeds.")
            
            # Fetch from RSS feeds
            all_articles = self.fetch_all_feeds(max_workers=max_workers)

            # Stage 2: Supplement with Google News if article count is low
            if len(all_articles) < 150:
                logger.info("Supplementing with Google News...")
                google_articles = self.fetch_google_news_policy_articles(max_articles=50)
                all_articles.extend(google_articles)

            # Stage 3: Supplement with direct scraping for high-value targets
            if len(all_articles) < 200:
                logger.info("Supplementing with direct scraping of reliable sources...")
                scraped_articles = self.direct_scrape_reliable_sources()
                all_articles.extend(scraped_articles)

            # Stage 4: Process and finalize articles
            unique_articles = self.deduplicate_articles(all_articles)
            for article in unique_articles: # Ensure all articles are scored
                article.calculate_relevance_scores()
            
            sorted_articles = self.sort_articles_by_relevance(unique_articles)
            
            # Stage 5: Generate outputs and reports
            output_file = self.generate_html(sorted_articles)
            self.export_articles_to_json(sorted_articles)
            self.cache_articles(sorted_articles)
            
            # Final logging
            runtime = time.time() - start_time
            logger.info(f"PolicyRadar finished in {runtime:.2f} seconds. Collected {len(sorted_articles)} unique articles.")
            
            # Generate reports
            if hasattr(self, 'feed_monitor'):
                feed_report = self.feed_monitor.get_feed_report()
                if feed_report:
                    self.write_enhanced_debug_report(runtime, feed_report)
            
            # Generate health dashboard
            self.generate_health_dashboard()
            
            return output_file

        except Exception as e:
            logger.critical(f"A critical error occurred in the main run process: {e}", exc_info=True)
            logger.info("Attempting to generate a report from cached articles as a fallback.")
            
            # Try to use cached articles
            cached_articles = self.load_cached_articles()
            if cached_articles:
                return self.generate_html(cached_articles)
            else:
                # Generate minimal HTML with error message
                error_article = NewsArticle(
                    title="PolicyRadar System Error",
                    url="#",
                    source="System",
                    category="System Notice",
                    published_date=datetime.now(),
                    summary=f"PolicyRadar encountered an error during execution: {str(e)}. Please check the logs for more details.",
                    tags=["System Error"]
                )
                return self.generate_minimal_html([error_article])

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

            def sort_articles_by_relevance(self, articles: List[NewsArticle]) -> List[NewsArticle]:
                """Sort articles using a sophisticated relevance algorithm"""
                # Define source quality tiers
                source_tiers = {
                    'tier1': ['pib', 'meity', 'rbi', 'supreme court', 'sebi', 'ministry'],  # Official sources
                    'tier2': ['prs', 'medianama', 'livelaw', 'bar and bench', 'iff', 'orf'],  # Specialized policy sources
                    'tier3': ['the hindu', 'indian express', 'economic times', 'livemint', 'business standard'],  # Major publications
                    'tier4': ['google news', 'the wire', 'scroll', 'print']  # Aggregators and smaller publications
                }

                # Calculate source tier bonus for each article
                for article in articles:
                    # Ensure article has relevance scores calculated
                    if article.relevance_scores['overall'] == 0:
                        article.calculate_relevance_scores()

                    # Calculate importance and timeliness if not already done
                    if not hasattr(article, 'importance') or article.importance == 0:
                        article.calculate_importance()
                    if not hasattr(article, 'timeliness') or article.timeliness == 0:
                        article.calculate_timeliness()

                    # Default to lowest tier
                    article.source_tier = 4
                    article_source = article.source.lower()

                    # Check for source in each tier
                    for tier, sources in source_tiers.items():
                        if any(source in article_source for source in sources):
                            article.source_tier = int(tier[-1])  # Extract tier number
                            break

                    # Calculate combined relevance score (0-1 scale)
                    # Formula: 60% importance + 30% timeliness + 10% source tier bonus
                    tier_bonus = (5 - article.source_tier) / 4  # Convert to 0-1 scale (tier1=1, tier4=0.25)
                    article.relevance_score = (0.6 * article.importance) + (0.3 * article.timeliness) + (0.1 * tier_bonus)

                # Sort by combined relevance score
                return sorted(articles, key=lambda x: x.relevance_score, reverse=True)

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

    def generate_minimal_html(self, articles: List[NewsArticle]) -> str:
        """Generate a minimal HTML page with emergency content"""
        html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PolicyRadar - System Notice</title>
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, sans-serif; line-height: 1.6; color: #333; max-width: 800px; margin: 0 auto; padding: 20px; }}
            h1 {{ color: #2c3e50; }}
            .notice {{ background-color: #fff8e1; border: 1px solid #ffd54f; border-radius: 8px; padding: 20px; margin-bottom: 20px; }}
            .notice h2 {{ margin-top: 0; color: #e74c3c; }}
            footer {{ margin-top: 40px; color: #777; font-size: 0.9em; text-align: center; }}
        </style>
    </head>
    <body>
        <h1>PolicyRadar</h1>

        <div class="notice">
            <h2>{articles[0].title}</h2>
            <p>{articles[0].summary}</p>
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

    def generate_html(self, articles: List[NewsArticle]) -> str:
        """Generate enhanced HTML output with improved layout and working filters"""
        logger.info(f"Generating HTML output with {len(articles)} articles")

        # Sort articles by relevance first
        articles = self.sort_articles_by_relevance(articles)

        # Prepare data for JSON injection with truncated summaries
        articles_data = {
            "generated": datetime.now().isoformat(),
            "total_articles": len(articles),
            "articles": [
                {
                    **article.to_dict(),
                    "summary": self.truncate_summary(article.summary, 150)  # Truncate summaries
                } for article in articles
            ],
            "categories": sorted(list(set(article.category for article in articles))),
            "sources": sorted(list(set(article.source for article in articles)))
        }

        # Convert to JSON string
        articles_json = json.dumps(articles_data, ensure_ascii=False, indent=2)

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
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="category" value="Economic Policy">
                        <span>Economic Policy</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="category" value="Technology Policy">
                        <span>Technology Policy</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="category" value="Healthcare Policy">
                        <span>Healthcare Policy</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="category" value="Environmental Policy">
                        <span>Environmental Policy</span>
                    </label>
                    <label class="filter-option">
                        <input type="checkbox" class="filter-checkbox" data-filter="category" value="Defense & Security">
                        <span>Defense & Security</span>
                    </label>
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

        // Render featured articles (top 2 by relevance)
        function renderFeaturedArticles() {{
            const featuredGrid = document.getElementById('featuredGrid');
            const featured = allArticles
                .sort((a, b) => b.relevance_scores.overall - a.relevance_scores.overall)
                .slice(0, 2);

            featuredGrid.innerHTML = featured.map(article => createArticleCard(article, true)).join('');
        }}

        // Render main content organized by categories
        function renderMainContent() {{
            const mainContent = document.getElementById('mainContent');
            const filtered = filterArticles();
            
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
        """Generate a system health dashboard HTML page"""
        try:
            # Calculate success rates
            total_feeds = self.statistics.get('total_feeds', 1)
            successful_feeds = self.statistics.get('successful_feeds', 0)
            success_rate = (successful_feeds / total_feeds) * 100
            
            # Create HTML content
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PolicyRadar System Health</title>
    <style>
        body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }}
        .container {{ max-width: 1000px; margin: 0 auto; }}
        .dashboard {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }}
        .card {{ background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); padding: 20px; }}
        .metric {{ font-size: 2em; font-weight: bold; text-align: center; }}
        .metric-label {{ text-align: center; color: #666; }}
        .status-success {{ color: #2ecc71; }}
        .status-warning {{ color: #f39c12; }}
        .status-danger {{ color: #e74c3c; }}
        table {{ width: 100%; border-collapse: collapse; }}
        th, td {{ padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }}
        th {{ background-color: #f2f2f2; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>PolicyRadar System Health Dashboard</h1>
        
        <div class="dashboard">
            <div class="card">
                <div class="metric">{total_feeds}</div>
                <div class="metric-label">Total Feeds Monitored</div>
            </div>
            
            <div class="card">
                <div class="metric">{successful_feeds}</div>
                <div class="metric-label">Successful Feeds</div>
            </div>
            
            <div class="card">
                <div class="metric">{self.statistics.get('total_articles', 0)}</div>
                <div class="metric-label">Articles Collected</div>
            </div>
            
            <div class="card">
                <div class="metric status-{'success' if success_rate > 80 else 'warning' if success_rate > 50 else 'danger'}">
                    {success_rate:.1f}%
                </div>
                <div class="metric-label">Success Rate</div>
            </div>
        </div>
        
        <div class="card">
            <h2>Feed Status</h2>
            <table>
                <thead>
                    <tr>
                        <th>Source</th>
                        <th>Status</th>
                        <th>Articles</th>
                        <th>Last Update</th>
                    </tr>
                </thead>
                <tbody>
"""
            
            # Add feed status rows
            for source, status in self.feed_health.items():
                last_update = self.source_last_update.get(source, 'N/A')
                if isinstance(last_update, datetime):
                    last_update = last_update.strftime('%Y-%m-%d %H:%M:%S')
                
                status_class = 'status-success' if status.get('status') == 'success' else 'status-danger'
                status_text = 'Operational' if status.get('status') == 'success' else 'Failed'
                
                html += f"""                    <tr>
                        <td>{source}</td>
                        <td class="{status_class}">{status_text}</td>
                        <td>{status.get('count', 0)}</td>
                        <td>{last_update}</td>
                    </tr>
"""
            
            html += """                </tbody>
            </table>
        </div>
        
        <div class="card">
            <h2>System Statistics</h2>
            <ul>
"""
            
            # Add statistics
            for key, value in self.statistics.items():
                html += f"                <li><strong>{key.replace('_', ' ').title()}:</strong> {value}</li>\n"
            
            html += """            </ul>
        </div>
    </div>
</body>
</html>
"""
            
            # Write to file
            health_file = os.path.join(Config.OUTPUT_DIR, 'health.html')
            with open(health_file, 'w', encoding='utf-8') as f:
                f.write(html)
            
            logger.info(f"System health dashboard generated: {health_file}")
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
    parser = argparse.ArgumentParser(description="PolicyRadar Enhanced - Indian Policy News Aggregator")
    parser.add_argument("--max", type=int, default=200, help="Maximum articles to collect")
    parser.add_argument("--reset-cache", action="store_true", help="Reset article cache before run")
    parser.add_argument("--ignore-duplicates", action="store_true", help="Don't check for duplicate articles")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Configure logging level
    if args.debug:
        logger.setLevel(logging.DEBUG)
        for handler in logger.handlers:
            handler.setLevel(logging.DEBUG)
    
    # Initialize PolicyRadar
    radar = PolicyRadarEnhanced()
    
    # Handle reset cache request
    if args.reset_cache:
        logger.info("Resetting article cache as requested")
        radar.reset_article_cache()
    
    # Set duplicate detection preference
    radar.ignore_duplicates = args.ignore_duplicates
    
    # Run the aggregator
    try:
        logger.info("Starting PolicyRadar aggregation process")
        output_file = radar.run()
        
        if output_file:
            logger.info(f"PolicyRadar completed successfully. Output: {output_file}")
        else:
            logger.error("PolicyRadar completed but no output file was generated")
    except Exception as e:
        logger.critical(f"Fatal error during PolicyRadar execution: {str(e)}", exc_info=True)
