from __future__ import annotations
from typing import List, Dict, Optional, Tuple, Set, Union, Any, Callable
import urllib.parse
import requests
import sys
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

# Create necessary directories first
DIRS = ['logs', 'cache', 'data', 'docs', 'backup', 'exports']
for directory in DIRS:
    Path(directory).mkdir(exist_ok=True)

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

# Filter out warnings
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning, module='feedparser')

# Disable SSL warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# SSL and NLTK configuration
def configure_nltk_ssl():
    """Configure SSL for NLTK downloads across different platforms"""
    try:
        if platform.system() == 'Darwin':
            ssl._create_default_https_context = ssl._create_unverified_context
            logger.info("Configured unverified SSL context for macOS NLTK downloads")
        
        import nltk
        
        try:
            nltk.download('punkt', quiet=True)
            nltk.download('stopwords', quiet=True)
            logger.info("Successfully downloaded NLTK resources")
        except Exception as download_error:
            logger.warning(f"Error downloading NLTK resources: {str(download_error)}")
            
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

def configure_dateutil():
    """Configure dateutil with proper error handling"""
    try:
        from dateutil import parser
        logger.info("python-dateutil loaded successfully")
        return True, parser
    except ImportError:
        logger.warning("python-dateutil not available. Date parsing will be limited.")
        return False, None

# Execute NLTK configuration
NLTK_AVAILABLE, stopwords_module, word_tokenize_func = configure_nltk_ssl()

# Execute dateutil configuration
DATEUTIL_AVAILABLE, dateutil_parser = configure_dateutil()

if NLTK_AVAILABLE:
    try:
        stopwords = stopwords_module
        word_tokenize = word_tokenize_func
        logger.info("NLTK modules loaded successfully")
    except Exception as e:
        logger.warning(f"Error setting up NLTK modules: {str(e)}")
        NLTK_AVAILABLE = False
else:
    logger.warning("Using fallback text processing instead of NLTK")
    
    def simple_tokenize(text):
        text = re.sub(r'[^\w\s]', ' ', text.lower())
        return text.split()
    
    COMMON_STOPWORDS = {
        'a', 'an', 'the', 'and', 'or', 'but', 'if', 'because', 'as', 'what',
        'which', 'this', 'that', 'these', 'those', 'then', 'just', 'so', 'than',
        'such', 'both', 'through', 'about', 'for', 'is', 'of', 'while', 'during',
        'to', 'from', 'in', 'on', 'at', 'by', 'with', 'about', 'against', 'between',
        'into', 'through', 'after', 'before', 'above', 'below', 'up', 'down', 'out'
    }
    
    class FallbackStopwords:
        @staticmethod
        def words(language):
            if language.lower() == 'english':
                return COMMON_STOPWORDS
            return set()
    
    word_tokenize = simple_tokenize
    stopwords = FallbackStopwords()


class Config:
    """Configuration class with all settings"""
    # Directories
    OUTPUT_DIR = 'docs'
    CACHE_DIR = 'cache'
    DATA_DIR = 'data'
    LOG_DIR = 'logs'
    BACKUP_DIR = 'backup'
    EXPORT_DIR = 'exports'
    
    # Timing
    CACHE_DURATION = 7200
    BACKUP_DURATION = 86400
    RETRY_DELAY = 1.5
    REQUEST_TIMEOUT = 20
    DEDUPLICATION_DAYS = 7
    
    # Retry settings
    MAX_RETRIES = 3
    RETRY_STATUS_CODES = [429, 500, 502, 503, 504]
    
    # User agents for rotation
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0',
        'Feedly/1.0 (+http://www.feedly.com/fetcher.html; like FeedFetcher-Google)',
        'Mozilla/5.0 (compatible; Inoreader/1.0; https://www.inoreader.com)'
    ]
    
    # Database
    DB_FILE = 'data/policyradar.db'
    DB_SCHEMA_VERSION = '1.0'
    
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
        "Defense & Security": [
            'defense', 'defence', 'security', 'military', 'army', 'navy', 'air force',
            'strategic', 'weapon', 'warfare', 'terrorist', 'terrorism', 'intelligence',
            'border', 'sovereignty', 'territorial', 'nuclear', 'missile', 'warfare', 
            'war', 'conflict', 'pakistan', 'indo-pak', 'loc', 'line of control',
            'strike', 'ceasefire', 'combat', 'hostilities'
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
        
        # Think tanks & Research organizations
        'PRS Legislative Research': 4.5,
        'Observer Research Foundation': 4.5,
        'ORF': 4.5,
        'Centre for Policy Research': 4.5,
        'CPR India': 4.5,
        'Takshashila Institution': 4.5,
        'IDFC Institute': 4.5,
        'Carnegie India': 4.5,
        'Gateway House': 4.5,
        
        # Legal news sources
        'LiveLaw': 4.5,
        'Bar and Bench': 4.5,
        'SCC Online': 4.5,
        
        # Policy-focused media
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
        
        # General news
        'Times of India': 3.5,
        'NDTV': 3.5,
        'India Today': 3.5,
        'Hindustan Times': 3.5,
        'News18': 3.5,
        'The News Minute': 3.5,
        'FirstPost': 3.5,
        
        # Google News
        'Google News': 3.0
    }

class NewsArticle:
    """Enhanced article class with improved metadata and relevance scoring"""
    
    def __init__(self, title, url, source, category, published_date=None, summary=None, content=None, tags=None):
        self.title = title
        self.url = url
        self.source = source
        self.category = category
        
        self.raw_date = published_date if isinstance(published_date, str) else None
        self.timestamp_verified = False
        self.timestamp_source = "unknown"
        
        self.published_date = self._parse_date(published_date)
        
        self.summary = summary or ""
        self.content = content or ""
        self.tags = tags or []
        self.keywords = []
        self.content_hash = self._generate_hash()
        
        self.importance = 0.0
        self.timeliness = 0.0
        
        self.relevance_scores = {
            'policy_relevance': 0,
            'source_reliability': 0,
            'recency': 0,
            'sector_specificity': 0,
            'overall': 0
        }
        
        self.metadata = {
            'source_type': self._determine_source_type(),
            'content_type': self._determine_content_type(),
            'word_count': len(self.title.split()) + len(self.summary.split()),
            'entities': {},
            'sentiment': 0,
            'processed': False,
            'collected_at': datetime.now().isoformat(),
        }
        
        self._verify_timestamp()
    
    def _verify_timestamp(self):
        """Verify if the timestamp is likely accurate based on source and format"""
        reliable_sources = ['The Hindu', 'Indian Express', 'Mint', 'BBC', 'Reuters', 'PTI', 'LiveMint', 'Economic Times']
        
        if any(reliable in self.source for reliable in reliable_sources):
            if self.published_date and isinstance(self.published_date, datetime):
                now = datetime.now()
                if self.published_date <= now and self.published_date >= now - timedelta(days=31):
                    self.timestamp_verified = True
                    self.timestamp_source = "feed"
        
        if self.timestamp_verified and self.published_date:
            today = datetime.now().date()
            yesterday = today - timedelta(days=1)
            pub_date = self.published_date.date()
            
            if pub_date == today:
                self.metadata['timestamp_display'] = f"Today {self.published_date.strftime('%I:%M %p').lstrip('0')}"
            elif pub_date == yesterday:
                self.metadata['timestamp_display'] = f"Yesterday {self.published_date.strftime('%I:%M %p').lstrip('0')}"
            else:
                self.metadata['timestamp_display'] = self.published_date.strftime("%d %b %I:%M %p").lstrip('0')
    
    def _generate_hash(self):
        """Generate unique hash for article to prevent duplicates"""
        content = f"{self.title}{self.url}".lower()
        return hashlib.md5(content.encode()).hexdigest()
    
    def _parse_date(self, date_string):
        """Parse various date formats from feeds with better error handling"""
        if not date_string:
            return None
        
        self.raw_date = date_string
        
        if isinstance(date_string, datetime):
            if date_string.tzinfo is not None:
                return date_string.replace(tzinfo=None)
            return date_string
            
        try:
            # Standard datetime formats first
            for fmt in [
                '%a, %d %b %Y %H:%M:%S %z',
                '%a, %d %b %Y %H:%M:%S %Z',
                '%Y-%m-%dT%H:%M:%S%z',
                '%Y-%m-%dT%H:%M:%S.%f%z',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%d',
                '%d %B %Y',
                '%d %b %Y',
                '%B %d, %Y',
                '%b %d, %Y'
            ]:
                try:
                    dt = datetime.strptime(date_string, fmt)
                    return dt.replace(tzinfo=None) if hasattr(dt, 'tzinfo') and dt.tzinfo else dt
                except ValueError:
                    continue
            
            # Use dateutil if available
            if DATEUTIL_AVAILABLE:
                try:
                    dt = dateutil_parser.parse(date_string)
                    return dt.replace(tzinfo=None) if hasattr(dt, 'tzinfo') and dt.tzinfo else dt
                except (ValueError, TypeError):
                    pass
            
            logger.debug(f"Unable to parse date: {date_string}")
            return datetime.now()  # Return current time instead of None
            
        except Exception as e:
            logger.debug(f"Error parsing date '{date_string}': {str(e)}")
            return datetime.now()  # Return current time instead of None

    def parse_flexible_date(self, date_text):
        """Parse flexible date strings with better error handling"""
        if not date_text:
            return None
                
        try:
            if DATEUTIL_AVAILABLE:
                return dateutil_parser.parse(date_text, fuzzy=True)
        except (ValueError, TypeError):
            pass
        
        try:
            # Clean the date text
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
                except ValueError:
                    continue
                    
            return None
        except Exception:
            return None

    
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
        else:
            return 'news'
    
    def calculate_relevance_scores(self):
        """Calculate various relevance scores for the article"""
        policy_relevance = 0.0
        source_reliability = 0.0
        recency = 0.0
        sector_specificity = 0.0
        crisis_score = 0.0
        overall = 0.0
        
        try:
            text = f"{self.title} {self.summary} {self.content}".lower()
            
            # 1. Policy relevance score
            high_relevance_matches = sum(1 for keyword in Config.POLICY_KEYWORDS['high_relevance'] if keyword.lower() in text)
            if high_relevance_matches > 0:
                policy_relevance += min(0.7, high_relevance_matches * 0.1)
            
            medium_relevance_matches = sum(1 for keyword in Config.POLICY_KEYWORDS['medium_relevance'] if keyword.lower() in text)
            if medium_relevance_matches > 0:
                policy_relevance += min(0.3, medium_relevance_matches * 0.05)
            
            policy_relevance = min(1.0, policy_relevance)
            
            # 2. Source reliability score
            for source_name, reliability in Config.SOURCE_RELIABILITY.items():
                if source_name.lower() in self.source.lower():
                    source_reliability = reliability / 5.0
                    break
            
            if source_reliability == 0:
                source_reliability = 0.5
            
            # 3. Recency score
            current_time = datetime.now()
            if self.published_date:
                if isinstance(self.published_date, datetime):
                    pub_date = self.published_date.replace(tzinfo=None) if hasattr(self.published_date, 'tzinfo') and self.published_date.tzinfo else self.published_date
                else:
                    pub_date = current_time
                
                hours_diff = (current_time - pub_date).total_seconds() / 3600
                
                if hours_diff <= 24:
                    recency = 1.0
                elif hours_diff <= 72:
                    recency = 0.8
                elif hours_diff <= 168:
                    recency = 0.6
                elif hours_diff <= 336:
                    recency = 0.4
                elif hours_diff <= 720:
                    recency = 0.2
                else:
                    recency = 0.1
            else:
                recency = 0.5
            
            # 4. Sector specificity score
            sector_scores = {}
            for sector, keywords in Config.POLICY_SECTORS.items():
                matches = sum(1 for keyword in keywords if keyword.lower() in text)
                density = matches / len(keywords)
                sector_scores[sector] = min(1.0, density * 2)
            
            if sector_scores:
                sector_specificity = max(sector_scores.values())
                best_sector = max(sector_scores.items(), key=lambda x: x[1])
                if best_sector[1] > 0.3 and best_sector[0] != self.category:
                    self.category = best_sector[0]
            else:
                sector_specificity = 0.3
            
            # 5. Crisis relevance score
            crisis_keywords = [
                'war', 'conflict', 'hostilities', 'military', 'troops', 'border', 'ceasefire',
                'pakistan', 'indo-pak', 'india-pakistan', 'loc', 'line of control',
                'air strike', 'artillery', 'missile', 'security threat', 'defense alert',
                'diplomatic crisis', 'evacuation', 'military action', 'casualties',
                'combat', 'airspace violation', 'territorial', 'sovereignty',
                'national security', 'emergency', 'terror', 'attack'
            ]
            
            crisis_matches = sum(1 for keyword in crisis_keywords if keyword.lower() in text)
            if crisis_matches > 0:
                title_crisis = any(keyword in self.title.lower() for keyword in 
                               ['war', 'attack', 'emergency', 'missile', 'strike', 'casualties', 'pakistan'])
                
                crisis_score = min(1.0, (crisis_matches * 0.15) + (0.5 if title_crisis else 0))
            
            # 6. Calculate overall score
            overall = (
                policy_relevance * 0.25 +
                source_reliability * 0.20 +
                recency * 0.25 +
                sector_specificity * 0.10 +
                crisis_score * 0.20
            )
            
            self.relevance_scores = {
                'policy_relevance': round(policy_relevance, 2),
                'source_reliability': round(source_reliability, 2),
                'recency': round(recency, 2),
                'sector_specificity': round(sector_specificity, 2),
                'crisis_relevance': round(crisis_score, 2),
                'overall': round(overall, 2)
            }
                    
            return self.relevance_scores
            
        except Exception as e:
            logger.error(f"Error calculating relevance scores: {str(e)}", exc_info=True)
            self.relevance_scores = {
                'policy_relevance': 0.0,
                'source_reliability': 0.5,
                'recency': 0.5,
                'sector_specificity': 0.3,
                'crisis_relevance': 0.0,
                'overall': 0.3
            }
            return self.relevance_scores
    
    def extract_keywords(self, max_keywords: int = 10) -> List[str]:
        """Extract important keywords with better error handling"""
        if not self.content and not self.summary:
            self.keywords = []
            return self.keywords
        
        text = f"{self.title} {self.summary}" if not self.content else f"{self.title} {self.content}"
        
        try:
            if NLTK_AVAILABLE:
                try:
                    tokens = word_tokenize(text.lower())
                    stop_words = set(stopwords.words('english'))
                    tokens = [word for word in tokens if word.isalpha() and word not in stop_words and len(word) > 3]
                    
                    from collections import Counter
                    freq_dist = Counter(tokens)
                    self.keywords = [word for word, freq in freq_dist.most_common(max_keywords)]
                    return self.keywords
                except Exception as e:
                    logger.warning(f"NLTK keyword extraction failed: {str(e)}")
            
            words = re.findall(r'\b[a-zA-Z]{4,}\b', text.lower())
            common_words = {'this', 'that', 'with', 'from', 'have', 'what', 'they', 'will', 'been'}
            words = [w for w in words if w not in common_words]
            from collections import Counter
            self.keywords = [word for word, _ in Counter(words).most_common(max_keywords)]
            return self.keywords
        except Exception as e:
            logger.warning(f"Error extracting keywords: {str(e)}")
            self.keywords = text.lower().split()[:max_keywords]
            return self.keywords
    
    def calculate_importance(self):
        """Calculate importance based on relevance scores"""
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
        
        if isinstance(self.published_date, str):
            try:
                self.published_date = datetime.strptime(self.published_date[:19], "%Y-%m-%d %H:%M:%S")
            except ValueError:
                try:
                    self.published_date = datetime.fromisoformat(self.published_date.replace('Z', '+00:00'))
                except:
                    self.published_date = datetime.strptime(self.metadata['collected_at'], "%Y-%m-%d %H:%M:%S")
        
        pub_date = self.published_date.replace(tzinfo=None) if hasattr(self.published_date, 'tzinfo') and self.published_date.tzinfo else self.published_date
        
        hours_diff = (current_time - pub_date).total_seconds() / 3600
        
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
            'raw_date': self.raw_date,
            'summary': self.summary,
            'content': self.content,
            'tags': self.tags,
            'keywords': self.keywords,
            'content_hash': self.content_hash,
            'relevance_scores': self.relevance_scores,
            'metadata': self.metadata
        }


class PolicyRadarEnhanced:
    """Enhanced PolicyRadar class with comprehensive Indian policy sources"""
    
    def __init__(self, max_feeds=None):
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
        
        all_feeds = self._get_comprehensive_feeds()
        if max_feeds:
            self.feeds = all_feeds[:max_feeds]
        else:
            self.feeds = all_feeds
        
        self.all_articles = []
        self.source_last_update = {}
        self.source_reliability_data = self._load_source_reliability_data()

    def initialize_db(self):
        """Initialize SQLite database with enhanced schema and better error handling"""
        try:
            os.makedirs(os.path.dirname(Config.DB_FILE), exist_ok=True)
            
            with sqlite3.connect(Config.DB_FILE, timeout=30.0) as conn:
                c = conn.cursor()
                c.execute("PRAGMA journal_mode=WAL")
                c.execute("PRAGMA user_version")
                db_version = c.fetchone()[0]
                
                if db_version == 0:
                    logger.info("Creating new database schema...")
                    c.execute('''CREATE TABLE IF NOT EXISTS schema_version (version TEXT, updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                    c.execute('''CREATE TABLE IF NOT EXISTS sources (id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT, category TEXT, type TEXT, reliability FLOAT, active BOOLEAN DEFAULT 1, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                    c.execute('''CREATE TABLE IF NOT EXISTS feed_history (feed_url TEXT PRIMARY KEY, last_success TIMESTAMP, last_error TEXT, error_count INTEGER DEFAULT 0, success_count INTEGER DEFAULT 0)''')
                    c.execute('''CREATE TABLE IF NOT EXISTS articles (hash TEXT PRIMARY KEY, title TEXT NOT NULL, url TEXT NOT NULL, source TEXT, category TEXT, published_date TIMESTAMP, summary TEXT, content TEXT, tags TEXT, keywords TEXT, policy_relevance FLOAT DEFAULT 0, source_reliability FLOAT DEFAULT 0, recency FLOAT DEFAULT 0, sector_specificity FLOAT DEFAULT 0, overall_relevance FLOAT DEFAULT 0, metadata TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
                    
                    logger.info("Creating database indexes...")
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_created_at ON articles(created_at)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_overall_relevance ON articles(overall_relevance)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_published_date ON articles(published_date)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_source ON articles(source)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_articles_url ON articles(url)')
                    c.execute('CREATE INDEX IF NOT EXISTS idx_feed_history_url ON feed_history(feed_url)')
                    
                    c.execute("PRAGMA user_version = 1")
                    c.execute("INSERT INTO schema_version VALUES (?, datetime('now'))", (Config.DB_SCHEMA_VERSION,))
                    conn.commit()
                    logger.info("Database schema created successfully")
                    
                elif db_version < 1:
                    logger.info(f"Database schema is at version {db_version}, no upgrades needed")
                    
        except sqlite3.Error as e:
            logger.error(f"Database initialization error: {e}")
            logger.warning("Continuing with in-memory operation only")
        except Exception as e:
            logger.error(f"Unexpected error during database initialization: {e}")
            logger.warning("Continuing with in-memory operation only")
    
    def _create_resilient_session(self):
        """Create a requests session with proper SSL handling and retry logic"""
        session = requests.Session()
        retry_strategy = Retry(total=Config.MAX_RETRIES, backoff_factor=Config.RETRY_DELAY, status_forcelist=Config.RETRY_STATUS_CODES, allowed_methods=["GET", "HEAD"])
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        return session
    
    def get_user_agent(self):
        """Return a random user agent from the list"""
        return random.choice(Config.USER_AGENTS)

    def load_article_hashes(self, days=Config.DEDUPLICATION_DAYS):
        """Load article hashes from database for deduplication"""
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                c.execute('SELECT hash FROM articles WHERE published_date >= ?', (cutoff_date.strftime("%Y-%m-%d %H:%M:%S"),))
                self.article_hashes = set(row[0] for row in c.fetchall())
                logger.debug(f"Loaded {len(self.article_hashes)} article hashes from the last {days} days")
        except sqlite3.Error as e:
            logger.error(f"Database error loading article hashes: {e}")
            self.article_hashes = set()
    
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
        
        for source, reliability in Config.SOURCE_RELIABILITY.items():
            if source not in reliability_data:
                reliability_data[source] = reliability
        
        return reliability_data
    
    def _get_comprehensive_feeds(self):
        """Return the comprehensive list of verified URLs from the intelligence database"""
        return [
            # TIER 1: GOVERNMENT SOURCES (120 URLs)
            
            # ECONOMIC POLICY (25 URLs)
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
            ("Ministry of Corporate Affairs", "https://www.mca.gov.in/MinistryV2/rss.html", "Economic Policy"),
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
            ("India Budget Portal", "https://www.pib.gov.in/newsite/erelevent.aspx?e_i=8", "Economic Policy"),
            ("India Budget Documents", "https://www.indiabudget.gov.in/doc/bh1.pdf", "Economic Policy"),
            ("Economic Survey Portal", "https://www.pib.gov.in/newsite/erelevent.aspx?e_i=14", "Economic Policy"),
            
            # TECHNOLOGY POLICY (20 URLs)
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
            
            # FOREIGN POLICY & DEFENSE (25 URLs)
            ("Ministry of External Affairs - Press Releases", "https://www.mea.gov.in/press-releases.htm?51/Press_Releases", "Foreign Policy"),
            ("MEA Media Briefings", "https://www.mea.gov.in/media-briefings.htm?49/Media_Briefings", "Foreign Policy"),
            ("Prime Minister's Office - Messages", "https://www.pmindia.gov.in/en/message-from-the-prime-minister/", "Foreign Policy"),
            ("PMO News Updates", "https://www.pmindia.gov.in/en/news-updates/", "Foreign Policy"),
            ("Ministry of Defence - Press Releases", "https://mod.gov.in/en/press-releases-ministry-defence-0/press-release-july-2025", "Defense & Security"),
            ("Ministry of Defence - Archive", "https://mod.gov.in/index.php/en/press-releases-ministry-defence-0", "Defense & Security"),
            ("Ministry of Home Affairs - What's New", "https://xn--i1b5bzbybhfo5c8b4bxh.xn--11b7cb3a6a.xn--h2brj9c/en/media/whats-new", "Defense & Security"),
            ("MHA Press Releases 2025", "https://xn--i1b5bzbybhfo5c8b4bxh.xn--11b7cb3a6a.xn--h2brj9c/en/commoncontent/press-release-2025", "Defense & Security"),
            ("DRDO Press Releases", "https://drdo.gov.in/drdo/press-release", "Defense & Security"),
            ("NSC Secretariat", "http://www.nsab.gov.in/", "Defense & Security"),
            ("Border Security Force", "https://www.bsf.gov.in/press-release.html", "Defense & Security"),
            ("Central Reserve Police Force", "https://crpf.gov.in/Media-Centre/Press-Release", "Defense & Security"),
            ("ITBP Press Releases", "https://itbpolice.nic.in/Home/ProPressRelease", "Defense & Security"),
            ("Assam Rifles", "https://assamrifles.gov.in/english/newwindow.html?2030", "Defense & Security"),
            ("Indian Coast Guard", "https://indiancoastguard.gov.in/news", "Defense & Security"),
            ("Indian Navy", "https://indiannavy.gov.in/content/civilian", "Defense & Security"),
            ("Indian Army", "https://indianarmy.nic.in/about/adjutant-general-branch-directorates-and-branches/e-news-letter-adjutant-general-branch-directorates-and-branches", "Defense & Security"),
            ("Indian Air Force", "https://indianairforce.nic.in/latest-news", "Defense & Security"),
            ("Intelligence Bureau", "https://www.mha.gov.in/en/notifications/notice", "Defense & Security"),
            ("RAW", "https://nis.gov.in", "Defense & Security"),
            ("Central Bureau of Investigation", "https://cbi.gov.in/press-releases", "Defense & Security"),
            ("National Investigation Agency", "https://nia.gov.in/press-releases.htm", "Defense & Security"),
            ("Enforcement Directorate", "https://enforcementdirectorate.gov.in/press-release", "Defense & Security"),
            
            # GOVERNANCE & ADMINISTRATION (25 URLs)
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
            
            # ENVIRONMENTAL & HEALTHCARE (25 URLs)
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

            # TIER 2: NEWS & ANALYSIS SOURCES (147 URLs)

            # ECONOMIC POLICY
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

            # TECHNOLOGY POLICY
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

            # FOREIGN POLICY
            ("The Diplomat - Politics", "https://thediplomat.com/topics/politics/feed/", "Foreign Policy"),
            ("StratNews Global - Asia", "https://stratnewsglobal.com/asia/", "Foreign Policy"),

            # GOVERNANCE & ADMINISTRATION
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

            # ENVIRONMENTAL POLICY
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

            # CONSTITUTIONAL & LEGAL
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
            
            # SOCIAL POLICY
            ("Forbes India - Gender Parity", "https://www.forbesindia.com/blog/category/gender-parity/", "Social Policy"),
            ("Hindustan Times - Gender Equality", "https://www.hindustantimes.com/feeds/rss/ht-insight/gender-equality/rssfeed.xml", "Social Policy"),

            # EDUCATION POLICY
            ("Hindustan Times - Education News", "https://www.hindustantimes.com/feeds/rss/education/rssfeed.xml", "Education Policy"),
            ("Hindustan Times - Employment News", "https://www.hindustantimes.com/feeds/rss/education/employment-news/rssfeed.xml", "Education Policy"),
            ("Hindustan Times - Education System In India", "https://www.hindustantimes.com/feeds/rss/ht-insight/education-in-india/rssfeed.xml", "Education Policy"),
            ("Hindustan Times - Education (Web Stories)", "https://www.hindustantimes.com/feeds/rss/web-stories/education/rssfeed.xml", "Education Policy"),
            ("Hindustan Times - Education (Videos)", "https://www.hindustantimes.com/feeds/rss/videos/education/rssfeed.xml", "Education Policy"),
            ("Business Today - Education", "https://www.businesstoday.in/education", "Education Policy"),
            ("Forbes India - Education", "https://www.forbesindia.com/blog/category/education/", "Education Policy"),
            
            # POLICY ANALYSIS
            ("Caravan Magazine - Politics", "https://caravanmagazine.in/politics", "Policy Analysis"),
            ("Frontline - Politics", "https://frontline.thehindu.com/politics/", "Policy Analysis"),
            ("Week - News Magazine", "https://www.theweek.in/news/india.html", "Policy Analysis"),
            ("Open Magazine - Current Affairs", "https://openthemagazine.com/features/politics-features/", "Policy Analysis"),
            ("EPW - Economic & Political Weekly", "https://www.epw.in/open-access", "Policy Analysis"),
            ("Pragati - Policy Magazine", "https://takshashila.org.in", "Policy Analysis"),
            ("Hindustan Times - Policy Infographic", "https://www.hindustantimes.com/feeds/rss/infographic/policy/rssfeed.xml", "Policy Analysis"),
            ("Forbes India - Economy & Policy Blog", "https://www.forbesindia.com/blog/category/economy-policy/", "Policy Analysis"),
            ("Fortune India - Opinion", "https://www.fortuneindia.com/opinion", "Policy Analysis"),
            ("Outlook Business - Business Magazine", "https://www.outlookbusiness.com/news", "Policy Analysis"),
        ]
    
    def clean_html(self, html_content):
        """Clean HTML content to plain text with improved handling"""
        if not html_content:
            return ""
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            for element in soup(["script", "style", "iframe", "noscript", "head", "meta", "link"]):
                element.extract()
            
            text = soup.get_text(separator=' ', strip=True)
            text = re.sub(r'\s+', ' ', text).strip()
            
            text = re.sub(r'(Follow|Like|Share on|View on) (Twitter|Facebook|LinkedIn|Instagram|YouTube).*', '', text)
            
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
            text = re.sub(r'<[^>]+>', ' ', html_content)
            text = re.sub(r'\s+', ' ', text).strip()
            return text
    
    def fetch_single_feed(self, feed_info):
        """Process a single feed with enhanced error handling and validation"""
        if not isinstance(feed_info, tuple) or len(feed_info) < 3:
            logger.error(f"Invalid feed info format: {feed_info}")
            return []
        
        source_name, feed_url, category = feed_info
        self.statistics['total_feeds'] += 1
        
        logger.info(f"Processing {source_name} feed: {feed_url}")
        
        try:
            articles = self.fetch_feed_with_retries(feed_url, source_name, category)
            
            if articles:
                self.update_feed_status(feed_url, True)
                self.statistics['successful_feeds'] += 1
                self.feed_health[source_name] = {'status': 'success', 'count': len(articles), 'method': 'primary'}
                self.source_last_update[source_name] = datetime.now()
            else:
                self.update_feed_status(feed_url, False, "No articles found")
                self.statistics['failed_feeds'] += 1
                self.feed_health[source_name] = {'status': 'failed', 'count': 0, 'last_error': "No articles found"}
                    
            return articles
        except Exception as e:
            error_message = str(e)
            logger.error(f"Exception fetching {source_name}: {error_message}")
            
            self.update_feed_status(feed_url, False, error_message)
            self.statistics['failed_feeds'] += 1
            self.feed_health[source_name] = {'status': 'failed', 'count': 0, 'last_error': error_message}
            
            return []
    
    def fetch_feed_with_retries(self, feed_url, source_name, category, retries=0):
        """Enhanced feed fetching with improved compatibility and error handling"""
        max_retries = Config.MAX_RETRIES
        articles = []
        
        if retries >= max_retries:
            logger.warning(f"Max retries ({max_retries}) exceeded for {source_name} at {feed_url}")
            return articles
        
        try:
            domain = urlparse(feed_url).netloc
            
            headers = {
                'User-Agent': self.get_user_agent(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.9',
                'Cache-Control': 'no-cache',
                'Pragma': 'no-cache',
                'Upgrade-Insecure-Requests': '1',
                'Sec-Fetch-Dest': 'document',
                'Sec-Fetch-Mode': 'navigate',
                'Sec-Fetch-Site': 'none',
                'Sec-Fetch-User': '?1',
                'Connection': 'keep-alive'
            }

            if retries > 0:
                headers['User-Agent'] = random.choice(Config.USER_AGENTS)
                headers['Referer'] = 'https://www.google.com/search?q=news'
            
            cookies = {'gdpr': 'true', 'euconsent': 'true', 'cookieconsent_status': 'accept', 'GDPRCookieConsent': 'true', 'cookie_consent': 'accepted'}
            
            retry_delay = Config.RETRY_DELAY * (1.5 ** retries) + random.uniform(0, 1)
            
            logger.debug(f"Attempt {retries+1} fetching {source_name} from {feed_url}")
            
            try:
                response = self.session.get(feed_url, headers=headers, cookies=cookies, timeout=Config.REQUEST_TIMEOUT * 1.5, verify=False, allow_redirects=True)
                
                if response.status_code == 200:
                    feed = feedparser.parse(response.content)
                    
                    if feed.entries:
                        logger.info(f"Found {len(feed.entries)} entries in {source_name} feed")
                        
                        for entry in feed.entries[:20]:
                            try:
                                title = entry.title.strip() if hasattr(entry, 'title') else ""
                                
                                if not title:
                                    continue
                                
                                link = None
                                if hasattr(entry, 'link'):
                                    link = entry.link
                                elif hasattr(entry, 'links') and entry.links:
                                    for link_info in entry.links:
                                        if link_info.get('rel') == 'alternate':
                                            link = link_info.get('href')
                                            break
                                
                                if not link:
                                    continue
                                
                                published = None
                                if hasattr(entry, 'published'):
                                    published = entry.published
                                elif hasattr(entry, 'pubDate'):
                                    published = entry.pubDate
                                elif hasattr(entry, 'updated'):
                                    published = entry.updated
                                
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
                                
                                content = ""
                                if hasattr(entry, 'content') and entry.content:
                                    for content_item in entry.content:
                                        if 'value' in content_item:
                                            content = self.clean_html(content_item.value)
                                            break
                                
                                article = NewsArticle(title=title, url=link, source=source_name, category=category, published_date=published, summary=summary if summary else f"Policy news from {source_name}", content=content, tags=self.assign_tags(title, summary or content))
                                article.calculate_relevance_scores()
                                article.extract_keywords()

                                is_crisis_related = any(kw in (title + " " + summary).lower() for kw in ['pakistan', 'indo-pak', 'india-pakistan', 'loc', 'border', 'attack', 'ceasefire', 'missile'])
                                relevance_threshold = 0.1 if is_crisis_related else 0.2

                                if article.relevance_scores['overall'] >= relevance_threshold:
                                    if article.content_hash not in self.article_hashes:
                                        self.article_hashes.add(article.content_hash)
                                        articles.append(article)
                                        self.save_article_to_db(article)
                                else:
                                    self.statistics['low_relevance_articles'] += 1
                                    
                            except Exception as e:
                                logger.debug(f"Error processing feed entry: {str(e)}")
                                continue
                        
                        logger.info(f"Extracted {len(articles)} articles from {source_name}")
                        return articles
                    else:
                        logger.warning(f"No entries found in feed for {source_name}")
                        
                        if 'xml' in response.headers.get('content-type', '').lower():
                            return self.parse_xml_feed(response.text, source_name, category)
                        else:
                            return self.scrape_articles_fallback(response.text, source_name, category, feed_url)
                
                elif response.status_code in [403, 401]:
                    logger.warning(f"Access denied ({response.status_code}) for {source_name}, retrying with modified headers")
                    time.sleep(retry_delay)
                    return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
                    
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request error for {source_name}: {str(e)}. Retry in {retry_delay}s")
                time.sleep(retry_delay)
                return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
        
        except Exception as e:
            logger.error(f"Unexpected error for {source_name}: {str(e)}")
            time.sleep(retry_delay)
            return self.fetch_feed_with_retries(feed_url, source_name, category, retries + 1)
        
        return articles
    
    def parse_xml_feed(self, content, source_name, category):
        """Parse XML feed content with better handling for malformed feeds"""
        articles = []
        try:
            fixed_content = re.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F]', '', content)
            if '<?xml' in fixed_content:
                fixed_content = re.sub(r'<\?xml[^>]*\?>', '<?xml version="1.0" encoding="UTF-8"?>', fixed_content)
            soup = BeautifulSoup(fixed_content, 'xml')
            if soup is None:
                soup = BeautifulSoup(fixed_content, 'html.parser')
            items = soup.find_all(['item', 'entry'])
            for item in items[:20]:
                try:
                    title_elem = item.find(['title'])
                    if not title_elem or not title_elem.get_text().strip():
                        continue
                    title = title_elem.get_text().strip()
                    link = None
                    link_elem = item.find('link')
                    if link_elem:
                        if link_elem.get('href'):
                            link = link_elem.get('href')
                        elif link_elem.string:
                            link = link_elem.string.strip()
                    if not link:
                        continue
                    published_date = datetime.now()
                    for date_tag in ['pubDate', 'published', 'updated', 'date']:
                        date_elem = item.find(date_tag)
                        if date_elem:
                            date_text = date_elem.get_text().strip()
                            if date_text:
                                parsed_date = self.parse_flexible_date(date_text)
                                if parsed_date:
                                    published_date = parsed_date
                                break
                    summary = ""
                    for summary_tag in ['description', 'summary', 'content']:
                        summary_elem = item.find(summary_tag)
                        if summary_elem:
                            summary = self.clean_html(summary_elem.get_text())
                            break
                    if not summary:
                        summary = f"Policy news from {source_name}"
                    article = NewsArticle(title=title, url=link, source=source_name, category=category, published_date=published_date, summary=summary, tags=self.assign_tags(title, summary))
                    article.calculate_relevance_scores()
                    article.extract_keywords()
                    if article.relevance_scores['overall'] >= 0.15:
                        if article.content_hash not in self.article_hashes:
                            self.article_hashes.add(article.content_hash)
                            articles.append(article)
                            self.save_article_to_db(article)
                    else:
                        self.statistics['low_relevance_articles'] += 1
                except Exception as e:
                    logger.debug(f"Error extracting feed item from XML: {str(e)}")
                    continue
            logger.info(f"Extracted {len(articles)} articles from XML for {source_name}")
        except Exception as e:
            logger.error(f"Error extracting feed from XML for {source_name}: {str(e)}")
        return articles
    
    def scrape_articles_fallback(self, content: str, source_name: str, category: str, url: str) -> List[NewsArticle]:
        """Robust HTML scraping with progressive fallbacks for Indian news sites"""
        articles: List[NewsArticle] = []
        try:
            logger.info(f"Attempting HTML scraping fallback for {source_name}")
            soup = BeautifulSoup(content, 'html.parser')
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
            article_elements = []
            domain = urlparse(url).netloc.lower()
            for site_key, selector in site_specific_selectors.items():
                if site_key in domain or site_key in source_name.lower():
                    article_elements = soup.select(selector)
                    if article_elements:
                        logger.info(f"Found {len(article_elements)} potential articles using site-specific selector for {source_name}")
                        break
            if not article_elements:
                generic_selectors = ["article, .post, .story-card, .news-item, .card", "div.story, div.news, div.article, section.story", "div:has(h2) a[href], div:has(h3) a[href]", ".content a[href], .container a[href]"]
                for selector in generic_selectors:
                    article_elements = soup.select(selector)
                    if article_elements and len(article_elements) >= 2:
                        logger.info(f"Found {len(article_elements)} potential articles using selector: {selector}")
                        break
            if not article_elements:
                article_elements = []
                headings = soup.find_all(['h1', 'h2', 'h3'])
                for heading in headings[:15]:
                    if heading.find('a'):
                        if heading.parent and heading.parent.name != 'body':
                            article_elements.append(heading.parent)
                        else:
                            article_elements.append(heading)
                if article_elements:
                    logger.info(f"Found {len(article_elements)} potential articles using heading-based approach")
            for element in article_elements[:15]:
                title, link = None, None
                for heading in element.find_all(['h1', 'h2', 'h3', 'h4']):
                    if heading.get_text().strip():
                        title = heading.get_text().strip()
                        if heading.find('a', href=True):
                            link = heading.find('a', href=True)['href']
                        break
                if not title:
                    for class_name in ['.title', '.headline', '.heading']:
                        title_elem = element.select_one(class_name)
                        if title_elem and title_elem.get_text().strip():
                            title = title_elem.get_text().strip()
                            break
                if not link:
                    links = element.find_all('a', href=True)
                    for a_tag in links:
                        if a_tag.get_text().strip() and len(a_tag.get_text().strip()) > 15:
                            link = a_tag['href']
                            break
                    if not link and links:
                        link = links[0]['href']
                if link and not link.startswith(('http://', 'https://')):
                    link = urljoin(url, link)
                if title and link and len(title) > 15:
                    summary = ""
                    for p in element.find_all('p'):
                        if p.get_text().strip() and p.get_text().strip() != title:
                            summary = p.get_text().strip()
                            if len(summary) > 30:
                                break
                    if not summary or len(summary) < 20:
                        summary = f"Policy news from {source_name}"
                    published_date = None
                    date_elements = element.select('.date, time, .meta-date, .timestamp')
                    if date_elements:
                        date_text = date_elements[0].get_text().strip()
                        try:
                            published_date = self.parse_flexible_date(date_text)
                        except:
                            published_date = None
                    article = NewsArticle(title=title, url=link, source=source_name, category=category, published_date=published_date, summary=summary, tags=self.assign_tags(title, summary))
                    if article.content_hash not in self.article_hashes and self.is_policy_relevant(article):
                        self.article_hashes.add(article.content_hash)
                        articles.append(article)
                        self.save_article_to_db(article)
            logger.info(f"HTML scraping for {source_name} found {len(articles)} articles")
        except Exception as e:
            logger.error(f"Error in HTML scraping for {source_name}: {str(e)}")
        return articles
    
    def is_policy_relevant(self, article):
        """Check if an article is policy-relevant based on keywords and title/summary"""
        text = f"{article.title} {article.summary}".lower()
        policy_keywords = ['policy', 'regulation', 'law', 'ministry', 'government', 'notification', 'amendment', 'cabinet', 'parliament', 'legislation', 'regulatory', 'compliance']
        matches = sum(1 for keyword in policy_keywords if keyword in text)
        return matches > 0
    
    def parse_flexible_date(self, date_text):
        """Parse flexible date strings"""
        if not date_text:
            return None
        try:
            from dateutil import parser
            return parser.parse(date_text, fuzzy=True)
        except:
            try:
                date_text = re.sub(r'(updated|posted|published):?\s*', '', date_text, flags=re.IGNORECASE)
                date_text = re.sub(r'\s+', ' ', date_text).strip()
                for fmt in ['%d %B %Y', '%d %b %Y', '%B %d, %Y', '%b %d, %Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y']:
                    try:
                        return datetime.strptime(date_text, fmt)
                    except:
                        continue
                return None
            except:
                return None
    
    def assign_tags(self, title, summary):
        """Improved crisis tagging with better precision"""
        tags = []
        full_text = f"{title} {summary}".lower()
        conflict_keywords = ['operation sindoor', 'india-pakistan', 'indo-pak', 'pakistan conflict', 'pakistan tension', 'pakistan ceasefire', 'pakistan border', 'pakistan military', 'pakistan war']
        if any(keyword in full_text for keyword in conflict_keywords):
            tags.append('India-Pakistan Conflict')
            logger.info(f"Added India-Pakistan Conflict tag to article: {title}")
        elif 'pakistan' in full_text and any(term in full_text for term in ['border', 'military', 'attack', 'conflict', 'tension', 'war', 'ceasefire', 'diplomatic', 'security', 'threat', 'defense']):
            tags.append('India-Pakistan Conflict')
            logger.info(f"Added India-Pakistan Conflict tag to article: {title}")
        tag_rules = {
            'Policy Analysis': ['analysis', 'study', 'report', 'research', 'survey', 'findings', 'data analysis', 'impact assessment', 'evaluation', 'review', 'suggests', 'concludes', 'recommends', 'proposes', 'examines'],
            'Legislative Updates': ['bill', 'act', 'parliament', 'amendment', 'legislation', 'rajya sabha', 'lok sabha', 'ordinance', 'draft bill', 'passed', 'enacted', 'introduced', 'tabled', 'clause'],
            'Regulatory Changes': ['regulation', 'rules', 'guidelines', 'notification', 'circular', 'compliance', 'enforcement', 'regulatory', 'mandate', 'framework', 'mandatory', 'requirement', 'standards'],
            'Court Rulings': ['court', 'supreme', 'judicial', 'judgment', 'verdict', 'tribunal', 'hearing', 'petition', 'bench', 'justice', 'order', 'legal', 'lawsuit', 'litigation', 'plea', 'challenge', 'writ'],
            'Government Initiatives': ['scheme', 'program', 'initiative', 'launch', 'implementation', 'project', 'mission', 'flagship', 'campaign', 'yojana', 'announced', 'inaugurated', 'ministry', 'minister', 'government'],
            'Policy Debate': ['debate', 'discussion', 'consultation', 'feedback', 'opinion', 'perspective', 'stakeholder', 'controversy', 'criticism', 'concerns', 'opposing', 'views', 'discourse', 'deliberation'],
            'International Relations': ['bilateral', 'diplomatic', 'foreign', 'international', 'global', 'relation', 'cooperation', 'treaty', 'agreement', 'pact', 'partnership', 'strategic', 'dialogue', 'summit', 'delegation'],
            'Digital Governance': ['digital', 'online', 'internet', 'tech', 'platform', 'data', 'privacy', 'cyber', 'algorithm', 'ai', 'artificial intelligence', 'electronic', 'e-governance', 'surveillance', 'security'],
            'Economic Measures': ['budget', 'fiscal', 'monetary', 'tax', 'economy', 'financial', 'gdp', 'investment', 'subsidy', 'stimulus', 'deficit', 'reform', 'revenue', 'trade', 'commerce', 'industry'],
            'Public Consultation': ['consultation', 'public input', 'feedback', 'draft', 'comments', 'review', 'suggestions', 'stakeholder', 'participation', 'discussion paper', 'white paper', 'deliberation'],
            'Policy Implementation': ['implementation', 'rollout', 'enforcement', 'execution', 'compliance', 'timeline', 'deadline', 'phase', 'effective from', 'operational']
        }
        if 'India-Pakistan Conflict' in tags:
            tags.remove('India-Pakistan Conflict')
            tags.insert(0, 'India-Pakistan Conflict')
        for tag, keywords in tag_rules.items():
            matches = sum(1 for keyword in keywords if keyword in full_text)
            if matches >= 2 or any(f" {keyword} " in f" {full_text} " for keyword in keywords[:5]):
                tags.append(tag)
        if not tags:
            if any(word in full_text for word in ['policy', 'government', 'ministry', 'official']):
                tags.append('Policy Development')
            else:
                tags.append('Policy News')
        return tags[:3]
    
    def update_feed_status(self, feed_url, success, error=None):
        """Update feed status in database with enhanced tracking"""
        try:
            with sqlite3.connect(Config.DB_FILE) as conn:
                c = conn.cursor()
                if success:
                    c.execute('''UPDATE feed_history SET last_success = CURRENT_TIMESTAMP, error_count = 0, last_error = NULL, success_count = success_count + 1 WHERE feed_url = ?''', (feed_url,))
                    if c.rowcount == 0:
                        c.execute('''INSERT INTO feed_history (feed_url, last_success, success_count) VALUES (?, CURRENT_TIMESTAMP, 1)''', (feed_url,))
                else:
                    c.execute('''INSERT OR IGNORE INTO feed_history (feed_url) VALUES (?)''', (feed_url,))
                    c.execute('''UPDATE feed_history SET error_count = error_count + 1, last_error = ? WHERE feed_url = ?''', (str(error), feed_url))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error updating feed status: {e}")
    
    def save_article_to_db(self, article):
        """Save article to database with enhanced error handling"""
        try:
            if not hasattr(article, 'relevance_scores') or article.relevance_scores['overall'] == 0:
                article.calculate_relevance_scores()
            if not hasattr(article, 'importance'):
                article.calculate_importance()
            if not hasattr(article, 'timeliness'):
                article.calculate_timeliness()
            if not hasattr(article, 'keywords') or not article.keywords:
                article.extract_keywords()
            os.makedirs(os.path.dirname(Config.DB_FILE), exist_ok=True)
            with sqlite3.connect(Config.DB_FILE, timeout=30.0) as conn:
                c = conn.cursor()
                published_date_str = None
                if article.published_date:
                    if isinstance(article.published_date, datetime):
                        published_date_str = article.published_date.strftime('%Y-%m-%d %H:%M:%S')
                    else:
                        published_date_str = str(article.published_date)
                c.execute('''REPLACE INTO articles (hash, title, url, source, category, published_date, summary, content, tags, keywords, policy_relevance, source_reliability, recency, sector_specificity, overall_relevance, metadata) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (article.content_hash, article.title[:500], article.url[:1000], article.source[:200], article.category[:100], published_date_str, article.summary[:2000], article.content[:5000] if article.content else "", json.dumps(article.tags)[:1000], json.dumps(article.keywords)[:1000], article.relevance_scores.get('policy_relevance', 0), article.relevance_scores.get('source_reliability', 0), article.relevance_scores.get('recency', 0), article.relevance_scores.get('sector_specificity', 0), article.relevance_scores.get('overall', 0), json.dumps(article.metadata)[:2000] if hasattr(article, 'metadata') else "{}"))
                conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Database error saving article: {e}")
        except Exception as e:
            logger.error(f"Unexpected error saving article: {e}")
    
    def fetch_all_feeds(self, max_workers=6):
        """Fetch feeds concurrently with better error handling"""
        all_articles = []
        start_time = time.time()
        
        if not self.feeds:
            logger.error("Feeds list is empty or not initialized properly")
            return all_articles
        
        valid_feeds = [feed for feed in self.feeds if isinstance(feed, tuple) and len(feed) >= 3 and all(isinstance(item, str) and item.strip() for item in feed)]
        if not valid_feeds:
            logger.error("No valid feeds found after filtering")
            return all_articles
        
        logger.info(f"Starting to fetch {len(valid_feeds)} feeds with {max_workers} workers")
        max_workers = min(max_workers, len(valid_feeds), 10)
        
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                future_to_feed = {executor.submit(self.fetch_single_feed, feed): feed for feed in valid_feeds}
                completed = 0
                for future in as_completed(future_to_feed, timeout=300):
                    feed = future_to_feed[future]
                    completed += 1
                    try:
                        articles = future.result(timeout=60)
                        if articles:
                            all_articles.extend(articles)
                            self.statistics['total_articles'] += len(articles)
                        if completed % 10 == 0:
                            logger.info(f"Processed {completed}/{len(valid_feeds)} feeds")
                    except Exception as e:
                        feed_name = feed[0] if isinstance(feed, tuple) and len(feed) > 0 else 'unknown'
                        logger.error(f"Exception fetching {feed_name}: {e}")
                    time.sleep(random.uniform(0.1, 0.5))
        except Exception as e:
            logger.error(f"Error in fetch_all_feeds: {str(e)}", exc_info=True)
        
        self.statistics['end_time'] = time.time()
        self.statistics['runtime'] = round(self.statistics['end_time'] - start_time, 2)
        logger.info(f"Feed fetching completed in {self.statistics['runtime']} seconds")
        logger.info(f"Successful feeds: {self.statistics.get('successful_feeds', 0)}/{self.statistics.get('total_feeds', 0)}")
        logger.info(f"Articles collected: {len(all_articles)}")
        return all_articles

    def sort_articles_by_relevance(self, articles: List[NewsArticle]) -> List[NewsArticle]:
        """Sort articles using sophisticated relevance algorithm with crisis prioritization"""
        for article in articles:
            is_crisis = 'India-Pakistan Conflict' in article.tags
            crisis_keywords = ['pakistan', 'indo-pak', 'border', 'attack', 'ceasefire', 'missile']
            has_crisis_keywords = any(kw in (article.title + " " + article.summary).lower() for kw in crisis_keywords)
            if is_crisis or has_crisis_keywords:
                article.relevance_scores['overall'] += 0.3
                if not hasattr(article, 'combined_score'):
                    article.combined_score = article.relevance_scores['overall']
                else:
                    article.combined_score += 0.3
        return sorted(articles, key=lambda x: getattr(x, 'combined_score', x.relevance_scores['overall']), reverse=True)

    def generate_html(self, articles: List[NewsArticle]) -> str:
        """Generate HTML with proper encoding and error handling"""
        try:
            logger.info(f"Generating HTML output with {len(articles)} articles")
            articles_by_category = defaultdict(list)
            for article in articles:
                articles_by_category[article.category].append(article)
            
            sorted_categories = sorted(articles_by_category.keys())
            if "System Notice" in sorted_categories:
                sorted_categories.remove("System Notice")
                sorted_categories.insert(0, "System Notice")
            
            now = datetime.now()
            timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
            build_date = now.strftime("%B %d, %Y")
            
            all_sources = sorted(set(article.source for article in articles if article.source))
            all_tags = sorted(set(tag for article in articles for tag in article.tags))
            
            html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>PolicyRadar Enhanced - Indian Policy News Aggregator</title>
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
            --crisis-bg: #ffebee;
            --crisis-border: #f44336;
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
            --high-importance: rgba(231, 76, 60, 0.2);
            --medium-importance: rgba(241, 196, 15, 0.15);
            --low-importance: rgba(236, 240, 241, 0.1);
            --crisis-bg: #3c1f1f;
            --crisis-border: #f44336;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif; line-height: 1.6; color: var(--text-color); background-color: var(--background-color); padding-bottom: 2rem; transition: background-color 0.3s ease, color 0.3s ease; }}
        a {{ color: var(--link-color); text-decoration: none; transition: color 0.2s; }}
        a:hover {{ color: var(--link-hover); text-decoration: underline; }}
        .container {{ width: 100%; max-width: 1200px; margin: 0 auto; padding: 0 1rem; }}
        header {{ background-color: var(--primary-color); color: white; padding: 1rem 0; position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1); }}
        .header-content {{ display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }}
        .logo {{ display: flex; align-items: center; font-size: 1.5rem; font-weight: bold; }}
        .logo span {{ margin-left: 0.5rem; }}
        .nav {{ display: flex; align-items: center; }}
        .nav a {{ color: white; margin-left: 1.5rem; font-size: 0.9rem; }}
        .theme-toggle {{ background: none; border: none; color: white; cursor: pointer; font-size: 1.2rem; margin-left: 1rem; display: flex; align-items: center; justify-content: center; }}
        main {{ padding: 2rem 0; }}
        .intro {{ margin-bottom: 2rem; text-align: center; }}
        .intro h1 {{ font-size: 2rem; margin-bottom: 0.5rem; color: var(--primary-color); }}
        .intro p {{ color: var(--light-text); max-width: 700px; margin: 0 auto; }}
        .timestamp {{ font-size: 0.8rem; color: var(--light-text); margin: 1rem 0; text-align: center; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .stat-card {{ background: white; padding: 20px; border-radius: 10px; text-align: center; box-shadow: 0 2px 10px rgba(0,0,0,0.1); background-color: var(--card-color); border: 1px solid var(--border-color); }}
        .stat-number {{ font-size: 2em; font-weight: bold; color: var(--secondary-color); }}
        .stat-label {{ color: var(--light-text); font-size: 0.9em; }}
        .crisis-alert {{ background-color: var(--crisis-bg); border-left: 4px solid var(--crisis-border); padding: 15px; margin-bottom: 20px; border-radius: 5px; }}
        .crisis-alert h3 {{ color: var(--crisis-border); margin: 0 0 10px 0; }}
        .filters {{ background-color: var(--card-color); border-radius: 8px; padding: 1rem; margin-bottom: 2rem; border: 1px solid var(--border-color); }}
        .filters-toggle {{ display: flex; justify-content: space-between; align-items: center; cursor: pointer; font-weight: 600; color: var(--primary-color); }}
        .filters-content {{ margin-top: 1rem; display: none; }}
        .filters-content.active {{ display: block; }}
        .filter-group {{ margin-bottom: 1rem; }}
        .filter-group-title {{ font-weight: 600; margin-bottom: 0.5rem; font-size: 0.9rem; color: var(--primary-color); }}
        .filter-options {{ display: flex; flex-wrap: wrap; gap: 0.5rem; }}
        .filter-option {{ display: inline-block; padding: 0.25rem 0.75rem; border-radius: 16px; font-size: 0.8rem; background-color: var(--background-color); border: 1px solid var(--border-color); cursor: pointer; transition: all 0.2s; }}
        .filter-option:hover {{ background-color: var(--secondary-color); color: white; border-color: var(--secondary-color); }}
        .filter-option.active {{ background-color: var(--secondary-color); color: white; border-color: var(--secondary-color); }}
        .filter-actions {{ display: flex; justify-content: flex-end; margin-top: 1rem; }}
        .filter-button {{ padding: 0.5rem 1rem; border-radius: 4px; font-size: 0.9rem; cursor: pointer; transition: all 0.2s; }}
        .apply-filters {{ background-color: var(--secondary-color); color: white; border: none; }}
        .apply-filters:hover {{ background-color: var(--link-hover); }}
        .reset-filters {{ background-color: transparent; color: var(--link-color); border: 1px solid var(--border-color); margin-right: 0.5rem; }}
        .reset-filters:hover {{ background-color: var(--border-color); }}
        .search-container {{ margin-bottom: 2rem; display: flex; align-items: center; justify-content: center; }}
        .search-box {{ display: flex; width: 100%; max-width: 600px; position: relative; }}
        .search-input {{ flex-grow: 1; padding: 0.75rem 1rem; padding-left: 3rem; border-radius: 8px; border: 1px solid var(--border-color); font-size: 1rem; background-color: var(--card-color); color: var(--text-color); transition: all 0.2s; width: 100%; }}
        .search-input:focus {{ outline: none; border-color: var(--secondary-color); box-shadow: 0 0 0 2px rgba(52, 152, 219, 0.2); }}
        .search-icon {{ position: absolute; left: 1rem; top: 50%; transform: translateY(-50%); color: var(--light-text); font-size: 1.2rem; }}
        .categories {{ display: flex; flex-wrap: wrap; gap: 0.5rem; margin-bottom: 1.5rem; justify-content: center; }}
        .category-link {{ padding: 0.5rem 1rem; background-color: var(--card-color); border-radius: 20px; border: 1px solid var(--border-color); font-size: 0.9rem; transition: all 0.2s; }}
        .category-link:hover {{ background-color: var(--secondary-color); color: white; }}
        .section {{ margin-bottom: 3rem; }}
        .section-header {{ display: flex; align-items: center; margin-bottom: 1rem; padding-bottom: 0.5rem; border-bottom: 2px solid var(--border-color); }}
        .section-icon {{ margin-right: 0.5rem; font-size: 1.2rem; }}
        .section-title {{ font-size: 1.4rem; color: var(--primary-color); }}
        .article-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 1.5rem; }}
        .article-card {{ background-color: var(--card-color); border-radius: 8px; overflow: hidden; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.05); transition: transform 0.2s, box-shadow 0.2s; display: flex; flex-direction: column; height: 100%; border: 1px solid var(--border-color); position: relative; }}
        .article-card:hover {{ transform: translateY(-5px); box-shadow: 0 8px 16px rgba(0, 0, 0, 0.1); }}
        .article-content {{ padding: 1.2rem; flex-grow: 1; display: flex; flex-direction: column; }}
        .article-source {{ font-size: 0.8rem; color: var(--light-text); margin-bottom: 0.5rem; display: flex; justify-content: space-between; }}
        .article-title {{ font-size: 1.1rem; margin-bottom: 0.7rem; font-weight: 600; line-height: 1.3; }}
        .article-summary {{ font-size: 0.9rem; margin-bottom: 1rem; color: var(--light-text); flex-grow: 1; }}
        .article-tags {{ display: flex; flex-wrap: wrap; margin-top: auto; gap: 0.5rem; margin-bottom: 15px; }}
        .tag {{ font-size: 0.7rem; padding: 0.25rem 0.5rem; background-color: var(--secondary-color); color: white; border-radius: 12px; white-space: nowrap; opacity: 0.8; }}
        .importance-indicator {{ position: absolute; top: 0; left: 0; width: 4px; height: 100%; }}
        .importance-high {{ background-color: #e74c3c; }}
        .importance-medium {{ background-color: #f39c12; }}
        .importance-low {{ background-color: #95a5a6; }}
        .article-date {{ font-size: 0.75rem; color: var(--light-text); }}
        .relevance-score {{ display: flex; align-items: center; gap: 10px; font-size: 0.9em; }}
        .score-bar {{ width: 100px; height: 6px; background: #eee; border-radius: 3px; overflow: hidden; }}
        .score-fill {{ height: 100%; background: linear-gradient(90deg, #ff6b6b, #ffd93d, #6bcf7f); transition: width 0.3s; }}
        .notice-card {{ background-color: var(--notice-bg); border: 1px solid var(--notice-border); border-radius: 8px; padding: 1rem; margin-bottom: 2rem; }}
        .notice-card .article-title {{ color: var(--accent-color); }}
        .empty-category {{ text-align: center; padding: 2rem; background-color: var(--card-color); border-radius: 8px; border: 1px solid var(--border-color); }}
        .empty-category p {{ color: var(--light-text); margin-bottom: 1rem; }}
        .system-notice {{ background-color: var(--notice-bg); border: 1px solid var(--notice-border); border-radius: 8px; padding: 1rem; margin-bottom: 2rem; text-align: center; }}
        .system-notice p {{ font-size: 1rem; color: var(--text-color); }}
        footer {{ background-color: var(--primary-color); color: white; padding: 2rem 0; text-align: center; margin-top: 2rem; }}
        .footer-content {{ max-width: 600px; margin: 0 auto; }}
        .footer-links {{ margin: 1rem 0; }}
        .footer-links a {{ color: white; margin: 0 0.5rem; font-size: 0.9rem; }}
        .copyright {{ font-size: 0.8rem; opacity: 0.8; }}
        @media (max-width: 768px) {{
            .header-content {{ flex-direction: column; text-align: center; }}
            .nav {{ margin-top: 1rem; justify-content: center; }}
            .nav a {{ margin: 0 0.75rem; }}
            .article-grid {{ grid-template-columns: 1fr; }}
            .intro h1 {{ font-size: 1.5rem; }}
            .stats {{ grid-template-columns: repeat(2, 1fr); }}
        }}
        @media (max-width: 600px) {{
            .container {{ padding: 0 0.5rem; }}
            .section-title {{ font-size: 1.2rem; }}
            .article-card {{ border-radius: 6px; }}
            .article-content {{ padding: 1rem; }}
            .article-title {{ font-size: 1rem; }}
            .article-summary {{ font-size: 0.85rem; }}
            .stats {{ grid-template-columns: 1fr; }}
        }}
    </style>
</head>
<body data-theme="light">
    <header>
        <div class="container">
            <div class="header-content">
                <div class="logo">🔍 <span>PolicyRadar Enhanced</span></div>
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
            <h1>PolicyRadar Enhanced</h1>
            <p>Comprehensive Indian Policy News Intelligence • {len(articles)} Articles • {len(articles_by_category)} Categories</p>
            <p>Real-time monitoring across Economic, Technology, Foreign, Defense, Healthcare, Environmental, Legal, and Social Policy domains</p>
        </div>
        <div class="timestamp">
            <p>Last updated: {timestamp} IST | Build {build_date}</p>
        </div>
        <div class="stats">
            <div class="stat-card"><div class="stat-number">{len(articles)}</div><div class="stat-label">Total Articles</div></div>
            <div class="stat-card"><div class="stat-number">{len(articles_by_category)}</div><div class="stat-label">Categories</div></div>
            <div class="stat-card"><div class="stat-number">{self.statistics['successful_feeds']}</div><div class="stat-label">Active Sources</div></div>
            <div class="stat-card"><div class="stat-number">{self.statistics.get('runtime', 0):.0f}s</div><div class="stat-label">Processing Time</div></div>
        </div>
"""
            crisis_articles = [a for a in articles if 'India-Pakistan Conflict' in a.tags]
            if crisis_articles:
                html += f"""
        <div class="crisis-alert">
            <h3>🚨 Crisis Monitoring Alert</h3>
            <p>Detected {len(crisis_articles)} articles related to India-Pakistan conflict or border tensions. These articles have been prioritized for immediate attention.</p>
        </div>
"""
            html += self.generate_system_notice_html()
            html += """
        <div class="search-container">
            <div class="search-box">
                <span class="search-icon">🔍</span>
                <input type="text" class="search-input" id="search-input" placeholder="Search for policy news...">
            </div>
        </div>
        <div class="filters">
            <div class="filters-toggle" id="filters-toggle">
                <span>Filter articles by source, importance, and more</span>
                <span id="toggle-icon">▼</span>
            </div>
            <div class="filters-content" id="filters-content">
                <div class="filter-group">
                    <div class="filter-group-title">Categories</div>
                    <div class="filter-options" id="category-filters">
"""
            for category in sorted_categories:
                icon = self.get_category_icon(category)
                html += f'                        <span class="filter-option" data-filter="category" data-value="{category}">{icon} {category}</span>\n'
            html += """                    </div>
                </div>
                <div class="filter-group">
                    <div class="filter-group-title">Sources</div>
                    <div class="filter-options" id="source-filters">
"""
            for source in all_sources[:15]:
                html += f'                        <span class="filter-option" data-filter="source" data-value="{source}">{source}</span>\n'
            html += """                    </div>
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
            for tag in all_tags[:10]:
                html += f'                        <span class="filter-option" data-filter="tag" data-value="{tag}">{tag}</span>\n'
            html += """                    </div>
                </div>
                <div class="filter-actions">
                    <button class="filter-button reset-filters" id="reset-filters">Reset Filters</button>
                    <button class="filter-button apply-filters" id="apply-filters">Apply Filters</button>
                </div>
            </div>
        </div>
        <div class="categories">
"""
            for category in sorted_categories:
                icon = self.get_category_icon(category)
                html += f'            <a href="#{category.replace(" ", "-").lower()}" class="category-link">{icon} {category}</a>\n'
            html += """        </div>
"""
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
                if not category_articles:
                    html += """            <div class="empty-category">
                <p>No recent articles found in this category. Check back soon for updates.</p>
            </div>
"""
                else:
                    html += """            <div class="article-grid">
"""
                    for article in category_articles[:50]:
                        card_class = "notice-card" if category == "System Notice" else "article-card"
                        importance_class = "importance-low"
                        relevance_score = article.relevance_scores.get('overall', 0)
                        score_percentage = int(relevance_score * 100)
                        if relevance_score >= 0.7:
                            importance_class = "importance-high"
                        elif relevance_score >= 0.4:
                            importance_class = "importance-medium"
                        display_date = "Unknown"
                        if article.published_date:
                            if hasattr(article, 'metadata') and 'timestamp_display' in article.metadata:
                                display_date = article.metadata['timestamp_display']
                            else:
                                try:
                                    if isinstance(article.published_date, datetime):
                                        display_date = article.published_date.strftime('%b %d, %Y')
                                    elif isinstance(article.published_date, str):
                                        date_obj = datetime.fromisoformat(article.published_date.replace('Z', '+00:00'))
                                        display_date = date_obj.strftime('%b %d, %Y')
                                except:
                                    display_date = "Recent"
                        importance_level = "high" if relevance_score >= 0.7 else "medium" if relevance_score >= 0.4 else "low"
                        data_attrs = f'data-source="{article.source}" data-category="{article.category}" data-importance="{importance_level}"'
                        if hasattr(article, 'tags') and article.tags:
                            data_attrs += f' data-tags="{" ".join(article.tags)}"'
                        tags_html = ''.join(f'<span class="tag">{tag}</span>' for tag in article.tags[:3])
                        html += f"""                <div class="{card_class}" {data_attrs}>
                    <div class="importance-indicator {importance_class}"></div>
                    <div class="article-content">
                        <div class="article-source">
                            <span>{article.source}</span>
                            <span class="article-date">{display_date}</span>
                        </div>
                        <h3 class="article-title">
                            <a href="{article.url}" target="_blank" rel="noopener noreferrer">{article.title}</a>
                        </h3>
                        <div class="article-summary">{article.summary[:200]}{'...' if len(article.summary) > 200 else ''}</div>
                        <div class="article-tags">{tags_html}</div>
                        <div class="relevance-score">
                            <span>Relevance:</span>
                            <div class="score-bar"><div class="score-fill" style="width: {score_percentage}%"></div></div>
                            <span>{score_percentage}%</span>
                        </div>
                    </div>
                </div>
"""
                    html += """            </div>
"""
                html += """        </section>
"""
            html += f"""    </main>
    <footer>
        <div class="container">
            <div class="footer-content">
                <p><strong>PolicyRadar Enhanced</strong> - Powered by {len(self.feeds)} verified sources</p>
                <div class="footer-links">
                    <a href="#" id="about">About</a>
                    <a href="#" onclick="showHealth()">System Health</a>
                    <a href="api_data.json" target="_blank">API Data</a>
                </div>
                <div class="copyright">
                    &copy; 2025 PolicyRadar Enhanced | Real-time intelligence across Economic, Technology, Defense, Environmental, Legal, and Social Policy domains<br>
                    Generated on {datetime.now().strftime('%B %d, %Y at %I:%M %p IST')}
                </div>
            </div>
        </div>
    </footer>
    <script>
        const themeToggle = document.getElementById('theme-toggle');
        const body = document.body;
        const savedTheme = localStorage.getItem('theme');
        const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
        if (savedTheme === 'dark' || (!savedTheme && prefersDark)) {{
            body.setAttribute('data-theme', 'dark');
            themeToggle.textContent = '🌙';
        }}
        themeToggle.addEventListener('click', () => {{
            const currentTheme = body.getAttribute('data-theme');
            const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
            body.setAttribute('data-theme', newTheme);
            themeToggle.textContent = newTheme === 'dark' ? '🌙' : '🔆';
            localStorage.setItem('theme', newTheme);
        }});
        function showHealth() {{ window.open('health.html', '_blank'); }}
        document.getElementById('about').addEventListener('click', (e) => {{
            e.preventDefault();
            alert('PolicyRadar Enhanced aggregates policy news from 100+ verified Indian sources. Updated regularly, it offers comprehensive coverage of policy developments across all major sectors including technology, economy, healthcare, environment, education, defense, and more.');
        }});
        const filtersToggle = document.getElementById('filters-toggle');
        const filtersContent = document.getElementById('filters-content');
        const toggleIcon = document.getElementById('toggle-icon');
        filtersToggle.addEventListener('click', () => {{
            filtersContent.classList.toggle('active');
            toggleIcon.textContent = filtersContent.classList.contains('active') ? '▲' : '▼';
        }});
        const filterOptions = document.querySelectorAll('.filter-option');
        const resetFiltersBtn = document.getElementById('reset-filters');
        const applyFiltersBtn = document.getElementById('apply-filters');
        const articleCards = document.querySelectorAll('.article-card');
        const sections = document.querySelectorAll('.section');
        const searchInput = document.getElementById('search-input');
        searchInput.addEventListener('input', () => {{
            const searchTerm = searchInput.value.toLowerCase();
            articleCards.forEach(card => {{
                const title = card.querySelector('.article-title').textContent.toLowerCase();
                const summary = card.querySelector('.article-summary').textContent.toLowerCase();
                const source = card.dataset.source.toLowerCase();
                if (searchTerm === '') {{
                    card.style.display = 'flex';
                }} else if (title.includes(searchTerm) || summary.includes(searchTerm) || source.includes(searchTerm)) {{
                    card.style.display = 'flex';
                }} else {{
                    card.style.display = 'none';
                }}
            }});
            sections.forEach(section => {{
                const visibleCards = section.querySelectorAll('.article-card[style="display: flex;"]');
                if (visibleCards.length === 0 && searchTerm !== '') {{
                    section.style.display = 'none';
                }} else {{
                    section.style.display = 'block';
                }}
            }});
        }});
        filterOptions.forEach(option => {{
            option.addEventListener('click', () => {{
                option.classList.toggle('active');
            }});
        }});
        applyFiltersBtn.addEventListener('click', () => {{
            const activeFilters = {{ category: [], source: [], importance: [], tag: [] }};
            document.querySelectorAll('.filter-option.active').forEach(option => {{
                const filterType = option.dataset.filter;
                const filterValue = option.dataset.value;
                activeFilters[filterType].push(filterValue);
            }});
            articleCards.forEach(card => {{
                let isVisible = true;
                if (activeFilters.category.length > 0) {{
                    if (!activeFilters.category.includes(card.dataset.category)) {{ isVisible = false; }}
                }}
                if (isVisible && activeFilters.source.length > 0) {{
                    if (!activeFilters.source.includes(card.dataset.source)) {{ isVisible = false; }}
                }}
                if (isVisible && activeFilters.importance.length > 0) {{
                    if (!activeFilters.importance.includes(card.dataset.importance)) {{ isVisible = false; }}
                }}
                if (isVisible && activeFilters.tag.length > 0) {{
                    const cardTags = (card.dataset.tags || '').split(' ');
                    let hasTag = false;
                    for (const tag of activeFilters.tag) {{
                        if (cardTags.includes(tag)) {{
                            hasTag = true;
                            break;
                        }}
                    }}
                    if (!hasTag) {{ isVisible = false; }}
                }}
                card.style.display = isVisible ? 'flex' : 'none';
            }});
            sections.forEach(section => {{
                const visibleCards = section.querySelectorAll('.article-card[style="display: flex;"]');
                section.style.display = visibleCards.length > 0 ? 'block' : 'none';
            }});
        }});
        resetFiltersBtn.addEventListener('click', () => {{
            filterOptions.forEach(option => {{ option.classList.remove('active'); }});
            articleCards.forEach(card => {{ card.style.display = 'flex'; }});
            sections.forEach(section => {{ section.style.display = 'block'; }});
            searchInput.value = '';
        }});
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {{
            anchor.addEventListener('click', function(e) {{
                if (this.getAttribute('href') === '#' || this.getAttribute('onclick')) return;
                e.preventDefault();
                const targetId = this.getAttribute('href');
                const targetElement = document.querySelector(targetId);
                if (targetElement) {{
                    window.scrollTo({{ top: targetElement.offsetTop - 100, behavior: 'smooth' }});
                }}
            }});
        }});
    </script>
</body>
</html>"""
            output_file = os.path.join(Config.OUTPUT_DIR, 'index.html')
            os.makedirs(Config.OUTPUT_DIR, exist_ok=True)
            with open(output_file, 'w', encoding='utf-8', errors='replace') as f:
                f.write(html)
            logger.info(f"HTML output generated: {output_file}")
            return output_file
        except UnicodeEncodeError as e:
            logger.error(f"Unicode encoding error generating HTML: {str(e)}")
            try:
                with open(output_file, 'w', encoding='utf-8', errors='ignore') as f:
                    f.write(html)
                return output_file
            except Exception as fallback_error:
                logger.error(f"Fallback HTML generation failed: {fallback_error}")
                return None
        except Exception as e:
            logger.error(f"Error generating HTML: {str(e)}")
            return None

    def get_category_icon(self, category: str) -> str:
        """Return emoji icon for category"""
        icons = {
            "Technology Policy": "💻", "Economic Policy": "📊", "Healthcare Policy": "🏥",
            "Environmental Policy": "🌱", "Education Policy": "🎓", "Agricultural Policy": "🌾",
            "Foreign Policy": "🌐", "Constitutional & Legal": "⚖️", "Defense & Security": "🛡️",
            "Social Policy": "👥", "Governance & Administration": "🏛️", "Policy News": "📑",
            "Policy Analysis": "📋", "System Notice": "⚠️"
        }
        return icons.get(category, "📄")

    def generate_system_notice_html(self) -> str:
        """Generate system notice HTML based on current system status"""
        total_feeds = self.statistics.get('total_feeds', 0)
        if total_feeds == 0:
            return ""
        success_rate = (self.statistics.get('successful_feeds', 0) / total_feeds) * 100
        if success_rate >= 80:
            return ""
        elif success_rate >= 40:
            return """<div class="system-notice"><p>⚠️ <strong>System Notice:</strong> Some news sources are currently unavailable. We're working to restore full service.</p></div>"""
        else:
            return """<div class="system-notice"><p>⚠️ <strong>System Notice:</strong> Feed aggregation is experiencing significant issues. Most sources may be temporarily unavailable while we work to resolve the problem.</p></div>"""

    def generate_health_dashboard(self) -> Optional[str]:
        """Generate system health dashboard HTML with detailed stats"""
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        total_feeds = self.statistics.get('total_feeds', 0)
        successful_feeds = self.statistics.get('successful_feeds', 0)
        success_rate = (successful_feeds / total_feeds * 100) if total_feeds > 0 else 0
        total_articles = self.statistics.get('total_articles', 0)
        runtime = self.statistics.get('runtime', 0)
        if success_rate >= 80:
            system_status, status_color = "Healthy", "#4CAF50"
        elif success_rate >= 50:
            system_status, status_color = "Degraded", "#FF9800"
        else:
            system_status, status_color = "Critical", "#F44336"
        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>PolicyRadar Enhanced - System Health</title></head>
<body><h1>PolicyRadar Enhanced - System Health</h1><p>Last updated: {timestamp}</p><div class="status">System Status: <span style="color: {status_color};">{system_status}</span></div><div class="metrics"><div>Success Rate: {success_rate:.1f}%</div><div>Articles: {total_articles}</div><div>Runtime: {runtime:.2f}s</div></div></body>
</html>"""
        health_file = os.path.join(Config.OUTPUT_DIR, 'health.html')
        try:
            with open(health_file, 'w', encoding='utf-8') as f:
                f.write(html)
            logger.info(f"Health dashboard generated: {health_file}")
            return health_file
        except Exception as e:
            logger.error(f"Error generating health dashboard: {str(e)}")
            return None

    def export_articles_json(self, articles: List[NewsArticle]) -> str:
        """Export articles to JSON format"""
        json_file = os.path.join(Config.EXPORT_DIR, 'articles.json')
        try:
            articles_data = [article.to_dict() for article in articles]
            export_data = {'metadata': {'total_articles': len(articles), 'generated_at': datetime.now().isoformat(), 'statistics': self.statistics}, 'articles': articles_data}
            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, ensure_ascii=False, default=str)
            logger.info(f"JSON export generated: {json_file}")
            return json_file
        except Exception as e:
            logger.error(f"Error exporting JSON: {str(e)}")
            return None

    def run(self, max_workers: int = 6, args=None) -> str:
        """Main method that combines multiple strategies for best results"""
        start_time = time.time()
        try:
            logger.info("Starting PolicyRadar aggregator with verified sources")
            all_articles = self.fetch_all_feeds(max_workers=max_workers)
            crisis_related = [a for a in all_articles if 'india-pakistan' in (a.title + a.summary).lower() or 'pakistan' in (a.title + a.summary).lower()]
            logger.info(f"Found {len(crisis_related)} articles mentioning Pakistan or India-Pakistan")
            for idx, article in enumerate(crisis_related[:5]):
                logger.info(f"Crisis article {idx+1}: '{article.title}' from {article.source}")
            sorted_articles = self.sort_articles_by_relevance(all_articles)
            crisis_articles = [a for a in sorted_articles if 'India-Pakistan Conflict' in a.tags]
            logger.info(f"Found {len(crisis_articles)} crisis-related articles with tag")
            if args and hasattr(args, 'fresh') and args.fresh:
                self.article_hashes = set()
                logger.info("Fresh mode enabled - collecting all articles regardless of history")
            if crisis_articles:
                logger.info("Checking timestamp data for crisis articles:")
                for idx, article in enumerate(crisis_articles[:5]):
                    logger.info(f"Crisis article #{idx+1}: '{article.title}'\n  Raw date: {getattr(article, 'raw_date', None)}\n  Parsed date: {article.published_date}")
                    if hasattr(article, 'timestamp_verified'):
                        logger.info(f"  Verified: {article.timestamp_verified}\n  Source: {article.timestamp_source}")
                        if hasattr(article, 'metadata'):
                            logger.info(f"  Display format: {article.metadata.get('timestamp_display', 'not available')}")
                            if 'date_parse_error' in article.metadata:
                                logger.info(f"  Parse error: {article.metadata.get('date_parse_error')}")
                    else:
                        logger.info("  Timestamp verification not implemented yet")
                    logger.info("---")
            output_file = self.generate_html(sorted_articles)
            self.export_articles_json(sorted_articles)
            runtime = time.time() - start_time
            logger.info(f"PolicyRadar aggregator completed in {runtime:.2f} seconds")
            logger.info(f"Total articles: {len(all_articles)}")
            logger.info(f"High relevance articles: {len([a for a in all_articles if a.relevance_scores['overall'] > 0.7])}")
            logger.info(f"Crisis articles: {len(crisis_articles)}")
            return output_file
        except Exception as e:
            logger.error(f"Critical error running PolicyRadar: {str(e)}", exc_info=True)
            emergency_article = NewsArticle(title="PolicyRadar System Error", url="#", source="PolicyRadar System", category="System Notice", summary="Our aggregation system encountered an error. We're working to resolve this issue.", tags=["System Error"])
            return self.generate_html([emergency_article])

    def fetch_html_content(self, url: str, source_name: str, category: str) -> List[NewsArticle]:
        """Enhanced HTML content fetching with site-specific handling"""
        articles = []
        try:
            logger.info(f"Fetching HTML content from {source_name}: {url}")
            headers = {'User-Agent': self.get_user_agent(), 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'Accept-Language': 'en-US,en;q=0.9', 'Cache-Control': 'no-cache', 'Pragma': 'no-cache'}
            response = self.session.get(url, headers=headers, timeout=30, verify=False)
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                site_configs = {
                    'pib.gov.in': {'container': 'div.content-area', 'items': 'div.news-container, ul li a', 'title': 'a', 'date': 'span.date', 'link': 'a'},
                    'mea.gov.in': {'container': 'div#innerContent', 'items': 'li', 'title': 'a', 'date': 'span', 'link': 'a'},
                    'meity.gov.in': {'container': 'div.view-content', 'items': 'div.views-row', 'title': 'a', 'date': 'span.date-display-single', 'link': 'a'},
                    'trai.gov.in': {'container': 'div.view-content', 'items': 'div.views-row', 'title': 'a', 'date': 'span.date-display-single', 'link': 'a'},
                }
                default_config = {'container': 'body', 'items': 'article, .post, .story-card', 'title': 'h1, h2, h3, .title, .headline', 'date': '.date, time, .timestamp', 'link': 'a'}
                config = default_config
                for site, site_config in site_configs.items():
                    if site in url:
                        config = site_config
                        break
                item_elements = soup.select(f"{config['container']} {config['items']}")
                for item_element in item_elements[:20]:
                    try:
                        title_element = item_element.select_one(config['title'])
                        link_element = item_element.select_one(config['link'])
                        date_element = item_element.select_one(config['date'])
                        if title_element and link_element:
                            title = title_element.get_text(strip=True)
                            link = urljoin(url, link_element['href'])
                            published_date = None
                            if date_element:
                                published_date = self.parse_flexible_date(date_element.get_text(strip=True))
                            summary = ""
                            summary_element = item_element.find('p')
                            if summary_element:
                                summary = summary_element.get_text(strip=True)
                            if title and len(title) > 15:
                                article = NewsArticle(title=title, url=link, source=source_name, category=category, published_date=published_date, summary=summary, tags=self.assign_tags(title, summary))
                                if article.content_hash not in self.article_hashes:
                                    article.calculate_relevance_scores()
                                    if article.relevance_scores['overall'] >= 0.2:
                                        self.article_hashes.add(article.content_hash)
                                        articles.append(article)
                                        self.save_article_to_db(article)
                    except Exception as item_error:
                        logger.debug(f"Error parsing item from {source_name}: {item_error}")
                        continue
                logger.info(f"Successfully scraped {len(articles)} articles from {source_name}")
            else:
                logger.warning(f"Failed to fetch HTML from {url} with status code {response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error(f"Request failed for {source_name} at {url}: {e}")
        except Exception as e:
            logger.error(f"Error scraping HTML from {source_name}: {e}")
        return articles

def main():
    """Main function with comprehensive error handling"""
    parser = argparse.ArgumentParser(description='PolicyRadar - Enhanced Indian Policy News Aggregator')
    parser.add_argument('--workers', type=int, default=6, help='Number of worker threads')
    parser.add_argument('--fresh', action='store_true', help='Ignore previously seen articles')
    parser.add_argument('--max-feeds', type=int, default=None, help='Maximum feeds to process')
    parser.add_argument('--max-articles', type=int, default=200, help='Maximum articles to collect')
    parser.add_argument('--debug', action='store_true', help='Enable debug logging')
    
    args = parser.parse_args()
    
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Debug logging enabled")
    
    try:
        logger.info("Checking system requirements...")
        
        if sys.version_info < (3, 7):
            logger.error("Python 3.7 or higher is required")
            sys.exit(1)
        
        for directory in DIRS:
            try:
                Path(directory).mkdir(exist_ok=True)
            except PermissionError:
                logger.error(f"Permission denied creating directory: {directory}")
                sys.exit(1)
        
        logger.info("Initializing PolicyRadar with verified sources...")
        policy_radar = PolicyRadarEnhanced(max_feeds=args.max_feeds)
        
        logger.info("Starting news aggregation...")
        output_file = policy_radar.run(max_workers=args.workers, args=args)
        
        if not output_file:
            logger.error("Failed to generate output file")
            sys.exit(1)
        
        print("\n=== PolicyRadar Enhanced Summary ===")
        print(f"Total sources attempted: {len(policy_radar.feeds)}")
        print(f"Total articles collected: {policy_radar.statistics.get('total_articles', 0)}")
        print(f"Successful feeds: {policy_radar.statistics.get('successful_feeds', 0)}")
        print(f"Failed feeds: {policy_radar.statistics.get('failed_feeds', 0)}")
        print(f"Output generated: {output_file}")
        
        total_feeds = policy_radar.statistics.get('total_feeds', 0)
        successful_feeds = policy_radar.statistics.get('successful_feeds', 0)
        if total_feeds > 0 and (successful_feeds / total_feeds) < 0.5:
            print("\n⚠️ WARNING: Less than 50% of feeds were successful. Check logs for details.")
        
        print(f"\n✅ Successfully processed verified government sources!")
        
    except KeyboardInterrupt:
        logger.info("Operation cancelled by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Critical error in main: {str(e)}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
