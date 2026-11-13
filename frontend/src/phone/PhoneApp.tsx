/**
 * বন্যা সাথী, the resident's phone app. Bangla first, voice on every screen.
 * Runs full-screen at /app or inside the phone frame of the guided demo (`embedded`).
 * The app asks for its status every few seconds while open, so an approved alert appears even without push.
 */
import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { phoneApi, type PersonOut, type StatusOut } from '../lib/api';
import { device } from '../lib/device';
import { useL } from '../lib/i18n';
import { speak, stopSpeaking, vibrate, type SpeakResult } from '../lib/speak';
import { AlertScreen, CallScreen, EvidenceScreen, HelpSheet, HomeScreen, MapScreen, RainScreen, SettingsScreen } from './screens';
import { tr, type Lang } from './strings';
import { Icon } from '../components/Icon';
import './phone.css';

export type Screen = { name: 'home' } | { name: 'alert'; rid: string } | { name: 'evidence'; rid: string } | { name: 'map' } | { name: 'rain' } | { name: 'settings' } | { name: 'call'; rid: string };

type Ctx = {
  deviceId: string; lang: Lang; setLang: (l: Lang) => void; status: StatusOut | null; person: PersonOut | null; error: string | null;
  refresh: () => Promise<void>; go: (s: Screen) => void; back: () => void; embedded: boolean;
  say: (bn: string, en: string, clip?: string) => void; speaking: boolean; voiceNote: string | null; large: boolean; setLarge: (v: boolean) => void;
  openHelp: () => void; setSpeakText: (bn: string, en: string) => void;
};
const C = createContext<Ctx | null>(null);
export const usePhone = () => {
  const c = useContext(C);
  if (!c) throw new Error('usePhone outside PhoneApp');
  return c;
};

export function PhoneApp({ deviceId, embedded = false, pollMs, initial, onAlertSeen }: {
  deviceId: string; embedded?: boolean; pollMs?: number; initial?: Screen; onAlertSeen?: (rid: string) => void;
}) {
  const site = useL();
  const [lang, setLangState] = useState<Lang>(site.chosen ? site.lang : device.lang());
  useEffect(() => { if (site.chosen) setLangState(site.lang); }, [site.lang, site.chosen]);
  const [status, setStatus] = useState<StatusOut | null>(null);
  const [person, setPerson] = useState<PersonOut | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [stack, setStack] = useState<Screen[]>([initial ?? { name: 'home' }]);
  const [speaking, setSpeaking] = useState(false);
  const [voiceNote, setVoiceNote] = useState<string | null>(null);
  const [flash, setFlash] = useState(0);
  const [help, setHelp] = useState(false);
  const [large, setLarge] = useState(false);
  const seen = useRef<Set<string>>(new Set());
  const lastClock = useRef<{ replay: boolean; t: number } | null>(null);
  const speakText = useRef<[string, string]>(['', '']);
  const screen = stack[stack.length - 1]!;

  const setLang = (l: Lang) => { setLangState(l); site.setLang(l); };

  const say = useCallback((bn: string, en: string, clip?: string) => {
    setSpeaking(true);
    void speak({ bn, en, lang, clip, onEnd: () => setSpeaking(false) }).then((r: SpeakResult) => {
      if (r === 'none') setSpeaking(false);
      setVoiceNote(r === 'en-fallback' ? (lang === 'bn' ? 'এই যন্ত্রে বাংলা কণ্ঠ নেই, ইংরেজিতে পড়া হচ্ছে।' : 'No Bangla voice on this device; reading in English.') : r === 'none' ? tr('noVoice', lang) : null);
    });
  }, [lang]);

  const refresh = useCallback(async () => {
    try {
      const st = await phoneApi.status(deviceId);
      // the clock moved (a replay jump, or back to live): start again from the home screen
      const prev = lastClock.current;
      if (prev && (prev.replay !== st.replay || Math.abs(new Date(st.as_of_utc).getTime() - prev.t) > 6 * 3.6e6)) {
        stopSpeaking();
        setStack([{ name: 'home' }]);
      }
      lastClock.current = { replay: st.replay, t: new Date(st.as_of_utc).getTime() };
      setStatus(st);
      setError(null);
      const a = st.active_alert;
      if (a && !seen.current.has(a.recipient_id)) {
        seen.current.add(a.recipient_id);
        if (!a.reply) {
          setStack((s) => [...s.filter((x) => x.name === 'home'), { name: 'alert', rid: a.recipient_id }]);
          if (person?.mode?.vibrate_light !== false) { vibrate(); setFlash((f) => f + 1); }
          phoneApi.ack(a.recipient_id, deviceId).catch(() => undefined);
          onAlertSeen?.(a.recipient_id);
        }
      }
    } catch (e) {
      setError(String((e as Error).message ?? e));
    }
  }, [deviceId, onAlertSeen, person]);

  useEffect(() => {
    phoneApi.person(deviceId).then((p) => { setPerson(p); if (p.mode?.large_text) setLarge(true); }).catch(() => undefined);
    void refresh();
    const t = window.setInterval(() => void refresh(), pollMs ?? (embedded ? 2500 : 15000));
    return () => { window.clearInterval(t); stopSpeaking(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deviceId]);

  const go = (s: Screen) => { stopSpeaking(); setSpeaking(false); setStack((st) => [...st, s]); };
  const back = () => { stopSpeaking(); setSpeaking(false); setStack((st) => (st.length > 1 ? st.slice(0, -1) : st)); };

  const ctx: Ctx = {
    deviceId, lang, setLang, status, person, error, refresh, go, back, embedded, say, speaking, voiceNote, large, setLarge,
    openHelp: () => setHelp(true), setSpeakText: (bn, en) => { speakText.current = [bn, en]; },
  };

  const onListen = () => {
    if (speaking) { stopSpeaking(); setSpeaking(false); return; }
    const [bn, en] = speakText.current;
    say(bn, en);
  };

  return (
    <C.Provider value={ctx}>
      <div className={`ph ${large ? 'large' : ''}`} lang={lang === 'bn' ? 'bn' : 'en'}>
        <header className="ph-top">
          <svg width="30" height="30" viewBox="0 0 64 64" aria-hidden="true"><rect width="64" height="64" rx="16" fill="#0B6E7F" /><path d="M14 38c6 0 6-4 12-4s6 4 12 4 6-4 12-4" fill="none" stroke="#fff" strokeWidth="4.5" strokeLinecap="round" /><path d="M14 47c6 0 6-4 12-4s6 4 12 4 6-4 12-4" fill="none" stroke="#3CC8F0" strokeWidth="4.5" strokeLinecap="round" /><path d="M32 11c-6 8-10 13-10 18a10 10 0 0 0 20 0c0-5-4-10-10-18z" fill="#fff" /></svg>
          <span className="name">{tr('appName', lang)}</span>
          <span className="sp" />
          <button className="ph-pill" onClick={() => setLang(lang === 'bn' ? 'en' : 'bn')} aria-label={lang === 'bn' ? 'Switch to English' : 'বাংলায় দেখুন'}>{tr('language', lang)}</button>
          <button className="ph-pill" onClick={() => setLarge(!large)} aria-pressed={large} aria-label={tr('modeLarge', lang)} title={tr('modeLarge', lang)}>
            <b style={{ fontSize: large ? '1.2em' : '1em' }}>অ</b><span style={{ fontSize: '.8em' }}>A</span>
          </button>
        </header>
        {status?.replay && (
          <div className="ph-replay" role="note"><Icon name="clock" size={14} /> {tr('replay', lang)} · {new Date(status.as_of_utc).toLocaleString(lang === 'bn' ? 'bn-BD' : 'en-GB', { timeZone: 'Asia/Dhaka', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })}</div>
        )}
        <main className="ph-body" key={`${screen.name}-${'rid' in screen ? screen.rid : ''}`}>
          {screen.name === 'home' && <HomeScreen />}
          {screen.name === 'alert' && <AlertScreen rid={screen.rid} />}
          {screen.name === 'evidence' && <EvidenceScreen rid={screen.rid} />}
          {screen.name === 'map' && <MapScreen />}
          {screen.name === 'rain' && <RainScreen />}
          {screen.name === 'settings' && <SettingsScreen />}
          {voiceNote && <p className="ph-note" role="status">{voiceNote}</p>}
        </main>
        <nav className="ph-bottom" aria-label={lang === 'bn' ? 'শুনুন ও সাহায্য' : 'Listen and help'}>
          <button className={`ph-listen ${speaking ? 'on' : ''}`} onClick={onListen} aria-pressed={speaking}>
            <Icon name={speaking ? 'stop' : 'speaker'} size={26} /> {speaking ? tr('stop', lang) : tr('listen', lang)}
          </button>
          <button className="ph-help" onClick={() => setHelp(true)}><Icon name="help" size={24} /> {tr('help', lang)}</button>
        </nav>
        {screen.name === 'call' && <CallScreen rid={screen.rid} />}
        {help && <HelpSheet onClose={() => setHelp(false)} />}
        {flash > 0 && <div className="ph-flash" key={flash} aria-hidden="true" />}
      </div>
    </C.Provider>
  );
}
