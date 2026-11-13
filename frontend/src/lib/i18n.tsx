/**
 * Site language: English or Bangla. English by default for an international audience; Bangla when the browser
 * prefers it or the visitor chooses it. Choosing a language also sets the phone app's language.
 * Bangla sentences on the website are drafts and need the same native-reader check as the phone app.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { device } from './device';

export type SiteLang = 'en' | 'bn';
const KEY = 'deltasar.lang';

function initial(): SiteLang {
  try {
    const v = localStorage.getItem(KEY);
    if (v === 'en' || v === 'bn') return v;
  } catch { /* ignore */ }
  return typeof navigator !== 'undefined' && navigator.language?.toLowerCase().startsWith('bn') ? 'bn' : 'en';
}

function chosenBefore(): boolean {
  try { return localStorage.getItem(KEY) != null; } catch { return false; }
}

const Ctx = createContext<{ lang: SiteLang; setLang: (l: SiteLang) => void; chosen: boolean }>({ lang: 'en', setLang: () => undefined, chosen: false });

export function LangProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<SiteLang>(initial);
  const [chosen, setChosen] = useState<boolean>(chosenBefore);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = (l: SiteLang) => {
    setLangState(l);
    setChosen(true);
    try { localStorage.setItem(KEY, l); } catch { /* ignore */ }
    device.setLang(l);
  };
  return <Ctx.Provider value={{ lang, setLang, chosen }}>{children}</Ctx.Provider>;
}

/** `L(english, bangla)` picks the visitor's language; works for strings and JSX. */
export function useL() {
  const { lang, setLang, chosen } = useContext(Ctx);
  const L = <T,>(en: T, bn: T): T => (lang === 'bn' ? bn : en);
  return { lang, setLang, L, bn: lang === 'bn', chosen };
}

const BN_DIGITS = '০১২৩৪৫৬৭৮৯';
/** Digits in Bangla script when the site is in Bangla. */
export function digits(s: string | number, lang: SiteLang): string {
  const t = String(s);
  return lang === 'bn' ? t.replace(/[0-9]/g, (d) => BN_DIGITS[+d]!) : t;
}
