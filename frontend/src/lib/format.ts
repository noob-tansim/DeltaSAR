/** Dates are stored in UTC and shown in Asia/Dhaka. Radar dates in file names are YYYYMMDD (UTC acquisition). */
export const TZ = 'Asia/Dhaka';

export function ymd(s: string): Date {
  return new Date(Date.UTC(+s.slice(0, 4), +s.slice(4, 6) - 1, +s.slice(6, 8)));
}

export function fmtDate(d: Date | string, opts: Intl.DateTimeFormatOptions = { day: 'numeric', month: 'short', year: 'numeric' }, locale = 'en-GB', tz = TZ): string {
  const x = typeof d === 'string' ? (/^\d{8}$/.test(d) ? ymd(d) : new Date(d)) : d;
  return new Intl.DateTimeFormat(locale, { timeZone: tz, ...opts }).format(x);
}
/** A radar pass is named by its UTC acquisition date (as in NASA's file names and in our pitch). */
export const pDay = (iso: string) => fmtDate(iso, { day: 'numeric', month: 'short' }, 'en-GB', 'UTC');
export const pLong = (iso: string) => fmtDate(iso, { day: 'numeric', month: 'long', year: 'numeric' }, 'en-GB', 'UTC');
export const dShort = (d: Date | string) => fmtDate(d, { day: 'numeric', month: 'short' }, 'en-GB', d instanceof Date || /^\d{8}$/.test(String(d)) ? 'UTC' : TZ);
export const dLong = (d: Date | string) => fmtDate(d, { day: 'numeric', month: 'long', year: 'numeric' }, 'en-GB', d instanceof Date || /^\d{8}$/.test(String(d)) ? 'UTC' : TZ);
export const dTime = (d: Date | string) => fmtDate(d, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
export const tOnly = (d: Date | string) => fmtDate(d, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });

export function ago(iso: string | Date, now = new Date()): string {
  const t = typeof iso === 'string' ? new Date(iso) : iso;
  const s = (now.getTime() - t.getTime()) / 1000;
  if (s < 90) return 'just now';
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400 * 1.5) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export const n0 = (v: number | null | undefined) => (v == null ? '–' : Math.round(v).toLocaleString('en-US'));
export const n1 = (v: number | null | undefined) => (v == null ? '–' : (Math.round(v * 10) / 10).toLocaleString('en-US', { maximumFractionDigits: 1 }));
export const range = (r: (number | null)[] | null | undefined, f = n0, unit = '') => (!r || r[0] == null ? '–' : `${f(r[0])}–${f(r[1] ?? null)}${unit}`);

export function clamp(v: number, a: number, b: number) {
  return Math.max(a, Math.min(b, v));
}

const BN_MONTHS = ['জানুয়ারি', 'ফেব্রুয়ারি', 'মার্চ', 'এপ্রিল', 'মে', 'জুন', 'জুলাই', 'আগস্ট', 'সেপ্টেম্বর', 'অক্টোবর', 'নভেম্বর', 'ডিসেম্বর'];
/** Pass day in Bangla ("৯ নভেম্বর"), by UTC date like pDay. */
export const pDayBn = (iso: string) => {
  const d = new Date(iso);
  return `${String(d.getUTCDate()).replace(/\d/g, (x) => '০১২৩৪৫৬৭৮৯'[+x]!)} ${BN_MONTHS[d.getUTCMonth()]}`;
};
