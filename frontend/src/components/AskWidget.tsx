/**
 * Ask DeltaSAR: a small assistant on the public pages (never in the resident app or the console).
 * Common questions are answered from a fixed, bilingual FAQ (no AI). Free questions go to the server, which asks
 * Google Gemini to answer only from the project's published facts and checks that every number can be traced.
 */
import { useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router-dom';
import { api } from '../lib/api';
import { useL } from '../lib/i18n';
import { speak, stopSpeaking } from '../lib/speak';
import { Icon } from './Icon';

type Msg = { role: 'user' | 'assistant'; text: string; kind?: 'faq' | 'ai' | 'note'; warn?: string[] };

const FAQ: { q: [string, string]; a: [string, string] }[] = [
  { q: ['What is NISAR?', 'NISAR কী?'], a: [
    'NISAR is the NASA–ISRO radar satellite. Its L-band radar (about 24 cm waves) sees through cloud and rain, day and night, so it sees the Jamuna even in the monsoon. We use its L2 GCOV product from NASA\'s ASF archive: 12 passes from 18 Jun to 16 Oct 2026 on tracks 069A and 019D.',
    'NISAR হলো নাসা ও ইসরোর রাডার উপগ্রহ। এর এল-ব্যান্ড রাডার (প্রায় ২৪ সেমি তরঙ্গ) মেঘ ও বৃষ্টি ভেদ করে দিনে-রাতে দেখতে পারে, তাই বর্ষাতেও যমুনা দেখা যায়। আমরা নাসার ASF সংরক্ষণাগার থেকে এর L2 GCOV তথ্য ব্যবহার করি: ১৮ জুন থেকে ১৬ অক্টোবর ২০২৬, ০৬৯এ ও ০১৯ডি ট্র্যাকের ১২টি ছবি।'] },
  { q: ['How much riverbank was lost?', 'কতটা নদীভাঙন হয়েছে?'], a: [
    'Between 18 Jun and 4 Oct 2026, 187 to 232 hectares of mainland riverbank became river, in 38 places, confirmed by the 16 Oct pass (NISAR track 069A). The largest site, in Char Girish union (Kazipur), is 38.8 ha. 712 buildings stand within 100 m of a bank that retreated.',
    '১৮ জুন থেকে ৪ অক্টোবর ২০২৬-এর মধ্যে মূল ভূখণ্ডের ১৮৭ থেকে ২৩২ হেক্টর পাড় নদী হয়ে গেছে, ৩৮টি জায়গায়; ১৬ অক্টোবরের ছবিতে তা নিশ্চিত (NISAR ট্র্যাক ০৬৯এ)। সবচেয়ে বড় জায়গা কাজীপুরের চরগিরিশ ইউনিয়নে, ৩৮.৮ হেক্টর। সরে যাওয়া পাড়ের ১০০ মিটারের মধ্যে ৭১২টি ঘরবাড়ি আছে।'] },
  { q: ['Is this an official flood warning?', 'এটি কি সরকারি সতর্কবার্তা?'], a: [
    'No. DeltaSAR reports what the radar observed; it does not forecast floods. Official forecasts come from FFWC and BMD. Call 1090 (free) for the government\'s voice forecast. In an emergency call 999.',
    'না। ডেল্টাসার শুধু জানায় রাডারে কী দেখা গেছে; বন্যার পূর্বাভাস দেয় না। সরকারি পূর্বাভাস দেয় FFWC ও BMD। সরকারি পূর্বাভাস শুনতে বিনা খরচে ১০৯০ নম্বরে ফোন করুন। জরুরি প্রয়োজনে ৯৯৯।'] },
  { q: ['How does an alert reach a family?', 'সতর্কবার্তা কীভাবে পরিবারের কাছে পৌঁছায়?'], a: [
    'A fixed rule checks every home against new data (for example, new water within 1 km). It can only draft. A union volunteer reads the evidence and approves. The phone then vibrates and reads the alert aloud in Bangla, and the family presses and holds "I am safe" or "I need help". "Help" opens a call-back task. Every step is counted in a ledger.',
    'একটি নির্দিষ্ট নিয়ম নতুন তথ্যের সাথে প্রতিটি বাড়ি মিলিয়ে দেখে (যেমন বাড়ির ১ কিমির মধ্যে নতুন পানি)। নিয়ম শুধু খসড়া বানায়। ইউনিয়নের একজন স্বেচ্ছাসেবক প্রমাণ দেখে অনুমোদন দেন। তখন ফোন কাঁপে, বাংলায় পড়ে শোনায়, আর পরিবার “আমি নিরাপদ” বা “সাহায্য দরকার” চেপে ধরে উত্তর দেয়। “সাহায্য” চাইলে স্বেচ্ছাসেবক ফোন করেন। প্রতিটি ধাপ খাতায় গোনা হয়।'] },
  { q: ['Which radar polarisation works best?', 'কোন পোলারাইজেশন সবচেয়ে ভালো?'], a: [
    'HH. Over the passes we measured, water and land differ by 9.0 to 11.6 dB in HH but only 6.8 to 8.2 dB in HV, where water is near the sensor\'s noise floor. So the water rule uses HH; HV only flags flooded crops, experimentally.',
    'HH। মাপা ছবিগুলোতে পানি আর মাটির পার্থক্য HH-এ ৯.০ থেকে ১১.৬ ডিবি, কিন্তু HV-তে মাত্র ৬.৮ থেকে ৮.২ ডিবি, যেখানে পানির মান যন্ত্রের নয়েজের কাছাকাছি। তাই পানির নিয়মে HH ব্যবহার হয়; HV শুধু ডোবা ফসল চিহ্নিত করতে, পরীক্ষামূলকভাবে।'] },
  { q: ['Do you need my location?', 'আমার অবস্থান কি লাগবে?'], a: [
    'No. You choose your union when you join, and the union\'s centre is used as your home. You may tap "use where I am now" once to set home more precisely; it is optional. The app never tracks you: alerts and the home screen use the home point you saved, checked against each new radar picture on the server.',
    'না। যোগ দেওয়ার সময় আপনি নিজের ইউনিয়ন বেছে নেন, আর ইউনিয়নের মাঝখানকে বাড়ি ধরা হয়। চাইলে একবার “আমার এখনকার জায়গা নিন” চেপে বাড়ির জায়গা ঠিক করতে পারেন; এটি ঐচ্ছিক। অ্যাপ কখনো আপনাকে অনুসরণ করে না: সতর্কবার্তা ও হোম পাতা আপনার সংরক্ষিত বাড়ির জায়গা দিয়ে সার্ভারে প্রতিটি নতুন রাডার ছবির সাথে মিলিয়ে দেখা হয়।'] },
];

export function AskWidget() {
  const loc = useLocation();
  const { L, lang } = useL();
  const [open, setOpen] = useState(false);
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [q, setQ] = useState('');
  const [busy, setBusy] = useState(false);
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const end = useRef<HTMLDivElement>(null);
  const hidden = /^\/(app|console|join)/.test(loc.pathname);

  useEffect(() => {
    if (open && enabled === null) api<{ enabled: boolean }>('/api/v1/ask/status', { timeoutMs: 60000 }).then((s) => setEnabled(s.enabled)).catch(() => setEnabled(false));
  }, [open, enabled]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [msgs, busy]);
  useEffect(() => () => stopSpeaking(), []);
  if (hidden) return null;

  const faq = (i: number) => {
    const f = FAQ[i]!;
    setMsgs((m) => [...m, { role: 'user', text: L(f.q[0], f.q[1]) }, { role: 'assistant', text: L(f.a[0], f.a[1]), kind: 'faq' }]);
  };
  const send = async () => {
    const text = q.trim();
    if (text.length < 2 || busy) return;
    setQ('');
    const history = msgs.filter((m) => m.kind !== 'note').slice(-6).map((m) => ({ role: m.role, text: m.text }));
    setMsgs((m) => [...m, { role: 'user', text }]);
    if (enabled === false) {
      setMsgs((m) => [...m, { role: 'assistant', kind: 'note', text: L('The AI assistant is switched off on this server. Try one of the questions above, or see Methods.', 'এই সার্ভারে এআই সহকারী বন্ধ আছে। ওপরের প্রশ্নগুলো চেষ্টা করুন, বা “পদ্ধতি” পাতা দেখুন।') }]);
      return;
    }
    setBusy(true);
    try {
      const r = await api<{ enabled: boolean; answer: string | null; untraced_numbers?: string[]; note?: string }>('/api/v1/ask', { method: 'POST', json: { question: text, lang, history }, timeoutMs: 60000 });
      if (!r.enabled || !r.answer) {
        setEnabled(false);
        setMsgs((m) => [...m, { role: 'assistant', kind: 'note', text: L('The AI assistant is switched off on this server. Try one of the questions above.', 'এই সার্ভারে এআই সহকারী বন্ধ আছে। ওপরের প্রশ্নগুলো চেষ্টা করুন।') }]);
      } else {
        setMsgs((m) => [...m, { role: 'assistant', kind: 'ai', text: r.answer!, warn: r.untraced_numbers?.length ? r.untraced_numbers : undefined }]);
      }
    } catch (e) {
      setMsgs((m) => [...m, { role: 'assistant', kind: 'note', text: String((e as Error).message) }]);
    } finally { setBusy(false); }
  };

  return (
    <>
      {!open && (
        <button className={`askw-fab ${loc.pathname.startsWith('/demo') ? 'left' : ''}`} onClick={() => setOpen(true)} aria-label={L('Ask DeltaSAR a question', 'ডেল্টাসারকে প্রশ্ন করুন')}>
          <Icon name="sparkle" size={20} /> <span>{L('Ask DeltaSAR', 'প্রশ্ন করুন')}</span>
        </button>
      )}
      {open && (
        <div className="askw" role="dialog" aria-label={L('Ask DeltaSAR', 'ডেল্টাসারকে প্রশ্ন')}>
          <header>
            <div>
              <b>{L('Ask DeltaSAR', 'ডেল্টাসারকে প্রশ্ন করুন')}</b>
              <div className="tiny">{L('Answers only from our published data · English or বাংলা', 'শুধু আমাদের প্রকাশিত তথ্য থেকে উত্তর · বাংলা বা English')}</div>
            </div>
            <button className="x" onClick={() => { stopSpeaking(); setOpen(false); }} aria-label={L('Close', 'বন্ধ করুন')}><Icon name="x" size={18} /></button>
          </header>
          <div className="body">
            {msgs.length === 0 && <p className="small muted" style={{ margin: '0 0 8px' }}>{L('Pick a question, or type your own.', 'একটি প্রশ্ন বেছে নিন, অথবা নিজে লিখুন।')}</p>}
            <div className="faq">
              {FAQ.map((f, i) => <button key={f.q[0]} onClick={() => faq(i)}>{L(f.q[0], f.q[1])}</button>)}
            </div>
            {msgs.map((m, i) => (
              <div key={i} className={`m ${m.role} ${m.kind ?? ''}`}>
                <p>{m.text}</p>
                {m.role === 'assistant' && m.kind !== 'note' && (
                  <div className="meta">
                    <span className={`tag ${m.kind}`}>{m.kind === 'faq' ? L('From our FAQ', 'আমাদের প্রশ্নোত্তর থেকে') : L('AI (Gemini), from our facts', 'এআই (Gemini), আমাদের তথ্য থেকে')}</span>
                    <button onClick={() => void speak({ bn: m.text, en: m.text, lang: /[ঀ-৿]/.test(m.text) ? 'bn' : 'en' })}><Icon name="speaker" size={14} /> {L('Listen', 'শুনুন')}</button>
                  </div>
                )}
                {m.warn && <p className="warn"><Icon name="info" size={13} /> {L(`Could not trace: ${m.warn.join(', ')}. Check Methods before quoting.`, `এই সংখ্যাগুলোর উৎস মেলেনি: ${m.warn.join(', ')}। ব্যবহারের আগে “পদ্ধতি” পাতা দেখুন।`)}</p>}
              </div>
            ))}
            {busy && <div className="m assistant"><p className="muted">{L('Thinking…', 'ভাবছে…')}</p></div>}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); void send(); }}>
            <input value={q} onChange={(e) => setQ(e.target.value.slice(0, 500))} placeholder={L('Ask about the river, the radar or the app…', 'নদী, রাডার বা অ্যাপ নিয়ে জিজ্ঞেস করুন…')} aria-label={L('Your question', 'আপনার প্রশ্ন')} />
            <button type="submit" disabled={busy || q.trim().length < 2} aria-label={L('Send', 'পাঠান')}><Icon name="send" size={18} /></button>
          </form>
          <p className="foot">{L('Not a warning. Emergency 999 · official forecast 1090. Do not type personal details.', 'এটি সতর্কবার্তা নয়। জরুরি ৯৯৯ · সরকারি পূর্বাভাস ১০৯০। ব্যক্তিগত তথ্য লিখবেন না।')}</p>
        </div>
      )}
      <style>{`
        .askw-fab{position:fixed;right:18px;bottom:18px;z-index:70;display:inline-flex;align-items:center;gap:8px;padding:0 18px;height:52px;border-radius:999px;border:0;background:linear-gradient(135deg,var(--river),#0e8aa0);color:#fff;font-weight:700;box-shadow:0 10px 30px rgba(11,110,127,.4)}
        .askw-fab:hover{filter:brightness(1.08)}
        .askw-fab.left{right:auto;left:50%;transform:translateX(-50%)}
        .askw{position:fixed;right:18px;bottom:18px;z-index:75;width:min(420px,calc(100vw - 24px));height:min(640px,calc(100vh - 100px));display:flex;flex-direction:column;background:var(--paper);border:1px solid var(--line);border-radius:22px;box-shadow:0 24px 70px rgba(10,24,33,.35);overflow:hidden;color:var(--ink)}
        .askw header{display:flex;justify-content:space-between;gap:10px;align-items:center;padding:14px 16px;background:linear-gradient(135deg,var(--night),var(--night-3));color:#fff}
        .askw header .tiny{color:var(--sky-2)}
        .askw .x{background:rgba(255,255,255,.08);border:0;color:#fff;width:36px;height:36px;border-radius:10px;display:grid;place-items:center}
        .askw .body{flex:1;overflow:auto;padding:14px 14px 6px}
        .askw .faq{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:12px}
        .askw .faq button{border:1px solid var(--line);background:var(--mist);border-radius:999px;padding:6px 11px;font-size:.82rem;font-weight:600;color:var(--river)}
        .askw .faq button:hover{border-color:var(--river)}
        .askw .m{margin:8px 0;display:flex;flex-direction:column}
        .askw .m p{margin:0;padding:10px 12px;border-radius:14px;font-size:.92rem;line-height:1.5;white-space:pre-wrap}
        .askw .m.user{align-items:flex-end}
        .askw .m.user p{background:var(--river);color:#fff;border-bottom-right-radius:4px;max-width:85%}
        .askw .m.assistant p{background:var(--mist);border-bottom-left-radius:4px}
        .askw .m.note p{background:var(--watch-lt);color:var(--watch-ink)}
        .askw .meta{display:flex;gap:8px;align-items:center;margin-top:5px}
        .askw .meta .tag{font-size:.7rem;font-weight:700;padding:2px 8px;border-radius:999px;background:var(--river-lt);color:var(--river)}
        .askw .meta .tag.ai{background:#efe9f7;color:#5b3a8c}
        .askw .meta button{border:0;background:none;color:var(--ink-2);font-size:.78rem;display:inline-flex;gap:4px;align-items:center}
        .askw .m p.warn{background:var(--danger-lt);color:#8e1616;font-size:.78rem;margin-top:4px;padding:6px 10px}
        .askw form{display:flex;gap:8px;padding:10px 12px;border-top:1px solid var(--line)}
        .askw form input{flex:1;min-height:46px;border-radius:14px;border:1.5px solid var(--line);padding:0 12px}
        .askw form input:focus{border-color:var(--river);outline:none}
        .askw form button{width:46px;height:46px;border-radius:14px;border:0;background:var(--river);color:#fff;display:grid;place-items:center}
        .askw form button[disabled]{opacity:.45}
        .askw .foot{margin:0;padding:0 14px 10px;font-size:.72rem;color:var(--ink-3)}
        @media (max-width:560px){
          .askw-fab{right:12px;bottom:12px;height:48px;padding:0 14px}
          .askw-fab span{display:none}
          .askw{right:0;left:0;bottom:0;width:100%;height:82vh;height:82dvh;border-radius:22px 22px 0 0}
        }
      `}</style>
    </>
  );
}
