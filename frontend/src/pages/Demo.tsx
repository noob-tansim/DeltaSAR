/**
 * Guided demo: the whole alert loop on the real 24 July 2026 NISAR pass, in a private sandbox for this visitor.
 * Left: what to do next. Middle: the volunteer console. Right: a phone running the real app.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import QRCode from 'qrcode';
import { EventCard, ImpactPanel, LedgerFeed, RULE } from '../console/parts';
import { Nav } from '../components/Chrome';
import { Icon, type IconName } from '../components/Icon';
import { useLiveNasa } from '../components/LiveNasa';
import { phoneApi, sandboxApi, type Snapshot } from '../lib/api';
import { ago, dTime, n0, pDay, pDayBn } from '../lib/format';
import { PhoneApp } from '../phone/PhoneApp';
import { digits, useL } from '../lib/i18n';

const KEY = 'bonna.demo';
type Saved = { sid: string; visitor: string };
const load = (): Saved | null => { try { return JSON.parse(localStorage.getItem(KEY) ?? 'null'); } catch { return null; } };
const save = (v: Saved | null) => { try { if (v) localStorage.setItem(KEY, JSON.stringify(v)); else localStorage.removeItem(KEY); } catch { /* ignore */ } };

export default function Demo() {
  const [saved, setSaved] = useState<Saved | null>(load());
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [label, setLabel] = useState<string | null>(null);
  const [volunteer, setVolunteer] = useState('Demo volunteer');
  const { pass: live } = useLiveNasa();
  const { L, lang } = useL();

  const run = useCallback(async (fn: () => Promise<Snapshot | (Snapshot & { label?: string })>) => {
    setBusy(true); setErr(null);
    try {
      const s = await fn();
      setSnap(s);
      if ('label' in s && s.label) setLabel(s.label);
    } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  }, []);

  const start = async () => {
    setBusy(true); setErr(null); setLabel(null);
    try {
      const r = await sandboxApi.create();
      const v = { sid: r.sandbox_id, visitor: r.visitor_device_id };
      save(v); setSaved(v); setSnap(r.snapshot);
    } catch (e) { setErr(String((e as Error).message)); } finally { setBusy(false); }
  };

  // resume a demo from this browser, or notice it expired
  useEffect(() => {
    if (!saved) return;
    sandboxApi.get(saved.sid).then(setSnap).catch(() => { save(null); setSaved(null); });
  }, [saved?.sid]); // eslint-disable-line react-hooks/exhaustive-deps

  // keep the console fresh (replies from phones, ledger)
  useEffect(() => {
    if (!saved) return;
    const t = window.setInterval(() => { if (!busy) sandboxApi.get(saved.sid).then(setSnap).catch(() => undefined); }, 3000);
    return () => window.clearInterval(t);
  }, [saved, busy]);

  const sid = saved?.sid;
  const radarEv = snap?.events.find((e) => e.rule === 'radar');
  const youRec = radarEv?.recipients.find((r) => r.display_name?.startsWith('Your phone'));

  // once the visitor has answered on the phone, the demo households answer by keypad too (simulated, labelled)
  const simulated = useRef<string | null>(null);
  useEffect(() => {
    if (!sid || !radarEv || !youRec?.reply || simulated.current === radarEv.event_id) return;
    if (radarEv.recipients.some((r) => r.reply && r.recipient_id !== youRec.recipient_id)) { simulated.current = radarEv.event_id; return; }
    simulated.current = radarEv.event_id;
    sandboxApi.simulateReplies(sid).then(setSnap).catch(() => undefined);
  }, [sid, radarEv, youRec?.reply, youRec?.recipient_id]);
  const helpOpen = radarEv?.recipients.filter((r) => r.reply === 'help' && !r.callback_done) ?? [];
  const asOf = snap ? new Date(snap.as_of_utc).getTime() : 0;
  const step = !snap ? 0
    : snap.mode === 'live' ? 8
      : snap.in_radar_gap && asOf >= Date.UTC(2026, 7, 7) ? 7
        : !radarEv && snap.radar?.date !== '20260724' ? 1
          : !radarEv ? 2
            : radarEv.state === 'drafted' || radarEv.state === 'late' ? 3
              : !youRec?.reply ? 4
                : helpOpen.length ? 5 : 6;

  const n = (v: string | number) => digits(v, lang);
  const steps: { icon: IconName; title: string; body: React.ReactNode; action?: string; act?: () => void }[] = [
    { icon: 'play', title: L('Start a private demo', 'নিজের ডেমো শুরু করুন'),
      body: L('You get your own copy of the alert system: a replay clock and six demo phones at real places on the Jamuna. Nothing you do touches anyone else.', 'আপনি সতর্কবার্তা ব্যবস্থার নিজের একটি কপি পাবেন: একটি রিপ্লে ঘড়ি আর যমুনার আসল জায়গায় ছয়টি ডেমো ফোন। আপনার কাজ অন্য কারও ওপর প্রভাব ফেলবে না।'),
      action: L('Start the demo', 'ডেমো শুরু করুন'), act: () => void start() },
    { icon: 'clock', title: L('It is 26 July 2026, in the monsoon', 'এখন ২৬ জুলাই ২০২৬, বর্ষাকাল'),
      body: L(<>The newest radar picture the system has is from {snap?.radar ? pDay(snap.radar.acquired_utc) : '12 Jul'}. The satellite passed again on 24 July, but NASA has not published that picture yet.</>, <>ব্যবস্থার কাছে সর্বশেষ রাডার ছবি ১২ জুলাইয়ের। ২৪ জুলাই উপগ্রহ আবার গেছে, কিন্তু নাসা সেই ছবি এখনো প্রকাশ করেনি।</>),
      action: L('NASA publishes the 24 July pass', 'নাসা ২৪ জুলাইয়ের ছবি প্রকাশ করল'), act: () => sid && void run(() => sandboxApi.nextEvent(sid)) },
    { icon: 'sat', title: L('New radar data has arrived', 'নতুন রাডার তথ্য এসেছে'),
      body: L(<>{label ?? 'The 24 July pass is now public.'} A fixed rule now checks every home against the new water.</>, <>২৪ জুলাইয়ের ছবি এখন প্রকাশিত (উপগ্রহ যাওয়ার প্রায় ৫৬ ঘণ্টা পর)। এখন একটি নির্দিষ্ট নিয়ম প্রতিটি বাড়ি নতুন পানির সাথে মিলিয়ে দেখবে।</>),
      action: L('Run the rules', 'নিয়ম চালান'), act: () => sid && void run(() => sandboxApi.tick(sid)) },
    { icon: 'bell', title: L('The rule drafted an alert', 'নিয়ম একটি খসড়া বানিয়েছে'),
      body: L(<>The radar rule found new water within 1 km of <b>{radarEv?.recipients.length ?? '…'}</b> of the 6 homes and drafted one alert. The other homes stay silent, with the reason shown. Open the receipt, then decide.</>, <>রাডারের নিয়ম ৬টি বাড়ির মধ্যে <b>{n(radarEv?.recipients.length ?? '…')}</b>টির ১ কিমির মধ্যে নতুন পানি পেয়েছে এবং একটি খসড়া বানিয়েছে। বাকি বাড়িগুলো চুপ, কারণসহ দেখানো। প্রমাণ খুলে দেখুন, তারপর সিদ্ধান্ত নিন।</>),
      action: L('Approve as the volunteer', 'স্বেচ্ছাসেবক হিসেবে অনুমোদন দিন'), act: () => sid && radarEv && void run(() => sandboxApi.approve(sid, radarEv.event_id, volunteer)) },
    { icon: 'speaker', title: L('The phone buzzes and speaks', 'ফোন কাঁপে আর পড়ে শোনায়'),
      body: L(<>The phone on the right shows the alert and reads it aloud in Bangla (or English if this computer has no Bangla voice). Now answer: <b>press and hold “সাহায্য দরকার”</b> (I need help) on the phone.</>, <>ডানের ফোনে সতর্কবার্তা আসে এবং বাংলায় পড়ে শোনায় (এই কম্পিউটারে বাংলা কণ্ঠ না থাকলে ইংরেজিতে)। এখন উত্তর দিন: ফোনে <b>“সাহায্য দরকার” চেপে ধরে রাখুন</b>।</>),
      action: L('Answer “need help” for me', 'আমার হয়ে “সাহায্য দরকার” পাঠান'), act: () => sid && youRec && saved && void run(async () => { await phoneApi.reply(youRec.recipient_id, saved.visitor, 'help', 'in_app'); await sandboxApi.simulateReplies(sid); return sandboxApi.get(sid); }) },
    { icon: 'help', title: L('Help requests are waiting', 'সাহায্যের অনুরোধ অপেক্ষায়'),
      body: L(<>The console shows {helpOpen.length === 1 ? 'it' : `all ${helpOpen.length}`} in red. In a pilot, a union volunteer phones or visits each one. The demo households answered too, by keypad or SMS (simulated, labelled).</>, <>কনসোলে {helpOpen.length === 1 ? 'অনুরোধটি' : `${n(helpOpen.length)}টি অনুরোধ`} লাল রঙে দেখাচ্ছে। পাইলটে ইউনিয়নের স্বেচ্ছাসেবক প্রত্যেককে ফোন করবেন বা দেখা করবেন। ডেমো পরিবারগুলোও কিপ্যাড বা এসএমএসে উত্তর দিয়েছে (অনুকরণ, চিহ্নিত)।</>),
      action: helpOpen.length > 1 ? L(`Mark the ${helpOpen.length} call-backs done`, `${n(helpOpen.length)}টি ফোন করা শেষ`) : L('Mark the call-back done', 'ফোন করা শেষ'), act: () => sid && helpOpen.length && void run(async () => { let s: Snapshot | null = null; for (const r of helpOpen) s = await sandboxApi.callbackDone(sid, r.recipient_id, volunteer); return s!; }) },
    { icon: 'shield', title: L('Every step is in the ledger', 'প্রতিটি ধাপ খাতায় লেখা আছে'),
      body: L(<>Every step wrote one row to the ledger; the impact numbers below come only from those rows. Next: the moments when the system must <b>not</b> alert.</>, <>প্রতিটি ধাপ খাতায় একটি সারি লিখেছে; নিচের প্রভাবের সংখ্যা শুধু সেখান থেকেই। এবার দেখুন কখন ব্যবস্থাটি সতর্কবার্তা <b>দেবে না</b>।</>),
      action: L('Jump to 7 August: radar off, heavy rain', '৭ আগস্টে যান: রাডার বন্ধ, ভারী বৃষ্টি'), act: () => sid && void run(async () => { await sandboxApi.clock(sid, { mode: 'replay', preset: 'gap_rain' }); return sandboxApi.tick(sid); }) },
    { icon: 'tri', title: L('When the system stays silent', 'ব্যবস্থাটি কখন চুপ থাকে'),
      body: L(<>The radar was off from 27 July to 10 August; the phone says so instead of guessing. IMERG measured <b>{snap?.rain?.mm ?? 75.2} mm</b> on the wettest spot on {snap?.rain?.date ?? '5 Aug'}. The level is 76 mm, so the rain rule stayed silent, and shows why.</>, <>২৭ জুলাই থেকে ১০ আগস্ট রাডার বন্ধ ছিল; ফোন অনুমান না করে তা-ই জানায়। ৫ আগস্ট সবচেয়ে বৃষ্টির জায়গায় IMERG মেপেছে <b>{n(snap?.rain?.mm ?? 75.2)} মিমি</b>। সীমা ৭৬ মিমি, তাই বৃষ্টির নিয়ম চুপ ছিল, আর কেন তা দেখায়।</>),
      action: L('Back to today (live)', 'আজকের দিনে ফিরুন (লাইভ)'), act: () => sid && void run(() => sandboxApi.clock(sid, { mode: 'live' })) },
    { icon: 'globe', title: L('Today, live', 'আজ, সরাসরি'),
      body: (() => {
        const r = snap?.mode === 'live' ? snap.radar : null;
        const dm = snap?.people.find((p) => p.is_visitor)?.rules.radar.values?.distance_m ?? null;
        const km = dm != null ? (dm / 1000).toFixed(1) : null;
        const valid = !!r && !r.processing_level.includes('PROVISIONAL');
        const same = !!(r && live && live.track === r.track && live.acquired_utc.slice(0, 10).replace(/-/g, '') === r.date);
        return L(
          <>Back to today. {r ? <>The newest NISAR pass, {pDay(r.acquired_utc)} ({valid ? 'VALIDATED' : 'PROVISIONAL'}), is already processed{km ? <>: the nearest new water is <b>{km} km</b> from this home, beyond the 1 km you chose, so your phone stays calm and sends nothing</> : null}.</> : <>The phone uses the newest processed pass and sends nothing unless a rule fires.</>} {live ? (same ? <>It is also NASA's newest pass over the reach in CMR, checked just now.</> : <>NASA's newest pass over the reach is {dTime(live.acquired_utc)} ({live.maturity}, {ago(live.acquired_utc)}), read live from NASA CMR; the pipeline ingests it next.</>) : null}</>,
          <>আজকের দিনে ফিরে এলাম। {r ? <>সর্বশেষ NISAR ছবি {pDayBn(r.acquired_utc)} ({valid ? 'যাচাইকৃত' : 'প্রাথমিক'}) ইতিমধ্যে হিসাব করা হয়েছে{km ? <>: নতুন পানি এই বাড়ি থেকে <b>{n(km)} কিমি</b> দূরে, আপনার বেছে নেওয়া ১ কিমির বাইরে, তাই ফোন শান্ত থাকে এবং কিছু পাঠায় না</> : null}।</> : <>ফোন সর্বশেষ হিসাব করা ছবি ব্যবহার করে; কোনো নিয়ম না মিললে কিছু পাঠায় না।</>} {live ? (same ? <>এটিই নাসা CMR-এ এই এলাকার সর্বশেষ ছবি, এইমাত্র দেখা।</> : <>নাসার সর্বশেষ ছবি {n(dTime(live.acquired_utc))} ({live.maturity === 'VALIDATED' ? 'যাচাইকৃত' : 'প্রাথমিক'}), সরাসরি নাসা CMR থেকে পড়া; এটিই পরের ধাপে যোগ হবে।</>) : null}</>);
      })() },
  ];

  return (
    <>
      <Nav />
      <div className="demo-top">
        <div className="demo-top-in">
          <div>
            <div className="eyebrow" style={{ marginBottom: 4 }}>{L('Live demo · private sandbox', 'লাইভ ডেমো · নিজস্ব স্যান্ডবক্স')}</div>
            <h1 style={{ fontSize: 'clamp(1.4rem,2.4vw,2rem)', margin: 0 }}>{L('The alert loop, on the real 24 July 2026 radar pass', '২৪ জুলাই ২০২৬-এর আসল রাডার ছবিতে সতর্কবার্তার পুরো ধাপ')}</h1>
          </div>
          {snap && (
            <div className="demo-clock">
              <span className={`chip ${snap.replay ? 'chip-replay' : 'chip-live'}`}>{snap.replay ? L('REPLAY · real data from a past date', 'রিপ্লে · আগের তারিখের আসল তথ্য') : L('LIVE', 'লাইভ')}</span>
              <b className="num">{dTime(snap.as_of_utc)}</b><span className="muted small">Dhaka</span>
              <button className="btn btn-ghost btn-sm" onClick={() => void start()} disabled={busy}>{L('Restart', 'আবার শুরু')}</button>
            </div>
          )}
        </div>
      </div>
      <main id="main" className="demo">
        <section className="demo-guide" aria-label="Steps">
          <ol className="dg-steps">
            {steps.map((s, i) => (
              <li key={s.title} className={i === step ? 'now' : i < step ? 'done' : 'later'}>
                <span className="dg-n">{i < step ? <Icon name="check" size={14} /> : i + 1}</span>
                <div>
                  <b>{s.title}</b>
                  {i === step && (
                    <div className="fade-in">
                      <p className="small" style={{ margin: '6px 0 10px' }}>{s.body}</p>
                      {s.action && <button className="btn btn-primary" onClick={s.act} disabled={busy}>{busy ? L('Working…', 'হচ্ছে…') : s.action} {!busy && <Icon name="arrow" size={16} />}</button>}
                      {i === 3 && (
                        <label className="field" style={{ marginTop: 10, fontWeight: 500 }}>{L('Your name as volunteer', 'স্বেচ্ছাসেবক হিসেবে আপনার নাম')}
                          <input className="input" value={volunteer} onChange={(e) => setVolunteer(e.target.value.slice(0, 60))} />
                        </label>
                      )}
                    </div>
                  )}
                </div>
              </li>
            ))}
          </ol>
          {err && <p className="callout warn small" role="alert">{err}</p>}
          {sid && <QrJoin sid={sid} joined={snap?.people.filter((p) => !p.device_id.startsWith(`${sid}-`)).length ?? 0} />}
          <p className="tiny muted" style={{ marginTop: 12 }}>
            All radar, rain and river values are real archived data; the replay shows only what NASA had published at that moment.
            Six demo phones sit at real union centre points. Voice call and SMS are simulated and labelled. <Link to="/methods">How it works</Link>.
          </p>
        </section>

        <section className="demo-console" aria-label="Volunteer console">
          {!snap ? (
            <div className="card" style={{ textAlign: 'center', padding: '48px 24px' }}>
              <h2 style={{ fontSize: '1.5rem' }}>{L('You are the union volunteer.', 'আপনি ইউনিয়নের স্বেচ্ছাসেবক।')}</h2>
              <p className="muted" style={{ maxWidth: '46ch', margin: '0 auto 18px' }}>{L('Rules draft alerts from NASA data. Nothing reaches a phone until you approve it. Every answer is counted.', 'নাসার তথ্য থেকে নিয়ম সতর্কবার্তার খসড়া বানায়। আপনি অনুমোদন না দিলে কোনো ফোনে কিছু যায় না। প্রতিটি উত্তর গোনা হয়।')}</p>
              <button className="btn btn-primary btn-lg" onClick={() => void start()} disabled={busy}><Icon name="play" size={18} /> {busy ? L('Starting… (the server may be waking up)', 'শুরু হচ্ছে… (সার্ভার চালু হতে পারে)') : L('Start the demo', 'ডেমো শুরু করুন')}</button>
            </div>
          ) : (
            <>
              <InputsBar snap={snap} />
              {snap.events.length === 0 && (
                <div className="card muted small" style={{ textAlign: 'center' }}>No drafts. {step === 1 ? 'Waiting for new data.' : step === 2 ? 'Run the rules to check every home.' : ''}</div>
              )}
              {snap.events.map((e) => (
                <EventCard key={e.event_id} ev={e} busy={busy} highlight={e.event_id === radarEv?.event_id}
                  onApprove={() => sid && void run(() => sandboxApi.approve(sid, e.event_id, volunteer))}
                  onReject={(reason) => sid && void run(() => sandboxApi.reject(sid, e.event_id, volunteer, reason))}
                  onCallback={(rid) => sid && void run(() => sandboxApi.callbackDone(sid, rid, volunteer))} />
              ))}
              <PeopleRules snap={snap} />
              <div className="grid-2" style={{ alignItems: 'start' }}>
                <div className="card"><h3 style={{ fontSize: '1rem' }}>Ledger <span className="muted tiny">append-only, newest first</span></h3><LedgerFeed rows={snap.ledger} /></div>
                <div className="card"><h3 style={{ fontSize: '1rem' }}>Impact <span className="muted tiny">from the ledger</span></h3><ImpactPanel i={snap.impact} /></div>
              </div>
            </>
          )}
        </section>

        <section className="demo-phone" aria-label="Demo phone">
          <PhoneFrame>
            {saved && snap ? <PhoneApp key={saved.sid} deviceId={saved.visitor} embedded pollMs={2000} /> : (
              <div className="ph" style={{ display: 'grid', placeItems: 'center', textAlign: 'center', padding: 24 }}>
                <div><b style={{ fontFamily: 'var(--font-display)', fontSize: '1.5rem', color: 'var(--river)' }}>বন্যা সাথী</b><p className="small muted">This phone joins when the demo starts.</p></div>
              </div>
            )}
          </PhoneFrame>
          {step === 4 && <div className="phone-hint fade-in"><Icon name="arrow" size={16} style={{ transform: 'rotate(90deg)' }} /> Press and hold “সাহায্য দরকার” on the phone</div>}
        </section>
      </main>
      <style>{`
        body{background:var(--mist)}
        .demo-top{background:var(--paper);border-bottom:1px solid var(--line)}
        .demo-top-in{width:min(1480px,100% - 32px);margin:auto;padding:14px 0;display:flex;gap:16px;align-items:center;justify-content:space-between;flex-wrap:wrap}
        .demo-clock{display:flex;gap:10px;align-items:center;flex-wrap:wrap}
        .demo-clock b{font-family:var(--font-display);font-size:1.3rem}
        .demo{width:min(1480px,100% - 32px);margin:18px auto 40px;display:grid;grid-template-columns:320px minmax(0,1fr) 380px;gap:20px;align-items:start}
        .demo-guide{position:sticky;top:calc(var(--nav-h) + 12px)}
        .demo-console{display:grid;gap:14px}
        .demo-phone{position:sticky;top:calc(var(--nav-h) + 12px)}
        .dg-steps{list-style:none;margin:0;padding:0;display:grid;gap:4px}
        .dg-steps li{display:grid;grid-template-columns:30px 1fr;gap:10px;padding:10px 12px;border-radius:var(--r-md)}
        .dg-steps li.now{background:var(--paper);border:1px solid var(--line)}
        .dg-steps li.later{opacity:.55}
        .dg-steps li.done b{color:var(--ink-2)}
        .dg-n{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font:700 .82rem var(--font-body);background:var(--mist-2);color:var(--ink-2)}
        .now .dg-n{background:var(--river);color:#fff}
        .done .dg-n{background:var(--safe);color:#fff}
        .phone-hint{margin-top:10px;text-align:center;font-weight:700;color:var(--kantha);display:flex;gap:6px;align-items:center;justify-content:center}
        @media (max-width:1240px){.demo{grid-template-columns:300px minmax(0,1fr)}.demo-phone{grid-column:1;grid-row:2;position:static}.demo-guide{position:static}}
        @media (max-width:820px){.demo{grid-template-columns:1fr;width:calc(100% - 24px)}.demo-guide{order:1}.demo-phone{order:2;grid-row:auto}.demo-console{order:3}}
      `}</style>
    </>
  );
}

function InputsBar({ snap }: { snap: Snapshot }) {
  const r = snap.radar;
  return (
    <div className="card" style={{ padding: 14 }}>
      <div className="grid-3" style={{ gap: 10 }}>
        <div className="row" style={{ gap: 10, alignItems: 'start' }}>
          <span className="cn-rule" style={{ background: RULE.radar!.color, width: 34, height: 34 }}><Icon name="sat" size={16} /></span>
          <div className="small">
            <b>NISAR {r ? pDay(r.acquired_utc) : '–'}</b> {r && <span className={`chip ${r.processing_level.includes('VALID') && !r.processing_level.includes('PROVISIONAL') ? 'chip-valid' : 'chip-prov'}`} style={{ padding: '0 7px' }}>{r.processing_level.includes('PROVISIONAL') ? 'PROVISIONAL' : 'VALIDATED'}</span>}
            <div className="muted tiny">{r ? `${r.age_days} days old · published ${r.latency_h} h after the pass · track ${r.track}` : 'no pass yet'}</div>
            {snap.in_radar_gap && <div className="tiny hatch" style={{ padding: '2px 6px', borderRadius: 6, marginTop: 4, fontWeight: 700 }}>Radar off 27 Jul – 10 Aug</div>}
          </div>
        </div>
        <div className="row" style={{ gap: 10, alignItems: 'start' }}>
          <span className="cn-rule" style={{ background: RULE.rain!.color, width: 34, height: 34 }}><Icon name="rain" size={16} /></span>
          <div className="small"><b>Rain {snap.rain ? `${snap.rain.mm} mm` : '–'}</b><div className="muted tiny">{snap.rain ? `${snap.rain.date} · NASA IMERG, wettest cell` : 'no value'}</div></div>
        </div>
        <div className="row" style={{ gap: 10, alignItems: 'start' }}>
          <span className="cn-rule" style={{ background: RULE.river!.color, width: 34, height: 34 }}><Icon name="wave" size={16} /></span>
          <div className="small"><b>River (FFWC)</b><div className="muted tiny">{snap.people[0]?.rules.river.reason ?? '–'}</div></div>
        </div>
      </div>
      {snap.next_pass && <p className="tiny muted" style={{ margin: '10px 0 0' }}>Next radar data: NISAR {pDay(snap.next_pass.acquired_utc)} (track {snap.next_pass.track}), published by NASA {dTime(snap.next_pass.published_utc)}.</p>}
    </div>
  );
}

function PeopleRules({ snap }: { snap: Snapshot }) {
  const cell = (x: { fired: boolean; reason: string; confidence: string; values: Record<string, number | null> }, rule: string) => (
    <td style={{ fontSize: '.8rem' }}>
      {x.fired ? <b style={{ color: 'var(--danger)' }}>fires{rule === 'radar' && x.confidence === 'less_sure' ? ' · less sure' : ''}</b> : <span className="muted">{x.reason}</span>}
      {rule === 'radar' && x.values.distance_m != null && <div className="tiny">{n0(x.values.distance_m)} m to new water</div>}
      {rule === 'rain' && x.values.rain_mm != null && <div className="tiny">{x.values.rain_mm} mm vs {x.values.limit_mm} mm</div>}
    </td>
  );
  return (
    <div className="card">
      <h3 style={{ fontSize: '1rem' }}>Every home, every rule <span className="muted tiny">why each rule fired or stayed silent, at this moment</span></h3>
      <div style={{ overflowX: 'auto' }}>
        <table className="table">
          <thead><tr><th>Demo phone</th><th>Radar (≤ 1 km)</th><th>Rain (≥ 76 mm)</th><th>River (DL − 0.30 m)</th></tr></thead>
          <tbody>
            {snap.people.map((p) => (
              <tr key={p.device_id} style={{ background: p.is_visitor ? 'var(--river-lt)' : undefined }}>
                <td style={{ fontSize: '.84rem' }}><b>{p.display_name}</b><div className="tiny muted">{p.channels.map((c) => c.replace('_sim', ' (demo)')).join(', ')}</div></td>
                {cell(p.rules.radar, 'radar')}{cell(p.rules.rain, 'rain')}{cell(p.rules.river, 'river')}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function QrJoin({ sid, joined }: { sid: string; joined: number }) {
  const [url, setUrl] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const link = `${window.location.origin}/join/${sid}`;
  useEffect(() => { QRCode.toDataURL(link, { margin: 1, width: 220, color: { dark: '#12222E', light: '#FFFFFF' } }).then(setUrl).catch(() => undefined); }, [link]);
  return (
    <div className="card" style={{ marginTop: 14, padding: 14 }}>
      <button className="row" onClick={() => setOpen((o) => !o)} style={{ background: 'none', border: 0, padding: 0, width: '100%', justifyContent: 'space-between' }} aria-expanded={open}>
        <b className="row" style={{ gap: 8 }}><Icon name="qr" size={18} /> Use your own phone</b>
        <span className="chip">{joined} joined</span>
      </button>
      {open && (
        <div className="fade-in" style={{ marginTop: 10, display: 'grid', gap: 8, justifyItems: 'center', textAlign: 'center' }}>
          {url && <img src={url} width={180} height={180} alt={`QR code to join this demo: ${link}`} style={{ borderRadius: 12, border: '1px solid var(--line)' }} />}
          <p className="tiny muted" style={{ margin: 0 }}>Scan before you approve. Your phone becomes a home in this demo and receives the alert (with a notification if you allow it).</p>
          <code className="tiny" style={{ wordBreak: 'break-all' }}>{link}</code>
        </div>
      )}
    </div>
  );
}

export function PhoneFrame({ children }: { children: React.ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div className="pf" ref={ref}>
      <div className="pf-notch" aria-hidden="true" />
      <div className="pf-screen">{children}</div>
      <style>{`
        .pf{width:100%;max-width:380px;margin:0 auto;height:min(780px,calc(100vh - var(--nav-h) - 110px));min-height:600px;background:#0f1a20;border-radius:44px;padding:12px;box-shadow:0 30px 70px rgba(18,34,46,.28),inset 0 0 0 2px #2b3a42;position:relative}
        .pf-notch{position:absolute;top:12px;left:50%;transform:translateX(-50%);width:120px;height:24px;background:#0f1a20;border-radius:0 0 16px 16px;z-index:5}
        .pf-screen{height:100%;border-radius:34px;overflow:hidden;background:var(--mist);position:relative}
        .pf-screen .ph{padding-top:16px}
        .pf-screen .ph-top{padding-top:18px}
        @media (max-width:600px){.pf{max-width:none;height:640px;min-height:0;padding:0;background:none;box-shadow:var(--shadow-2);border-radius:22px}.pf-notch{display:none}.pf-screen{border-radius:22px;border:1px solid var(--line)}.pf-screen .ph,.pf-screen .ph-top{padding-top:0}.pf-screen .ph-top{padding-top:12px}}
      `}</style>
    </div>
  );
}
