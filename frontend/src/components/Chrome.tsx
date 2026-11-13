/** Site chrome: top navigation, footer, the "waking the server" banner. */
import { useEffect, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useApiState } from '../lib/api';
import { useL } from '../lib/i18n';
import { Icon, Logo } from './Icon';

export const REPO_URL = (import.meta.env.VITE_REPO_URL as string | undefined) || 'https://github.com/';

const LINKS: [string, string, string][] = [
  ['/', 'Story', 'গল্প'],
  ['/explore', 'Explore the map', 'মানচিত্র দেখুন'],
  ['/demo', 'Live demo', 'লাইভ ডেমো'],
  ['/app', 'বন্যা সাথী app', 'বন্যা সাথী অ্যাপ'],
  ['/methods', 'Methods & data', 'পদ্ধতি ও তথ্য'],
];

export function Nav({ dark = true }: { dark?: boolean }) {
  const [open, setOpen] = useState(false);
  const loc = useLocation();
  const { L, lang, setLang } = useL();
  useEffect(() => setOpen(false), [loc.pathname]);
  return (
    <header className={`nav ${dark ? 'nav-dark' : 'nav-light'}`}>
      <a href="#main" className="skip">Skip to content</a>
      <div className="nav-in">
        <Link to="/" className="brand" aria-label="DeltaSAR home">
          <Logo size={32} />
          <span className="brand-t">
            <b>DeltaSAR</b>
            <span className="bn">বন্যা সাথী</span>
          </span>
        </Link>
        <nav aria-label="Main" className={`links ${open ? 'open' : ''}`}>
          {LINKS.map(([to, en, bn]) => (
            <NavLink key={to} to={to} end={to === '/'} className={({ isActive }) => (isActive ? 'on' : '')}>
              {L(en, bn)}
            </NavLink>
          ))}
        </nav>
        <div className="lang" role="group" aria-label="Language / ভাষা">
          <button aria-pressed={lang === 'en'} onClick={() => setLang('en')} lang="en">EN</button>
          <button aria-pressed={lang === 'bn'} onClick={() => setLang('bn')} lang="bn">বাংলা</button>
        </div>
        <button className="menu" aria-expanded={open} aria-label="Menu" onClick={() => setOpen((o) => !o)}>
          <Icon name={open ? 'x' : 'menu'} />
        </button>
      </div>
      <style>{`
        .nav{position:sticky;top:0;z-index:50;height:var(--nav-h)}
        .nav-dark{background:var(--night);color:var(--sky);border-bottom:1px solid var(--night-line)}
        .nav-light{background:#fff;color:var(--ink);border-bottom:1px solid var(--line)}
        .nav-in{position:relative;height:100%;display:flex;align-items:center;gap:22px;width:min(1320px,100% - 32px);margin-inline:auto}
        .brand{display:flex;flex:none;align-items:center;gap:10px;color:inherit;text-decoration:none}
        .brand-t{display:flex;flex-direction:column;line-height:1}
        .brand-t b{font-family:var(--font-display);font-size:1.15rem;letter-spacing:-.01em}
        .brand-t .bn{font-size:.8rem;opacity:.75;margin-top:3px}
        .links{display:flex;gap:4px;position:absolute;left:50%;transform:translateX(-50%)}
        .links a{color:inherit;text-decoration:none;padding:8px 12px;border-radius:6px;font-weight:500;font-size:.95rem;opacity:.82}
        .links a:hover{opacity:1;background:${dark ? 'rgba(255,255,255,.06)' : 'var(--mist)'}}
        .links a.on{opacity:1;background:${dark ? 'rgba(60,200,240,.14)' : 'var(--river-lt)'};color:${dark ? 'var(--water)' : 'var(--river)'}}
        .lang{display:inline-flex;flex:none;margin-left:auto;border:1px solid ${dark ? 'var(--night-line)' : 'var(--line)'};border-radius:8px;padding:3px;gap:2px}
        .lang button{border:0;background:none;color:inherit;font-weight:700;font-size:.82rem;padding:5px 11px;border-radius:5px;opacity:.7;min-height:32px}
        .lang button[aria-pressed='true']{opacity:1;background:${dark ? 'var(--water)' : 'var(--river)'};color:${dark ? 'var(--night)' : '#fff'}}
        .menu{display:none;margin-left:8px;background:none;border:1px solid ${dark ? 'var(--night-line)' : 'var(--line)'};color:inherit;border-radius:8px;width:44px;height:44px;align-items:center;justify-content:center}
        @media (max-width: 1020px){
          .lang{margin-left:auto}
          .menu{display:inline-flex}
          .links{display:none;position:absolute;top:var(--nav-h);left:0;right:0;transform:none;flex-direction:column;padding:10px 16px 16px;background:${dark ? 'var(--night)' : '#fff'};border-bottom:1px solid ${dark ? 'var(--night-line)' : 'var(--line)'};margin:0}
          .links.open{display:flex}
          .links a{padding:12px 14px}
        }
      `}</style>
    </header>
  );
}

export function Footer() {
  const { L } = useL();
  return (
    <footer className="on-night" style={{ background: 'var(--night)', color: 'var(--sky-2)', padding: '48px 0 36px', borderTop: '1px solid var(--night-line)' }}>
      <div className="container" style={{ display: 'grid', gap: 28, gridTemplateColumns: 'repeat(auto-fit,minmax(220px,1fr))' }}>
        <div>
          <div className="row" style={{ gap: 10, color: 'var(--sky)' }}>
            <Logo size={30} />
            <b style={{ fontFamily: 'var(--font-display)', fontSize: '1.1rem' }}>DeltaSAR · বন্যা সাথী</b>
          </div>
          <p className="small" style={{ marginTop: 12 }}>
            {L(<>Team Astro Bengalis, Bangladesh. NASA Space Apps Challenge 2026: <i>Dancing with the SARs</i>. Code under Apache-2.0.</>, <>টিম অ্যাস্ট্রো বেঙ্গলিস, বাংলাদেশ। নাসা স্পেস অ্যাপস চ্যালেঞ্জ ২০২৬: <i>Dancing with the SARs</i>। কোড Apache-2.0 লাইসেন্সে উন্মুক্ত।</>)}
          </p>
        </div>
        <div className="small">
          <b style={{ color: 'var(--sky)' }}>{L('Not an official warning.', 'এটি সরকারি সতর্কবার্তা নয়।')}</b>
          <p style={{ marginTop: 6 }}>{L(<>Official flood forecasts: FFWC and BMD. Call <b style={{ color: 'var(--sky)' }}>1090</b> (free) for the government's voice forecast.</>, <>সরকারি বন্যা পূর্বাভাস: FFWC ও BMD। সরকারি পূর্বাভাস শুনতে বিনা খরচে <b style={{ color: 'var(--sky)' }}>১০৯০</b> নম্বরে ফোন করুন।</>)}</p>
        </div>
        <div className="small">
          <b style={{ color: 'var(--sky)' }}>Data</b>
          <p style={{ marginTop: 6 }}>
            NISAR data courtesy of NASA/JPL-Caltech and ISRO, distributed by ASF DAAC. NASA GIBS, CMR, EONET, POWER, GPM IMERG. FFWC (BWDB).
            Copernicus, ESA WorldCover, Google Open Buildings, geoBoundaries. <Link to="/methods#sources" style={{ color: 'var(--water)' }}>Full list and licences</Link>.
          </p>
        </div>
        <div className="small stack" style={{ gap: 8 }}>
          <a href={REPO_URL} target="_blank" rel="noreferrer" className="row" style={{ color: 'var(--water)', gap: 8 }}><Icon name="github" size={16} /> Open repository</a>
          <Link to="/console" style={{ color: 'var(--sky-2)' }}>Volunteer console (team)</Link>
          <Link to="/methods#ai" style={{ color: 'var(--sky-2)' }}>How AI was used</Link>
        </div>
      </div>
    </footer>
  );
}

export function WakeBanner() {
  const s = useApiState();
  const { L } = useL();
  if (!s.waking && !s.down) return null;
  return (
    <div role="status" style={{ position: 'fixed', top: 'calc(var(--nav-h) + 10px)', left: '50%', transform: 'translateX(-50%)', zIndex: 80, background: 'var(--night-2)', color: 'var(--sky)', border: '1px solid var(--night-line)', borderRadius: 8, padding: '10px 18px', boxShadow: 'var(--shadow-2)', display: 'flex', gap: 10, alignItems: 'center', fontSize: '.9rem', maxWidth: 'calc(100% - 32px)' }}>
      {s.waking ? (
        <><span className="dot pulse" style={{ color: 'var(--water)' }} /> {L('Waking the server (free hosting sleeps when idle). This takes up to a minute, once.', 'সার্ভার চালু হচ্ছে (বিনামূল্যের হোস্টিং অলস থাকলে ঘুমিয়ে পড়ে)। একবার, এক মিনিট পর্যন্ত লাগতে পারে।')}</>
      ) : (
        <><Icon name="info" size={16} /> {L('The server is not answering yet. The story and maps still work; please try again in a minute.', 'সার্ভার এখনো সাড়া দিচ্ছে না। গল্প ও মানচিত্র চলবে; এক মিনিট পরে আবার চেষ্টা করুন।')}</>
      )}
    </div>
  );
}
