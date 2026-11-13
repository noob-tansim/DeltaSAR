/** Methods, validation, data sources and licences, limits, AI use. Everything a judge needs to check validity. */
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';
import { Footer, Nav, REPO_URL } from '../components/Chrome';
import { Icon } from '../components/Icon';
import { LiveConnections } from '../components/LiveConnections';
import { useL } from '../lib/i18n';
import { useData, type Season, type Validation } from '../lib/data';
import { dShort, n0, pDay, ymd } from '../lib/format';

const STEPS: [string, string][] = [
  ['Find passes', 'NASA CMR search for NISAR L2 GCOV granules over the reach. Only tracks 069A and 019D cover all of it; we never compare across tracks.'],
  ['Read only the reach', 'Range reads of each GCOV HDF5 file (ASF DAAC, Earthdata Login): HH and HV, γ⁰ to dB, values outside −35 to +5 dB masked as unknown.'],
  ['Find the threshold', 'One HH threshold per track from the baseline scene\'s own histogram valley (069A: −15.62 dB). Every area is also computed at −1 and +1 dB.'],
  ['Map water', '3×3 median filter, HH below the threshold = open water; patches under 2,000 m² dropped. Unknown pixels stay unknown, never dry.'],
  ['Compare', 'New water = water now that was land at the baseline pass of the same track. Bank loss = mainland that became channel-connected water at the old bank line, confirmed by a later pass.'],
  ['Publish with receipts', 'Per pass: granule id, CMR id, acquisition and publication time, threshold, ±1 dB areas, unknown %. The alert rules read only these files.'],
  ['Draft, approve, deliver', 'Three fixed rules (radar, river, rain) draft alerts; a volunteer approves; push, email and in-app delivery are real, call and SMS simulated. Every step writes one ledger row.'],
];

const SOURCES: [string, string, string, string, string][] = [
  ['NISAR L2 GCOV (NASA/ISRO)', 'Water maps, bank loss, radar rule', 'ASF DAAC via Earthdata Login (processing only)', 'NASA open data', 'NISAR data courtesy of NASA/JPL-Caltech and ISRO, distributed by ASF DAAC'],
  ['NASA CMR', 'Newest pass, publication delay (live in the browser)', 'cmr.earthdata.nasa.gov, no key', 'NASA open', 'NASA EOSDIS'],
  ['NASA GIBS', 'NISAR, OPERA DSWx-S1, Sentinel-1 RTC, MODIS flood, IMERG, MODIS true colour tiles (live)', 'gibs.earthdata.nasa.gov WMTS, no key', 'NASA open', 'NASA GIBS / ESDIS'],
  ['GPM IMERG V07 Early', 'Rain rule, rain screen, season chart', 'NASA SERVIR ClimateSERV, no key', 'NASA open', 'NASA GPM'],
  ['NASA POWER', 'Rain at any clicked point (live)', 'power.larc.nasa.gov, no key', 'NASA open', 'NASA POWER Project'],
  ['NASA EONET', 'Flood events on the season chart (live)', 'eonet.gsfc.nasa.gov, no key', 'NASA open', 'NASA EONET'],
  ['OPERA DSWx-S1 (NASA JPL)', 'Independent water map from another radar', 'GIBS layer; CMR file count', 'NASA open', 'NASA JPL OPERA'],
  ['FFWC (BWDB)', 'River level and danger level for the river rule', 'Public FFWC pages; typed entry as fallback', 'Public, Government of Bangladesh', 'Flood Forecasting and Warning Centre, BWDB'],
  ['GloFAS v4 via Open-Meteo', 'River flow (model) for context and the drivers chart', 'Open-Meteo Flood API', 'CC BY 4.0', 'Copernicus EMS GloFAS; Open-Meteo.com'],
  ['Copernicus DEM GLO-30, MERIT Hydro HAND', 'Height above the river', 'Google Earth Engine', 'Copernicus licence; CC BY-NC 4.0 / ODbL (we use ODbL)', '© DLR e.V. 2010-2014 and © Airbus 2014-2018 (Copernicus); Yamazaki et al. 2019'],
  ['Sentinel-1/2, JRC Global Surface Water, Landsat 8/9', 'Permanent channel; optical pictures', 'Google Earth Engine', 'Copernicus open; CC BY 4.0; USGS public domain', 'Contains modified Copernicus Sentinel data 2024-2026; Pekel et al. 2016'],
  ['ESA WorldCover 2021', 'Cropland on lost land', 'ESA WorldCover S3', 'CC BY 4.0', '© ESA WorldCover project 2021'],
  ['Google Open Buildings v3', 'Buildings near a moving bank', 'Google', 'CC BY 4.0 / ODbL', 'Sirko et al. 2021'],
  ['geoBoundaries BGD ADM4', 'Unions', 'geoBoundaries', 'CC BY 3.0 IGO', 'Runfola et al. 2020; BBS, OCHA ROAP'],
  ['Esri basemaps', 'Background map (online only, never cached)', 'server.arcgisonline.com', 'Esri terms of use', 'Esri, HERE, Garmin, © OpenStreetMap contributors; Maxar, Earthstar Geographics'],
];

export default function Methods() {
  const { L } = useL();
  const { data: val } = useData<Validation>('validation.json');
  const { data: season } = useData<Season>('season.json');
  const loc = useLocation();
  useEffect(() => {
    if (loc.hash) setTimeout(() => document.getElementById(loc.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }), 200);
  }, [loc.hash]);
  const g069 = season?.cmr.granules.filter((g) => g.track === '069A' && g.full_frame && g.acquired_utc > '2026-07-20') ?? [];
  const afterGap = g069.find((g) => g.acquired_utc.startsWith('2026-08-17'));
  const lat = g069.filter((g) => g !== afterGap).map((g) => g.latency_hours);
  return (
    <>
      <Nav />
      <main id="main" className="on-paper">
        <section className="section tight" style={{ background: 'var(--mist)' }}>
          <div className="narrow">
            <div className="eyebrow"><Icon name="receipt" size={15} /> {L('Methods and data', 'পদ্ধতি ও তথ্য')}</div>
            <h1 style={{ fontSize: 'clamp(2rem,4vw,3rem)' }}>{L('How every number is made, and how sure it is.', 'প্রতিটি সংখ্যা কীভাবে তৈরি, আর তা কতটা নিশ্চিত।')}</h1>
            <p className="lead">{L('Fixed code computes every value; no AI model produces a number or sends an alert. Each value carries a receipt back to the NASA file it came from.', 'প্রতিটি মান নির্দিষ্ট কোড দিয়ে হিসাব করা; কোনো এআই সংখ্যা বানায় না বা সতর্কবার্তা পাঠায় না। প্রতিটি মানের সাথে নাসার যে ফাইল থেকে এসেছে তার প্রমাণ থাকে।')}</p>
            <div className="row" style={{ marginTop: 12 }}>
              <a className="btn btn-primary" href={REPO_URL} target="_blank" rel="noreferrer"><Icon name="github" size={16} /> {L('Open repository (Apache-2.0)', 'উন্মুক্ত কোড (Apache-2.0)')}</a>
              <a className="btn btn-ghost" href="#sources">{L('Data and licences', 'তথ্য ও লাইসেন্স')}</a>
              <a className="btn btn-ghost" href="#limits">{L('Limits', 'সীমাবদ্ধতা')}</a>
            </div>
          </div>
        </section>

        <section className="section tight" id="live" style={{ paddingBottom: 0 }}>
          <div className="narrow"><LiveConnections /></div>
        </section>

        <section className="section tight">
          <div className="narrow">
            <h2>{L('From radar file to answered alert', 'রাডার ফাইল থেকে উত্তর পাওয়া সতর্কবার্তা পর্যন্ত')}</h2>
            <ol className="m-steps">
              {STEPS.map(([t, d], i) => (<li key={t}><span className="n">{i + 1}</span><div><b>{t}</b><p className="small" style={{ margin: '2px 0 0' }}>{d}</p></div></li>))}
            </ol>
            {season && (
              <>
                <h3 style={{ marginTop: 28 }}>Water thresholds, from each track's own scene</h3>
                <table className="table">
                  <thead><tr><th>Track</th><th className="r">Threshold</th><th className="r">Water median</th><th className="r">Land median</th><th>Method</th></tr></thead>
                  <tbody>
                    {Object.entries(season.thresholds_by_track).map(([k, t]) => (
                      <tr key={k}><td><b>{k}</b><div className="tiny muted">baseline {t.baseline_pass}</div></td><td className="r">{t.threshold_db} dB</td><td className="r">{t.water_median_db} dB</td><td className="r">{t.land_median_db} dB</td><td className="small">{t.method}</td></tr>
                    ))}
                  </tbody>
                </table>
                <p className="small muted">Areas are reported at the threshold and ±1 dB. A range wider than ±25 % of its middle makes an alert “less sure”. Track 019D has no clear histogram valley, so it is a cross-check only.</p>
                <h3 style={{ marginTop: 28 }}>How fast is the radar? (measured, not promised)</h3>
                <p className="small">Since late July, NASA published track 069A full frames <b>{lat.length ? `${Math.floor(Math.min(...lat))}–${Math.round(Math.max(...lat))} hours` : '45–71 hours'}</b> after the satellite passed{afterGap ? `, except ${Math.round(afterGap.latency_hours)} hours for 17 Aug, the first pass after the radar gap` : ''} (CMR record insert time, {season.cmr.granules.length} granules checked). Each track repeats every 12 days. The radar was off from 27 July to 10 August 2026; that gap is shown, never filled.</p>
              </>
            )}
          </div>
        </section>

        {val && (
          <section className="section tight" style={{ background: 'var(--mist)' }}>
            <div className="narrow">
              <h2>{L('Validation, pass by pass', 'যাচাই, ছবি ধরে ধরে')}</h2>
              <p>Each pass was predicted without seeing it. CSI = hits / (hits + misses + false alarms) on water outside the permanent channel.</p>
              {val.skill && (
                <table className="table">
                  <thead><tr><th>Pass (069A)</th><th className="r">River-flow rule</th><th className="r">ML model</th><th className="r">Same as last pass</th></tr></thead>
                  <tbody>
                    {val.skill.rows.map((r) => (
                      <tr key={r.pass}><td>{dShort(ymd(r.pass))}</td><td className="r">{r.stage_proxy.toFixed(2)}</td><td className="r">{r.ml.toFixed(2)}</td><td className="r" style={{ fontWeight: r.persistence != null && r.persistence > r.ml ? 700 : 400 }}>{r.persistence?.toFixed(2) ?? '–'}</td></tr>
                    ))}
                    <tr><td><b>Mean</b></td><td className="r"><b>{val.skill.mean.stage_proxy.toFixed(2)}</b></td><td className="r"><b>{val.skill.mean.ml.toFixed(2)}</b></td><td className="r"><b>{val.skill.mean.persistence.toFixed(2)}</b></td></tr>
                  </tbody>
                </table>
              )}
              <p className="small">Conclusion: the newest radar picture is the best guide to the next 12 days. The ML model helps only when the river changes fast (after the radar gap, 17 Aug). The app therefore shows the picture and its age, never a forecast. A rain-only model had no skill on any pass (Brier skill score ≤ 0.04): local rain does not explain the water; upstream flow does better.</p>
              <h3 style={{ marginTop: 24 }}>Which polarisation? Water against stable land, median dB</h3>
              <div style={{ overflowX: 'auto' }}>
                <table className="table">
                  <thead><tr><th>Pass</th><th className="r">HH water</th><th className="r">HH land</th><th className="r">HH contrast</th><th className="r">HV water</th><th className="r">HV land</th><th className="r">HV contrast</th></tr></thead>
                  <tbody>{val.pol.map((p) => (<tr key={p.date}><td>{dShort(ymd(p.date))}</td><td className="r">{p.HH.water_med}</td><td className="r">{p.HH.land_med}</td><td className="r"><b>{p.HH.contrast_db}</b></td><td className="r">{p.HV.water_med}</td><td className="r">{p.HV.land_med}</td><td className="r">{p.HV.contrast_db}</td></tr>))}</tbody>
                </table>
              </div>
              <p className="small">HH separates water from land by about 3 dB more than HV, and water in HV sits near the noise floor (−23 dB). HV is used only to flag flooded vegetation (HH &gt; −8 dB, HH−HV &gt; 6 dB, HH rose ≥ 3 dB), which stays experimental: in October it mostly picks up flooded aman paddy.</p>
            </div>
          </section>
        )}

        <section className="section tight" id="sources">
          <div className="container">
            <h2>{L('Data sources and licences', 'তথ্যের উৎস ও লাইসেন্স')}</h2>
            <p className="muted">NASA open data is the core; other agencies and third parties are named and labelled where they appear.</p>
            <div style={{ overflowX: 'auto' }}>
              <table className="table">
                <thead><tr><th>Source</th><th>Used for</th><th>Access</th><th>Licence</th><th>Attribution</th></tr></thead>
                <tbody>{SOURCES.map((s) => (<tr key={s[0]}><td><b>{s[0]}</b></td><td className="small">{s[1]}</td><td className="small">{s[2]}</td><td className="small">{s[3]}</td><td className="tiny">{s[4]}</td></tr>))}</tbody>
              </table>
            </div>
            <p className="small muted">No api.nasa.gov key is needed for any of the services above. Earthdata Login is needed only to download NISAR files for processing.</p>
            <h3 style={{ marginTop: 28 }}>Challenge resources, and how we used them</h3>
            <div className="grid-2" style={{ marginTop: 10 }}>
              {([
                ['NASA Earthdata Search', 'https://search.earthdata.nasa.gov/search', 'Finding NISAR GCOV and OPERA DSWx granules over the reach; every pass links to its CMR record.'],
                ['ASF Data Search Vertex', 'https://search.asf.alaska.edu/', 'NISAR GCOV downloads and the granule inventory; each pass in the explorer has a “Find in ASF Vertex” link.'],
                ['NISAR Data User Guide (ASF)', 'https://nisar-docs.asf.alaska.edu/', 'Reference for the GCOV product, its maturity labels (PROVISIONAL / VALIDATED), tracks and frames.'],
                ['Intro to SAR (Earthdata)', 'https://www.earthdata.nasa.gov/learn/earth-observation-data-basics/sar', 'Polarisation and scattering: why open water is dark in HH, double bounce in flooded crops, volume scattering in HV.'],
                ['NASA ARSET trainings', 'https://appliedsciences.nasa.gov/get-involved/training', 'Background on SAR flood mapping (thresholds, change detection): the family of methods used here.'],
                ['NISAR StoryMaps and white papers', 'https://nisar.jpl.nasa.gov/applications/arcgis-storymaps/', 'Reference examples of SAR applications for floods and land change.'],
                ['CSA RADARSAT-1 / RCM and SAR Python tutorial', 'https://github.com/asc-csa/Synthetic_Aperture_Radar_Tutorial', 'Not used yet. C-band RCM could add looks between NISAR passes (next step).'],
                ['CONAE SAOCOM catalogue', 'https://catalogos.conae.gov.ar/catalogo/catalogoSatSaocomInfo.html', 'Not used yet (registration). L-band like NISAR, so the same water rule could transfer: a natural partner.'],
              ] as [string, string, string][]).map(([t, u, d]) => (
                <a key={t} href={u} target="_blank" rel="noreferrer" className="card" style={{ textDecoration: 'none', color: 'inherit', padding: 16 }}>
                  <b className="row" style={{ gap: 6, color: 'var(--river)' }}>{t} <Icon name="ext" size={13} /></b>
                  <p className="small" style={{ margin: '6px 0 0', color: 'var(--ink-2)' }}>{d}</p>
                </a>
              ))}
            </div>
          </div>
        </section>

        <section className="section tight" id="limits" style={{ background: 'var(--mist)' }}>
          <div className="narrow">
            <h2>{L('Limits, said plainly', 'সীমাবদ্ধতা, সোজা কথায়')}</h2>
            <ul className="ticks no">
              <li><span>NISAR data before 25 Oct 2026 is PROVISIONAL (CRID P05023). Validated files (P05036) exist from 25 Oct; the 9 Nov pass is the next to ingest. Every screen shows the label of the pass it uses.</span></li>
              <li><span>River level differs between dates: land-to-water change near the bank includes some water-level effect. River flow here is modelled (GloFAS), not a gauge.</span></li>
              <li><span>Buildings are model-detected footprints from older imagery: what stood there, not a damage count.</span></li>
              <li><span>Height above river (MERIT Hydro, about 90 m) has errors of a metre or more: we never show water depth.</span></li>
              <li><span>FFWC river readings for most of the 2026 season are not online in one place; the replay shows the river rule as “no reading” until they are typed in.</span></li>
              <li><span>Rain is one daily value for the whole reach (the wettest IMERG cell), not per home.</span></li>
              <li><span>The demo replays 2026; all people in it are demo participants. Voice calls and SMS are simulated and labelled. Bangla text is a draft awaiting a native reader's check.</span></li>
              <li><span>Not an official warning. Official forecasts: FFWC and BMD; call 1090.</span></li>
            </ul>
          </div>
        </section>

        <section className="section tight" id="ai">
          <div className="narrow">
            <h2>{L('How AI was used', 'এআই কীভাবে ব্যবহার হয়েছে')}</h2>
            <p>AI coding assistants helped write code, documents and draft text. A person on the team reviewed and tested each part. AI computes no number on any screen and is not in the alert path: rules, thresholds and approvals are fixed code and human decisions. The full log of tools, prompts and checks is in <code>docs/AI_USE.md</code> in the repository.</p>
            <h3 style={{ marginTop: 24 }}>Reproduce it</h3>
            <pre className="m-pre">{`# backend (Python 3.11+)
cd backend && pip install -r requirements.txt
python -m pytest tests -q                    # rules, ranges, replay, engine, sandbox
uvicorn src.api.app:app --port 8010

# web app (Node 20+)
cd frontend && npm install && npm run dev    # http://localhost:5173`}</pre>
            <p className="small muted">Team Astro Bengalis · NASA Space Apps Challenge 2026 · Dancing with the SARs. Pass dates are UTC acquisition dates (as in NASA file names); times are shown in Dhaka. Latest processed pass: {season ? pDay(season.processed[season.processed.length - 1]!.acquired_utc) : '–'}; {season ? n0(season.processed.length) : '–'} passes.</p>
          </div>
        </section>
      </main>
      <Footer />
      <style>{`
        .m-steps{list-style:none;padding:0;margin:18px 0 0;display:grid;gap:12px}
        .m-steps li{display:grid;grid-template-columns:34px 1fr;gap:12px}
        .m-steps .n{width:30px;height:30px;border-radius:50%;background:var(--river);color:#fff;display:grid;place-items:center;font-weight:700;font-size:.85rem}
        .m-pre{background:var(--night);color:var(--sky);padding:16px;border-radius:var(--r-md);overflow:auto;font-size:.82rem;font-family:var(--font-mono)}
      `}</style>
    </>
  );
}
