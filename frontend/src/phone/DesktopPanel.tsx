/**
 * Laptop view of the resident app: the same person and the same data as the phone column, expanded:
 * a large map of the home area, the three inputs in detail, and the alert history. Shown at >= 1100 px.
 */
import { useEffect, useRef, useState } from 'react';
import type { Map as MLMap } from 'maplibre-gl';
import { Icon } from '../components/Icon';
import { StatusShape, STATUS_WORD } from '../components/StatusBadge';
import { circle, createMap, maplibregl, setGibs, setImage, whenReady } from '../components/map';
import { phoneApi, type AlertOut, type PersonOut, type StatusOut } from '../lib/api';
import { ago, dTime, n0, n1 } from '../lib/format';
import { GIBS } from '../lib/nasa';

type Rain = Awaited<ReturnType<typeof phoneApi.rain>>;

export function DesktopPanel({ deviceId }: { deviceId: string }) {
  const [st, setSt] = useState<StatusOut | null>(null);
  const [person, setPerson] = useState<PersonOut | null>(null);
  const [alerts, setAlerts] = useState<AlertOut[]>([]);
  const [rain, setRain] = useState<Rain | null>(null);
  useEffect(() => {
    const load = () => {
      phoneApi.status(deviceId).then(setSt).catch(() => undefined);
      phoneApi.alerts(deviceId).then(setAlerts).catch(() => undefined);
      phoneApi.rain(deviceId).then(setRain).catch(() => undefined);
    };
    phoneApi.person(deviceId).then(setPerson).catch(() => undefined);
    load();
    const t = window.setInterval(load, 15000);
    return () => window.clearInterval(t);
  }, [deviceId]);

  if (!st || !person) return <div className="dp-empty">Loading your area…</div>;
  const r = st.radar;
  const rv = st.river;
  const u = st.union;
  return (
    <div className="dp">
      <header className="dp-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 4 }}>My area · আমার এলাকা</div>
          <h1>{u ? `${u.name_en}${u.name_bn ? ` · ${u.name_bn}` : ''}` : 'Home'}</h1>
          <div className="small muted">{u?.upazila_en} · home at {person.home_lat.toFixed(4)}° N, {person.home_lon.toFixed(4)}° E · alert distance {n1(person.radar_km)} km</div>
        </div>
        <div className="dp-status">
          <StatusShape status={st.status} size={42} />
          <div><b>{STATUS_WORD[st.status][1]}</b><div className="small bn">{STATUS_WORD[st.status][0]}</div></div>
        </div>
      </header>
      {st.replay && <div className="chip chip-replay" style={{ justifySelf: 'start' }}>REPLAY · real data from {dTime(st.as_of_utc)}</div>}

      <div className="dp-grid">
        <section className="dp-map card" aria-label="Map of the home area">
          <HomeMapLarge st={st} person={person} />
        </section>
        <section className="card dp-card">
          <h3><Icon name="sat" size={18} /> Radar · রাডার</h3>
          {r ? (
            <>
              <dl className="kv">
                <dt>Picture</dt><dd>{dTime(r.pass_utc)} Dhaka · track {r.track}</dd>
                <dt>Age</dt><dd>{n1(r.age_days)} days{r.stale ? ' (old)' : ''}</dd>
                <dt>Nearest new water</dt><dd>{r.new_water_distance_m != null ? `${n0(r.new_water_distance_m)} m · about ${r.walk_minutes} min walk` : 'none in this picture'}</dd>
                <dt>How sure</dt><dd>{r.confidence === 'less_sure' ? 'less sure (only at the looser threshold)' : r.confidence}</dd>
                <dt>Data</dt><dd>{r.processing_level}</dd>
                <dt>Next picture</dt><dd>{r.next_expected_local_date ?? '–'} (12-day cycle)</dd>
              </dl>
              {st.in_radar_gap && <p className="small hatch" style={{ padding: '6px 10px', borderRadius: 8, marginTop: 10 }}>The radar was off from 27 July to 10 August 2026. Nothing is filled in.</p>}
            </>
          ) : <p className="small muted">No radar picture yet.</p>}
        </section>
        <section className="card dp-card">
          <h3><Icon name="wave" size={18} /> River · নদী</h3>
          {rv ? (
            <>
              <div className="dp-gauge" aria-label={`River ${rv.level_m ?? 'unknown'} metres, danger level ${rv.danger_level_m} metres`}>
                {rv.level_m != null && <div className="lv" style={{ width: `${Math.min(100, (rv.level_m / (rv.danger_level_m + 1)) * 100)}%` }} />}
                <div className="dl" style={{ left: `${(rv.danger_level_m / (rv.danger_level_m + 1)) * 100}%` }}><span>danger {rv.danger_level_m} m</span></div>
                <div className="ln" style={{ left: `${(rv.line_m / (rv.danger_level_m + 1)) * 100}%` }} />
              </div>
              <dl className="kv" style={{ marginTop: 14 }}>
                <dt>Station</dt><dd>Jamuna at {rv.station} (FFWC)</dd>
                <dt>Level</dt><dd>{rv.level_m != null ? `${rv.level_m} m (${rv.kind})` : 'no reading'}</dd>
                <dt>Alert line</dt><dd>{rv.line_m} m (danger − 0.30 m)</dd>
                <dt>Reading</dt><dd>{rv.valid_local ? `${dTime(rv.valid_local)}${rv.stale ? ' · old' : ''}` : '–'}</dd>
              </dl>
            </>
          ) : <p className="small muted">No river station configured.</p>}
        </section>
        <section className="card dp-card">
          <h3><Icon name="rain" size={18} /> Rain · বৃষ্টি</h3>
          {rain && rain.days.length ? (
            <>
              <div className="dp-bars">
                {rain.days.map((d) => (
                  <div key={d.date} title={`${d.date}: ${d.mm} mm`}>
                    <span className="v">{Math.round(d.mm)}</span>
                    <span className="b" style={{ height: `${Math.min(100, (d.mm / Math.max(rain.limit_mm * 1.2, 1)) * 100)}%`, background: d.mm >= rain.limit_mm ? 'var(--danger)' : 'var(--river)' }} />
                    <span className="d">{d.date.slice(8)}</span>
                  </div>
                ))}
                <div className="lim" style={{ bottom: `${(1 / 1.2) * 100}%` }}><span>your level {rain.limit_mm} mm</span></div>
              </div>
              <p className="tiny muted" style={{ marginTop: 8 }}>{rain.source}. {rain.note}</p>
            </>
          ) : <p className="small muted">No rain values.</p>}
        </section>
        <section className="card dp-card dp-alerts">
          <h3><Icon name="bell" size={18} /> Alerts received · সতর্কবার্তা</h3>
          {alerts.length === 0 ? <p className="small muted">No alerts yet. Alerts arrive only after a volunteer approves them.</p> : (
            <ul>
              {alerts.map((a) => (
                <li key={a.recipient_id}>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <b>{a.rule === 'radar' ? 'Radar: new water near home' : a.rule === 'river' ? 'River near danger level' : 'Heavy rain'}</b>
                    <span className={`chip ${a.reply === 'help' ? '' : a.reply === 'safe' ? 'chip-valid' : ''}`} style={{ background: a.reply === 'help' ? 'var(--danger-lt)' : undefined, color: a.reply === 'help' ? 'var(--danger)' : undefined }}>{a.reply ? (a.reply === 'safe' ? 'you answered: safe' : 'you answered: help') : 'not answered'}</span>
                  </div>
                  <p className="small bn" style={{ margin: '4px 0 2px' }}>{a.message_bn}</p>
                  <p className="tiny muted" style={{ margin: 0 }}>{a.sent_utc ? `sent ${dTime(a.sent_utc)} (${ago(a.sent_utc)})` : ''}{a.approved_by ? ` · approved by ${a.approved_by}` : ''}{a.replay ? ' · REPLAY' : ''}</p>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
      <p className="tiny muted">Not an official warning. Official forecasts: FFWC and BMD; call 1090. Sources: {st.sources.join(' · ')}.</p>
      <style>{`
        .dp{display:grid;gap:14px;align-content:start;padding:24px 28px 32px;min-width:0}
        .dp-empty{display:grid;place-items:center;color:var(--ink-3)}
        .dp-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-end;flex-wrap:wrap}
        .dp-head h1{font-size:1.9rem;margin:0}
        .dp-status{display:flex;gap:12px;align-items:center;background:var(--paper);border:1px solid var(--line);border-radius:18px;padding:10px 16px}
        .dp-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}
        .dp-map{grid-column:1 / -1;height:min(46vh,460px);padding:0;overflow:hidden;position:relative}
        .dp-card h3{font-size:1.05rem;display:flex;gap:8px;align-items:center;color:var(--river)}
        .dp-alerts{grid-column:1 / -1}
        .dp-alerts ul{list-style:none;margin:0;padding:0;display:grid;gap:10px}
        .dp-alerts li{border:1px solid var(--line);border-radius:14px;padding:10px 12px}
        .dp-gauge{position:relative;height:18px;border-radius:9px;background:var(--mist);margin-top:26px}
        .dp-gauge .lv{height:100%;border-radius:9px;background:linear-gradient(90deg,#7fb0cc,var(--river))}
        .dp-gauge .dl{position:absolute;top:-22px;bottom:-4px;border-left:2px solid var(--danger)}
        .dp-gauge .dl span{position:absolute;top:0;right:6px;font-size:.72rem;color:var(--danger);white-space:nowrap;font-weight:700}
        .dp-gauge .ln{position:absolute;top:-4px;bottom:-4px;border-left:2px dashed var(--watch)}
        .dp-bars{position:relative;display:flex;gap:6px;align-items:flex-end;height:130px;padding-top:14px}
        .dp-bars>div:not(.lim){flex:1;display:grid;grid-template-rows:auto 1fr auto;justify-items:center;height:100%}
        .dp-bars .b{width:100%;border-radius:5px;align-self:end}
        .dp-bars .v{font-size:.7rem;font-weight:700}
        .dp-bars .d{font-size:.68rem;color:var(--ink-3)}
        .dp-bars .lim{position:absolute;left:0;right:0;border-top:2px dashed var(--danger);margin-bottom:16px}
        .dp-bars .lim span{position:absolute;right:0;top:-18px;font-size:.7rem;color:var(--danger);font-weight:700}
        @media (max-width:1400px){.dp-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
      `}</style>
    </div>
  );
}

function HomeMapLarge({ st, person }: { st: StatusOut; person: PersonOut }) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  const [view, setView] = useState<'water' | 'radar' | 'satellite'>('water');
  const r = st.radar;
  useEffect(() => {
    if (!el.current) return;
    const m = createMap(el.current, { base: 'light', center: [person.home_lon, person.home_lat], zoom: 12 });
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right');
    map.current = m;
    whenReady(m, () => {
      m.addSource('ring', { type: 'geojson', data: circle(person.home_lon, person.home_lat, person.radar_km * 1000) as never });
      m.addLayer({ id: 'ring', type: 'line', source: 'ring', paint: { 'line-color': '#2e7d32', 'line-width': 3, 'line-dasharray': [1.5, 1.5] } });
      m.addSource('ring2', { type: 'geojson', data: circle(person.home_lon, person.home_lat, person.radar_km * 2000) as never });
      m.addLayer({ id: 'ring2', type: 'line', source: 'ring2', paint: { 'line-color': '#e2a100', 'line-width': 1.5, 'line-dasharray': [2, 2] } });
      new maplibregl.Marker({ color: '#0B6E7F' }).setLngLat([person.home_lon, person.home_lat]).addTo(m);
      if (r?.overlay_url) setImage(m, 'nw', r.overlay_url, 0.95, 'ring', r.overlay_bounds ?? undefined);
    });
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); m.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [person.home_lat, person.home_lon, r?.overlay_url]);
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    whenReady(m, () => {
      const date = r ? new Date(r.pass_utc).toISOString().slice(0, 10) : null;
      setGibs(m, 'nisar', view === 'radar' ? GIBS.nisar! : null, date, 1, 'nw');
      const base = m.getSource('base') as unknown as { setTiles?: (t: string[]) => void } | undefined;
      base?.setTiles?.([`https://server.arcgisonline.com/ArcGIS/rest/services/${view === 'satellite' ? 'World_Imagery' : 'Canvas/World_Light_Gray_Base'}/MapServer/tile/{z}/{y}/{x}`]);
    });
  }, [view, r]);
  return (
    <>
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <div className="seg" role="group" aria-label="Map view" style={{ position: 'absolute', top: 12, left: 12, zIndex: 2, background: 'rgba(255,255,255,.95)' }}>
        <button aria-pressed={view === 'water'} onClick={() => setView('water')}>New water</button>
        <button aria-pressed={view === 'radar'} onClick={() => setView('radar')}>NISAR radar</button>
        <button aria-pressed={view === 'satellite'} onClick={() => setView('satellite')}>Satellite</button>
      </div>
      <div className="legend" style={{ position: 'absolute', left: 12, bottom: 12, zIndex: 2, background: 'rgba(255,255,255,.95)', padding: '6px 10px', borderRadius: 10 }}>
        <span><span className="sw" style={{ background: 'var(--water)' }} />New water since 18 Jun</span>
        <span><span style={{ width: 14, borderTop: '3px dashed #2e7d32' }} />Alert distance {person.radar_km} km</span>
        <span><span style={{ width: 14, borderTop: '2px dashed #e2a100' }} />Watch distance {person.radar_km * 2} km</span>
      </div>
    </>
  );
}
