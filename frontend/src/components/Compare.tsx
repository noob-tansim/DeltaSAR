/**
 * Swipe comparison: two synced maps, the right one clipped by a handle. Keyboard: arrow keys move the handle.
 * A tap on either label jumps fully to that side, for people who cannot drag.
 */
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import type { Map as MLMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { createMap, fitReach, whenReady, type BaseKind } from './map';

export function Compare({ left, right, leftLabel, rightLabel, base = 'dark', style, label, start = 50, deps = [] }: {
  left: (m: MLMap) => void; right: (m: MLMap) => void; leftLabel: string; rightLabel: string; base?: BaseKind;
  style?: CSSProperties; label: string; start?: number; deps?: unknown[];
}) {
  const box = useRef<HTMLDivElement>(null);
  const aEl = useRef<HTMLDivElement>(null);
  const bEl = useRef<HTMLDivElement>(null);
  const maps = useRef<{ a?: MLMap; b?: MLMap }>({});
  const [pos, setPos] = useState(start);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!aEl.current || !bEl.current) return;
    const a = createMap(aEl.current, { base });
    const b = createMap(bEl.current, { base, attribution: false });
    fitReach(a, 20);
    fitReach(b, 20);
    let syncing = false;
    const sync = (from: MLMap, to: MLMap) => () => {
      if (syncing) return;
      syncing = true;
      to.jumpTo({ center: from.getCenter(), zoom: from.getZoom(), bearing: from.getBearing(), pitch: from.getPitch() });
      syncing = false;
    };
    a.on('move', sync(a, b));
    b.on('move', sync(b, a));
    maps.current = { a, b };
    let n = 0;
    const done = () => {
      n += 1;
      if (n === 2) setReady(true);
    };
    whenReady(a, done);
    whenReady(b, done);
    const ro = new ResizeObserver(() => {
      a.resize();
      b.resize();
    });
    ro.observe(aEl.current);
    return () => {
      ro.disconnect();
      a.remove();
      b.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!ready || !maps.current.a || !maps.current.b) return;
    left(maps.current.a);
    right(maps.current.b);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, ...deps]);

  const drag = useCallback((clientX: number) => {
    const r = box.current?.getBoundingClientRect();
    if (!r) return;
    setPos(Math.max(0, Math.min(100, ((clientX - r.left) / r.width) * 100)));
  }, []);

  const onDown = (e: React.PointerEvent) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    drag(e.clientX);
  };

  return (
    <div ref={box} style={{ position: 'relative', overflow: 'hidden', ...style }} role="group" aria-label={label}>
      <div ref={aEl} style={{ position: 'absolute', inset: 0 }} />
      <div ref={bEl} style={{ position: 'absolute', inset: 0, clipPath: `inset(0 0 0 ${pos}%)` }} />
      <div
        role="slider" tabIndex={0} aria-label="Move the divider" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(pos)}
        onPointerDown={onDown} onPointerMove={(e) => e.buttons === 1 && drag(e.clientX)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setPos((p) => Math.max(0, p - 5));
          if (e.key === 'ArrowRight') setPos((p) => Math.min(100, p + 5));
        }}
        style={{ position: 'absolute', top: 0, bottom: 0, left: `${pos}%`, width: 44, marginLeft: -22, cursor: 'ew-resize', touchAction: 'none', zIndex: 3, display: 'grid', placeItems: 'center' }}
      >
        <div style={{ position: 'absolute', top: 0, bottom: 0, width: 2, background: '#fff', boxShadow: '0 0 0 1px rgba(0,0,0,.25)' }} />
        <div style={{ width: 40, height: 40, borderRadius: 20, background: '#fff', boxShadow: '0 2px 10px rgba(0,0,0,.35)', display: 'grid', placeItems: 'center', color: 'var(--ink)', zIndex: 1 }}>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true"><path d="M9 6l-6 6 6 6M15 6l6 6-6 6" /></svg>
        </div>
      </div>
      <button type="button" onClick={() => setPos(100)} className="cmp-label" style={{ left: 12 }}>{leftLabel}</button>
      <button type="button" onClick={() => setPos(0)} className="cmp-label" style={{ right: 12 }}>{rightLabel}</button>
      <style>{`.cmp-label{position:absolute;top:12px;z-index:4;background:rgba(10,24,33,.82);color:#e6f1f3;border:1px solid rgba(214,238,242,.18);border-radius:6px;padding:6px 12px;font-size:.82rem;font-weight:600;max-width:44%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}`}</style>
    </div>
  );
}
