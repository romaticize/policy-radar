/**
 * PolicyRadar v6.2 - Top Stories Module
 * 
 * Replaces pattern-based "Trending Topics" with velocity-based "Top Stories"
 * Shows articles that are being covered by multiple sources (breaking/high-impact)
 * 
 * Include after main index.html scripts:
 *   <script src="js/top-stories.js"></script>
 */

(function() {
    'use strict';

    // =========================================
    // CONFIGURATION
    // =========================================
    const CONFIG = {
        maxSidebarItems: 5,
        maxTickerItems: 10,
        tickerBaseSpeed: 35, // seconds for base animation
    };

    // =========================================
    // INJECT CSS
    // =========================================
    const styles = `
        /* Top Stories Banner */
        .top-stories-banner {
            background: var(--bg-secondary);
            border-bottom: 1px solid var(--border-color);
            padding: 0.5rem 0;
            overflow: hidden;
        }

        .top-stories-banner-inner {
            max-width: 1400px;
            margin: 0 auto;
            padding: 0 1rem;
            display: flex;
            align-items: center;
            gap: 1rem;
        }

        .top-stories-badge {
            background: var(--accent-primary);
            color: white;
            font-weight: 600;
            font-size: 0.7rem;
            padding: 0.25rem 0.6rem;
            border-radius: 3px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
            flex-shrink: 0;
            white-space: nowrap;
        }

        .top-stories-ticker {
            flex: 1;
            overflow: hidden;
            mask-image: linear-gradient(
                90deg, transparent 0%, black 3%, black 97%, transparent 100%
            );
            -webkit-mask-image: linear-gradient(
                90deg, transparent 0%, black 3%, black 97%, transparent 100%
            );
        }

        .top-stories-ticker-track {
            display: flex;
            gap: 2.5rem;
            animation: ticker-scroll var(--ticker-duration, 45s) linear infinite;
            width: max-content;
        }

        .top-stories-ticker-track:hover {
            animation-play-state: paused;
        }

        @keyframes ticker-scroll {
            0% { transform: translateX(0); }
            100% { transform: translateX(-50%); }
        }

        .ticker-item {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            white-space: nowrap;
            font-size: 0.8125rem;
            color: var(--text-secondary);
            text-decoration: none;
        }

        .ticker-item:hover { color: var(--accent-primary); }

        .ticker-item-source {
            color: var(--text-muted);
            font-size: 0.75rem;
        }

        .ticker-dot {
            width: 4px;
            height: 4px;
            background: var(--accent-primary);
            border-radius: 50%;
            flex-shrink: 0;
        }

        .top-stories-view-all {
            font-size: 0.75rem;
            color: var(--accent-primary);
            text-decoration: none;
            white-space: nowrap;
            padding: 0.25rem 0.5rem;
            border: 1px solid var(--accent-primary);
            border-radius: var(--radius-sm);
            transition: all var(--transition-fast);
        }

        .top-stories-view-all:hover {
            background: var(--accent-primary);
            color: white;
        }

        /* Top Stories Sidebar Section */
        .top-stories-list {
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
        }

        .top-story-item {
            display: flex;
            flex-direction: column;
            gap: 0.25rem;
            padding: var(--space-3);
            background: var(--bg-secondary);
            border: 1px solid transparent;
            border-radius: var(--radius-sm);
            cursor: pointer;
            transition: all var(--transition-fast);
            text-decoration: none;
            color: inherit;
        }

        .top-story-item:hover {
            border-color: var(--accent-primary);
            background: var(--accent-glow);
        }

        .top-story-header {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }

        .top-story-rank {
            font-size: 0.6875rem;
            font-weight: 700;
            color: var(--accent-primary);
            background: var(--accent-glow);
            width: 1.25rem;
            height: 1.25rem;
            display: flex;
            align-items: center;
            justify-content: center;
            border-radius: 3px;
            flex-shrink: 0;
        }

        .top-story-meta {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.6875rem;
            color: var(--text-muted);
        }

        .top-story-source-count {
            background: var(--high-bg);
            color: var(--high-color);
            padding: 0.125rem 0.375rem;
            border-radius: 3px;
            font-weight: 600;
        }

        .top-story-title {
            font-size: 0.8125rem;
            font-weight: 500;
            line-height: 1.4;
            color: var(--text-primary);
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
        }

        .top-stories-empty {
            color: var(--text-muted);
            font-size: 0.875rem;
            padding: 1rem 0;
            text-align: center;
        }

        .view-all-stories-btn {
            margin-top: var(--space-3);
            padding: var(--space-2) var(--space-3);
            font-size: 0.8125rem;
            background: var(--bg-secondary);
            border: 1px solid var(--border-color);
            border-radius: var(--radius-sm);
            cursor: pointer;
            color: var(--text-secondary);
            width: 100%;
            transition: all var(--transition-fast);
        }

        .view-all-stories-btn:hover {
            background: var(--accent-primary);
            border-color: var(--accent-primary);
            color: white;
        }

        .view-all-stories-btn.active {
            background: var(--accent-primary);
            border-color: var(--accent-primary);
            color: white;
        }

        /* Enhanced Newsletter */
        .newsletter-cta {
            background: linear-gradient(
                135deg, var(--accent-primary) 0%, #1d4ed8 100%
            ) !important;
            color: white !important;
            border: none !important;
        }

        .newsletter-cta .card-title { color: white; }
        .newsletter-cta p { color: rgba(255, 255, 255, 0.9); }

        .newsletter-cta .btn-primary {
            background: white;
            color: var(--accent-primary);
            border: none;
            font-weight: 600;
        }

        .newsletter-cta .btn-primary:hover {
            background: rgba(255, 255, 255, 0.9);
            transform: translateY(-1px);
        }

        /* Mobile */
        @media (max-width: 768px) {
            .top-stories-banner { display: none; }
        }
    `;

    // Inject styles
    const styleSheet = document.createElement('style');
    styleSheet.textContent = styles;
    document.head.appendChild(styleSheet);

    // =========================================
    // TOP STORIES MODULE
    // =========================================
    const TopStories = {
        stories: [],
        isFiltered: false,

        init() {
            // Create banner element if not exists
            this.createBanner();
            
            // Override the old renderTrendingTopics if it exists
            if (typeof window.renderTrendingTopics === 'function') {
                const originalRender = window.renderTrendingTopics;
                window.renderTrendingTopics = () => {
                    this.render();
                };
            }

            console.log('[TopStories] Initialized');
        },

        createBanner() {
            // Check if banner already exists
            if (document.getElementById('top-stories-banner')) return;

            const banner = document.createElement('div');
            banner.id = 'top-stories-banner';
            banner.className = 'top-stories-banner';
            banner.style.display = 'none';
            banner.innerHTML = `
                <div class="top-stories-banner-inner">
                    <span class="top-stories-badge">📌 Top Stories</span>
                    <div class="top-stories-ticker">
                        <div class="top-stories-ticker-track" id="ticker-track">
                        </div>
                    </div>
                    <a href="#" class="top-stories-view-all" 
                       onclick="TopStories.toggleFilter(); return false;">
                        View All
                    </a>
                </div>
            `;

            // Insert after filter-bar
            const filterBar = document.querySelector('.filter-bar');
            if (filterBar && filterBar.nextSibling) {
                filterBar.parentNode.insertBefore(banner, filterBar.nextSibling);
            }
        },

        getTopStories() {
            const state = window.state;
            if (!state || !state.allArticles) return [];

            return state.allArticles
                .filter(a => a.is_breaking || a.is_high_impact)
                .sort((a, b) => (b.relevance_score || 0) - (a.relevance_score || 0))
                .slice(0, CONFIG.maxTickerItems);
        },

        render() {
            this.stories = this.getTopStories();
            this.renderSidebar();
            this.renderTicker();
        },

        renderSidebar() {
            // Try to find the trending-list container (old) or top-stories-list (new)
            let container = document.getElementById('top-stories-list');
            if (!container) {
                container = document.getElementById('trending-list');
            }
            if (!container) return;

            // Update the card title if it still says "Trending"
            const cardTitle = container.parentElement?.querySelector('.card-title');
            if (cardTitle && cardTitle.textContent.includes('Trending')) {
                cardTitle.textContent = '📌 Today\'s Top Stories';
                
                // Add subtitle
                const subtitle = document.createElement('p');
                subtitle.style.cssText = `
                    font-size: 0.75rem; 
                    color: var(--text-muted); 
                    margin-bottom: 0.75rem;
                `;
                subtitle.textContent = 'Most covered by multiple sources';
                cardTitle.after(subtitle);
            }

            // Hide the old clear trending button
            const clearBtn = document.getElementById('clear-trending-btn');
            if (clearBtn) clearBtn.style.display = 'none';

            if (!this.stories || this.stories.length === 0) {
                container.innerHTML = `
                    <p class="top-stories-empty">
                        No major developments detected today
                    </p>
                `;
                return;
            }

            const escapeHtml = window.escapeHtml || (s => s);

            container.innerHTML = this.stories.slice(0, CONFIG.maxSidebarItems)
                .map((article, index) => {
                    const sourceCount = article.breaking_source_count || 
                        (article.is_breaking ? '5+' : '3+');
                    return `
                        <a class="top-story-item" 
                           href="${escapeHtml(article.url)}" 
                           target="_blank" 
                           rel="noopener">
                            <div class="top-story-header">
                                <span class="top-story-rank">${index + 1}</span>
                                <div class="top-story-meta">
                                    <span class="top-story-source-count">
                                        ${sourceCount} sources
                                    </span>
                                    <span>${escapeHtml(article.source_name || '')}</span>
                                </div>
                            </div>
                            <div class="top-story-title">
                                ${escapeHtml(article.title || '')}
                            </div>
                        </a>
                    `;
                }).join('');

            // Add or update view all button
            let viewAllBtn = document.getElementById('view-all-stories-btn');
            if (!viewAllBtn) {
                viewAllBtn = document.createElement('button');
                viewAllBtn.id = 'view-all-stories-btn';
                viewAllBtn.className = 'view-all-stories-btn';
                viewAllBtn.onclick = () => this.toggleFilter();
                container.after(viewAllBtn);
            }
            viewAllBtn.textContent = this.isFiltered ? 
                '← Back to All Articles' : 
                `View All ${this.stories.length} Top Stories`;
            viewAllBtn.classList.toggle('active', this.isFiltered);
        },

        renderTicker() {
            const banner = document.getElementById('top-stories-banner');
            const track = document.getElementById('ticker-track');
            if (!banner || !track) return;

            if (this.stories.length < 3) {
                banner.style.display = 'none';
                return;
            }

            banner.style.display = 'block';
            const escapeHtml = window.escapeHtml || (s => s);

            // Duplicate for seamless loop
            const items = [...this.stories, ...this.stories];
            track.innerHTML = items.map(article => {
                const title = (article.title || '').substring(0, 70);
                const ellipsis = (article.title || '').length > 70 ? '...' : '';
                return `
                    <a class="ticker-item" 
                       href="${escapeHtml(article.url)}" 
                       target="_blank" 
                       rel="noopener">
                        <span class="ticker-dot"></span>
                        <span>${escapeHtml(title)}${ellipsis}</span>
                        <span class="ticker-item-source">
                            ${escapeHtml(article.source_name || '')}
                        </span>
                    </a>
                `;
            }).join('');

            // Adjust animation duration
            const duration = Math.max(CONFIG.tickerBaseSpeed, this.stories.length * 4);
            track.style.setProperty('--ticker-duration', `${duration}s`);
        },

        toggleFilter() {
            this.isFiltered = !this.isFiltered;
            const state = window.state;

            if (this.isFiltered) {
                // Filter to top stories
                const topUrls = new Set(this.stories.map(a => a.url));
                state.filteredArticles = state.allArticles.filter(a => 
                    a.is_breaking || a.is_high_impact || topUrls.has(a.url)
                );
                state.totalPages = Math.ceil(
                    state.filteredArticles.length / (window.CONFIG?.pageSize || 25)
                );
                state.currentPage = 1;

                if (typeof window.renderArticles === 'function') {
                    window.renderArticles();
                }
                if (typeof window.announceToScreenReader === 'function') {
                    window.announceToScreenReader(
                        `Showing ${state.filteredArticles.length} top stories`
                    );
                }
            } else {
                // Reset to normal
                if (typeof window.applyFiltersAndRender === 'function') {
                    window.applyFiltersAndRender();
                }
            }

            this.renderSidebar();
        }
    };

    // =========================================
    // INITIALIZE ON DOM READY
    // =========================================
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => TopStories.init());
    } else {
        TopStories.init();
    }

    // Export for global access
    window.TopStories = TopStories;

})();
