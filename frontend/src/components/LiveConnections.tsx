/** "Live NASA connections": each service the site uses, asked something real about the reach, from this browser. */
import { useEffect, useState } from 'react';
import { API_BASE } from '../lib/api';
import { useL } from '../lib/i18n';
import { probeAll, type Probe } from '../lib/nasa';
import { Icon } from './Icon';

export function LiveConnections() {
  const { L } = useL();
  const [rows, setRows] = useState<Record<string, Probe>>({});
  const [run, setRun] = useState(0);
  useEffect(() => {
    setRows({});
    void probeAll(API_BASE, (p) => setRows((r) => ({ ...r, [p.id]: p })));
  }, [run]);
  const order = ['cmr', 'asf', 'gibs', 'eonet', 'power', 'api'];
  const ok = Object.values(rows).filter((r) => r.ok).length;
  return (
    <div className="card lc">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <div>
          <h3 style={{ margin: 0 }}>{L('Live NASA connections', 'নাসার সাথে সরাসরি সংযোগ')}</h3>
          <p className="small muted" style={{ margin: '2px 0 0' }}>{L('Checked from your browser just now, no keys. Each asks for something real about the Jamuna reach.', 'এইমাত্র আপনার ব্রাউজার থেকে যাচাই করা, কোনো কী ছাড়া। প্রতিটি যমুনা এলাকার আসল তথ্য চায়।')}</p>
        </div>
        <button className="btn btn-ghost btn-sm" onClick={() => setRun((x) => x + 1)}><Icon name="clock" size={14} /> {L('Check again', 'আবার যাচাই')} · {ok}/{order.length}</button>
      </div>
      <ul>
        {order.map((id) => {
          const r = rows[id];
          return (
            <li key={id}>
              <span className={`lc-dot ${r == null ? 'wait' : r.ok ? 'ok' : 'bad'}`} aria-label={r == null ? 'checking' : r.ok ? 'working' : 'not answering'} />
              <div style={{ minWidth: 0 }}>
                <b>{r?.name ?? id}</b> <span className="tiny muted">{r?.what}</span>
                <div className="small" style={{ color: r?.ok === false ? 'var(--danger)' : 'var(--ink-2)' }}>{r == null ? L('checking…', 'যাচাই হচ্ছে…') : r.detail}</div>
              </div>
              <span className="tiny muted num">{r?.ms != null ? `${r.ms} ms` : ''}</span>
            </li>
          );
        })}
      </ul>
      <style>{`
        .lc ul{list-style:none;margin:14px 0 0;padding:0;display:grid;gap:2px}
        .lc li{display:grid;grid-template-columns:14px 1fr auto;gap:12px;align-items:center;padding:9px 6px;border-top:1px solid var(--line)}
        .lc-dot{width:12px;height:12px;border-radius:50%;background:#c3ced2}
        .lc-dot.ok{background:var(--safe);box-shadow:0 0 0 4px var(--safe-lt)}
        .lc-dot.bad{background:var(--danger);box-shadow:0 0 0 4px var(--danger-lt)}
        .lc-dot.wait{animation:pulse 1.4s infinite}
      `}</style>
    </div>
  );
}
