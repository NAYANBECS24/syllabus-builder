/* Only the public app shell is cached here. No uploads, API replies or secrets. */
const CACHE = 'sylex-shell-v5.0';
const ASSETS = ['index.html', 'styles.css', 'chat.css', 'cinematic.css', 'workspace.css', 'studio.css',
  'demo-data.js', 'api-client.js', 'app.js', 'book.js', 'book-finder.js', 'chat.js', 'cinematic.js',
  'workspace.js', 'studio-core.js', 'studio-store.js', 'studio.js', 'offline.js', 'local-assistant.js'];
const root = new URL('./', self.location.href);
self.addEventListener('install', event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS.map(asset => new URL(asset, root).href))));
});
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key.startsWith('sylex-shell-') && key !== CACHE) await caches.delete(key);
    await self.clients.claim();
  })());
});
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== root.origin) return;
  let asset = url.pathname.slice(root.pathname.length);
  if (url.pathname === root.pathname) asset = 'index.html';
  if (!ASSETS.includes(asset)) return;
  event.respondWith((async () => {
    const cache = await caches.open(CACHE);
    return await cache.match(new URL(asset, root).href) || fetch(event.request);
  })());
});
