/** Status is always shape + word + colour (+ sound on the phone). Unknown is hatched, never a solid fill. */
import type { ReactElement } from 'react';
import type { Status } from '../lib/api';

const SHAPE: Record<Status, ReactElement> = {
  calm: <circle cx="12" cy="12" r="9" />,
  watch: <path d="M12 2.5 22 20.5H2z" />,
  alert: <path d="M8 2.5h8l5.5 5.5v8L16 21.5H8L2.5 16V8z" />,
  no_data: <rect x="3" y="3" width="18" height="18" rx="3" />,
};
const COLOR: Record<Status, string> = { calm: 'var(--safe)', watch: 'var(--watch)', alert: 'var(--danger)', no_data: 'var(--unknown)' };
const MARK: Record<Status, ReactElement | null> = {
  calm: <path d="M7.5 12.5 10.5 15.5 16.5 9" stroke="#fff" strokeWidth="2.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />,
  watch: <path d="M12 9v5M12 17.2h.01" stroke="var(--watch-ink)" strokeWidth="2.4" strokeLinecap="round" />,
  alert: <path d="M12 7v6M12 16.5h.01" stroke="#fff" strokeWidth="2.6" strokeLinecap="round" />,
  no_data: <path d="M9 9.5a3 3 0 1 1 3.5 3c-.4.1-.5.4-.5.8V15M12 18h.01" stroke="#fff" strokeWidth="2.2" fill="none" strokeLinecap="round" />,
};

export function StatusShape({ status, size = 44 }: { status: Status; size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" style={{ flex: 'none' }}>
      {status === 'no_data' && (
        <defs>
          <pattern id="hatch-sb" width="4" height="4" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="4" height="4" fill="#8a99a3" />
            <rect width="1.6" height="4" fill="#5b6b76" />
          </pattern>
        </defs>
      )}
      <g fill={status === 'no_data' ? 'url(#hatch-sb)' : COLOR[status]}>{SHAPE[status]}</g>
      {MARK[status]}
    </svg>
  );
}

export const STATUS_WORD: Record<Status, [string, string]> = {
  calm: ['এখন কোনো সতর্কবার্তা নেই', 'No alert now'],
  watch: ['সতর্ক থাকুন', 'Stay alert'],
  alert: ['সতর্কবার্তা', 'Alert'],
  no_data: ['নতুন তথ্য নেই', 'No new information'],
};
export const STATUS_BG: Record<Status, string> = { calm: 'var(--safe-lt)', watch: 'var(--watch-lt)', alert: 'var(--danger-lt)', no_data: '#eef1f3' };
export const STATUS_BORDER: Record<Status, string> = { calm: '#9fceA2', watch: 'var(--watch)', alert: 'var(--danger)', no_data: '#b8c3ca' };
export const STATUS_INK: Record<Status, string> = { calm: '#1d5a20', watch: 'var(--watch-ink)', alert: '#8e1616', no_data: 'var(--ink-2)' };
