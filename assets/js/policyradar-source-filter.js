// policyradar-source-filter.js - Source Type Filter Addon
// Add this AFTER your main inline script loads
// In index.html, add: <script defer src="js/policyradar-source-filter.js"></script>

(function() {
    'use strict';
    
    // Wait for DOM and state to be ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        // Small delay to ensure main script has initialized
        setTimeout(init, 100);
    }
    
    // ==========================================================================
    // SOURCE TYPE CLASSIFICATION
    // ==========================================================================
    const SOURCE_TYPES = {
        government: [
            'pib', 'pmo', 'mea', 'mod', 'mha', 'meity', 'dea', 'cbdt', 'cbic',
            'gst council', 'cabinet', 'president', 'vice president', 'lok sabha',
            'rajya sabha', 'gazette', 'niti aayog', 'digital india', 'india.gov',
            'mnre', 'moef', 'mohfw', 'ugc', 'aicte', 'ncert', 'dst', 'drdo',
            'election commission', 'cvc', 'rti', 'lokpal', 'upsc', 'ssc',
            'labour', 'epfo', 'esic', 'fssai', 'icmr', 'aiims', 'ayush', 
            'icar', 'forest survey', 'mygov', 'press information', 'ministry'
        ],
        regulator: [
            'rbi', 'reserve bank', 'sebi', 'irdai', 'pfrda', 'ibbi', 'cci',
            'competition commission', 'trai', 'cag', 'cert-in', 'cpcb', 'ngt'
        ],
        media: [
            'economic times', 'mint', 'livemint', 'financial express', 'cnbc',
            'hindu', 'hindustan times', 'times of india', 'indian express',
            'theprint', 'print', 'ndtv', 'scroll', 'wire', 'quint',
            'india today', 'outlook', 'business today', 'forbes', 'fortune',
            'deccan', 'frontline', 'caravan', 'diplomat', 'inc42', 'yourstory',
            'medianama', 'moneycontrol', 'bloomberg', 'reuters', 'pti',
            'ani', 'ians', 'down to earth', 'mongabay'
        ],
        'think-tank': [
            'orf', 'observer research', 'carnegie', 'brookings', 'idsa', 'icrier',
            'nipfp', 'ncaer', 'cbga', 'cpr', 'cprindia', 'vidhi', 'prs',
            'prsindia', 'daksh', 'ccs', 'centre for civil', 'gateway house',
            'takshashila', 'ceew', 'teri', 'cse', 'climate policy', 'nias',
            'iff', 'internet freedom', 'sflc', 'cis-india'
        ],
        legal: [
            'livelaw', 'bar and bench', 'barandbench', 'supreme court observer',
            'scobserver', 'scc online', 'legally india', 'taxguru', 'nyaaya',
            'ipleaders', 'lawctopus', 'legal bites'
        ]
    };
    
    function getSourceType(sourceName) {
        if (!sourceName) return 'other';
        const name = sourceName.toLowerCase();
        
        for (const [type, keywords] of Object.entries(SOURCE_TYPES)) {
            if (keywords.some(kw => name.includes(kw))) {
                return type;
            }
        }
        return 'other';
    }
    
    // ==========================================================================
    // INITIALIZATION
    // ==========================================================================
    function init() {
        console.log('[SourceFilter] Initializing...');
        
        // Check if state exists (from main script)
        if (typeof state === 'undefined') {
            console.error('[SourceFilter] state not found. Make sure main script loads first.');
            return;
        }
        
        // Add sourceType to filters
        if (!state.filters.sourceType) {
            state.filters.sourceType = 'all';
        }
        
        // Inject the UI
        injectSourceFilterUI();
        
        // Patch the filter function
        patchApplyFilters();
        
        // Load from URL if present
        loadSourceFilterFromURL();
        
        console.log('[SourceFilter] Ready!');
    }
    
    // ==========================================================================
    // UI INJECTION
    // ==========================================================================
    function injectSourceFilterUI() {
        // Find the domain filter row to insert after
        const domainRow = document.querySelector('.domain-filter-row');
        if (!domainRow) {
            console.warn('[SourceFilter] Could not find .domain-filter-row');
            return;
        }
        
        // Create source filter row
        const sourceRow = document.createElement('div');
        sourceRow.className = 'source-type-filter-row';
        sourceRow.innerHTML = `
            <div class="source-type-pills" role="radiogroup" aria-label="Source type filter">
                <button class="source-pill active" data-source-type="all">
                    All Sources
                </button>
                <button class="source-pill" data-source-type="government">
                    🏛️ Govt
                </button>
                <button class="source-pill" data-source-type="regulator">
                    📋 Regulators
                </button>
                <button class="source-pill" data-source-type="media">
                    📰 Media
                </button>
                <button class="source-pill" data-source-type="think-tank">
                    🧠 Think Tanks
                </button>
                <button class="source-pill" data-source-type="legal">
                    ⚖️ Legal
                </button>
            </div>
        `;
        
        // Insert after domain row
        domainRow.parentNode.insertBefore(sourceRow, domainRow.nextSibling);
        
        // Add event listeners
        sourceRow.querySelectorAll('.source-pill').forEach(btn => {
            btn.addEventListener('click', () => {
                setSourceTypeFilter(btn.dataset.sourceType, btn);
            });
        });
        
        // Add styles
        addStyles();
    }
    
    function addStyles() {
        const style = document.createElement('style');
        style.textContent = `
            .source-type-filter-row {
                padding: var(--space-2, 0.5rem) var(--space-6, 1.5rem);
                border-bottom: 1px solid var(--border-color, #e5e7eb);
                background: var(--bg-primary, #fff);
                overflow-x: auto;
                -webkit-overflow-scrolling: touch;
            }
            
            .source-type-pills {
                display: flex;
                gap: var(--space-2, 0.5rem);
                min-width: max-content;
            }
            
            .source-pill {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1, 0.25rem);
                padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
                font-size: 0.8125rem;
                font-weight: 500;
                color: var(--text-secondary, #374151);
                background: var(--bg-card, #fff);
                border: 1px solid var(--border-color, #e5e7eb);
                border-radius: var(--radius-md, 10px);
                cursor: pointer;
                transition: all 0.15s ease;
                white-space: nowrap;
            }
            
            .source-pill:hover {
                border-color: var(--accent-primary, #2563eb);
                background: var(--accent-glow, rgba(37, 99, 235, 0.1));
            }
            
            .source-pill.active {
                background: var(--accent-primary, #2563eb);
                border-color: var(--accent-primary, #2563eb);
                color: white;
            }
            
            /* Dark mode */
            [data-theme="dark"] .source-type-filter-row {
                background: var(--bg-primary, #0f172a);
                border-color: var(--border-color, #334155);
            }
            
            [data-theme="dark"] .source-pill {
                background: var(--bg-card, #1e293b);
                border-color: var(--border-color, #334155);
                color: var(--text-secondary, #cbd5e1);
            }
            
            [data-theme="dark"] .source-pill:hover {
                border-color: var(--accent-primary, #3b82f6);
                background: var(--accent-glow, rgba(59, 130, 246, 0.15));
            }
            
            [data-theme="dark"] .source-pill.active {
                background: var(--accent-primary, #3b82f6);
                color: white;
            }
            
            /* Mobile */
            @media (max-width: 768px) {
                .source-type-filter-row {
                    padding: var(--space-2, 0.5rem) var(--space-3, 0.75rem);
                }
                
                .source-pill {
                    padding: var(--space-1, 0.25rem) var(--space-2, 0.5rem);
                    font-size: 0.75rem;
                }
            }
            
            /* Touch targets */
            @media (hover: none) and (pointer: coarse) {
                .source-pill {
                    min-height: 44px;
                    padding: var(--space-3, 0.75rem) var(--space-4, 1rem);
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    // ==========================================================================
    // FILTER LOGIC
    // ==========================================================================
    function setSourceTypeFilter(type, element) {
        // Update UI
        document.querySelectorAll('.source-pill').forEach(pill => {
            pill.classList.remove('active');
        });
        element.classList.add('active');
        
        // Update state
        state.filters.sourceType = type;
        state.currentPage = 1;
        
        // Update URL
        updateURLWithSourceType();
        
        // Apply filters
        if (typeof applyFiltersAndRender === 'function') {
            applyFiltersAndRender();
        }
        
        // Show toast
        if (type !== 'all' && typeof showToast === 'function') {
            const labels = {
                'government': 'Government sources',
                'regulator': 'Regulatory bodies',
                'media': 'Media outlets',
                'think-tank': 'Think tanks',
                'legal': 'Legal sources'
            };
            showToast(`Filtering by ${labels[type] || type}`);
        }
    }
    
    // Expose to global scope
    window.setSourceTypeFilter = setSourceTypeFilter;
    window.getSourceType = getSourceType;
    
    // ==========================================================================
    // PATCH EXISTING FILTER FUNCTION
    // ==========================================================================
    function patchApplyFilters() {
        // Store original function
        const originalApplyFiltersAndRender = window.applyFiltersAndRender;
        
        if (typeof originalApplyFiltersAndRender !== 'function') {
            console.warn('[SourceFilter] applyFiltersAndRender not found');
            return;
        }
        
        // Override with patched version
        window.applyFiltersAndRender = function() {
            // Call original first
            let articles = [...state.allArticles];
            
            // ============ EXISTING FILTERS (copy from original) ============
            
            // Time filter
            if (state.filters.time !== 'all') {
                const now = new Date();
                const cutoff = new Date();
                if (state.filters.time === 'today') {
                    cutoff.setHours(0, 0, 0, 0);
                } else if (state.filters.time === 'week') {
                    cutoff.setDate(now.getDate() - 7);
                }
                articles = articles.filter(a => new Date(a.publication_date) >= cutoff);
            }
            
            // Priority filter
            if (state.filters.priority !== 'all') {
                if (state.filters.priority === 'critical') {
                    articles = articles.filter(a => a.priority_class === 'critical');
                } else if (state.filters.priority === 'high') {
                    articles = articles.filter(a => 
                        a.priority_class === 'critical' || a.priority_class === 'high'
                    );
                }
            }
            
            // Domain filter
            if (state.filters.domain && typeof DOMAIN_CONFIG !== 'undefined' && DOMAIN_CONFIG[state.filters.domain]) {
                const domainConfig = DOMAIN_CONFIG[state.filters.domain];
                
                if (state.filters.subsector && domainConfig.subsectors && domainConfig.subsectors[state.filters.subsector]) {
                    const subsectorKeywords = domainConfig.subsectors[state.filters.subsector].keywords;
                    articles = articles.filter(a => {
                        const text = `${a.title || ''} ${a.summary || ''}`.toLowerCase();
                        return subsectorKeywords.some(kw => text.includes(kw.toLowerCase()));
                    });
                } else {
                    const domainKeywords = domainConfig.keywords;
                    articles = articles.filter(a => {
                        const text = `${a.title || ''} ${a.summary || ''}`.toLowerCase();
                        return domainKeywords.some(kw => text.includes(kw.toLowerCase()));
                    });
                }
            }
            
            // Trending filter
            if (state.filters.trendingIndex !== null && state.trendingTopics && state.trendingTopics[state.filters.trendingIndex]) {
                const topic = state.trendingTopics[state.filters.trendingIndex];
                const topicName = (topic.topic || topic.name || '').toLowerCase();
                
                if (topic.article_urls && topic.article_urls.length > 0) {
                    const articleUrls = new Set(topic.article_urls);
                    articles = articles.filter(a => articleUrls.has(a.url));
                } else if (topicName) {
                    articles = articles.filter(a => {
                        const text = `${a.title || ''} ${a.summary || ''}`.toLowerCase();
                        return text.includes(topicName);
                    });
                }
            }
            
            // Search filter
            if (state.filters.search && typeof searchArticles === 'function') {
                articles = searchArticles(articles, state.filters.search);
            }
            
            // New only filter
            if (state.filters.newOnly) {
                articles = articles.filter(a => a.isNew);
            }
            
            // ============ NEW: SOURCE TYPE FILTER ============
            if (state.filters.sourceType && state.filters.sourceType !== 'all') {
                articles = articles.filter(a => {
                    const type = getSourceType(a.source_name);
                    return type === state.filters.sourceType;
                });
            }
            
            // ============ UPDATE STATE AND RENDER ============
            state.filteredArticles = articles;
            state.totalPages = Math.ceil(articles.length / (typeof CONFIG !== 'undefined' ? CONFIG.pageSize : 25));
            state.currentPage = Math.min(state.currentPage, Math.max(1, state.totalPages));
            
            if (typeof renderArticles === 'function') renderArticles();
            if (typeof renderPagination === 'function') renderPagination();
            if (typeof updateFilterCount === 'function') updateFilterCount();
            if (typeof updateURLParams === 'function') updateURLParams();
            
            // Announce to screen readers
            if (typeof announce === 'function') {
                announce(`Showing ${articles.length} articles`);
            }
        };
        
        console.log('[SourceFilter] Patched applyFiltersAndRender');
    }
    
    // ==========================================================================
    // URL PERSISTENCE
    // ==========================================================================
    function updateURLWithSourceType() {
        const params = new URLSearchParams(window.location.search);
        
        if (state.filters.sourceType && state.filters.sourceType !== 'all') {
            params.set('source', state.filters.sourceType);
        } else {
            params.delete('source');
        }
        
        const newURL = params.toString() 
            ? `${window.location.pathname}?${params}` 
            : window.location.pathname;
        
        window.history.replaceState({}, '', newURL);
    }
    
    function loadSourceFilterFromURL() {
        const params = new URLSearchParams(window.location.search);
        const sourceType = params.get('source');
        
        if (sourceType && SOURCE_TYPES[sourceType]) {
            state.filters.sourceType = sourceType;
            
            // Update UI
            document.querySelectorAll('.source-pill').forEach(pill => {
                pill.classList.toggle('active', pill.dataset.sourceType === sourceType);
            });
            
            // Re-apply filters
            if (typeof applyFiltersAndRender === 'function') {
                setTimeout(() => applyFiltersAndRender(), 200);
            }
        }
    }
    
    // ==========================================================================
    // PATCH RESET FILTERS
    // ==========================================================================
    const originalResetFilters = window.resetFilters;
    if (typeof originalResetFilters === 'function') {
        window.resetFilters = function() {
            // Reset source type
            state.filters.sourceType = 'all';
            document.querySelectorAll('.source-pill').forEach(pill => {
                pill.classList.toggle('active', pill.dataset.sourceType === 'all');
            });
            
            // Call original
            originalResetFilters();
        };
    }
    
})();
