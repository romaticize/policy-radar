/**
 * PolicyRadar Service Worker v6.2
 * Provides caching for offline support and faster loads
 */

const CACHE_VERSION = 'policyradar-v6.2';
const STATIC_CACHE = `${CACHE_VERSION}-static`;
const DATA_CACHE = `${CACHE_VERSION}-data`;

// Static assets to cache on install
const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/topic-explorer.html',
  '/knowledge-graph.html',
];

// Data files with network-first strategy
const DATA_PATTERNS = [
  /\/data\/.+\.json$/,
];

// CDN assets (cache but update in background)
const CDN_PATTERNS = [
  /cdnjs\.cloudflare\.com/,
  /unpkg\.com/,
];

// =========================================
// INSTALL - Cache static assets
// =========================================
self.addEventListener('install', (event) => {
  console.log('[SW] Installing service worker');
  
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => {
        console.log('[SW] Caching static assets');
        return cache.addAll(STATIC_ASSETS);
      })
      .then(() => self.skipWaiting())
  );
});

// =========================================
// ACTIVATE - Clean old caches
// =========================================
self.addEventListener('activate', (event) => {
  console.log('[SW] Activating service worker');
  
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
      .then(() => self.clients.claim())
  );
});

// =========================================
// FETCH - Handle requests
// =========================================
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  
  // Skip non-GET requests
  if (event.request.method !== 'GET') {
    return;
  }
  
  // Data files: Network first, cache fallback
  if (isDataRequest(url)) {
    event.respondWith(networkFirstStrategy(event.request, DATA_CACHE));
    return;
  }
  
  // CDN assets: Stale while revalidate
  if (isCdnRequest(url)) {
    event.respondWith(staleWhileRevalidate(event.request, STATIC_CACHE));
    return;
  }
  
  // Static assets: Cache first, network fallback
  if (isStaticRequest(url)) {
    event.respondWith(cacheFirstStrategy(event.request, STATIC_CACHE));
    return;
  }
  
  // Default: Network only
  event.respondWith(fetch(event.request));
});

// =========================================
// STRATEGIES
// =========================================

/**
 * Network first, cache fallback
 * Best for: API data that should be fresh but available offline
 */
async function networkFirstStrategy(request, cacheName) {
  try {
    const networkResponse = await fetch(request);
    
    // Cache successful responses
    if (networkResponse.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, networkResponse.clone());
    }
    
    return networkResponse;
  } catch (error) {
    console.log('[SW] Network failed, trying cache:', request.url);
    const cachedResponse = await caches.match(request);
    
    if (cachedResponse) {
      return cachedResponse;
    }
    
    // Return offline fallback for HTML
    if (request.headers.get('accept')?.includes('text/html')) {
      return caches.match('/');
    }
    
    throw error;
  }
}

/**
 * Cache first, network fallback
 * Best for: Static assets that rarely change
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
    console.log('[SW] Both cache and network failed:', request.url);
    throw error;
  }
}

/**
 * Stale while revalidate
 * Best for: CDN assets - serve cache immediately, update in background
 */
async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cachedResponse = await cache.match(request);
  
  // Fetch in background
  const fetchPromise = fetch(request).then((networkResponse) => {
    if (networkResponse.ok) {
      cache.put(request, networkResponse.clone());
    }
    return networkResponse;
  }).catch(() => null);
  
  // Return cached version immediately if available
  return cachedResponse || fetchPromise;
}

// =========================================
// HELPERS
// =========================================

function isDataRequest(url) {
  return DATA_PATTERNS.some((pattern) => pattern.test(url.pathname));
}

function isCdnRequest(url) {
  return CDN_PATTERNS.some((pattern) => pattern.test(url.href));
}

function isStaticRequest(url) {
  return url.origin === self.location.origin && (
    url.pathname === '/' ||
    url.pathname.endsWith('.html') ||
    url.pathname.endsWith('.css') ||
    url.pathname.endsWith('.js') ||
    url.pathname.endsWith('.png') ||
    url.pathname.endsWith('.svg') ||
    url.pathname.endsWith('.ico')
  );
}

// =========================================
// BACKGROUND SYNC (for future use)
// =========================================
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-data') {
    event.waitUntil(syncData());
  }
});

async function syncData() {
  // Future: Sync any pending user actions
  console.log('[SW] Background sync triggered');
}

// =========================================
// PUSH NOTIFICATIONS (for future use)
// =========================================
self.addEventListener('push', (event) => {
  if (!event.data) return;
  
  const data = event.data.json();
  
  const options = {
    body: data.body || 'New policy updates available',
    icon: '/icon-192.png',
    badge: '/badge-72.png',
    tag: 'policyradar-notification',
    data: {
      url: data.url || '/',
    },
  };
  
  event.waitUntil(
    self.registration.showNotification(data.title || 'PolicyRadar', options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  
  const url = event.notification.data?.url || '/';
  
  event.waitUntil(
    clients.matchAll({ type: 'window' }).then((clientList) => {
      // Focus existing tab if available
      for (const client of clientList) {
        if (client.url === url && 'focus' in client) {
          return client.focus();
        }
      }
      // Open new tab
      if (clients.openWindow) {
        return clients.openWindow(url);
      }
    })
  );
});

console.log('[SW] Service worker loaded');
