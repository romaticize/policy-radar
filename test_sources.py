#!/usr/bin/env python3
"""
PolicyRadar Source Tester - Test individual sources for debugging
"""

import sys
import argparse
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import datetime
import json
from urllib.parse import urljoin, urlparse

def test_rss_feed(url, name):
    """Test an RSS feed and report its status"""
    print(f"\n🔍 Testing RSS Feed: {name}")
    print(f"   URL: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            # Try to parse as RSS
            feed = feedparser.parse(response.content)
            
            if feed.entries:
                print(f"   ✅ SUCCESS: Found {len(feed.entries)} entries")
                print(f"   Feed Title: {feed.feed.get('title', 'N/A')}")
                
                # Show first 3 entries
                print("\n   Sample Entries:")
                for i, entry in enumerate(feed.entries[:3], 1):
                    title = entry.get('title', 'No title')
                    link = entry.get('link', 'No link')
                    date = entry.get('published', entry.get('pubDate', 'No date'))
                    print(f"   {i}. {title[:60]}...")
                    print(f"      Link: {link}")
                    print(f"      Date: {date}")
                
                return True
            else:
                print("   ❌ FAIL: No entries found in feed")
                # Check if it's HTML instead
                if '<html' in response.text[:1000].lower():
                    print("   ℹ️  This appears to be an HTML page, not an RSS feed")
                return False
        else:
            print(f"   ❌ FAIL: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {type(e).__name__}: {str(e)}")
        return False

def test_html_source(url, name, selector_config=None):
    """Test an HTML source and try to extract articles"""
    print(f"\n🔍 Testing HTML Source: {name}")
    print(f"   URL: {url}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        
        response = requests.get(url, headers=headers, timeout=10, verify=False)
        print(f"   Status Code: {response.status_code}")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Try different common patterns
            patterns = [
                # Common government site patterns
                {'container': 'div.view-content', 'items': 'div.views-row', 'title': 'a'},
                {'container': 'div#content', 'items': 'ul li', 'title': 'a'},
                {'container': 'div.content-area', 'items': 'div.news-container', 'title': 'a'},
                {'container': 'div#innerContent', 'items': 'li', 'title': 'a'},
                # Generic patterns
                {'container': 'main', 'items': 'article', 'title': 'h2 a, h3 a'},
                {'container': 'body', 'items': 'a[href*="press"], a[href*="news"], a[href*="release"]', 'title': None},
            ]
            
            # Use provided selector config if available
            if selector_config:
                patterns.insert(0, selector_config)
            
            articles_found = False
            
            for pattern in patterns:
                if pattern.get('container'):
                    container = soup.select_one(pattern['container'])
                    if not container:
                        continue
                    items = container.select(pattern['items'])
                else:
                    items = soup.select(pattern['items'])
                
                if items:
                    print(f"   ✅ Found {len(items)} potential articles using pattern: {pattern}")
                    print("\n   Sample Articles:")
                    
                    count = 0
                    for item in items[:5]:
                        if pattern.get('title'):
                            title_elem = item.select_one(pattern['title']) if pattern['title'] else item
                        else:
                            title_elem = item
                            
                        if title_elem:
                            title = title_elem.get_text(strip=True)
                            link = title_elem.get('href', '')
                            
                            if not link and title_elem.name == 'a':
                                link = title_elem.get('href', '')
                            
                            if title and len(title) > 10:
                                count += 1
                                if not link.startswith(('http://', 'https://')):
                                    link = urljoin(url, link)
                                print(f"   {count}. {title[:60]}...")
                                print(f"      Link: {link}")
                    
                    if count > 0:
                        articles_found = True
                        break
            
            if not articles_found:
                print("   ⚠️  No articles found with common patterns")
                # Try to find any links that might be articles
                all_links = soup.find_all('a', href=True)
                relevant_links = []
                
                keywords = ['press', 'release', 'news', 'notification', 'circular', 'update', 'announcement']
                for link in all_links:
                    href = link.get('href', '').lower()
                    text = link.get_text(strip=True).lower()
                    if any(kw in href or kw in text for kw in keywords):
                        relevant_links.append(link)
                
                if relevant_links:
                    print(f"   ℹ️  Found {len(relevant_links)} links with relevant keywords")
                    for i, link in enumerate(relevant_links[:3], 1):
                        print(f"   {i}. {link.get_text(strip=True)[:60]}...")
                        print(f"      Link: {urljoin(url, link.get('href'))}")
                else:
                    print("   ℹ️  No relevant links found on the page")
            
            return articles_found
        else:
            print(f"   ❌ FAIL: HTTP {response.status_code}")
            return False
            
    except Exception as e:
        print(f"   ❌ ERROR: {type(e).__name__}: {str(e)}")
        return False

def test_source(url, name=None, source_type=None):
    """Test a single source (auto-detect type if not specified)"""
    if not name:
        name = urlparse(url).netloc
    
    if not source_type:
        # Auto-detect based on URL patterns
        if any(ext in url.lower() for ext in ['.xml', '.rss', '/rss', '/feed']):
            source_type = 'rss'
        else:
            source_type = 'html'
    
    if source_type == 'rss':
        return test_rss_feed(url, name)
    else:
        return test_html_source(url, name)

def test_all_sources_from_json(json_file):
    """Test all sources from the JSON configuration file"""
    try:
        with open(json_file, 'r') as f:
            config = json.load(f)
        
        results = {
            'working': [],
            'failed': [],
            'total': 0
        }
        
        print("="*80)
        print("TESTING ALL VERIFIED SOURCES")
        print("="*80)
        
        # Test government sources
        for category, sources in config.get('verified_sources', {}).items():
            print(f"\n\n{'='*40}")
            print(f"CATEGORY: {category.upper()}")
            print(f"{'='*40}")
            
            # Test RSS feeds
            for feed in sources.get('rss_feeds', []):
                results['total'] += 1
                if test_rss_feed(feed['url'], feed['name']):
                    results['working'].append(feed['name'])
                else:
                    results['failed'].append(feed['name'])
            
            # Test HTML sources
            for source in sources.get('html_sources', []):
                results['total'] += 1
                selector_config = source.get('selector_config')
                if test_html_source(source['url'], source['name'], selector_config):
                    results['working'].append(source['name'])
                else:
                    results['failed'].append(source['name'])
        
        # Test news media sources
        for category, sources in config.get('news_media_sources', {}).items():
            print(f"\n\n{'='*40}")
            print(f"NEWS MEDIA: {category.upper()}")
            print(f"{'='*40}")
            
            for source in sources:
                results['total'] += 1
                if source.get('type') == 'rss':
                    if test_rss_feed(source['url'], source['name']):
                        results['working'].append(source['name'])
                    else:
                        results['failed'].append(source['name'])
        
        # Test think tanks
        print(f"\n\n{'='*40}")
        print("THINK TANKS")
        print(f"{'='*40}")
        
        for source in config.get('think_tanks', []):
            results['total'] += 1
            if test_rss_feed(source['url'], source['name']):
                results['working'].append(source['name'])
            else:
                results['failed'].append(source['name'])
        
        # Print summary
        print(f"\n\n{'='*80}")
        print("SUMMARY")
        print(f"{'='*80}")
        print(f"Total sources tested: {results['total']}")
        print(f"✅ Working: {len(results['working'])} ({len(results['working'])/results['total']*100:.1f}%)")
        print(f"❌ Failed: {len(results['failed'])} ({len(results['failed'])/results['total']*100:.1f}%)")
        
        if results['failed']:
            print("\nFailed sources:")
            for name in results['failed']:
                print(f"  - {name}")
        
    except Exception as e:
        print(f"Error reading JSON file: {e}")

def main():
    parser = argparse.ArgumentParser(description='Test PolicyRadar sources')
    parser.add_argument('--url', help='Test a single URL')
    parser.add_argument('--name', help='Name for the source')
    parser.add_argument('--type', choices=['rss', 'html'], help='Source type')
    parser.add_argument('--json', help='Test all sources from JSON config file')
    parser.add_argument('--category', help='Test only sources from a specific category')
    
    args = parser.parse_args()
    
    if args.json:
        test_all_sources_from_json(args.json)
    elif args.url:
        test_source(args.url, args.name, args.type)
    else:
        print("Please provide either --url or --json argument")
        parser.print_help()

if __name__ == "__main__":
    main()
