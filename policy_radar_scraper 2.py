#!/usr/bin/env python3
"""
PolicyRadar - Indian Policy News Aggregator (Enhanced Version)

This tool aggregates Indian policy news from reliable sources using multiple strategies:
1. Google News RSS Integration (primary method)
2. Direct Website Scraping (for important policy sources)
3. RSS/Atom Feed Parsing (with fallback mechanisms)

Key features:
- Resilient session handling with proper retry logic
- Enhanced error handling with fallback mechanisms
- Policy-specific content filtering
- Category-based news organization
- Clean, responsive HTML output with dark/light mode
- System health dashboard
"""

import requests
import urllib.parse
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
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from requests.packages.urllib3.exceptions import InsecureRequestWarning
import sqlite3
import argparse
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
import warnings
from datetime import datetime, timedelta

# Filter out specific warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module='feedparser')

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('policyradar.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Create necessary directories
DIRS = ['logs', 'cache', 'data', 'docs', 'backup']
for directory in DIRS:
    Path(directory).mkdir(exist_ok=True)

# Configuration class
class Config:
    # Directories
    OUTPUT_DIR = 'docs'
    CACHE_DIR = 'cache'
    DATA_DIR = 'data'
    LOG_DIR = 'logs'
    BACKUP_DIR = 'backup'
    
    # Timing
    CACHE_DURATION = 3600  # 1 hour in seconds
    BACKUP_DURATION = 86400  # 24 hours in seconds
    RETRY_DELAY = 1.5  # base delay for exponential backoff
    REQUEST_TIMEOUT = 15  # timeout for requests
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_STATUS_CODES = [429, 500, 502, 503, 504]

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

class NewsArticle:
    """Class representing a news article"""
    
    def __init__(self, title, url, source, category, published_date=None, summary=None, tags=None):
        self.title = title
        self.url = url
        self.source = source
        self.category = category
        self.published_date = published_date
        self.summary = summary
        self.tags = tags or []
        self.content_hash = self._generate_hash()
    
    def _generate_hash(self):
        """Generate unique hash for article to prevent duplicates"""
        content = f"{self.title}{self.url}".lower()
        return hashlib.md5(content.encode()).hexdigest()
    
    def to_dict(self):
        """Convert article to dictionary for JSON serialization"""
        return {
            'title': self.title,
            'url': self.url,
            'source': self.source,
            'category': self.category,
            'published_date': self.published_date,
            'summary': self.summary,
            'tags': self.tags,
            'content_hash': self.content_hash
        }

class PolicyRadar:
    """Main class for the PolicyRadar news aggregator"""
    
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
            'google_news_articles': 0
        }
        self.load_article_hashes()
        self.feeds = self._get_curated_feeds()
    
    def _create_resilient_session(self):
        """Create a requests session with proper SSL handling and retry logic"""
        session = requests.Session()
        
        # Create adapter with retry strategy
        retry_strategy = Retry(
            total=Config.MAX_RETRIES,
            backoff_factor=Config.RETRY_DELAY,
            status_forcelist=Config.RETRY_STATUS_CODES,
            allowed_methods=["GET", "HEAD"]
        )
        
        # Adapter with custom SSL context
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        return session
    
    def get_user_agent(self):
        """Return a random user agent from the list"""
        return random.choice(Config.USER_AGENTS)
    
    def initialize_db(self):
        """Initialize SQLite database for feed history and articles"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                
                # Create tables
                c.execute('''CREATE TABLE IF NOT EXISTS feed_history
                            (feed_url TEXT, last_success TIMESTAMP, last_error TEXT, 
                            error_count INTEGER DEFAULT 0, PRIMARY KEY (feed_url))''')
                
                c.execute('''CREATE TABLE IF NOT EXISTS articles
                            (hash TEXT PRIMARY KEY, title TEXT, url TEXT, source TEXT,
                            category TEXT, published_date TIMESTAMP, summary TEXT,
                            tags TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                
                # Index for faster lookups
                c.execute('CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at)')
                c.execute('CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)')
                
                conn.commit()
                logger.debug("Database initialized successfully")
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            # Continue without raising error - we'll use in-memory storage if needed
    
    def load_article_hashes(self):
        """Load existing article hashes from database to prevent duplicates"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('SELECT hash FROM articles')
                self.article_hashes = set(row[0] for row in c.fetchall())
                logger.debug(f"Loaded {len(self.article_hashes)} article hashes from database")
        except sqlite3.Error as e:
            logger.error(f"Database error loading article hashes: {e}")
            # Continue with empty set if there's a problem
            self.article_hashes = set()
    
    def update_feed_status(self, feed_url, success, error=None):
        """Update feed status in database"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                
                if success:
                    c.execute('''UPDATE feed_history 
                                SET last_success = CURRENT_TIMESTAMP, error_count = 0, last_error = NULL
                                WHERE feed_url = ?''', (feed_url,))
                    
                    # If no record was updated, insert a new one
                    if c.rowcount == 0:
                        c.execute('''INSERT INTO feed_history 
                                    (feed_url, last_success) VALUES (?, CURRENT_TIMESTAMP)''', 
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
        """Save article to database"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                
                c.execute('''INSERT OR IGNORE INTO articles 
                            (hash, title, url, source, category, published_date, summary, tags)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                        (article.content_hash, article.title, article.url, article.source,
                        article.category, article.published_date, article.summary,
                        json.dumps(article.tags)))
                
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error saving article: {e}")
    
    def _get_curated_feeds(self):
        """Return a carefully curated list of reliable Indian policy news feeds"""
        return [
            # Google News - most reliable approach
            ("Google News - India Policy", "https://news.google.com/rss/search?q=india+policy&hl=en-IN&gl=IN&ceid=IN:en", "Policy News"),
            ("Google News - Economic Policy", "https://news.google.com/rss/search?q=india+economic+policy&hl=en-IN&gl=IN&ceid=IN:en", "Economic Policy"),
            ("Google News - Technology Policy", "https://news.google.com/rss/search?q=india+technology+policy&hl=en-IN&gl=IN&ceid=IN:en", "Technology Policy"),
            
            # Government sources
            ("PRS Legislative", "https://prsindia.org/feeds/bills/introduced", "Constitutional & Legal"),
            ("PIB", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "Government Policy"),
            
            # Think tanks
            ("ORF", "https://www.orfonline.org/feed/?post_type=research", "Policy Analysis"),
            ("CPR India", "https://cprindia.org/feed/", "Policy Analysis"),
            
            # Business & Economic sources
            ("The Hindu Business Line", "https://www.thehindubusinessline.com/economy/feeder/default.rss", "Economic Policy"),
            ("Business Standard Economy", "https://www.business-standard.com/rss/markets-106.rss", "Economic Policy"),
            ("Economic Times Policy", "https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1286551326.cms", "Economic Policy"),
            
            # Legal and Constitutional
            ("Bar and Bench", "https://www.barandbench.com/feed", "Constitutional & Legal"),
            ("LiveLaw", "https://www.livelaw.in/feed/", "Constitutional & Legal"),
            
            # Tech Policy
            ("MediaNama", "https://www.medianama.com/feed/", "Technology Policy"),
            ("Internet Freedom Foundation", "https://internetfreedom.in/rss", "Technology Policy"),
            
            # Other reliable sources
            ("The News Minute", "https://www.thenewsminute.com/rss.xml", "State & Local Policies"),
            ("Indian Express Opinion", "https://indianexpress.com/section/opinion/columns/feed/", "Policy Analysis"),
            ("Indian Express Education", "https://indianexpress.com/section/education/feed/", "Education Policy"),
        ]
    
    def fetch_google_news_policy_articles(self, max_articles=100):
        """Fetch Indian policy news from Google News RSS with multiple targeted queries"""
        all_articles = []
        
        # Policy-focused search queries (general)
        general_queries = [
            "India policy", 
            "India government policy",
            "India economic policy",
            "India technology policy",
            "India health policy",
            "India environmental policy", 
            "India education policy",
            "India foreign policy"
        ]
        
        # Site-specific policy queries (targeting quality sources)
        site_queries = [
            "site:thehindu.com India policy",
            "site:indianexpress.com India policy",
            "site:economictimes.indiatimes.com policy",
            "site:livemint.com policy",
            "site:business-standard.com policy",
            "site:thewire.in policy",
            "site:scroll.in policy",
            "site:prsindia.org policy",
            "site:idronline.org policy",
            "site:cprindia.org policy"
        ]
        
        # Combine all queries
        all_queries = general_queries + site_queries
        
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
                        for entry in feed.entries[:10]:  # Limit to 10 per query
                            title = entry.title
                            link = entry.link
                            
                            # Extract source and date
                            source = entry.source.title if hasattr(entry, 'source') else "Google News"
                            published = entry.published if hasattr(entry, 'published') else None
                            
                            # Create summary from description
                            summary = ""
                            if hasattr(entry, 'description'):
                                # Clean HTML from description
                                soup = BeautifulSoup(entry.description, 'html.parser')
                                summary = soup.get_text().strip()
                            
                            # Determine category based on query and title
                            category = self.categorize_article(title, summary, query)
                            
                            # Create article
                            article = NewsArticle(
                                title=title,
                                url=link,
                                source=source,
                                category=category,
                                published_date=published,
                                summary=summary,
                                tags=self.assign_tags(title, summary)
                            )
                            
                            # Add if not duplicate
                            if article.content_hash not in self.article_hashes:
                                self.article_hashes.add(article.content_hash)
                                all_articles.append(article)
                                self.save_article_to_db(article)
                                
                                # Stop if we reached the limit
                                if len(all_articles) >= max_articles:
                                    break
                        
                        # Stop if we reached the limit
                        if len(all_articles) >= max_articles:
                            break
                    else:
                        logger.warning(f"No Google News results for query: {query}")
                        
                else:
                    logger.warning(f"Failed to fetch Google News for query '{query}': Status {response.status_code}")
                    
            except Exception as e:
                logger.error(f"Error fetching Google News for query '{query}': {str(e)}")
            
            # Add a short delay between queries to avoid rate limiting
            time.sleep(random.uniform(0.5, 1.0))
        
        self.statistics['google_news_articles'] = len(all_articles)
        logger.info(f"Found {len(all_articles)} articles from Google News RSS")
        return all_articles
    
    def direct_scrape_reliable_sources(self):
        """Directly scrape the most reliable Indian policy news websites"""
        articles = []
        
        # Reliable sources with specific policy content URLs and selectors
        reliable_sources = [
            # Government sites
            {
                "name": "PRS Legislative Research",
                "url": "https://prsindia.org/billtrack/recent",
                "category": "Constitutional & Legal",
                "selectors": {
                    "article": ".views-row, .bill-listing-item",
                    "title": "h2, h3, .field-content a",
                    "summary": ".listing-desc, .field-content p",
                    "link": "a"
                }
            },
            # Think tanks with strong policy focus
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
            # Major newspapers - opinion sections
            {
                "name": "Indian Express Opinion",
                "url": "https://indianexpress.com/section/opinion/columns/",
                "category": "Policy Analysis",
                "selectors": {
                    "article": "article, .articles > div, .ie-first-story",
                    "title": "h2, h3, .title, .heading",
                    "summary": "p, .synopsis, .excerpt",
                    "link": "a"
                }
            },
            {
                "name": "The Hindu Opinion",
                "url": "https://www.thehindu.com/opinion/lead/",
                "category": "Policy Analysis",
                "selectors": {
                    "article": ".story-card, .story-card-33, article",
                    "title": "h2, h3, .title, a.story-card-33-heading",
                    "summary": "p, .story-card-33-info, .summary",
                    "link": "a, .story-card-33 a"
                }
            },
            # Business newspapers - policy sections
            {
                "name": "Economic Times Policy",
                "url": "https://economictimes.indiatimes.com/news/economy/policy",
                "category": "Economic Policy",
                "selectors": {
                    "article": ".eachStory, .story-card, article",
                    "title": "h3, .title, .story-title",
                    "summary": ".desc, p, .summary",
                    "link": "a"
                }
            },
            {
                "name": "LiveMint Economy",
                "url": "https://www.livemint.com/economy",
                "category": "Economic Policy",
                "selectors": {
                    "article": ".cardHolder, .story-list, article",
                    "title": "h2, .headline, .title",
                    "summary": ".synopsis, p, .summary",
                    "link": "a"
                }
            },
            # Tech policy
            {
                "name": "MediaNama",
                "url": "https://www.medianama.com/category/policy/",
                "category": "Technology Policy",
                "selectors": {
                    "article": "article, .post, .grid-post",
                    "title": "h2, h3, .title",
                    "summary": "p, .excerpt, .entry-content p:first-of-type",
                    "link": "a, .more-link"
                }
            },
            {
                "name": "Internet Freedom Foundation",
                "url": "https://internetfreedom.in/",
                "category": "Technology Policy",
                "selectors": {
                    "article": "article, .post, .blog-post",
                    "title": "h2, h3, .title",
                    "summary": "p, .excerpt, .content p:first-of-type",
                    "link": "a, .more-link"
                }
            },
            # Additional policy-focused sources
            {
                "name": "IDR",
                "url": "https://idronline.org/themes/",
                "category": "Development Policy",
                "selectors": {
                    "article": "article, .article, .post-card",
                    "title": "h2, h3, .title",
                    "summary": "p, .excerpt, .subtitle",
                    "link": "a"
                }
            },
            {
                "name": "ORF",
                "url": "https://www.orfonline.org/research/",
                "category": "Policy Analysis",
                "selectors": {
                    "article": ".card, article, .research-item",
                    "title": "h2, h3, .title, .card-title",
                    "summary": "p, .excerpt, .card-text",
                    "link": "a"
                }
            }
        ]
        
        logger.info(f"Performing direct scraping on {len(reliable_sources)} source URLs")
        
        for source in reliable_sources:
            name = source["name"]
            url = source["url"]
            category = source["category"]
            selectors = source["selectors"]
            
            logger.info(f"Direct scraping {name} at {url}")
            
            try:
                # Use browser-like headers with Google referrer
                headers = {
                    'User-Agent': self.get_user_agent(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Referer': f'https://www.google.com/search?q={name.replace(" ", "+")}+india+policy',
                    'Sec-Fetch-Site': 'cross-site',
                    'Cache-Control': 'max-age=0',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                # Add GDPR consent cookies
                cookies = {
                    'gdpr': 'true', 
                    'euconsent': 'true',
                    'cookieconsent_status': 'accept',
                    'GDPRCookieConsent': 'true'
                }
                
                # Fetch content
                response = self.session.get(
                    url,
                    headers=headers,
                    cookies=cookies,
                    timeout=30,
                    verify=False,
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    # Parse HTML
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Extract articles using custom selectors for this source
                    article_elements = soup.select(selectors["article"])
                    
                    if article_elements:
                        logger.info(f"Found {len(article_elements)} potential articles using selector: {selectors['article']}")
                        
                        source_articles = []
                        
                        # Process each article element
                        for element in article_elements[:15]:  # Limit to 15 per source
                            try:
                                # Extract title
                                title_elem = element.select_one(selectors["title"])
                                if not title_elem:
                                    continue
                                    
                                title = title_elem.get_text().strip()
                                
                                # Extract link
                                link = None
                                
                                # If title element is a link
                                if title_elem.name == 'a' and title_elem.has_attr('href'):
                                    link = title_elem['href']
                                else:
                                    # Try to find link
                                    link_elem = element.select_one(selectors["link"])
                                    if link_elem and link_elem.has_attr('href'):
                                        link = link_elem['href']
                                
                                # Skip if no link
                                if not link:
                                    continue
                                    
                                # Make relative URLs absolute
                                if link and not link.startswith('http'):
                                    link = urljoin(url, link)
                                
                                # Extract summary
                                summary = ""
                                summary_elem = element.select_one(selectors["summary"])
                                if summary_elem:
                                    summary = summary_elem.get_text().strip()
                                
                                # Create article object
                                if title and link:
                                    article = NewsArticle(
                                        title=title,
                                        url=link,
                                        source=name,
                                        category=category,
                                        summary=summary if summary else f"Policy news from {name}",
                                        tags=self.assign_tags(title, summary)
                                    )
                                    
                                    # Add if not duplicate
                                    if article.content_hash not in self.article_hashes:
                                        self.article_hashes.add(article.content_hash)
                                        source_articles.append(article)
                                        self.save_article_to_db(article)
                            except Exception as e:
                                logger.debug(f"Error extracting article from {name}: {str(e)}")
                                continue
                        
                        # Add articles to results
                        if source_articles:
                            articles.extend(source_articles)
                            logger.info(f"Found {len(source_articles)} articles from {name} via direct scraping")
                        else:
                            logger.warning(f"No articles found from {name} via direct scraping")
                    else:
                        logger.warning(f"No article elements found for {name} with selector pattern")
                else:
                    logger.warning(f"Failed to fetch {name} (Status: {response.status_code})")
            
            except Exception as e:
                logger.error(f"Error in direct scrape for {name}: {str(e)}")
            
            # Add delay to avoid being blocked
            time.sleep(random.uniform(1, 2))
        
        self.statistics['direct_scrape_articles'] = len(articles)
        logger.info(f"Direct scraping found {len(articles)} articles")
        return articles
    
    def fetch_all_feeds(self, max_workers=6):
        """Fetch all feeds concurrently with improved thread management"""
        all_articles = []
        start_time = time.time()
        
        # Ensure feeds is properly initialized and contains no None values
        if not self.feeds:
            logger.error("Feeds list is empty or not initialized properly")
            return all_articles

        # Filter out any None entries to prevent TypeErrors
        valid_feeds = [feed for feed in self.feeds if feed]
        
        if not valid_feeds:
            logger.error("No valid feeds found after filtering")
            return all_articles
        
        logger.info(f"Starting to fetch {len(valid_feeds)} feeds with {max_workers} workers")
        
        try:
            # Get unique categories
            categories = set(feed[2] for feed in valid_feeds if isinstance(feed, tuple) and len(feed) >= 3)
            logger.info(f"Processing feeds across {len(categories)} categories")
            
            # Shuffle feeds to avoid hitting the same domain simultaneously
            shuffled_feeds = valid_feeds.copy()
            random.shuffle(shuffled_feeds)
            
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_feed = {executor.submit(self.fetch_single_feed, feed): feed for feed in shuffled_feeds}
                
                # Process completed futures as they finish
                for future in as_completed(future_to_feed):
                    feed = future_to_feed[future]
                    try:
                        articles = future.result()
                        all_articles.extend(articles)
                        self.statistics['total_articles'] += len(articles)
                        
                        # Add delay between requests to avoid overwhelming servers
                        time.sleep(random.uniform(0.5, 1.0))
                    except Exception as e:
                        logger.error(f"Exception fetching {feed[0] if isinstance(feed, tuple) and len(feed) > 0 else 'unknown'}: {e}")
        except Exception as e:
            logger.error(f"Error in fetch_all_feeds: {str(e)}", exc_info=True)
        
        self.statistics['end_time'] = time.time()
        self.statistics['runtime'] = round(self.statistics['end_time'] - start_time, 2)
        
        # Log summary statistics
        logger.info(f"Feed fetching completed in {self.statistics['runtime']} seconds")
        logger.info(f"Successful feeds: {self.statistics['successful_feeds']}/{self.statistics['total_feeds']}")
        logger.info(f"Articles collected: {len(all_articles)}")
        
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
        """Enhanced feed fetching with improved compatibility and better error handling"""
        max_retries = Config.MAX_RETRIES
        
        # Initialize empty list
        articles = []
        
        # Check if we've exceeded max retries
        if retries >= max_retries:
            logger.warning(f"Max retries ({max_retries}) exceeded for {source_name} at {feed_url}")
            return articles
        
        try:
            # Get domain for site-specific headers
            domain = urlparse(feed_url).netloc
            
            # Initialize headers
            headers = {
                'User-Agent': self.get_user_agent(),
                'Accept': 'application/rss+xml, application/atom+xml, application/xml, text/xml, */*;q=0.1',
                'Accept-Language': 'en-US,en;q=0.5',
                'Cache-Control': 'max-age=0',
                'Connection': 'keep-alive'
            }
            
            # Add site-specific headers if available
            for site, site_headers in Config.SITE_SPECIFIC_HEADERS.items():
                if site in domain:
                    for key, value in site_headers.items():
                        headers[key] = value
            
            # Add GDPR consent cookies
            cookies = {
                'gdpr': 'true', 
                'euconsent': 'true',
                'cookieconsent_status': 'accept',
                'GDPRCookieConsent': 'true'
            }
            
            # Use exponential backoff with jitter for retries
            retry_delay = Config.RETRY_DELAY * (1.5 ** retries) + random.uniform(0, 1)
            
            # Log attempt
            logger.debug(f"Attempt {retries+1} fetching {source_name} from {feed_url}")
            
            # Make request with proper error handling
            try:
                response = self.session.get(
                    feed_url,
                    headers=headers,
                    cookies=cookies,
                    timeout=Config.REQUEST_TIMEOUT,
                    verify=False,  # Disable verification to avoid SSL errors
                    allow_redirects=True
                )
                
                if response.status_code == 200:
                    # Try parsing with feedparser
                    feed = feedparser.parse(response.content)
                    
                    if feed.entries:
                        logger.info(f"Found {len(feed.entries)} entries in {source_name} feed")
                        
                        # Process entries
                        for entry in feed.entries[:20]:  # Limit to 20 per feed
                            try:
                                title = entry.title.strip() if hasattr(entry, 'title') else ""
                                
                                # Skip entries without titles
                                if not title:
                                    continue
                                
                                # Extract link
                                link = None
                                if hasattr(entry, 'link'):
                                    link = entry.link
                                elif hasattr(entry, 'links') and entry.links:
                                    for link_info in entry.links:
                                        if link_info.get('rel') == 'alternate':
                                            link = link_info.get('href')
                                            break
                                
                                # Skip entries without links
                                if not link:
                                    continue
                                
                                # Extract publication date
                                published = None
                                if hasattr(entry, 'published'):
                                    published = entry.published
                                elif hasattr(entry, 'pubDate'):
                                    published = entry.pubDate
                                elif hasattr(entry, 'updated'):
                                    published = entry.updated
                                
                                # Extract summary
                                summary = ""
                                if hasattr(entry, 'summary'):
                                    summary = self.clean_html(entry.summary)
                                elif hasattr(entry, 'description'):
                                    summary = self.clean_html(entry.description)
                                elif hasattr(entry, 'content') and entry.content:
                                    for content_item in entry.content:
                                        if 'value' in content_item:
                                            summary = self.clean_html(content_item.value)
                                            break
                                
                                # Create article
                                article = NewsArticle(
                                    title=title,
                                    url=link,
                                    source=source_name,
                                    category=category,
                                    published_date=published,
                                    summary=summary if summary else f"Policy news from {source_name}",
                                    tags=self.assign_tags(title, summary)
                                )
                                
                                # Check for duplicates
                                if article.content_hash not in self.article_hashes:
                                    self.article_hashes.add(article.content_hash)
                                    articles.append(article)
                                    self.save_article_to_db(article)
                            except Exception as e:
                                logger.debug(f"Error processing feed entry: {str(e)}")
                                continue
                        
                        logger.info(f"Extracted {len(articles)} articles from {source_name}")
                        return articles
                    else:
                        logger.warning(f"No entries found in feed for {source_name}")
                        
                        # Try alternative parsing approaches
                        if 'xml' in response.headers.get('content-type', '').lower():
                            return self.parse_xml_feed(response.text, source_name, category)
                        else:
                            return self.scrape_articles_fallback(response.text, source_name, category, feed_url)
                
                elif response.status_code in [403, 401]:
                    # Access denied, try with different headers
                    logger.warning(f"Access denied ({response.status_code}) for {source_name}, retrying with modified headers")
                    time.sleep(retry_delay)
                    return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
                    
                else:
                    # Other error, retry with backoff
                    logger.warning(f"Failed to fetch {source_name} (Status: {response.status_code}). Retry in {retry_delay}s")
                    time.sleep(retry_delay)
                    return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
                    
            except requests.exceptions.RequestException as e:
                # Network error, retry with backoff
                logger.warning(f"Request error for {source_name}: {str(e)}. Retry in {retry_delay}s")
                time.sleep(retry_delay)
                return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
        
        except Exception as e:
            # Unexpected error, retry with backoff
            logger.error(f"Unexpected error for {source_name}: {str(e)}")
            time.sleep(retry_delay)
            return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
        
        # Safety return
        return articles
    
    def clean_html(self, html_content):
        """Clean HTML content to plain text"""
        if not html_content:
            return ""
        
        # Remove HTML tags
        text = re.sub(r'<[^>]+>', ' ', html_content)
        
        # Replace HTML entities
        text = re.sub(r'&nbsp;', ' ', text)
        text = re.sub(r'&amp;', '&', text)
        text = re.sub(r'&lt;', '<', text)
        text = re.sub(r'&gt;', '>', text)
        text = re.sub(r'&quot;', '"', text)
        text = re.sub(r'&#39;', "'", text)
        
        # Normalize whitespace
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
                        summary=summary if summary else f"Policy news from {source_name}",
                        tags=self.assign_tags(title, summary or "")
                    )
                    
                    # Check for duplicates
                    if article.content_hash not in self.article_hashes:
                        self.article_hashes.add(article.content_hash)
                        articles.append(article)
                        self.save_article_to_db(article)
                    
                except Exception as e:
                    logger.debug(f"Error extracting feed item from XML: {str(e)}")
            
            logger.info(f"Extracted {len(articles)} articles from XML for {source_name}")
            
        except Exception as e:
            logger.error(f"Error extracting feed from XML for {source_name}: {str(e)}")
        
        return articles
    
    def scrape_articles_fallback(self, content, source_name, category, url):
        """Robust HTML scraping with progressive fallbacks for Indian news sites"""
        articles = []
        
        try:
            logger.info(f"Attempting HTML scraping fallback for {source_name}")
            soup = BeautifulSoup(content, 'html.parser')
            
            # Site-specific patterns for major Indian news sources
            site_specific_selectors = {
                "thehindu": ".story-card-33, .story-card",
                "indianexpress": ".articles article, .ie-first-story, .article-block",
                "livemint": ".cardHolder, .story-list, article",
                "economictimes": ".eachStory, .story-card",
                "business-standard": ".listing-page, .aticle-list"
            }
            
            # Check if we have a specific selector for this source
            article_elements = []
            domain = urlparse(url).netloc.lower()
            
            for site_key, selector in site_specific_selectors.items():
                if site_key in domain or site_key in source_name.lower():
                    article_elements = soup.select(selector)
                    if article_elements:
                        logger.info(f"Found {len(article_elements)} potential articles using site-specific selector for {source_name}")
                        break
            
            # If no site-specific match, try generic selectors
            if not article_elements:
                # Try very generic patterns that should match most news sites
                generic_selectors = [
                    "article, .post, .story-card, .news-item, .card",
                    "div.story, div.news, div.article, section.story",
                    "div:has(h2) a[href], div:has(h3) a[href]"
                ]
                
                for selector in generic_selectors:
                    article_elements = soup.select(selector)
                    if article_elements and len(article_elements) >= 2:
                        logger.info(f"Found {len(article_elements)} potential articles using selector: {selector}")
                        break
            
            # If still no elements found, try direct heading approach
            if not article_elements:
                article_elements = []
                headings = soup.find_all(['h1', 'h2', 'h3'])
                for heading in headings[:15]:
                    if heading.find('a'):
                        # If heading contains a link, use the parent element
                        if heading.parent and heading.parent.name != 'body':
                            article_elements.append(heading.parent)
                        else:
                            # Create a wrapper for just this heading+link
                            article_elements.append(heading)
                
                if article_elements:
                    logger.info(f"Found {len(article_elements)} potential articles using heading-based approach")
            
            # Process found elements into articles
            for element in article_elements[:15]:  # Limit to 15
                # Extract the title and link
                title = None
                link = None
                
                # Try to find title in headings
                for heading in element.find_all(['h1', 'h2', 'h3', 'h4']):
                    if heading.get_text().strip():
                        title = heading.get_text().strip()
                        
                        # If the heading contains a link, extract it
                        if heading.find('a', href=True):
                            link = heading.find('a', href=True)['href']
                        break
                
                # If no title in headings, try looking for classed elements
                if not title:
                    for class_name in ['.title', '.headline', '.heading']:
                        title_elem = element.select_one(class_name)
                        if title_elem and title_elem.get_text().strip():
                            title = title_elem.get_text().strip()
                            break
                
                # If no link yet, look for it
                if not link:
                    # Try links near the title first
                    links = element.find_all('a', href=True)
                    for a_tag in links:
                        if a_tag.get_text().strip() and len(a_tag.get_text().strip()) > 15:
                            link = a_tag['href']
                            break
                    
                    # If still no link, just take the first one
                    if not link and links:
                        link = links[0]['href']
                
                # Make relative URLs absolute
                if link and not link.startswith(('http://', 'https://')):
                    link = urljoin(url, link)
                
                # If we have both title and link, create an article
                if title and link and len(title) > 15:
                    # Extract summary if available
                    summary = ""
                    for p in element.find_all('p'):
                        if p.get_text().strip() and p.get_text().strip() != title:
                            summary = p.get_text().strip()
                            if len(summary) > 30:  # Only use if substantial
                                break
                    
                    # Ensure minimal summary
                    if not summary or len(summary) < 20:
                        summary = f"Policy news from {source_name}"
                    
                    # Create article
                    article = NewsArticle(
                        title=title,
                        url=link,
                        source=source_name,
                        category=category,
                        summary=summary,
                        tags=self.assign_tags(title, summary)
                    )
                    
                    # Check for duplicates
                    if article.content_hash not in self.article_hashes:
                        self.article_hashes.add(article.content_hash)
                        articles.append(article)
                        self.save_article_to_db(article)
            
            logger.info(f"HTML scraping for {source_name} found {len(articles)} articles")
            
        except Exception as e:
            logger.error(f"Error in HTML scraping for {source_name}: {str(e)}")
        
        return articles
    
    def categorize_article(self, title, summary, query=None):
        """Categorize article based on content"""
        text = (title + " " + summary).lower()
        
        # First check if query provides a hint
        if query:
            query = query.lower()
            if "economic" in query or "economy" in query:
                return "Economic Policy"
            elif "technology" in query or "tech" in query:
                return "Technology Policy"
            elif "health" in query or "healthcare" in query:
                return "Healthcare Policy"
            elif "environment" in query or "climate" in query:
                return "Environmental Policy"
            elif "education" in query or "school" in query:
                return "Education Policy"
            elif "foreign" in query or "diplomacy" in query:
                return "Foreign Policy"
        
        # Then analyze the content
        categories = {
            "Technology Policy": ["digital", "technology", "tech", "it ", "cyber", "internet", "data", "privacy", 
                                 "social media", "platform", "algorithm", "ai ", "artificial intelligence", "app"],
            
            "Economic Policy": ["economy", "economic", "finance", "budget", "tax", "fiscal", "monetary", "gdp", 
                              "growth", "investment", "rbi", "reserve bank", "trade", "business", "industry"],
            
            "Healthcare Policy": ["health", "healthcare", "hospital", "medical", "patient", "doctor", "drug", 
                                "pharma", "disease", "treatment", "vaccine", "ayushman"],
            
            "Environmental Policy": ["environment", "climate", "pollution", "green", "sustainable", "emission", 
                                   "forest", "wildlife", "biodiversity", "carbon", "renewable", "clean energy"],
            
            "Education Policy": ["education", "school", "university", "student", "teacher", "learning", 
                               "skill", "curriculum", "academic", "college", "degree", "literacy"],
            
            "Foreign Policy": ["foreign", "diplomatic", "bilateral", "international", "global", "relations", 
                             "treaty", "ambassador", "embassy", "cooperation", "strategic", "border"],
            
            "Constitutional & Legal": ["court", "judicial", "legal", "law", "constitution", "supreme court", 
                                    "high court", "judgment", "verdict", "litigation", "judiciary", "rights"],
            
            "State & Local Policies": ["state government", "local", "municipal", "mayor", "city", "urban", 
                                     "rural", "district", "panchayat", "gram", "municipality"]
        }
        
        # Count matches for each category
        scores = {}
        for category, keywords in categories.items():
            score = 0
            for keyword in keywords:
                if keyword in text:
                    score += 1
            scores[category] = score
        
        # Find category with highest score
        max_score = 0
        best_category = "Policy News"  # Default
        
        for category, score in scores.items():
            if score > max_score:
                max_score = score
                best_category = category
        
        return best_category
    
    def assign_tags(self, title, summary):
        """Assign tags to articles based on content"""
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
            ]
        }
        
        # Check for each tag
        for tag, keywords in tag_rules.items():
            # Count how many keywords match
            matches = sum(1 for keyword in keywords if keyword in full_text)
            
            # Add tag if multiple matches or a strong single match
            if matches >= 2 or any(f" {keyword} " in f" {full_text} " for keyword in keywords):
                tags.append(tag)
        
        # Ensure at least one tag
        if not tags:
            # Add a default tag based on keywords
            if any(word in full_text for word in ['policy', 'government', 'ministry', 'official']):
                tags.append('Policy Development')
            else:
                tags.append('Policy News')  # Generic fallback
        
        # Limit to 3 tags maximum
        return tags[:3]
    
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
                    article = NewsArticle(
                        title=article_data['title'],
                        url=article_data['url'],
                        source=article_data['source'],
                        category=article_data['category'],
                        published_date=article_data['published_date'],
                        summary=article_data['summary'],
                        tags=article_data['tags']
                    )
                    articles.append(article)
                
                logger.info(f"Loaded {len(articles)} articles from cache")
        except Exception as e:
            logger.error(f"Error loading cached articles: {str(e)}")
        
        return articles
    
    def run(self, max_workers=6):
        """Main method that combines multiple strategies for best results"""
        start_time = time.time()
        
        try:
            logger.info("Starting PolicyRadar aggregator")
            all_articles = []
            
            # Step 1: Try Google News RSS (our most reliable source)
            google_articles = self.fetch_google_news_policy_articles(max_articles=100)
            all_articles.extend(google_articles)
            logger.info(f"Collected {len(google_articles)} articles from Google News")
            
            # Step 2: Try direct scraping of reliable sources
            direct_articles = self.direct_scrape_reliable_sources()
            all_articles.extend(direct_articles)
            logger.info(f"Collected {len(direct_articles)} articles from direct scraping")
            
            # Step 3: Try standard feed fetching
            feed_articles = self.fetch_all_feeds(max_workers)
            all_articles.extend(feed_articles)
            logger.info(f"Collected {len(feed_articles)} articles from feeds")
            
            # Step 4: Add historical/cached articles if we still need more
            if len(all_articles) < 15:
                cached_articles = self.load_cached_articles()
                if cached_articles:
                    # Only add cached articles we don't already have
                    new_cached = []
                    for article in cached_articles:
                        if article.content_hash not in self.article_hashes:
                            new_cached.append(article)
                            self.article_hashes.add(article.content_hash)
                    
                    all_articles.extend(new_cached)
                    logger.info(f"Added {len(new_cached)} articles from cache")
            
            # Step 5: Cache all current articles for future runs
            if all_articles:
                self.cache_articles(all_articles)
            
            # Generate HTML output
            output_file = self.generate_html(all_articles)
            
            # Generate health dashboard
            health_file = self.generate_health_dashboard()
            
            # Log summary
            end_time = time.time()
            runtime = end_time - start_time
            
            logger.info(f"PolicyRadar aggregator completed in {runtime:.2f} seconds")
            logger.info(f"Total articles: {len(all_articles)}")
            
            # Write debug report
            self.write_debug_report()
            
            return output_file
                
        except Exception as e:
            logger.error(f"Critical error running PolicyRadar: {str(e)}", exc_info=True)
            
            # Generate emergency content even on failure
            emergency_article = NewsArticle(
                title="PolicyRadar System Error",
                url="#",
                source="PolicyRadar System",
                category="System Notice",
                summary="Our aggregation system encountered an error. We're working to resolve this issue.",
                tags=["System Error"]
            )
            
            # Generate minimal HTML
            output_file = self.generate_minimal_html([emergency_article])
            return output_file
    
    def write_debug_report(self):
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
            
            logger.info(f"Debug report written to {report_file}")
            return report_file
        except Exception as e:
            logger.error(f"Failed to write debug report: {str(e)}")
            return None
    
    def generate_minimal_html(self, articles):
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
        
    def get_category_icon(self, category):
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
            "System Notice": "⚠️"
        }
        
        return icons.get(category, "📄")
        
    def generate_system_notice_html(self):
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
        
    def generate_html(self, articles):
        """Generate HTML output with proper categories and styling"""
        logger.info(f"Generating HTML output with {len(articles)} articles")
        
        # Sort articles by category
        articles_by_category = {}
        for article in articles:
            category = article.category
            if category not in articles_by_category:
                articles_by_category[category] = []
            articles_by_category[category].append(article)
        
        # Sort categories by name, but keep "System Notice" at the top if it exists
        sorted_categories = sorted(articles_by_category.keys())
        if "System Notice" in sorted_categories:
            sorted_categories.remove("System Notice")
            sorted_categories.insert(0, "System Notice")
        
        # Set up timestamp and build info
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        build_date = now.strftime("%B %d, %Y")
        
        # Start building HTML
        html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PolicyRadar - Indian Policy News Aggregator</title>
        <meta name="description" content="An aggregator for policy news from Indian sources, organized by sector">
        <meta name="keywords" content="India, policy, news, government, tech policy, economic policy, legal, environmental">
        <meta name="author" content="PolicyRadar">
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>🔍</text></svg>">
        <style>
            :root {{
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
            }}
            
            [data-theme="dark"] {{
                --primary-color: #1a1a2e;
                --secondary-color: #0f3460;
                --accent-color: #e94560;
                --background-color: #121212;
                --card-color: #1e1e1e;
                --text-color: #e0e0e0;
                --light-text: #aaaaaa;
                --link-color: #64b5f6;
                --link-hover: #90caf9;
                --border-color: #333333;
                --notice-bg: #2c2c2c;
                --notice-border: #ffd54f;
            }}
            
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--text-color);
                background-color: var(--background-color);
                padding-bottom: 2rem;
                transition: background-color 0.3s ease, color 0.3s ease;
            }}
            
            a {{
                color: var(--link-color);
                text-decoration: none;
                transition: color 0.2s;
            }}
            
            a:hover {{
                color: var(--link-hover);
                text-decoration: underline;
            }}
            
            .container {{
                width: 100%;
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 1rem;
            }}
            
            header {{
                background-color: var(--primary-color);
                color: white;
                padding: 1rem 0;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }}
            
            .header-content {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                flex-wrap: wrap;
            }}
            
            .logo {{
                display: flex;
                align-items: center;
                font-size: 1.5rem;
                font-weight: bold;
            }}
            
            .logo span {{
                margin-left: 0.5rem;
            }}
            
            .nav {{
                display: flex;
                align-items: center;
            }}
            
            .nav a {{
                color: white;
                margin-left: 1.5rem;
                font-size: 0.9rem;
            }}
            
            .theme-toggle {{
                background: none;
                border: none;
                color: white;
                cursor: pointer;
                font-size: 1.2rem;
                margin-left: 1rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            
            main {{
                padding: 2rem 0;
            }}
            
            .intro {{
                margin-bottom: 2rem;
                text-align: center;
            }}
            
            .intro h1 {{
                font-size: 2rem;
                margin-bottom: 0.5rem;
                color: var(--primary-color);
            }}
            
            .intro p {{
                color: var(--light-text);
                max-width: 700px;
                margin: 0 auto;
            }}
            
            .timestamp {{
                font-size: 0.8rem;
                color: var(--light-text);
                margin: 1rem 0;
                text-align: center;
            }}
            
            .categories {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
                margin-bottom: 1.5rem;
                justify-content: center;
            }}
            
            .category-link {{
                padding: 0.5rem 1rem;
                background-color: var(--card-color);
                border-radius: 20px;
                border: 1px solid var(--border-color);
                font-size: 0.9rem;
                transition: all 0.2s;
            }}
            
            .category-link:hover {{
                background-color: var(--secondary-color);
                color: white;
            }}
            
            .section {{
                margin-bottom: 3rem;
            }}
            
            .section-header {{
                display: flex;
                align-items: center;
                margin-bottom: 1rem;
                padding-bottom: 0.5rem;
                border-bottom: 2px solid var(--border-color);
            }}
            
            .section-icon {{
                margin-right: 0.5rem;
                font-size: 1.2rem;
            }}
            
            .section-title {{
                font-size: 1.4rem;
                color: var(--primary-color);
            }}
            
            .article-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 1.5rem;
            }}
            
            .article-card {{
                background-color: var(--card-color);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
                transition: transform 0.2s, box-shadow 0.2s;
                display: flex;
                flex-direction: column;
                height: 100%;
                border: 1px solid var(--border-color);
            }}
            
            .article-card:hover {{
                transform: translateY(-5px);
                box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1);
            }}
            
            .article-content {{
                padding: 1.2rem;
                flex-grow: 1;
                display: flex;
                flex-direction: column;
            }}
            
            .article-source {{
                font-size: 0.8rem;
                color: var(--light-text);
                margin-bottom: 0.5rem;
            }}
            
            .article-title {{
                font-size: 1.1rem;
                margin-bottom: 0.7rem;
                font-weight: 600;
                line-height: 1.3;
            }}
            
            .article-summary {{
                font-size: 0.9rem;
                margin-bottom: 1rem;
                color: var(--light-text);
                flex-grow: 1;
            }}
            
            .article-tags {{
                display: flex;
                flex-wrap: wrap;
                margin-top: auto;
                gap: 0.5rem;
            }}
            
            .tag {{
                font-size: 0.7rem;
                padding: 0.25rem 0.5rem;
                background-color: var(--secondary-color);
                color: white;
                border-radius: 12px;
                white-space: nowrap;
                opacity: 0.8;
            }}
            
            .notice-card {{
                background-color: var(--notice-bg);
                border: 1px solid var(--notice-border);
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 2rem;
            }}
            
            .notice-card .article-title {{
                color: var(--accent-color);
            }}
            
            .empty-category {{
                text-align: center;
                padding: 2rem;
                background-color: var(--card-color);
                border-radius: 8px;
                border: 1px solid var(--border-color);
            }}
            
            .empty-category p {{
                color: var(--light-text);
                margin-bottom: 1rem;
            }}
            
            .system-notice {{
                background-color: var(--notice-bg);
                border: 1px solid var(--notice-border);
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 2rem;
                text-align: center;
            }}
            
            .system-notice p {{
                font-size: 1rem;
                color: var(--text-color);
            }}
            
            footer {{
                background-color: var(--primary-color);
                color: white;
                padding: 2rem 0;
                text-align: center;
                margin-top: 2rem;
            }}
            
            .footer-content {{
                max-width: 600px;
                margin: 0 auto;
            }}
            
            .footer-links {{
                margin: 1rem 0;
            }}
            
            .footer-links a {{
                color: white;
                margin: 0 0.5rem;
                font-size: 0.9rem;
            }}
            
            .copyright {{
                font-size: 0.8rem;
                opacity: 0.8;
            }}
            
            /* Mobile Optimization */
            @media (max-width: 768px) {{
                .header-content {{
                    flex-direction: column;
                    text-align: center;
                }}
                
                .nav {{
                    margin-top: 1rem;
                    justify-content: center;
                }}
                
                .nav a {{
                    margin: 0 0.75rem;
                }}
                
                .article-grid {{
                    grid-template-columns: 1fr;
                }}
                
                .intro h1 {{
                    font-size: 1.5rem;
                }}
            }}
            
            @media (max-width: 600px) {{
                .container {{
                    padding: 0 0.5rem;
                }}
                
                .section-title {{
                    font-size: 1.2rem;
                }}
                
                .article-card {{
                    border-radius: 6px;
                }}
                
                .article-content {{
                    padding: 1rem;
                }}
                
                .article-title {{
                    font-size: 1rem;
                }}
                
                .article-summary {{
                    font-size: 0.85rem;
                }}
            }}
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
                        <a href="#">Home</a>
                        <a href="#about">About</a>
                        <a href="#" onclick="showHealth()">System Health</a>
                        <button class="theme-toggle" id="theme-toggle">🔆</button>
                    </div>
                </div>
            </div>
        </header>
        
        <main class="container">
            <div class="intro">
                <h1>PolicyRadar</h1>
                <p>Tracking policy developments across India. Updated daily with the latest policy news and analysis from trusted sources.</p>
            </div>
            
            <div class="timestamp">
                <p>Last updated: {timestamp} IST | Build {build_date}</p>
            </div>
            
            <!-- System notice for feed issues -->
            {self.generate_system_notice_html()}
            
            <!-- Category navigation -->
            <div class="categories">
    """
        
        # Add category links
        for category in sorted_categories:
            icon = self.get_category_icon(category)
            html += f'            <a href="#{category.replace(" ", "-").lower()}" class="category-link">{icon} {category}</a>\n'
        
        html += """        </div>
    """
        
        # Add articles by category
        for category in sorted_categories:
            category_articles = articles_by_category[category]
            
            icon = self.get_category_icon(category)
            html += f"""
            <section id="{category.replace(' ', '-').lower()}" class="section">
                <div class="section-header">
                    <div class="section-icon">{icon}</div>
                    <h2 class="section-title">{category}</h2>
                </div>
                
    """
            
            # If no articles in this category, show a message
            if not category_articles:
                html += """            <div class="empty-category">
                    <p>No recent articles found in this category. Check back soon for updates.</p>
                </div>
    """
            else:
                html += """            <div class="article-grid">
    """
                
                # Add articles in this category
                for article in category_articles[:12]:  # Limit to 12 per category
                    # Special styling for system notices
                    card_class = "notice-card" if category == "System Notice" else "article-card"
                    
                    html += f"""                <div class="{card_class}">
                        <div class="article-content">
                            <div class="article-source">{article.source}</div>
                            <h3 class="article-title"><a href="{article.url}" target="_blank" rel="noopener">{article.title}</a></h3>
                            <div class="article-summary">{article.summary if article.summary else 'No summary available.'}</div>
                            <div class="article-tags">
    """
                    
                    # Add tags
                    for tag in article.tags[:3]:  # Limit to 3 tags per article
                        html += f'                            <span class="tag">{tag}</span>\n'
                    
                    html += """                        </div>
                        </div>
                    </div>
    """
                
                html += """            </div>
    """
            
            html += """        </section>
    """
        
        # Add footer and JavaScript
        html += """    </main>
        
        <footer>
            <div class="container">
                <div class="footer-content">
                    <p><strong>PolicyRadar</strong> - Indian Policy News Aggregator</p>
                    <div class="footer-links">
                        <a href="#" id="about">About</a>
                        <a href="#" onclick="showHealth()">System Health</a>
                        <a href="https://github.com/example/policyradar" target="_blank">GitHub</a>
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
            
            // Show health dashboard in a new window
            function showHealth() {
                window.open('health.html', '_blank');
            }
            
            // About modal
            document.getElementById('about').addEventListener('click', (e) => {
                e.preventDefault();
                alert('PolicyRadar aggregates policy news from various Indian sources. Updated daily, it offers a curated collection of the latest policy developments across sectors including technology, economy, healthcare, environment, education, and more.');
            });
            
            // Smooth scrolling for anchor links
            document.querySelectorAll('a[href^="#"]').forEach(anchor => {
                anchor.addEventListener('click', function(e) {
                    if (this.getAttribute('href') === '#' || this.getAttribute('onclick')) {
                        return; // Skip links that are just "#" or have onclick
                    }
                    
                    e.preventDefault();
                    const targetId = this.getAttribute('href');
                    const targetElement = document.querySelector(targetId);
                    
                    if (targetElement) {
                        window.scrollTo({
                            top: targetElement.offsetTop - 100,
                            behavior: 'smooth'
                        });
                    }
                });
            });
        </script>
    </body>
    </html>"""

        # Write HTML to file
        output_file = os.path.join(Config.OUTPUT_DIR, 'index.html')
        try:
            # Ensure output directory exists
            os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"HTML output generated successfully: {output_file}")
        except Exception as e:
            logger.error(f"Error writing HTML file: {str(e)}")
            output_file = None
        
        return output_file
        
    def generate_health_dashboard(self):
        """Generate system health dashboard HTML"""
        # Set up timestamp
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate health metrics
        total_feeds = self.statistics.get('total_feeds', 0)
        successful_feeds = self.statistics.get('successful_feeds', 0)
        success_rate = (successful_feeds / total_feeds * 100) if total_feeds > 0 else 0
        
        total_articles = self.statistics.get('total_articles', 0)
        runtime = self.statistics.get('runtime', 0)
        
        # Determine system status
        if success_rate >= 80:
            system_status = "Healthy"
            status_color = "#4CAF50"  # Green
        elif success_rate >= 50:
            system_status = "Degraded"
            status_color = "#FF9800"  # Orange/Amber
        else:
            system_status = "Critical"
            status_color = "#F44336"  # Red
        
        # Build health dashboard HTML
        html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PolicyRadar - System Health</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>">
        <style>
            :root {{
                --primary-color: #2c3e50;
                --secondary-color: #3498db;
                --accent-color: #e74c3c;
                --background-color: #f9f9f9;
                --card-color: #ffffff;
                --text-color: #333333;
                --light-text: #777777;
                --link-color: #2980b9;
                --border-color: #dddddd;
                
                --healthy-color: #4CAF50;
                --warning-color: #FF9800;
                --critical-color: #F44336;
            }}
            
            [data-theme="dark"] {{
                --primary-color: #1a1a2e;
                --secondary-color: #0f3460;
                --accent-color: #e94560;
                --background-color: #121212;
                --card-color: #1e1e1e;
                --text-color: #e0e0e0;
                --light-text: #aaaaaa;
                --link-color: #64b5f6;
                --border-color: #333333;
            }}
            
            * {{
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }}
            
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--text-color);
                background-color: var(--background-color);
                padding-bottom: 2rem;
                transition: background-color 0.3s ease, color 0.3s ease;
            }}
            
            a {{
                color: var(--link-color);
                text-decoration: none;
            }}
            
            a:hover {{
                text-decoration: underline;
            }}
            
            .container {{
                width: 100%;
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 1rem;
            }}
            
            header {{
                background-color: var(--primary-color);
                color: white;
                padding: 1rem 0;
                position: sticky;
                top: 0;
                z-index: 100;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }}
            
            .header-content {{
                display: flex;
                justify-content: space-between;
                align-items: center;
            }}
            
            .logo {{
                display: flex;
                align-items: center;
                font-size: 1.5rem;
                font-weight: bold;
            }}
            
            .logo span {{
                margin-left: 0.5rem;
            }}
            
            .nav {{
                display: flex;
                align-items: center;
            }}
            
            .nav a {{
                color: white;
                margin-left: 1.5rem;
                font-size: 0.9rem;
            }}
            
            .theme-toggle {{
                background: none;
                border: none;
                color: white;
                cursor: pointer;
                font-size: 1.2rem;
                margin-left: 1rem;
            }}
            
            main {{
                padding: 2rem 0;
            }}
            
            .page-title {{
                text-align: center;
                margin-bottom: 2rem;
            }}
            
            .page-title h1 {{
                font-size: 2rem;
                color: var(--primary-color);
            }}
            
            .timestamp {{
                text-align: center;
                color: var(--light-text);
                margin-bottom: 2rem;
                font-size: 0.9rem;
            }}
            
            .status-card {{
                background-color: var(--card-color);
                border-radius: 8px;
                padding: 2rem;
                margin-bottom: 2rem;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
                text-align: center;
                border: 1px solid var(--border-color);
            }}
            
            .status-title {{
                font-size: 1.2rem;
                margin-bottom: 1rem;
                color: var(--light-text);
            }}
            
            .system-status {{
                font-size: 2rem;
                font-weight: bold;
                margin-bottom: 0.5rem;
            }}
            
            .health-metrics {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
                gap: 1.5rem;
                margin-bottom: 2rem;
            }}
            
            .metric-card {{
                background-color: var(--card-color);
                border-radius: 8px;
                padding: 1.5rem;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
                text-align: center;
                border: 1px solid var(--border-color);
            }}
            
            .metric-value {{
                font-size: 2rem;
                font-weight: bold;
                margin-bottom: 0.5rem;
                color: var(--secondary-color);
            }}
            
            .metric-label {{
                font-size: 1rem;
                color: var(--light-text);
            }}
            
            .feeds-table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 2rem;
                background-color: var(--card-color);
                border-radius: 8px;
                overflow: hidden;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05);
            }}
            
            .feeds-table th,
           .feeds-table td {
               padding: 1rem;
               text-align: left;
               border-bottom: 1px solid var(--border-color);
           }
           
           .feeds-table th {
               background-color: var(--primary-color);
               color: white;
               font-weight: 500;
           }
           
           .feeds-table tbody tr:hover {
               background-color: rgba(0, 0, 0, 0.02);
           }
           
           .feeds-table tbody tr:last-child td {
               border-bottom: none;
           }
           
           .status-indicator {
               display: inline-block;
               width: 10px;
               height: 10px;
               border-radius: 50%;
               margin-right: 5px;
           }
           
           .status-success {
               background-color: var(--healthy-color);
           }
           
           .status-failed {
               background-color: var(--critical-color);
           }
           
           .section-header {
               margin-bottom: 1.5rem;
               color: var(--primary-color);
               border-bottom: 2px solid var(--border-color);
               padding-bottom: 0.5rem;
           }
           
           footer {
               background-color: var(--primary-color);
               color: white;
               padding: 1.5rem 0;
               text-align: center;
               margin-top: 2rem;
           }
           
           .back-link {
               margin-top: 2rem;
               text-align: center;
           }
           
           .back-link a {
               padding: 0.5rem 1rem;
               background-color: var(--secondary-color);
               color: white;
               border-radius: 4px;
               transition: background-color 0.2s;
           }
           
           .back-link a:hover {
               background-color: #2980b9;
               text-decoration: none;
           }
           
           @media (max-width: 768px) {{
               .header-content {{
                   flex-direction: column;
               }}
               
               .nav {{
                   margin-top: 1rem;
               }}
               
               .health-metrics {{
                   grid-template-columns: 1fr;
               }}
           }}
           
       </style>
    </head>
    <body data-theme="light">
       <header>
           <div class="container">
               <div class="header-content">
                   <div class="logo">
                       📊 <span>PolicyRadar Status</span>
                   </div>
                   <div class="nav">
                       <a href="index.html">Home</a>
                       <button class="theme-toggle" id="theme-toggle">🔆</button>
                   </div>
               </div>
           </div>
       </header>
       
       <main class="container">
           <div class="page-title">
               <h1>System Health Dashboard</h1>
           </div>
           
           <div class="timestamp">
               <p>Last updated: {timestamp} IST</p>
           </div>
           
           <div class="status-card">
               <div class="status-title">Current System Status</div>
               <div class="system-status" style="color: {status_color};">{system_status}</div>
               <p>Success Rate: {success_rate:.1f}%</p>
           </div>
           
           <div class="health-metrics">
               <div class="metric-card">
                   <div class="metric-value">{successful_feeds}/{total_feeds}</div>
                   <div class="metric-label">Feeds Successfully Fetched</div>
               </div>
               
               <div class="metric-card">
                   <div class="metric-value">{total_articles}</div>
                   <div class="metric-label">Articles Collected</div>
               </div>
               
               <div class="metric-card">
                   <div class="metric-value">{runtime:.2f}s</div>
                   <div class="metric-label">Total Runtime</div>
               </div>
               
               <div class="metric-card">
                   <div class="metric-value">{self.statistics.get('direct_scrape_articles', 0)}</div>
                   <div class="metric-label">Articles from Direct Scraping</div>
               </div>
           </div>
           
           <h2 class="section-header">Feed Status Details</h2>
           
           <table class="feeds-table">
               <thead>
                   <tr>
                       <th>Source Name</th>
                       <th>Status</th>
                       <th>Articles</th>
                       <th>Method</th>
                   </tr>
               </thead>
               <tbody>
    """
       
       # Add feed health details
       for source_name, health in self.feed_health.items():
           status = health.get('status', 'unknown')
           count = health.get('count', 0)
           method = health.get('method', '-')
           
           status_class = "status-success" if status == "success" else "status-failed"
           
           html += f"""                <tr>
                       <td>{source_name}</td>
                       <td><span class="status-indicator {status_class}"></span> {status.capitalize()}</td>
                       <td>{count}</td>
                       <td>{method}</td>
                   </tr>
    """
       
       # Add footer and JavaScript
       html += """            </tbody>
           </table>
           
           <div class="back-link">
               <a href="index.html">Back to PolicyRadar</a>
           </div>
       </main>
       
       <footer>
           <div class="container">
               <p>&copy; 2025 PolicyRadar | System Health Dashboard</p>
           </div>
       </footer>
       
       <script>
           // Theme toggling functionality
           const themeToggle = document.getElementById('theme-toggle');
           const body = document.body;
           
           // Check for saved theme preference
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
    </html>
    """
       
       # Write HTML to file
       health_file = os.path.join(Config.OUTPUT_DIR, 'health.html')
       try:
           # Ensure output directory exists
           os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
           
           with open(health_file, 'w', encoding='utf-8') as f:
               f.write(html)
           logger.info(f"Health dashboard generated successfully: {health_file}")
       except Exception as e:
           logger.error(f"Error writing health dashboard file: {str(e)}")
           health_file = None
       
       return health_file


def main():
       """Main function"""
       parser = argparse.ArgumentParser(description='PolicyRadar - Indian Policy News Aggregator')
       parser.add_argument('--workers', type=int, default=6, help='Number of worker threads')
       parser.add_argument('--output', type=str, default='docs/index.html', help='Output HTML file')
       parser.add_argument('--debug', action='store_true', help='Enable debug logging')
       args = parser.parse_args()
       
       # Set debug logging if requested
       if args.debug:
           logger.setLevel(logging.DEBUG)
           logger.info("Debug logging enabled")
       
       try:
           logger.info("Starting PolicyRadar...")
           radar = PolicyRadar()
           output_file = radar.run(max_workers=args.workers)
           
           if output_file:
               print(f"Successfully generated PolicyRadar at {output_file}")
               return 0
           else:
               print("Failed to generate PolicyRadar output")
               return 1
       except Exception as e:
           logger.error(f"Error running PolicyRadar: {str(e)}", exc_info=True)
           print(f"Error: {str(e)}")
           return 1

if __name__ == "__main__":
       exit(main())

