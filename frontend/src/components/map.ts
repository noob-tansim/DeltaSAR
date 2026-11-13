/** MapLibre helpers: a no-key base map, image overlays on the reach, NASA GIBS tile layers. */
import * as maplibregl from 'maplibre-gl';
import type { Map as MLMap, StyleSpecification } from 'maplibre-gl';
import { IMG_BOUNDS } from '../lib/data';
import { gibsTiles, type GibsLayer } from '../lib/nasa';
// MapLibre 6 runs its tile parsing in a module worker; let Vite bundle it with its imports.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';

maplibregl.setWorkerUrl(workerUrl);

export type BaseKind = 'dark' | 'light' | 'satellite';
// Esri basemap tile services (no key; attribution required). Online only: never cached or bundled.
const ESRI = (svc: string) => [`https://server.arcgisonline.com/ArcGIS/rest/services/${svc}/MapServer/tile/{z}/{y}/{x}`];
const ATTR = 'Basemap: Esri, HERE, Garmin, © OpenStreetMap contributors';
const ATTR_SAT = 'Imagery: Esri, Maxar, Earthstar Geographics';

export function baseStyle(kind: BaseKind): StyleSpecification {
  const dark = kind !== 'light';
  const base = kind === 'satellite' ? 'World_Imagery' : dark ? 'Canvas/World_Dark_Gray_Base' : 'Canvas/World_Light_Gray_Base';
  const labels = dark ? 'Canvas/World_Dark_Gray_Reference' : 'Canvas/World_Light_Gray_Reference';
  return {
    version: 8,
    sources: {
      base: { type: 'raster', tiles: ESRI(base), tileSize: 256, attribution: kind === 'satellite' ? ATTR_SAT : ATTR, maxzoom: kind === 'satellite' ? 18 : 16 },
      labels: { type: 'raster', tiles: ESRI(labels), tileSize: 256, maxzoom: 16 },
    },
    layers: [
      { id: 'bg', type: 'background', paint: { 'background-color': dark ? '#0a1821' : '#eef3f3' } },
      { id: 'base', type: 'raster', source: 'base', paint: { 'raster-opacity': kind === 'dark' ? 0.75 : 1, 'raster-saturation': kind === 'dark' ? -0.3 : 0 } },
      { id: 'labels', type: 'raster', source: 'labels', paint: { 'raster-opacity': dark ? 0.9 : 0.95 } },
    ],
  };
}

export function createMap(el: HTMLElement, opts: { base?: BaseKind; center?: [number, number]; zoom?: number; interactive?: boolean; bounds?: [number, number, number, number]; attribution?: boolean } = {}): MLMap {
  const map = new maplibregl.Map({
    container: el,
    style: baseStyle(opts.base ?? 'dark'),
    center: opts.center ?? [89.69, 24.5],
    zoom: opts.zoom ?? 9.2,
    interactive: opts.interactive ?? true,
    attributionControl: opts.attribution === false ? false : { compact: true },
    cooperativeGestures: false,
    dragRotate: false,
    pitchWithRotate: false,
    maxZoom: 16,
    fadeDuration: 0,
  });
  map.touchZoomRotate.disableRotation();
  // NASA GIBS has no tiles outside a pass's swath (HTTP 404/500): a gap in the picture, not an app error
  map.on('error', (e) => {
    const err = (e as { error?: { message?: string; name?: string; status?: number } }).error;
    if (err?.status || /AJAX|fetch|network|https?:\/\//i.test(`${err?.name ?? ''} ${err?.message ?? ''}`)) return;
    console.warn('[map]', err?.message);
  });
  if (import.meta.env.DEV) ((window as unknown as { __maps?: MLMap[] }).__maps ??= []).push(map);
  if (opts.bounds) map.fitBounds([[opts.bounds[0], opts.bounds[1]], [opts.bounds[2], opts.bounds[3]]], { padding: 20, duration: 0 });
  return map;
}

export function whenReady(map: MLMap, fn: () => void): void {
  if (map.isStyleLoaded()) fn();
  else map.once('load', fn);
}

const coords = (b: readonly number[] = IMG_BOUNDS) => {
  const [w, s, e, n] = b as [number, number, number, number];
  return [[w, n], [e, n], [e, s], [w, s]] as [[number, number], [number, number], [number, number], [number, number]];
};

/** Add or update an image overlay (our maps of the reach). Placed under the labels. */
export function setImage(map: MLMap, id: string, url: string | null, opacity = 1, before = 'labels', bounds?: readonly number[]): void {
  const src = map.getSource(id) as maplibregl.ImageSource | undefined;
  if (!url) {
    if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', 'none');
    return;
  }
  if (src) {
    src.updateImage({ url, coordinates: coords(bounds) });
    map.setLayoutProperty(id, 'visibility', 'visible');
    map.setPaintProperty(id, 'raster-opacity', opacity);
    return;
  }
  map.addSource(id, { type: 'image', url, coordinates: coords(bounds) });
  map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 0, 'raster-resampling': 'linear' } }, map.getLayer(before) ? before : undefined);
}

export function setVisible(map: MLMap, id: string, on: boolean): void {
  if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none');
}

/** NASA GIBS WMTS layer for one date (YYYY-MM-DD). Replaces the source when the date changes. */
export function setGibs(map: MLMap, id: string, layer: GibsLayer | null, date: string | null, opacity = 0.9, before = 'labels'): void {
  const want = layer && date ? gibsTiles(layer, date) : null;
  const cur = map.getSource(id) as (maplibregl.RasterTileSource & { tiles?: string[] }) | undefined;
  if (cur && (!want || cur.tiles?.[0] !== want)) {
    if (map.getLayer(id)) map.removeLayer(id);
    map.removeSource(id);
  }
  if (!want || !layer) return;
  if (!map.getSource(id)) {
    map.addSource(id, { type: 'raster', tiles: [want], tileSize: 256, maxzoom: layer.maxzoom, attribution: 'NASA GIBS / ESDIS' });
    map.addLayer({ id, type: 'raster', source: id, paint: { 'raster-opacity': opacity, 'raster-fade-duration': 150 } }, map.getLayer(before) ? before : undefined);
  } else {
    map.setPaintProperty(id, 'raster-opacity', opacity);
  }
}

export function fitReach(map: MLMap, padding = 24, duration = 0): void {
  const [w, s, e, n] = IMG_BOUNDS;
  map.fitBounds([[w, s], [e, n]], { padding, duration });
}

/** A circle polygon (for "my distance" rings), radius in metres. */
export type PolygonFeature = { type: 'Feature'; properties: Record<string, unknown>; geometry: { type: 'Polygon'; coordinates: [number, number][][] } };
export function circle(lon: number, lat: number, radiusM: number, steps = 64): PolygonFeature {
  const pts: [number, number][] = [];
  const dLat = radiusM / 111_320;
  const dLon = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180));
  for (let i = 0; i <= steps; i++) {
    const a = (i / steps) * 2 * Math.PI;
    pts.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)]);
  }
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [pts] } };
}

export { maplibregl };
