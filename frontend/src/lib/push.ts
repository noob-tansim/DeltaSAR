/** Web Push: ask permission, subscribe with the server's VAPID key, send the subscription to the API. */
import { phoneApi } from './api';

function b64ToBytes(b64: string): Uint8Array<ArrayBuffer> {
  const pad = '='.repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, '+').replace(/_/g, '/'));
  const out = new Uint8Array(new ArrayBuffer(raw.length));
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function pushSupported(): boolean {
  return 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;
}

/** Returns a short reason when push is not possible; the app then shows alerts by polling. */
export async function enablePush(deviceId: string): Promise<'ok' | string> {
  if (!pushSupported()) return 'This browser has no Web Push (on iPhone: add to Home Screen first).';
  const key = await phoneApi.pushKey().catch(() => null);
  if (!key?.enabled || !key.public_key) return 'Push is not configured on the server; alerts still appear while the app is open.';
  const perm = await Notification.requestPermission();
  if (perm !== 'granted') return 'Notifications were not allowed; alerts still appear while the app is open.';
  const reg = await navigator.serviceWorker.ready;
  const sub = (await reg.pushManager.getSubscription()) ?? (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: b64ToBytes(key.public_key) }));
  await phoneApi.subscribe(deviceId, sub.toJSON());
  return 'ok';
}
