const CACHE_NAME = 'doc-index-v1';
const MAX_CACHE_ITEMS = 100;
const CACHEABLE_TYPES = /\.(html|css|js|png|jpg|jpeg|gif|ico|json|woff2?)$/i;

self.addEventListener('install', e => {
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

async function trimCache(cache) {
  const keys = await cache.keys();
  if (keys.length > MAX_CACHE_ITEMS) {
    // Remove oldest entries (FIFO)
    const toDelete = keys.slice(0, keys.length - MAX_CACHE_ITEMS);
    await Promise.all(toDelete.map(k => cache.delete(k)));
  }
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);

  // Only cache same-origin GET requests for safe file types
  if (e.request.method !== 'GET' || url.origin !== location.origin) {
    return;
  }

  // Only cache static assets and index, skip documents (pdf, xlsx, etc.)
  const isCacheable = CACHEABLE_TYPES.test(url.pathname) || url.pathname.endsWith('/');

  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok && isCacheable) {
          const clone = res.clone();
          caches.open(CACHE_NAME).then(c => {
            c.put(e.request, clone);
            trimCache(c);
          });
        }
        return res;
      })
      .catch(() => caches.match(e.request))
  );
});
