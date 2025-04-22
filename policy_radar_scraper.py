#!/usr/bin/env python3
"""
PolicyRadar - Indian Policy News Aggregator
Created by Roma Thakur

PolicyRadar cuts through information overload by carefully curating the most significant 
policy developments across key domains in India. We monitor over 30 trusted sources 
so you don't have to, bringing you a concise, organized view of what matters in Indian policy.

This script aggregates policy news from multiple sources and organizes them by category.
"""

import requests
import feedparser
import datetime
import os
import re
import time
import random
import json
import urllib3
import ssl

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Create output directory if it doesn't exist
output_dir = 'docs'
if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    print(f"Created output directory: {output_dir}")

# Class to store article information
class NewsArticle:
    def __init__(self, title, url, source, category, published_date=None, summary=None, tags=None):
        self.title = title
        self.url = url
        self.source = source
        self.category = category
        self.published_date = published_date
        self.summary = summary
        self.tags = tags or []  # Default to empty list if no tags provided

def is_policy_related_state_news(title, summary, source_name):
    """Filter out non-policy content for state/local news sources"""
    # Must-have keywords for state/local policies
    policy_keywords = [
        'policy', 'government', 'governance', 'bill', 'act', 'ordinance',
        'scheme', 'program', 'initiative', 'regulation', 'amendment',
        'municipal', 'panchayat', 'zilla', 'district', 'civic', 'local body',
        'state cabinet', 'assembly', 'legislative', 'cm', 'chief minister',
        'urban planning', 'smart city', 'rural development'
    ]
    # Keywords to exclude (not policy-related)
    exclude_keywords = [
        'cricket', 'bollywood', 'sports', 'entertainment', 'movie',
        'actor', 'actress', 'film', 'celebrity', 'crime', 'accident',
        'robbery', 'murder', 'rape', 'weather', 'festival'
    ]
    
    title_lower = title.lower()
    summary_lower = summary.lower() if summary else ""
    full_text = title_lower + " " + summary_lower
    
    # Check for exclusion keywords
    if any(exclude in full_text for exclude in exclude_keywords):
        return False
    
    # Check for policy keywords
    if any(keyword in full_text for keyword in policy_keywords):
        return True
    
    # Special rules for specific sources
    if source_name in ['EastMojo', 'The News Minute']:
        # For these sources, require at least two policy keywords
        matches = sum(1 for keyword in policy_keywords if keyword in full_text)
        return matches >= 2
    
    return False

def fetch_feed(feed_url, source_name, category):
    """Fetch and parse an RSS feed, returning a list of articles"""
    print(f"Fetching: {source_name} ({category})")
    articles = []
    
    try:
        # Set up headers to mimic a browser
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Connection': 'keep-alive',
        }
        
        # Use requests to get the RSS content - disable SSL verification for problematic sites
        response = requests.get(feed_url, headers=headers, timeout=15, verify=False)
        if response.status_code != 200:
            print(f"Failed to fetch {source_name}: HTTP {response.status_code}")
            return articles  # Return empty list
        
        # Parse the feed
        feed = feedparser.parse(response.text)
        
        # Process entries
        for entry in feed.entries[:10]:  # Limit to 10 entries per source
            title = entry.get('title', '').strip()
            url = entry.get('link', '').strip()
            
            # Skip if no title or URL
            if not title or not url:
                continue
            
            # Extract publication date
            published_date = None
            if 'published' in entry:
                published_date = entry.published
            elif 'pubDate' in entry:
                published_date = entry.pubDate
            elif 'updated' in entry:
                published_date = entry.updated
            
            # Extract summary
            summary = None
            if 'summary' in entry:
                summary = re.sub(r'<.*?>', '', entry.summary)  # Remove HTML tags
                summary = summary[:200] + '...' if len(summary) > 200 else summary
            elif 'description' in entry:
                summary = re.sub(r'<.*?>', '', entry.description)  # Remove HTML tags
                summary = summary[:200] + '...' if len(summary) > 200 else summary
            
            # Filter out non-policy content for State & Local Policies category
            if category == "State & Local Policies":
                if not is_policy_related_state_news(title, summary, source_name):
                    continue  # Skip non-policy articles
            
            # Assign tags based on content (simplified approach)
            tags = []
            lower_title = title.lower()
            if any(term in lower_title for term in ['court', 'supreme', 'judicial', 'judgment', 'verdict']):
                tags.append('Court Rulings')
            elif any(term in lower_title for term in ['bill', 'act', 'parliament', 'amendment', 'legislation']):
                tags.append('Legislative Updates')
            elif any(term in lower_title for term in ['analysis', 'study', 'report', 'research']):
                tags.append('Analysis')
            elif any(term in lower_title for term in ['breaking', 'just in', 'alert', 'latest']):
                tags.append('Breaking News')
            elif any(term in lower_title for term in ['expert', 'opinion', 'view', 'perspective']):
                tags.append('Expert Opinion')
            
            # Create article object
            article = NewsArticle(
                title=title,
                url=url,
                source=source_name,
                category=category,
                published_date=published_date,
                summary=summary,
                tags=tags
            )
            
            articles.append(article)
        
        print(f"Found {len(articles)} articles from {source_name}")
        return articles
        
    except Exception as e:
        print(f"Error processing {source_name}: {str(e)}")
        return articles  # Make sure to return empty list even in error case

def generate_html(articles, categories, category_descriptions):
    """Generate an HTML page with the articles organized by categories"""
    if not articles:
        print("No articles to display")
        return None
    
    # Create output directory if it doesn't exist
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    output_file = os.path.join(output_dir, 'index.html')
    
    html = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>PolicyRadar - Indian Policy News Aggregator</title>
        <style>
            :root {
                --primary-color: #1a237e;
                --secondary-color: #f57c00;
                --light-bg: #f8f9fa;
                --dark-text: #333;
                --light-text: #fff;
                --link-color: #1565c0;
                --link-hover: #0d47a1;
                --shadow: 0 2px 5px rgba(0,0,0,0.1);
                --hover-shadow: 0 4px 10px rgba(0,0,0,0.15);
            }
            
            * {
                box-sizing: border-box;
                margin: 0;
                padding: 0;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
                line-height: 1.6;
                color: var(--dark-text);
                background-color: var(--light-bg);
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                padding: 0 20px;
            }
            
            header {
                background-color: var(--primary-color);
                color: var(--light-text);
                padding: 2rem 0;
                text-align: center;
            }
            
            header h1 {
                font-size: 2.5rem;
                margin-bottom: 0.5rem;
            }
            
            header p {
                font-size: 1.1rem;
                opacity: 0.9;
            }
            
            .about-section {
                background-color: #fff;
                padding: 2rem;
                margin: 2rem 0;
                border-radius: 8px;
                box-shadow: var(--shadow);
            }
            
            .about-section h2 {
                color: var(--primary-color);
                margin-bottom: 1rem;
                font-size: 1.8rem;
            }
            
            .about-section p {
                margin-bottom: 1rem;
            }
            
            .about-section ul {
                margin-left: 1.5rem;
                margin-bottom: 1rem;
            }
            
            .about-section li {
                margin-bottom: 0.5rem;
            }
            
            .nav-container {
                position: sticky;
                top: 0;
                background-color: #fff;
                padding: 1rem 0;
                box-shadow: var(--shadow);
                z-index: 100;
                margin-bottom: 2rem;
            }
            
            .nav {
                display: flex;
                justify-content: center;
                flex-wrap: wrap;
                gap: 10px;
            }
            
            .nav-btn {
                background-color: #f5f5f5;
                border: 1px solid #ddd;
                border-radius: 20px;
                padding: 8px 16px;
                cursor: pointer;
                transition: all 0.2s ease;
                font-size: 0.9rem;
            }
            
            .nav-btn:hover {
                background-color: #e0e0e0;
            }
            
            .nav-btn.active {
                background-color: var(--primary-color);
                color: white;
                border-color: var(--primary-color);
            }
            
            section {
                display: none;
                margin-bottom: 3rem;
            }
            
            section.active {
                display: block;
            }
            
            .section-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                margin-bottom: 1.5rem;
            }
            
            .section-header h2 {
                color: var(--primary-color);
                font-size: 1.8rem;
            }
            
            .section-description {
                background-color: #fff;
                padding: 1.5rem;
                border-radius: 8px;
                box-shadow: var(--shadow);
                margin-bottom: 2rem;
                border-left: 4px solid var(--secondary-color);
            }
            
            .article {
                margin-bottom: 20px;
                padding: 1.5rem;
                background-color: #fff;
                border-radius: 8px;
                box-shadow: var(--shadow);
                transition: transform 0.2s ease, box-shadow 0.2s ease;
            }
            
            .article:hover {
                transform: translateY(-3px);
                box-shadow: var(--hover-shadow);
            }
            
            .article h3 {
                margin-top: 0;
                margin-bottom: 10px;
                font-size: 1.3rem;
            }
            
            .article-meta {
                font-size: 0.85rem;
                color: #666;
                margin-bottom: 1rem;
                display: flex;
                justify-content: space-between;
                flex-wrap: wrap;
            }
            
            .article-summary {
                margin-top: 1rem;
                font-style: italic;
                color: #555;
            }
            
            .tag-container {
                margin-top: 1rem;
                display: flex;
                flex-wrap: wrap;
                gap: 5px;
            }
            
            .tag {
                font-size: 0.75rem;
                padding: 3px 8px;
                border-radius: 4px;
                display: inline-block;
            }
            
            .tag-court-rulings { background-color: #e3f2fd; color: #0d47a1; }
            .tag-legislative-updates { background-color: #e8f5e9; color: #2e7d32; }
            .tag-analysis { background-color: #f3e5f5; color: #7b1fa2; }
            .tag-breaking-news { background-color: #ffebee; color: #c62828; }
            .tag-expert-opinion { background-color: #fff3e0; color: #e65100; }
            
            a {
                color: var(--link-color);
                text-decoration: none;
            }
            
            a:hover {
                text-decoration: underline;
                color: var(--link-hover);
            }
            
            .source-tag {
                display: inline-block;
                background-color: #e0e0e0;
                padding: 2px 8px;
                border-radius: 4px;
                font-size: 0.8rem;
                margin-right: 5px;
            }
            
            .category-technology { border-left: 4px solid #2196f3; }
            .category-economic { border-left: 4px solid #4caf50; }
            .category-healthcare { border-left: 4px solid #9c27b0; }
            .category-environmental { border-left: 4px solid #009688; }
            .category-education { border-left: 4px solid #ff9800; }
            .category-foreign { border-left: 4px solid #3f51b5; }
            .category-legal { border-left: 4px solid #e91e63; }
            .category-state { border-left: 4px solid #8bc34a; }
            
            .date {
                color: #666;
            }
            
            .footer {
                background-color: var(--primary-color);
                color: var(--light-text);
                padding: 2rem 0;
                margin-top: 3rem;
            }
            
            .footer-content {
                display: flex;
                flex-wrap: wrap;
                justify-content: space-between;
            }
            
            .footer-section {
                flex: 1;
                min-width: 250px;
                margin-bottom: 1.5rem;
                padding-right: 1rem;
            }
            
            .footer-section h3 {
                margin-bottom: 1rem;
                font-size: 1.3rem;
            }
            
            .footer-section p {
                margin-bottom: 0.8rem;
                font-size: 0.95rem;
                opacity: 0.9;
            }
            
            .copyright {
                text-align: center;
                padding-top: 1.5rem;
                margin-top: 1.5rem;
                border-top: 1px solid rgba(255,255,255,0.1);
                font-size: 0.9rem;
                opacity: 0.8;
            }
            
            .top-button {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background-color: var(--primary-color);
                color: white;
                border: none;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                font-size: 20px;
                cursor: pointer;
                box-shadow: var(--shadow);
                display: none;
                z-index: 99;
            }
            
            .top-button:hover {
                background-color: #303f9f;
            }
            
            .source-group {
                margin-bottom: 2rem;
            }
            
            .source-group h3 {
                color: var(--primary-color);
                margin-bottom: 1rem;
                padding-bottom: 0.5rem;
                border-bottom: 1px solid #eee;
            }
            
            @media (max-width: 768px) {
                .nav-btn {
                    padding: 6px 12px;
                    font-size: 0.8rem;
                }
                
                .article-meta {
                    flex-direction: column;
                    gap: 5px;
                }
                
                .footer-section {
                    flex: 100%;
                }
            }
        </style>
        <script>
            window.onload = function() {
                // Set up navigation
                const navButtons = document.querySelectorAll('.nav-btn');
                const sections = document.querySelectorAll('section');
                const aboutButton = document.getElementById('about-button');
                const aboutSection = document.getElementById('about-section');
                
                navButtons.forEach(button => {
                    button.addEventListener('click', function() {
                        // Remove active class from all buttons
                        navButtons.forEach(btn => btn.classList.remove('active'));
                        // Add active class to clicked button
                        this.classList.add('active');
                        
                        // Hide all sections
                        sections.forEach(section => section.classList.remove('active'));
                        
                        // Show the corresponding section
                        const targetId = this.getAttribute('data-target');
                        document.getElementById(targetId).classList.add('active');
                        
                        // Hide about section when navigating to content
                        if (targetId !== 'about-section') {
                            aboutSection.style.display = 'none';
                        }
                        
                        // Scroll to top
                        window.scrollTo(0, 0);
                    });
                });
                
                // About button functionality
                aboutButton.addEventListener('click', function() {
                    // Toggle display of about section
                    if (aboutSection.style.display === 'none' || aboutSection.style.display === '') {
                        aboutSection.style.display = 'block';
                    } else {
                        aboutSection.style.display = 'none';
                    }
                });
                
                // Back to top button
                const topButton = document.getElementById('top-button');
                
                window.addEventListener('scroll', function() {
                    if (window.pageYOffset > 300) {
                        topButton.style.display = 'block';
                    } else {
                        topButton.style.display = 'none';
                    }
                });
                
                topButton.addEventListener('click', function() {
                    window.scrollTo({
                        top: 0,
                        behavior: 'smooth'
                    });
                });
                
                // Make the "all articles" section active by default
                document.querySelector('.nav-btn[data-target="all-section"]').click();
            };
        </script>
    </head>
    <body>
        <header>
            <div class="container">
                <h1>PolicyRadar</h1>
                <p>Cutting through the noise of Indian policy developments</p>
                <p><small>Generated on: """ + datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</small></p>
            </div>
        </header>
        
        <main class="container">
            <div class="about-section" id="about-section">
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
                <p>PolicyRadar is updated daily:</p>
                <ul>
                    <li>Monday: Weekend developments and upcoming policy agenda</li>
                    <li>Wednesday: Mid-week updates and emerging issues</li>
                    <li>Friday: Week's most significant developments and analysis</li>
                </ul>
                
                <h2>About the Creator</h2>
                <p>PolicyRadar is created and curated by Roma Thakur, a technical writer and policy researcher with expertise in data privacy, technology policy, and regulatory communications. With a background in both computer science and social & public policy, Roma brings a multidisciplinary perspective to policy curation.</p>
            </div>
            
            <div class="nav-container">
                <div class="nav">
                    <button class="nav-btn" data-target="all-section">All Policy News</button>
    """
    
    # Add navigation buttons for each category
    for category in categories:
        category_id = category.lower().replace(' ', '-').replace('&', 'and')
        html += f'<button class="nav-btn" data-target="{category_id}-section">{category}</button>\n'
    
    html += """
                    <button class="nav-btn" id="about-button">About</button>
                </div>
            </div>
            
            <!-- All articles section -->
            <section id="all-section">
                <div class="section-header">
                    <h2>Latest Policy Developments</h2>
                </div>
    """
    
    # Group articles by category for the All section
    category_articles = {}
    for article in articles:
        if article.category not in category_articles:
            category_articles[article.category] = []
        category_articles[article.category].append(article)
    
    # Add articles by category in the All section
    for category, cat_articles in category_articles.items():
        if cat_articles:
            category_class = f"category-{category.lower().split()[0]}"
            html += f'<div class="section-header"><h2>{category}</h2></div>\n'
            
            # Add description if available
            if category in category_descriptions:
                html += f'<div class="section-description"><p>{category_descriptions[category]}</p></div>\n'
            
            # Group by source
            source_articles = {}
            for article in cat_articles:
                if article.source not in source_articles:
                    source_articles[article.source] = []
                source_articles[article.source].append(article)
            
            # Display articles by source
            for source, src_articles in source_articles.items():
                html += f'<div class="source-group"><h3>{source}</h3>\n'
                
                for article in src_articles:
                    html += f'<div class="article {category_class}">\n'
                    html += f'<h3><a href="{article.url}" target="_blank">{article.title}</a></h3>\n'
                    html += '<div class="article-meta">\n'
                    
                    html += f'<div><span class="source-tag">{article.source}</span></div>\n'
                    
                    if article.published_date:
                        html += f'<span class="date">{article.published_date}</span>\n'
                        
                    html += '</div>\n'
                    
                    if article.summary:
                        html += f'<div class="article-summary">{article.summary}</div>\n'
                    
                    # Add tags if any
                    if article.tags:
                        html += '<div class="tag-container">\n'
                        for tag in article.tags:
                            tag_class = f"tag-{tag.lower().replace(' ', '-')}"
                            html += f'<span class="tag {tag_class}">{tag}</span>\n'
                        html += '</div>\n'
                        
                    html += '</div>\n'
                
                html += '</div>\n'
    
    html += "</section>\n"
    
    # Add individual category sections
    for category in categories:
        category_id = category.lower().replace(' ', '-').replace('&', 'and')
        category_articles_filtered = [a for a in articles if a.category == category]
        category_class = f"category-{category.lower().split()[0]}"
        
        html += f'<section id="{category_id}-section">\n'
        html += f'<div class="section-header"><h2>{category}</h2></div>\n'
        
        # Add description if available
        if category in category_descriptions:
            html += f'<div class="section-description"><p>{category_descriptions[category]}</p></div>\n'
        
        # Group by source
        source_articles = {}
        for article in category_articles_filtered:
            if article.source not in source_articles:
                source_articles[article.source] = []
            source_articles[article.source].append(article)
        
        # Display articles by source
        if source_articles:
            for source, src_articles in source_articles.items():
                html += f'<div class="source-group"><h3>{source}</h3>\n'
                
                for article in src_articles:
                    html += f'<div class="article {category_class}">\n'
                    html += f'<h3><a href="{article.url}" target="_blank">{article.title}</a></h3>\n'
                    html += '<div class="article-meta">\n'
                    
                    html += f'<div><span class="source-tag">{article.source}</span></div>\n'
                    
                    if article.published_date:
                        html += f'<span class="date">{article.published_date}</span>\n'
                        
                    html += '</div>\n'
                    
                    if article.summary:
                        html += f'<div class="article-summary">{article.summary}</div>\n'
                    
                    # Add tags if any
                    if article.tags:
                        html += '<div class="tag-container">\n'
                        for tag in article.tags:
                            tag_class = f"tag-{tag.lower().replace(' ', '-')}"
                            html += f'<span class="tag {tag_class}">{tag}</span>\n'
                        html += '</div>\n'
                        
                    html += '</div>\n'
                
                html += '</div>\n'
        else:
            html += "<p>No articles found for this category.</p>\n"
        
        html += "</section>\n"
    
    html += """
        </main>
        
        <button id="top-button" class="top-button">↑</button>
        
        <footer class="footer">
            <div class="container">
                <div class="footer-content">
                    <div class="footer-section">
                        <h3>PolicyRadar</h3>
                        <p>A curated view of Indian policy developments across key domains.</p>
                        <p>Published daily.</p>
                    </div>
                    
                    <div class="footer-section">
                        <h3>Contact</h3>
                        <p>For suggestions, feedback, or collaboration opportunities, please reach out to us.</p>
                        <p>We value your input, suggestions, and questions.</p>
                    </div>
                    
                    <div class="footer-section">
                        <h3>Other Ways to Connect</h3>
                        <p><strong>Suggest a Source</strong>: Know of a valuable policy news source we should monitor?</p>
                        <p><strong>Report an Error</strong>: Accuracy matters. If you spot any inaccuracies, please notify us.</p>
                        <p><strong>Collaboration Opportunities</strong>: We're open to partnerships with organizations and individuals working in the policy space.</p>
                    </div>
                </div>
                
                <div class="copyright">
                    <p>&copy; """ + datetime.datetime.now().strftime('%Y') + """ PolicyRadar by Roma Thakur. All rights reserved.</p>
                </div>
            </div>
        </footer>
    </body>
    </html>
    """
    
    # Write to file
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"HTML output saved to {output_file}")
    return output_file

# Category descriptions
category_descriptions = {
    "Technology Policy": "Covering digital governance, data privacy, cybersecurity, AI regulation, telecommunications, internet access, and tech industry oversight. This category tracks policy developments that shape India's digital landscape and technology adoption.",
    "Economic Policy": "Monitoring fiscal policies, monetary decisions, taxation, trade agreements, financial regulations, economic reforms, labor laws, and market interventions. Follows how government decisions influence India's economic development and business environment.",
    "Healthcare Policy": "Tracking healthcare access initiatives, medical insurance policies, pharmaceutical regulations, public health programs, medical education standards, and healthcare infrastructure development across India.",
    "Environmental Policy": "Following climate action plans, pollution control measures, conservation efforts, renewable energy policies, forest management, water resource governance, and sustainability initiatives at national and state levels.",
    "Education Policy": "Covering school and higher education frameworks, skill development programs, educational inclusion measures, research funding, academic standards, and reforms to teaching methodologies across India's educational landscape.",
    "Foreign Policy": "Monitoring international relations, bilateral and multilateral agreements, trade negotiations, diplomatic initiatives, security alliances, and India's position on global governance and regional cooperation.",
    "Constitutional & Legal": "Tracking constitutional amendments, Supreme Court decisions, legal reforms, judicial appointments, legislative changes, and interpretations of fundamental rights that shape India's legal framework.",
    "State & Local Policies": "Following state-specific policy innovations, center-state relations, local governance initiatives, urban planning, rural development schemes, and regional policy approaches that impact local communities."
}

# Define RSS feeds for each category
feeds = [
    # Technology Policy
    ("MediaNama", "https://www.medianama.com/feed/", "Technology Policy"),
    ("Internet Freedom Foundation", "https://internetfreedom.in/rss", "Technology Policy"),
    ("Inc42", "https://inc42.com/feed/", "Technology Policy"),
    ("Entrackr", "https://entrackr.com/rss", "Technology Policy"),
    ("Mint Tech", "https://www.livemint.com/rss/technology", "Technology Policy"),
    ("The Ken", "https://the-ken.com/feed/", "Technology Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/google_feeds.xml", "Technology Policy"),

    # Economic Policy
    ("Mint Economy", "https://www.livemint.com/rss/economy", "Economic Policy"),
    ("Economic Times Economy", "https://economictimes.indiatimes.com/news/economy/rssfeeds/1373380680.cms", "Economic Policy"),
    ("Business Standard Economy", "https://www.business-standard.com/rss/economy-102.rss", "Economic Policy"),
    ("Money Control Economy", "https://www.moneycontrol.com/rss/economy.xml", "Economic Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/category/economy/google_feeds.xml", "Economic Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/category/budget/google_feeds.xml", "Economic Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/category/indias-job-crisis/google_feeds.xml", "Economic Policy"),
    ("The Hindu Business Line", "https://www.thehindubusinessline.com/economy/feeder/default.rss", "Economic Policy"),
    ("The Print - Economy", "https://theprint.in/category/economy/feed/", "Economic Policy"),

    # Healthcare Policy
    ("Express Healthcare", "https://www.expresshealthcare.in/feed/", "Healthcare Policy"),
    ("Health Issues India", "https://www.healthissuesindia.com/feed/", "Healthcare Policy"),
    ("ET Health", "https://health.economictimes.indiatimes.com/rss/topstories", "Healthcare Policy"),
    ("The Hindu Health", "https://www.thehindu.com/sci-tech/health/feeder/default.rss", "Healthcare Policy"),
    ("The Print - Health", "https://theprint.in/category/health/feed/", "Healthcare Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/category/health/google_feeds.xml", "Healthcare Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/category/mental-health/google_feeds.xml", "Healthcare Policy"),

    # Environmental Policy
    ("Down To Earth", "https://www.downtoearth.org.in/feed", "Environmental Policy"),
    ("Mongabay India", "https://india.mongabay.com/feed/", "Environmental Policy"),
    ("Carbon Copy", "https://carboncopy.info/feed/", "Environmental Policy"),
    ("The Print - Environment", "https://theprint.in/environment/feed/", "Environmental Policy"),
    ("Centre for Science and Environment", "https://www.cseindia.org/rss/home.xml", "Environmental Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/google_feeds.xml", "Environmental Policy"),

    # Education Policy
    ("The Hindu Education", "https://www.thehindu.com/education/feeder/default.rss", "Education Policy"),
    ("India Education Diary", "https://indiaeducationdiary.in/feed/", "Education Policy"),
    ("The Print Education", "https://theprint.in/category/india/education/feed/", "Education Policy"),
    ("Education World", "https://www.educationworld.in/feed/", "Education Policy"),
    ("The Wire Education", "https://thewire.in/category/education/feed", "Education Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/category/education/google_feeds.xml", "Education Policy"),

    # Foreign Policy
    ("The Hindu International", "https://www.thehindu.com/news/international/feeder/default.rss", "Foreign Policy"),
    ("The Diplomat - South Asia", "https://thediplomat.com/regions/south-asia/feed/", "Foreign Policy"),
    ("Gateway House", "https://www.gatewayhouse.in/feed/", "Foreign Policy"),
    ("The Print - Diplomacy", "https://theprint.in/category/diplomacy/feed/", "Foreign Policy"),
    ("Institute of Peace and Conflict Studies", "https://www.ipcs.org/feed/", "Foreign Policy"),
    ("IndiaSpend", "https://www.indiaspend.com/google_feeds.xml", "Foreign Policy"),

    # Constitutional & Legal
    ("Live Law", "https://www.livelaw.in/feed", "Constitutional & Legal"),
    ("Indiaspend", "https://www.indiaspend.com/category/police-judicial-reforms/google_feeds.xml", "Constitutional & Legal"),
    ("Indiaspend", "https://www.indiaspend.com/category/data-gaps/google_feeds.xml", "Constitutional & Legal"),
    ("Bar and Bench", "https://www.barandbench.com/feed", "Constitutional & Legal"),
    ("The Leaflet", "https://theleaflet.in/feed/", "Constitutional & Legal"),
    ("SCObserver", "https://www.scobserver.in/feed/", "Constitutional & Legal"),
    ("Vidhi Centre for Legal Policy", "https://vidhilegalpolicy.in/feed/", "Constitutional & Legal"),

    # State & Local Policies
    ("East Mojo", "https://www.eastmojo.com/feed/", "State & Local Policies"),
    ("Gaon Connection", "https://en.gaonconnection.com/feed/", "State & Local Policies"),
    ("101 Reporters", "https://101reporters.com/rss.xml", "State & Local Policies"),
    ("IndiaSpend", "https://www.indiaspend.com/google_feeds.xml", "State & Local Policies"),
    ("IndiaSpend", "https://www.indiaspend.com/category/gendercheck/google_feeds.xml", "State & Local Policies"),
]

def main():
    """Main function to run the PolicyRadar aggregator"""
    print("Starting PolicyRadar aggregator...")
    
    # Define the categories
    categories = [
        "Technology Policy", 
        "Economic Policy", 
        "Healthcare Policy", 
        "Environmental Policy", 
        "Education Policy",
        "Foreign Policy",
        "Constitutional & Legal",
        "State & Local Policies"
    ]
    
    # Initialize an empty list to store all articles
    all_articles = []
    
    # Fetch articles from feeds
    for source_name, feed_url, category in feeds:
        articles = fetch_feed(feed_url, source_name, category)
        if articles is not None:  # Add this check
            all_articles.extend(articles)
        else:
            print(f"Warning: fetch_feed returned None for {source_name}")
        
        # Add a small random delay between requests to avoid hammering servers
        time.sleep(random.uniform(1, 3))
    
    print(f"Total articles collected: {len(all_articles)}")
    
    # Generate HTML with the collected articles
    if all_articles:
        output_file = generate_html(all_articles, categories, category_descriptions)
        print(f"HTML output saved to {output_file}")
    else:
        print("No articles were collected. Check feed URLs and network connection.")

# Run the main function if this script is executed directly
if __name__ == "__main__":
    main()
