// policyradar-filters.js - Standalone filter UI
// Just add <script src="js/policyradar-filters.js"></script> to your index.html

(function() {
    'use strict';
    
    console.log('[PolicyRadar Filters] Loading...');

    // Wait for DOM and data to be ready
    function init() {
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setup);
        } else {
            setup();
        }
    }

    function setup() {
        console.log('[PolicyRadar Filters] Setting up...');
        
        // Wait a bit for other scripts to load data
        setTimeout(createFilterUI, 500);
    }

    // Source type classification
    const SOURCE_TYPES = {
        government: [
            'pib', 'pmo', 'mea', 'mod', 'mha', 'meity', 'dea', 'cbdt', 'cbic',
            'gst council', 'cabinet', 'niti aayog', 'digital india', 'india.gov',
            'mnre', 'moef', 'mohfw', 'ugc', 'drdo', 'election commission',
            'labour', 'epfo', 'esic', 'fssai', 'icmr', 'ayush', 'icar'
        ],
        regulator: [
            'rbi', 'sebi', 'irdai', 'pfrda', 'ibbi', 'cci', 'trai', 'cag',
            'cert-in', 'cpcb', 'ngt', 'bar council', 'nmc'
        ],
        media: [
            'economic times', 'mint', 'financial express', 'cnbc', 'hindu',
            'hindustan times', 'times of india', 'indian express', 'theprint',
            'ndtv', 'scroll', 'wire', 'quint', 'india today', 'outlook',
            'business today', 'medianama', 'moneycontrol', 'inc42'
        ],
        'think-tank': [
            'orf', 'observer research', 'carnegie', 'brookings', 'idsa',
            'vidhi', 'prs', 'daksh', 'ceew', 'teri', 'cse', 'climate policy',
            'cprindia', 'cpr', 'iff', 'sflc'
        ],
        legal: [
            'livelaw', 'bar and bench', 'supreme court observer', 'scc online',
            'legally india', 'taxguru', 'law insider', 'ipleaders'
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

    // Current filter state
    let currentFilter = 'all';

    function createFilterUI() {
        console.log('[PolicyRadar Filters] Creating UI...');

        // Check if already created
        if (document.getElementById('pr-filter-bar')) {
            console.log('[PolicyRadar Filters] Already exists');
            return;
        }

        // Create container
        const filterBar = document.createElement('div');
        filterBar.id = 'pr-filter-bar';
        filterBar.innerHTML = `
            <style>
                #pr-filter-bar {
                    padding: 12px 16px;
                    margin: 10px auto;
                    max-width: 1200px;
                    background: var(--card-bg, #f8f9fa);
                    border-radius: 8px;
                    display: flex;
                    flex-wrap: wrap;
                    gap: 8px;
                    align-items: center;
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                }
                [data-theme="dark"] #pr-filter-bar {
                    background: #1e293b;
                }
                #pr-filter-bar .pr-label {
                    font-size: 14px;
                    font-weight: 500;
                    color: #666;
                    margin-right: 4px;
                }
                [data-theme="dark"] #pr-filter-bar .pr-label {
                    color: #94a3b8;
                }
                #pr-filter-bar .pr-btn {
                    padding: 6px 12px;
                    font-size: 13px;
                    border: 1px solid #ddd;
                    border-radius: 16px;
                    background: white;
                    color: #333;
                    cursor: pointer;
                    transition: all 0.15s;
                }
                [data-theme="dark"] #pr-filter-bar .pr-btn {
                    background: #334155;
                    border-color: #475569;
                    color: #e2e8f0;
                }
                #pr-filter-bar .pr-btn:hover {
                    border-color: #2563eb;
                    color: #2563eb;
                }
                #pr-filter-bar .pr-btn.active {
                    background: #2563eb;
                    border-color: #2563eb;
                    color: white;
                }
                #pr-filter-bar .pr-stats {
                    margin-left: auto;
                    font-size: 12px;
                    color: #888;
                }
                @media (max-width: 600px) {
                    #pr-filter-bar .pr-btn {
                        padding: 5px 10px;
                        font-size: 12px;
                    }
                }
            </style>
            <span class="pr-label">Filter:</span>
            <button class="pr-btn active" data-filter="all">All</button>
            <button class="pr-btn" data-filter="government">🏛️ Govt</button>
            <button class="pr-btn" data-filter="regulator">📋 Regulators</button>
            <button class="pr-btn" data-filter="media">📰 Media</button>
            <button class="pr-btn" data-filter="think-tank">🧠 Think Tanks</button>
            <button class="pr-btn" data-filter="legal">⚖️ Legal</button>
            <span class="pr-stats" id="pr-stats"></span>
        `;

        // Find where to insert
        const header = document.querySelector('header') || 
                      document.querySelector('.header') ||
                      document.querySelector('nav') ||
                      document.querySelector('.nav');
        
        if (header) {
            header.parentNode.insertBefore(filterBar, header.nextSibling);
        } else {
            // Insert at top of body
            document.body.insertBefore(filterBar, document.body.firstChild);
        }

        // Add click handlers
        filterBar.querySelectorAll('.pr-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                filterBar.querySelectorAll('.pr-btn').forEach(b => b.classList.remove('active'));
                btn.classList.add('active');
                currentFilter = btn.dataset.filter;
                applyFilter();
            });
        });

        console.log('[PolicyRadar Filters] UI created successfully!');
        
        // Initial count
        updateStats();
    }

    function applyFilter() {
        console.log('[PolicyRadar Filters] Applying filter:', currentFilter);
        
        // Find all article cards
        const cards = document.querySelectorAll('.article-card, .card, [class*="article"], [class*="card"]');
        
        let shown = 0;
        let total = 0;

        cards.forEach(card => {
            // Try to find source name in the card
            const sourceEl = card.querySelector('.article-source, .source, [class*="source"]');
            const sourceName = sourceEl ? sourceEl.textContent : card.textContent;
            
            const type = getSourceType(sourceName);
            total++;

            if (currentFilter === 'all' || type === currentFilter) {
                card.style.display = '';
                shown++;
            } else {
                card.style.display = 'none';
            }
        });

        // Update stats
        const statsEl = document.getElementById('pr-stats');
        if (statsEl) {
            if (currentFilter === 'all') {
                statsEl.textContent = `${total} articles`;
            } else {
                statsEl.textContent = `${shown} of ${total}`;
            }
        }

        // Also try to filter category sections that are now empty
        document.querySelectorAll('.category-section, section').forEach(section => {
            const visibleCards = section.querySelectorAll('.article-card:not([style*="display: none"]), .card:not([style*="display: none"])');
            if (visibleCards.length === 0 && section.querySelector('.article-card, .card')) {
                section.style.display = 'none';
            } else {
                section.style.display = '';
            }
        });
    }

    function updateStats() {
        const cards = document.querySelectorAll('.article-card, .card, [class*="article"]');
        const statsEl = document.getElementById('pr-stats');
        if (statsEl && cards.length > 0) {
            statsEl.textContent = `${cards.length} articles`;
        }
    }

    // Start
    init();
})();
