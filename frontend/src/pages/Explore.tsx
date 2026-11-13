/** Explorer: every pass, every layer, NASA live layers, compare, union ranking, and a report for any point. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import type { Map as MLMap, MapMouseEvent } from 'maplibre-gl';
import { DistanceSpark } from '../components/charts';
import { Nav } from '../components/Chrome';
import { Compare } from '../components/Compare';
import { Icon } from '../components/Icon';
import { maplibregl, setGibs, setImage, setVisible, type BaseKind, baseStyle, whenReady, fitReach } from '../components/map';
import { MapView } from '../components/MapView';
import { phoneApi, type PointReport } from '../lib/api';
import { dataUrl, HEAD_PAIR, loadJSON, useData, type Processed, type Season, type UnionRow } from '../lib/data';
import { dShort, dTime, n0, n1, pDay, pLong, range, ymd } from '../lib/format';
import { GIBS, isoDay, powerRain } from '../lib/nasa';
import { useL } from '../lib/i18n';

type Ours = 'water' | 'newwater' | 'bankloss' | 'banklines' | 'sites' | 'freq' | 'hand' | 'river';
type Nasa = 'nisar' | 'opera' | 'imerg' | 'modisflood' | 'rtc';
type Bg = BaseKind | 's2' | 'l89';
type Metric = 'none' | 'bank' | 'near' | 'newwater';

const OURS: [Ours, string, string][] = [
  ['water', 'Water on this pass', 'var(--water)'],
  ['newwater', 'New water since the baseline pass', '#7fe9ff'],
  ['bankloss', 'Riverbank lost, Jun → Oct (confirmed)', 'var(--bankloss)'],
  ['banklines', 'Bank lines (16 Oct)', '#ffe08a'],
  ['sites', 'Bank-loss sites S01…', 'var(--bankloss)'],
  ['freq', 'Times under water, 10 passes', '#5aa0ff'],
  ['hand', 'Height above the river (HAND)', '#c9a96e'],
  ['river', 'Permanent river channel', '#4f7d96'],
];
const NASA: [Nasa, string][] = [
  ['nisar', 'NISAR radar picture (this pass date)'],
  ['opera', 'OPERA water, Sentinel-1 (same date)'],
  ['rtc', 'Sentinel-1 C-band radar (same date)'],
  ['modisflood', 'MODIS flood, 2-day (optical)'],
  ['imerg', 'IMERG rain rate (daily)'],
];

export default function Explore() {
  const { data: season } = useData<Season>('season.json');
  const { data: unions } = useData<UnionRow[]>('unions.json');
  const [params] = useSearchParams();
  if (!season || !unions) return (<><Nav /><div style={{ height: 'calc(100vh - var(--nav-h))', background: 'var(--night)' }} /></>);
  return <Explorer season={season} unions={unions} startBank={params.get('view') === 'bank'} />;
}

const OURS_BN: Record<string, string> = {"Water on this pass": "এই ছবিতে পানি", "New water since the baseline pass": "শুরুর ছবির পর নতুন পানি", "Riverbank lost, Jun → Oct (confirmed)": "নদীভাঙন, জুন → অক্টোবর (নিশ্চিত)", "Bank lines (16 Oct)": "পাড়ের রেখা (১৬ অক্টোবর)", "Bank-loss sites S01…": "ভাঙনের জায়গা S01…", "Times under water, 10 passes": "কতবার পানির নিচে, ১০টি ছবি", "Height above the river (HAND)": "নদী থেকে উচ্চতা (HAND)", "Permanent river channel": "স্থায়ী নদীখাত", "NISAR radar picture (this pass date)": "NISAR রাডার ছবি (এই তারিখ)", "OPERA water, Sentinel-1 (same date)": "OPERA পানি, সেন্টিনেল-১ (একই তারিখ)", "Sentinel-1 C-band radar (same date)": "সেন্টিনেল-১ সি-ব্যান্ড রাডার (একই তারিখ)", "MODIS flood, 2-day (optical)": "MODIS বন্যা, ২ দিন (ক্যামেরা)", "IMERG rain rate (daily)": "IMERG বৃষ্টি (দৈনিক)"};

function Explorer({ season, unions, startBank }: { season: Season; unions: UnionRow[]; startBank: boolean }) {
  const { L } = useL();
  const tl = (t: string) => L(t, OURS_BN[t] ?? t);
  const passes = season.processed;
  const [sel, setSel] = useState('069A_20260724');
  const [cmpA, setCmpA] = useState('069A_20260618');
  const [cmpB, setCmpB] = useState('069A_20261016');
  const [mode, setMode] = useState<'one' | 'compare'>('one');
  const [cmpShow, setCmpShow] = useState<'water' | 'radar'>('water');
  const [ours, setOurs] = useState<Record<Ours, boolean>>({ water: !startBank, newwater: false, bankloss: startBank, banklines: startBank, sites: startBank, freq: false, hand: false, river: false });
  const [nasa, setNasa] = useState<Nasa | null>(null);
  const [bg, setBg] = useState<Bg>('s2');
  const [metric, setMetric] = useState<Metric>(startBank ? 'bank' : 'none');
  const [table, setTable] = useState(startBank);
  const [point, setPoint] = useState<{ lat: number; lon: number } | null>(null);
  const [site, setSite] = useState<Record<string, any> | null>(null);
  const [panel, setPanel] = useState(true);
  const map = useRef<MLMap | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  const p = passes.find((x) => x.key === sel)!;

  // ---- layers on the single map
  const apply = (m: MLMap) => {
    const pics = season.pictures;
    const bgImg = bg === 's2' ? pics.optical['scene_S2_20261015']?.url : bg === 'l89' ? pics.optical['scene_L89_20260509']?.url : null;
    setImage(m, 'bgimg', bgImg ? dataUrl(bgImg) : null, 0.9, 'freq');
    setImage(m, 'freq', ours.freq && pics.other.times_under_water ? dataUrl(pics.other.times_under_water) : null, 0.9, 'hand');
    setImage(m, 'hand', ours.hand && pics.other.hand ? dataUrl(pics.other.hand) : null, 0.8, 'river');
    setImage(m, 'river', ours.river && pics.other.river_khal ? dataUrl(pics.other.river_khal) : null, 0.85, 'water');
    setImage(m, 'water', ours.water && p.water_png ? dataUrl(p.water_png) : null, 0.92, 'newwater');
    setImage(m, 'newwater', ours.newwater && p.newwater_png ? dataUrl(p.newwater_png) : null, 1, 'bankloss');
    setImage(m, 'bankloss', ours.bankloss && pics.bankloss[HEAD_PAIR.id] ? dataUrl(pics.bankloss[HEAD_PAIR.id]!) : null, 1, 'gibs');
    const nd = isoDay(p.date);
    setGibs(m, 'gibs', nasa ? GIBS[nasa]! : null, nasa === 'imerg' || nasa === 'modisflood' ? isoDay(p.date) : nd, nasa === 'imerg' ? 0.75 : 0.95, 'freq');
    setVisible(m, 'banklines', ours.banklines);
    setVisible(m, 'sites-f', ours.sites);
    setVisible(m, 'sites-l', ours.sites);
    setVisible(m, 'unions-fill', metric !== 'none');
    if (metric !== 'none' && m.getLayer('unions-fill')) {
      const key = metric === 'bank' ? 'bank' : metric === 'near' ? 'near' : 'nw';
      const stops = metric === 'bank' ? [2, '#5c2a2a', 8, '#a83a32', 20, '#ff5a4e', 40, '#ffb0a8'] : metric === 'near' ? [10, '#3a3020', 100, '#8a6a20', 300, '#e0a630', 700, '#ffe08a'] : [1, '#123a4a', 4, '#1f6d8a', 8, '#2fa6cf', 15, '#a8ecff'];
      m.setPaintProperty('unions-fill', 'fill-color', ['case', ['==', ['get', key], null], 'rgba(0,0,0,0)', ['<', ['get', key], stops[0] as number], 'rgba(0,0,0,0)', ['interpolate', ['linear'], ['get', key], ...stops]]);
    }
  };

  const setupStatic = async (m: MLMap) => {
    m.addSource('bl', { type: 'geojson', data: dataUrl('geo/banklines.geojson') });
    m.addSource('sites', { type: 'geojson', data: dataUrl('geo/sites.geojson') });
    const ug = await loadJSON<any>('geo/unions.geojson');
    const by = new Map(unions.map((u) => [u.name_en, u]));
    for (const f of ug.features) {
      const u = by.get(f.properties.shapeName);
      f.properties.bank = u?.bank_loss_ha_range ? (u.bank_loss_ha_range[0]! + (u.bank_loss_ha_range[1] ?? 0)) / 2 : null;
      f.properties.near = u?.buildings_within_100m_of_retreating_bank ?? null;
      f.properties.nw = u?.new_water_km2_range ? (u.new_water_km2_range[0]! + (u.new_water_km2_range[1] ?? 0)) / 2 : null;
    }
    m.addSource('unions', { type: 'geojson', data: ug });
    // fixed order from bottom to top, all under the basemap labels
    for (const id of ['bgimg', 'freq', 'hand', 'river', 'water', 'newwater', 'bankloss']) setImage(m, id, dataUrl(season.pictures.water['069A_20260618']!), 0, 'labels');
    m.addLayer({ id: 'unions-fill', type: 'fill', source: 'unions', paint: { 'fill-color': 'rgba(0,0,0,0)', 'fill-opacity': 0.5 }, layout: { visibility: 'none' } }, 'freq');
    m.addLayer({ id: 'unions-line', type: 'line', source: 'unions', paint: { 'line-color': 'rgba(214,238,242,.28)', 'line-width': ['interpolate', ['linear'], ['zoom'], 9, 0.4, 13, 1.2] } }, 'labels');
    m.addLayer({ id: 'banklines', type: 'line', source: 'bl', paint: { 'line-color': '#ffe08a', 'line-width': 1.4 } });
    m.addLayer({ id: 'sites-f', type: 'fill', source: 'sites', paint: { 'fill-color': '#ff5a4e', 'fill-opacity': 0.35 } });
    m.addLayer({ id: 'sites-l', type: 'line', source: 'sites', paint: { 'line-color': '#ff5a4e', 'line-width': 2 } });
    m.on('click', 'sites-f', (e) => {
      const f = e.features?.[0];
      if (f) {
        e.preventDefault();
        setSite(f.properties as Record<string, any>);
        setPoint(null);
        setPanel(true);
      }
    });
    m.on('click', (e: MapMouseEvent & { defaultPrevented?: boolean }) => {
      if (e.defaultPrevented) return;
      setSite(null);
      setPoint({ lat: +e.lngLat.lat.toFixed(5), lon: +e.lngLat.lng.toFixed(5) });
      setPanel(true);
    });
    m.on('mouseenter', 'sites-f', () => (m.getCanvas().style.cursor = 'pointer'));
    m.on('mouseleave', 'sites-f', () => (m.getCanvas().style.cursor = ''));
    m.getCanvas().style.cursor = 'crosshair';
    apply(m);
  };

  useEffect(() => {
    if (map.current && mode === 'one') apply(map.current);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sel, ours, nasa, bg, metric, mode]);

  // basemap change: swap only the base sources
  useEffect(() => {
    const m = map.current;
    if (!m || mode !== 'one') return;
    const kind: BaseKind = bg === 'light' ? 'light' : bg === 'satellite' ? 'satellite' : 'dark';
    const st = baseStyle(kind);
    const src = m.getSource('base') as any;
    const lab = m.getSource('labels') as any;
    if (src?.setTiles) src.setTiles((st.sources.base as any).tiles);
    if (lab?.setTiles) lab.setTiles((st.sources.labels as any).tiles);
  }, [bg, mode]);

  // point marker
  useEffect(() => {
    const m = map.current;
    marker.current?.remove();
    if (!m || !point) return;
    const el = document.createElement('div');
    el.style.cssText = 'width:18px;height:18px;border-radius:50%;background:#fff;border:4px solid #ff5a4e;box-shadow:0 0 0 4px rgba(255,90,78,.3)';
    marker.current = new maplibregl.Marker({ element: el }).setLngLat([point.lon, point.lat]).addTo(m);
  }, [point]);

  const flyTo = (lon: number, lat: number, z = 12) => {
    map.current?.flyTo({ center: [lon, lat], zoom: z, duration: 900 });
    setPoint({ lat, lon });
    setSite(null);
    setPanel(true);
  };

  const legend = useMemo(() => {
    const out: [string, string, boolean?][] = [];
    for (const [k, t, c] of OURS) if (ours[k]) out.push([t, c]);
    if (nasa) out.push([NASA.find((x) => x[0] === nasa)![1], '#9ad1ff']);
    if (metric !== 'none') out.push([metric === 'bank' ? 'Union: bank lost (ha)' : metric === 'near' ? 'Union: buildings ≤100 m of a retreating bank' : 'Union: new water (km²)', '#e0a630']);
    return out;
  }, [ours, nasa, metric]);

  return (
    <>
      <Nav />
      <div className="ex dark-ui on-night">
        <aside className={`ex-side ${panel ? '' : 'collapsed'}`} aria-label="Map controls">
          <div className="ex-scroll">
            <h1 style={{ fontSize: '1.45rem', margin: 0 }}>{L('Radar explorer', 'রাডার মানচিত্র')}</h1>
            <p className="small" style={{ margin: '4px 0 14px' }}>{L(`Sirajganj–Kazipur reach of the Jamuna, ${season.aoi.grid_m} m grid. Click anywhere on the map for a point report.`, 'যমুনার সিরাজগঞ্জ–কাজীপুর অংশ, ২০ মিটার গ্রিড। কোনো জায়গার বিবরণ দেখতে মানচিত্রে ক্লিক করুন।')}</p>

            <div className="seg" role="group" aria-label="View" style={{ marginBottom: 14 }}>
              <button aria-pressed={mode === 'one'} onClick={() => setMode('one')}>{L('One pass', 'একটি ছবি')}</button>
              <button aria-pressed={mode === 'compare'} onClick={() => setMode('compare')}><Icon name="swap" size={14} /> {L('Compare two', 'দুটি তুলনা')}</button>
            </div>

            {mode === 'one' ? (
              <>
                <Label>{L('Radar pass', 'রাডার ছবি')}</Label>
                <PassChips passes={passes} sel={sel} onSel={setSel} />
                <PassCard p={p} />
              </>
            ) : (
              <>
                <Label>{L('Before (left)', 'আগে (বাঁয়ে)')}</Label>
                <PassChips passes={passes} sel={cmpA} onSel={setCmpA} />
                <Label>{L('After (right)', 'পরে (ডানে)')}</Label>
                <PassChips passes={passes} sel={cmpB} onSel={setCmpB} />
                <div className="seg" role="group" aria-label="Show" style={{ marginTop: 10 }}>
                  <button aria-pressed={cmpShow === 'water'} onClick={() => setCmpShow('water')}>Our water maps</button>
                  <button aria-pressed={cmpShow === 'radar'} onClick={() => setCmpShow('radar')}>NISAR picture (GIBS)</button>
                </div>
                {passes.find((x) => x.key === cmpA)?.track !== passes.find((x) => x.key === cmpB)?.track && (
                  <p className="callout warn small" style={{ marginTop: 10 }}>Different tracks see the river from different angles. We never compute change across tracks; this view is for looking only.</p>
                )}
              </>
            )}

            {mode === 'one' && (
              <>
                <Label>{L('Our NISAR analysis', 'আমাদের NISAR বিশ্লেষণ')}</Label>
                {OURS.map(([k, t, c]) => (
                  <label key={k} className="toggle">
                    <input type="checkbox" checked={ours[k]} onChange={(e) => setOurs((o) => ({ ...o, [k]: e.target.checked }))} />
                    <span className="sw" style={{ background: c }} /> {tl(t)}
                  </label>
                ))}
                <Label>{L('NASA live layers', 'নাসার লাইভ স্তর')} <span className="chip chip-live" style={{ padding: '0 7px', marginLeft: 6 }}>GIBS</span></Label>
                <label className="toggle"><input type="radio" name="nasa" checked={nasa === null} onChange={() => setNasa(null)} /> {L('None', 'কোনোটি নয়')}</label>
                {NASA.map(([k, t]) => (
                  <label key={k} className="toggle"><input type="radio" name="nasa" checked={nasa === k} onChange={() => setNasa(k)} /> {tl(t)}</label>
                ))}
                {nasa && <p className="tiny" style={{ color: 'var(--sky-3)', margin: '2px 0 0' }}>{GIBS[nasa]!.note} Date: {isoDay(p.date)}.</p>}
                <Label>{L('Unions', 'ইউনিয়ন')}</Label>
                <select className="input" value={metric} onChange={(e) => setMetric(e.target.value as Metric)} style={{ background: 'var(--night-3)', color: 'var(--sky)', borderColor: 'var(--night-line)' }}>
                  <option value="none">Outlines only</option>
                  <option value="bank">Colour by riverbank lost (ha)</option>
                  <option value="near">Colour by buildings near a retreating bank</option>
                  <option value="newwater">Colour by new water, Jun → Jul (km²)</option>
                </select>
                <button className="btn btn-ghost btn-sm" style={{ marginTop: 10, width: '100%' }} onClick={() => setTable((t) => !t)}>
                  <Icon name="users" size={15} /> {table ? L('Hide the union ranking', 'ইউনিয়নের তালিকা লুকান') : L('Show the union ranking', 'ইউনিয়নের তালিকা দেখুন')}
                </button>
                <Label>{L('Background', 'পটভূমি')}</Label>
                <div className="seg" role="group" aria-label="Background" style={{ flexWrap: 'wrap' }}>
                  {([['s2', 'Sentinel-2 · Oct'], ['l89', 'Landsat · May'], ['dark', 'Dark'], ['light', 'Light'], ['satellite', 'Satellite']] as [Bg, string][]).map(([k, t]) => (
                    <button key={k} aria-pressed={bg === k} onClick={() => setBg(k)}>{t}</button>
                  ))}
                </div>
              </>
            )}
          </div>
        </aside>

        <div className="ex-map">
          {mode === 'one' ? (
            <MapView label="Radar explorer map" style={{ position: 'absolute', inset: 0 }} onReady={(m) => { map.current = m; void setupStatic(m); }} padding={30}>
              {legend.length > 0 && (
                <div className="ex-legend legend">
                  {legend.map(([t, c]) => <span key={t}><span className="sw" style={{ background: c }} />{tl(t)}</span>)}
                </div>
              )}
            </MapView>
          ) : (
            <Compare
              key={`${cmpShow}`}
              label="Compare two NISAR passes"
              leftLabel={`Before · ${pDay(passes.find((x) => x.key === cmpA)!.acquired_utc)}`}
              rightLabel={`After · ${pDay(passes.find((x) => x.key === cmpB)!.acquired_utc)}`}
              style={{ position: 'absolute', inset: 0 }}
              deps={[cmpA, cmpB, cmpShow]}
              left={(m) => paintCompare(m, season, passes.find((x) => x.key === cmpA)!, cmpShow)}
              right={(m) => paintCompare(m, season, passes.find((x) => x.key === cmpB)!, cmpShow)}
            />
          )}
          {mode === 'compare' && <CompareNumbers a={passes.find((x) => x.key === cmpA)!} b={passes.find((x) => x.key === cmpB)!} />}
          <button className="ex-toggle btn btn-sm" onClick={() => setPanel((v) => !v)} aria-label={panel ? 'Hide the side panel' : 'Show the side panel'}>
            <Icon name={panel ? 'back' : 'layers'} size={16} />
          </button>
          {(point || site) && mode === 'one' && (
            <div className="ex-report fade-in">
              <button className="ex-close" onClick={() => { setPoint(null); setSite(null); }} aria-label="Close"><Icon name="x" size={18} /></button>
              {site ? <SiteCard s={site} /> : point && <PointCard lat={point.lat} lon={point.lon} passes={passes} />}
            </div>
          )}
          {table && mode === 'one' && <UnionTable unions={unions} metric={metric} onPick={(u) => flyTo(u.lon, u.lat, 12)} onClose={() => setTable(false)} />}
        </div>
      </div>
      <style>{`
        .ex{display:grid;grid-template-columns:360px 1fr;height:calc(100vh - var(--nav-h));height:calc(100dvh - var(--nav-h))}
        .ex-side{border-right:1px solid var(--night-line);background:var(--night);min-height:0;overflow:hidden}
        .ex-side.collapsed{display:none}
        .ex:has(.ex-side.collapsed){grid-template-columns:1fr}
        .ex-scroll{height:100%;overflow:auto;padding:18px 18px 40px}
        .ex-map{position:relative;min-height:0}
        .ex-legend{position:absolute;left:64px;top:12px;background:rgba(10,24,33,.88);border:1px solid var(--night-line);padding:9px 12px;border-radius:12px;color:var(--sky-2);max-width:min(520px,calc(100% - 24px));z-index:2}
        .ex-toggle{position:absolute;top:12px;left:12px;z-index:5;background:rgba(10,24,33,.88);color:var(--sky);border:1px solid var(--night-line);width:40px;padding:0}
        .ex-report{position:absolute;top:12px;right:12px;width:min(380px,calc(100% - 24px));max-height:calc(100% - 24px);overflow:auto;background:rgba(15,36,48,.97);border:1px solid var(--night-line);border-radius:var(--r-lg);padding:18px;z-index:6;box-shadow:0 20px 50px rgba(0,0,0,.4)}
        .ex-close{position:absolute;top:10px;right:10px;background:none;border:0;color:var(--sky-2);width:36px;height:36px;border-radius:10px}
        .ex-close:hover{background:rgba(255,255,255,.06)}
        .lbl{font:600 .72rem var(--font-body);letter-spacing:.12em;text-transform:uppercase;color:var(--sky-3);margin:18px 0 8px;display:flex;align-items:center}
        @media (max-width:860px){
          .ex{grid-template-columns:1fr;grid-template-rows:auto auto;height:auto}
          .ex-map{order:1;height:64vh;height:64dvh}
          .ex-side{order:2;border-right:0;border-top:1px solid var(--night-line);max-height:none}
          .ex-side.collapsed{display:block}
          .ex-scroll{height:auto}
          .ex-toggle{display:none}
          .ex-legend{left:12px;top:auto;bottom:12px}
          .ex-report{position:fixed;top:auto;left:0;right:0;bottom:0;width:100%;max-height:58vh;border-radius:22px 22px 0 0;z-index:60}
          .ex-table{position:fixed !important;left:0 !important;right:0 !important;bottom:0 !important;border-radius:22px 22px 0 0 !important;z-index:60 !important;max-height:70vh;overflow:auto}
        }
      `}</style>
    </>
  );
}

function paintCompare(m: MLMap, season: Season, p: Processed, show: 'water' | 'radar') {
  whenReady(m, () => {
    fitReach(m, 20);
    const opt = season.pictures.optical['scene_S2_20261015'];
    if (show === 'water') {
      setGibs(m, 'g', null, null);
      if (opt) setImage(m, 'bgimg', dataUrl(opt.url), 0.7);
      setImage(m, 'water', p.water_png ? dataUrl(p.water_png) : null, 0.95);
    } else {
      setImage(m, 'water', null);
      setImage(m, 'bgimg', null);
      setGibs(m, 'g', GIBS.nisar!, isoDay(p.date), 1);
    }
  });
}

/** The number the build guide asks for on screen: water area on each date and the change, with its assumptions. */
function CompareNumbers({ a, b }: { a: Processed; b: Processed }) {
  const same = a.track === b.track;
  const both = a.water_km2 != null && b.water_km2 != null;
  const delta = both ? b.water_km2! - a.water_km2! : null;
  return (
    <div className="cmp-num fade-in" role="status">
      {same && both ? (
        <>
          <div className="row" style={{ gap: 14, alignItems: 'baseline', flexWrap: 'wrap' }}>
            <span><span className="tiny">{pDay(a.acquired_utc)}</span><b>{n0(a.water_km2)} km²</b></span>
            <Icon name="arrow" size={18} />
            <span><span className="tiny">{pDay(b.acquired_utc)}</span><b>{n0(b.water_km2)} km²</b></span>
            <span className={`delta ${delta! >= 0 ? 'up' : 'down'}`}>{delta! >= 0 ? '+' : '−'}{n0(Math.abs(delta!))} km² {delta! >= 0 ? 'more water' : 'less water'}</span>
          </div>
          <div className="tiny" style={{ marginTop: 6 }}>Water seen by NISAR over the whole reach, track {a.track}, HH &lt; {a.threshold_db} dB after a 3×3 median filter. Each pass is also tested at ±1 dB (see the pass card). Two NISAR GCOV scenes, same track and geometry.</div>
        </>
      ) : (
        <div className="small">{same ? 'Whole-reach water area is computed for track 069A passes only; track 019D is a cross-check. Compare visually, or pick two 069A passes.' : 'Different tracks see the river from different angles, so no change number is computed. Pick two passes of the same track.'}</div>
      )}
      <style>{`.cmp-num{position:absolute;left:50%;transform:translateX(-50%);bottom:28px;z-index:5;width:min(620px,calc(100% - 24px));background:rgba(10,24,33,.92);border:1px solid var(--night-line);border-radius:var(--r-lg);padding:12px 16px;color:var(--sky-2)}
        .cmp-num b{display:block;font-family:var(--font-display);font-size:1.6rem;color:#fff;line-height:1}
        .cmp-num .tiny{color:var(--sky-3)}
        .cmp-num .delta{margin-left:auto;font-weight:700;padding:4px 10px;border-radius:6px}
        .cmp-num .delta.up{background:rgba(43,183,227,.18);color:#7fe2ff}
        .cmp-num .delta.down{background:rgba(91,191,122,.18);color:#9be3b0}`}</style>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return <div className="lbl">{children}</div>;
}

function PassChips({ passes, sel, onSel }: { passes: Processed[]; sel: string; onSel: (k: string) => void }) {
  return (
    <div className="row" style={{ gap: 6 }}>
      {passes.map((q) => (
        <button key={q.key} onClick={() => onSel(q.key)} aria-pressed={q.key === sel} className="chip"
          style={{ cursor: 'pointer', minHeight: 30, background: q.key === sel ? 'var(--water)' : undefined, color: q.key === sel ? 'var(--night)' : undefined, borderColor: q.track === '019D' ? 'rgba(197,111,164,.5)' : undefined }}>
          {pDay(q.acquired_utc)}{q.track === '019D' && <span style={{ opacity: 0.7 }}> D</span>}
        </button>
      ))}
    </div>
  );
}

function PassCard({ p }: { p: Processed }) {
  const lat = p.published_utc ? Math.round((new Date(p.published_utc).getTime() - new Date(p.acquired_utc).getTime()) / 3.6e6) : null;
  return (
    <div className="card" style={{ marginTop: 12, padding: 16 }}>
      <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.25rem', color: '#fff' }}>{pLong(p.acquired_utc)}</div>
      <div className="tiny" style={{ color: 'var(--sky-3)', marginBottom: 10 }}>{dTime(p.acquired_utc)} in Dhaka · track {p.track} {p.track === '069A' ? '(ascending)' : '(descending)'}</div>
      <dl className="kv" style={{ fontSize: '.84rem' }}>
        {p.water_km2 != null && (<><dt>Water</dt><dd>{n0(p.water_km2)} km² ({n0(p.water_outside_channel_km2)} beyond the channel)</dd></>)}
        <dt>New water</dt><dd>{p.new_water_km2 ? `${n0(p.new_water_km2.strict)}–${n0(p.new_water_km2.loose)} km² vs baseline` : 'baseline pass'}{p.range_within_25pct === false && <span className="chip chip-prov" style={{ marginLeft: 6, padding: '0 7px' }}>less sure</span>}</dd>
        <dt>Threshold</dt><dd>HH &lt; {p.threshold_db} dB, tested ±1 dB</dd>
        <dt>NASA delay</dt><dd>{lat != null ? `${lat} h (published ${dShort(p.published_utc!)})` : '–'}</dd>
        <dt>Data</dt><dd>{p.processing_level}</dd>
        <dt>CMR id</dt><dd className="mono">{p.cmr_id}</dd>
      </dl>
      <div className="row" style={{ gap: 8, marginTop: 10 }}>
        {p.cmr_id && <a className="btn btn-ghost btn-sm" href={`https://cmr.earthdata.nasa.gov/search/concepts/${p.cmr_id}.html`} target="_blank" rel="noreferrer"><Icon name="ext" size={14} /> NASA CMR record</a>}
        {p.granule_id && <a className="btn btn-ghost btn-sm" href={`https://search.asf.alaska.edu/#/?searchType=List%20Search&searchList=${encodeURIComponent(p.granule_id)}`} target="_blank" rel="noreferrer"><Icon name="ext" size={14} /> Find in ASF Vertex</a>}
      </div>
    </div>
  );
}

function PointCard({ lat, lon, passes }: { lat: number; lon: number; passes: Processed[] }) {
  const [r, setR] = useState<PointReport | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [rain, setRain] = useState<{ date: string; mm: number | null }[] | null>(null);
  useEffect(() => {
    setR(null); setErr(null); setRain(null);
    phoneApi.point(lat, lon).then(setR).catch((e) => setErr(String(e.message ?? e)));
    powerRain(lat, lon, 14).then(setRain).catch(() => setRain([]));
  }, [lat, lon]);
  const rows069 = r?.passes?.filter((x) => x.track === '069A').map((x) => ({ date: x.date, d: x.baseline ? null : x.dist_new_water_m?.mid ?? null })) ?? [];
  return (
    <div>
      <div className="lbl" style={{ marginTop: 0 }}>Point report</div>
      <div className="mono tiny" style={{ color: 'var(--sky-3)' }}>{lat.toFixed(4)}° N, {lon.toFixed(4)}° E</div>
      {err && <p className="small" style={{ color: 'var(--char)' }}>{err}</p>}
      {!r && !err && <p className="small">Asking the server…</p>}
      {r && !r.covered && <p className="small">{r.message}</p>}
      {r && r.covered && (
        <>
          <h3 style={{ margin: '6px 0 2px', color: '#fff' }}>{r.nearest_union?.name_en ?? 'Unknown union'}</h3>
          <div className="small" style={{ color: 'var(--sky-3)' }}>{r.nearest_union?.upazila_en} · nearest union centre</div>
          {r.in_permanent_river && <p className="callout small" style={{ marginTop: 10 }}>This point is inside the permanent river channel.</p>}
          <dl className="kv" style={{ marginTop: 12 }}>
            <dt>To the river</dt><dd>{r.distance_to_river_m != null ? `${n0(r.distance_to_river_m)} m` : '–'}</dd>
            <dt>Above the river</dt><dd>{r.height_above_river_m != null ? `${n1(r.height_above_river_m)} m (HAND, ±1 m or more)` : '–'}</dd>
          </dl>
          <div className="lbl">Distance to new water, each pass (069A)</div>
          <DistanceSpark rows={rows069} />
          <p className="tiny" style={{ color: 'var(--sky-3)', margin: '4px 0 0' }}>Red: new water within 1 km, the default alert distance. Gaps: baseline pass or no new water.</p>
        </>
      )}
      <div className="lbl">Rain here, last 14 days <span className="chip chip-live" style={{ padding: '0 7px', marginLeft: 6 }}>NASA POWER · live</span></div>
      {rain == null ? <p className="small">Asking NASA POWER…</p> : rain.length === 0 ? <p className="small">NASA POWER did not answer.</p> : (
        <div style={{ display: 'flex', alignItems: 'flex-end', gap: 3, height: 64 }} aria-label="Daily rain bars">
          {rain.map((d) => (
            <div key={d.date} title={`${d.date}: ${d.mm == null ? 'not yet available' : `${d.mm} mm`}`} style={{ flex: 1, height: d.mm == null ? 4 : Math.max(2, Math.min(64, d.mm * 1.2)), background: d.mm == null ? 'transparent' : '#7d97a1', border: d.mm == null ? '1px dashed #4c6470' : 'none', borderRadius: 2 }} />
          ))}
        </div>
      )}
      {rain && rain.length > 0 && <p className="tiny" style={{ color: 'var(--sky-3)', marginTop: 4 }}>Total {n1(rain.reduce((a, d) => a + (d.mm ?? 0), 0))} mm. Dashed days: NASA has not published them yet.</p>}
      <p className="tiny" style={{ color: 'var(--sky-3)', marginTop: 10 }}>{passes.length} passes checked. Observation, not a forecast.</p>
    </div>
  );
}

function SiteCard({ s }: { s: Record<string, any> }) {
  let lc: any = s.land_cover;
  try { if (typeof lc === 'string') lc = JSON.parse(lc); } catch { lc = null; }
  return (
    <div>
      <div className="lbl" style={{ marginTop: 0 }}>Bank-loss site</div>
      <h3 style={{ margin: '0 0 2px', color: '#fff' }}>{s.site_id} · {s.union}</h3>
      <div className="small" style={{ color: 'var(--sky-3)' }}>{s.upazila}</div>
      <dl className="kv" style={{ marginTop: 12 }}>
        <dt>Area lost</dt><dd>{n1(s.area_ha)} ha</dd>
        <dt>Bank moved up to</dt><dd>{n0(s.max_retreat_m)} m</dd>
        <dt>Buildings on it</dt><dd>{s.building_count} (older imagery)</dd>
        {lc?.ha && (<><dt>Cropland</dt><dd>{n1(lc.ha.cropland)} ha</dd></>)}
        <dt>Dates</dt><dd>{dShort(ymd(HEAD_PAIR.before))} → {dShort(ymd(HEAD_PAIR.after))}, confirmed {dShort(ymd(HEAD_PAIR.confirm))}</dd>
      </dl>
      <p className="tiny" style={{ color: 'var(--sky-3)', marginTop: 10 }}>Mainland land that turned into river connected to the main channel, touching the June bank line. Track 069A, threshold −15.62 dB (±1 dB for the range).</p>
    </div>
  );
}

function UnionTable({ unions, metric, onPick, onClose }: { unions: UnionRow[]; metric: Metric; onPick: (u: UnionRow) => void; onClose: () => void }) {
  const [sort, setSort] = useState<'bank' | 'near' | 'nw'>(metric === 'near' ? 'near' : metric === 'newwater' ? 'nw' : 'bank');
  const val = (u: UnionRow) => sort === 'bank' ? (u.bank_loss_ha_range?.[1] ?? 0) : sort === 'near' ? (u.buildings_within_100m_of_retreating_bank ?? 0) : (u.new_water_km2_range?.[1] ?? 0);
  const rows = [...unions].filter((u) => val(u) > 0).sort((a, b) => val(b) - val(a)).slice(0, 40);
  return (
    <div className="ex-table fade-in">
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: 8 }}>
        <b style={{ color: '#fff' }}>Unions, ranked</b>
        <div className="row" style={{ gap: 8 }}>
          <div className="seg" role="group" aria-label="Sort by">
            <button aria-pressed={sort === 'bank'} onClick={() => setSort('bank')}>Bank lost</button>
            <button aria-pressed={sort === 'near'} onClick={() => setSort('near')}>Near a moving bank</button>
            <button aria-pressed={sort === 'nw'} onClick={() => setSort('nw')}>New water</button>
          </div>
          <button className="ex-close" style={{ position: 'static' }} onClick={onClose} aria-label="Close the table"><Icon name="x" size={18} /></button>
        </div>
      </div>
      <div style={{ overflow: 'auto', maxHeight: 260 }}>
        <table className="table">
          <thead><tr><th>Union</th><th>Upazila</th><th className="r">Bank lost, ha</th><th className="r">Buildings ≤100 m of moving bank</th><th className="r">New water Jun→Jul, km²</th><th /></tr></thead>
          <tbody>
            {rows.map((u) => (
              <tr key={u.union_id}>
                <td><b style={{ color: 'var(--sky)' }}>{u.name_en}</b>{u.name_bn && <span className="small" style={{ marginLeft: 6 }}>{u.name_bn}</span>}</td>
                <td>{u.upazila}</td>
                <td className="r">{range(u.bank_loss_ha_range, n1)}</td>
                <td className="r">{u.buildings_within_100m_of_retreating_bank ?? '–'}</td>
                <td className="r">{range(u.new_water_km2_range, n1)}</td>
                <td className="r"><button className="btn btn-ghost btn-sm" onClick={() => onPick(u)}>Show</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="tiny" style={{ color: 'var(--sky-3)', margin: '8px 0 0' }}>Ranges are at the threshold ±1 dB. Buildings are model-detected footprints from older imagery, not a damage count. Source: union_summary.json, insights.json.</p>
      <style>{`.ex-table{position:absolute;left:12px;right:12px;bottom:12px;z-index:7;background:rgba(15,36,48,.97);border:1px solid var(--night-line);border-radius:var(--r-lg);padding:14px 16px;box-shadow:0 20px 50px rgba(0,0,0,.4)}`}</style>
    </div>
  );
}

