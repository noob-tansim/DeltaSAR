/**
 * Speaking. Order: a recorded clip (public/audio/<key>.mp3, recorded by a native speaker) → the device's Bangla
 * voice → the English text with an English voice (so a laptop without Bangla still speaks) → nothing, and say so.
 */
export type SpeakResult = 'clip' | 'bn' | 'en-fallback' | 'en' | 'none';

let current: HTMLAudioElement | null = null;

function voices(): SpeechSynthesisVoice[] {
  return 'speechSynthesis' in window ? window.speechSynthesis.getVoices() : [];
}
if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
  window.speechSynthesis.getVoices();
  window.speechSynthesis.addEventListener?.('voiceschanged', () => window.speechSynthesis.getVoices());
}

export function hasBanglaVoice(): boolean | null {
  const v = voices();
  if (!v.length) return null;
  return v.some((x) => x.lang.toLowerCase().startsWith('bn'));
}

export function stopSpeaking(): void {
  if ('speechSynthesis' in window) window.speechSynthesis.cancel();
  if (current) {
    current.pause();
    current = null;
  }
}

function say(text: string, lang: 'bn' | 'en', onEnd?: () => void): boolean {
  if (!text || !('speechSynthesis' in window)) return false;
  const synth = window.speechSynthesis;
  const vs = voices();
  const u = new SpeechSynthesisUtterance(text);
  if (lang === 'bn') {
    const v = vs.find((x) => x.lang.toLowerCase() === 'bn-bd') ?? vs.find((x) => x.lang.toLowerCase().startsWith('bn'));
    if (!v && vs.length) return false;
    if (v) u.voice = v;
    u.lang = 'bn-BD';
    u.rate = 0.88;
  } else {
    const v = vs.find((x) => /en-(gb|in)/i.test(x.lang)) ?? vs.find((x) => x.lang.toLowerCase().startsWith('en'));
    if (v) u.voice = v;
    u.lang = v?.lang ?? 'en-GB';
    u.rate = 0.95;
  }
  u.onend = () => onEnd?.();
  u.onerror = () => onEnd?.();
  synth.cancel();
  synth.speak(u);
  return true;
}

/** Speak `bn` (or `en` when the person chose English). Returns how it was spoken. */
export async function speak(opts: { bn: string; en: string; lang: 'bn' | 'en'; clip?: string; onEnd?: () => void }): Promise<SpeakResult> {
  stopSpeaking();
  if (opts.clip) {
    try {
      const a = new Audio(`/audio/${opts.clip}.mp3`);
      current = a;
      a.onended = () => opts.onEnd?.();
      await a.play();
      return 'clip';
    } catch {
      current = null;
    }
  }
  if (opts.lang === 'en') return say(opts.en, 'en', opts.onEnd) ? 'en' : 'none';
  if (say(opts.bn, 'bn', opts.onEnd)) return 'bn';
  return say(opts.en, 'en', opts.onEnd) ? 'en-fallback' : 'none';
}

export function vibrate(pattern: number[] = [300, 150, 300, 150, 600]): void {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* not supported */
  }
}
