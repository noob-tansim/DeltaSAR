/** The map sections of the story page, loaded after the first paint (they need MapLibre). English and Bangla. */
import { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Map as MLMap } from 'maplibre-gl';
import { ChartLegend, SeasonChart } from '../components/charts';
import { Compare } from '../components/Compare';
import { Icon } from '../components/Icon';
import { useLiveNasa } from '../components/LiveNasa';
import { fitReach, setGibs, setImage } from '../components/map';
import { MapView } from '../components/MapView';
import { Stat } from '../components/Stat';
import { dataUrl, HEAD_PAIR, type Season, type Story as StoryT } from '../lib/data';
import { dLong, dShort, dTime, n0, n1, pDay, pLong, ymd } from '../lib/format';
import { digits, useL } from '../lib/i18n';
import { GIBS } from '../lib/nasa';

const BN_MONTH: Record<string, string> = { Jan: 'জানুয়ারি', Feb: 'ফেব্রুয়ারি', Mar: 'মার্চ', Apr: 'এপ্রিল', May: 'মে', Jun: 'জুন', Jul: 'জুলাই', Aug: 'আগস্ট', Sept: 'সেপ্টেম্বর', Sep: 'সেপ্টেম্বর', Oct: 'অক্টোবর', Nov: 'নভেম্বর', Dec: 'ডিসেম্বর',
  January: 'জানুয়ারি', February: 'ফেব্রুয়ারি', March: 'মার্চ', April: 'এপ্রিল', June: 'জুন', July: 'জুলাই', August: 'আগস্ট', September: 'সেপ্টেম্বর', October: 'অক্টোবর', November: 'নভেম্বর', December: 'ডিসেম্বর' };
/** "24 July 2026" → "২৪ জুলাই ২০২৬" when the site is in Bangla. */
function useBnDate() {
  const { lang } = useL();
  return (s: string) => (lang === 'bn' ? digits(s.replace(/[A-Za-z]+/g, (w) => BN_MONTH[w] ?? w), 'bn') : s);
}

// ---------------------------------------------------------------- why radar
export function WhyRadar() {
  const { L } = useL();
  return (
    <section className="section on-paper">
      <div className="container split">
        <div>
          <h2>{L('In the monsoon, cameras in space see cloud. NISAR sees water.', 'বর্ষায় মহাকাশের ক্যামেরা দেখে মেঘ। NISAR দেখে পানি।')}</h2>
          <p className="lead">
            {L('Drag the divider. On the left, NASA\'s MODIS camera on the morning of 25 July (Dhaka). On the right, NISAR\'s L-band radar six hours earlier, at dawn. The radar\'s 24 cm wave passes through cloud and rain, so the river shows up every pass.',
              'মাঝের দাগটি টানুন। বাঁয়ে ২৫ জুলাই সকালে নাসার MODIS ক্যামেরার ছবি। ডানে ছয় ঘণ্টা আগে, ভোরে NISAR-এর এল-ব্যান্ড রাডার। রাডারের ২৪ সেমি তরঙ্গ মেঘ ও বৃষ্টি ভেদ করে যায়, তাই প্রতিবার নদী দেখা যায়।')}
          </p>
          <ul className="ticks" style={{ marginTop: 18 }}>
            <li><span>{L(<><b>Open water is dark</b> in radar: smooth water reflects the signal away. We find the threshold from each scene's own histogram (−15.6 dB on track 069A) and report every area at ±1 dB.</>, <><b>রাডারে খোলা পানি কালো</b> দেখায়: মসৃণ পানি সংকেত অন্যদিকে ফিরিয়ে দেয়। প্রতিটি ছবির নিজস্ব হিস্টোগ্রাম থেকে সীমা ঠিক করা হয় (ট্র্যাক ০৬৯এ-তে −১৫.৬ ডিবি), আর প্রতিটি আয়তন ±১ ডিবিতেও মাপা হয়।</>)}</span></li>
            <li><span>{L(<><b>Two tracks cover the whole reach</b>, 069A and 019D, each every 12 days. We never mix tracks in one comparison.</>, <><b>দুটি ট্র্যাক পুরো এলাকা ঢাকে</b>, ০৬৯এ ও ০১৯ডি, প্রতিটি ১২ দিন পরপর। এক তুলনায় দুই ট্র্যাক মেশানো হয় না।</>)}</span></li>
            <li><span>{L(<><b>The 27 Jul – 10 Aug gap stays a gap.</b> The radar was off. We never fill it with a model.</>, <><b>২৭ জুলাই – ১০ আগস্টের ফাঁক ফাঁকই থাকে।</b> তখন রাডার বন্ধ ছিল। কোনো মডেল দিয়ে তা ভরানো হয় না।</>)}</span></li>
          </ul>
          <p className="tiny muted" style={{ marginTop: 16 }}>{L('Both pictures come live from NASA GIBS (no key). MODIS Terra true colour, 25 Jul 2026; NISAR L2 GCOV, 24 Jul 2026.', 'দুটি ছবিই সরাসরি নাসা GIBS থেকে আসে। MODIS Terra, ২৫ জুলাই ২০২৬; NISAR L2 GCOV, ২৪ জুলাই ২০২৬।')}</p>
        </div>
        <Compare
          label={L('MODIS optical against NISAR radar over the Jamuna, 24 and 25 July 2026', 'যমুনার ওপর MODIS ক্যামেরা বনাম NISAR রাডার, ২৪ ও ২৫ জুলাই ২০২৬')}
          leftLabel={L('MODIS camera · 25 Jul', 'MODIS ক্যামেরা · ২৫ জুলাই')}
          rightLabel={L('NISAR radar · 24 Jul', 'NISAR রাডার · ২৪ জুলাই')}
          start={48}
          style={{ height: 'min(560px, 70vh)', borderRadius: 'var(--r-xl)', boxShadow: 'var(--shadow-2)' }}
          left={(m) => setGibs(m, 'g-left', GIBS.truecolor!, '2026-07-25', 1)}
          right={(m) => setGibs(m, 'g-right', GIBS.nisar!, '2026-07-24', 1)}
        />
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- season
export function SeasonSection({ season }: { season: Season }) {
  const { L, lang } = useL();
  const bd = useBnDate();
  const d = (v: string | number) => digits(v, lang);
  const { floods } = useLiveNasa();
  const p069 = season.processed.filter((p) => p.track === '069A');
  const [sel, setSel] = useState<string>('069A_20260724');
  const [playing, setPlaying] = useState(false);
  const [layer, setLayer] = useState<'water' | 'new'>('water');
  const map = useRef<MLMap | null>(null);
  const p = season.processed.find((x) => x.key === sel) ?? p069[0]!;

  useEffect(() => {
    if (!playing) return;
    const t = window.setInterval(() => {
      setSel((k) => {
        const i = p069.findIndex((x) => x.key === k);
        return p069[(i + 1) % p069.length]!.key;
      });
    }, 1400);
    return () => window.clearInterval(t);
  }, [playing, p069]);

  useEffect(() => {
    const m = map.current;
    if (!m) return;
    setImage(m, 'water', layer === 'water' && p.water_png ? dataUrl(p.water_png) : null, 0.95);
    setImage(m, 'new', layer === 'new' && p.newwater_png ? dataUrl(p.newwater_png) : null, 1);
  }, [p, layer]);

  const lagH = p.published_utc ? Math.round((new Date(p.published_utc).getTime() - new Date(p.acquired_utc).getTime()) / 3.6e6) : null;
  const opt = season.pictures.optical['scene_S2_20261015'];
  return (
    <section className="section on-night">
      <div className="container">
        <div className="split rev" style={{ alignItems: 'start' }}>
          <div>
            <h2>{L(`The 2026 monsoon in ${season.processed.length} NISAR passes`, `${d(season.processed.length)}টি NISAR ছবিতে ২০২৬-এর বর্ষা`)}</h2>
            <p className="lead">
              {L('Each bar is one NISAR pass: the water it saw over the reach. The line is the river\'s flow. Rain is at the bottom. Click a bar, or press play.',
                'প্রতিটি দণ্ড একটি NISAR ছবি: এলাকায় কতটা পানি দেখা গেছে। রেখাটি নদীর প্রবাহ। নিচে বৃষ্টি। কোনো দণ্ডে ক্লিক করুন, বা চালু করুন।')}
            </p>
          </div>
          <div className="callout" style={{ alignSelf: 'end' }}>
            {L(
              <><b>What drives it?</b> Water extent follows the river's flow from upstream more than local rain: about {n1(season.fit.slope_km2_per_1000m3s)} km² more water for every extra 1,000 m³/s (R² {season.fit.r2}, weak: a rising and a falling river differ). A model using local rain alone showed no skill on any pass.</>,
              <><b>কেন বাড়ে-কমে?</b> পানির বিস্তার স্থানীয় বৃষ্টির চেয়ে উজানের নদীপ্রবাহ বেশি মানে: প্রতি ১,০০০ ঘনমিটার/সেকেন্ড বাড়তি প্রবাহে প্রায় {d(n1(season.fit.slope_km2_per_1000m3s))} বর্গকিমি বেশি পানি (সম্পর্ক দুর্বল: নদী বাড়ার আর কমার সময় আলাদা)। শুধু স্থানীয় বৃষ্টি দিয়ে বানানো মডেল কোনো ছবিতেই কাজে আসেনি।</>,
            )}
          </div>
        </div>
        <div className="card" style={{ marginTop: 24, padding: '20px 18px 14px' }}>
          <SeasonChart season={season} selected={sel} onSelect={(k) => { setPlaying(false); setSel(k); }} floods={floods} />
          <div style={{ marginTop: 10 }}><ChartLegend floods={floods.length > 0} /></div>
        </div>
        <div className="split" style={{ marginTop: 24, alignItems: 'stretch' }}>
          <div className="card stack" style={{ gap: 14 }}>
            <div className="row">
              <button className="btn btn-water btn-sm" onClick={() => setPlaying((v) => !v)} aria-pressed={playing}>
                <Icon name={playing ? 'pause' : 'play'} size={14} /> {playing ? L('Pause', 'থামান') : L('Play the season', 'মৌসুম চালান')}
              </button>
              <div className="seg" role="group" aria-label={L('Map layer', 'মানচিত্রের স্তর')}>
                <button aria-pressed={layer === 'water'} onClick={() => setLayer('water')}>{L('All water', 'সব পানি')}</button>
                <button aria-pressed={layer === 'new'} onClick={() => setLayer('new')}>{L('New since 18 Jun', '১৮ জুনের পর নতুন')}</button>
              </div>
            </div>
            <div>
              <div className="tiny" style={{ color: 'var(--sky-3)', textTransform: 'uppercase', letterSpacing: '.1em', fontWeight: 600 }}>{L('Selected pass', 'বাছাই করা ছবি')}</div>
              <div style={{ fontFamily: 'var(--font-display)', fontSize: '1.7rem', color: '#fff', lineHeight: 1.1 }}>{bd(pLong(p.acquired_utc))}</div>
              <div className="small">{L(`${dTime(p.acquired_utc)} in Dhaka · track ${p.track}`, `ঢাকায় ${bd(dTime(p.acquired_utc))} · ট্র্যাক ${p.track}`)}</div>
            </div>
            <dl className="kv">
              <dt>{L('Water in the reach', 'এলাকায় পানি')}</dt><dd>{p.water_km2 != null ? L(`${n0(p.water_km2)} km²`, `${d(n0(p.water_km2))} বর্গকিমি`) : L('track 019D: shown on the map', 'ট্র্যাক ০১৯ডি: মানচিত্রে দেখানো')}</dd>
              <dt>{L('New since baseline', 'শুরুর পর নতুন')}</dt><dd>{p.new_water_km2 ? L(`${n0(p.new_water_km2.strict)}–${n0(p.new_water_km2.loose)} km² (±1 dB)`, `${d(n0(p.new_water_km2.strict))}–${d(n0(p.new_water_km2.loose))} বর্গকিমি (±১ ডিবি)`) : L('this is the baseline pass', 'এটিই শুরুর ছবি')}</dd>
              <dt>{L('Published by NASA', 'নাসার প্রকাশ')}</dt><dd>{p.published_utc ? L(`${dTime(p.published_utc)}, ${lagH} h after the pass`, `${bd(dTime(p.published_utc))}, ছবি তোলার ${d(lagH ?? 0)} ঘণ্টা পর`) : '–'}</dd>
              <dt>{L('River flow', 'নদীপ্রবাহ')}</dt><dd>{p.discharge_m3s ? L(`${n0(p.discharge_m3s)} m³/s (GloFAS model)`, `${d(n0(p.discharge_m3s))} ঘনমিটার/সে (GloFAS মডেল)`) : '–'}</dd>
              <dt>{L('Data', 'তথ্য')}</dt><dd>{p.processing_level}</dd>
              <dt>{L('Granule', 'ফাইল')}</dt><dd className="mono" style={{ fontSize: '.72rem', color: 'var(--sky-3)', overflowWrap: 'anywhere' }}>{p.granule_id}</dd>
            </dl>
            <div className="row" style={{ marginTop: 'auto' }}>
              {season.processed.map((q) => (
                <button key={q.key} onClick={() => { setPlaying(false); setSel(q.key); }} aria-pressed={q.key === sel}
                  className="chip" style={{ cursor: 'pointer', background: q.key === sel ? 'var(--water)' : undefined, color: q.key === sel ? 'var(--night)' : undefined }}>
                  {bd(pDay(q.acquired_utc))}{q.track === '019D' ? ' ·D' : ''}
                </button>
              ))}
            </div>
          </div>
          <div className="mapcard" style={{ minHeight: 480 }}>
            <MapView label={L('Water seen by NISAR on the selected pass', 'বাছাই করা ছবিতে NISAR-এর দেখা পানি')} style={{ height: '100%', minHeight: 480 }}
              onReady={(m) => {
                map.current = m;
                if (opt) setImage(m, 'optical', dataUrl(opt.url), 0.55);
                setImage(m, 'water', p.water_png ? dataUrl(p.water_png) : null, 0.95);
              }}>
              <div className="legend" style={{ position: 'absolute', left: 12, bottom: 12, background: 'rgba(10,24,33,.85)', padding: '8px 12px', borderRadius: 12, color: 'var(--sky-2)' }}>
                <span><span className="sw" style={{ background: 'var(--water)' }} />{layer === 'water' ? L('Water seen by radar', 'রাডারে দেখা পানি') : L('New water since 18 Jun', '১৮ জুনের পর নতুন পানি')}</span>
                <span><span className="sw" style={{ background: '#6f7f5d' }} />{L('Sentinel-2, 15 Oct (background)', 'সেন্টিনেল-২, ১৫ অক্টোবর (পটভূমি)')}</span>
              </div>
            </MapView>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- bank
export function BankSection({ story, season }: { story: StoryT; season: Season }) {
  const { L, lang } = useL();
  const bd = useBnDate();
  const d = (v: string | number) => digits(v, lang);
  const hp = story.headline_pair;
  const exp = hp.exposure.mainland_bank_loss;
  const ins = story.insights;
  const s01 = ins.where.rows[0];
  const q = useMemo(() => {
    const f = (x: string) => season.processed.find((p) => p.date === x && p.track === '069A')?.discharge_m3s;
    return { before: f(HEAD_PAIR.before), after: f(HEAD_PAIR.after) };
  }, [season]);
  const lo = Math.round(hp.mainland_bank_loss_ha_range[0]);
  const hi = Math.round(hp.mainland_bank_loss_ha_range[1]);
  return (
    <section className="section on-paper">
      <div className="container">
        <div className="split" style={{ alignItems: 'start' }}>
          <div>
            <h2>{L(`${lo}–${hi} hectares of land became river.`, `${d(lo)}–${d(hi)} হেক্টর জমি নদী হয়ে গেছে।`)}</h2>
            <p className="lead">
              {L(
                <>Between {dLong(ymd(HEAD_PAIR.before))} and {dLong(ymd(HEAD_PAIR.after))}, NISAR saw mainland bank turn into river channel, and the next pass on {dLong(ymd(HEAD_PAIR.confirm))} confirmed it. We count only land that touched the old bank line and joined the main channel.</>,
                <>{bd(dLong(ymd(HEAD_PAIR.before)))} থেকে {bd(dLong(ymd(HEAD_PAIR.after)))}-এর মধ্যে NISAR দেখেছে মূল ভূখণ্ডের পাড় নদীখাতে পরিণত হয়েছে; {bd(dLong(ymd(HEAD_PAIR.confirm)))}-এর পরের ছবিতে তা নিশ্চিত হয়েছে। শুধু সেই জমি গোনা হয়েছে যা পুরোনো পাড়ের রেখা ছুঁয়ে মূল নদীর সাথে মিশেছে।</>,
              )}
            </p>
            <div className="callout warn" style={{ marginTop: 18 }}>
              {L(
                <><b>Bank, not flood.</b> On {dShort(ymd(HEAD_PAIR.after))} the river carried {n0(q.after ?? null)} m³/s, less than the {n0(q.before ?? null)} m³/s of {dShort(ymd(HEAD_PAIR.before))}. A lower river cannot flood more land, so this change is the bank moving. (Flow is modelled by GloFAS, not a gauge.)</>,
                <><b>এটি ভাঙন, বন্যা নয়।</b> {bd(dShort(ymd(HEAD_PAIR.after)))} নদীতে প্রবাহ ছিল {d(n0(q.after ?? null))} ঘনমিটার/সে, যা {bd(dShort(ymd(HEAD_PAIR.before)))}-এর {d(n0(q.before ?? null))}-এর চেয়ে কম। নিচু নদী বেশি জমি ডোবাতে পারে না, তাই এই পরিবর্তন পাড় সরে যাওয়া। (প্রবাহ GloFAS মডেলের, মাপক যন্ত্রের নয়।)</>,
              )}
            </div>
            <div className="stats two" style={{ marginTop: 18 }}>
              <Stat value={d(exp.sites)} label={L('places where the bank moved, each 0.5 ha or more', 'জায়গায় পাড় সরেছে, প্রতিটি ০.৫ হেক্টর বা বেশি')} source={L('NISAR bank-loss rule', 'NISAR ভাঙনের নিয়ম')} />
              <Stat value={d(n0(exp.land_cover.ha.cropland ?? null))} unit={L('ha', 'হেক্টর')} label={L('of it was cropland', 'ছিল ফসলি জমি')} source="ESA WorldCover 2021" />
              <Stat value={d(exp.buildings)} label={L('buildings stood on the land that is now river', 'টি ঘরবাড়ি ছিল সেই জমিতে, যা এখন নদী')} source="Google Open Buildings" />
              {s01 && <Stat value={d(n1(s01.largest_ha))} unit={L('ha', 'হেক্টর')} label={L(`the largest single site, ${s01.largest_site} in ${s01.union}, ${s01.upazila}`, `সবচেয়ে বড় একক জায়গা, ${s01.largest_site}, ${s01.union}, ${s01.upazila}`)} source={L('Site list, Explorer', 'জায়গার তালিকা, মানচিত্রে')} to="/explore?view=bank" />}
            </div>
          </div>
          <div className="stack" style={{ gap: 16 }}>
            <div className="mapcard" style={{ height: 520 }}>
              <MapView label={L('Mainland bank loss, June to October 2026', 'মূল ভূখণ্ডের ভাঙন, জুন থেকে অক্টোবর ২০২৬')} style={{ height: '100%' }} base="dark"
                onReady={(m) => {
                  const opt = season.pictures.optical['scene_S2_20261015'];
                  if (opt) setImage(m, 'optical', dataUrl(opt.url), 0.85);
                  const bl = season.pictures.bankloss[HEAD_PAIR.id];
                  if (bl) setImage(m, 'bankloss', dataUrl(bl), 1);
                  m.addSource('sites', { type: 'geojson', data: dataUrl('geo/sites.geojson') });
                  m.addLayer({ id: 'sites-o', type: 'line', source: 'sites', paint: { 'line-color': '#ff5a4e', 'line-width': 2 } }, 'labels');
                  m.addSource('bl', { type: 'geojson', data: dataUrl('geo/banklines.geojson') });
                  m.addLayer({ id: 'bl', type: 'line', source: 'bl', paint: { 'line-color': '#ffe08a', 'line-width': 1.2, 'line-opacity': 0.7 } }, 'labels');
                  if (s01) m.flyTo({ center: [s01.lon, s01.lat], zoom: 12.3, duration: 0 });
                  else fitReach(m);
                }}>
                <div className="legend" style={{ position: 'absolute', left: 12, bottom: 12, background: 'rgba(10,24,33,.85)', padding: '8px 12px', borderRadius: 12, color: 'var(--sky-2)' }}>
                  <span><span className="sw" style={{ background: 'var(--bankloss)' }} />{L('Bank lost, Jun → Oct', 'ভেঙে যাওয়া পাড়, জুন → অক্টোবর')}</span>
                  <span><span className="sw" style={{ background: '#ffe08a', height: 3 }} />{L('Bank lines', 'পাড়ের রেখা')}</span>
                </div>
              </MapView>
            </div>
            <div className="card">
              <h3 style={{ fontSize: '1.05rem' }}>{L('Who lives next to a moving bank', 'সরে যাওয়া পাড়ের পাশে কারা')}</h3>
              <p className="small muted" style={{ marginBottom: 10 }}>{L(`${ins.near_bank.label}. Bank line of ${dShort(ymd(story.headline_pair.confirm_pass))}.`, `সক্রিয়ভাবে সরে যাওয়া পাড়ের কাছে (পর্যবেক্ষণ, পূর্বাভাস নয়)। ${bd(dShort(ymd(story.headline_pair.confirm_pass)))}-এর পাড়ের রেখা।`)}</p>
              <table className="table">
                <thead><tr><th>{L('Within', 'দূরত্ব')}</th><th className="r">{L('Buildings', 'ঘরবাড়ি')}</th><th className="r">{L('Cropland', 'ফসলি জমি')}</th></tr></thead>
                <tbody>
                  {ins.near_bank.rows.map((r) => (
                    <tr key={r.within_m}><td>{L(`${r.within_m} m of the bank`, `পাড় থেকে ${d(r.within_m)} মিটার`)}</td><td className="r">{d(n0(r.buildings))}</td><td className="r">{L(`${n0(r.cropland_ha)} ha`, `${d(n0(r.cropland_ha))} হেক্টর`)}</td></tr>
                  ))}
                </tbody>
              </table>
              <p className="tiny muted" style={{ marginTop: 10 }}>{L(ins.near_bank.caveat, 'ঘরবাড়ির তথ্য পুরোনো উপগ্রহ ছবি থেকে মডেলে শনাক্ত করা (আগে কী ছিল), ক্ষতির হিসাব নয়।')}</p>
              <Link to="/explore?view=bank" className="btn btn-ghost btn-sm" style={{ marginTop: 6 }}>{L('Rank the unions', 'ইউনিয়নের তালিকা')} <Icon name="arrow" size={14} /></Link>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
