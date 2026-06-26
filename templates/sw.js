// Doc-Index Service Worker
//
// Two responsibilities:
//   (1) Reactive cache: network-first for every same-origin GET. Success
//       refreshes the cache; failure (offline) serves from cache. This is
//       what makes "already-visited" pages keep working after disconnect.
//   (2) Proactive cache: when the page posts {type:'CACHE_FILES', urls:[…]},
//       fetch each URL and put it in the cache. This is the "缓存离线" button
//       — the user opts in to download all docs while online.
//
// Bump CACHE_NAME to invalidate everything on the next install.
const CACHE_NAME = 'doc-index-v3';
const MAX_CACHE_ITEMS = 500;

self.addEventListener('install', () => {
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
    const toDelete = keys.slice(0, keys.length - MAX_CACHE_ITEMS);
    await Promise.all(toDelete.map(k => cache.delete(k)));
  }
}

self.addEventListener('fetch', e => {
  const url = new URL(e.request.url);
  if (e.request.method !== 'GET' || url.origin !== location.origin) {
    return;
  }
  e.respondWith(
    fetch(e.request)
      .then(res => {
        if (res.ok) {
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

self.addEventListener('message', e => {
  const data = e.data || {};
  if (data.type === 'CACHE_FILES' && Array.isArray(data.urls)) {
    e.waitUntil((async () => {
      const cache = await caches.open(CACHE_NAME);
      for (const url of data.urls) {
        try {
          await cache.add(url);
        } catch (_) {
          // Best-effort; individual failures must not abort the batch.
        }
      }
    })());
  }
});
