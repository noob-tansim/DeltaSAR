/**
 * Live NASA services called straight from the browser. None needs a key; all send CORS headers.
 *   CMR    https://cmr.earthdata.nasa.gov  (granule search: newest NISAR pass, OPERA files)
 *   GIBS   https://gibs.earthdata.nasa.gov (map tiles: NISAR, OPERA DSWx, IMERG, MODIS flood, Sentinel-1)
 *   EONET  https://eonet.gsfc.nasa.gov     (natural events: floods)
 *   POWER  https://power.larc.nasa.gov     (daily rain at a point)
 */
import { useEffect, useState } from 'react';
import { BBOX } from './data';

const BB = BBOX.join(',');

export type LivePass = { granule: string; track: string; acquired_utc: string; published_utc: string; maturity: 'VALIDATED' | 'PROVISIONAL'; full_frame: boolean; latency_h: number };

function parseGranule(item: any, maturity: LivePass['maturity']): LivePass {
  const ur: string = item.umm.GranuleUR;
  const m = ur.match(/_(\d{3})_([AD])_/);
  return {
    granule: ur,
    track: m ? `${m[1]}${m[2]}` : '?',
    acquired_utc: item.umm.TemporalExtent.RangeDateTime.BeginningDateTime,
    published_utc: item.meta['revision-date'],
    maturity,
    full_frame: /_F_J_/.test(ur),
    latency_h: (new Date(item.meta['revision-date']).getTime() - new Date(item.umm.TemporalExtent.RangeDateTime.BeginningDateTime).getTime()) / 3.6e6,
  };
}

/** Newest NISAR L2 GCOV granules over the reach, validated and provisional collections together. */
export async function newestNisar(n = 6): Promise<LivePass[]> {
  const q = (sn: string) => `https://cmr.earthdata.nasa.gov/search/granules.umm_json?short_name=${sn}&bounding_box=${BB}&sort_key=-start_date&page_size=${n}`;
  const [v, p] = await Promise.all([
    fetch(q('NISAR_L2_GCOV_V1')).then((r) => r.json()),
    fetch(q('NISAR_L2_GCOV_PROVISIONAL_V1')).then((r) => r.json()),
  ]);
  const all = [...(v.items ?? []).map((i: any) => parseGranule(i, 'VALIDATED')), ...(p.items ?? []).map((i: any) => parseGranule(i, 'PROVISIONAL'))];
  return all.sort((a, b) => b.acquired_utc.localeCompare(a.acquired_utc)).slice(0, n);
}

export async function operaCount(sinceIso: string): Promise<number> {
  const r = await fetch(`https://cmr.earthdata.nasa.gov/search/granules.json?short_name=OPERA_L3_DSWX-S1_V1&bounding_box=${BB}&temporal=${sinceIso},&page_size=0`);
  return Number(r.headers.get('CMR-Hits') ?? 0);
}

export type FloodEvent = { id: string; title: string; date: string; link: string; lon: number; lat: number };
export async function eonetFloods(): Promise<FloodEvent[]> {
  const r = await fetch('https://eonet.gsfc.nasa.gov/api/v3/events?category=floods&status=all&start=2026-05-01&end=2026-12-31');
  const j = await r.json();
  return (j.events ?? [])
    .filter((e: any) => /Bangladesh/i.test(e.title))
    .map((e: any) => ({ id: e.id, title: e.title, date: e.geometry?.[0]?.date, link: e.link, lon: e.geometry?.[0]?.coordinates?.[0], lat: e.geometry?.[0]?.coordinates?.[1] }));
}

export async function powerRain(lat: number, lon: number, days = 14): Promise<{ date: string; mm: number | null }[]> {
  const end = new Date();
  const start = new Date(end.getTime() - days * 864e5);
  const f = (d: Date) => d.toISOString().slice(0, 10).replace(/-/g, '');
  const r = await fetch(`https://power.larc.nasa.gov/api/temporal/daily/point?parameters=PRECTOTCORR&community=AG&longitude=${lon.toFixed(3)}&latitude=${lat.toFixed(3)}&start=${f(start)}&end=${f(end)}&format=JSON`);
  const j = await r.json();
  const p = j.properties?.parameter?.PRECTOTCORR ?? {};
  return Object.entries(p).map(([d, v]) => ({ date: d, mm: (v as number) < 0 ? null : (v as number) }));
}

// ---------------------------------------------------------------- GIBS
export type GibsLayer = { id: string; title: string; matrix: string; ext: 'png' | 'jpg'; maxzoom: number; note: string };
export const GIBS: Record<string, GibsLayer> = {
  nisar: { id: 'NISAR_L2_Geocoded_Polarimetric_Covariance', title: 'NISAR radar (L-band GCOV, false colour)', matrix: 'GoogleMapsCompatible_Level13', ext: 'png', maxzoom: 13, note: 'NASA-ISRO NISAR, through NASA GIBS. One picture per pass date.' },
  opera: { id: 'OPERA_L3_Dynamic_Surface_Water_Extent-Sentinel-1', title: 'OPERA water extent (Sentinel-1, C-band)', matrix: 'GoogleMapsCompatible_Level12', ext: 'png', maxzoom: 12, note: 'NASA JPL OPERA DSWx-S1: an independent water map from another radar.' },
  rtc: { id: 'OPERA_L2_Radiometric_Terrain_Corrected_SAR_Sentinel-1', title: 'Sentinel-1 C-band backscatter (OPERA RTC)', matrix: 'GoogleMapsCompatible_Level12', ext: 'png', maxzoom: 12, note: 'C-band radar for comparison with NISAR L-band.' },
  imerg: { id: 'IMERG_Precipitation_Rate', title: 'IMERG rain rate, daily', matrix: 'GoogleMapsCompatible_Level6', ext: 'png', maxzoom: 6, note: 'NASA GPM IMERG.' },
  modisflood: { id: 'MODIS_Combined_Flood_2-Day', title: 'MODIS flood, 2-day', matrix: 'GoogleMapsCompatible_Level9', ext: 'png', maxzoom: 9, note: 'Optical flood map: shows what cloud does in the monsoon.' },
  truecolor: { id: 'MODIS_Terra_CorrectedReflectance_TrueColor', title: 'MODIS Terra true colour', matrix: 'GoogleMapsCompatible_Level9', ext: 'jpg', maxzoom: 9, note: 'What an ordinary camera in space sees that day.' },
  viirs: { id: 'VIIRS_SNPP_CorrectedReflectance_TrueColor', title: 'VIIRS true colour', matrix: 'GoogleMapsCompatible_Level9', ext: 'jpg', maxzoom: 9, note: 'Daily optical picture.' },
};
export function gibsTiles(layer: GibsLayer, date: string): string {
  return `https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/${layer.id}/default/${date}/${layer.matrix}/{z}/{y}/{x}.${layer.ext}`;
}
/** YYYYMMDD (UTC) → YYYY-MM-DD */
export const isoDay = (ymd: string) => `${ymd.slice(0, 4)}-${ymd.slice(4, 6)}-${ymd.slice(6, 8)}`;

export function useNewestNisar() {
  const [passes, setPasses] = useState<LivePass[] | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    newestNisar().then(setPasses).catch(() => setError(true));
  }, []);
  return { passes, error };
}

// ---------------------------------------------------------------- ASF (Alaska Satellite Facility, NASA's SAR archive)
export type AsfScene = { scene: string; start: string; path: number; direction: string; url: string; validated: boolean };
/** NISAR GCOV scenes over the reach from the ASF Search API (the API behind ASF Vertex), newest first. No key. */
export async function asfNisar(n = 6): Promise<AsfScene[]> {
  const poly = `POLYGON((${BBOX[0]} ${BBOX[1]},${BBOX[2]} ${BBOX[1]},${BBOX[2]} ${BBOX[3]},${BBOX[0]} ${BBOX[3]},${BBOX[0]} ${BBOX[1]}))`;
  const r = await fetch(`https://api.daac.asf.alaska.edu/services/search/param?dataset=NISAR&processingLevel=GCOV&intersectsWith=${encodeURIComponent(poly)}&maxResults=${n}&output=geojson`);
  const j = await r.json();
  return (j.features ?? []).map((f: any) => ({
    scene: f.properties.sceneName, start: f.properties.startTime, path: f.properties.pathNumber, direction: f.properties.flightDirection,
    url: f.properties.url, validated: !String(f.properties.url).includes('PROVISIONAL'),
  }));
}

// ---------------------------------------------------------------- live connection check
export type Probe = { id: string; name: string; what: string; ok: boolean | null; ms: number | null; detail: string; url: string };
async function timed<T>(fn: () => Promise<T>): Promise<[T, number]> {
  const t0 = performance.now();
  const v = await fn();
  return [v, Math.round(performance.now() - t0)];
}
/** Ask every NASA service the site uses for something real about the reach, from this browser, now. */
export async function probeAll(apiBase: string, onEach: (p: Probe) => void): Promise<void> {
  const run = async (id: string, name: string, what: string, url: string, fn: () => Promise<string>) => {
    try {
      const [detail, ms] = await timed(fn);
      onEach({ id, name, what, ok: true, ms, detail, url });
    } catch (e) {
      onEach({ id, name, what, ok: false, ms: null, detail: String((e as Error).message ?? e).slice(0, 120), url });
    }
  };
  await Promise.all([
    run('cmr', 'NASA CMR (Earthdata Search)', 'Newest NISAR GCOV granule over the reach', 'https://cmr.earthdata.nasa.gov', async () => {
      const p = (await newestNisar(2))[0];
      if (!p) throw new Error('no granule');
      return `${p.acquired_utc.slice(0, 10)} · track ${p.track} · ${p.maturity}`;
    }),
    run('asf', 'ASF Search API (Vertex)', 'NISAR GCOV scenes in NASA\'s SAR archive', 'https://search.asf.alaska.edu', async () => {
      const s = await asfNisar(3);
      if (!s.length) throw new Error('no scenes');
      return `${s.length} newest: ${s[0]!.start.slice(0, 10)}, path ${s[0]!.path} ${s[0]!.direction.toLowerCase()}`;
    }),
    run('gibs', 'NASA GIBS', 'NISAR radar map tile for the newest pass', 'https://gibs.earthdata.nasa.gov', async () => {
      const r = await fetch(gibsTiles(GIBS.nisar!, '2026-11-09').replace('{z}', '9').replace('{y}', '220').replace('{x}', '383'));
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return `tile ${Math.round(((await r.blob()).size) / 1024)} KB, 9 Nov 2026`;
    }),
    run('eonet', 'NASA EONET', 'Flood events in Bangladesh, 2026', 'https://eonet.gsfc.nasa.gov', async () => {
      const f = await eonetFloods();
      return `${f.length} flood events; newest ${f.sort((a, b) => b.date.localeCompare(a.date))[0]?.date.slice(0, 10) ?? '–'}`;
    }),
    run('power', 'NASA POWER', 'Daily rain at the reach centre, last 7 days', 'https://power.larc.nasa.gov', async () => {
      const d = (await powerRain(24.5, 89.69, 7)).filter((x) => x.mm != null);
      return `${d.length} days, ${d.reduce((a, x) => a + (x.mm ?? 0), 0).toFixed(1)} mm in total`;
    }),
    run('api', 'DeltaSAR API (our server)', 'Rules, alerts, ledger; IMERG rain and FFWC river inside', apiBase || window.location.origin, async () => {
      const r = await fetch(`${apiBase}/api/v1/health`);
      const j = await r.json();
      if (!r.ok || !j.ok) throw new Error(`HTTP ${r.status}`);
      return `${j.radar_passes} radar passes · ${j.rain_days} IMERG rain days · ${j.database}`;
    }),
  ]);
}
