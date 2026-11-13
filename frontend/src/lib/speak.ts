/**
 * Speaking. Order: a recorded clip (public/audio/<key>.mp3, recorded by a native speaker) → the device's Bangla
 * voice → Bangla audio from our server (Gemini text-to-speech reading the same approved text, cached) → the English
 * text with an English voice → nothing, and say so.
 */
import { API_BASE } from './api';

export type SpeakResult = 'clip' | 'bn' | 'bn-server' | 'en-fallback' | 'en' | 'none';

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

/** The browser loads its voice list late (Windows Chrome especially): wait up to 600 ms for it. */
function voicesReady(): Promise<void> {
  if (!('speechSynthesis' in window) || voices().length) return Promise.resolve();
  return new Promise((res) => {
    const done = () => { window.speechSynthesis.removeEventListener?.('voiceschanged', done); res(); };
    window.speechSynthesis.addEventListener?.('voiceschanged', done);
    setTimeout(done, 600);
  });
}

const serverAudio = new Map<string, string>();
/** Bangla audio for the exact text, from /api/v1/tts (generated once, then cached on the server and here). */
async function serverSpeech(text: string, onEnd?: () => void): Promise<boolean> {
  try {
    let url = serverAudio.get(text);
    if (!url) {
      const r = await fetch(`${API_BASE}/api/v1/tts`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: text.slice(0, 700) }) });
      if (!r.ok) return false;
      url = URL.createObjectURL(await r.blob());
      serverAudio.set(text, url);
    }
    const a = new Audio(url);
    current = a;
    a.onended = () => onEnd?.();
    await a.play();
    return true;
  } catch {
    return false;
  }
}

/** Speak `bn` (or `en` when the person chose English). Returns how it was spoken. */
export async function speak(opts: { bn: string; en: string; lang: 'bn' | 'en'; clip?: string; onEnd?: () => void }): Promise<SpeakResult> {
  stopSpeaking();
  await voicesReady();
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
  if (hasBanglaVoice() === true && say(opts.bn, 'bn', opts.onEnd)) return 'bn';
  if (await serverSpeech(opts.bn, opts.onEnd)) return 'bn-server';
  return say(opts.en, 'en', opts.onEnd) ? 'en-fallback' : 'none';
}

export function vibrate(pattern: number[] = [300, 150, 300, 150, 600]): void {
  try {
    navigator.vibrate?.(pattern);
  } catch {
    /* not supported */
  }
}
