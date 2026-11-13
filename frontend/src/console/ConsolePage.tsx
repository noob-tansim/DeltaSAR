/** /console: the volunteer console for the shared (non-sandbox) service. Token asked once, kept for this tab only. */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Nav } from '../components/Chrome';
import { Icon } from '../components/Icon';
import { consoleApi, type EventOut, type Impact, type LedgerRow } from '../lib/api';
import { device } from '../lib/device';
import { dTime } from '../lib/format';
import { Checks, EventCard, ImpactPanel, LedgerFeed } from './parts';

export default function ConsolePage() {
  const [token, setToken] = useState<string | null>(device.consoleToken());
  const [name, setName] = useState('Volunteer');
  if (!token) return <Login onOk={(t, n) => { device.setConsoleToken(t); setToken(t); setName(n); }} />;
  return <Console token={token} volunteer={name} onLogout={() => { device.setConsoleToken(null); setToken(null); }} />;
}

function Login({ onOk }: { onOk: (t: string, n: string) => void }) {
  const [t, setT] = useState('');
  const [n, setN] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const go = async () => {
    try { await consoleApi(t).clock(); onOk(t, n || 'Volunteer'); } catch (e) { setErr(String((e as Error).message)); }
  };
  return (
    <>
      <Nav dark={false} />
      <main id="main" style={{ minHeight: 'calc(100vh - var(--nav-h))', display: 'grid', placeItems: 'center', padding: 24 }}>
        <form className="card stack" style={{ width: 'min(420px,100%)' }} onSubmit={(e) => { e.preventDefault(); void go(); }}>
          <h1 style={{ fontSize: '1.6rem', margin: 0 }}>বন্যা সাথী · volunteer console</h1>
          <p className="small muted" style={{ margin: 0 }}>For the union volunteers of the team's live service. To try the system yourself, use the <a href="/demo">guided demo</a>: it needs no token.</p>
          <label className="field">Your name<input className="input" value={n} onChange={(e) => setN(e.target.value)} autoComplete="name" /></label>
          <label className="field">Console token<input className="input" type="password" value={t} onChange={(e) => setT(e.target.value)} autoComplete="current-password" /></label>
          {err && <p className="small" style={{ color: 'var(--danger)', margin: 0 }}>{err}</p>}
          <button className="btn btn-primary" type="submit" disabled={!t}>Open the console</button>
        </form>
      </main>
    </>
  );
}

function Console({ token, volunteer, onLogout }: { token: string; volunteer: string; onLogout: () => void }) {
  const api = useMemo(() => consoleApi(token), [token]);
  const [clock, setClock] = useState<any>(null);
  const [drafts, setDrafts] = useState<EventOut[]>([]);
  const [events, setEvents] = useState<EventOut[]>([]);
  const [ledger, setLedger] = useState<LedgerRow[]>([]);
  const [impact, setImpact] = useState<Impact | null>(null);
  const [inputs, setInputs] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [when, setWhen] = useState('2026-07-26T14:00');

  const load = useCallback(async () => {
    try {
      const [c, d, e, l, i, inp] = await Promise.all([api.clock(), api.drafts(), api.events(), api.ledger(), api.impact(), api.inputs()]);
      setClock(c); setDrafts(d); setEvents(e.filter((x) => !d.some((y) => y.event_id === x.event_id))); setLedger(l); setImpact(i); setInputs(inp);
    } catch (e) { setMsg(String((e as Error).message)); }
  }, [api]);
  useEffect(() => { void load(); const t = window.setInterval(() => void load(), 5000); return () => window.clearInterval(t); }, [load]);

  const act = async (fn: () => Promise<unknown>, ok?: string) => {
    setBusy(true); setMsg(null);
    try { await fn(); if (ok) setMsg(ok); await load(); } catch (e) { setMsg(String((e as Error).message)); } finally { setBusy(false); }
  };
  const help = events.flatMap((e) => e.recipients.filter((r) => r.reply === 'help' && !r.callback_done).map((r) => ({ e, r })));

  return (
    <>
      <Nav dark={false} />
      <main id="main" className="cs">
        <header className="card cs-clock">
          <div>
            <div className="eyebrow" style={{ marginBottom: 4 }}>Volunteer console · {volunteer}</div>
            <div className="row" style={{ gap: 10 }}>
              <span className={`chip ${clock?.mode === 'replay' ? 'chip-replay' : 'chip-live'}`}>{clock?.mode === 'replay' ? 'REPLAY' : 'LIVE'}</span>
              <b style={{ fontFamily: 'var(--font-display)', fontSize: '1.4rem' }}>{clock ? dTime(clock.as_of_utc) : '…'}</b><span className="muted small">Dhaka</span>
              {clock?.demo_timing && <span className="chip">demo timing: approve within {Math.round(clock.approval_window_s / 60)} min</span>}
            </div>
            {clock?.next_event_label && <div className="tiny muted" style={{ marginTop: 4 }}>Next: {clock.next_event_label} ({dTime(clock.next_event_utc)})</div>}
          </div>
          <div className="row" style={{ gap: 8 }}>
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void act(() => api.setClock({ mode: 'live' }), 'Clock: LIVE')}>Live</button>
            <input className="input" type="datetime-local" value={when} onChange={(e) => setWhen(e.target.value)} style={{ minHeight: 38, width: 200 }} aria-label="Replay time (Dhaka)" />
            <button className="btn btn-ghost btn-sm" disabled={busy} onClick={() => void act(() => api.setClock({ mode: 'replay', as_of_utc: new Date(`${when}:00+06:00`).toISOString(), new_run: true }), 'New replay run started')}>Replay from here</button>
            <button className="btn btn-ghost btn-sm" disabled={busy || clock?.mode !== 'replay'} onClick={() => void act(() => api.nextEvent())}>Next event</button>
            <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void act(() => api.tick(), 'Rules checked')}><Icon name="receipt" size={14} /> Check now</button>
            <button className="btn btn-ghost btn-sm" onClick={onLogout}>Sign out</button>
          </div>
        </header>
        {msg && <p className="callout small" role="status">{msg}</p>}
        <div className="cs-grid">
          <div className="stack" style={{ gap: 14 }}>
            {help.length > 0 && (
              <div className="cn-help" style={{ margin: 0 }}>
                <b><Icon name="help" size={16} /> {help.length} help request{help.length > 1 ? 's' : ''}</b>
                {help.map(({ e, r }) => (
                  <div key={r.recipient_id} className="row" style={{ justifyContent: 'space-between' }}>
                    <span>{r.display_name} · {r.union_name} · {e.rule} {e.event_key}</span>
                    <button className="btn btn-danger btn-sm" disabled={busy} onClick={() => void act(() => api.callbackDone(r.recipient_id, volunteer))}>Call-back done</button>
                  </div>
                ))}
              </div>
            )}
            <h2 style={{ fontSize: '1.2rem', margin: '4px 0 0' }}>Drafts waiting for you ({drafts.length})</h2>
            {drafts.length === 0 && <div className="card small muted">No drafts. Rules run every 30 seconds, or press “Check now”.</div>}
            {drafts.map((e) => <EventCard key={e.event_id} ev={e} busy={busy} onApprove={() => void act(() => api.approve(e.event_id, volunteer), 'Approved and sent')} onReject={(r) => void act(() => api.reject(e.event_id, volunteer, r), 'Rejected')} />)}
            <h2 style={{ fontSize: '1.2rem', margin: '10px 0 0' }}>Sent and closed</h2>
            {events.slice(0, 8).map((e) => <EventCard key={e.event_id} ev={e} busy={busy} onCallback={(rid) => void act(() => api.callbackDone(rid, volunteer))} />)}
          </div>
          <div className="stack" style={{ gap: 14 }}>
            {inputs && (
              <div className="card">
                <h3 style={{ fontSize: '1rem' }}>Inputs and why each rule did or did not fire</h3>
                <Checks checks={inputs.checks} />
                {inputs.rules?.map((r: any) => (
                  <div key={r.rule} className="small" style={{ marginTop: 10 }}>
                    <b>{r.rule}</b>: {r.fired} fired of {r.people_checked}
                    <ul style={{ margin: '4px 0 0', paddingLeft: 18 }}>{Object.entries(r.reasons).map(([k, v]) => <li key={k}>{String(v)} × {k}</li>)}</ul>
                  </div>
                ))}
              </div>
            )}
            <RiverEntry onSave={(b) => void act(() => api.addRiver(b), 'River reading saved')} busy={busy} volunteer={volunteer} />
            {impact && <div className="card"><h3 style={{ fontSize: '1rem' }}>Impact</h3><ImpactPanel i={impact} /></div>}
            <div className="card"><h3 style={{ fontSize: '1rem' }}>Ledger</h3><LedgerFeed rows={ledger} max={30} /></div>
          </div>
        </div>
      </main>
      <style>{`
        body{background:var(--mist)}
        .cs{width:min(1320px,100% - 32px);margin:16px auto 40px;display:grid;gap:14px}
        .cs-clock{display:flex;justify-content:space-between;gap:14px;flex-wrap:wrap;align-items:center;padding:16px 18px}
        .cs-grid{display:grid;grid-template-columns:minmax(0,1.5fr) minmax(0,1fr);gap:16px;align-items:start}
        @media (max-width:980px){.cs-grid{grid-template-columns:1fr}}
      `}</style>
    </>
  );
}

function RiverEntry({ onSave, busy, volunteer }: { onSave: (b: Record<string, unknown>) => void; busy: boolean; volunteer: string }) {
  const [st, setSt] = useState('Kazipur');
  const [lv, setLv] = useState('');
  const [kind, setKind] = useState<'observed' | 'forecast'>('observed');
  const [lead, setLead] = useState(0);
  const [valid, setValid] = useState(new Date(Date.now() + 6 * 3.6e6).toISOString().slice(0, 16));
  const [src, setSrc] = useState('http://old.ffwc.gov.bd/ffwc_charts/waterlevelobs.php');
  const level = Number(lv);
  const ok = lv !== '' && level >= 5 && level <= 25;
  return (
    <form className="card stack" style={{ gap: 8 }} onSubmit={(e) => { e.preventDefault(); if (ok) onSave({ station: st, level_m: level, kind, lead_days: kind === 'observed' ? 0 : lead, valid_local: `${valid}:00+06:00`, source_url: src, entered_by: volunteer }); }}>
      <h3 style={{ fontSize: '1rem', margin: 0 }}>Type a river reading from the FFWC bulletin</h3>
      <div className="grid-2" style={{ gap: 8 }}>
        <label className="field">Station<select className="input" value={st} onChange={(e) => setSt(e.target.value)}><option>Kazipur</option><option>Sirajganj</option></select></label>
        <label className="field">Level (m)<input className="input" inputMode="decimal" value={lv} onChange={(e) => setLv(e.target.value)} aria-invalid={lv !== '' && !ok} /></label>
        <label className="field">Kind<select className="input" value={kind} onChange={(e) => setKind(e.target.value as 'observed' | 'forecast')}><option value="observed">observed</option><option value="forecast">forecast</option></select></label>
        <label className="field">Lead (days)<input className="input" type="number" min={0} max={5} value={lead} disabled={kind === 'observed'} onChange={(e) => setLead(+e.target.value)} /></label>
      </div>
      <label className="field">Valid at (Dhaka)<input className="input" type="datetime-local" value={valid} onChange={(e) => setValid(e.target.value)} /></label>
      <label className="field">Source link<input className="input" value={src} onChange={(e) => setSrc(e.target.value)} /></label>
      {lv !== '' && !ok && <p className="tiny" style={{ color: 'var(--danger)', margin: 0 }}>Allowed 5 to 25 m. Out-of-range values are refused, never clipped.</p>}
      <button className="btn btn-ghost btn-sm" disabled={!ok || busy}>Save reading</button>
    </form>
  );
}
