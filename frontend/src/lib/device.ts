/** Who this browser is to the API: a random device id kept in localStorage (no account, no password). */
const KEY = 'bonna.device';
const SB = 'bonna.sandbox';
const LANG = 'bonna.lang';
const TOKEN = 'bonna.console';

function get(k: string): string | null {
  try {
    return localStorage.getItem(k);
  } catch {
    return null;
  }
}
function set(k: string, v: string | null): void {
  try {
    if (v == null) localStorage.removeItem(k);
    else localStorage.setItem(k, v);
  } catch {
    /* private mode: works for this visit only */
  }
}

export function newDeviceId(): string {
  const a = new Uint8Array(12);
  crypto.getRandomValues(a);
  return 'dev-' + Array.from(a, (b) => b.toString(16).padStart(2, '0')).join('');
}

export const device = {
  id: () => get(KEY),
  setId: (v: string | null) => set(KEY, v),
  ensureId: () => {
    let d = get(KEY);
    if (!d) {
      d = newDeviceId();
      set(KEY, d);
    }
    return d;
  },
  sandbox: () => get(SB),
  setSandbox: (v: string | null) => set(SB, v),
  lang: (): 'bn' | 'en' => (get(LANG) === 'en' ? 'en' : 'bn'),
  setLang: (v: 'bn' | 'en') => set(LANG, v),
  consoleToken: () => {
    try {
      return sessionStorage.getItem(TOKEN);
    } catch {
      return null;
    }
  },
  setConsoleToken: (v: string | null) => {
    try {
      if (v) sessionStorage.setItem(TOKEN, v);
      else sessionStorage.removeItem(TOKEN);
    } catch {
      /* ignore */
    }
  },
};
