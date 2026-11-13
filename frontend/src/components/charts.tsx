/** Small SVG charts. Every value drawn comes from /data/*.json (see the source line under each chart). */
import { useId, useMemo } from 'react';
import type { Processed, Season, Validation } from '../lib/data';
import { GAP } from '../lib/data';
import { dShort, pDay, ymd } from '../lib/format';
import type { FloodEvent } from '../lib/nasa';

const T0 = Date.UTC(2026, 5, 1);
const T1 = Date.UTC(2026, 10, 16);

export function SeasonChart({ season, selected, onSelect, floods = [], dark = true, height = 300 }: {
  season: Season; selected?: string | null; onSelect?: (key: string) => void; floods?: FloodEvent[]; dark?: boolean; height?: number;
}) {
  const hid = useId().replace(/:/g, '');
  const W = 1000, H = height, L = 52, R = 52, TOP = 18, B = 34;
  const x = (t: number) => L + ((t - T0) / (T1 - T0)) * (W - L - R);
  const plotH = H - TOP - B;
  const flowH = plotH * 0.62;
  const rainTop = TOP + flowH + 16;
  const rainH = plotH - flowH - 16;
  const qMax = 50000;
  const yq = (q: number) => TOP + flowH - (q / qMax) * flowH;
  const wMax = 900;
  const yw = (w: number) => TOP + flowH - (w / wMax) * flowH;
  const rMax = 80;
  const ink = dark ? '#a8bec6' : '#41525e';
  const grid = dark ? 'rgba(214,238,242,.09)' : 'rgba(18,34,46,.08)';

  const flowPath = useMemo(() => {
    const pts = season.daily.filter((d) => d.discharge_m3s != null).map((d) => [x(ymd(d.date).getTime()), yq(d.discharge_m3s as number)]);
    if (!pts.length) return '';
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0]!.toFixed(1)},${p[1]!.toFixed(1)}`).join('');
    return line;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [season]);
  const flowArea = flowPath ? `${flowPath}L${x(ymd(season.daily[season.daily.length - 1]!.date).getTime())},${TOP + flowH}L${x(ymd(season.daily[0]!.date).getTime())},${TOP + flowH}Z` : '';
  const g0 = x(new Date(GAP[0]).getTime());
  const g1 = x(new Date(GAP[1]).getTime());
  const months = [5, 6, 7, 8, 9, 10].map((m) => Date.UTC(2026, m, 1));
  const passes = season.processed;
  const p069 = passes.filter((p) => p.track === '069A' && p.water_km2 != null);

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Jamuna 2026 season: river flow, water area seen by each NISAR pass, daily rain, and the radar gap" style={{ display: 'block', overflow: 'visible' }}>
      <defs>
        <pattern id={`h${hid}`} width="7" height="7" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="7" height="7" fill="transparent" />
          <rect width="2" height="7" fill={dark ? 'rgba(168,190,198,.28)' : 'rgba(107,123,134,.3)'} />
        </pattern>
        <linearGradient id={`f${hid}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor="#3cc8f0" stopOpacity=".28" />
          <stop offset="1" stopColor="#3cc8f0" stopOpacity="0" />
        </linearGradient>
      </defs>
      {[0, 10000, 20000, 30000, 40000, 50000].map((q) => (
        <g key={q}>
          <line x1={L} x2={W - R} y1={yq(q)} y2={yq(q)} stroke={grid} />
          <text x={L - 8} y={yq(q) + 4} fill={ink} fontSize="11" textAnchor="end">{q / 1000}k</text>
        </g>
      ))}
      {[0, 300, 600, 900].map((w) => (
        <text key={w} x={W - R + 8} y={yw(w) + 4} fill="#3cc8f0" fontSize="11">{w}</text>
      ))}
      <text x={L - 8} y={TOP - 6} fill={ink} fontSize="11" textAnchor="end">m³/s</text>
      <text x={W - R + 8} y={TOP - 6} fill="#3cc8f0" fontSize="11">km²</text>
      <rect x={g0} y={TOP} width={g1 - g0} height={plotH} fill={`url(#h${hid})`} />
      <text x={(g0 + g1) / 2} y={TOP + 14} fill={ink} fontSize="11" textAnchor="middle" fontWeight="600">radar off</text>
      {months.map((m) => (
        <g key={m}>
          <line x1={x(m)} x2={x(m)} y1={TOP} y2={H - B} stroke={grid} />
          <text x={x(m) + 4} y={H - B + 18} fill={ink} fontSize="12">{new Date(m).toLocaleString('en-GB', { month: 'short' })}</text>
        </g>
      ))}
      <path d={flowArea} fill={`url(#f${hid})`} />
      <path d={flowPath} fill="none" stroke={dark ? '#e6f1f3' : '#12222e'} strokeWidth="1.6" strokeOpacity=".75" />
      {p069.map((p) => {
        const cx = x(new Date(p.acquired_utc).getTime());
        const sel = selected === p.key;
        return (
          <g key={p.key} onClick={() => onSelect?.(p.key)} style={{ cursor: onSelect ? 'pointer' : 'default' }}>
            <rect x={cx - 7} y={yw(p.water_km2!)} width="14" height={TOP + flowH - yw(p.water_km2!)} rx="3" fill="#3cc8f0" fillOpacity={sel ? 1 : 0.62} stroke={sel ? '#fff' : 'none'} strokeWidth="1.5" />
            <text x={cx} y={yw(p.water_km2!) - 6} fill="#3cc8f0" fontSize="10.5" textAnchor="middle" fontWeight={sel ? 700 : 500}>{Math.round(p.water_km2!)}</text>
          </g>
        );
      })}
      {passes.filter((p) => p.track === '019D').map((p) => {
        const cx = x(new Date(p.acquired_utc).getTime());
        return <circle key={p.key} cx={cx} cy={TOP + flowH - 4} r="4" fill="none" stroke="#3cc8f0" strokeWidth="1.5" onClick={() => onSelect?.(p.key)} style={{ cursor: onSelect ? 'pointer' : 'default' }}><title>{`Track 019D pass ${pDay(p.acquired_utc)}`}</title></circle>;
      })}
      {season.daily.map((d) => {
        const mm = d.rain_imerg_mm;
        if (mm == null || mm <= 0) return null;
        const t = ymd(d.date).getTime();
        const h = (Math.min(mm, rMax) / rMax) * rainH;
        return <rect key={d.date} x={x(t) - 1.6} y={rainTop + rainH - h} width="3.2" height={h} fill={mm >= 76 ? '#ff5a4e' : mm >= 60 ? '#ffb547' : dark ? '#7d97a1' : '#8aa0aa'}><title>{`${dShort(ymd(d.date))}: ${mm} mm (IMERG)`}</title></rect>;
      })}
      <line x1={L} x2={W - R} y1={rainTop + rainH - (76 / rMax) * rainH} y2={rainTop + rainH - (76 / rMax) * rainH} stroke="#ff5a4e" strokeDasharray="4 4" strokeWidth="1" />
      <text x={W - R + 8} y={rainTop + rainH - (76 / rMax) * rainH + 4} fill="#ff5a4e" fontSize="10.5">76 mm</text>
      <text x={L - 8} y={rainTop + 10} fill={ink} fontSize="11" textAnchor="end">rain</text>
      {floods.map((f) => {
        const t = new Date(f.date).getTime();
        if (t < T0 || t > T1) return null;
        return (
          <g key={f.id}>
            <line x1={x(t)} x2={x(t)} y1={TOP} y2={H - B} stroke="#ffb547" strokeDasharray="2 3" />
            <path d={`M${x(t)},${TOP - 2} l-5,-9 h10 z`} fill="#ffb547"><title>{`NASA EONET: ${f.title}, ${dShort(f.date)}`}</title></path>
          </g>
        );
      })}
    </svg>
  );
}

export function ChartLegend({ dark = true, floods = false }: { dark?: boolean; floods?: boolean }) {
  const c = dark ? 'var(--sky-2)' : 'var(--ink-2)';
  const item = (sw: React.ReactNode, t: string) => <span className="row" style={{ gap: 6, color: c, fontSize: '.82rem' }}>{sw}{t}</span>;
  return (
    <div className="row" style={{ gap: 16 }}>
      {item(<span style={{ width: 16, height: 2, background: dark ? '#e6f1f3' : '#12222e' }} />, 'River flow, GloFAS (model)')}
      {item(<span style={{ width: 10, height: 12, borderRadius: 2, background: '#3cc8f0' }} />, 'Water seen by NISAR, track 069A (km²)')}
      {item(<span style={{ width: 10, height: 10, borderRadius: 5, border: '1.5px solid #3cc8f0' }} />, 'Track 019D pass')}
      {item(<span style={{ width: 4, height: 12, background: '#7d97a1' }} />, 'Daily rain, NASA IMERG (wettest cell)')}
      {item(<span className="hatch" style={{ width: 16, height: 12, borderRadius: 2 }} />, 'Radar off, 27 Jul–10 Aug')}
      {floods && item(<span style={{ width: 0, height: 0, borderLeft: '5px solid transparent', borderRight: '5px solid transparent', borderTop: '9px solid #ffb547' }} />, 'NASA EONET flood event')}
    </div>
  );
}

/** HH against HV: water-to-land contrast per pass (dB). */
export function PolChart({ v, dark = true }: { v: Validation; dark?: boolean }) {
  const W = 560, H = 230, L = 40, B = 30, T = 14;
  const n = v.pol.length;
  const x = (i: number) => L + 16 + (i * (W - L - 32)) / Math.max(1, n - 1);
  const y = (db: number) => T + (H - T - B) * (1 - (db - 4) / 10);
  const ink = dark ? '#a8bec6' : '#41525e';
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Water-to-land contrast in HH and HV for each NISAR pass">
      {[4, 6, 8, 10, 12, 14].map((d) => (
        <g key={d}>
          <line x1={L} x2={W - 8} y1={y(d)} y2={y(d)} stroke={dark ? 'rgba(214,238,242,.09)' : 'rgba(18,34,46,.08)'} />
          <text x={L - 8} y={y(d) + 4} fill={ink} fontSize="11" textAnchor="end">{d}</text>
        </g>
      ))}
      <text x={L - 8} y={T - 2} fill={ink} fontSize="10.5" textAnchor="end">dB</text>
      {v.pol.map((p, i) => (
        <g key={p.date}>
          <line x1={x(i)} x2={x(i)} y1={y(p.HV.contrast_db)} y2={y(p.HH.contrast_db)} stroke={dark ? 'rgba(214,238,242,.25)' : 'rgba(18,34,46,.2)'} strokeWidth="2" />
          <circle cx={x(i)} cy={y(p.HH.contrast_db)} r="6" fill="#3cc8f0"><title>{`HH ${p.HH.contrast_db} dB, ${dShort(ymd(p.date))}`}</title></circle>
          <circle cx={x(i)} cy={y(p.HV.contrast_db)} r="6" fill="#c56fa4"><title>{`HV ${p.HV.contrast_db} dB, ${dShort(ymd(p.date))}`}</title></circle>
          {i % 2 === 0 && <text x={x(i)} y={H - 10} fill={ink} fontSize="10.5" textAnchor="middle">{dShort(ymd(p.date))}</text>}
        </g>
      ))}
    </svg>
  );
}

/** A tiny line of distances to new water per pass, for the point report. */
export function DistanceSpark({ rows, limit = 1000 }: { rows: { date: string; d: number | null }[]; limit?: number }) {
  const W = 300, H = 90, L = 4, B = 16;
  const vals = rows.map((r) => r.d).filter((d): d is number => d != null);
  const max = Math.max(limit * 2, ...vals, 1);
  const x = (i: number) => L + (i * (W - 2 * L)) / Math.max(1, rows.length - 1);
  const y = (d: number) => 6 + (H - B - 6) * (d / max);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Distance to new water at each pass">
      <rect x="0" y={6} width={W} height={y(limit) - 6} fill="rgba(255,90,78,.12)" />
      <text x={W - 4} y={y(limit) - 4} fontSize="9.5" fill="#ff5a4e" textAnchor="end">within {limit / 1000} km</text>
      {rows.map((r, i) => r.d == null
        ? <text key={r.date} x={x(i)} y={H - B - 4} fontSize="9" textAnchor="middle" fill="#7d97a1">–</text>
        : <circle key={r.date} cx={x(i)} cy={y(r.d)} r="3.6" fill={r.d <= limit ? '#ff5a4e' : '#3cc8f0'}><title>{`${dShort(ymd(r.date))}: ${r.d} m`}</title></circle>)}
      {rows.map((r, i) => i % 3 === 0 && <text key={`t${r.date}`} x={x(i)} y={H - 3} fontSize="9" textAnchor="middle" fill="#7d97a1">{dShort(ymd(r.date))}</text>)}
    </svg>
  );
}

export const passLabel = (p: Processed) => `${pDay(p.acquired_utc)} · ${p.track}`;
