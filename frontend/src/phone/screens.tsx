/** Screens of the phone app. Every sentence exists in Bangla and English; Bangla lines marked NEW need a native check. */
import { useEffect, useRef, useState } from 'react';
import type { Map as MLMap } from 'maplibre-gl';
import { Icon } from '../components/Icon';
import { StatusShape, STATUS_BG, STATUS_BORDER, STATUS_INK, STATUS_WORD } from '../components/StatusBadge';
import { circle, createMap, maplibregl, setGibs, setImage, whenReady } from '../components/map';
import { phoneApi, type AlertOut, type EvidenceOut } from '../lib/api';
import { GIBS } from '../lib/nasa';
import { usePhone } from './PhoneApp';
import { monthName, num, say as sayT, STATION_BN, tr, when, type Lang } from './strings';

const T = (lang: Lang, bn: string, en: string) => (lang === 'bn' ? bn : en);

// ================================================================ home
export function HomeScreen() {
  const { status, lang, go, setSpeakText, error } = usePhone();
  if (!status) {
    return <p className="ph-note">{error ? T(lang, 'সার্ভারের সাথে যোগাযোগ হচ্ছে না। একটু পরে আবার চেষ্টা করুন।', 'Cannot reach the server. Please try again shortly.') : tr('loading', lang)}</p>;
  }
  const s = status.status;
  const u = status.union;
  const area = u ? (lang === 'bn' ? `${u.name_bn ?? u.name_en}${u.upazila_en ? `, ${u.upazila_bn ?? STATION_BN[u.upazila_en] ?? u.upazila_en}` : ''}` : `${u.name_en}${u.upazila_en ? `, ${u.upazila_en}` : ''}`) : '—';
  const r = status.radar;
  let fact = '';
  let factEn = '';
  if (s === 'alert' && status.active_alert) {
    fact = status.active_alert.message_bn; factEn = status.active_alert.message_en;
  } else if (s === 'no_data') {
    fact = status.in_radar_gap ? tr('gap', 'bn') : T('bn', 'শেষ রাডার ছবি অনেক পুরোনো এবং নদীর নতুন খবর নেই।', ''); // NEW
    factEn = status.in_radar_gap ? tr('gap', 'en') : 'The last radar picture is old and there is no new river reading.';
  } else if (r?.walk_minutes != null && r.new_water_distance_m != null && r.new_water_distance_m <= 3000) {
    fact = sayT.newWaterWalk(r.walk_minutes, 'bn'); factEn = sayT.newWaterWalk(r.walk_minutes, 'en');
  } else if (r) {
    fact = tr('radarNoNewWater', 'bn'); factEn = tr('radarNoNewWater', 'en');
  } else {
    fact = tr('radarNone', 'bn'); factEn = tr('radarNone', 'en');
  }
  const word = STATUS_WORD[s];
  const riv = status.river;
  const rain = status.rain;
  const valid = r?.processing_level?.includes('VALIDATED');

  const bn = [tr('myArea', 'bn'), area, word[0], fact,
    r ? sayT.pictureAge(r.pass_utc, r.age_days, 'bn') : '',
    riv?.level_m != null ? sayT.river(STATION_BN[riv.station] ?? riv.station, riv.level_m, riv.danger_level_m, 'bn') : '',
    tr('notOfficial', 'bn'), tr('call1090', 'bn')].filter(Boolean).join('। ');
  const en = [tr('myArea', 'en'), area, word[1], factEn, r ? sayT.pictureAge(r.pass_utc, r.age_days, 'en') : '',
    riv?.level_m != null ? sayT.river(riv.station, riv.level_m, riv.danger_level_m, 'en') : '', tr('notOfficial', 'en'), tr('call1090', 'en')].filter(Boolean).join('. ');
  setSpeakText(bn, en);

  return (
    <>
      <div>
        <div className="ph-area-k">{tr('myArea', lang)}</div>
        <h1 className="ph-area">{area}</h1>
      </div>
      <section className={`ph-status ${s === 'no_data' ? 'hatch' : ''}`} style={{ background: s === 'no_data' ? undefined : STATUS_BG[s], borderColor: STATUS_BORDER[s], color: STATUS_INK[s] }} aria-live="polite">
        <StatusShape status={s} size={52} />
        <div>
          <div className="w">{lang === 'bn' ? word[0] : word[1]}</div>
          <div className="f">{lang === 'bn' ? fact : factEn}</div>
          {s === 'alert' && status.active_alert && (
            <button className="ph-pill" style={{ marginTop: 8, background: 'var(--danger)', color: '#fff' }} onClick={() => go({ name: 'alert', rid: status.active_alert!.recipient_id })}>{tr('openAlert', lang)} <Icon name="arrow" size={16} /></button>
          )}
        </div>
      </section>
      <div className="ph-chips">
        {r && <span className="ph-chip"><Icon name="sat" size={15} /> {sayT.pictureAge(r.pass_utc, r.age_days, lang)}</span>}
        {r && <span className="ph-chip" style={{ borderColor: valid ? '#9fcea2' : '#f0d68a', background: valid ? 'var(--safe-lt)' : 'var(--watch-lt)' }}><Icon name={valid ? 'check' : 'info'} size={15} /> {valid ? tr('verified', lang) : tr('provisional', lang)}</span>}
        {r?.stale && <span className="ph-chip hatch">{tr('oldInfo', lang)}</span>}
        {status.in_radar_gap && <span className="ph-chip hatch" style={{ borderColor: 'var(--unknown)' }}><Icon name="clock" size={15} /> {tr('gap', lang)}</span>}
      </div>
      {r && status.union && <HomeMap />}
      <div className="ph-card stack" style={{ gap: 12 }}>
        <div className="ph-row">
          <span className="ic"><Icon name="wave" /></span>
          <div>
            <div className="t">{riv?.level_m != null ? sayT.river(lang === 'bn' ? (STATION_BN[riv.station] ?? riv.station) : riv.station, riv.level_m, riv.danger_level_m, lang) : tr('riverNone', lang)}</div>
            <div className="s">FFWC{riv?.valid_local ? ` · ${when(riv.valid_local, lang)}` : ''}{riv?.stale ? ` · ${tr('oldInfo', lang)}` : ''}</div>
          </div>
        </div>
        <div className="ph-row">
          <span className="ic"><Icon name="rain" /></span>
          <div>
            <div className="t">{rain?.last_24h_mm != null ? `${tr('rainTitle', lang)}: ${sayT.rain(rain.last_24h_mm, rain.limit_mm, lang)}` : tr('rainNone', lang)}</div>
            <div className="s">NASA IMERG{rain?.date ? ` · ${when(rain.date + 'T12:00:00Z', lang, false)}` : ''}</div>
          </div>
        </div>
      </div>
      <div className="ph-tiles">
        <button className="ph-tile" onClick={() => go({ name: 'map' })}><Icon name="map" size={30} />{tr('map', lang)}</button>
        <button className="ph-tile" onClick={() => go({ name: 'rain' })}><Icon name="rain" size={30} />{tr('rainTile', lang)}</button>
        <button className="ph-tile" onClick={() => go({ name: 'settings' })}><Icon name="bell" size={30} />{tr('myAlerts', lang)}</button>
      </div>
      <p className="ph-official">{tr('notOfficial', lang)} {tr('call1090', lang)}.</p>
    </>
  );
}

// ================================================================ maps
function useMiniMap(el: React.RefObject<HTMLDivElement | null>, zoom: number, interactive: boolean) {
  const { status, person } = usePhone();
  const map = useRef<MLMap | null>(null);
  const home = person ? [person.home_lon, person.home_lat] : status?.union ? [status.union.lon, status.union.lat] : null;
  useEffect(() => {
    if (!el.current || !home) return;
    let m: MLMap;
    try { m = createMap(el.current, { base: 'light', center: home as [number, number], zoom, interactive, attribution: interactive }); } catch { return; }
    map.current = m;
    whenReady(m, () => {
      const km = person?.radar_km ?? 1;
      m.addSource('ring', { type: 'geojson', data: circle(home[0]!, home[1]!, km * 1000) as never });
      m.addLayer({ id: 'ring', type: 'line', source: 'ring', paint: { 'line-color': '#2e7d32', 'line-width': 2.5, 'line-dasharray': [1.5, 1.5] } });
      const pin = document.createElement('div');
      pin.innerHTML = '<svg width="34" height="34" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#0B6E7F" stroke="#fff" stroke-width="2"/><path d="M7 12 12 8l5 4M8.5 11v5h7v-5" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>';
      new maplibregl.Marker({ element: pin }).setLngLat(home as [number, number]).addTo(m);
      const r = status?.radar;
      if (r?.overlay_url) setImage(m, 'nw', r.overlay_url, 0.95, 'ring', r.overlay_bounds ?? undefined);
    });
    const ro = new ResizeObserver(() => m.resize());
    ro.observe(el.current);
    return () => { ro.disconnect(); m.remove(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [home?.[0], home?.[1], status?.radar?.overlay_url]);
  return map;
}

function HomeMap() {
  const el = useRef<HTMLDivElement>(null);
  const { go, lang } = usePhone();
  useMiniMap(el, 11.6, false);
  return (
    <button className="ph-map" onClick={() => go({ name: 'map' })} aria-label={tr('map', lang)} style={{ padding: 0, display: 'block', width: '100%' }}>
      <div ref={el} style={{ position: 'absolute', inset: 0 }} />
      <MapLegend />
    </button>
  );
}

function MapLegend() {
  const { lang, person } = usePhone();
  return (
    <div style={{ position: 'absolute', left: 8, bottom: 8, background: 'rgba(255,255,255,.92)', borderRadius: 10, padding: '4px 8px', fontSize: '.72em', display: 'flex', gap: 10, fontWeight: 600, zIndex: 2 }}>
      <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}><span className="sw" style={{ background: 'var(--water)', width: 10, height: 10 }} />{tr('legendNewWater', lang)}</span>
      <span style={{ display: 'inline-flex', gap: 4, alignItems: 'center' }}><span style={{ width: 12, height: 0, borderTop: '2.5px dashed #2e7d32' }} />{sayT.km(person?.radar_km ?? 1, lang)}</span>
    </div>
  );
}

export function MapScreen() {
  const { lang, back, status, setSpeakText } = usePhone();
  const el = useRef<HTMLDivElement>(null);
  const map = useMiniMap(el, 11.2, true);
  const [view, setView] = useState<'simple' | 'radar'>('simple');
  const date = status?.radar ? new Date(status.radar.pass_utc).toISOString().slice(0, 10) : null;
  useEffect(() => {
    const m = map.current;
    if (!m) return;
    whenReady(m, () => setGibs(m, 'nisar', view === 'radar' ? GIBS.nisar! : null, date, 1, 'nw'));
  }, [view, date, map]);
  setSpeakText(`${tr('map', 'bn')}। ${tr('legendNewWater', 'bn')}। ${tr('gapNote', 'bn')}`, `${tr('map', 'en')}. ${tr('legendNewWater', 'en')}. ${tr('gapNote', 'en')}`);
  return (
    <>
      <button className="ph-back" onClick={back}><Icon name="back" size={18} /> {tr('back', lang)}</button>
      <h2>{tr('map', lang)}</h2>
      <div className="seg" role="group" aria-label={tr('map', lang)}>
        <button aria-pressed={view === 'simple'} onClick={() => setView('simple')}>{tr('viewSimple', lang)}</button>
        <button aria-pressed={view === 'radar'} onClick={() => setView('radar')}>{tr('viewRadar', lang)}</button>
      </div>
      <div className="ph-map" style={{ height: 'calc(340px * var(--s))' }}>
        <div ref={el} style={{ position: 'absolute', inset: 0 }} />
        <MapLegend />
      </div>
      <p className="ph-note">{view === 'radar' ? T(lang, 'নাসা-ইসরো NISAR রাডার ছবি (NASA GIBS থেকে)। পানি কালো দেখায়।', 'NASA-ISRO NISAR radar picture (from NASA GIBS). Water looks dark.') /* NEW */ : T(lang, 'নীল: রাডারে দেখা নতুন পানি, যা ১৮ জুন শুকনো ছিল। সবুজ বৃত্ত: আপনার দূরত্ব।', 'Blue: new water seen by radar that was dry on 18 June. Green circle: your distance.') /* NEW */}</p>
      <p className="ph-note">{tr('gapNote', lang)}</p>
    </>
  );
}

// ================================================================ alert
function HoldButton({ kind, label, onDone, chosen }: { kind: 'safe' | 'help'; label: string; onDone: () => void; chosen: boolean }) {
  const [p, setP] = useState(0);
  const t = useRef<number | null>(null);
  const start = useRef(0);
  const run = () => {
    start.current = performance.now();
    const step = () => {
      const v = Math.min(1, (performance.now() - start.current) / 1200);
      setP(v);
      if (v >= 1) { t.current = null; setP(0); onDone(); return; }
      t.current = requestAnimationFrame(step);
    };
    t.current = requestAnimationFrame(step);
  };
  const stop = () => { if (t.current) cancelAnimationFrame(t.current); t.current = null; setP(0); };
  return (
    <button className={`ph-hold ${kind} ${chosen ? 'chosen' : ''}`} onPointerDown={(e) => { (e.target as HTMLElement).setPointerCapture?.(e.pointerId); run(); }} onPointerUp={stop} onPointerLeave={stop} onPointerCancel={stop}
      onKeyDown={(e) => { if ((e.key === 'Enter' || e.key === ' ') && !t.current) { e.preventDefault(); run(); } }} onKeyUp={stop} onContextMenu={(e) => e.preventDefault()}
      aria-label={`${label}. Press and hold`}>
      <span className="fill" style={{ transform: `scaleX(${p})` }} />
      <Icon name={kind === 'safe' ? 'check' : 'help'} size={26} /> {label}
    </button>
  );
}

export function AlertScreen({ rid }: { rid: string }) {
  const { lang, back, go, deviceId, say, person, refresh, setSpeakText, embedded } = usePhone();
  const [a, setA] = useState<AlertOut | null>(null);
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const spoke = useRef(false);
  useEffect(() => { phoneApi.alert(rid).then(setA).catch((e) => setErr(String(e.message))); }, [rid]);
  useEffect(() => {
    if (!a || spoke.current) return;
    spoke.current = true;
    if (person?.mode?.listen || embedded) say(full(a, 'bn'), full(a, 'en'));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a]);
  if (err) return <p className="ph-note">{tr('alertMissing', lang)}</p>;
  if (!a) return <p className="ph-note">{tr('loading', lang)}</p>;
  setSpeakText(full(a, 'bn'), full(a, 'en'));
  const answer = async (r: 'safe' | 'help') => {
    setSending(true);
    try {
      const out = await phoneApi.reply(rid, deviceId, r, 'in_app');
      setA(out);
      say(tr(r === 'safe' ? 'replySafeGot' : 'replyHelpGot', 'bn'), tr(r === 'safe' ? 'replySafeGot' : 'replyHelpGot', 'en'));
      void refresh();
    } catch (e) {
      setErr(String((e as Error).message));
    } finally { setSending(false); }
  };
  const v = a.values;
  const msg = lang === 'bn' ? a.message_bn : a.message_en;
  return (
    <>
      <button className="ph-back" onClick={back}><Icon name="back" size={18} /> {tr('back', lang)}</button>
      <section className="ph-alert-top" role="alert">
        <div className="w"><StatusShape status="alert" size={34} /> {tr('alert', lang)}{a.replay && <span className="ph-pill" style={{ background: 'rgba(255,255,255,.2)', color: '#fff', minHeight: 26, fontSize: '.55em' }}>{tr('replayShort', lang)}</span>}</div>
        <div className="ph-msg">{msg}</div>
      </section>
      {a.rule === 'radar' && v.walk_minutes != null && (
        <div className="ph-walk">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="var(--danger)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><circle cx="13" cy="4" r="2" /><path d="M9 20l3-6 3 3v4M7 10l4-3 4 3 3 1M11 7l-1 6" /></svg>
          <div>
            <div className="big">{num(v.walk_minutes, lang)} {tr('minutes', lang)}</div>
            <div className="ph-note">{sayT.walkOnly(v.walk_minutes, lang)} · {num(v.distance_m, lang)} {tr('metre', lang)}</div>
          </div>
          <span className="ph-chip" style={{ marginLeft: 'auto' }}>{tr(a.confidence, lang)}</span>
        </div>
      )}
      {a.reply ? (
        <div className="ph-card" style={{ borderColor: a.reply === 'help' ? 'var(--danger)' : 'var(--safe)', borderWidth: 2 }} role="status">
          <b>{tr(a.reply === 'safe' ? 'replySafeGot' : 'replyHelpGot', lang)}</b>
          <div className="ph-note" style={{ marginTop: 4 }}>{T(lang, 'উত্তর বদলাতে নিচের বোতাম চেপে ধরুন।', 'To change your answer, press and hold the other button.') /* NEW */}</div>
        </div>
      ) : (
        <p className="ph-note" style={{ margin: 0 }}>{tr('holdHint', lang)}</p>
      )}
      <div className="stack" style={{ gap: 10, opacity: sending ? 0.6 : 1 }}>
        <HoldButton kind="safe" label={tr('safe', lang)} onDone={() => void answer('safe')} chosen={a.reply === 'safe'} />
        <HoldButton kind="help" label={tr('needHelp', lang)} onDone={() => void answer('help')} chosen={a.reply === 'help'} />
      </div>
      <div>
        <div className="ph-area-k" style={{ marginBottom: 6 }}>{tr('whatToDo', lang)}</div>
        <ul className="ph-todo">
          <li><Icon name="arrow" size={18} />{tr('todo1', lang)}</li>
          <li><Icon name="drop" size={18} />{tr('todo2', lang)}</li>
          <li><Icon name="phone" size={18} />{tr('todo3', lang)}</li>
        </ul>
      </div>
      {a.approved_by && a.approved_utc && <p className="ph-note" style={{ margin: 0 }}><Icon name="shield" size={14} style={{ display: 'inline', verticalAlign: '-2px' }} /> {sayT.approvedBy(a.approved_by, a.approved_utc, lang)}</p>}
      <div className="row" style={{ gap: 8 }}>
        <button className="ph-big ghost" style={{ flex: 1 }} onClick={() => go({ name: 'evidence', rid })}><Icon name="receipt" size={18} /> {tr('seeEvidence', lang)}</button>
        {a.channels.includes('call_sim') || embedded ? <button className="ph-big ghost" style={{ flex: 1 }} onClick={() => go({ name: 'call', rid })}><Icon name="phone" size={18} /> {T(lang, 'ফোন কল (ডেমো)', 'Phone call (demo)')}</button> : null}
      </div>
      <p className="ph-official">{lang === 'bn' ? a.not_official_bn : a.not_official_en}</p>
    </>
  );
}

function full(a: AlertOut, lang: Lang) {
  return `${lang === 'bn' ? a.message_bn : a.message_en} ${tr('pressKeys', lang)} ${tr('notOfficial', lang)} ${tr('call1090', lang)}`;
}

// ================================================================ evidence
export function EvidenceScreen({ rid }: { rid: string }) {
  const { lang, back, setSpeakText, person } = usePhone();
  const [e, setE] = useState<EvidenceOut | null>(null);
  const [side, setSide] = useState(1);
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<MLMap | null>(null);
  useEffect(() => { phoneApi.evidence(rid).then(setE).catch(() => undefined); }, [rid]);
  useEffect(() => {
    if (!e || !el.current || !person || !e.overlays.length) return;
    const m = createMap(el.current, { base: 'light', center: [person.home_lon, person.home_lat], zoom: 11.3, interactive: true });
    map.current = m;
    whenReady(m, () => {
      e.overlays.forEach((o, i) => setImage(m, o.id, o.url, i === 1 ? 0.95 : 0, 'labels', o.bounds));
      new maplibregl.Marker({ color: '#0B6E7F' }).setLngLat([person.home_lon, person.home_lat]).addTo(m);
    });
    return () => m.remove();
  }, [e, person]);
  useEffect(() => {
    const m = map.current;
    if (!m || !e) return;
    whenReady(m, () => e.overlays.forEach((o, i) => m.getLayer(o.id) && m.setPaintProperty(o.id, 'raster-opacity', i === side ? 0.95 : 0)));
  }, [side, e]);
  if (!e) return <p className="ph-note">{tr('loading', lang)}</p>;
  setSpeakText(e.rows.map((r) => `${r.label_bn}: ${r.value_bn}`).join('। '), e.rows.map((r) => `${r.label_en}: ${r.value_en}`).join('. '));
  const rc = e.receipt;
  return (
    <>
      <button className="ph-back" onClick={back}><Icon name="back" size={18} /> {tr('back', lang)}</button>
      <h2>{tr('evidence', lang)}</h2>
      <div className="ph-card stack" style={{ gap: 10 }}>
        {e.rows.map((r) => (
          <div key={r.key}>
            <div className="ph-area-k">{lang === 'bn' ? r.label_bn : r.label_en}</div>
            <div style={{ fontWeight: 600 }}>{lang === 'bn' ? r.value_bn : r.value_en}</div>
          </div>
        ))}
      </div>
      {e.overlays.length > 0 && (
        <>
          <div className="seg" role="group" aria-label="Radar pictures">
            {e.overlays.map((o, i) => <button key={o.id} aria-pressed={side === i} onClick={() => setSide(i)}>{i === 0 ? tr('radarBefore', lang) : i === 1 ? tr('radarAfter', lang) : tr('legendNewWater', lang)}</button>)}
          </div>
          <div className="ph-map" style={{ height: 'calc(220px * var(--s))' }}><div ref={el} style={{ position: 'absolute', inset: 0 }} /></div>
          <p className="ph-note" style={{ margin: 0 }}>{e.overlays[side]?.label}</p>
        </>
      )}
      <details className="ph-card">
        <summary style={{ fontWeight: 700, cursor: 'pointer' }}>{tr('receipt', lang)} · {tr('receiptHint', lang)}</summary>
        <dl className="kv" style={{ marginTop: 10, fontSize: '.78em' }}>
          {rc.input?.granule_id && (<><dt>Granule</dt><dd className="mono">{rc.input.granule_id}</dd></>)}
          {rc.input?.cmr_id && (<><dt>NASA CMR</dt><dd className="mono">{rc.input.cmr_id}</dd></>)}
          {rc.input?.acquired_utc && (<><dt>Acquired</dt><dd>{rc.input.acquired_utc}</dd></>)}
          {rc.input?.published_utc && (<><dt>Published</dt><dd>{rc.input.published_utc}</dd></>)}
          {rc.input?.processing_level && (<><dt>Level</dt><dd>{rc.input.processing_level}</dd></>)}
          {rc.method?.water_rule && (<><dt>Rule</dt><dd>{rc.method.water_rule}</dd></>)}
          {rc.method?.tested_at_db && (<><dt>Tested at</dt><dd>{rc.method.tested_at_db.join(', ')} dB</dd></>)}
          {rc.aoi_result?.new_water_km2_range && (<><dt>Whole reach</dt><dd>{rc.aoi_result.new_water_km2_range.join('–')} km² new water</dd></>)}
          <dt>Rule version</dt><dd>{rc.rule} {rc.rule_version} · code {rc.code_version}</dd>
          <dt>As of</dt><dd>{rc.as_of_utc}{rc.replay ? ' (REPLAY)' : ''}</dd>
        </dl>
      </details>
      <p className="ph-official">{lang === 'bn' ? e.not_official_bn : e.not_official_en}</p>
    </>
  );
}

// ================================================================ rain
export function RainScreen() {
  const { lang, back, deviceId, setSpeakText } = usePhone();
  const [d, setD] = useState<Awaited<ReturnType<typeof phoneApi.rain>> | null>(null);
  useEffect(() => { phoneApi.rain(deviceId).then(setD).catch(() => undefined); }, [deviceId]);
  if (!d) return <p className="ph-note">{tr('loading', lang)}</p>;
  const max = Math.max(d.limit_mm * 1.15, ...d.days.map((x) => x.mm), 10);
  const last = d.days[d.days.length - 1];
  setSpeakText(last ? `${tr('rainTitle', 'bn')}: ${sayT.rain(last.mm, d.limit_mm, 'bn')}` : tr('rainNone', 'bn'), last ? `${tr('rainTitle', 'en')}: ${sayT.rain(last.mm, d.limit_mm, 'en')}` : tr('rainNone', 'en'));
  return (
    <>
      <button className="ph-back" onClick={back}><Icon name="back" size={18} /> {tr('back', lang)}</button>
      <h2>{tr('rainTile', lang)}</h2>
      <div className="ph-card">
        <div style={{ position: 'relative', height: 180, display: 'flex', alignItems: 'flex-end', gap: 8, paddingTop: 10 }}>
          <div style={{ position: 'absolute', left: 0, right: 0, bottom: `${(d.limit_mm / max) * 170}px`, borderTop: '2px dashed var(--danger)' }}>
            <span style={{ position: 'absolute', right: 0, top: -20, fontSize: '.72em', color: 'var(--danger)', fontWeight: 700 }}>{tr('yourLevel', lang)} {sayT.mm(d.limit_mm, lang)}</span>
          </div>
          {d.days.map((x) => (
            <div key={x.date} style={{ flex: 1, display: 'grid', justifyItems: 'center', gap: 4 }}>
              <span style={{ fontSize: '.7em', fontWeight: 700 }}>{num(Math.round(x.mm), lang)}</span>
              <div style={{ width: '100%', height: `${Math.max(2, (x.mm / max) * 150)}px`, background: x.mm >= d.limit_mm ? 'var(--danger)' : 'var(--river)', borderRadius: 6 }} />
              <span style={{ fontSize: '.66em', color: 'var(--ink-3)' }}>{when(x.date + 'T06:00:00Z', lang, false).split(' ').slice(0, 2).join(' ')}</span>
            </div>
          ))}
        </div>
      </div>
      {last && <p style={{ fontWeight: 700, margin: 0 }}>{last.mm >= d.limit_mm ? tr('rainOver', lang) : tr('rainUnder', lang)} · {sayT.rain(last.mm, d.limit_mm, lang)}</p>}
      <p className="ph-note">{d.source ?? ''}</p>
      <p className="ph-note">{T(lang, 'পুরো এলাকার জন্য দিনে একটি মান (সবচেয়ে বেশি বৃষ্টির ঘর)।', d.note) /* NEW */}</p>
    </>
  );
}

// ================================================================ settings
export function SettingsScreen() {
  const { lang, back, person, deviceId, refresh, setSpeakText } = usePhone();
  const [p, setP] = useState(person);
  const [saved, setSaved] = useState<string | null>(null);
  useEffect(() => setP(person), [person]);
  setSpeakText(`${tr('whichMonths', 'bn')} ${tr('howMuchRain', 'bn')}`, `${tr('whichMonths', 'en')} ${tr('howMuchRain', 'en')}`);
  if (!p) return <p className="ph-note">{tr('loading', lang)}</p>;
  const save = async () => {
    try {
      await phoneApi.putPerson(deviceId, { display_name: p.display_name, union_id: p.union_id, home_lat: p.home_lat, home_lon: p.home_lon, months: p.months, rain_on: p.rain_on, rain_mm: p.rain_mm, river_on: p.river_on, radar_on: p.radar_on, radar_km: p.radar_km, channels: p.channels, email: p.email, phone: p.phone, mode: p.mode, consent: true });
      setSaved(tr('saved', lang));
      void refresh();
    } catch (e) { setSaved(String((e as Error).message)); }
  };
  const custom = p.rain_mm !== 76 && p.rain_mm !== 152;
  return (
    <>
      <button className="ph-back" onClick={back}><Icon name="back" size={18} /> {tr('back', lang)}</button>
      <h2>{tr('myAlerts', lang)}</h2>
      <div className="ph-card stack" style={{ gap: 10 }}>
        <b>{tr('whichMonths', lang)}</b>
        <div className="ph-months">
          {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
            <button key={m} aria-pressed={p.months.includes(m)} onClick={() => setP({ ...p, months: p.months.includes(m) ? (p.months.length > 1 ? p.months.filter((x) => x !== m) : p.months) : [...p.months, m].sort((a, b) => a - b) })}>{monthName(m, lang)}</button>
          ))}
        </div>
      </div>
      <div className="ph-card stack" style={{ gap: 8 }}>
        <b>{tr('howMuchRain', lang)}</b>
        <button className="ph-opt" aria-pressed={p.rain_mm === 76} onClick={() => setP({ ...p, rain_mm: 76 })}>{tr('rain3', lang)} · {sayT.mm(76, lang)}</button>
        <button className="ph-opt" aria-pressed={p.rain_mm === 152} onClick={() => setP({ ...p, rain_mm: 152 })}>{tr('rain6', lang)} · {sayT.mm(152, lang)}</button>
        <label className="ph-opt" style={{ display: 'grid', gap: 6 }} aria-pressed={custom}>
          <span>{tr('rainCustom', lang)}: <b>{sayT.mm(p.rain_mm, lang)}</b></span>
          <input type="range" min={10} max={300} step={5} value={p.rain_mm} onChange={(e) => setP({ ...p, rain_mm: +e.target.value })} aria-label={tr('rainCustom', lang)} />
        </label>
      </div>
      <div className="ph-card">
        <label className="ph-switch">{tr('radarSwitch', lang)}<input type="checkbox" checked={p.radar_on} onChange={(e) => setP({ ...p, radar_on: e.target.checked })} /></label>
        <label style={{ display: 'grid', gap: 4, fontSize: '.9em', fontWeight: 600 }}>
          {tr('radarDistance', lang)}: {sayT.km(p.radar_km, lang)}
          <input type="range" min={0.2} max={5} step={0.1} value={p.radar_km} onChange={(e) => setP({ ...p, radar_km: +e.target.value })} />
        </label>
        <label className="ph-switch">{tr('riverSwitch', lang)}<input type="checkbox" checked={p.river_on} onChange={(e) => setP({ ...p, river_on: e.target.checked })} /></label>
        <label className="ph-switch">{tr('ruleRain', lang)}<input type="checkbox" checked={p.rain_on} onChange={(e) => setP({ ...p, rain_on: e.target.checked })} /></label>
      </div>
      <button className="ph-big primary" onClick={() => void save()}>{tr('save', lang)}</button>
      {saved && <p className="ph-note" role="status">{saved}</p>}
      <p className="ph-note">{tr('privacy', lang)}</p>
    </>
  );
}

// ================================================================ simulated call
export function CallScreen({ rid }: { rid: string }) {
  const { lang, back, deviceId, say, refresh } = usePhone();
  const [a, setA] = useState<AlertOut | null>(null);
  const [state, setState] = useState<'ringing' | 'talking' | 'done'>('ringing');
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => { phoneApi.alert(rid).then(setA).catch(() => undefined); }, [rid]);
  const play = () => a && say(full(a, 'bn'), full(a, 'en'));
  const key = async (k: string) => {
    if (!a) return;
    if (k === '9') return play();
    if (k === '0') { setNote(tr('call1090', lang)); return say(tr('call1090', 'bn'), tr('call1090', 'en')); }
    const r = k === '1' ? 'safe' : 'help';
    await phoneApi.reply(rid, deviceId, r, 'call_sim').catch(() => undefined);
    setState('done');
    setNote(tr(r === 'safe' ? 'replySafeGot' : 'replyHelpGot', lang));
    say(tr(r === 'safe' ? 'replySafeGot' : 'replyHelpGot', 'bn'), tr(r === 'safe' ? 'replySafeGot' : 'replyHelpGot', 'en'));
    void refresh();
  };
  return (
    <div className="ph-call" role="dialog" aria-label={T(lang, 'ফোন কল, ডেমো', 'Phone call, demo')}>
      <span className="badge-sim">{T(lang, 'ডেমো: ফোন কলের সিমুলেশন', 'Demo: simulated phone call')}</span>
      <div style={{ width: 64, height: 64, borderRadius: 32, background: 'var(--river)', display: 'grid', placeItems: 'center', marginTop: 6, flex: 'none' }}><Icon name="phone" size={30} /></div>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.5em', fontWeight: 700 }}>{tr('appName', lang)}</div>
      <div style={{ opacity: 0.75 }}>{state === 'ringing' ? T(lang, 'কল আসছে…', 'Incoming call…') : state === 'talking' ? T(lang, 'কথা চলছে', 'In call') : T(lang, 'কল শেষ', 'Call ended')}</div>
      {state === 'ringing' ? (
        <div className="row" style={{ gap: 40, marginTop: 'auto' }}>
          <button className="ph-key k2" onClick={back} aria-label="Decline"><Icon name="x" size={28} /></button>
          <button className="ph-key k1" onClick={() => { setState('talking'); play(); }} aria-label="Answer"><Icon name="phone" size={28} /></button>
        </div>
      ) : (
        <>
          {a && <p style={{ textAlign: 'center', fontSize: '.92em', color: '#cfe6ec', margin: 0 }}>{lang === 'bn' ? a.message_bn : a.message_en}</p>}
          {note && <p role="status" style={{ textAlign: 'center', fontWeight: 700, margin: 0 }}>{note}</p>}
          <div className="ph-keys">
            {[['1', T(lang, 'নিরাপদ', 'safe')], ['2', T(lang, 'সাহায্য', 'help')], ['9', T(lang, 'আবার', 'repeat')], ['0', '1090']].map(([k, s], i) => k ? (
              <button key={k} className={`ph-key k${k}`} onClick={() => void key(k)} disabled={state === 'done' && (k === '1' || k === '2')}>{lang === 'bn' ? num(+k, 'bn') : k}<small>{s}</small></button>
            ) : <span key={i} />)}
          </div>
          <button className="ph-big danger" style={{ width: '100%', position: 'sticky', bottom: 0, flex: 'none', boxShadow: '0 -10px 18px #0a1821' }} onClick={back}>{T(lang, 'কল শেষ করুন', 'End call')}</button>
        </>
      )}
    </div>
  );
}

// ================================================================ help
export function HelpSheet({ onClose }: { onClose: () => void }) {
  const { lang, status, go } = usePhone();
  const a = status?.active_alert;
  return (
    <div className="ph-sheet-bg" onClick={onClose}>
      <div className="ph-sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-label={tr('help', lang)}>
        <h2 style={{ fontSize: '1.3em' }}>{tr('help', lang)}</h2>
        {a && !a.reply && <button className="ph-big danger" onClick={() => { onClose(); go({ name: 'alert', rid: a.recipient_id }); }}><Icon name="help" size={20} /> {tr('needHelp', lang)}</button>}
        <a className="ph-big primary" href="tel:1090"><Icon name="phone" size={20} /> {tr('call1090Button', lang)}</a>
        <a className="ph-big ghost" href="tel:999"><Icon name="phone" size={20} /> {T(lang, 'জাতীয় জরুরি সেবা ৯৯৯', 'National emergency 999')}</a>
        <p className="ph-note">{tr('helpAbout', lang)}</p>
        <p className="ph-note">{tr('sourceLine', lang)}</p>
        <button className="ph-big ghost" onClick={onClose}>{tr('close', lang)}</button>
      </div>
    </div>
  );
}
