/** "Live from NASA": the newest NISAR pass over the reach, read from NASA CMR in this browser right now. */
import { useEffect, useState } from 'react';
import { loadJSON, type Season } from '../lib/data';
import { ago, dTime } from '../lib/format';
import { eonetFloods, newestNisar, operaCount, type FloodEvent, type LivePass } from '../lib/nasa';
import { Icon } from './Icon';
import { digits, useL } from '../lib/i18n';

export function useLiveNasa() {
  const [pass, setPass] = useState<LivePass | null>(null);
  const [live, setLive] = useState<boolean | null>(null);
  const [opera, setOpera] = useState<number | null>(null);
  const [floods, setFloods] = useState<FloodEvent[]>([]);
  useEffect(() => {
    let alive = true;
    newestNisar(4)
      .then((ps) => {
        if (!alive) return;
        const full = ps.find((p) => p.full_frame) ?? ps[0] ?? null;
        setPass(full);
        setLive(true);
      })
      .catch(async () => {
        // NASA not reachable: use the CMR record saved on 12 Nov, and say so
        const s = await loadJSON<Season>('season.json');
        const g = [...s.cmr.granules].filter((x) => x.full_frame).sort((a, b) => b.acquired_utc.localeCompare(a.acquired_utc))[0];
        if (alive && g) {
          setPass({ granule: g.granule, track: g.track, acquired_utc: g.acquired_utc, published_utc: g.published_utc, maturity: g.maturity as LivePass['maturity'], full_frame: true, latency_h: g.latency_hours });
          setLive(false);
        }
      });
    const since = new Date(Date.now() - 30 * 864e5).toISOString().slice(0, 10) + 'T00:00:00Z';
    operaCount(since).then((n) => alive && setOpera(n)).catch(() => undefined);
    eonetFloods().then((f) => alive && setFloods(f)).catch(() => undefined);
    return () => { alive = false; };
  }, []);
  return { pass, live, opera, floods };
}

export function LiveNasaStrip({ compact = false }: { compact?: boolean }) {
  const { pass, live, opera, floods } = useLiveNasa();
  const { L, lang } = useL();
  const d = (v: string | number) => digits(v, lang);
  const days = pass ? Math.max(0, Math.round((Date.now() - new Date(pass.acquired_utc).getTime()) / 864e5)) : 0;
  const lastFlood = floods.sort((a, b) => b.date.localeCompare(a.date))[0];
  return (
    <div className="live-strip" aria-live="polite">
      <span className={`chip ${live === false ? '' : 'chip-live'}`}>
        <span className={`dot ${live ? 'pulse' : ''}`} /> {live === false ? L('NASA CMR · saved 12 Nov', 'নাসা CMR · ১২ নভেম্বরে সংরক্ষিত') : L('LIVE · NASA CMR', 'সরাসরি · নাসা CMR')}
      </span>
      {pass ? (
        <span className="live-main">
          {L(<>Newest NISAR pass over this reach: <b>{dTime(pass.acquired_utc)}</b> (Dhaka), track {pass.track},</>, <>এই এলাকার সর্বশেষ NISAR ছবি: <b>{d(dTime(pass.acquired_utc))}</b> (ঢাকা), ট্র্যাক {pass.track},</>)}{' '}
          <span className={`chip ${pass.maturity === 'VALIDATED' ? 'chip-valid' : 'chip-prov'}`} style={{ padding: '1px 8px' }}>{pass.maturity === 'VALIDATED' ? L('VALIDATED', 'যাচাইকৃত') : L('PROVISIONAL', 'প্রাথমিক')}</span>{' '}
          {L(<>· published {Math.round(pass.latency_h)} h after the satellite passed · <b>{ago(pass.acquired_utc)}</b></>, <>· উপগ্রহ যাওয়ার {d(Math.round(pass.latency_h))} ঘণ্টা পর প্রকাশিত · <b>{d(days)} দিন আগে</b></>)}
        </span>
      ) : (
        <span className="live-main muted">{L('Asking NASA CMR for the newest NISAR pass…', 'নাসা CMR থেকে সর্বশেষ NISAR ছবির খোঁজ নেওয়া হচ্ছে…')}</span>
      )}
      {!compact && opera != null && (
        <span className="live-sub"><Icon name="drop" size={14} /> {L(`${opera} OPERA water maps (Sentinel-1) over the reach in the last 30 days`, `গত ৩০ দিনে এই এলাকার ${d(opera)}টি OPERA পানির মানচিত্র (সেন্টিনেল-১)`)}</span>
      )}
      {!compact && lastFlood && (
        <span className="live-sub"><Icon name="tri" size={14} /> {L(`NASA EONET: ${lastFlood.title.replace(/\s+\d+$/, '')}, ${new Date(lastFlood.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`, `নাসা EONET: বাংলাদেশে বন্যা, ${new Date(lastFlood.date).toLocaleDateString('bn-BD', { day: 'numeric', month: 'long' })}`)}</span>
      )}
      {!compact && <a href="/methods#live" className="live-sub" style={{ color: 'var(--water)', textDecoration: 'none' }}><Icon name="check" size={14} /> {L('All live NASA connections', 'নাসার সব সরাসরি সংযোগ')}</a>}
      <style>{`
        .live-strip{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:center;font-size:.9rem;color:var(--sky-2)}
        .live-main b{color:var(--sky)}
        .live-sub{display:inline-flex;gap:6px;align-items:center;color:var(--sky-3)}
      `}</style>
    </div>
  );
}
