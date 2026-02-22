/**
 * PolicyRadar Service Worker
 * ==========================
 * Provides offline caching and faster subsequent loads.
 * 
 * Strategy:
 * - Static assets: Cache First (long-lived)
 * - API data: Network First with cache fallback
 * - HTML pages: Stale While Revalidate
 */

const CACHE_VERSION = 'policyradar-v5';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DATA_CACHE = `${CACHE_VERSION}-data`;
const HTML_CACHE = `${CACHE_VERSION}-html`;

// Static assets to cache immediately on install
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/topic-explorer.html',
    '/knowledge-graph.html',
    // Add any CSS/JS files if you have external ones
];

// Data endpoints to cache
const DATA_ENDPOINTS = [
    '/data/initial.json',
    '/data/public_data.json',
];

// Cache duration settings (in seconds)
const CACHE_DURATION = {
    static: 7 * 24 * 60 * 60,  // 7 days
    data: 5 * 60,              // 5 minutes
    html: 60 * 60,             // 1 hour
};

// ============================================
// INSTALL EVENT
// ============================================
self.addEventListener('install', (event) => {
    console.log('[SW] Installing service worker...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[SW] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => {
                // Skip waiting to activate immediately
                return self.skipWaiting();
            })
            .catch((error) => {
                console.error('[SW] Install failed:', error);
            })
    );
});

// ============================================
// ACTIVATE EVENT
// ============================================
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating service worker...');
    
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => {
                            // Delete old version caches
                            return name.startsWith('policyradar-') && 
                                   !name.startsWith(CACHE_VERSION);
                        })
                        .map((name) => {
                            console.log('[SW] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => {
                // Take control of all pages immediately
                return self.clients.claim();
            })
    );
});

// ============================================
// FETCH EVENT
// ============================================
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Only handle same-origin requests
    if (url.origin !== self.location.origin) {
        return;
    }
    
    // Route to appropriate strategy
    if (isDataRequest(url)) {
        event.respondWith(networkFirstStrategy(event.request, DATA_CACHE));
    } else if (isHTMLRequest(event.request)) {
        event.respondWith(staleWhileRevalidateStrategy(event.request, HTML_CACHE));
    } else if (isStaticAsset(url)) {
        event.respondWith(cacheFirstStrategy(event.request, STATIC_CACHE));
    }
});

// ============================================
// CACHING STRATEGIES
// ============================================

/**
 * Cache First Strategy
 * Used for: Static assets (CSS, JS, images)
 * Returns cached version if available, otherwise fetches from network.
 */
async function cacheFirstStrategy(request, cacheName) {
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        return cachedResponse;
    }
    
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('[SW] Cache first failed:', error);
        return new Response('Offline', { status: 503 });
    }
}

/**
 * Network First Strategy
 * Used for: API data (JSON)
 * Tries network first, falls back to cache if offline.
 */
async function networkFirstStrategy(request, cacheName) {
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.log('[SW] Network failed, trying cache:', request.url);
        
        const cachedResponse = await caches.match(request);
        
        if (cachedResponse) {
            // Add header to indicate cached response
            const headers = new Headers(cachedResponse.headers);
            headers.set('X-Cache-Status', 'cached');
            
            return new Response(cachedResponse.body, {
                status: cachedResponse.status,
                statusText: cachedResponse.statusText,
                headers: headers
            });
        }
        
        // Return empty data structure if nothing cached
        return new Response(JSON.stringify({
            articles: [],
            trending_topics: [],
            error: 'offline',
            message: 'No cached data available. Please connect to the internet.'
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

/**
 * Stale While Revalidate Strategy
 * Used for: HTML pages
 * Returns cached version immediately, then updates cache in background.
 */
async function staleWhileRevalidateStrategy(request, cacheName) {
    const cache = await caches.open(cacheName);
    const cachedResponse = await cache.match(request);
    
    // Start network fetch (don't await yet)
    const networkPromise = fetch(request)
        .then((networkResponse) => {
            if (networkResponse.ok) {
                cache.put(request, networkResponse.clone());
            }
            return networkResponse;
        })
        .catch((error) => {
            console.log('[SW] Background revalidation failed:', error);
            return null;
        });
    
    // Return cached version if available, otherwise wait for network
    if (cachedResponse) {
        return cachedResponse;
    }
    
    return networkPromise || new Response('Offline', { status: 503 });
}

// ============================================
// HELPER FUNCTIONS
// ============================================

function isDataRequest(url) {
    return url.pathname.startsWith('/data/') && 
           url.pathname.endsWith('.json');
}

function isHTMLRequest(request) {
    return request.headers.get('Accept')?.includes('text/html') ||
           request.url.endsWith('.html') ||
           request.url.endsWith('/');
}

function isStaticAsset(url) {
    const staticExtensions = ['.css', '.js', '.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.woff', '.woff2'];
    return staticExtensions.some(ext => url.pathname.endsWith(ext));
}

// ============================================
// BACKGROUND SYNC (for future use)
// ============================================
self.addEventListener('sync', (event) => {
    if (event.tag === 'sync-reading-list') {
        event.waitUntil(syncReadingList());
    }
});

async function syncReadingList() {
    // Future: Sync reading list with a backend
    console.log('[SW] Syncing reading list...');
}

// ============================================
// PUSH NOTIFICATIONS (for future use)
// ============================================
self.addEventListener('push', (event) => {
    if (!event.data) return;
    
    const data = event.data.json();
    
    event.waitUntil(
        self.registration.showNotification(data.title || 'PolicyRadar Update', {
            body: data.body || 'New policy updates available',
            icon: '/icon-192.png',
            badge: '/badge-72.png',
            tag: 'policyradar-notification',
            data: data.url || '/'
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    event.notification.close();
    
    event.waitUntil(
        clients.openWindow(event.notification.data || '/')
    );
});

// ============================================
// MESSAGE HANDLER
// ============================================
self.addEventListener('message', (event) => {
    if (event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data.type === 'CLEAR_CACHE') {
        event.waitUntil(
            caches.keys().then((names) => {
                return Promise.all(names.map(name => caches.delete(name)));
            })
        );
    }
    
    if (event.data.type === 'CACHE_DATA') {
        event.waitUntil(
            caches.open(DATA_CACHE).then((cache) => {
                return cache.addAll(DATA_ENDPOINTS);
            })
        );
    }
});

console.log('[SW] Service worker loaded');
