// assets/js/main.js - PolicyRadar V7.3.1 Enhanced

document.addEventListener('DOMContentLoaded', () => {
    // DOM Elements
    const categoriesContainer = document.getElementById('categories-container');
    const loader = document.getElementById('loader');
    const errorMessage = document.getElementById('error-message');
    const lastUpdatedElem = document.getElementById('last-updated');
    const searchInput = document.getElementById('search-input');
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = document.getElementById('themeIcon');
    
    const DATA_URL = 'data/public_data.json';
    let allArticles = [];
    
    // ==========================================================================
    // FILTER STATE
    // ==========================================================================
    const state = {
        searchQuery: '',
        sourceType: 'all',
        dateFrom: null,
        dateTo: null,
        category: 'all'
    };

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
            'bsf', 'crpf', 'itbp', 'coast guard', 'navy', 'air force', 'army',
            'cbi', 'nia', 'ed', 'labour', 'epfo', 'esic', 'fssai', 'icmr',
            'aiims', 'cdsco', 'nmc', 'ayush', 'icar', 'forest survey', 'mygov'
        ],
        regulator: [
            'rbi', 'sebi', 'irdai', 'pfrda', 'ibbi', 'cci', 'trai', 'cag',
            'cert-in', 'cpcb', 'ngt', 'bar council', 'nmc'
        ],
        media: [
            'economic times', 'mint', 'financial express', 'cnbc', 'hindu',
            'hindustan times', 'times of india', 'indian express', 'theprint',
            'ndtv', 'scroll', 'wire', 'quint', 'india today', 'outlook',
            'business today', 'forbes', 'fortune', 'deccan', 'frontline',
            'caravan', 'week', 'diplomat', 'stratnews', 'inc42', 'yourstory',
            'medianama', 'the ken', 'epw', 'mongabay', 'down to earth'
        ],
        'think-tank': [
            'orf', 'observer research', 'carnegie', 'brookings', 'idsa', 'icrier',
            'nipfp', 'ncaer', 'cbga', 'cpr', 'cprindia', 'accountability',
            'vidhi', 'prs', 'daksh', 'ccs', 'centre for civil', 'gateway house',
            'delhi policy', 'takshashila', 'icwa', 'ceew', 'teri', 'cse',
            'climate policy', 'irade', 'nias', 'igidr', 'iff', 'sflc', 'cis'
        ],
        legal: [
            'livelaw', 'bar and bench', 'supreme court observer', 'scc online',
            'legally india', 'law times', 'taxguru', 'nyaaya', 'law insider',
            'ipleaders', 'lawctopus', 'legal bites', 'legal affairs'
        ]
    };

    function getSourceType(sourceName) {
        const name = (sourceName || '').toLowerCase();
        for (const [type, keywords] of Object.entries(SOURCE_TYPES)) {
            if (keywords.some(kw => name.includes(kw))) {
                return type;
            }
        }
        return 'other';
    }

    // ==========================================================================
    // URL FILTER PERSISTENCE
    // ==========================================================================
    function updateURLWithFilters() {
        const params = new URLSearchParams();
        if (state.searchQuery) params.set('q', state.searchQuery);
        if (state.sourceType !== 'all') params.set('source', state.sourceType);
        if (state.category !== 'all') params.set('cat', state.category);
        if (state.dateFrom) params.set('from', state.dateFrom);
        if (state.dateTo) params.set('to', state.dateTo);
        
        const newURL = window.location.pathname + 
            (params.toString() ? '?' + params.toString() : '');
        window.history.replaceState({}, '', newURL);
    }

    function restoreFiltersFromURL() {
        const params = new URLSearchParams(window.location.search);
        
        if (params.get('q')) {
            state.searchQuery = params.get('q');
            searchInput.value = state.searchQuery;
        }
        if (params.get('source')) {
            state.sourceType = params.get('source');
            setActiveSourceButton(state.sourceType);
        }
        if (params.get('cat')) {
            state.category = params.get('cat');
        }
        if (params.get('from')) {
            state.dateFrom = params.get('from');
            const dateFromInput = document.getElementById('date-from');
            if (dateFromInput) dateFromInput.value = state.dateFrom;
        }
        if (params.get('to')) {
            state.dateTo = params.get('to');
            const dateToInput = document.getElementById('date-to');
            if (dateToInput) dateToInput.value = state.dateTo;
        }
    }

    function setActiveSourceButton(type) {
        document.querySelectorAll('[data-source-type]').forEach(btn => {
            btn.classList.toggle('active', btn.dataset.sourceType === type);
        });
    }

    // ==========================================================================
    // FILTER UI INJECTION
    // ==========================================================================
    function injectFilterUI() {
        const searchContainer = document.querySelector('.search-container');
        if (!searchContainer) return;

        // Create filters wrapper
        const filtersDiv = document.createElement('div');
        filtersDiv.className = 'filters-wrapper';
        filtersDiv.innerHTML = `
            <div class="filter-row">
                <div class="filter-group" role="group" aria-label="Source Type">
                    <span class="filter-label">Source:</span>
                    <button class="filter-btn active" data-source-type="all">All</button>
                    <button class="filter-btn" data-source-type="government">
                        🏛️ Govt
                    </button>
                    <button class="filter-btn" data-source-type="regulator">
                        📋 Regulators
                    </button>
                    <button class="filter-btn" data-source-type="media">
                        📰 Media
                    </button>
                    <button class="filter-btn" data-source-type="think-tank">
                        🧠 Think Tanks
                    </button>
                    <button class="filter-btn" data-source-type="legal">
                        ⚖️ Legal
                    </button>
                </div>
                <div class="filter-group date-range">
                    <span class="filter-label">Date:</span>
                    <input type="date" id="date-from" class="date-input" 
                           aria-label="From date">
                    <span class="date-separator">to</span>
                    <input type="date" id="date-to" class="date-input" 
                           aria-label="To date">
                    <button class="filter-btn clear-dates" id="clear-dates" 
                            title="Clear dates">✕</button>
                </div>
            </div>
            <div class="filter-stats" id="filter-stats"></div>
        `;

        // Insert after search container
        searchContainer.parentNode.insertBefore(
            filtersDiv, 
            searchContainer.nextSibling
        );

        // Attach event listeners
        attachFilterListeners();
    }

    function attachFilterListeners() {
        // Source type buttons
        document.querySelectorAll('[data-source-type]').forEach(btn => {
            btn.addEventListener('click', () => {
                state.sourceType = btn.dataset.sourceType;
                setActiveSourceButton(state.sourceType);
                applyFilters();
            });
        });

        // Date inputs
        const dateFrom = document.getElementById('date-from');
        const dateTo = document.getElementById('date-to');
        
        if (dateFrom) {
            dateFrom.addEventListener('change', () => {
                state.dateFrom = dateFrom.value || null;
                applyFilters();
            });
        }
        if (dateTo) {
            dateTo.addEventListener('change', () => {
                state.dateTo = dateTo.value || null;
                applyFilters();
            });
        }

        // Clear dates button
        const clearDates = document.getElementById('clear-dates');
        if (clearDates) {
            clearDates.addEventListener('click', () => {
                state.dateFrom = null;
                state.dateTo = null;
                if (dateFrom) dateFrom.value = '';
                if (dateTo) dateTo.value = '';
                applyFilters();
            });
        }
    }

    // ==========================================================================
    // FILTERING LOGIC
    // ==========================================================================
    function applyFilters() {
        let filtered = [...allArticles];

        // Search query filter
        if (state.searchQuery) {
            const searchTerms = expandSearchQuery(state.searchQuery);
            filtered = filtered.filter(article => {
                const title = (article.title || '').toLowerCase();
                const source = (article.source_name || '').toLowerCase();
                const summary = (article.summary || '').toLowerCase();
                const category = (article.category || '').toLowerCase();
                
                return searchTerms.some(term => 
                    title.includes(term) ||
                    source.includes(term) ||
                    summary.includes(term) ||
                    category.includes(term)
                );
            });
        }

        // Source type filter
        if (state.sourceType !== 'all') {
            filtered = filtered.filter(article => {
                const type = getSourceType(article.source_name);
                return type === state.sourceType;
            });
        }

        // Date range filter
        if (state.dateFrom) {
            const fromDate = new Date(state.dateFrom);
            fromDate.setHours(0, 0, 0, 0);
            filtered = filtered.filter(article => 
                article.publication_date >= fromDate
            );
        }
        if (state.dateTo) {
            const toDate = new Date(state.dateTo);
            toDate.setHours(23, 59, 59, 999);
            filtered = filtered.filter(article => 
                article.publication_date <= toDate
            );
        }

        // Update URL and display
        updateURLWithFilters();
        updateFilterStats(filtered.length, allArticles.length);
        displayContent(filtered);
    }

    function expandSearchQuery(query) {
        const abbreviations = {
            'cpi': ['climate policy initiative', 'cpi india'],
            'rbi': ['reserve bank', 'rbi'],
            'sebi': ['securities and exchange board', 'sebi'],
            'cci': ['competition commission', 'cci'],
            'trai': ['telecom regulatory', 'trai'],
            'niti': ['niti aayog'],
            'prs': ['prs legislative', 'prs india', 'prsindia'],
            'ceew': ['council on energy', 'ceew'],
            'iff': ['internet freedom foundation'],
            'cpr': ['centre for policy research', 'cprindia'],
            'orf': ['observer research foundation'],
            'teri': ['the energy and resources institute'],
        };
        
        let terms = [query.toLowerCase()];
        for (const [abbr, expansions] of Object.entries(abbreviations)) {
            if (query.toLowerCase().includes(abbr)) {
                terms = terms.concat(expansions);
            }
        }
        return terms;
    }

    function updateFilterStats(shown, total) {
        const statsEl = document.getElementById('filter-stats');
        if (!statsEl) return;
        
        if (shown === total) {
            statsEl.textContent = `Showing all ${total} articles`;
        } else {
            statsEl.textContent = `Showing ${shown} of ${total} articles`;
        }
        statsEl.className = 'filter-stats' + (shown < total ? ' filtered' : '');
    }

    // ==========================================================================
    // DATA FETCHING & DISPLAY
    // ==========================================================================
    async function fetchData() {
        try {
            // Fetch status first
            const statusResponse = await fetch(
                `data/status.json?v=${Date.now()}`
            );
            if (statusResponse.ok) {
                const status = await statusResponse.json();
                updateLastUpdatedDisplay(status.last_run_human);
            }
            
            // Then fetch articles data
            const response = await fetch(`${DATA_URL}?v=${Date.now()}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            allArticles = data.articles.map(article => ({
                ...article,
                publication_date: new Date(article.publication_date),
                source_type: getSourceType(article.source_name)
            }));
            
            // Inject filter UI after data loads
            injectFilterUI();
            
            // Restore filters from URL
            restoreFiltersFromURL();
            
            // Apply filters (this will also display)
            applyFilters();
            
            updateMetadata(data.last_updated);
            loader.style.display = 'none';
        } catch (error) {
            console.error("Failed to fetch policy data:", error);
            loader.style.display = 'none';
            errorMessage.style.display = 'block';
        }
    }

    function updateLastUpdatedDisplay(lastUpdated) {
        const elem = document.getElementById('last-updated');
        if (elem) {
            elem.textContent = `Last Updated: ${lastUpdated}`;
        }
    }

    function displayContent(articles) {
        categoriesContainer.innerHTML = '';
        if (articles.length === 0) {
            categoriesContainer.innerHTML = `
                <div class="no-results">
                    <p>No articles match your filters.</p>
                    <button class="filter-btn" onclick="location.href=location.pathname">
                        Clear all filters
                    </button>
                </div>`;
            return;
        }

        // Group articles by category
        const articlesByCategory = articles.reduce((acc, article) => {
            const category = article.category || article.source_name;
            if (!acc[category]) {
                acc[category] = [];
            }
            acc[category].push(article);
            return acc;
        }, {});

        // Sort categories by article count (descending)
        const sortedCategories = Object.keys(articlesByCategory)
            .sort((a, b) => articlesByCategory[b].length - articlesByCategory[a].length);

        sortedCategories.forEach(category => {
            const categorySection = document.createElement('section');
            categorySection.className = 'category-section';

            const articlesHtml = articlesByCategory[category]
                .slice(0, 20)  // Limit per category for performance
                .map(article => createArticleCard(article))
                .join('');

            const count = articlesByCategory[category].length;
            const showMore = count > 20 ? 
                `<p class="show-more">+ ${count - 20} more articles</p>` : '';

            categorySection.innerHTML = `
                <h2 class="category-title">
                    <span>${getCategoryIcon(category)}</span>
                    ${category}
                    <span class="category-count">${count}</span>
                </h2>
                <div class="article-grid">
                    ${articlesHtml}
                </div>
                ${showMore}
            `;
            categoriesContainer.appendChild(categorySection);
        });
    }

    function createArticleCard(article) {
        const publishedDate = article.publication_date.toLocaleDateString('en-GB', {
            day: 'numeric', month: 'short', year: 'numeric'
        });
        
        const sourceType = article.source_type || getSourceType(article.source_name);
        const sourceIcon = {
            'government': '🏛️',
            'regulator': '📋',
            'media': '📰',
            'think-tank': '🧠',
            'legal': '⚖️',
            'other': '📄'
        }[sourceType] || '📄';

        const priorityClass = article.relevance_score >= 0.7 ? 'high-priority' : 
                             article.relevance_score >= 0.5 ? 'medium-priority' : '';

        const summary = article.summary || article.title;

        return `
            <div class="article-card ${priorityClass}" data-source-type="${sourceType}">
                <div class="article-header">
                    <span class="article-source" title="${sourceType}">
                        ${sourceIcon} ${article.source_name}
                    </span>
                    <span class="article-date">${publishedDate}</span>
                </div>
                <h3 class="article-title">
                    <a href="${article.url}" target="_blank" 
                       rel="noopener noreferrer">${article.title}</a>
                </h3>
                <p class="article-summary">${summary.substring(0, 150)}${summary.length > 150 ? '...' : ''}</p>
            </div>
        `;
    }

    function updateMetadata(lastUpdatedISO) {
        const lastUpdatedDate = new Date(lastUpdatedISO);
        lastUpdatedElem.textContent = 
            `Last Updated: ${lastUpdatedDate.toLocaleString('en-GB')}`;
        const yearEl = document.getElementById('year');
        if (yearEl) yearEl.textContent = new Date().getFullYear();
    }

    function handleSearch() {
        state.searchQuery = searchInput.value.toLowerCase().trim();
        applyFilters();
    }

    function getCategoryIcon(category) {
        const categoryLower = (category || '').toLowerCase();
        
        // Specific category icons
        const iconMap = {
            'economic': '💰',
            'finance': '💰',
            'governance': '🏛️',
            'constitutional': '⚖️',
            'legal': '⚖️',
            'technology': '💻',
            'defence': '🛡️',
            'security': '🛡️',
            'environment': '🌿',
            'climate': '🌿',
            'healthcare': '🏥',
            'health': '🏥',
            'education': '📚',
            'foreign': '🌐',
            'trade': '📊',
            'infrastructure': '🏗️',
            'energy': '⚡',
            'agriculture': '🌾',
            'social': '👥',
            'politics': '🗳️'
        };
        
        for (const [key, icon] of Object.entries(iconMap)) {
            if (categoryLower.includes(key)) return icon;
        }
        
        // Hash-based fallback
        let hash = 0;
        for (let i = 0; i < category.length; i++) {
            hash = category.charCodeAt(i) + ((hash << 5) - hash);
        }
        const emojis = ['📄', '📑', '📈', '⚖️', '🏛️', '🌐', '🔬', '💡'];
        return emojis[Math.abs(hash) % emojis.length];
    }
    
    function toggleTheme() {
        const body = document.body;
        const currentTheme = body.getAttribute('data-theme');
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        body.setAttribute('data-theme', newTheme);
        themeIcon.textContent = newTheme === 'dark' ? '☀️' : '🌙';
        localStorage.setItem('theme', newTheme);
    }

    function loadTheme() {
        const savedTheme = localStorage.getItem('theme') || 'light';
        document.body.setAttribute('data-theme', savedTheme);
        themeIcon.textContent = savedTheme === 'dark' ? '☀️' : '🌙';
    }

    // ==========================================================================
    // EVENT LISTENERS
    // ==========================================================================
    searchInput.addEventListener('input', handleSearch);
    themeToggle.addEventListener('click', toggleTheme);

    // ==========================================================================
    // INITIAL LOAD
    // ==========================================================================
    loadTheme();
    fetchData();
});
