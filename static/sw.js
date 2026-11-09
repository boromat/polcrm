/* PolCRM Service Worker - offline shell + network-first for HTML */

const VERSION = 'v5-2026-11-09';
const SHELL_CACHE = `polcrm-shell-${VERSION}`;
const RUNTIME_CACHE = `polcrm-runtime-${VERSION}`;

const SHELL_ASSETS = [
    '/static/css/style.css',
    '/static/js/app.js',
    '/static/icons/icon.svg',
    'https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css',
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(SHELL_CACHE).then((c) => c.addAll(SHELL_ASSETS).catch(() => {}))
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) =>
            Promise.all(
                keys
                    .filter((k) => k !== SHELL_CACHE && k !== RUNTIME_CACHE)
                    .map((k) => caches.delete(k))
            )
        )
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    const req = event.request;
    if (req.method !== 'GET') return;

    const url = new URL(req.url);

    // Don't cache API, POST routes, auth, or Flask static handlers with queries
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/oauth')) return;

    // Same-origin static: stale-while-revalidate
    // (zwroc cache od razu, ale w tle pobierz nowsza wersje i nadpisz cache)
    if (url.origin === location.origin && url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.open(RUNTIME_CACHE).then((cache) =>
                cache.match(req).then((cached) => {
                    const fetchPromise = fetch(req).then((res) => {
                        if (res.ok) cache.put(req, res.clone());
                        return res;
                    }).catch(() => cached);
                    return cached || fetchPromise;
                })
            )
        );
        return;
    }

    // Google Fonts / jsDelivr CDN: cache-first
    if (/(fonts\.googleapis|fonts\.gstatic|cdn\.jsdelivr)/i.test(url.hostname)) {
        event.respondWith(
            caches.match(req).then(
                (cached) =>
                    cached ||
                    fetch(req).then((res) => {
                        if (res.ok) {
                            const copy = res.clone();
                            caches.open(RUNTIME_CACHE).then((c) => c.put(req, copy));
                        }
                        return res;
                    })
            )
        );
        return;
    }

    // HTML pages - network first, fallback to cached shell if offline
    if (req.mode === 'navigate' || (req.headers.get('accept') || '').includes('text/html')) {
        event.respondWith(
            fetch(req)
                .then((res) => {
                    const copy = res.clone();
                    caches.open(RUNTIME_CACHE).then((c) => c.put(req, copy));
                    return res;
                })
                .catch(() =>
                    caches.match(req).then(
                        (cached) =>
                            cached ||
                            new Response(
                                `<!doctype html><meta charset="utf-8"><title>Offline - PolCRM</title>
                                <body style="font-family: system-ui; background: #0a0a14; color: #e5e7eb; padding: 40px; text-align: center;">
                                <h1 style="color:#a29bfe;">Jesteś offline</h1>
                                <p>Nie mogę połączyć się z serwerem. Sprawdź internet i spróbuj ponownie.</p>
                                <button onclick="location.reload()" style="margin-top:20px; padding:10px 20px; background:#6c5ce7; color:white; border:0; border-radius:8px; cursor:pointer;">Spróbuj ponownie</button>
                                </body>`,
                                { headers: { 'Content-Type': 'text/html; charset=utf-8' } }
                            )
                    )
                )
        );
    }
});
