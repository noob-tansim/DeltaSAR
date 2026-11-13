/** Volunteer-console building blocks, shared by the guided demo (/demo) and the real console (/console). */
import { Fragment, useState } from 'react';
import { Icon, type IconName } from '../components/Icon';
import type { EventOut, Impact, InputCheck, LedgerRow, Recipient } from '../lib/api';
import { dTime, n0, tOnly } from '../lib/format';
import './console.css';

export const RULE: Record<string, { icon: IconName; title: string; color: string }> = {
  radar: { icon: 'sat', title: 'Radar: new water near homes', color: 'var(--river)' },
  river: { icon: 'wave', title: 'River near danger level', color: '#1f5fa8' },
  rain: { icon: 'rain', title: 'Heavy rain', color: '#5b3a8c' },
};

const STATE: Record<string, [string, string]> = {
  drafted: ['Waiting for approval', 'st-draft'], late: ['Late: not approved in time', 'st-late'], approved: ['Approved', 'st-ok'],
  sending: ['Sending', 'st-ok'], sent: ['Sent', 'st-ok'], closed: ['Closed', 'st-closed'], rejected: ['Rejected', 'st-rej'],
};
const REC: Record<string, string> = {
  queued: 'queued', sent: 'sent, not seen yet', acked: 'seen', replied_safe: 'answered: safe', replied_help: 'answered: NEEDS HELP',
  no_reply: 'no reply', retried: 'retried', no_reply_final: 'no reply after 2 retries', failed: 'failed',
};
const CH: Record<string, string> = { in_app: 'app', push: 'push', email: 'email', call_sim: 'call (demo)', sms_sim: 'SMS (demo)' };

export function Checks({ checks }: { checks: InputCheck[] }) {
  return (
    <ul className="cn-checks">
      {checks.map((c) => (
        <li key={c.name} className={c.ok ? 'ok' : 'bad'}>
          <Icon name={c.ok ? 'check' : 'x'} size={15} />
          <span><b>{c.name}</b>: {c.value} <span className="muted">· allowed {c.allowed}</span></span>
        </li>
      ))}
    </ul>
  );
}

export function Receipt({ r }: { r: Record<string, any> }) {
  const rows: [string, string | undefined][] = [
    ['Granule', r.input?.granule_id], ['NASA CMR id', r.input?.cmr_id], ['Acquired (UTC)', r.input?.acquired_utc], ['Published (UTC)', r.input?.published_utc],
    ['Data level', r.input?.processing_level], ['Baseline pass', r.input?.baseline_date], ['Water rule', r.method?.water_rule], ['Threshold method', r.method?.threshold_method],
    ['Tested at', r.method?.tested_at_db ? `${r.method.tested_at_db.join(', ')} dB` : undefined], ['"Sure" means', r.method?.sure_means],
    ['New water, whole reach', r.aoi_result?.new_water_km2_range ? `${r.aoi_result.new_water_km2_range.join('–')} km² (${r.aoi_result.range_within_25pct ? 'within' : 'wider than'} ±25%)` : undefined],
    ['Station', r.input?.station], ['Level', r.input?.level_m != null ? `${r.input.level_m} m` : undefined], ['Line', r.method?.line], ['Rain', r.input?.rain_mm != null ? `${r.input.rain_mm} mm (${r.input.source})` : undefined],
    ['Rule', `${r.rule} v${r.rule_version} · code ${r.code_version}`], ['As of (UTC)', `${r.as_of_utc}${r.replay ? ' · REPLAY' : ''}`],
  ];
  return (
    <div className="cn-receipt">
      <dl className="kv">
        {rows.filter(([, v]) => v).map(([k, v]) => (<Fragment key={k}><dt>{k}</dt><dd className={/Granule|CMR/.test(k) ? 'mono' : ''}>{v}</dd></Fragment>))}
      </dl>
      {r.limits && <ul className="cn-limits">{(r.limits as string[]).map((l) => <li key={l}>{l}</li>)}</ul>}
    </div>
  );
}

export function EventCard({ ev, onApprove, onReject, onCallback, busy, highlight }: {
  ev: EventOut; onApprove?: () => void; onReject?: (reason: string) => void; onCallback?: (rid: string) => void; busy?: boolean; highlight?: boolean;
}) {
  const [open, setOpen] = useState(ev.state === 'drafted');
  const [rej, setRej] = useState(false);
  const [reason, setReason] = useState('');
  const rule = RULE[ev.rule] ?? RULE.radar!;
  const [label, cls] = STATE[ev.state] ?? [ev.state, ''];
  const pending = ev.state === 'drafted' || ev.state === 'late';
  const help = ev.recipients.filter((r) => r.reply === 'help' && !r.callback_done);
  return (
    <article className={`cn-ev ${highlight ? 'hl' : ''} ${pending ? 'pending' : ''}`}>
      <header className="cn-ev-h">
        <span className="cn-rule" style={{ background: rule.color }}><Icon name={rule.icon} size={18} /></span>
        <div style={{ minWidth: 0 }}>
          <b>{rule.title}</b>
          <div className="tiny muted">{ev.event_key} · created {dTime(ev.created_utc)} · {ev.recipients.length} {ev.recipients.length === 1 ? 'person' : 'people'}</div>
        </div>
        <span className={`cn-st ${cls}`}>{label}</span>
      </header>
      {ev.replay && <div className="chip chip-replay" style={{ marginBottom: 8 }}>REPLAY · real data from a past date</div>}
      <p className="cn-msg bn">{ev.message_bn}</p>
      <p className="cn-msg-en">{ev.message_en}</p>
      {pending && ev.seconds_left != null && (
        <p className="tiny" style={{ color: ev.seconds_left < 0 ? 'var(--danger)' : 'var(--ink-3)', margin: '0 0 8px' }}>
          {ev.seconds_left < 0 ? 'Approval window passed. It stays here, red, and never sends by itself.' : `Approve within ${Math.ceil(ev.seconds_left / 60)} min.`}
        </p>
      )}
      {pending && onApprove && (
        <div className="row" style={{ gap: 8, marginBottom: 6 }}>
          <button className="btn btn-primary" onClick={onApprove} disabled={busy}><Icon name="send" size={16} /> Approve and send</button>
          {!rej ? <button className="btn btn-ghost" onClick={() => setRej(true)} disabled={busy}>Reject…</button> : (
            <span className="row" style={{ gap: 6 }}>
              <input className="input" style={{ minHeight: 40, width: 220 }} placeholder="Reason (required)" value={reason} onChange={(e) => setReason(e.target.value)} />
              <button className="btn btn-danger btn-sm" disabled={reason.trim().length < 3 || busy} onClick={() => onReject?.(reason)}>Reject</button>
            </span>
          )}
        </div>
      )}
      {help.length > 0 && (
        <div className="cn-help">
          <b><Icon name="help" size={16} /> {help.length} help {help.length === 1 ? 'request' : 'requests'}: call back now</b>
          {help.map((r) => (
            <div key={r.recipient_id} className="row" style={{ justifyContent: 'space-between' }}>
              <span>{r.display_name} · answered {r.reply_utc ? tOnly(r.reply_utc) : ''} by {CH[r.reply_via ?? ''] ?? r.reply_via}</span>
              {onCallback && <button className="btn btn-danger btn-sm" onClick={() => onCallback(r.recipient_id)} disabled={busy}>Call-back done</button>}
            </div>
          ))}
        </div>
      )}
      <button className="cn-more" onClick={() => setOpen((o) => !o)} aria-expanded={open}>
        <Icon name={open ? 'down' : 'chev'} size={14} /> Recipients, input checks and the evidence receipt
      </button>
      {open && (
        <div className="cn-detail">
          <Recipients recs={ev.recipients} />
          <h4>Input checks</h4>
          <Checks checks={ev.input_checks} />
          <h4>Evidence receipt</h4>
          <Receipt r={ev.evidence} />
          {ev.rejected_reason && <p className="small" style={{ color: 'var(--danger)' }}>Rejected: {ev.rejected_reason}</p>}
        </div>
      )}
    </article>
  );
}

export function Recipients({ recs }: { recs: Recipient[] }) {
  return (
    <table className="table" style={{ fontSize: '.84rem' }}>
      <thead><tr><th>Person</th><th className="r">Distance</th><th>How sure</th><th>Channels</th><th>State</th></tr></thead>
      <tbody>
        {recs.map((r) => (
          <tr key={r.recipient_id} style={{ background: r.reply === 'help' && !r.callback_done ? 'var(--danger-lt)' : undefined }}>
            <td>{r.display_name}</td>
            <td className="r">{r.values.distance_m != null ? `${n0(r.values.distance_m as number)} m · ${r.values.walk_minutes} min` : '–'}</td>
            <td>{r.confidence === 'sure' ? 'sure' : r.confidence === 'less_sure' ? <span className="chip chip-prov" style={{ padding: '0 7px' }}>less sure</span> : r.confidence}</td>
            <td>{r.channels.map((c) => <span key={c} className={`chip ${c.endsWith('_sim') ? 'chip-sim' : ''}`} style={{ padding: '0 7px', marginRight: 4 }}>{CH[c] ?? c}</span>)}</td>
            <td>{REC[r.state] ?? r.state}{r.callback_done ? ' · call-back done' : ''}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

const KIND: Record<string, [string, IconName]> = {
  sandbox_created: ['Demo started', 'play'], person_joined: ['A phone joined', 'phone'], clock_set: ['Clock set', 'clock'], input_seen: ['New input visible', 'sat'],
  rule_evaluated: ['Rules checked', 'receipt'], draft_created: ['Draft created', 'bell'], recipient_added: ['Recipient added', 'user'], approved: ['Approved by a volunteer', 'shield'],
  rejected: ['Rejected', 'x'], late: ['Late (not approved in time)', 'clock'], sent: ['Sent', 'send'], send_failed: ['Send failed', 'x'], acked: ['Seen on the phone', 'check'],
  reply_safe: ['Answered: safe', 'check'], reply_help: ['Answered: NEEDS HELP', 'help'], retry: ['Retried', 'clock'], no_reply_final: ['No reply after retries', 'x'],
  callback_done: ['Call-back done', 'phone'], closed: ['Alert closed', 'check'], river_reading_added: ['River reading typed in', 'wave'],
};

export function LedgerFeed({ rows, max = 14 }: { rows: LedgerRow[]; max?: number }) {
  const show = rows.filter((r) => r.kind !== 'rule_evaluated' || rows.indexOf(r) < 3).slice(0, max);
  return (
    <ol className="cn-ledger" aria-live="polite">
      {show.map((r) => {
        const [t, ic] = KIND[r.kind] ?? [r.kind, 'info'];
        const p = r.payload ?? {};
        const extra = r.kind === 'sent' ? ` · ${CH[p.channel] ?? p.channel}` : r.kind === 'clock_set' ? ` · ${p.mode}${p.as_of_utc ? ` ${dTime(p.as_of_utc)}` : ''}` : r.kind === 'input_seen' ? ` · ${p.input} ${p.key}` : r.kind === 'draft_created' ? ` · ${p.rule}, ${p.recipients} people` : r.kind.startsWith('reply') && p.via ? ` · via ${CH[p.via] ?? p.via}` : '';
        return (
          <li key={r.id} className={`k-${r.kind}`}>
            <span className="ic"><Icon name={ic} size={13} /></span>
            <span className="t">{t}{extra}{r.actor && r.actor !== 'system' ? <span className="muted"> · {r.actor}</span> : null}</span>
            <span className="tm mono">#{r.id} {tOnly(r.utc)}</span>
          </li>
        );
      })}
      {!show.length && <li className="muted small">Nothing yet.</li>}
    </ol>
  );
}

export function ImpactPanel({ i }: { i: Impact }) {
  const cells: [string, number | string, string?][] = [
    ['Drafts', i.drafts_created], ['Approved', i.approved], ['Alerts sent', i.alerts_sent], ['Seen', i.acknowledged],
    ['Safe', i.replies_safe, 'var(--safe)'], ['Need help', i.replies_help, 'var(--danger)'], ['Call-backs done', i.callbacks_done], ['No reply', i.no_reply_final],
  ];
  return (
    <div>
      <div className="cn-impact">
        {cells.map(([k, v, c]) => (
          <div key={k}><b style={{ color: c }}>{v}</b><span>{k}</span></div>
        ))}
      </div>
      <p className="tiny muted" style={{ margin: '8px 0 0' }}>
        Counted from ledger rows only. {i.median_minutes_input_to_approval != null && `Median draft → approval: ${i.median_minutes_input_to_approval} min. `}
        {i.median_minutes_approval_to_first_ack != null && `Approval → first seen: ${i.median_minutes_approval_to_first_ack} min. `}{i.participants_note}
      </p>
    </div>
  );
}
