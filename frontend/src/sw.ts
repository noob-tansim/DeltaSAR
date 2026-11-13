/// <reference lib="webworker" />
/**
 * Service worker.
 *  - precache: app shell, fonts, icons (list injected at build time)
 *  - the phone app's last server answers and map pictures are kept, so with no network it opens with
 *    "last data and its age" instead of a blank page
 *  - Web Push: shows the alert and opens it when touched
 */
import { clientsClaim } from 'workbox-core';
import { createHandlerBoundToURL, precacheAndRoute } from 'workbox-precaching';
import { NavigationRoute, registerRoute } from 'workbox-routing';
import { NetworkFirst, StaleWhileRevalidate } from 'workbox-strategies';

declare const self: ServiceWorkerGlobalScope & { __WB_MANIFEST: Array<{ url: string; revision: string | null }> };

self.skipWaiting();
clientsClaim();
precacheAndRoute(self.__WB_MANIFEST);

// Every page of the site opens from the cached shell; the router then picks the screen.
registerRoute(new NavigationRoute(createHandlerBoundToURL('/index.html')));

const isGet = (r: Request) => r.method === 'GET';
// The API may live on another origin (Render): match by path. Network first; the cache only answers after 4 s.
registerRoute(
  ({ url, request }) => isGet(request) && (/^\/api\/v1\/people\/[^/]+(\/(status|alerts|rain))?$/.test(url.pathname) || url.pathname === '/api/v1/unions' || /^\/api\/v1\/alerts\/[^/]+(\/evidence)?$/.test(url.pathname)),
  new NetworkFirst({ cacheName: 'bonna-api', networkTimeoutSeconds: 4 }),
);
registerRoute(({ url, request }) => isGet(request) && url.origin === self.location.origin && url.pathname.startsWith('/data/'), new StaleWhileRevalidate({ cacheName: 'deltasar-data' }));

interface PushPayload { title?: string; body?: string; recipient_id?: string; url?: string; vibrate?: number[] }

self.addEventListener('push', (event) => {
  let p: PushPayload = {};
  try { p = (event.data?.json() ?? {}) as PushPayload; } catch { p = { body: event.data?.text() }; }
  const url = p.recipient_id ? `/app/alert/${p.recipient_id}` : '/app/';
  const options: NotificationOptions & { vibrate?: number[] } = {
    body: p.body ?? '', tag: p.recipient_id ?? 'bonna-alert', icon: '/icons/icon-192.png', badge: '/icons/icon-192.png',
    lang: 'bn', requireInteraction: true, data: { url }, vibrate: p.vibrate ?? [300, 150, 300, 150, 600],
  };
  event.waitUntil(self.registration.showNotification(p.title ?? 'বন্যা সাথী', options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data as { url?: string } | null)?.url ?? '/app/';
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (list) => {
      for (const c of list) {
        if ('focus' in c) {
          await (c as WindowClient).navigate(url).catch(() => undefined);
          return (c as WindowClient).focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
