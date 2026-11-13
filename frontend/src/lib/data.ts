/** Static data built by backend/jobs/build_web_data.py and served from the CDN under /data/. */
import { useEffect, useState } from 'react';

export const BBOX: [number, number, number, number] = [89.46, 24.205, 89.918, 24.8];
export const IMG_BOUNDS: [number, number, number, number] = [89.461504, 24.205168, 89.917721, 24.799402];
export const CENTER: [number, number] = [89.69, 24.5];
export const GAP: [string, string] = ['2026-07-27T22:03:25Z', '2026-08-10T00:55:27Z'];
export const HEAD_PAIR = { id: 'erosion_069A_interim', before: '20260618', after: '20261004', confirm: '20261016', track: '069A' };

export type Granule = {
  track: string; acquired_utc: string; published_utc: string; latency_hours: number; collection: string; maturity: string;
  crid: string; frame: string; mode: string; full_frame: boolean; granule: string; cmr_id: string;
};
export type Processed = {
  key: string; track: string; date: string; acquired_utc: string; published_utc: string | null; granule_id: string | null; cmr_id: string | null;
  processing_level: string | null; is_baseline: boolean; threshold_db: number | null; new_water_km2: { strict: number; mid: number; loose: number } | null;
  range_within_25pct: boolean | null; unknown_pct: number | null; water_km2: number | null; water_outside_channel_km2: number | null;
  discharge_m3s: number | null; water_png: string | null; newwater_png: string | null; sar_webp: string | null;
};
export type Season = {
  aoi: { id: string; label: string; bbox: number[]; grid_m: number };
  gap_utc: string[];
  cmr: { retrieved_utc: string; granules: Granule[] };
  processed: Processed[];
  daily: { date: string; discharge_m3s: number | null; rain_power_mm: number | null; rain_imerg_mm: number | null }[];
  pictures: {
    bounds: number[]; water: Record<string, string>; newwater: Record<string, string>; sar: Record<string, string>;
    optical: Record<string, { url: string; label: string }>; bankloss: Record<string, string>; other: Record<string, string>;
  };
  thresholds_by_track: Record<string, { threshold_db: number; method: string; water_median_db: number; land_median_db: number; baseline_pass: string }>;
  fit: { slope_km2_per_1000m3s: number; intercept_km2: number; r2: number; n: number };
  fit_takeaway: string;
  sources: Record<string, string>;
};
export type Story = {
  headline_pair: { mainland_bank_loss_ha_range: [number, number]; mainland_bank_loss_ha_mid: number; bank_loss_confirmed: boolean; confirm_pass: string; new_water_km2_range: [number, number]; threshold: { threshold_db: number; method: string; water_median_db: number; land_median_db: number }; caveat: string; exposure: { mainland_bank_loss: { sites: number; area_ha: number; buildings: number; land_cover: { ha: Record<string, number>; pct: Record<string, number>; labels: Record<string, string> } } } };
  pairs: Record<string, { track: string; before: string; after: string; confirm_pass: string | null; mainland_bank_loss_ha_range: number[] | null; bank_loss_confirmed: boolean; new_water_km2_range: number[] | null; flooded_vegetation_km2_range: number[] | null }>;
  insights: {
    frequency: { n_passes: number; histogram: { times_under_water: number; area_ha: number }[]; by_date: { date: string; buildings_in_water: number; cropland_in_water_ha: number }[]; takeaway: string; caveat: string };
    bankloss_time: { rows: { date: string; bank_loss_ha_low: number; bank_loss_ha_high: number; bank_loss_ha_mid: number; discharge_m3s: number; flow_ratio_vs_18jun: number; comparable_flow: boolean; confirmed: boolean }[]; takeaway: string; caveat: string };
    where: { rows: { union: string; upazila: string; sites: number; bank_loss_ha: number; cropland_ha: number; buildings: number; largest_site: string; largest_ha: number; lat: number; lon: number }[]; takeaway: string };
    near_bank: { rows: { within_m: number; buildings: number; cropland_ha: number }[]; by_union: { union: string; upazila: string; buildings_50m: number; buildings_100m: number; buildings_200m: number; buildings_500m: number }[]; top_stretches: { stretch: number; length_m: number; buildings_within_100m: number; union: string; upazila: string; lat: number; lon: number; rank: number }[]; takeaway: string; caveat: string; label: string };
    retreat: { sites: { site_id: string; union: string; area_ha: number; lat: number; lon: number; series: { date: string; retreat_m: number; comparable_flow: boolean }[]; rate_m_per_day?: number }[]; takeaway: string };
    learned: string[];
  };
  river_fit: { slope_km2_per_1000m3s: number; r2: number; n: number };
};
export type UnionRow = {
  union_id: string; name_en: string; name_bn: string | null; upazila: string | null; lat: number; lon: number;
  new_water_km2_range: number[] | null; bank_loss_ha_range: number[] | null; bank_loss_confirmed: boolean | null;
  flooded_vegetation_km2_range: number[] | null; buildings_within_100m_of_retreating_bank: number | null;
  buildings_within_500m_of_retreating_bank: number | null; bank_loss_sites: number | null; cropland_lost_ha: number | null; buildings_on_lost_land: number | null;
};
export type Validation = {
  persistence: { csi: number; hit: number; far: number; pass: string; from: string }[];
  pol: { date: string; HH: { water_med: number; land_med: number; contrast_db: number }; HV: { water_med: number; land_med: number; contrast_db: number } }[];
  skill?: { rows: { pass: string; stage_proxy: number; ml: number; persistence: number | null }[]; mean: { stage_proxy: number; ml: number; persistence: number }; persistence_wins: number; n: number; metric: string; sources: Record<string, string> };
};

const cache = new Map<string, Promise<unknown>>();
export function loadJSON<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`/data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export function useData<T>(path: string): { data: T | null; error: string | null } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let alive = true;
    loadJSON<T>(path).then((d) => alive && setData(d)).catch((e) => alive && setError(String(e)));
    return () => { alive = false; };
  }, [path]);
  return { data, error };
}

export const dataUrl = (rel: string) => `/data/${rel}`;
