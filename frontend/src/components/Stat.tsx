/** One headline number: icon, value, unit, what it means, and where it comes from (in words, linked to Methods). */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { Icon, type IconName } from './Icon';

export type Tone = 'water' | 'loss' | 'people' | 'crop' | 'neutral';

export function Stat({ icon, tone = 'neutral', value, unit, label, source, to = '/methods' }: {
  icon: IconName; tone?: Tone; value: ReactNode; unit?: string; label: ReactNode; source?: string; to?: string;
}) {
  return (
    <div className={`st st-${tone}`}>
      <div className="st-top">
        <span className="st-ic"><Icon name={icon} size={18} /></span>
        <div className="st-v num">{value}{unit && <small>{unit}</small>}</div>
      </div>
      <div className="st-k">{label}</div>
      {source && (
        <Link to={to} className="st-src" title="How this number is made">
          <Icon name="info" size={12} /> {source}
        </Link>
      )}
    </div>
  );
}
