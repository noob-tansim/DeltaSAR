/** One headline number: value, unit, what it means, and where it comes from (in words, linked to Methods). */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

export function Stat({ value, unit, label, source, to = '/methods' }: {
  value: ReactNode; unit?: string; label: ReactNode; source?: string; to?: string;
}) {
  return (
    <div className="st">
      <div className="st-v num">{value}{unit && <small>{unit}</small>}</div>
      <div className="st-k">{label}</div>
      {source && (
        <Link to={to} className="st-src" title="How this number is made">
          {source}
        </Link>
      )}
    </div>
  );
}
