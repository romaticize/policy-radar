/**
 * PolicyRadar Service Worker - Optimized
 * =======================================
 * 
 * Improvements over original:
 * 1. Smarter cache invalidation
 * 2. Size limits on cached data
 * 3. Shorter data cache TTL
 * 4. Better offline handling
 * 
 * Version: 2.0.0
 * Date: January 13, 2026
 */

const CACHE_VERSION = 'policyradar-v2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DATA_CACHE = `${CACHE_VERSION}-data`;
const HTML_CACHE = `${CACHE_VERSION}-html`;

// Static assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/topic-explorer.html',
    '/knowledge-graph.html',
];

// Data endpoints with caching rules
const DATA_CONFIG = {
    '/data/initial.json': {
        maxAge: 5 * 60,  // 5 minutes
        cacheFirst: false,
    },
    '/data/public_data.json': {
        maxAge: 5 * 60,  // 5 minutes
        cacheFirst: false,
    },
};

// Cache size limits
const CACHE_LIMITS = {
    [STATIC_CACHE]: 20,     // 20 entries
    [DATA_CACHE]: 5,        // 5 entries
    [HTML_CACHE]: 10,       // 10 entries
};

// ============================================
// INSTALL
// ============================================
self.addEventListener('install', (event) => {
    console.log('[SW v2] Installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[SW v2] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => self.skipWaiting())
            .catch((error) => {
                console.error('[SW v2] Install failed:', error);
            })
    );
});

// ============================================
// ACTIVATE
// ============================================
self.addEventListener('activate', (event) => {
    console.log('[SW v2] Activating...');
    
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => {
                            // Delete any cache not matching current version
                            return name.startsWith('policyradar-') && 
                                   !name.startsWith(CACHE_VERSION);
                        })
                        .map((name) => {
                            console.log('[SW v2] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => self.clients.claim())
    );
});

// ============================================
// FETCH
// ============================================
self.addEventListener('fetch', (event) => {
    const url = new URL(event.request.url);
    
    // Only handle same-origin requests
    if (url.origin !== self.location.origin) {
        return;
    }
    
    // Route to appropriate strategy
    if (isDataRequest(url)) {
        event.respondWith(networkFirstWithFallback(event.request, DATA_CACHE));
    } else if (isHTMLRequest(event.request)) {
        event.respondWith(networkFirstWithFallback(event.request, HTML_CACHE));
    } else if (isStaticAsset(url)) {
        event.respondWith(cacheFirstWithNetwork(event.request, STATIC_CACHE));
    }
});

// ============================================
// STRATEGIES
// ============================================

/**
 * Cache First with Network Fallback
 * Used for: Static assets
 */
async function cacheFirstWithNetwork(request, cacheName) {
    const cached = await caches.match(request);
    
    if (cached) {
        // Refresh cache in background
        refreshCache(request, cacheName);
        return cached;
    }
    
    try {
        const response = await fetch(request);
        
        if (response.ok) {
            await addToCache(cacheName, request, response.clone());
        }
        
        return response;
    } catch (error) {
        console.error('[SW v2] Cache first failed:', error);
        return new Response('Offline', { status: 503 });
    }
}

/**
 * Network First with Cache Fallback
 * Used for: Data, HTML
 */
async function networkFirstWithFallback(request, cacheName) {
    try {
        const response = await fetch(request);
        
        if (response.ok) {
            // Cache the response
            await addToCache(cacheName, request, response.clone());
        }
        
        return response;
    } catch (error) {
        console.log('[SW v2] Network failed, trying cache:', request.url);
        
        const cached = await caches.match(request);
        
        if (cached) {
            // Add header to indicate cached response
            const headers = new Headers(cached.headers);
            headers.set('X-Cache-Status', 'cached');
            
            return new Response(cached.body, {
                status: cached.status,
                statusText: cached.statusText,
                headers: headers
            });
        }
        
        // Return offline response for data requests
        if (isDataRequest(new URL(request.url))) {
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
        
        return new Response('Offline', { status: 503 });
    }
}

// ============================================
// CACHE MANAGEMENT
// ============================================

/**
 * Add item to cache with size limits
 */
async function addToCache(cacheName, request, response) {
    const cache = await caches.open(cacheName);
    
    // Enforce size limits
    const keys = await cache.keys();
    const limit = CACHE_LIMITS[cacheName] || 50;
    
    if (keys.length >= limit) {
        // Delete oldest entries
        const toDelete = keys.slice(0, keys.length - limit + 1);
        await Promise.all(toDelete.map(key => cache.delete(key)));
        console.log(`[SW v2] Evicted ${toDelete.length} old cache entries from ${cacheName}`);
    }
    
    await cache.put(request, response);
}

/**
 * Refresh cache in background
 */
async function refreshCache(request, cacheName) {
    try {
        const response = await fetch(request);
        if (response.ok) {
            await addToCache(cacheName, request, response);
        }
    } catch (error) {
        // Silently fail - we're just refreshing
    }
}

// ============================================
// HELPERS
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
    const staticExtensions = [
        '.css', '.js', '.png', '.jpg', '.jpeg', 
        '.gif', '.svg', '.ico', '.woff', '.woff2'
    ];
    return staticExtensions.some(ext => url.pathname.endsWith(ext));
}

// ============================================
// MESSAGE HANDLERS
// ============================================

self.addEventListener('message', (event) => {
    const { type } = event.data;
    
    switch (type) {
        case 'SKIP_WAITING':
            self.skipWaiting();
            break;
            
        case 'CLEAR_CACHE':
            event.waitUntil(
                caches.keys().then((names) => {
                    return Promise.all(
                        names.map(name => {
                            console.log('[SW v2] Clearing cache:', name);
                            return caches.delete(name);
                        })
                    );
                }).then(() => {
                    // Notify all clients
                    self.clients.matchAll().then(clients => {
                        clients.forEach(client => {
                            client.postMessage({ type: 'CACHE_CLEARED' });
                        });
                    });
                })
            );
            break;
            
        case 'GET_CACHE_STATUS':
            event.waitUntil(
                getCacheStatus().then(status => {
                    event.source.postMessage({
                        type: 'CACHE_STATUS',
                        ...status
                    });
                })
            );
            break;
            
        case 'PREFETCH_DATA':
            event.waitUntil(
                prefetchData()
            );
            break;
            
        default:
            console.log('[SW v2] Unknown message type:', type);
    }
});

async function getCacheStatus() {
    const keys = await caches.keys();
    const status = {
        caches: keys.length,
        entries: 0,
        sizes: {}
    };
    
    for (const key of keys) {
        const cache = await caches.open(key);
        const cacheKeys = await cache.keys();
        status.entries += cacheKeys.length;
        status.sizes[key] = cacheKeys.length;
    }
    
    return status;
}

async function prefetchData() {
    console.log('[SW v2] Prefetching data...');
    const cache = await caches.open(DATA_CACHE);
    
    try {
        const urls = ['/data/initial.json', '/data/public_data.json'];
        for (const url of urls) {
            const response = await fetch(url);
            if (response.ok) {
                await cache.put(url, response);
                console.log('[SW v2] Prefetched:', url);
            }
        }
    } catch (error) {
        console.error('[SW v2] Prefetch failed:', error);
    }
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
    console.log('[SW v2] Syncing reading list...');
    // Future: Sync reading list with a backend
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

console.log('[SW v2] Service worker loaded');
