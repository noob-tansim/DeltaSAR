/** /app: the installable phone app. First visit: choose how to use it and where home is; then the app. */
import { useEffect, useMemo, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Nav } from '../components/Chrome';
import { Icon } from '../components/Icon';
import { DesktopPanel } from './DesktopPanel';
import { ApiError, phoneApi, type UnionOut } from '../lib/api';
import { device } from '../lib/device';
import { enablePush, pushSupported } from '../lib/push';
import { speak } from '../lib/speak';
import { PhoneApp, type Screen } from './PhoneApp';
import { tr, type Lang } from './strings';
import './phone.css';

const BBOX = [89.46, 24.205, 89.918, 24.8];

export default function AppPage() {
  const [id, setId] = useState<string | null>(device.id());
  const [state, setState] = useState<'checking' | 'join' | 'ready'>('checking');
  const loc = useLocation();
  const initial: Screen | undefined = useMemo(() => {
    const m = loc.pathname.match(/^\/app\/alert\/([^/]+)/);
    return m ? { name: 'alert', rid: m[1]! } : undefined;
  }, [loc.pathname]);

  useEffect(() => {
    if (!id) { setState('join'); return; }
    phoneApi.person(id).then(() => setState('ready')).catch((e) => setState(e instanceof ApiError && e.status === 404 ? 'join' : 'ready'));
  }, [id]);

  const wide = useWide(1100);
  const phone = (
    <>
      {state === 'checking' && <div className="ph" style={{ display: 'grid', placeItems: 'center' }}>…</div>}
      {state === 'join' && <Onboarding onDone={(d) => { setId(d); setState('ready'); }} />}
      {state === 'ready' && id && <PhoneApp deviceId={id} initial={initial} />}
    </>
  );
  const reset = () => { device.setId(null); device.setSandbox(null); setId(null); };

  // Phone and small tablet: the app itself, full screen, like an installed app.
  if (!wide) return <div className="app-full">{phone}<style>{`.app-full{height:100vh;height:100dvh;max-width:560px;margin:0 auto;background:#fff}`}</style></div>;

  // Laptop: the same app in a column, with the expanded view of the same person's data beside it.
  return (
    <>
      <Nav dark={false} />
      <div className="app-desk">
        <div className="app-col" aria-label="বন্যা সাথী app">{phone}</div>
        <main id="main" className="app-main">
          {state === 'ready' && id ? (
            <>
              <DesktopPanel deviceId={id} />
              <div className="app-tools">
                <span className="small muted">This browser is a demo participant. Install on a phone: browser menu → <i>Add to Home screen</i>.</span>
                <span className="row" style={{ gap: 8 }}>
                  <Link to="/demo" className="btn btn-ghost btn-sm"><Icon name="play" size={14} /> See an alert arrive (guided demo)</Link>
                  <button className="btn btn-ghost btn-sm" onClick={reset}>Start again as a new phone</button>
                </span>
              </div>
            </>
          ) : (
            <section className="app-intro">
              <div className="eyebrow"><Icon name="phone" size={14} /> The resident app</div>
              <h1>বন্যা সাথী · Bonna Sathi</h1>
              <p className="lead">What NISAR radar saw near your home, how old the picture is, and an alert you can hear and answer. Bangla first; every screen can be read aloud; status is always shape, word and colour.</p>
              <ul className="ticks" style={{ marginTop: 18 }}>
                <li><span>Choose how you use the phone: listening, pictures, large text, or vibration and light.</span></li>
                <li><span>Choose your union, or use where you are now. Your details are used only for alerts.</span></li>
                <li><span>Alerts arrive only after a union volunteer approves them. Press and hold to answer “safe” or “help”.</span></li>
              </ul>
              <p className="small muted" style={{ marginTop: 18 }}>Join on the left. Once joined, this side shows the expanded view of your area: a large map, radar, river and rain in detail, and your alerts.</p>
            </section>
          )}
        </main>
      </div>
      <style>{`
        body{background:var(--mist)}
        .app-desk{width:min(1480px,100% - 40px);margin:18px auto 28px;display:grid;grid-template-columns:420px minmax(0,1fr);gap:22px;align-items:start}
        .app-col{position:sticky;top:calc(var(--nav-h) + 18px);height:calc(100vh - var(--nav-h) - 36px);min-height:620px;border-radius:26px;overflow:hidden;border:1px solid var(--line);box-shadow:var(--shadow-2);background:#fff}
        .app-main{background:var(--paper);border:1px solid var(--line);border-radius:26px;min-height:calc(100vh - var(--nav-h) - 36px);box-shadow:var(--shadow-1)}
        .app-tools{display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;align-items:center;padding:0 28px 24px}
        .app-intro{padding:48px 44px;max-width:720px}
        .app-intro h1{font-size:2.4rem}
      `}</style>
    </>
  );
}

function useWide(min: number): boolean {
  const q = `(min-width: ${min}px)`;
  const [w, setW] = useState(() => window.matchMedia(q).matches);
  useEffect(() => {
    const m = window.matchMedia(q);
    const f = () => setW(m.matches);
    m.addEventListener('change', f);
    return () => m.removeEventListener('change', f);
  }, [q]);
  return w;
}

const MODES: [string, 'listen' | 'pictures' | 'large_text' | 'vibrate_light', 'modeListen' | 'modePictures' | 'modeLarge' | 'modeVibrate', 'modeListenSub' | 'modePicturesSub' | 'modeLargeSub' | 'modeVibrateSub'][] = [
  ['speaker', 'listen', 'modeListen', 'modeListenSub'],
  ['map', 'pictures', 'modePictures', 'modePicturesSub'],
  ['info', 'large_text', 'modeLarge', 'modeLargeSub'],
  ['bell', 'vibrate_light', 'modeVibrate', 'modeVibrateSub'],
];

function Onboarding({ onDone }: { onDone: (deviceId: string) => void }) {
  const [lang, setLang] = useState<Lang>(device.lang());
  const [step, setStep] = useState(0);
  const [mode, setMode] = useState<Record<string, boolean>>({ listen: true });
  const [unions, setUnions] = useState<UnionOut[]>([]);
  const [q, setQ] = useState('');
  const [union, setUnion] = useState<UnionOut | null>(null);
  const [home, setHome] = useState<[number, number] | null>(null);
  const [channels, setChannels] = useState<string[]>(['in_app']);
  const [consent, setConsent] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { phoneApi.unions().then(setUnions).catch(() => setMsg('The server is waking up; the list will appear in a moment.')); }, []);
  const list = unions.filter((u) => !q || u.name_en.toLowerCase().includes(q.toLowerCase()) || (u.name_bn ?? '').includes(q)).slice(0, 60);
  const sayIt = (bn: string, en: string) => { if (mode.listen) void speak({ bn, en, lang }); };

  const locate = () => {
    navigator.geolocation?.getCurrentPosition((p) => {
      const { latitude: la, longitude: lo } = p.coords;
      if (lo >= BBOX[0]! && lo <= BBOX[2]! && la >= BBOX[1]! && la <= BBOX[3]!) {
        setHome([la, lo]);
        setMsg(null);
      } else setMsg(tr('locationOutside', lang));
    }, () => setMsg(tr('locationFailed', lang)), { enableHighAccuracy: true, timeout: 10000 });
  };

  const finish = async () => {
    if (!union) return setMsg(tr('needUnion', lang));
    if (!consent) return setMsg(tr('needConsent', lang));
    setBusy(true);
    const id = device.ensureId();
    try {
      await phoneApi.putPerson(id, { union_id: union.union_id, home_lat: home?.[0] ?? union.lat, home_lon: home?.[1] ?? union.lon, months: [6, 7, 8, 9, 10], rain_on: true, rain_mm: 76, river_on: true, radar_on: true, radar_km: 1, channels, mode, consent: true });
      if (channels.includes('push')) await enablePush(id).catch(() => undefined);
      onDone(id);
    } catch (e) {
      setMsg(String((e as Error).message));
    } finally { setBusy(false); }
  };

  return (
    <div className="ph" lang={lang}>
      <header className="ph-top">
        <span className="name">{tr('appName', lang)}</span><span className="sp" />
        <button className="ph-pill" onClick={() => { const l = lang === 'bn' ? 'en' : 'bn'; setLang(l); device.setLang(l); }}>{tr('language', lang)}</button>
      </header>
      <main className="ph-body">
        {step === 0 ? (
          <>
            <h2>{tr('howUse', lang)}</h2>
            <p className="ph-note" style={{ margin: 0 }}>{tr('chooseByListening', lang)} · {tr('laterChange', lang)}</p>
            {MODES.map(([ic, k, t, sub]) => (
              <button key={k} className="ph-mode" aria-pressed={!!mode[k]} onClick={() => { setMode((m) => ({ ...m, [k]: !m[k] })); sayIt(tr(t, 'bn'), tr(t, 'en')); }}>
                <span className="ic"><Icon name={ic as never} size={26} /></span>
                <span><b>{tr(t, lang)}</b><span>{tr(sub, lang)}</span></span>
              </button>
            ))}
            <button className="ph-big primary" onClick={() => setStep(1)}>{tr('next', lang)} <Icon name="arrow" size={18} /></button>
          </>
        ) : (
          <>
            <button className="ph-back" onClick={() => setStep(0)}><Icon name="back" size={18} /> {tr('back', lang)}</button>
            <h2>{tr('chooseUnion', lang)}</h2>
            <p className="ph-note" style={{ margin: 0 }}>{tr('areaWhy', lang)}</p>
            <input className="ph-input" placeholder={tr('searchUnion', lang)} value={q} onChange={(e) => setQ(e.target.value)} aria-label={tr('searchUnion', lang)} />
            <div className="ph-list" role="listbox" aria-label={tr('chooseUnion', lang)}>
              {list.map((u) => (
                <button key={u.union_id} className="ph-opt" aria-pressed={union?.union_id === u.union_id} onClick={() => { setUnion(u); sayIt(u.name_bn ?? u.name_en, u.name_en); }}>
                  <b>{lang === 'bn' ? (u.name_bn ?? u.name_en) : u.name_en}</b> <span className="ph-note">· {u.upazila_en}</span>
                </button>
              ))}
            </div>
            {union && (
              <div className="ph-card">
                <b>{tr('homePlace', lang)}</b>
                <p className="ph-note" style={{ margin: '4px 0 8px' }}>{home ? `${home[0].toFixed(4)}, ${home[1].toFixed(4)}` : tr('homeAtCentre', lang)}</p>
                <button className="ph-big ghost" style={{ width: '100%' }} onClick={locate}><Icon name="crosshair" size={18} /> {tr('useMyLocation', lang)}</button>
                <p className="ph-note" style={{ margin: '8px 0 0' }}>{lang === 'bn' ? 'জায়গা দেওয়া ঐচ্ছিক, শুধু একবার বাড়ি ঠিক করতে। অ্যাপ কখনো আপনাকে অনুসরণ করে না।' : 'Optional, used once to set your home. The app never tracks you.'}</p>
              </div>
            )}
            <div className="ph-card">
              <b>{tr('joinTitle', lang)}</b>
              {([['in_app', 'chApp', true], ['push', 'chAppSub', pushSupported()], ['call_sim', 'chCall', true], ['sms_sim', 'chSms', true]] as [string, 'chApp' | 'chAppSub' | 'chCall' | 'chSms', boolean][]).filter((x) => x[2]).map(([c, k]) => (
                <label key={c} className="ph-switch">
                  <span>{c === 'push' ? (lang === 'bn' ? 'ফোনে নোটিফিকেশন' : 'Phone notifications') : tr(k, lang)}</span>
                  <input type="checkbox" checked={channels.includes(c)} disabled={c === 'in_app'} onChange={(e) => setChannels((cs) => (e.target.checked ? [...cs, c] : cs.filter((x) => x !== c)))} />
                </label>
              ))}
            </div>
            <label className="ph-switch ph-card"><span>{tr('consent', lang)} · <span className="ph-note">{tr('privacy', lang)}</span></span><input type="checkbox" checked={consent} onChange={(e) => setConsent(e.target.checked)} /></label>
            <p className="ph-note" style={{ margin: 0 }}>{tr('demoNote', lang)}</p>
            {msg && <p className="ph-note" role="alert" style={{ color: 'var(--danger)', margin: 0 }}>{msg}</p>}
            <button className="ph-big primary" onClick={() => void finish()} disabled={busy}>{busy ? tr('loading', lang) : tr('start', lang)}</button>
          </>
        )}
      </main>
    </div>
  );
}
