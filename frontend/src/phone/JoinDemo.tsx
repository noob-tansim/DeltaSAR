/** /join/:sid — a phone scanned the QR code of a guided demo. It becomes a phone inside that demo. */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { Icon } from '../components/Icon';
import { sandboxApi } from '../lib/api';
import { device, newDeviceId } from '../lib/device';
import { enablePush, pushSupported } from '../lib/push';

export default function JoinDemo() {
  const { sid } = useParams();
  const nav = useNavigate();
  const [state, setState] = useState<'joining' | 'ask' | 'error'>('joining');
  const [msg, setMsg] = useState('');
  const [id, setId] = useState<string | null>(null);

  useEffect(() => {
    if (!sid) return;
    // a phone that belongs to the live service keeps its own id; demo phones get their own
    const current = device.id();
    const d = current && device.sandbox() ? current : newDeviceId();
    sandboxApi.join(sid, d)
      .then(() => { device.setId(d); device.setSandbox(sid); setId(d); setState('ask'); })
      .catch((e) => { setMsg(String(e.message ?? e)); setState('error'); });
  }, [sid]);

  const go = async (withPush: boolean) => {
    if (withPush && id) {
      const r = await enablePush(id).catch((e) => String(e));
      if (r !== 'ok') setMsg(r);
    }
    nav('/app');
  };

  return (
    <div style={{ minHeight: '100dvh', display: 'grid', placeItems: 'center', padding: 24, background: 'var(--mist)' }}>
      <div className="card" style={{ maxWidth: 420, width: '100%', textAlign: 'center' }}>
        <div style={{ width: 64, height: 64, borderRadius: 20, background: 'var(--river-lt)', color: 'var(--river)', display: 'grid', placeItems: 'center', margin: '0 auto 12px' }}><Icon name="phone" size={32} /></div>
        {state === 'joining' && <h1 style={{ fontSize: '1.5rem' }}>Joining the demo…</h1>}
        {state === 'error' && (<><h1 style={{ fontSize: '1.5rem' }}>Could not join</h1><p className="muted">{msg}</p><a className="btn btn-primary" href="/demo">Start a new demo</a></>)}
        {state === 'ask' && (
          <>
            <h1 style={{ fontSize: '1.5rem' }}>This phone is in the demo.</h1>
            <p className="muted">When the volunteer on the big screen approves the alert, this phone shows it, vibrates and reads it aloud. Allow notifications to get it even with the app closed.</p>
            {msg && <p className="small" style={{ color: 'var(--danger)' }}>{msg}</p>}
            <div className="stack" style={{ marginTop: 16 }}>
              {pushSupported() && <button className="btn btn-primary btn-lg" onClick={() => void go(true)}><Icon name="bell" size={18} /> Allow notifications and open</button>}
              <button className="btn btn-ghost btn-lg" onClick={() => void go(false)}>Open without notifications</button>
            </div>
            <p className="tiny muted" style={{ marginTop: 14 }}>Demo participant only. Nothing about you is stored except a random id for this phone; it is removed after 12 hours.</p>
          </>
        )}
      </div>
    </div>
  );
}
