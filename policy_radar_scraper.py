# Copyright (c) 2025 Roma Thakur
# Licensed under the MIT License

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

# Keep these imports at the top
from __future__ import annotations  # Add this at the top of your file
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
from collections import Counter, defaultdict  # Keep this single import
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from pathlib import Path
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
from datetime import datetime, timedelta

# REMOVE the duplicate imports below:
# from typing import List, Dict, Optional, Tuple, Set, Union, Any, Callable
# from collections import Counter

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
        import nltk
        
        # Try to download with the configured context
        try:
            # Download resources - REMOVED punkt_tab which was causing errors
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
            from nltk.corpus import stopwords
            from nltk.tokenize import word_tokenize
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
    
    # Add to Config class
    CRISIS_KEYWORDS = {
        'National Security': [
            'war', 'conflict', 'hostilities', 'military', 'troops', 'border', 'ceasefire',
            'pakistan', 'indo-pak', 'india-pakistan', 'loc', 'line of control',
            'air strike', 'artillery', 'missile', 'security threat', 'defense alert',
            'diplomatic crisis', 'evacuation', 'military action', 'casualties',
            'combat', 'airspace violation', 'territorial', 'sovereignty',
            'national security', 'emergency', 'terror', 'attack'
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
        "Defense & Security": [
            'defense', 'defence', 'security', 'military', 'army', 'navy', 'air force',
            'strategic', 'weapon', 'warfare', 'terrorist', 'terrorism', 'intelligence',
            'border', 'sovereignty', 'territorial', 'nuclear', 'missile', 'warfare', 
            'war', 'conflict', 'pakistan', 'indo-pak', 'loc', 'line of control',  # Added keywords
            'strike', 'ceasefire', 'combat', 'hostilities'  # Added keywords
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
        self.collection_timestamp = datetime.now()
        
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
        """Generate unique hash for article to prevent duplicates"""
        content = f"{self.title}{self.url}".lower()
        return hashlib.md5(content.encode()).hexdigest()
    
    def _parse_date(self, date_string):
        """Parse various date formats - returns naive datetime"""
        if not date_string:
            return datetime.now()
        
        if isinstance(date_string, datetime):
            # Convert to naive datetime if aware
            if date_string.tzinfo is not None:
                return date_string.replace(tzinfo=None)
            return date_string
            
        try:
            # Try various formats
            for fmt in ['%a, %d %b %Y %H:%M:%S %z', '%Y-%m-%dT%H:%M:%S%z', '%Y-%m-%d']:
                try:
                    dt = datetime.strptime(date_string, fmt)
                    # Convert to naive datetime by removing timezone info
                    return dt.replace(tzinfo=None)
                except:
                    continue
            
            # If all else fails, return current time
            return datetime.now()
        except:
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
        """Calculate various relevance scores for the article with crisis boosting"""
        # Initialize all variables at the start
        policy_relevance = 0.0
        source_reliability = 0.0
        recency = 0.0
        sector_specificity = 0.0
        crisis_score = 0.0  # New score for crisis relevance
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
            
            # 5. Crisis relevance score (0-1)
            crisis_keywords = [
                'pakistan', 'indo-pak', 'india-pakistan', 'loc', 'line of control',
                'air strike', 'artillery', 'missile', 'border', 'ceasefire',
                'military action', 'attack', 'security threat', 'defense alert',
                'combat', 'airspace', 'territorial', 'emergency'
            ]
            
            crisis_matches = sum(1 for keyword in crisis_keywords if keyword.lower() in text)
            if crisis_matches > 0:
                # Check for very high urgency indicators in the title specifically
                title_crisis = any(keyword in self.title.lower() for keyword in 
                               ['war', 'attack', 'emergency', 'missile', 'strike', 'pakistan'])
                
                # More matches = higher score, with a boost for title mentions
                crisis_score = min(1.0, (crisis_matches * 0.15) + (0.5 if title_crisis else 0))
            
            # Calculate overall score with weighted components - ADJUST WEIGHTS TO PRIORITIZE CRISIS
            overall = (
                policy_relevance * 0.25 +      # Decreased from 0.35
                source_reliability * 0.15 +    # Decreased from 0.25
                recency * 0.25 +               # Decreased from 0.30
                sector_specificity * 0.10 +    # Kept the same
                crisis_score * 0.25            # INCREASED crisis score weight (25%)
            )
            
            # Update the article's relevance scores
            self.relevance_scores = {
                'policy_relevance': round(policy_relevance, 2),
                'source_reliability': round(source_reliability, 2),
                'recency': round(recency, 2),
                'sector_specificity': round(sector_specificity, 2),
                'crisis_relevance': round(crisis_score, 2),  # New field
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
                'crisis_relevance': 0.0,  # New field
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
                return "Agriculture & Rural"
            elif any(word in text for word in ['labor', 'labour', 'employment', 'job', 'worker', 'workforce']):
                return "Labor & Employment"
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
        self.feeds = self._get_curated_feeds()
        
        # New field to store all articles for advanced filtering
        self.all_articles = []
        
        # Keep track of when each source was last successfully fetched
        self.source_last_update = {}
        
        # Load stored source reliability data if available
        self.source_reliability_data = self._load_source_reliability_data()
    

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
    
        # Solution 1: Add proper cache clearing with age limits
    def load_article_hashes(self, days=7):
        """Load article hashes from database, filtered by recency
        
        Args:
            days (int): Number of days to look back for filtering duplicates
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('SELECT hash FROM articles WHERE published_date >= ?', 
                         (cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),))
                self.article_hashes = set(row[0] for row in c.fetchall())
                logger.debug(f"Loaded {len(self.article_hashes)} article hashes from the last {days} days")
        except sqlite3.Error as e:
            logger.error(f"Database error loading article hashes: {e}")
            self.article_hashes = set()

    def clear_article_cache(self):
        """Clear the article hashes cache (both in-memory and optionally database)"""
        self.article_hashes = set()
        logger.info("Cleared article hash cache in memory")
        
        try:
            # Optionally also truncate the articles table to completely reset
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                # Just delete article hashes older than one day
                yesterday = datetime.now() - timedelta(days=1)
                c.execute('DELETE FROM articles WHERE published_date < ?', 
                         (yesterday.strftime("%Y-%m-%d %H:%M:%S"),))
                deleted_count = c.rowcount
                conn.commit()
                logger.info(f"Deleted {deleted_count} old articles from database")
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
        """Save article to database with enhanced metadata"""
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
            
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                
                c.execute('''REPLACE INTO articles 
                            (hash, title, url, source, category, published_date, summary,
                            content, tags, keywords, policy_relevance, source_reliability,
                            recency, sector_specificity, overall_relevance, metadata)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                        (article.content_hash, article.title, article.url, article.source,
                        article.category, article.published_date, article.summary,
                        article.content, json.dumps(article.tags), json.dumps(article.keywords),
                        article.relevance_scores['policy_relevance'],
                        article.relevance_scores['source_reliability'],
                        article.relevance_scores['recency'],
                        article.relevance_scores['sector_specificity'],
                        article.relevance_scores['overall'],
                        json.dumps(article.metadata)))
                
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error saving article: {e}")
    
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
    
    def _get_curated_feeds(self):
        """Return a carefully curated list of reliable Indian policy news feeds with improved categorization"""
        return [
            # Government sources - Critical for policy updates
            ("Press Information Bureau", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3", "Governance & Administration"),
            ("Ministry of Electronics & IT", "https://www.meity.gov.in/whatsnew", "Technology Policy"),
            ("Reserve Bank of India", "https://rbi.org.in/Scripts/BS_PressReleaseDisplay.aspx", "Economic Policy"),
            ("TRAI", "https://www.trai.gov.in/rss.xml", "Technology Policy"),

                # Added Defense & International News Sources for Crisis Coverage
            ("PTI News", "https://www.ptinews.com/home", "Defense & Security"),
            ("NDTV Defense", "https://www.ndtv.com/authors/vishnu-som-692", "Defense & Security"),
            ("Reuters India", "https://www.reuters.com/world/india/", "Defense & Security"),
            ("AFP News", "https://www.afp.com/en/actus/afp_communique/all/feed", "Defense & Security"),
            ("EIN News India", "https://www.einnews.com/rss/yLbHd_qDcH18vHzj", "Defense & Security"),
            ("AP News India", "https://apnews.com/hub/india", "Defense & Security"),
            ("The Hindu National", "https://www.thehindu.com/news/national/", "Defense & Security"),
            ("Indian Express India", "https://indianexpress.com/section/india/", "Defense & Security"),
            ("The Independent India", "https://www.independent.co.uk/asia/india", "Defense & Security"),
            ("BBC India", "https://www.bbc.com/news/world/asia/india", "Defense & Security"),
            ("CNN India", "https://edition.cnn.com/world/india", "Defense & Security"),
            ("France 24 India", "https://www.france24.com/en/tag/india/", "Defense & Security"),
            ("Al Jazeera India", "https://www.aljazeera.com/where/india/", "Defense & Security"),
            ("The News Minute", "https://www.thenewsminute.com/collection/latest-stories", "Defense & Security"),
            
            
            # Google News - Good coverage across sectors
            ("Google News - India Policy", "https://news.google.com/rss/search?q=india+policy+government&hl=en-IN&gl=IN&ceid=IN:en", "Policy News"),
            ("Google News - Economic Policy", "https://news.google.com/rss/search?q=india+economic+policy+budget+finance&hl=en-IN&gl=IN&ceid=IN:en", "Economic Policy"),
            ("Google News - Technology Policy", "https://news.google.com/rss/search?q=india+technology+policy+digital&hl=en-IN&gl=IN&ceid=IN:en", "Technology Policy"),
            ("Google News - Healthcare Policy", "https://news.google.com/rss/search?q=india+healthcare+policy+medical&hl=en-IN&gl=IN&ceid=IN:en", "Healthcare Policy"),
            ("Google News - Environmental Policy", "https://news.google.com/rss/search?q=india+environment+policy+climate&hl=en-IN&gl=IN&ceid=IN:en", "Environmental Policy"),
            
            # Think tanks and research organizations - High-quality analysis
            ("PRS Legislative", "https://dot.gov.in/whatsnew", "Constitutional & Legal"),
            ("Observer Research Foundation", "https://www.orfonline.org/feed/?post_type=research", "Policy Analysis"),
            ("CPR India", "https://cprindia.org/feed/", "Policy Analysis"),
            ("Carnegie India", "https://carnegieendowment.org/india", "Policy Analysis"),
            
            # Business & Economic sources
            ("The Hindu Business Line", "https://www.thehindubusinessline.com/economy/feeder/default.rss", "Economic Policy"),
            ("Business Standard Economy", "https://www.business-standard.com/rss/economy-policy-101.rss", "Economic Policy"),
            ("Economic Times Policy", "https://economictimes.indiatimes.com/news/economy/policy/rssfeeds/1286551326.cms", "Economic Policy"),
            ("Mint Economy", "https://www.livemint.com/rss/economy", "Economic Policy"),
            
            # Legal and Constitutional
            ("Bar and Bench", "https://www.barandbench.com/feed", "Constitutional & Legal"),
            ("LiveLaw", "https://www.livelaw.in/category/top-stories/google_feeds.xml", "Constitutional & Legal"),
            
            # Tech Policy
            ("MediaNama", "https://www.medianama.com/feed/", "Technology Policy"),
            ("Internet Freedom Foundation", "https://internetfreedom.in/rss", "Technology Policy"),
            
            # Major newspapers - General policy coverage
            ("The Hindu National", "https://www.thehindu.com/news/national/feeder/default.rss", "Governance & Administration"),
            ("Indian Express India", "https://indianexpress.com/section/india/feed/", "Governance & Administration"),
            ("Times of India India", "https://timesofindia.indiatimes.com/rssfeeds/296589292.cms", "Governance & Administration"),
            ("The Print India", "https://theprint.in/category/india/feed/", "Governance & Administration"),
            
            # Sector-specific sources
            ("The Hindu Education", "https://www.thehindu.com/education/feeder/default.rss", "Education Policy"),
            ("Down To Earth", "https://www.downtoearth.org.in/rss", "Environmental Policy"),
            ("The Hindu Agriculture", "https://www.thehindu.com/business/agri-business/feeder/default.rss", "Agricultural Policy"),
            ("Economic Times Healthcare", "https://health.economictimes.indiatimes.com/rss/topstories", "Healthcare Policy"),
            
            # Opinion and Analysis
            ("The Hindu Opinion", "https://www.thehindu.com/opinion/feeder/default.rss", "Policy Analysis"),
            ("Indian Express Opinion", "https://indianexpress.com/section/opinion/columns/feed/", "Policy Analysis"),
            ("Mint Opinion", "https://www.livemint.com/rss/opinion", "Policy Analysis"),
            ("Scroll Opinion", "https://scroll.in/rss/opinion", "Policy Analysis"),
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
        # Add these specialized conflict queries to your list
        india_pak_conflict_queries = [
            "Pakistan India border recent",
            "Pakistan India military recent",
            "India Pakistan ceasefire violation recent",
            "India Pakistan conflict latest",
            "India Pakistan war tension",
        ]

        
        all_queries = general_queries + sector_queries + site_queries + india_pak_conflict_queries
        
        
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
                            
                            # Calculate relevance
                            article.calculate_relevance_scores()
                            
                            # Only accept articles with reasonable relevance - LOWERED THRESHOLD
                            if article.relevance_scores['overall'] >= 0.2:  # Changed from 0.4 to 0.2
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
                logger.error(f"Error fetching Google News for query '{query}': {str(e)}")
            
            # Add a short delay between queries to avoid rate limiting
            time.sleep(random.uniform(0.5, 1.0))
        
        self.statistics['google_news_articles'] = len(all_articles)
        logger.info(f"Found {len(all_articles)} articles from Google News RSS")
        return all_articles
    
    def direct_scrape_reliable_sources(self):
        """Directly scrape the most reliable Indian policy news websites with enhanced targeting"""
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
            {
                "name": "Ministry of Electronics & IT",
                "url": "https://www.meity.gov.in/whatsnew",
                "category": "Technology Policy",
                "selectors": {
                    "article": ".view-content .views-row",
                    "title": "a",
                    "summary": "p",
                    "link": "a"
                }
            },
            {
                "name": "PIB - Press Release",
                "url": "https://pib.gov.in/AllReleasem.aspx",
                "category": "Governance & Administration",
                "selectors": {
                    "article": ".content-area article, .listing tr",
                    "title": "h3, a",
                    "summary": "p",
                    "link": "a"
                }
            },
            # TRAI website
            {
                "name": "TRAI Regulations",
                "url": "https://www.trai.gov.in/notifications/regulation",
                "category": "Technology Policy",
                "selectors": {
                    "article": "table tr",
                    "title": "td a",
                    "summary": "td:nth-child(2)",
                    "link": "td a"
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
            # Major newspapers - policy sections
            {
                "name": "The Hindu - Policy & Issues",
                "url": "https://www.thehindu.com/news/national/",
                "category": "Governance & Administration",
                "selectors": {
                    "article": ".story-card, .story-card-33, article",
                    "title": "h2, h3, .title, a.story-card-33-heading",
                    "summary": "p, .story-card-33-info, .summary",
                    "link": "a, .story-card-33 a"
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
            # Healthcare policy
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
            # Environmental policy
            {
                "name": "Down To Earth",
                "url": "https://www.downtoearth.org.in/news",
                "category": "Environmental Policy",
                "selectors": {
                    "article": ".list-item, article, .news-item",
                    "title": "h2, h3, .title, a",
                    "summary": "p, .summary, .excerpt",
                    "link": "a"
                }
            },
            # Legal news
            {
                "name": "LiveLaw Top Stories",
                "url": "https://www.livelaw.in/top-stories",
                "category": "Constitutional & Legal",
                "selectors": {
                    "article": ".post, article, .post-box",
                    "title": "h3, h2, .title, a",
                    "summary": ".post-content p, .summary, .excerpt",
                    "link": "a"
                }
            },
            
                        # Update problematic source URLs and selectors
            {
                "name": "PTI News",
                "url": "https://www.ptinews.com/",  # Try main page instead
                "category": "Defense & Security",
                "selectors": {
                    "article": ".news-item, .listing-item, article", 
                    "title": "h3, h2, .headline, a.title",
                    "summary": "p, .summary, .excerpt",
                    "link": "a"
                }
            },

            {
                "name": "NDTV Defense",
                "url": "https://www.ndtv.com/india",  # Try broader section
                "category": "Defense & Security",
                "selectors": {
                    "article": ".news_Itm, .new-featured-post, article",
                    "title": "h2, .newsHdng, .headline, a",
                    "summary": ".newsCont, p, .summary",
                    "link": "a"
                }
            },
                        
            {
                "name": "Bar and Bench",
                "url": "https://www.barandbench.com/news",
                "category": "Constitutional & Legal",
                "selectors": {
                    "article": "article, .post, .card",
                    "title": "h2, h3, .title",
                    "summary": "p, .excerpt, .entry-content",
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
                                
                                # Extract date if available
                                date_elem = element.select_one('.date, .time, .timestamp, [datetime]')
                                published_date = None
                                if date_elem:
                                    date_text = date_elem.get_text().strip()
                                    if date_text:
                                        try:
                                            from dateutil import parser
                                            published_date = parser.parse(date_text, fuzzy=True)
                                        except:
                                            published_date = None
                                    elif date_elem.has_attr('datetime'):
                                        try:
                                            published_date = parser.parse(date_elem['datetime'])
                                        except:
                                            published_date = None
                                
                                if not published_date:
                                    published_date = datetime.now()
                                
                                # Create article object
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
                                    
                                    # Calculate relevance
                                    article.calculate_relevance_scores()
                                    
                                    # Check for crisis-related content
                                    is_crisis_related = any(kw in (title + " " + summary).lower() for kw in [
                                        'pakistan', 'indo-pak', 'india-pakistan', 'loc', 'border', 'attack', 
                                        'ceasefire', 'missile'
                                    ])
                                    
                                    # Use lower threshold for crisis content
                                    relevance_threshold = 0.1 if is_crisis_related else 0.2  # Much lower for crisis articles
                                    
                                    # Apply threshold check
                                    if article.relevance_scores['overall'] >= relevance_threshold:
                                        # Add if not duplicate
                                        if article.content_hash not in self.article_hashes:
                                            self.article_hashes.add(article.content_hash)
                                            source_articles.append(article)
                                            self.save_article_to_db(article)
                                        else:
                                            self.statistics['low_relevance_articles'] += 1
                                            
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
        # Add these lines where you're processing articles
        duplicate_count = 0
        low_relevance_count = 0
        
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
                    
                # Add these lines to log the filtering statistics
                if duplicate_count > 0:
                    logger.info(f"Filtered {duplicate_count} duplicate articles from {source_name}")
                if low_relevance_count > 0:
                    logger.info(f"Filtered {low_relevance_count} low-relevance articles from {source_name}")
                    
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

                    # Add these lines to log the filtering statistics
            if duplicate_count > 0:
                logger.info(f"Filtered {duplicate_count} duplicate articles from {source_name}")
            if low_relevance_count > 0:
                logger.info(f"Filtered {low_relevance_count} low-relevance articles from {source_name}")
    
            
            
            return []
    
    def fetch_feed_with_retries(self, feed_url, source_name, category, retries=0):
        """Enhanced feed fetching with improved compatibility and better error handling"""
        max_retries = Config.MAX_RETRIES
        
        # Initialize empty list
        articles = []

        # Initialize tracking counters
        duplicate_count = 0
        low_relevance_count = 0
        
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
                                
                                # Extract content if available
                                content = ""
                                if hasattr(entry, 'content') and entry.content:
                                    for content_item in entry.content:
                                        if 'value' in content_item:
                                            content = self.clean_html(content_item.value)
                                            break
                                
                                # Create article
                                article = NewsArticle(
                                    title=title,
                                    url=link,
                                    source=source_name,
                                    category=category,
                                    published_date=published,
                                    summary=summary if summary else f"Policy news from {source_name}",
                                    content=content,
                                    tags=self.assign_tags(title, summary or content)
                                )
                                
                                # Calculate relevance
                                article.calculate_relevance_scores()

                                # Extract keywords
                                article.extract_keywords()

                                # Check for crisis-related content
                                is_crisis_related = any(kw in (title + " " + summary).lower() for kw in [
                                    'pakistan', 'indo-pak', 'india-pakistan', 'loc', 'border', 'attack', 
                                    'ceasefire', 'missile'
                                ])

                                # Use lower threshold for crisis content
                                relevance_threshold = 0.1 if is_crisis_related else 0.2  # Much lower for crisis articles

                                # Apply threshold check
                                if article.relevance_scores['overall'] >= relevance_threshold:
                                    # Check for duplicates
                                    if article.content_hash not in self.article_hashes:
                                        self.article_hashes.add(article.content_hash)
                                        articles.append(article)
                                        self.save_article_to_db(article)
                                    else:
                                        duplicate_count += 1
                                        # Log the first few duplicates to aid debugging
                                        if duplicate_count <= 3:
                                            logger.debug(f"Duplicate article: '{article.title}' from {article.source} (hash: {article.content_hash[:6]}...)")
                                else:
                                    low_relevance_count += 1
                                    self.statistics['low_relevance_articles'] += 1
                                    
                            except Exception as e:
                                logger.debug(f"Error processing feed entry: {str(e)}")
                                continue
                        
                        # MOVED OUTSIDE THE LOOP - update overall statistics after processing all articles
                        self.statistics['duplicate_articles'] += duplicate_count
                        self.statistics['filtered_articles'] += low_relevance_count
                        
                        logger.info(f"Extracted {len(articles)} articles from {source_name}")
                        logger.info(f"Filtered out: {duplicate_count} duplicates, {low_relevance_count} low relevance articles from {source_name}")
                        
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
                                from dateutil import parser
                                published_date = parser.parse(date_text)
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
                    
                    # Solution 2: Lower the relevance threshold
                    # In fetch_feed_with_retries and other similar methods, change:
                    if article.relevance_scores['overall'] >= 0.2:  # Changed from 0.4 to 0.2
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
    
    
    def scrape_articles_fallback(self, content: str, source_name: str, category: str, url: str) -> List[NewsArticle]:
        """Robust HTML scraping with progressive fallbacks for Indian news sites"""
        articles: List[NewsArticle] = []
        
        # Rest of the function remains the same
            
        try:
            logger.info(f"Attempting HTML scraping fallback for {source_name}")
            soup = BeautifulSoup(content, 'html.parser')
            
            # Site-specific patterns for major Indian news sources
            site_specific_selectors = {
                "thehindu": ".story-card-33, .story-card",
                "indianexpress": ".articles article, .ie-first-story, .article-block",
                "livemint": ".cardHolder, .story-list, article",
                "economictimes": ".eachStory, .story-card",
                "business-standard": ".listing-page, .aticle-list",
                "pib.gov.in": ".release-content, .content ul li",
                "prsindia.org": ".view-content .views-row, .bill-listing-item",
                "meity.gov.in": ".view-content .views-row",
                "livelaw.in": "article, .story-list .media",
                "medianama.com": "article, .post, .grid-post"
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
                # Try increasingly generic patterns
                generic_selectors = [
                    "article, .post, .story-card, .news-item, .card",
                    "div.story, div.news, div.article, section.story",
                    "div:has(h2) a[href], div:has(h3) a[href]",
                    ".content a[href], .container a[href]"
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
                    
                    # Extract date if available
                    published_date = None
                    date_elements = element.select('.date, time, .meta-date, .timestamp')
                    if date_elements:
                        date_text = date_elements[0].get_text().strip()
                        try:
                            published_date = self.parse_flexible_date(date_text)
                        except:
                            published_date = None
                    
                    # Create article with enhanced metadata
                    article = NewsArticle(
                        title=title,
                        url=link,
                        source=source_name,
                        category=category,
                        published_date=published_date,
                        summary=summary,
                        tags=self.assign_tags(title, summary)
                    )
                    
                    # Check for duplicates and relevance
                    if article.content_hash not in self.article_hashes and self.is_policy_relevant(article):
                        self.article_hashes.add(article.content_hash)
                        articles.append(article)
                        self.save_article_to_db(article)
            
            logger.info(f"HTML scraping for {source_name} found {len(articles)} articles")
            
        except Exception as e:
            logger.error(f"Error in HTML scraping for {source_name}: {str(e)}")
        
        return articles
    
    def categorize_article(self, title: str, summary: str, query: str = None) -> str:
        """Categorize article based on content using enhanced classification"""
        text = (title + " " + summary).lower()
        
        # First check if query provides a hint
        if query:
            query = query.lower()
            for sector, keywords in Config.POLICY_SECTORS.items():  # Changed from SECTOR_KEYWORDS
                if any(keyword.lower() in query for keyword in keywords):
                    return sector
        
        # Check for direct sector matches
        sector_scores = {}
        for sector, keywords in Config.POLICY_SECTORS.items():  # Changed from SECTOR_KEYWORDS
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
                return "Agriculture & Rural"
            elif any(word in text for word in ['labor', 'labour', 'employment', 'job', 'worker', 'workforce']):
                return "Labor & Employment"
            elif any(word in text for word in ['defense', 'defence', 'security', 'military', 'armed forces']):
                return "Defense & Security"
            else:
                return "Policy News"  # Default catch-all
        
        return best_sector
    
    def assign_tags(self, title, summary):
        """Assign tags to articles based on content with improved detection"""
        tags = []
        full_text = f"{title} {summary}".lower()
        
        # More lenient detection for India-Pakistan conflict
        conflict_indicators = [
            'pakistan', 'indo-pak', 'loc', 'line of control', 'border', 
            'ceasefire', 'military', 'troops', 'war', 'conflict', 'attack',
            'kashmir', 'tensions', 'security', 'defense'
        ]
        
        # Count matches
        conflict_matches = sum(1 for keyword in conflict_indicators if keyword in full_text)
        
        # If title directly mentions Pakistan or major conflict terms, or multiple indicators are present
        if ('pakistan' in title.lower() or 
            'war' in title.lower() or 
            'attack' in title.lower() or 
            conflict_matches >= 2):
            tags.append('India-Pakistan Conflict')
            logger.info(f"Added India-Pakistan Conflict tag to article: {title}")
        
        
        # Rest of your tagging logic...
            
        # Tag rules with clearer patterns
        tag_rules = {
            'Policy Analysis': [
                'analysis', 'study', 'report', 'research', 'survey', 'findings', 
                'data analysis', 'impact assessment', 'evaluation', 'review',
                'suggests', 'concludes', 'recommends', 'proposes', 'examines'
            ],
            'Legislative Updates': [
                'bill', 'act', 'parliament', 'amendment', 'legislation', 
                'rajya sabha', 'lok sabha', 'ordinance', 'draft bill',
                'passed', 'enacted', 'introduced', 'tabled', 'clause'
            ],
            'Regulatory Changes': [
                'regulation', 'rules', 'guidelines', 'notification', 'circular', 
                'compliance', 'enforcement', 'regulatory', 'mandate',
                'framework', 'mandatory', 'requirement', 'standards'
            ],
            'Court Rulings': [
                'court', 'supreme', 'judicial', 'judgment', 'verdict', 'tribunal',
                'hearing', 'petition', 'bench', 'justice', 'order', 'legal',
                'lawsuit', 'litigation', 'plea', 'challenge', 'writ'
            ],
            'Government Initiatives': [
                'scheme', 'program', 'initiative', 'launch', 'implementation', 
                'project', 'mission', 'flagship', 'campaign', 'yojana',
                'announced', 'inaugurated', 'ministry', 'minister', 'government'
            ],
            'Policy Debate': [
                'debate', 'discussion', 'consultation', 'feedback', 'opinion', 
                'perspective', 'stakeholder', 'controversy', 'criticism',
                'concerns', 'opposing', 'views', 'discourse', 'deliberation'
            ],
            'International Relations': [
                'bilateral', 'diplomatic', 'foreign', 'international', 'global',
                'relation', 'cooperation', 'treaty', 'agreement', 'pact',
                'partnership', 'strategic', 'dialogue', 'summit', 'delegation'
            ],
            'Digital Governance': [
                'digital', 'online', 'internet', 'tech', 'platform', 'data',
                'privacy', 'cyber', 'algorithm', 'ai', 'artificial intelligence',
                'electronic', 'e-governance', 'surveillance', 'security'
            ],
            'Economic Measures': [
                'budget', 'fiscal', 'monetary', 'tax', 'economy', 'financial',
                'gdp', 'investment', 'subsidy', 'stimulus', 'deficit',
                'reform', 'revenue', 'trade', 'commerce', 'industry'
            ],
            'Public Consultation': [
                'consultation', 'public input', 'feedback', 'draft', 'comments',
                'review', 'suggestions', 'stakeholder', 'participation',
                'discussion paper', 'white paper', 'deliberation'
            ],
            'Policy Implementation': [
                'implementation', 'rollout', 'enforcement', 'execution', 'compliance',
                'timeline', 'deadline', 'phase', 'effective from', 'operational'
            ]
        }

        # Ensure the crisis tag takes precedence in the list
        if 'India-Pakistan Conflict' in tags:
            tags.remove('India-Pakistan Conflict')
            tags.insert(0, 'India-Pakistan Conflict')
        
        # Check for each tag
        for tag, keywords in tag_rules.items():
            # Count how many keywords match
            matches = sum(1 for keyword in keywords if keyword in full_text)
            
            # Add tag if multiple matches or a strong single match
            if matches >= 2 or any(f" {keyword} " in f" {full_text} " for keyword in keywords[:5]):
                tags.append(tag)

        
        # Ensure at least one tag
        if not tags:
            # Add a default tag based on keywords
            if any(word in full_text for word in ['policy', 'government', 'ministry', 'official']):
                tags.append('Policy Development')
            else:
                tags.append('Policy News')  # Generic fallback
        
        # Limit to 3 tags maximum (prioritize more specific tags)
        return tags[:3]

    
        
        return tags

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

    def get_articles_from_db(self, days=7, limit=100, category=None, min_relevance=0):
        """Retrieve articles from database with filtering"""
        articles = []
        
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                conn.row_factory = sqlite3.Row
                c = conn.cursor()
                
                # Build query with parameters
                query = '''SELECT * FROM articles WHERE 1=1'''
                params = []
                
                # Add date filter
                if days > 0:
                    query += ' AND datetime(published_date) >= datetime("now", ?)'
                    params.append(f'-{days} days')
                
                # Add category filter
                if category:
                    query += ' AND category = ?'
                    params.append(category)
                
                # Add relevance filter
                if min_relevance > 0:
                    query += ' AND overall_relevance >= ?'
                    params.append(min_relevance)
                
                # Add ordering and limit
                query += ' ORDER BY datetime(published_date) DESC LIMIT ?'
                params.append(limit)
                
                # Execute query
                c.execute(query, params)
                
                # Process results
                for row in c.fetchall():
                    # Create article object
                    article = NewsArticle(
                        title=row['title'],
                        url=row['url'],
                        source=row['source'],
                        category=row['category'],
                        published_date=row['published_date'],
                        summary=row['summary'],
                        content=row['content'],
                        tags=json.loads(row['tags']) if row['tags'] else []
                    )
                    
                    # Set additional properties
                    article.content_hash = row['hash']
                    article.keywords = json.loads(row['keywords']) if row['keywords'] else []
                    article.relevance_scores = {
                        'policy_relevance': row['policy_relevance'],
                        'source_reliability': row['source_reliability'],
                        'recency': row['recency'],
                        'sector_specificity': row['sector_specificity'],
                        'overall': row['overall_relevance']
                    }
                    article.metadata = json.loads(row['metadata']) if row['metadata'] else {}
                    
                    articles.append(article)
        
        except sqlite3.Error as e:
            logger.error(f"Database error retrieving articles: {e}")
        
        return articles
    
    def parse_flexible_date(self, date_text):
        """Parse flexible date strings"""
        # Note: This method was used in scrape_articles_fallback but not defined
        if not date_text:
            return None
            
        try:
            from dateutil import parser
            return parser.parse(date_text, fuzzy=True)
        except:
            try:
                # Clean common patterns
                date_text = re.sub(r'(updated|posted|published):?\s*', '', date_text, flags=re.IGNORECASE)
                date_text = re.sub(r'\s+', ' ', date_text).strip()
                
                # Try manual parsing
                for fmt in [
                    '%d %B %Y',
                    '%d %b %Y',
                    '%B %d, %Y',
                    '%b %d, %Y',
                    '%Y-%m-%d',
                    '%d/%m/%Y',
                    '%m/%d/%Y'
                ]:
                    try:
                        return datetime.strptime(date_text, fmt)
                    except:
                        continue
                        
                # If all else fails
                return None
            except:
                return None

    def fetch_targeted_policy_news(self, max_articles=200):
        """Fetch policy news from multiple sources with intelligent targeting"""
        logger.info(f"Fetching targeted policy news (max: {max_articles} articles)")
        
        all_articles = []
        
        try:
            # Step 1: Get articles from RSS feeds first
            feed_articles = self.fetch_all_feeds(max_workers=6)
            logger.info(f"Collected {len(feed_articles)} articles from feeds")
            all_articles.extend(feed_articles)
            
            # Step 2: If we need more articles, try Google News
            if len(all_articles) < max_articles:
                remaining = max_articles - len(all_articles)
                logger.info(f"Fetching additional {remaining} articles from Google News")
                google_articles = self.fetch_google_news_policy_articles(max_articles=remaining)
                all_articles.extend(google_articles)
            
            # Step 3: If we still need more articles, try direct scraping
            if len(all_articles) < max_articles:
                remaining = max_articles - len(all_articles)
                logger.info(f"Fetching additional {remaining} articles via direct scraping")
                scraped_articles = self.direct_scrape_reliable_sources()
                all_articles.extend(scraped_articles)
            
            # Step 4: Deduplicate articles again (just in case)
            unique_hashes = set()
            unique_articles = []
            
            for article in all_articles:
                if article.content_hash not in unique_hashes:
                    unique_hashes.add(article.content_hash)
                    unique_articles.append(article)
            
            # Record statistics
            self.statistics['total_articles'] = len(unique_articles)
            self.statistics['high_importance_articles'] = sum(1 for a in unique_articles if a.relevance_scores.get('overall', 0) >= 0.7)
            self.statistics['critical_articles'] = sum(1 for a in unique_articles 
                                                    if a.relevance_scores.get('overall', 0) >= 0.7 
                                                    and a.relevance_scores.get('recency', 0) >= 0.8)
            
            logger.info(f"Successfully collected {len(unique_articles)} unique articles")
            return unique_articles
            
        except Exception as e:
            logger.error(f"Error fetching targeted policy news: {str(e)}", exc_info=True)
            # Return any articles we've managed to collect so far
            return all_articles

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

    def parse_flexible_date(self, date_text):
        """Parse flexible date strings"""
        if not date_text:
            return None
                
        try:
            from dateutil import parser
            return parser.parse(date_text, fuzzy=True)
        except:
            try:
                # Clean common patterns
                date_text = re.sub(r'(updated|posted|published):?\s*', '', date_text, flags=re.IGNORECASE)
                date_text = re.sub(r'\s+', ' ', date_text).strip()
                
                # Try manual parsing
                for fmt in [
                    '%d %B %Y',
                    '%d %b %Y',
                    '%B %d, %Y',
                    '%b %d, %Y',
                    '%Y-%m-%d',
                    '%d/%m/%Y',
                    '%m/%d/%Y'
                ]:
                    try:
                        return datetime.strptime(date_text, fmt)
                    except:
                        continue
                        
                # If all else fails
                return None
            except:
                return None

    def run(self, max_workers: int = 6) -> str:
        """Main method that combines multiple strategies for best results"""
        start_time = time.time()
        
        try:
            logger.info("Starting PolicyRadar aggregator")
            
            # Step 1: Collect articles from multiple sources using intelligent strategies
            all_articles = self.fetch_targeted_policy_news(max_articles=200)

            # Add this after collecting all articles in run() method
            crisis_related = [a for a in all_articles if 'india-pakistan' in (a.title + a.summary).lower() 
                              or 'pakistan' in (a.title + a.summary).lower()]
            logger.info(f"Found {len(crisis_related)} articles mentioning Pakistan or India-Pakistan")
            for idx, article in enumerate(crisis_related[:5]):
                logger.info(f"Crisis article {idx+1}: '{article.title}' from {article.source}")

            
            # Step 2: Sort articles by importance and recency
            sorted_articles = self.sort_articles_by_relevance(all_articles)

            
            # ADD THIS DEBUGGING CODE HERE
            crisis_articles = [a for a in sorted_articles if 'India-Pakistan Conflict' in a.tags]
            logger.info(f"Found {len(crisis_articles)} crisis-related articles")
            if crisis_articles:
                for ca in crisis_articles[:3]:  # Log details of up to 3 crisis articles
                    logger.info(f"Crisis article: {ca.title} | Tags: {ca.tags}")
            else:
                logger.info("No crisis-related articles found. Check if tagging is working properly.")
        
            
            # Step 3: Generate HTML output
            output_file = self.generate_html(sorted_articles)
            
            # Step 4: Generate system health dashboard
            health_file = self.generate_health_dashboard()
            
            # Step 5: Generate about page
            about_file = self.generate_about_page()
            
            # Step 6: Create JSON data file for API access
            data_file = self.export_articles_json(sorted_articles)
            
            # Log summary
            end_time = time.time()
            runtime = end_time - start_time
            
            logger.info(f"PolicyRadar aggregator completed in {runtime:.2f} seconds")
            logger.info(f"Total articles: {len(all_articles)}")
            logger.info(f"High importance articles: {self.statistics['high_importance_articles']}")
            logger.info(f"Critical (high importance + timely) articles: {self.statistics['critical_articles']}")
            
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

    def sort_articles_by_relevance(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Sort articles using a sophisticated relevance algorithm with crisis prioritization"""
    
  
        # Define source quality tiers
        source_tiers = {
            'tier1': ['pib', 'meity', 'rbi', 'supreme court', 'sebi', 'ministry'],  # Official sources
            'tier2': ['prs', 'medianama', 'livelaw', 'bar and bench', 'iff', 'orf'],  # Specialized policy sources
            'tier3': ['the hindu', 'indian express', 'economic times', 'livemint', 'business standard'],  # Major publications
            'tier4': ['google news', 'the wire', 'scroll', 'print']  # Aggregators and smaller publications
        }
        
        # Calculate source tier bonus for each article
        for article in articles:
            # Check if article is crisis-related
            is_crisis = 'India-Pakistan Conflict' in article.tags
            crisis_keywords = ['pakistan', 'indo-pak', 'border', 'attack', 'ceasefire', 'missile']
            has_crisis_keywords = any(kw in (article.title + " " + article.summary).lower() for kw in crisis_keywords)
            
            # Apply a crisis boost (add up to 0.3 to relevance score for crisis content)
            if is_crisis or has_crisis_keywords:
                # Update the 'overall' score in the relevance_scores dictionary
                article.relevance_scores['overall'] += 0.3
                
                # Also ensure the article has a combined_score for sorting
                if not hasattr(article, 'combined_score'):
                    article.combined_score = article.relevance_scores['overall']
                else:
                    article.combined_score += 0.3
                
        # Sort by the combined score
        return sorted(articles, key=lambda x: getattr(x, 'combined_score', x.relevance_scores['overall']), reverse=True)

    
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
            "Agriculture & Rural": "🌾",
            "Labor & Employment": "👷",
            "Defense & Security": "🛡️",
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


    def generate_html(self, articles: List[NewsArticle]) -> str:
        """Generate enhanced HTML output with proper categories and advanced filtering"""
        logger.info(f"Generating HTML output with {len(articles)} articles")

        # In generate_html method - replace the current crisis article detection with:
        potential_crisis_articles = [a for a in articles if any(
            keyword in (a.title + " " + a.summary).lower() 
            for keyword in ['pakistan', 'indo-pak', 'india-pakistan', 'loc', 'border', 'ceasefire']
        )]
        logger.info(f"Found {len(potential_crisis_articles)} potential crisis articles")

        # Use ALL potential crisis articles rather than filtering them further
        crisis_articles = potential_crisis_articles
        
        # Log a sample of crisis articles for debugging
        for article in potential_crisis_articles[:10]:  # Limit to first 10 for log clarity
            logger.info(f"Crisis article: '{article.title}' from {article.source}")
        
        # Double check crisis articles to prevent false positives
        crisis_articles = []
        for article in potential_crisis_articles:
            # Look for strong conflict indicators in title or summary
            text = (article.title + " " + article.summary).lower()
            strong_indicators = [
                "pakistan", "war", "indo-pak", "border clash", "ceasefire", 
                "military action", "cross-border", "loc", "line of control"
            ]
            
            # Count how many strong indicators are present
            indicator_count = sum(1 for indicator in strong_indicators if indicator in text)
            
            # Only include articles with at least 2 strong indicators
            if indicator_count >= 2:
                crisis_articles.append(article)
            else:
                # Remove the tag if it was a false positive
                if 'India-Pakistan Conflict' in article.tags:
                    article.tags.remove('India-Pakistan Conflict')
                    logger.info(f"Removed incorrect India-Pakistan Conflict tag from: {article.title}")

        if crisis_articles:
            logger.info(f"Adding crisis section with {len(crisis_articles)} articles")

        # Add this in generate_html after identifying crisis articles
        logger.info(f"Including {len(crisis_articles)} articles in crisis section")
        crisis_titles = [a.title for a in crisis_articles[:5]]
        logger.info(f"Crisis section preview: {crisis_titles}")
        
        # Group articles by category
        articles_by_category = defaultdict(list)
        for article in articles:
            category = article.category
            articles_by_category[category].append(article)
        
        # Sort categories by name, but keep "System Notice" at the top if it exists
        sorted_categories = sorted(articles_by_category.keys())
        if "System Notice" in sorted_categories:
            sorted_categories.remove("System Notice")
            sorted_categories.insert(0, "System Notice")
        
        # Add debugging to show article counts by category
        for category, articles_list in articles_by_category.items():
            logger.info(f"Category {category}: {len(articles_list)} articles")
        
        # Set up timestamp and build info
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        build_date = now.strftime("%B %d, %Y")
        
        # Generate list of unique sources for filtering
        all_sources = sorted(set(article.source for article in articles if article.source))
        
        # Generate list of all tags for filtering
        all_tags = set()
        for article in articles:
            all_tags.update(article.tags)
        all_tags = sorted(all_tags)
        
        # Start building HTML
        html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PolicyRadar - Indian Policy News Aggregator</title>
        <meta name="description" content="An intelligent aggregator for policy news from Indian sources, organized by sector">
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
                --high-importance: rgba(231, 76, 60, 0.1);
                --medium-importance: rgba(241, 196, 15, 0.1);
                --low-importance: rgba(236, 240, 241, 0.5);
            }}
            
            [data-theme="dark"] {{
                --primary-color: #16213e;         /* Keep dark blue for backgrounds */
                --primary-text-color: #e0e6f2;    /* NEW: Light blue-white for primary text */
                --secondary-color: #0f4c81;       /* Enhanced secondary blue */
                --accent-color: #e94560;          /* Kept your accent red */
                --background-color: #0f0f17;      /* Darker background for better contrast */
                --card-color: #1e2132;            /* More blue-tinted card background */
                --text-color: #f0f0f0;            /* Brighter text for better readability */
                --light-text: #c5c5c5;            /* Lighter secondary text */
                --link-color: #7ab3ef;            /* Brighter link color */
                --link-hover: #a5cdff;            /* Even brighter on hover */
                --border-color: #373e59;          /* Blue-tinted border for better definition */
                --notice-bg: #2a2a36;             /* Darker notice background */
                --notice-border: #ffd54f;         /* Kept yellow notice border */
                --high-importance: rgba(231, 76, 60, 0.3);    /* Increased opacity */
                --medium-importance: rgba(241, 196, 15, 0.2); /* Increased opacity */
                --low-importance: rgba(236, 240, 241, 0.15);  /* Increased opacity */
            }}

            /* Enhanced dark mode styling for consistent text colors */
            [data-theme="dark"] .intro h1,
            [data-theme="dark"] .section-title,
            [data-theme="dark"] .section-header,
            [data-theme="dark"] .page-title h1,
            [data-theme="dark"] .article-title,
            [data-theme="dark"] .article-title a {{
                color: var(--primary-text-color);
            }}

            /* Make sure PolicyRadar title in header has consistent color */
            [data-theme="dark"] .logo span {{
                color: white;
            }}

            /* Dark theme styling for filters toggle */
            [data-theme="dark"] .filters-toggle {{
                color: var(--primary-text-color);
            }}

            /* Ensure category links have good contrast */
            [data-theme="dark"] .category-link {{
                color: var(--text-color);
            }}

            [data-theme="dark"] .category-link:hover {{
                background-color: var(--secondary-color);
                color: white;
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
            
            .filters-container {{
                background-color: var(--card-color);
                border-radius: 8px;
                padding: 1rem;
                margin-bottom: 2rem;
                border: 1px solid var(--border-color);
            }}
            
            .filters-toggle {{
                display: flex;
                justify-content: space-between;
                align-items: center;
                cursor: pointer;
                font-weight: 600;
                color: var(--primary-color);
            }}
            
            .filters-content {{
                margin-top: 1rem;
                display: none;
            }}
            
            .filters-content.active {{
                display: block;
            }}
            
            .filter-group {{
                margin-bottom: 1rem;
            }}
            
            .filter-group-title {{
                font-weight: 600;
                margin-bottom: 0.5rem;
                font-size: 0.9rem;
                color: var(--primary-color);
            }}
            
            .filter-options {{
                display: flex;
                flex-wrap: wrap;
                gap: 0.5rem;
            }}
            
            .filter-option {{
                display: inline-block;
                padding: 0.25rem 0.75rem;
                border-radius: 16px;
                font-size: 0.8rem;
                background-color: var(--background-color);
                border: 1px solid var(--border-color);
                cursor: pointer;
                transition: all 0.2s;
            }}
            
            .filter-option:hover {{
                background-color: var(--secondary-color);
                color: white;
                border-color: var(--secondary-color);
            }}
            
            .filter-option.active {{
                background-color: var(--secondary-color);
                color: white;
                border-color: var(--secondary-color);
            }}
            
            .filter-actions {{
                display: flex;
                justify-content: flex-end;
                margin-top: 1rem;
            }}
            
            .filter-button {{
                padding: 0.5rem 1rem;
                border-radius: 4px;
                font-size: 0.9rem;
                cursor: pointer;
                transition: all 0.2s;
            }}
            
            .apply-filters {{
                background-color: var(--secondary-color);
                color: white;
                border: none;
            }}
            
            .apply-filters:hover {{
                background-color: var(--link-hover);
            }}
            
            .reset-filters {{
                background-color: transparent;
                color: var(--link-color);
                border: 1px solid var(--border-color);
                margin-right: 0.5rem;
            }}
            
            .reset-filters:hover {{
                background-color: var(--border-color);
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
                position: relative;
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
                display: flex;
                justify-content: space-between;
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

            /* Crisis-specific styles */
            .crisis-article {{
                border-left: 4px solid #e74c3c !important;
                background-color: rgba(231, 76, 60, 0.05);
            }}
            
            .crisis-tag {{
                background-color: #e74c3c !important;
                color: white !important;
                font-weight: bold;
            }}
       
            
            .importance-indicator {{
                position: absolute;
                top: 0;
                left: 0;
                width: 4px;
                height: 100%;
            }}
            
            .importance-high {{
                background-color: #e74c3c;
            }}
            
            .importance-medium {{
                background-color: #f39c12;
            }}
            
            .importance-low {{
                background-color: #95a5a6;
            }}
            
            .article-date {{
                font-size: 0.75rem;
                color: var(--light-text);
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
            
            .search-container {{
                margin-bottom: 2rem;
                display: flex;
                align-items: center;
                justify-content: center;
            }}
            
            .search-box {{
                display: flex;
                width: 100%;
                max-width: 600px;
                position: relative;
            }}
            
            .search-input {{
                flex-grow: 1;
                padding: 0.75rem 1rem;
                padding-left: 3rem;
                border-radius: 8px;
                border: 1px solid var(--border-color);
                font-size: 1rem;
                background-color: var(--card-color);
                color: var(--text-color);
                transition: all 0.2s;
                width: 100%;
            }}
            
            .search-input:focus {{
                outline: none;
                border-color: var(--secondary-color);
                box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2);
            }}
            
            .search-icon {{
                position: absolute;
                left: 1rem;
                top: 50%;
                transform: translateY(-50%);
                color: var(--light-text);
                font-size: 1.2rem;
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
    """
        # Log that crisis CSS styles were added
        logger.info("Added crisis CSS styles to HTML")

        # Add body and header
        html += f"""
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
            <div class="intro">
                <h1>PolicyRadar</h1>
                <p>Tracking policy developments across India. Updated with the latest policy news and analysis from trusted sources.</p>
            </div>
            
            <div class="timestamp">
                <p>Last updated: {timestamp} IST | Build {build_date}</p>
            </div>
            
            <!-- System notice for feed issues -->
            {self.generate_system_notice_html()}
    """

        # Sort crisis articles by relevance
        sorted_crisis_articles = sorted(crisis_articles, 
                                       key=lambda x: x.relevance_scores.get('overall', 0), 
                                       reverse=True)

        # Take up to 20 articles for display in crisis section
        crisis_display_articles = sorted_crisis_articles[:20]  # Show up to 20 instead of just 5


        # Then in the generate_html function where crisis articles are displayed:
        if crisis_display_articles:
            html += """
            <div class="crisis-alert" style="background-color: rgba(231, 76, 60, 0.1); border: 2px solid #e74c3c; border-radius: 8px; padding: 1rem; margin-bottom: 2rem;">
                <h2 style="color: #e74c3c;">⚠️ India-Pakistan Conflict Updates</h2>
                <div class="crisis-grid" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1rem; margin-top: 1rem;">
            """
            
            # Add reliable timestamp tracking
            current_time = datetime.now()
            collection_time = getattr(self, 'collection_timestamp', current_time)
            
            # Add ALL crisis articles to the section with better timestamps
            for article in crisis_display_articles:
                # Default display format: Use the article's source
                display_time = ""
                
                # APPROACH 1: Try to use source-specific date patterns (most reliable for news)
                if article.source == "The Hindu" or article.source == "The Indian Express":
                    # Major papers usually have today's articles - show as "Today"
                    display_time = "Today"
                elif "Mint" in article.source or "Economic Times" in article.source:
                    # Financial papers typically have very recent news
                    display_time = "Latest"
                elif "BBC" in article.source or "Al Jazeera" in article.source:
                    # International sources might be reporting on significant developments
                    display_time = "Breaking"
                
                # APPROACH 2: Use collection timing to indicate recency
                # Add a "New" indicator for articles likely collected in the current run
                minutes_since_collection = int((current_time - collection_time).total_seconds() / 60)
                if minutes_since_collection < 30:  # If these were collected recently
                    display_time = "New"
                    
                # APPROACH 3: Use actual dates if they look reasonable
                if hasattr(article, 'published_date') and article.published_date:
                    try:
                        # Format as date string if it's from before today
                        if isinstance(article.published_date, datetime):
                            today = datetime.now().date()
                            article_date = article.published_date.date()
                            
                            if article_date == today:
                                # Only override with time if we're confident about it
                                if article.published_date.hour != 0 or article.published_date.minute != 0:
                                    display_time = article.published_date.strftime("%H:%M")
                            elif (today - article_date).days == 1:
                                display_time = "Yesterday"
                            else:
                                display_time = article.published_date.strftime("%d %b")
                    except:
                        pass  # Keep the display_time we already set if there's an error
                
                html += f"""
                    <div class="crisis-card" style="padding: 0.75rem; border-left: 4px solid #e74c3c; background-color: rgba(231, 76, 60, 0.05);">
                        <h3 class="article-title" style="font-size: 1rem; margin-bottom: 0.5rem;"><a href="{article.url}" target="_blank">{article.title}</a></h3>
                        <div class="article-source" style="font-size: 0.8rem; color: #666; display: flex; justify-content: space-between;">
                            <span>{article.source}</span>
                            {f'<span class="article-time" style="font-style: italic; color: #888;">{display_time}</span>' if display_time else ''}
                        </div>
                    </div>
                """
                
            html += """
                </div>
            </div>
           """
        # Add search bar and filters
        html += """
            <!-- Search Bar -->
            <div class="search-container">
                <div class="search-box">
                    <span class="search-icon">🔍</span>
                    <input type="text" class="search-input" id="search-input" placeholder="Search for policy news...">
                </div>
            </div>
            
            <!-- Filters Panel -->
            <div class="filters-container">
                <div class="filters-toggle" id="filters-toggle">
                    <span>Filter articles by source, importance, and more</span>
                    <span id="toggle-icon">▼</span>
                </div>
                <div class="filters-content" id="filters-content">
                    <div class="filter-group">
                        <div class="filter-group-title">Categories</div>
                        <div class="filter-options" id="category-filters">
    """
        
        # Add category filter options
        for category in sorted_categories:
            html += f'                    <span class="filter-option" data-filter="category" data-value="{category}">{self.get_category_icon(category)} {category}</span>\n'

        html += """                </div>
                    </div>
                    
                    <div class="filter-group">
                        <div class="filter-group-title">Sources</div>
                        <div class="filter-options" id="source-filters">
    """
        
        # Add source filter options (limit to top 15 for UI cleanliness)
        for source in all_sources[:15]:
            html += f'                    <span class="filter-option" data-filter="source" data-value="{source}">{source}</span>\n'

        html += """                </div>
                    </div>
                    
                    <div class="filter-group">
                        <div class="filter-group-title">Importance</div>
                        <div class="filter-options" id="importance-filters">
                            <span class="filter-option" data-filter="importance" data-value="high">High Priority</span>
                            <span class="filter-option" data-filter="importance" data-value="medium">Medium Priority</span>
                            <span class="filter-option" data-filter="importance" data-value="low">Low Priority</span>
                        </div>
                    </div>
                    
                    <div class="filter-group">
                        <div class="filter-group-title">Tags</div>
                        <div class="filter-options" id="tag-filters">
    """
        
        # Add tag filter options (limit to top 10 for UI cleanliness)
        for tag in all_tags[:10]:
            html += f'                    <span class="filter-option" data-filter="tag" data-value="{tag}">{tag}</span>\n'

        html += """                </div>
                    </div>
                    
                    <div class="filter-actions">
                        <button class="filter-button reset-filters" id="reset-filters">Reset Filters</button>
                        <button class="filter-button apply-filters" id="apply-filters">Apply Filters</button>
                    </div>
                </div>
            </div>
            
            <!-- Category navigation -->
            <div class="categories">
    """
        
        # Add category links
        for category in sorted_categories:
            icon = self.get_category_icon(category)
            html += f'        <a href="#{category.replace(" ", "-").lower()}" class="category-link">{icon} {category}</a>\n'

        html += """    </div>
    """
        
        # Add articles by category
        for category in sorted_categories:
            category_articles = articles_by_category[category]
            
            icon = self.get_category_icon(category)
            html += f"""
            <section id="{category.replace(' ', '-').lower()}" class="section" data-category="{category}">
                <div class="section-header">
                    <div class="section-icon">{icon}</div>
                    <h2 class="section-title">{category}</h2>
                </div>
                
    """
            
            # If no articles in this category, show a message
            if not category_articles:
                html += """        <div class="empty-category">
                    <p>No recent articles found in this category. Check back soon for updates.</p>
                </div>
    """
            else:
                html += """        <div class="article-grid">
    """
                
                # Allow more articles for Defense & Security category
                article_limit = 25 if category == "Defense & Security" else 12
                for article in category_articles[:article_limit]:  # Display more defense articles
                    # Check if this is a crisis-related article
                    crisis_related = 'India-Pakistan Conflict' in article.tags
                    
                    # Special styling for system notices or crisis articles
                    card_class = "notice-card" if category == "System Notice" else f"article-card{' crisis-article' if crisis_related else ''}"
                    
                    # Determine importance class
                    importance_class = "importance-low"
                    if hasattr(article, 'importance'):
                        if article.importance >= 0.7:
                            importance_class = "importance-high"
                        elif article.importance >= 0.4:
                            importance_class = "importance-medium"
                    
                    # Format date for display
                    display_date = ""
                    if hasattr(article, 'published_date') and article.published_date:
                        try:
                            if isinstance(article.published_date, str):
                                # Try to parse the date string
                                date_obj = self.parse_flexible_date(article.published_date)
                                if date_obj:
                                    display_date = date_obj.strftime("%d %b %Y")
                            elif isinstance(article.published_date, datetime):
                                display_date = article.published_date.strftime("%d %b %Y")
                        except:
                            # If date parsing fails, leave it blank
                            pass
                    
                    # Add data attributes for filtering
                    data_attrs = f'data-source="{article.source}" data-category="{article.category}"'
                    
                    if hasattr(article, 'importance'):
                        importance_level = "high" if article.importance >= 0.7 else "medium" if article.importance >= 0.4 else "low"
                        data_attrs += f' data-importance="{importance_level}"'
                    
                    if hasattr(article, 'tags') and article.tags:
                        data_attrs += f' data-tags="{" ".join(article.tags)}"'
                    
                    html += f"""            <div class="{card_class}" {data_attrs}>
                        <div class="importance-indicator {importance_class}"></div>
                        <div class="article-content">
                            <div class="article-source">
                                <span>{article.source}</span>
                                <span class="article-date">{display_date}</span>
                            </div>
                            <h3 class="article-title"><a href="{article.url}" target="_blank" rel="noopener">{article.title}</a></h3>
                            <div class="article-summary">{article.summary if article.summary else 'No summary available.'}</div>
                            <div class="article-tags">
    """
                    
                    # Add tags with special styling for crisis tags
                    for tag in article.tags[:3]:  # Limit to 3 tags per article
                        tag_class = "tag crisis-tag" if tag == "India-Pakistan Conflict" else "tag"
                        html += f'                        <span class="{tag_class}">{tag}</span>\n'
                    
                    html += """                    </div>
                        </div>
                    </div>
    """
                
            html += """        </div>
        </section>
    """
        
        # Add footer and JavaScript
        html += """</main>

    <footer>
        <div class="container">
            <div class="footer-content">
                <p><strong>PolicyRadar</strong> - Indian Policy News Aggregator</p>
                <div class="footer-links">
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
        
        // Filters toggle
        const filtersToggle = document.getElementById('filters-toggle');
        const filtersContent = document.getElementById('filters-content');
        const toggleIcon = document.getElementById('toggle-icon');
        
        filtersToggle.addEventListener('click', () => {
            filtersContent.classList.toggle('active');
            toggleIcon.textContent = filtersContent.classList.contains('active') ? '▲' : '▼';
        });
        
        // Filter functionality
        const filterOptions = document.querySelectorAll('.filter-option');
        const resetFiltersBtn = document.getElementById('reset-filters');
        const applyFiltersBtn = document.getElementById('apply-filters');
        const articleCards = document.querySelectorAll('.article-card');
        const sections = document.querySelectorAll('.section');
        
        // Search functionality
        const searchInput = document.getElementById('search-input');
        
        searchInput.addEventListener('input', () => {
            const searchTerm = searchInput.value.toLowerCase();
            
            articleCards.forEach(card => {
                const title = card.querySelector('.article-title').textContent.toLowerCase();
                const summary = card.querySelector('.article-summary').textContent.toLowerCase();
                const source = card.dataset.source.toLowerCase();
                
                if (searchTerm === '') {
                    card.style.display = 'flex'; // Show all cards when search is empty
                } else if (title.includes(searchTerm) || summary.includes(searchTerm) || source.includes(searchTerm)) {
                    card.style.display = 'flex'; // Show matching cards
                } else {
                    card.style.display = 'none'; // Hide non-matching cards
                }
            });
            
            // Show/hide sections based on visible cards
            sections.forEach(section => {
                const visibleCards = section.querySelectorAll('.article-card[style="display: flex;"]');
                if (visibleCards.length === 0 && searchTerm !== '') {
                    section.style.display = 'none';
                } else {
                    section.style.display = 'block';
                }
            });
        });
        
        // Handle filter option clicks
        filterOptions.forEach(option => {
            option.addEventListener('click', () => {
                option.classList.toggle('active');
            });
        });
        
        // Apply filters
        applyFiltersBtn.addEventListener('click', () => {
            // Get selected filters
            const activeFilters = {
                category: [],
                source: [],
                importance: [],
                tag: []
            };
            
            document.querySelectorAll('.filter-option.active').forEach(option => {
                const filterType = option.dataset.filter;
                const filterValue = option.dataset.value;
                activeFilters[filterType].push(filterValue);
            });
            
            // Apply filters to articles
            articleCards.forEach(card => {
                let isVisible = true;
                
                // Category filter
                if (activeFilters.category.length > 0) {
                    if (!activeFilters.category.includes(card.dataset.category)) {
                        isVisible = false;
                    }
                }
                
                // Source filter
                if (isVisible && activeFilters.source.length > 0) {
                    if (!activeFilters.source.includes(card.dataset.source)) {
                        isVisible = false;
                    }
                }
                
                // Importance filter
                if (isVisible && activeFilters.importance.length > 0) {
                    if (!activeFilters.importance.includes(card.dataset.importance)) {
                        isVisible = false;
                    }
                }
                
                // Tag filter
                if (isVisible && activeFilters.tag.length > 0) {
                    const cardTags = (card.dataset.tags || '').split(' ');
                    let hasTag = false;
                    
                    for (const tag of activeFilters.tag) {
                        if (cardTags.includes(tag)) {
                            hasTag = true;
                            break;
                        }
                    }
                    
                    if (!hasTag) {
                        isVisible = false;
                    }
                }
                
                // Apply visibility
                card.style.display = isVisible ? 'flex' : 'none';
            });
            
            // Show/hide sections based on visible cards
            sections.forEach(section => {
                const visibleCards = section.querySelectorAll('.article-card[style="display: flex;"]');
                section.style.display = visibleCards.length > 0 ? 'block' : 'none';
            });
        });
        
        // Reset filters
        resetFiltersBtn.addEventListener('click', () => {
            // Remove active class from all filter options
            filterOptions.forEach(option => {
                option.classList.remove('active');
            });
            
            // Show all articles
            articleCards.forEach(card => {
                card.style.display = 'flex';
            });
            
            // Show all sections
            sections.forEach(section => {
                section.style.display = 'block';
            });
            
            // Clear search
            searchInput.value = '';
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
            
    def generate_health_dashboard(self) -> Optional[str]:
        """Generate system health dashboard HTML with detailed stats"""
        # Set up timestamp
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        
        # Calculate health metrics
        total_feeds = self.statistics.g