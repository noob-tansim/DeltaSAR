import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';
import type { Map as MLMap } from 'maplibre-gl';
import 'maplibre-gl/dist/maplibre-gl.css';
import { createMap, fitReach, whenReady, type BaseKind } from './map';

/** A MapLibre map. `onReady` runs once the style has loaded; keep the map in a ref to update layers later. */
export function MapView({ base = 'dark', onReady, style, className, interactive = true, label, children, fit = true, padding = 24 }: {
  base?: BaseKind; onReady?: (m: MLMap) => void; style?: CSSProperties; className?: string; interactive?: boolean; label: string;
  children?: ReactNode; fit?: boolean; padding?: number;
}) {
  const el = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!el.current) return;
    let map: MLMap;
    try {
      map = createMap(el.current, { base, interactive });
    } catch {
      setFailed(true);
      return;
    }
    if (fit) fitReach(map, padding);
    whenReady(map, () => onReady?.(map));
    const ro = new ResizeObserver(() => map.resize());
    ro.observe(el.current);
    return () => {
      ro.disconnect();
      map.remove();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return (
    <div className={className} style={{ position: 'relative', overflow: 'hidden', ...style }}>
      <div ref={el} role="region" aria-label={label} style={{ position: 'absolute', inset: 0 }} />
      {failed && (
        <div style={{ position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', padding: 20, textAlign: 'center', color: 'var(--sky-2)' }}>
          This browser cannot draw the map (WebGL is off). The numbers on this page still apply.
        </div>
      )}
      {children}
    </div>
  );
}
