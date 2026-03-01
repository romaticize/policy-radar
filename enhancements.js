/**
 * PolicyRadar v6.2 Enhancements Module
 * 
 * This module adds:
 * - Virtual Scrolling (IntersectionObserver-based)
 * - Newsletter Export
 * - Reading List
 * - Service Worker Registration
 * 
 * Include after the main index.html scripts:
 *   <script src="enhancements.js"></script>
 */

(function() {
    'use strict';
    
    // =========================================
    // CONFIGURATION
    // =========================================
    const ENHANCEMENTS_CONFIG = {
        virtualScroll: {
            enabled: true,
            batchSize: 25,          // Articles to render per batch
            bufferSize: 5,          // Batches to keep in DOM above/below viewport
            scrollThreshold: 200,   // Pixels from edge to trigger load
        },
        readingList: {
            storageKey: 'policyradar_reading_list',
            maxItems: 100,
        },
        newsletter: {
            maxArticles: 25,
            format: 'markdown',     // 'markdown' or 'plain'
        },
    };
    
    // =========================================
    // VIRTUAL SCROLLING
    // =========================================
    const VirtualScroll = {
        state: {
            renderedRange: { start: 0, end: 0 },
            itemHeight: 150,        // Estimated, will be measured
            containerHeight: 0,
            totalItems: 0,
            isActive: false,
        },
        
        init() {
            if (!ENHANCEMENTS_CONFIG.virtualScroll.enabled) return;
            
            const container = document.getElementById('articles-grid');
            if (!container) return;
            
            // Create sentinel elements for infinite scroll
            this.topSentinel = document.createElement('div');
            this.topSentinel.className = 'virtual-sentinel top-sentinel';
            this.topSentinel.style.cssText = 'height: 1px; width: 100%; position: absolute; top: 0;';
            
            this.bottomSentinel = document.createElement('div');
            this.bottomSentinel.className = 'virtual-sentinel bottom-sentinel';
            this.bottomSentinel.style.cssText = 'height: 1px; width: 100%;';
            
            // Set up intersection observer
            this.observer = new IntersectionObserver(
                (entries) => this.handleIntersection(entries),
                {
                    root: null,
                    rootMargin: `${ENHANCEMENTS_CONFIG.virtualScroll.scrollThreshold}px`,
                    threshold: 0,
                }
            );
            
            // Measure item height from first rendered item
            requestAnimationFrame(() => {
                const firstArticle = container.querySelector('.article-card');
                if (firstArticle) {
                    const rect = firstArticle.getBoundingClientRect();
                    this.state.itemHeight = rect.height + 16; // Include gap
                }
            });
            
            this.state.isActive = true;
            console.log('[VirtualScroll] Initialized');
        },
        
        handleIntersection(entries) {
            for (const entry of entries) {
                if (!entry.isIntersecting) continue;
                
                if (entry.target.classList.contains('bottom-sentinel')) {
                    this.loadMore('down');
                } else if (entry.target.classList.contains('top-sentinel')) {
                    this.loadMore('up');
                }
            }
        },
        
        loadMore(direction) {
            const { batchSize } = ENHANCEMENTS_CONFIG.virtualScroll;
            const articles = window.state?.filteredArticles || [];
            
            if (direction === 'down') {
                const newEnd = Math.min(this.state.renderedRange.end + batchSize, articles.length);
                if (newEnd > this.state.renderedRange.end) {
                    this.renderBatch(this.state.renderedRange.end, newEnd, 'append');
                    this.state.renderedRange.end = newEnd;
                }
            } else {
                const newStart = Math.max(this.state.renderedRange.start - batchSize, 0);
                if (newStart < this.state.renderedRange.start) {
                    this.renderBatch(newStart, this.state.renderedRange.start, 'prepend');
                    this.state.renderedRange.start = newStart;
                }
            }
        },
        
        renderBatch(start, end, mode = 'append') {
            const articles = window.state?.filteredArticles || [];
            const container = document.getElementById('articles-grid');
            if (!container) return;
            
            const fragment = document.createDocumentFragment();
            
            for (let i = start; i < end; i++) {
                const article = articles[i];
                if (!article) continue;
                
                const card = this.createArticleCard(article, i);
                fragment.appendChild(card);
            }
            
            if (mode === 'prepend') {
                container.insertBefore(fragment, container.firstChild);
            } else {
                container.appendChild(fragment);
            }
        },
        
        createArticleCard(article, index) {
            const template = document.createElement('template');
            // Re-use existing renderArticleCard if available
            if (typeof window.renderArticleCard === 'function') {
                template.innerHTML = window.renderArticleCard(article, index);
            } else {
                template.innerHTML = this.fallbackRender(article, index);
            }
            return template.content.firstElementChild;
        },
        
        fallbackRender(article, index) {
            const priority = article.priority_class || 'medium';
            const isNew = article.isNew ? 'new' : '';
            const inReadingList = ReadingList.has(article.url);
            const sourceCount = article.source_count || 1;
            const isMultiSource = sourceCount > 1;
            const isBreaking = article.is_breaking;

            return `
                <article class="article-card ${priority} ${isNew} ${isMultiSource ? 'multi-source' : ''}"
                         data-index="${index}"
                         data-url="${this.escape(article.url)}"
                         data-source-count="${sourceCount}"
                         tabindex="0">
                    <div class="article-header">
                        <div class="article-meta">
                            <a href="${this.escape(article.url)}" class="article-source" target="_blank" rel="noopener">
                                ${this.escape(article.source_name || 'Unknown')}
                            </a>
                            ${isMultiSource ? `
                                <span class="source-count-badge" title="Covered by ${sourceCount} sources">
                                    +${sourceCount - 1} sources
                                </span>
                            ` : ''}
                            <span class="article-separator">•</span>
                            <time class="article-date">${this.formatDate(article.publication_date)}</time>
                        </div>
                        <div class="article-badges">
                            ${isBreaking ? `<span class="breaking-badge">Breaking</span>` : ''}
                            ${priority !== 'medium' ? `<span class="article-priority">${priority}</span>` : ''}
                        </div>
                    </div>
                    <h3 class="article-title">
                        <a href="${this.escape(article.url)}" target="_blank" rel="noopener">
                            ${this.escape(article.title)}
                        </a>
                    </h3>
                    <div class="article-footer">
                        <span class="article-category">${this.escape(article.category || 'Governance')}</span>
                        <div class="article-actions">
                            <button class="article-action ${inReadingList ? 'active' : ''}"
                                    onclick="ReadingList.toggle('${this.escape(article.url)}')"
                                    title="${inReadingList ? 'Remove from Reading List' : 'Add to Reading List'}">
                                ${inReadingList ? '🔖' : '📑'}
                            </button>
                            <button class="article-action"
                                    onclick="shareArticle(event, '${this.escape(article.url)}', '${this.escape(article.title)}')"
                                    title="Share">
                                📤
                            </button>
                        </div>
                    </div>
                </article>
            `;
        },
        
        escape(str) {
            if (!str) return '';
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        },
        
        formatDate(dateStr) {
            if (!dateStr) return '';
            try {
                return new Date(dateStr).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
            } catch {
                return dateStr.substring(0, 10);
            }
        },
        
        reset() {
            this.state.renderedRange = { start: 0, end: 0 };
        },
        
        destroy() {
            if (this.observer) {
                this.observer.disconnect();
            }
            this.state.isActive = false;
        },
    };
    
    // =========================================
    // READING LIST
    // =========================================
    const ReadingList = {
        items: new Map(), // url -> article data
        
        init() {
            this.load();
            this.renderButton();
            console.log('[ReadingList] Initialized with', this.items.size, 'items');
        },
        
        load() {
            try {
                const stored = localStorage.getItem(ENHANCEMENTS_CONFIG.readingList.storageKey);
                if (stored) {
                    const parsed = JSON.parse(stored);
                    this.items = new Map(Object.entries(parsed));
                }
            } catch (e) {
                console.warn('[ReadingList] Failed to load:', e);
            }
        },
        
        save() {
            try {
                const obj = Object.fromEntries(this.items);
                localStorage.setItem(ENHANCEMENTS_CONFIG.readingList.storageKey, JSON.stringify(obj));
            } catch (e) {
                console.warn('[ReadingList] Failed to save:', e);
            }
        },
        
        add(article) {
            if (!article?.url) return false;
            if (this.items.size >= ENHANCEMENTS_CONFIG.readingList.maxItems) {
                // Remove oldest
                const oldest = this.items.keys().next().value;
                this.items.delete(oldest);
            }
            
            this.items.set(article.url, {
                title: article.title,
                source: article.source_name,
                date: article.publication_date,
                category: article.category,
                addedAt: new Date().toISOString(),
            });
            
            this.save();
            this.updateUI();
            this.showToast('Added to Reading List');
            return true;
        },
        
        remove(url) {
            if (this.items.delete(url)) {
                this.save();
                this.updateUI();
                this.showToast('Removed from Reading List');
                return true;
            }
            return false;
        },
        
        toggle(url) {
            if (this.has(url)) {
                return this.remove(url);
            } else {
                // Find article data
                const articles = window.state?.allArticles || [];
                const article = articles.find(a => a.url === url);
                if (article) {
                    return this.add(article);
                }
            }
            return false;
        },
        
        has(url) {
            return this.items.has(url);
        },
        
        getAll() {
            return Array.from(this.items.entries()).map(([url, data]) => ({
                url,
                ...data,
            }));
        },
        
        clear() {
            this.items.clear();
            this.save();
            this.updateUI();
            this.showToast('Reading List cleared');
        },
        
        renderButton() {
            // Add reading list button to header actions
            const headerActions = document.querySelector('.header-actions');
            if (!headerActions) return;
            
            const btn = document.createElement('button');
            btn.id = 'reading-list-btn';
            btn.className = 'icon-btn';
            btn.setAttribute('aria-label', 'Reading List');
            btn.setAttribute('title', 'Reading List (r)');
            btn.innerHTML = `
                <span class="icon">📚</span>
                <span class="reading-list-badge" id="reading-list-badge" style="display: none;">0</span>
            `;
            btn.onclick = () => this.showModal();
            
            // Insert before theme toggle if exists
            const themeBtn = headerActions.querySelector('#theme-toggle');
            if (themeBtn) {
                headerActions.insertBefore(btn, themeBtn);
            } else {
                headerActions.appendChild(btn);
            }
            
            this.updateUI();
        },
        
        updateUI() {
            const badge = document.getElementById('reading-list-badge');
            if (badge) {
                const count = this.items.size;
                badge.textContent = count;
                badge.style.display = count > 0 ? 'flex' : 'none';
            }
            
            // Update article card buttons
            document.querySelectorAll('.article-card').forEach(card => {
                const url = card.dataset.url;
                const btn = card.querySelector('.article-action[onclick*="ReadingList"]');
                if (btn && url) {
                    const inList = this.has(url);
                    btn.classList.toggle('active', inList);
                    btn.innerHTML = inList ? '🔖' : '📑';
                    btn.title = inList ? 'Remove from Reading List' : 'Add to Reading List';
                }
            });
        },
        
        showModal() {
            // Remove existing modal
            document.getElementById('reading-list-modal')?.remove();
            
            const items = this.getAll();
            
            const modal = document.createElement('div');
            modal.id = 'reading-list-modal';
            modal.className = 'modal-overlay';
            modal.innerHTML = `
                <div class="modal" role="dialog" aria-modal="true" aria-labelledby="reading-list-title">
                    <div class="modal-header">
                        <h2 id="reading-list-title">📚 Reading List (${items.length})</h2>
                        <button class="modal-close" onclick="document.getElementById('reading-list-modal').remove()" aria-label="Close">×</button>
                    </div>
                    <div class="modal-body">
                        ${items.length === 0 ? `
                            <div class="empty-state" style="padding: 2rem; text-align: center;">
                                <p style="color: var(--text-muted);">Your reading list is empty.</p>
                                <p style="color: var(--text-muted); font-size: 0.875rem; margin-top: 0.5rem;">
                                    Click the 📑 button on any article to save it for later.
                                </p>
                            </div>
                        ` : `
                            <div class="reading-list-items">
                                ${items.map(item => `
                                    <div class="reading-list-item">
                                        <div class="reading-list-item-content">
                                            <a href="${this.escape(item.url)}" target="_blank" rel="noopener" class="reading-list-item-title">
                                                ${this.escape(item.title)}
                                            </a>
                                            <div class="reading-list-item-meta">
                                                ${this.escape(item.source)} • ${item.category || 'Governance'}
                                            </div>
                                        </div>
                                        <button class="reading-list-item-remove" onclick="ReadingList.remove('${this.escape(item.url)}')" title="Remove">×</button>
                                    </div>
                                `).join('')}
                            </div>
                            <div class="modal-footer" style="margin-top: 1rem; display: flex; gap: 0.5rem; justify-content: flex-end;">
                                <button class="btn btn-secondary" onclick="NewsletterExport.exportReadingList()">
                                    📋 Export for Newsletter
                                </button>
                                <button class="btn btn-danger" onclick="ReadingList.clear(); document.getElementById('reading-list-modal').remove();">
                                    🗑️ Clear All
                                </button>
                            </div>
                        `}
                    </div>
                </div>
            `;
            
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.remove();
            });
            
            document.body.appendChild(modal);
            modal.classList.add('visible');
            modal.querySelector('.modal-close').focus();
        },
        
        escape(str) {
            if (!str) return '';
            const div = document.createElement('div');
            div.textContent = str;
            return div.innerHTML;
        },
        
        showToast(message) {
            if (typeof window.showToast === 'function') {
                window.showToast(message);
            } else {
                console.log('[ReadingList]', message);
            }
        },
    };
    
    // =========================================
    // NEWSLETTER EXPORT (Hidden - keyboard shortcut only: 'n')
    // =========================================
    const NewsletterExport = {
        init() {
            // No visible button - access via 'n' keyboard shortcut only
            console.log('[NewsletterExport] Ready (press "n" to access)');
        },
        
        showModal() {
            // Remove existing modal
            document.getElementById('newsletter-modal')?.remove();
            
            const articles = window.state?.filteredArticles || [];
            const topArticles = articles.slice(0, ENHANCEMENTS_CONFIG.newsletter.maxArticles);
            
            const modal = document.createElement('div');
            modal.id = 'newsletter-modal';
            modal.className = 'modal-overlay';
            modal.innerHTML = `
                <div class="modal" role="dialog" aria-modal="true" aria-labelledby="newsletter-title" style="max-width: 700px;">
                    <div class="modal-header">
                        <h2 id="newsletter-title">📰 Export for Newsletter</h2>
                        <button class="modal-close" onclick="document.getElementById('newsletter-modal').remove()" aria-label="Close">×</button>
                    </div>
                    <div class="modal-body">
                        <p style="color: var(--text-muted); margin-bottom: 1rem;">
                            Export the top ${topArticles.length} articles for use with Claude or other AI tools to generate your newsletter.
                        </p>
                        
                        <div style="margin-bottom: 1rem;">
                            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer;">
                                <input type="radio" name="export-format" value="markdown" checked>
                                <span>Markdown (recommended for Claude)</span>
                            </label>
                            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; margin-top: 0.5rem;">
                                <input type="radio" name="export-format" value="plain">
                                <span>Plain Text</span>
                            </label>
                            <label style="display: flex; align-items: center; gap: 0.5rem; cursor: pointer; margin-top: 0.5rem;">
                                <input type="radio" name="export-format" value="json">
                                <span>JSON (for programmatic use)</span>
                            </label>
                        </div>
                        
                        <div class="modal-footer" style="display: flex; gap: 0.5rem;">
                            <button class="btn btn-primary" onclick="NewsletterExport.copyToClipboard()">
                                📋 Copy to Clipboard
                            </button>
                            <button class="btn btn-secondary" onclick="NewsletterExport.download()">
                                💾 Download File
                            </button>
                        </div>
                        
                        <details style="margin-top: 1rem;">
                            <summary style="cursor: pointer; color: var(--accent-primary);">Preview export</summary>
                            <pre id="newsletter-preview" style="
                                margin-top: 0.5rem;
                                padding: 1rem;
                                background: var(--bg-secondary);
                                border-radius: 8px;
                                font-size: 0.75rem;
                                overflow: auto;
                                max-height: 300px;
                                white-space: pre-wrap;
                            ">${this.escape(this.generateExport('markdown'))}</pre>
                        </details>
                    </div>
                </div>
            `;
            
            // Update preview on format change
            modal.querySelectorAll('input[name="export-format"]').forEach(input => {
                input.addEventListener('change', () => {
                    const preview = modal.querySelector('#newsletter-preview');
                    if (preview) {
                        preview.textContent = this.generateExport(input.value);
                    }
                });
            });
            
            modal.addEventListener('click', (e) => {
                if (e.target === modal) modal.remove();
            });
            
            document.body.appendChild(modal);
            modal.classList.add('visible');
            modal.querySelector('.modal-close').focus();
        },
        
        generateExport(format = 'markdown') {
            const articles = window.state?.filteredArticles || [];
            const topArticles = articles.slice(0, ENHANCEMENTS_CONFIG.newsletter.maxArticles);
            const today = new Date().toLocaleDateString('en-IN', { 
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' 
            });
            
            if (format === 'json') {
                return JSON.stringify({
                    generated: new Date().toISOString(),
                    count: topArticles.length,
                    articles: topArticles.map(a => ({
                        title: a.title,
                        source: a.source_name,
                        url: a.url,
                        date: a.publication_date,
                        category: a.category,
                        priority: a.priority_class,
                        summary: a.summary,
                    })),
                }, null, 2);
            }
            
            if (format === 'plain') {
                let output = `POLICYRADAR DAILY BRIEFING\n`;
                output += `${today}\n`;
                output += `${'='.repeat(50)}\n\n`;
                output += `${topArticles.length} Top Policy Articles\n\n`;
                
                // Group by category
                const byCategory = this.groupByCategory(topArticles);
                
                for (const [category, catArticles] of Object.entries(byCategory)) {
                    output += `\n${category.toUpperCase()}\n${'-'.repeat(30)}\n\n`;
                    
                    for (const article of catArticles) {
                        const priority = article.priority_class === 'critical' ? '[!!] ' : 
                                        article.priority_class === 'high' ? '[!] ' : '';
                        output += `${priority}${article.title}\n`;
                        output += `  Source: ${article.source_name}\n`;
                        output += `  URL: ${article.url}\n`;
                        if (article.summary) {
                            output += `  Summary: ${article.summary.substring(0, 200)}...\n`;
                        }
                        output += `\n`;
                    }
                }
                
                return output;
            }
            
            // Default: Markdown
            let output = `# PolicyRadar Daily Briefing\n\n`;
            output += `**${today}** | ${topArticles.length} articles\n\n`;
            output += `---\n\n`;
            
            // Summary stats
            const critical = topArticles.filter(a => a.priority_class === 'critical').length;
            const high = topArticles.filter(a => a.priority_class === 'high').length;
            
            output += `## Quick Stats\n\n`;
            output += `- 🔴 Critical: ${critical}\n`;
            output += `- 🟠 High Priority: ${high}\n`;
            output += `- 📰 Total: ${topArticles.length}\n\n`;
            
            // Group by category
            const byCategory = this.groupByCategory(topArticles);
            
            for (const [category, catArticles] of Object.entries(byCategory)) {
                output += `## ${category}\n\n`;
                
                for (const article of catArticles) {
                    const priority = article.priority_class === 'critical' ? '🔴 ' : 
                                    article.priority_class === 'high' ? '🟠 ' : '';
                    output += `### ${priority}${article.title}\n\n`;
                    output += `**Source:** ${article.source_name} | **Date:** ${this.formatDate(article.publication_date)}\n\n`;
                    if (article.summary) {
                        output += `> ${article.summary}\n\n`;
                    }
                    output += `[Read Article](${article.url})\n\n`;
                    output += `---\n\n`;
                }
            }
            
            output += `\n*Generated by PolicyRadar - policyradar.in*\n`;
            
            return output;
        },
        
        exportReadingList() {
            const items = ReadingList.getAll();
            if (items.length === 0) {
                this.showToast('Reading list is empty');
                return;
            }
            
            const today = new Date().toLocaleDateString('en-IN', { 
                weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' 
            });
            
            let output = `# My Policy Reading List\n\n`;
            output += `**${today}** | ${items.length} saved articles\n\n`;
            output += `---\n\n`;
            
            for (const item of items) {
                output += `### ${item.title}\n\n`;
                output += `**Source:** ${item.source} | **Category:** ${item.category || 'Governance'}\n\n`;
                output += `[Read Article](${item.url})\n\n`;
                output += `---\n\n`;
            }
            
            navigator.clipboard.writeText(output).then(() => {
                this.showToast('Reading list copied to clipboard');
            }).catch(() => {
                this.showToast('Failed to copy');
            });
        },
        
        copyToClipboard() {
            const format = document.querySelector('input[name="export-format"]:checked')?.value || 'markdown';
            const content = this.generateExport(format);
            
            navigator.clipboard.writeText(content).then(() => {
                this.showToast('Copied to clipboard! Paste into Claude to generate your newsletter.');
                document.getElementById('newsletter-modal')?.remove();
            }).catch(() => {
                this.showToast('Failed to copy');
            });
        },
        
        download() {
            const format = document.querySelector('input[name="export-format"]:checked')?.value || 'markdown';
            const content = this.generateExport(format);
            const today = new Date().toISOString().split('T')[0];
            
            const ext = format === 'json' ? 'json' : format === 'plain' ? 'txt' : 'md';
            const filename = `policyradar-briefing-${today}.${ext}`;
            const mimeType = format === 'json' ? 'application/json' : 'text/plain';
            
            const blob = new Blob([content], { type: mimeType });
            const url = URL.createObjectURL(blob);
            
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            a.click();
            
            URL.revokeObjectURL(url);
            this.showToast(`Downloaded ${filename}`);
        },
        
        groupByCategory(articles) {
            const groups = {};
            for (const article of articles) {
                const cat = article.category || 'Governance';
                if (!groups[cat]) groups[cat] = [];
                groups[cat].push(article);
            }
            return groups;
        },
        
        formatDate(dateStr) {
            if (!dateStr) return '';
            try {
                return new Date(dateStr).toLocaleDateString('en-IN', { month: 'short', day: 'numeric' });
            } catch {
                return dateStr.substring(0, 10);
            }
        },
        
        escape(str) {
            if (!str) return '';
            return str.replace(/</g, '&lt;').replace(/>/g, '&gt;');
        },
        
        showToast(message) {
            if (typeof window.showToast === 'function') {
                window.showToast(message);
            } else {
                console.log('[NewsletterExport]', message);
            }
        },
    };
    
    // =========================================
    // SERVICE WORKER REGISTRATION
    // =========================================
    const ServiceWorkerManager = {
        init() {
            if ('serviceWorker' in navigator) {
                window.addEventListener('load', () => {
                    navigator.serviceWorker.register('/sw.js')
                        .then(reg => {
                            console.log('[SW] Registered:', reg.scope);
                            
                            // Check for updates
                            reg.addEventListener('updatefound', () => {
                                const newWorker = reg.installing;
                                newWorker.addEventListener('statechange', () => {
                                    if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                                        this.showUpdateNotification();
                                    }
                                });
                            });
                        })
                        .catch(err => {
                            console.warn('[SW] Registration failed:', err);
                        });
                });
            }
        },
        
        showUpdateNotification() {
            const banner = document.createElement('div');
            banner.className = 'update-banner';
            banner.innerHTML = `
                <span>🔄 A new version is available!</span>
                <button onclick="location.reload()">Refresh</button>
                <button onclick="this.parentElement.remove()">Dismiss</button>
            `;
            banner.style.cssText = `
                position: fixed;
                bottom: 20px;
                left: 50%;
                transform: translateX(-50%);
                background: var(--accent-primary);
                color: white;
                padding: 0.75rem 1rem;
                border-radius: 8px;
                display: flex;
                align-items: center;
                gap: 1rem;
                z-index: 10000;
                box-shadow: var(--shadow-lg);
            `;
            document.body.appendChild(banner);
        },
    };
    
    // =========================================
    // KEYBOARD SHORTCUTS EXTENSION
    // =========================================
    const KeyboardExtensions = {
        init() {
            document.addEventListener('keydown', (e) => {
                // Ignore if typing in input
                if (e.target.matches('input, textarea, select')) return;
                if (e.ctrlKey || e.metaKey || e.altKey) return;
                
                switch (e.key.toLowerCase()) {
                    case 'r':
                        e.preventDefault();
                        ReadingList.showModal();
                        break;
                    case 'n':
                        e.preventDefault();
                        NewsletterExport.showModal();
                        break;
                    case 'b':
                        e.preventDefault();
                        // Toggle reading list for focused article
                        const focused = document.querySelector('.article-card.keyboard-focus');
                        if (focused) {
                            const url = focused.dataset.url || focused.querySelector('.article-title a')?.href;
                            if (url) ReadingList.toggle(url);
                        }
                        break;
                }
            });
            
            // Update shortcuts help modal if it exists
            this.updateShortcutsHelp();
        },
        
        updateShortcutsHelp() {
            const modal = document.getElementById('shortcuts-modal');
            if (!modal) return;
            
            const grid = modal.querySelector('.shortcuts-grid');
            if (!grid) return;
            
            // Add new shortcuts (newsletter intentionally hidden)
            const newShortcuts = `
                <div class="shortcut-item">
                    <kbd>r</kbd>
                    <span>Open Reading List</span>
                </div>
                <div class="shortcut-item">
                    <kbd>b</kbd>
                    <span>Toggle bookmark (focused article)</span>
                </div>
            `;
            
            grid.insertAdjacentHTML('beforeend', newShortcuts);
        },
    };
    
    // =========================================
    // CSS INJECTION
    // =========================================
    const StyleInjector = {
        init() {
            const styles = document.createElement('style');
            styles.textContent = `
                /* Reading List Badge */
                .reading-list-badge {
                    position: absolute;
                    top: -4px;
                    right: -4px;
                    background: var(--critical-color);
                    color: white;
                    font-size: 0.625rem;
                    font-weight: 700;
                    min-width: 16px;
                    height: 16px;
                    border-radius: 8px;
                    display: flex;
                    align-items: center;
                    justify-content: center;
                    padding: 0 4px;
                }
                
                .icon-btn {
                    position: relative;
                }
                
                /* Reading List Modal */
                .reading-list-items {
                    max-height: 400px;
                    overflow-y: auto;
                }
                
                .reading-list-item {
                    display: flex;
                    align-items: flex-start;
                    gap: 0.75rem;
                    padding: 0.75rem;
                    border-bottom: 1px solid var(--border-color);
                }
                
                .reading-list-item:last-child {
                    border-bottom: none;
                }
                
                .reading-list-item-content {
                    flex: 1;
                    min-width: 0;
                }
                
                .reading-list-item-title {
                    font-weight: 500;
                    color: var(--text-primary);
                    text-decoration: none;
                    display: block;
                    margin-bottom: 0.25rem;
                }
                
                .reading-list-item-title:hover {
                    color: var(--accent-primary);
                }
                
                .reading-list-item-meta {
                    font-size: 0.75rem;
                    color: var(--text-muted);
                }
                
                .reading-list-item-remove {
                    background: none;
                    border: none;
                    color: var(--text-muted);
                    font-size: 1.25rem;
                    cursor: pointer;
                    padding: 0.25rem;
                    line-height: 1;
                    border-radius: 4px;
                }
                
                .reading-list-item-remove:hover {
                    background: var(--critical-bg);
                    color: var(--critical-color);
                }
                
                /* Article Action Active State */
                .article-action.active {
                    background: var(--accent-light);
                    color: var(--accent-primary);
                }
                
                /* Danger Button */
                .btn-danger {
                    background: var(--critical-color);
                    color: white;
                }
                
                .btn-danger:hover {
                    background: #b91c1c;
                }
                
                /* Update Banner */
                .update-banner button {
                    background: rgba(255,255,255,0.2);
                    border: none;
                    color: white;
                    padding: 0.375rem 0.75rem;
                    border-radius: 4px;
                    cursor: pointer;
                    font-size: 0.875rem;
                }
                
                .update-banner button:hover {
                    background: rgba(255,255,255,0.3);
                }
                
                /* Virtual Scroll Sentinels */
                .virtual-sentinel {
                    pointer-events: none;
                }
            `;
            document.head.appendChild(styles);
        },
    };
    
    // =========================================
    // INITIALIZATION
    // =========================================
    function init() {
        StyleInjector.init();
        ReadingList.init();
        NewsletterExport.init();
        KeyboardExtensions.init();
        ServiceWorkerManager.init();
        
        // Initialize virtual scroll after articles load
        if (window.state?.allArticles?.length > 100) {
            VirtualScroll.init();
        }
        
        console.log('[PolicyRadar] Enhancements loaded v6.2');
    }
    
    // Wait for DOM and main app
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(init, 100); // Allow main app to initialize
        });
    } else {
        setTimeout(init, 100);
    }
    
    // Export for global access
    window.ReadingList = ReadingList;
    window.NewsletterExport = NewsletterExport;
    window.VirtualScroll = VirtualScroll;
    
})();
