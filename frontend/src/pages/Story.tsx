/** The story page: what NISAR saw on the Jamuna in 2026, what it means, and how it reaches people. English and Bangla. */
import { lazy, Suspense, useEffect, type ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Footer, Nav } from '../components/Chrome';
import { PolChart } from '../components/charts';
import { Icon, type IconName } from '../components/Icon';
import { LiveNasaStrip } from '../components/LiveNasa';
import { Stat } from '../components/Stat';
import { prewarm } from '../lib/api';
import { dataUrl, useData, type Season, type Story as StoryT, type Validation } from '../lib/data';
import { n0 } from '../lib/format';
import { digits, useL } from '../lib/i18n';

const WhyRadar = lazy(() => import('./StoryMaps').then((m) => ({ default: m.WhyRadar })));
const SeasonSection = lazy(() => import('./StoryMaps').then((m) => ({ default: m.SeasonSection })));
const BankSection = lazy(() => import('./StoryMaps').then((m) => ({ default: m.BankSection })));
const Slot = ({ h, dark }: { h: number; dark?: boolean }) => <div style={{ height: h, background: dark ? 'var(--night)' : 'var(--paper)' }} />;

export default function Story() {
  const { data: season } = useData<Season>('season.json');
  const { data: story } = useData<StoryT>('story.json');
  const { data: val } = useData<Validation>('validation.json');
  useEffect(() => prewarm(), []);
  return (
    <>
      <Nav />
      <main id="main">
        <Hero season={season} story={story} />
        <Suspense fallback={<Slot h={760} />}><WhyRadar /></Suspense>
        <Suspense fallback={<Slot h={1200} dark />}>{season && <SeasonSection season={season} />}</Suspense>
        <Suspense fallback={<Slot h={1100} />}>{story && season && <BankSection story={story} season={season} />}</Suspense>
        {val && <HonestSection val={val} />}
        <ChallengeSection />
        <LoopSection />
        <LimitsSection />
      </main>
      <Footer />
    </>
  );
}

// ---------------------------------------------------------------- hero
function Hero({ season, story }: { season: Season | null; story: StoryT | null }) {
  const { L, lang } = useL();
  const d = (v: string | number) => digits(v, lang);
  const pics = season?.pictures;
  const hp = story?.headline_pair;
  const near100 = story?.insights.near_bank.rows.find((r) => r.within_m === 100);
  const peakCrop = story ? Math.max(...story.insights.frequency.by_date.map((x) => x.cropland_in_water_ha)) : null;
  const bank = hp ? `${d(Math.round(hp.mainland_bank_loss_ha_range[0]))}–${d(Math.round(hp.mainland_bank_loss_ha_range[1]))}` : '–';
  return (
    <section className="on-night hero">
      <div className="hero-glow" aria-hidden="true" />
      <div className="container hero-grid">
        <div className="fade-in">
          <div className="eyebrow"><Icon name="sat" size={15} /> {L('NASA–ISRO NISAR · Jamuna River, Bangladesh · 2026 monsoon', 'নাসা–ইসরো NISAR · যমুনা নদী, বাংলাদেশ · ২০২৬ বর্ষা')}</div>
          <h1>
            {L(<>The river moved.<br /><span className="hl">Radar saw it through the cloud.</span></>, <>নদী সরে গেছে।<br /><span className="hl">মেঘের ভেতর দিয়েও রাডার তা দেখেছে।</span></>)}
          </h1>
          <p className="lead">
            {L(
              <>DeltaSAR turns every NISAR pass over the Jamuna into a map of where water and riverbank changed, with a receipt for each number. <b className="em">বন্যা সাথী (Bonna Sathi)</b> carries that evidence to families on the river islands: a volunteer checks every alert, the phone reads it aloud in Bangla, and the family answers <i>safe</i> or <i>help</i>.</>,
              <>ডেল্টাসার যমুনার ওপর NISAR উপগ্রহের প্রতিটি ছবি থেকে মানচিত্র বানায়: কোথায় পানি ও নদীর পাড় বদলেছে, প্রতিটি সংখ্যার প্রমাণসহ। <b className="em">বন্যা সাথী</b> সেই খবর চরের পরিবারের কাছে পৌঁছে দেয়: একজন স্বেচ্ছাসেবক প্রতিটি সতর্কবার্তা যাচাই করেন, ফোন তা বাংলায় পড়ে শোনায়, আর পরিবার জানায় <i>নিরাপদ</i> নাকি <i>সাহায্য দরকার</i>।</>,
            )}
          </p>
          <div className="row" style={{ marginTop: 26, gap: 12 }}>
            <Link to="/demo" className="btn btn-water btn-lg"><Icon name="play" size={18} /> {L('Run the alert loop · 2 min', 'সতর্কবার্তার পুরো ধাপ দেখুন · ২ মিনিট')}</Link>
            <Link to="/explore" className="btn btn-ghost btn-lg"><Icon name="map" size={18} /> {L('Explore the radar map', 'রাডার মানচিত্র দেখুন')}</Link>
          </div>
          <p className="small" style={{ marginTop: 16, color: 'var(--sky-3)' }}>
            {L('“Radar evidence, a human check, a spoken alert, and a counted reply.”', '“রাডারের প্রমাণ, মানুষের যাচাই, পড়ে শোনানো সতর্কবার্তা, আর গোনা উত্তর।”')}
          </p>
        </div>
        <figure className="radar-window" aria-label={L('NISAR radar picture of the reach on 24 July 2026, with new water since 18 June in cyan', '২৪ জুলাই ২০২৬-এর NISAR রাডার ছবি; নীল রঙে ১৮ জুনের পর নতুন পানি')}>
          {pics && (
            <>
              <img src={dataUrl(pics.sar['069A_20260724'] ?? '')} alt="" loading="eager" />
              <img src={dataUrl(pics.newwater['069A_20260724'] ?? '')} alt="" className="nw" />
            </>
          )}
          <figcaption>
            <span className="chip chip-live" style={{ padding: '2px 9px' }}>NISAR L-band HH</span>
            <span>{L('24 Jul 2026, 23:21 UTC (25 Jul, 05:21 in Dhaka) · through monsoon cloud', '২৪ জুলাই ২০২৬, ২৩:২১ UTC (ঢাকায় ২৫ জুলাই ভোর ৫:২১) · বর্ষার মেঘের ভেতর দিয়ে')}</span>
            <span className="row" style={{ gap: 6 }}><span className="sw" style={{ background: 'var(--water)' }} /> {L('new water since 18 Jun', '১৮ জুনের পর নতুন পানি')}</span>
          </figcaption>
        </figure>
      </div>
      <div className="container" style={{ marginTop: 40 }}>
        <div className="live-band"><LiveNasaStrip /></div>
        <div className="stats" style={{ marginTop: 16 }}>
          <Stat icon="sat" tone="water" value={season ? d(season.processed.length) : '–'} unit={L('passes', 'টি ছবি')}
            label={L('NISAR radar passes mapped, 18 Jun – 16 Oct, on the two tracks that cover the whole reach', '১৮ জুন – ১৬ অক্টোবর, পুরো এলাকার দুই ট্র্যাকের NISAR রাডার ছবি থেকে মানচিত্র')}
            source={L('NASA–ISRO NISAR L2 GCOV', 'নাসা–ইসরো NISAR L2 GCOV')} />
          <Stat icon="tri" tone="loss" value={bank} unit={L('ha', 'হেক্টর')}
            label={L(<>of mainland riverbank became river, <b>confirmed</b> by a later pass</>, <>মূল ভূখণ্ডের নদীর পাড় নদীতে পরিণত, পরের ছবিতে <b>নিশ্চিত</b></>)}
            source={L('NISAR track 069A, 18 Jun → 4 Oct', 'NISAR ট্র্যাক ০৬৯এ, ১৮ জুন → ৪ অক্টোবর')} />
          <Stat icon="home" tone="people" value={near100 ? d(n0(near100.buildings)) : '–'}
            label={L('buildings stand within 100 m of a bank that retreated this season', 'টি ঘরবাড়ি এই মৌসুমে সরে যাওয়া পাড়ের ১০০ মিটারের মধ্যে')}
            source={L('Google Open Buildings + NISAR bank line', 'গুগল ওপেন বিল্ডিংস + NISAR পাড়ের রেখা')} />
          <Stat icon="drop" tone="crop" value={peakCrop ? d(n0(peakCrop)) : '–'} unit={L('ha', 'হেক্টর')}
            label={L('of cropland under water at the peak pass, 24 Jul, seen through cloud', 'ফসলি জমি পানির নিচে, ২৪ জুলাইয়ের সর্বোচ্চ ছবিতে, মেঘ ভেদ করে দেখা')}
            source={L('ESA WorldCover + NISAR water map', 'ESA WorldCover + NISAR পানির মানচিত্র')} />
        </div>
      </div>
      <style>{`
        .hero{position:relative;overflow:hidden;padding:clamp(40px,6vw,84px) 0 clamp(40px,6vw,72px);background:radial-gradient(1200px 700px at 85% -10%,rgba(43,183,227,.14),transparent 60%),radial-gradient(900px 500px at -10% 110%,rgba(156,47,110,.12),transparent 60%),var(--night)}
        .hero h1 .hl{color:var(--water)}
        .hero .lead .em{color:#fff}
        .hero-glow{display:none}
        .hero-grid{display:grid;grid-template-columns:minmax(0,7fr) minmax(0,5fr);gap:clamp(24px,4vw,56px);align-items:center;position:relative}
        @media (max-width:900px){.hero-grid{grid-template-columns:1fr}}
        .radar-window{margin:0;position:relative;border-radius:var(--r-xl);overflow:hidden;aspect-ratio:4/5;background:#05121a;border:1px solid var(--night-line);box-shadow:0 30px 80px rgba(0,0,0,.45),0 0 0 1px rgba(43,183,227,.08)}
        .radar-window img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;object-position:52% 38%;transform:scale(1.55);transform-origin:52% 38%}
        .radar-window img.nw{opacity:.85;animation:nwpulse 5s ease-in-out infinite}
        @keyframes nwpulse{0%,100%{opacity:.35}50%{opacity:.95}}
        .radar-window figcaption{position:absolute;left:12px;right:12px;bottom:12px;display:flex;flex-wrap:wrap;gap:6px 12px;align-items:center;font-size:.8rem;color:var(--sky);background:rgba(5,18,26,.8);backdrop-filter:blur(6px);padding:10px 12px;border-radius:14px;border:1px solid var(--night-line)}
        .live-band{border:1px solid rgba(43,183,227,.18);background:rgba(43,183,227,.06);border-radius:var(--r-lg);padding:14px 18px;isolation:isolate}
      `}</style>
    </section>
  );
}

// ---------------------------------------------------------------- honest science
function HonestSection({ val }: { val: Validation }) {
  const { L, lang } = useL();
  const sk = val.skill;
  const hh = val.pol.map((p) => p.HH.contrast_db);
  const hv = val.pol.map((p) => p.HV.contrast_db);
  const f = (v: number) => digits(v.toFixed(1), lang);
  const rows: [string, number, string][] = sk ? [
    [L('Same as the last radar pass', 'আগের রাডার ছবির মতোই'), sk.mean.persistence, L('persistence', 'আগের ছবি')],
    [L('Machine-learning model (flow, rain, terrain)', 'মেশিন-লার্নিং মডেল (প্রবাহ, বৃষ্টি, ভূমি)'), sk.mean.ml, L('trained on NISAR water maps', 'NISAR মানচিত্রে প্রশিক্ষিত')],
    [L('River-flow rule (stage proxy)', 'নদীপ্রবাহের নিয়ম'), sk.mean.stage_proxy, L('flow → height above river', 'প্রবাহ → নদী থেকে উচ্চতা')],
  ] : [];
  return (
    <section className="section on-night">
      <div className="container">
        <div className="eyebrow"><Icon name="shield" size={15} /> {L('What the radar can tell, and what it cannot', 'রাডার কী বলতে পারে, আর কী পারে না')}</div>
        <h2 style={{ maxWidth: '24ch' }}>{L('We tested our own claims. Two answers for the challenge.', 'নিজেদের দাবি আমরা নিজেরাই পরীক্ষা করেছি। চ্যালেঞ্জের দুটি প্রশ্নের উত্তর।')}</h2>
        <div className="grid-2" style={{ marginTop: 28, alignItems: 'stretch' }}>
          <div className="card">
            <h3>{L('Which polarisation shows the change?', 'কোন পোলারাইজেশনে পরিবর্তন সবচেয়ে স্পষ্ট?')} <span style={{ color: 'var(--water)' }}>HH.</span></h3>
            <p className="small">
              {L(
                <>Water against land contrast is {f(Math.min(...hh))}–{f(Math.max(...hh))} dB in HH but only {f(Math.min(...hv))}–{f(Math.max(...hv))} dB in HV, where water sits at the sensor's noise floor (about −23 dB). So the water rule uses HH; HV helps only to flag flooded crops, which stays experimental.</>,
                <>পানি আর মাটির পার্থক্য HH-এ {f(Math.min(...hh))}–{f(Math.max(...hh))} ডিবি, কিন্তু HV-তে মাত্র {f(Math.min(...hv))}–{f(Math.max(...hv))} ডিবি; HV-তে পানির মান যন্ত্রের নয়েজের কাছাকাছি (প্রায় −২৩ ডিবি)। তাই পানির নিয়মে HH ব্যবহার করা হয়; HV শুধু ডোবা ফসল চিহ্নিত করতে, যা এখনো পরীক্ষামূলক।</>,
              )}
            </p>
            <PolChart v={val} />
            <div className="legend" style={{ color: 'var(--sky-2)' }}>
              <span><span className="sw" style={{ background: '#3cc8f0', borderRadius: 7 }} />{L('HH contrast', 'HH পার্থক্য')}</span>
              <span><span className="sw" style={{ background: '#c56fa4', borderRadius: 7 }} />{L('HV contrast', 'HV পার্থক্য')}</span>
              <span className="tiny" style={{ color: 'var(--sky-3)' }}>{L(`median water vs stable land, ${val.pol.length} passes`, `পানি বনাম স্থির ভূমির মধ্যমা, ${digits(val.pol.length, lang)}টি ছবি`)}</span>
            </div>
          </div>
          <div className="card">
            <h3>{L('Can we forecast the water?', 'পানির পূর্বাভাস কি দেওয়া যায়?')} <span style={{ color: 'var(--char)' }}>{L('Not better than the last picture.', 'আগের ছবির চেয়ে ভালো নয়।')}</span></h3>
            <p className="small">
              {L(
                <>We predicted each pass without seeing it, three ways. Plain persistence, “the same as the last pass”, wins on {sk?.persistence_wins} of {sk?.n} passes. So the app shows the newest radar picture and its age. It never shows a forecast as fact.</>,
                <>প্রতিটি ছবি না দেখে তিনভাবে অনুমান করা হয়েছে। “আগের ছবির মতোই” এই সহজ অনুমান {digits(sk?.n ?? 0, lang)}টির মধ্যে {digits(sk?.persistence_wins ?? 0, lang)}টিতে জিতেছে। তাই অ্যাপ সর্বশেষ রাডার ছবি ও তার বয়স দেখায়; কোনো পূর্বাভাসকে সত্য বলে দেখায় না।</>,
              )}
            </p>
            <div className="stack" style={{ gap: 14, marginTop: 18 }}>
              {rows.map(([t, v, sub], i) => (
                <div key={t}>
                  <div className="row" style={{ justifyContent: 'space-between' }}>
                    <span style={{ color: '#fff', fontWeight: 600 }}>{t} <span className="tiny" style={{ color: 'var(--sky-3)', fontWeight: 400 }}>· {sub}</span></span>
                    <b className="num" style={{ color: i === 0 ? 'var(--water)' : 'var(--sky)' }}>{digits(v.toFixed(2), lang)}</b>
                  </div>
                  <div style={{ height: 10, background: 'rgba(255,255,255,.06)', borderRadius: 6, marginTop: 6 }}>
                    <div style={{ width: `${(v / 0.6) * 100}%`, height: '100%', borderRadius: 6, background: i === 0 ? 'linear-gradient(90deg,#2bb7e3,#7fe2ff)' : i === 1 ? '#7d97a1' : '#4c6470' }} />
                  </div>
                </div>
              ))}
            </div>
            <p className="tiny" style={{ marginTop: 16, color: 'var(--sky-3)' }}>{L(`Mean CSI (critical success index, 1 = perfect) on water outside the permanent channel, leave-one-pass-out, track 069A, ${sk?.n} passes.`, `গড় CSI (১ = নিখুঁত), স্থায়ী নদীখাতের বাইরের পানিতে, প্রতিটি ছবি বাদ রেখে যাচাই, ট্র্যাক ০৬৯এ।`)}</p>
          </div>
        </div>
      </div>
    </section>
  );
}

// ---------------------------------------------------------------- the challenge, point by point
type Ask = [string, ReactNode, ReactNode, string, string, string];
const ASKS: Ask[] = [
  ['“Track and visualize one or more types of surface change” with NISAR', <>Two: <b>flood water</b> on every pass, and <b>riverbank loss</b> (mainland that became river), with ±1 dB ranges and a confirming later pass.</>, <>দুটি: প্রতিটি ছবিতে <b>বন্যার পানি</b>, আর <b>নদীভাঙন</b> (মূল ভূখণ্ড যা নদী হয়ে গেছে), ±১ ডিবি পরিসীমা ও পরের ছবিতে নিশ্চিতসহ।</>, '/explore', 'Explorer', 'মানচিত্র'],
  ['“Interactive change-detection maps, time-series animations … image sliders, web maps”', <>Swipe any two passes of a track; play the season; click any point for its own time series; rank unions.</>, <>একই ট্র্যাকের যেকোনো দুটি ছবি পাশাপাশি তুলনা; পুরো মৌসুম চালিয়ে দেখা; যেকোনো জায়গায় ক্লিক করে তার সময়রেখা; ইউনিয়নের তালিকা।</>, '/explore', 'Compare two passes', 'দুটি ছবি তুলনা'],
  ['“Which polarizations highlight these changes?”', <><b>HH.</b> Water–land contrast 9–12 dB in HH against 7–8 dB in HV, measured on every pass; HV only flags flooded crops, experimentally.</>, <><b>HH।</b> পানি–মাটির পার্থক্য HH-এ ৯–১২ ডিবি, HV-তে ৭–৮ ডিবি, প্রতিটি ছবিতে মাপা; HV শুধু ডোবা ফসলের জন্য, পরীক্ষামূলক।</>, '/methods', 'Polarisation table', 'পোলারাইজেশন সারণি'],
  ['“Hypothesize the physical drivers”', <>Water extent follows upstream river flow, not local rain. Banks moved although the river was <i>lower</i> than in June: erosion of the Jamuna's sandy banks, not flooding. On the lost land: cropland and homes.</>, <>পানির বিস্তার উজানের নদীপ্রবাহ অনুসরণ করে, স্থানীয় বৃষ্টি নয়। জুনের চেয়ে নদী <i>নিচে</i> থাকলেও পাড় সরেছে: এটি যমুনার বালুময় পাড়ের ভাঙন, বন্যা নয়। হারানো জমিতে ছিল ফসল ও ঘরবাড়ি।</>, '/methods', 'Validation', 'যাচাই'],
  ['“Different frequencies (from other sensors)”', <>NISAR L-band beside Sentinel-1 C-band and OPERA water (both from NASA GIBS), and MODIS optical to show what cloud hides.</>, <>NISAR এল-ব্যান্ডের পাশে সেন্টিনেল-১ সি-ব্যান্ড ও OPERA পানির মানচিত্র (নাসা GIBS থেকে), আর মেঘ কী ঢেকে রাখে দেখাতে MODIS ছবি।</>, '/explore', 'NASA live layers', 'নাসার লাইভ স্তর'],
  ['“Ancillary datasets … to contextualize”', <>ESA WorldCover cropland, Google Open Buildings, union boundaries, height above river, IMERG rain, FFWC river levels, NASA EONET flood events.</>, <>ESA WorldCover ফসলি জমি, গুগল ওপেন বিল্ডিংস, ইউনিয়নের সীমানা, নদী থেকে উচ্চতা, IMERG বৃষ্টি, FFWC নদীর পানির উচ্চতা, নাসা EONET বন্যার ঘটনা।</>, '/methods#sources', 'All sources', 'সব উৎস'],
  ['“Actionable insights … for decision-makers and the public”', <>A volunteer-approved, spoken alert that people answer; help requests followed up; impact counted from a ledger. Union ranking for officers.</>, <>স্বেচ্ছাসেবকের যাচাই করা, পড়ে শোনানো সতর্কবার্তা যার উত্তর দেওয়া যায়; সাহায্যের অনুরোধের পর খোঁজ নেওয়া; খাতা থেকে গোনা প্রভাব। কর্মকর্তাদের জন্য ইউনিয়নের তালিকা।</>, '/demo', 'Run the loop', 'ধাপগুলো চালান'],
  ['“What future applications of NISAR are possible?”', <>Watching each retreating stretch pass by pass; InSAR coherence for embankments and fields (the pipeline already reads NISAR GUNW); soil moisture and crops; new reaches as one config entry; L-band SAOCOM (CONAE) and C-band RCM (CSA) to fill days between NISAR passes.</>, <>প্রতিটি ভাঙনপ্রবণ অংশ ছবি ধরে ধরে নজরে রাখা; বাঁধ ও জমির জন্য InSAR কোহেরেন্স (NISAR GUNW আগে থেকেই পড়া হয়); মাটির আর্দ্রতা ও ফসল; নতুন এলাকা যোগ করা; NISAR ছবির মাঝের দিনগুলোর জন্য SAOCOM (এল-ব্যান্ড) ও RCM (সি-ব্যান্ড)।</>, '/methods#limits', 'Limits and next steps', 'সীমাবদ্ধতা ও পরের ধাপ'],
];

function ChallengeSection() {
  const { L } = useL();
  return (
    <section className="section on-paper">
      <div className="container">
        <div className="split" style={{ alignItems: 'end' }}>
          <div>
            <div className="eyebrow"><Icon name="sat" size={15} /> Dancing with the SARs</div>
            <h2>{L('What the challenge asks, and where we answer it.', 'চ্যালেঞ্জ কী চেয়েছে, আর আমরা কোথায় উত্তর দিয়েছি।')}</h2>
          </div>
          <p className="lead" style={{ marginBottom: 6 }}>
            {L('Our study area is home. Team Astro Bengalis is from Bangladesh, where the Jamuna moves every monsoon and families on the chars lose land they farmed the year before.',
              'আমাদের গবেষণার এলাকা আমাদের নিজের দেশ। টিম অ্যাস্ট্রো বেঙ্গলিস বাংলাদেশের; এখানে প্রতি বর্ষায় যমুনা সরে যায়, আর চরের পরিবার আগের বছরের চাষের জমি হারায়।')}
          </p>
        </div>
        <div className="asks">
          {ASKS.map(([q, en, bn, to, cen, cbn]) => (
            <div key={q} className="ask">
              <p className="q">{q}</p>
              <p className="a small">{L(en, bn)}</p>
              <Link to={to} className="small" style={{ fontWeight: 600 }}>{L(cen, cbn)} <Icon name="arrow" size={13} style={{ display: 'inline', verticalAlign: '-2px' }} /></Link>
            </div>
          ))}
        </div>
      </div>
      <style>{`
        .asks{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px;margin-top:28px}
        @media (max-width:1000px){.asks{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media (max-width:560px){.asks{grid-template-columns:1fr}}
        .ask{border:1px solid var(--line);border-radius:var(--r-lg);padding:16px 16px 14px;background:linear-gradient(180deg,#fff,var(--mist));display:flex;flex-direction:column;transition:box-shadow .15s,border-color .15s}
        .ask:hover{border-color:#b9d6da;box-shadow:var(--shadow-1)}
        .ask .q{font-family:var(--font-display);font-weight:600;font-size:1.02rem;line-height:1.3;color:var(--river);margin:0 0 8px}
        .ask .a{color:var(--ink-2);flex:1}
      `}</style>
    </section>
  );
}

// ---------------------------------------------------------------- the loop
const LOOP: [IconName, string, string, string, string][] = [
  ['sat', 'New data', 'A NISAR pass is published (about 2 days after the satellite), or a FFWC river reading, or a day of IMERG rain.', 'নতুন তথ্য', 'NISAR-এর নতুন ছবি প্রকাশ (উপগ্রহ যাওয়ার প্রায় ২ দিন পর), বা FFWC-এর নদীর মাপ, বা IMERG-এর এক দিনের বৃষ্টি।'],
  ['receipt', 'Fixed rule', 'Typed, range-checked rules: new water within 1 km of home; river at danger level −0.30 m; rain over your own level. No AI.', 'নির্দিষ্ট নিয়ম', 'যাচাই করা নিয়ম: বাড়ির ১ কিমির মধ্যে নতুন পানি; নদী বিপদসীমার ০.৩০ মি নিচে; আপনার ঠিক করা সীমার বেশি বৃষ্টি। কোনো এআই নয়।'],
  ['bell', 'Draft', 'The rule can only draft. Each draft carries the evidence receipt: granule, threshold, ±1 dB test, data age.', 'খসড়া', 'নিয়ম শুধু খসড়া বানাতে পারে। প্রতিটি খসড়ায় প্রমাণ থাকে: কোন ছবি, কোন সীমা, ±১ ডিবি পরীক্ষা, তথ্যের বয়স।'],
  ['shield', 'A volunteer approves', 'Nothing is sent without a person. A draft not approved in 15 minutes turns red; it never sends itself.', 'স্বেচ্ছাসেবকের অনুমোদন', 'মানুষ ছাড়া কিছুই পাঠানো হয় না। ১৫ মিনিটে অনুমোদন না হলে খসড়া লাল হয়; নিজে থেকে কখনো যায় না।'],
  ['speaker', 'The phone speaks', 'App alert with vibration and light, push, email; voice call and SMS shown as demos. Bangla first, read aloud.', 'ফোন পড়ে শোনায়', 'কাঁপুনি ও আলোসহ অ্যাপ সতর্কবার্তা, পুশ, ইমেইল; ফোন কল ও এসএমএস ডেমো হিসেবে। বাংলায়, পড়ে শোনানো।'],
  ['phone', 'Safe or help', 'Press and hold “আমি নিরাপদ” or “সাহায্য দরকার”, or press 1 or 2 on a call. Unanswered: retried twice.', 'নিরাপদ নাকি সাহায্য', '“আমি নিরাপদ” বা “সাহায্য দরকার” চেপে ধরুন, বা কলে ১ অথবা ২ চাপুন। উত্তর না এলে দুবার আবার পাঠানো হয়।'],
  ['users', 'Follow-up', '“Help” opens a call-back task for the volunteer. The alert closes only when every help request is done.', 'খোঁজ নেওয়া', '“সাহায্য” চাইলে স্বেচ্ছাসেবকের কাছে ফোন করার কাজ যায়। সব অনুরোধের পর সতর্কবার্তা বন্ধ হয়।'],
  ['check', 'Counted', 'Every step writes one row to an append-only ledger. Impact numbers are counted from it, nowhere else.', 'গোনা হয়', 'প্রতিটি ধাপ একটি খাতায় লেখা হয়, যা মোছা যায় না। প্রভাবের সংখ্যা শুধু সেখান থেকেই গোনা।'],
];

function LoopSection() {
  const { L } = useL();
  return (
    <section className="section" style={{ background: 'linear-gradient(180deg,#fff, var(--mist))' }}>
      <div className="container">
        <div className="split" style={{ alignItems: 'end' }}>
          <div>
            <div className="eyebrow" style={{ color: 'var(--kantha)' }}><Icon name="users" size={15} /> {L('From pixels to people', 'ছবি থেকে মানুষের কাছে')}</div>
            <h2>{L('A map does not save anyone. A message that is heard, and answered, might.', 'মানচিত্র কাউকে বাঁচায় না। যে বার্তা শোনা যায় আর যার উত্তর দেওয়া যায়, সেটি হয়তো বাঁচায়।')}</h2>
          </div>
          <p className="lead" style={{ marginBottom: 12 }}>
            {L('Many people on the chars share basic phones and many do not read. Voice alerts worked better than SMS in a Practical Action pilot with about 10,000 people, and the government already runs a free voice forecast line, 1090. বন্যা সাথী adds what radar saw near each home, and a way to answer.',
              'চরের অনেকে সাধারণ ফোন ভাগাভাগি করে ব্যবহার করেন, অনেকে পড়তে পারেন না। প্রায় ১০,০০০ মানুষের এক পাইলট প্রকল্পে (প্র্যাকটিক্যাল অ্যাকশন) এসএমএসের চেয়ে ভয়েস বার্তা বেশি কাজে এসেছে; সরকারের বিনা খরচের পূর্বাভাস লাইন ১০৯০ আগে থেকেই আছে। বন্যা সাথী যোগ করে প্রতিটি বাড়ির কাছে রাডার কী দেখেছে, আর উত্তর দেওয়ার উপায়।')}
          </p>
        </div>
        <ol className="loop">
          {LOOP.map(([ic, ten, den, tbn, dbn], i) => (
            <li key={ten} className={i === 5 ? 'hl' : ''}>
              <span className="n">{i + 1}</span>
              <span className="ic"><Icon name={ic} size={20} /></span>
              <b>{L(ten, tbn)}</b>
              <span className="small">{L(den, dbn)}</span>
            </li>
          ))}
        </ol>
        <div className="cta-band">
          <div>
            <h3 style={{ margin: 0 }}>{L('Try the whole loop yourself, on the real 24 July 2026 pass.', '২৪ জুলাই ২০২৬-এর আসল ছবি দিয়ে পুরো ধাপগুলো নিজেই চালিয়ে দেখুন।')}</h3>
            <p className="small muted" style={{ margin: '4px 0 0' }}>{L('You play the volunteer. A phone beside you gets the alert, speaks it, and answers. Scan a QR code to make it your own phone. About two minutes.', 'আপনি স্বেচ্ছাসেবক। পাশের ফোনে সতর্কবার্তা আসবে, পড়ে শোনাবে, উত্তর দেবে। কিউআর কোড স্ক্যান করে নিজের ফোনও যোগ করতে পারেন। প্রায় দুই মিনিট।')}</p>
          </div>
          <Link to="/demo" className="btn btn-kantha btn-lg"><Icon name="play" size={18} /> {L('Start the live demo', 'লাইভ ডেমো শুরু করুন')}</Link>
        </div>
      </div>
      <style>{`
        .loop{list-style:none;padding:0;margin:32px 0 0;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
        @media (max-width:900px){.loop{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @media (max-width:520px){.loop{grid-template-columns:1fr}}
        .loop li{position:relative;background:#fff;border:1px solid var(--line);border-radius:var(--r-lg);padding:18px 18px 16px;display:grid;gap:8px;align-content:start}
        .loop li .ic{width:38px;height:38px;border-radius:11px;display:grid;place-items:center;background:var(--river-lt);color:var(--river)}
        .loop li b{color:var(--ink);font-family:var(--font-display);font-size:1.12rem}
        .loop li .small{color:var(--ink-2)}
        .loop li .n{position:absolute;top:16px;right:16px;font:700 .8rem var(--font-mono);color:var(--ink-3)}
        .loop li.hl{border-color:var(--kantha);box-shadow:0 0 0 3px var(--kantha-lt)}
        .loop li.hl .ic{background:var(--kantha-lt);color:var(--kantha)}
        .cta-band{margin-top:28px;display:flex;flex-wrap:wrap;gap:16px;justify-content:space-between;align-items:center;padding:22px 26px;border-radius:var(--r-lg);border:1px solid #e7c6d9;background:linear-gradient(90deg,var(--kantha-lt),#fff)}
      `}</style>
    </section>
  );
}

// ---------------------------------------------------------------- limits
function LimitsSection() {
  const { L } = useL();
  return (
    <section className="section tight" style={{ background: 'var(--mist)' }}>
      <div className="container split even" style={{ alignItems: 'start' }}>
        <div>
          <div className="eyebrow"><Icon name="info" size={15} /> {L('What we do not claim', 'যা আমরা দাবি করি না')}</div>
          <h2 style={{ fontSize: 'clamp(1.5rem,2.6vw,2rem)' }}>{L('Said before anyone asks.', 'কেউ জিজ্ঞেস করার আগেই বলে রাখি।')}</h2>
          <ul className="ticks no" style={{ marginTop: 14 }}>
            <li><span>{L(<><b>Not real-time.</b> Radar arrives about two days after each pass (45–71 h on track 069A since late July). Rain within a day or two; river daily.</>, <><b>তাৎক্ষণিক নয়।</b> প্রতিটি ছবি উপগ্রহ যাওয়ার প্রায় দুই দিন পর আসে (জুলাইয়ের শেষ থেকে ৪৫–৭১ ঘণ্টা)। বৃষ্টির তথ্য এক-দুই দিনে; নদীর তথ্য প্রতিদিন।</>)}</span></li>
            <li><span>{L(<><b>Not a forecast.</b> Our model does not beat the last picture; we show the picture and its age.</>, <><b>পূর্বাভাস নয়।</b> আমাদের মডেল আগের ছবির চেয়ে ভালো নয়; তাই ছবি আর তার বয়স দেখানো হয়।</>)}</span></li>
            <li><span>{L(<><b>Not an official warning.</b> Official forecasts: FFWC and BMD; call 1090. Every alert says so.</>, <><b>সরকারি সতর্কবার্তা নয়।</b> সরকারি পূর্বাভাস: FFWC ও BMD; ১০৯০ নম্বরে ফোন করুন। প্রতিটি সতর্কবার্তায় তা লেখা থাকে।</>)}</span></li>
            <li><span>{L(<><b>Not depth.</b> Terrain data is too coarse for “knee-deep”. We give walking minutes to the nearest new water.</>, <><b>পানির গভীরতা নয়।</b> ভূমির তথ্য এত সূক্ষ্ম নয়; তাই নতুন পানি কত মিনিট হাঁটা দূরে, তা বলা হয়।</>)}</span></li>
          </ul>
        </div>
        <div>
          <div className="eyebrow"><Icon name="check" size={15} /> {L('What is real in this demo', 'এই ডেমোতে কী আসল')}</div>
          <h2 style={{ fontSize: 'clamp(1.5rem,2.6vw,2rem)' }}>{L('Real data, labelled replay.', 'আসল তথ্য, চিহ্নিত রিপ্লে।')}</h2>
          <ul className="ticks" style={{ marginTop: 14 }}>
            <li><span>{L('Every radar number comes from real NISAR files (PROVISIONAL, CRID P05023; VALIDATED from 25 Oct), with granule IDs.', 'রাডারের প্রতিটি সংখ্যা আসল NISAR ফাইল থেকে (২৫ অক্টোবরের আগে প্রাথমিক, পরে যাচাইকৃত), ফাইলের নামসহ।')}</span></li>
            <li><span>{L('The replay uses only data that NASA had published at that moment. The screen says REPLAY.', 'রিপ্লেতে শুধু সেই সময়ে নাসার প্রকাশিত তথ্যই ব্যবহার হয়। পর্দায় “রিপ্লে” লেখা থাকে।')}</span></li>
            <li><span>{L('Rules, approvals, replies and the ledger are the production code. Voice calls and SMS are simulated and labelled.', 'নিয়ম, অনুমোদন, উত্তর আর খাতা আসল কোড। ফোন কল ও এসএমএস অনুকরণ, তা লেখা থাকে।')}</span></li>
            <li><span>{L('All people in the demo are demo participants, placed at real union centre points.', 'ডেমোর সবাই ডেমো অংশগ্রহণকারী, আসল ইউনিয়নের কেন্দ্রে বসানো।')}</span></li>
          </ul>
          <Link to="/methods" className="btn btn-ghost" style={{ marginTop: 18 }}>{L('Methods, data and licences', 'পদ্ধতি, তথ্য ও লাইসেন্স')} <Icon name="arrow" size={16} /></Link>
        </div>
      </div>
    </section>
  );
}
