/** Inline SVG icons (24 px grid, stroke 2). Decorative unless a `title` is given. */
import type { CSSProperties } from 'react';

const P: Record<string, string> = {
  wave: 'M2 12c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2M2 17c2.5 0 2.5-2 5-2s2.5 2 5 2 2.5-2 5-2 2.5 2 5 2',
  drop: 'M12 3c-4 5-6.5 8.4-6.5 11.5a6.5 6.5 0 0 0 13 0C18.5 11.4 16 8 12 3z',
  sat: 'M13 7 9 3 5 7l4 4m8 2 4 4-4 4-4-4m-4-6 6 6m2-10 4-4m-8 8a3 3 0 0 0 4 4M3 21l3.5-3.5',
  radar: 'M12 12 19 5M12 3a9 9 0 1 0 9 9M12 7a5 5 0 1 0 5 5',
  play: 'M7 4v16l13-8z',
  pause: 'M7 4h4v16H7zM14 4h4v16h-4z',
  check: 'M4 12.5 9.5 18 20 6',
  x: 'M6 6l12 12M18 6 6 18',
  tri: 'M12 3 2 20h20L12 3zM12 10v4M12 17h.01',
  oct: 'M8 3h8l5 5v8l-5 5H8l-5-5V8zM12 8v5M12 16h.01',
  circle: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z',
  speaker: 'M4 9v6h4l5 4V5L8 9H4zM16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12',
  stop: 'M6 6h12v12H6z',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zM5.6 5.6l4 4M14.4 14.4l4 4M18.4 5.6l-4 4M9.6 14.4l-4 4',
  phone: 'M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2z',
  map: 'M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14',
  rain: 'M7 15a4 4 0 0 1-.5-8A5.5 5.5 0 0 1 17 7.5 3.5 3.5 0 0 1 17 15M8 18l-1 2M12 18l-1 2M16 18l-1 2',
  bell: 'M6 16V11a6 6 0 0 1 12 0v5l2 2H4l2-2zM10 21h4',
  arrow: 'M5 12h14M13 6l6 6-6 6',
  back: 'M19 12H5M11 6l-6 6 6 6',
  ext: 'M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5',
  layers: 'm12 3 9 5-9 5-9-5 9-5zM3 13l9 5 9-5M3 17.5l9 5 9-5',
  info: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 11v6M12 7.5h.01',
  clock: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 2',
  home: 'M3 11 12 4l9 7M5 10v10h5v-6h4v6h5V10',
  user: 'M12 12a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM4 21a8 8 0 0 1 16 0',
  users: 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21a7 7 0 0 1 14 0M16 3.5a4 4 0 0 1 0 7.5M18 14a6 6 0 0 1 4 7',
  shield: 'M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3zM8.5 12l2.5 2.5 4.5-5',
  qr: 'M4 4h6v6H4zM14 4h6v6h-6zM4 14h6v6H4zM14 14h2v2h-2zM18 14h2v2h-2zM14 18h2v2h-2zM18 18h2v2h-2zM16 16h2v2h-2z',
  chev: 'M9 6l6 6-6 6',
  down: 'M6 9l6 6 6-6',
  receipt: 'M6 3h12v18l-3-2-3 2-3-2-3 2V3zM9 8h6M9 12h6M9 16h3',
  send: 'M4 12 20 4l-6 16-3-7-7-1z',
  swap: 'M7 4v16M7 20l-3-3M7 20l3-3M17 20V4M17 4l-3 3M17 4l3 3',
  globe: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18',
  bolt: 'M13 2 4 14h7l-1 8 9-12h-7l1-8z',
  github: 'M9 19c-4.3 1.4-4.3-2.5-6-3m12 5v-3.5c0-1 .1-1.4-.5-2 2.8-.3 5.5-1.4 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.2 4.2 0 0 0-.1-3.2s-1.1-.3-3.5 1.3a12.3 12.3 0 0 0-6.2 0C6.5 2.8 5.4 3.1 5.4 3.1a4.2 4.2 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.5c0 4.6 2.7 5.7 5.5 6-.6.6-.6 1.2-.5 2V21',
  sparkle: 'M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18',
  crosshair: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 2v4M12 18v4M2 12h4M18 12h4',
  menu: 'M4 7h16M4 12h16M4 17h16',
  keypad: 'M6 4h2v2H6zM11 4h2v2h-2zM16 4h2v2h-2zM6 9h2v2H6zM11 9h2v2h-2zM16 9h2v2h-2zM6 14h2v2H6zM11 14h2v2h-2zM16 14h2v2h-2zM11 19h2v2h-2z',
};

export type IconName = keyof typeof P;

export function Icon({ name, size = 20, title, style, className, stroke = 2 }: { name: IconName; size?: number; title?: string; style?: CSSProperties; className?: string; stroke?: number }) {
  const filled = name === 'play' || name === 'pause' || name === 'stop';
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={filled ? 'currentColor' : 'none'} stroke={filled ? 'none' : 'currentColor'}
      strokeWidth={stroke} strokeLinecap="round" strokeLinejoin="round" aria-hidden={title ? undefined : true} role={title ? 'img' : undefined}
      style={{ flex: 'none', ...style }} className={className}>
      {title && <title>{title}</title>}
      <path d={P[name]} />
    </svg>
  );
}

/** Logo: a drop over two waves. */
export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden="true" style={{ flex: 'none' }}>
      <rect width="64" height="64" rx="16" fill="#0B6E7F" />
      <path d="M14 38c6 0 6-4 12-4s6 4 12 4 6-4 12-4" fill="none" stroke="#fff" strokeWidth="4.5" strokeLinecap="round" />
      <path d="M14 47c6 0 6-4 12-4s6 4 12 4 6-4 12-4" fill="none" stroke="#3CC8F0" strokeWidth="4.5" strokeLinecap="round" />
      <path d="M32 11c-6 8-10 13-10 18a10 10 0 0 0 20 0c0-5-4-10-10-18z" fill="#fff" />
    </svg>
  );
}
