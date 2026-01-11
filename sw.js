/**
 * PolicyRadar Service Worker
 * ==========================
 * Provides offline caching and faster subsequent loads.
 * 
 * Caching Strategy:
 * - Static assets: Cache-first (HTML, CSS, JS)
 * - Data files: Network-first with cache fallback
 * - Images: Cache-first with network fallback
 * 
 * Installation:
 * Add to index.html before </body>:
 * 
 * <script>
 *   if ('serviceWorker' in navigator) {
 *     navigator.serviceWorker.register('/sw.js')
 *       .then(reg => console.log('SW registered'))
 *       .catch(err => console.log('SW failed:', err));
 *   }
 * </script>
 */

const CACHE_VERSION = 'policyradar-v1';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DATA_CACHE = `${CACHE_VERSION}-data`;

// Static assets to cache immediately
const STATIC_ASSETS = [
    '/',
    '/index.html',
    '/topic-explorer.html',
    '/knowledge-graph.html',
    'https://cdnjs.cloudflare.com/ajax/libs/jspdf/2.5.1/jspdf.umd.min.js',
];

// Data files to cache with network-first strategy
const DATA_PATTERNS = [
    /\/data\/.*\.json$/,
    /\/public_data\.json$/,
    /\/initial\.json$/,
];

// Install event - cache static assets
self.addEventListener('install', (event) => {
    console.log('[SW] Installing...');
    
    event.waitUntil(
        caches.open(STATIC_CACHE)
            .then((cache) => {
                console.log('[SW] Caching static assets');
                return cache.addAll(STATIC_ASSETS);
            })
            .then(() => {
                // Take over immediately
                return self.skipWaiting();
            })
    );
});

// Activate event - clean up old caches
self.addEventListener('activate', (event) => {
    console.log('[SW] Activating...');
    
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name.startsWith('policyradar-') && name !== STATIC_CACHE && name !== DATA_CACHE)
                        .map((name) => {
                            console.log('[SW] Deleting old cache:', name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => {
                // Claim all clients immediately
                return self.clients.claim();
            })
    );
});

// Fetch event - serve from cache or network
self.addEventListener('fetch', (event) => {
    const { request } = event;
    const url = new URL(request.url);
    
    // Skip non-GET requests
    if (request.method !== 'GET') return;
    
    // Skip cross-origin requests except for CDNs
    if (url.origin !== self.location.origin && 
        !url.hostname.includes('cdnjs.cloudflare.com')) {
        return;
    }
    
    // Data files: Network-first, cache fallback
    if (DATA_PATTERNS.some(pattern => pattern.test(url.pathname))) {
        event.respondWith(networkFirstWithCache(request, DATA_CACHE));
        return;
    }
    
    // Static assets: Cache-first, network fallback
    event.respondWith(cacheFirstWithNetwork(request, STATIC_CACHE));
});

/**
 * Network-first strategy with cache fallback
 * Best for data that changes frequently
 */
async function networkFirstWithCache(request, cacheName) {
    try {
        // Try network first
        const networkResponse = await fetch(request);
        
        // Cache successful responses
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        // Network failed, try cache
        console.log('[SW] Network failed, trying cache:', request.url);
        const cachedResponse = await caches.match(request);
        
        if (cachedResponse) {
            console.log('[SW] Serving from cache:', request.url);
            return cachedResponse;
        }
        
        // Both failed
        console.error('[SW] No cache available:', request.url);
        return new Response(JSON.stringify({ 
            error: 'Offline', 
            message: 'Data not available offline' 
        }), {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
        });
    }
}

/**
 * Cache-first strategy with network fallback
 * Best for static assets
 */
async function cacheFirstWithNetwork(request, cacheName) {
    // Try cache first
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
        // Return cached, but also update in background
        updateCache(request, cacheName);
        return cachedResponse;
    }
    
    // Not in cache, try network
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            cache.put(request, networkResponse.clone());
        }
        
        return networkResponse;
    } catch (error) {
        console.error('[SW] Network failed:', request.url);
        
        // Return offline page for HTML requests
        if (request.headers.get('Accept')?.includes('text/html')) {
            return caches.match('/');
        }
        
        throw error;
    }
}

/**
 * Background cache update (stale-while-revalidate pattern)
 */
async function updateCache(request, cacheName) {
    try {
        const networkResponse = await fetch(request);
        
        if (networkResponse.ok) {
            const cache = await caches.open(cacheName);
            await cache.put(request, networkResponse);
            console.log('[SW] Cache updated:', request.url);
        }
    } catch (error) {
        // Ignore background update failures
    }
}

// Handle messages from the page
self.addEventListener('message', (event) => {
    if (event.data.type === 'SKIP_WAITING') {
        self.skipWaiting();
    }
    
    if (event.data.type === 'CLEAR_CACHE') {
        caches.keys().then((cacheNames) => {
            return Promise.all(
                cacheNames.map((name) => caches.delete(name))
            );
        }).then(() => {
            event.ports[0].postMessage({ success: true });
        });
    }
});

console.log('[SW] Service Worker loaded');
