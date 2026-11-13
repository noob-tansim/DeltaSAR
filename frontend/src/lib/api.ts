/**
 * Calls to the DeltaSAR API (FastAPI on Render). The address comes from VITE_API_BASE at build time;
 * empty means "same origin" (local development through the Vite proxy).
 *
 * Render's free tier sleeps when idle, so the first call can take up to a minute. `apiState` lets any screen show
 * "waking the server" instead of a blank page.
 */
import { useSyncExternalStore } from 'react';

export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, '') ?? '';

type ApiState = { waking: boolean; down: boolean; lastOk: number | null };
let state: ApiState = { waking: false, down: false, lastOk: null };
const subs = new Set<() => void>();
function setState(p: Partial<ApiState>) {
  state = { ...state, ...p };
  subs.forEach((f) => f());
}
export function useApiState(): ApiState {
  return useSyncExternalStore(
    (f) => {
      subs.add(f);
      return () => subs.delete(f);
    },
    () => state,
  );
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

const sleep = (ms: number) => new Promise((r) => window.setTimeout(r, ms));

/**
 * One API call. While the free server wakes up, Render's proxy refuses connections or answers 502/503/504 without
 * reaching our code, so those are retried every few seconds until `timeoutMs` (default two minutes) has passed.
 */
export async function api<T>(path: string, init: RequestInit & { json?: unknown; token?: string; timeoutMs?: number } = {}): Promise<T> {
  const { json, token, timeoutMs = 120_000, ...rest } = init;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (json !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;
  const deadline = Date.now() + timeoutMs;
  const slow = window.setTimeout(() => setState({ waking: true }), 2500);
  try {
    for (;;) {
      const ctrl = new AbortController();
      const kill = window.setTimeout(() => ctrl.abort(), Math.max(1000, deadline - Date.now()));
      let res: Response | null = null;
      try {
        res = await fetch(`${API_BASE}${path}`, {
          ...rest,
          headers: { ...headers, ...(rest.headers as Record<string, string> | undefined) },
          body: json !== undefined ? JSON.stringify(json) : rest.body,
          signal: ctrl.signal,
        });
      } catch {
        res = null; // no connection yet (server asleep) or timed out
      } finally {
        window.clearTimeout(kill);
      }
      const waking = res === null || res.status === 502 || res.status === 503 || res.status === 504;
      if (waking) {
        if (Date.now() + 3000 < deadline) {
          setState({ waking: true });
          await sleep(3000);
          continue;
        }
        setState({ waking: false, down: true });
        throw new ApiError(0, 'The server could not be reached. Please try again in a minute.');
      }
      setState({ waking: false, down: false, lastOk: Date.now() });
      if (!res!.ok) {
        let msg = `${res!.status} ${res!.statusText}`;
        try {
          const b = await res!.json();
          msg = typeof b.detail === 'string' ? b.detail : Array.isArray(b.detail) ? b.detail.map((d: { msg: string }) => d.msg).join('; ') : msg;
        } catch {
          /* not JSON */
        }
        throw new ApiError(res!.status, msg);
      }
      return (await res!.json()) as T;
    }
  } finally {
    window.clearTimeout(slow);
  }
}

/** Wake the server early (Render free tier) so the demo is ready when the visitor gets there. */
let warmed = false;
export function prewarm(): void {
  if (warmed) return;
  warmed = true;
  api('/api/v1/health', { timeoutMs: 120_000 }).catch(() => { warmed = false; });
}

// ------------------------------------------------------------------ shared types
export type Confidence = 'sure' | 'less_sure' | 'unknown';
export type Status = 'calm' | 'watch' | 'alert' | 'no_data';

export type InputCheck = { name: string; value: string; allowed: string; ok: boolean };
export type Recipient = {
  recipient_id: string; person_id: string; display_name: string | null; union_name: string | null; confidence: Confidence;
  values: Record<string, unknown>; state: string; retry_count: number; reply: 'safe' | 'help' | null; reply_utc: string | null;
  reply_via: string | null; callback_done: boolean; channels: string[];
};
export type EventOut = {
  event_id: string; rule: 'radar' | 'river' | 'rain'; event_key: string; scope: string; state: string; replay: boolean;
  as_of_utc: string; created_utc: string; seconds_left: number | null; message_bn: string; message_en: string;
  approved_by: string | null; approved_utc: string | null; rejected_reason: string | null;
  evidence: Record<string, any>; input_checks: InputCheck[]; recipients: Recipient[];
};
export type LedgerRow = { id: number; utc: string; kind: string; actor: string; person_id: string | null; payload: Record<string, any>; scope?: string };
export type Impact = {
  drafts_created: number; approved: number; rejected: number; late: number; alerts_sent: number;
  sends_ok_by_channel: Record<string, number>; sends_failed_by_channel: Record<string, number>; acknowledged: number;
  replies_safe: number; replies_help: number; no_reply_final: number; callbacks_done: number;
  median_minutes_input_to_approval: number | null; median_minutes_approval_to_first_ack: number | null; participants_note: string;
};
export type RuleView = { fired: boolean; reason: string; confidence: Confidence; values: Record<string, number | null> };
export type SandboxPerson = {
  device_id: string; display_name: string; lat: number; lon: number; union: string | null; union_bn: string | null;
  channels: string[]; is_visitor: boolean; has_push: boolean; rules: Record<'radar' | 'river' | 'rain', RuleView>;
};
export type Snapshot = {
  sandbox_id: string; mode: 'live' | 'replay'; replay: boolean; as_of_utc: string; as_of_local: string; in_radar_gap: boolean;
  next_pass: { date: string; track: string; published_utc: string; acquired_utc: string } | null;
  radar: { key: string; track: string; date: string; acquired_utc: string; published_utc: string; processing_level: string; is_baseline: boolean; age_days: number; new_water_km2: Record<string, number>; latency_h: number } | null;
  rain: { date: string; mm: number; source: string } | null;
  people: SandboxPerson[]; events: EventOut[]; ledger: LedgerRow[]; impact: Impact; approval_window_s: number;
  label?: string;
};

export type AlertOut = {
  recipient_id: string; event_id: string; rule: 'radar' | 'river' | 'rain'; event_state: string; state: string; confidence: Confidence;
  message_bn: string; message_en: string; values: Record<string, any>; replay: boolean; as_of_utc: string; created_utc: string;
  approved_by: string | null; approved_utc: string | null; sent_utc: string | null; ack_utc: string | null;
  reply: 'safe' | 'help' | null; reply_utc: string | null; reply_via: string | null; channels: string[];
  not_official_bn: string; not_official_en: string;
};
export type StatusOut = {
  as_of_utc: string; replay: boolean; status: Status; reasons: string[]; covered: boolean; in_radar_gap: boolean;
  union: UnionOut | null;
  radar: { track: string; pass_utc: string; pass_local: string; published_utc: string | null; age_days: number; stale: boolean; processing_level: string; new_water_distance_m: number | null; walk_minutes: number | null; confidence: Confidence; grew_since_previous_pass: boolean | null; next_expected_local_date: string | null; overlay_url: string | null; overlay_bounds: number[] | null } | null;
  river: { station: string; level_m: number | null; danger_level_m: number; line_m: number; kind: string | null; valid_local: string | null; age_hours: number | null; stale: boolean; source_url: string | null } | null;
  rain: { date: string | null; last_24h_mm: number | null; limit_mm: number; source: string | null; stale: boolean } | null;
  active_alert: AlertOut | null; sources: string[]; not_official: boolean;
};
export type EvidenceOut = {
  recipient_id: string; rule: string;
  rows: { key: string; label_bn: string; label_en: string; value_bn: string; value_en: string }[];
  receipt: Record<string, any>; overlays: { id: string; label: string; url: string; bounds: number[] }[];
  not_official_bn: string; not_official_en: string;
};
export type PersonOut = {
  device_id: string; display_name: string | null; union_id: string | null; home_lat: number; home_lon: number; months: number[];
  rain_on: boolean; rain_mm: number; river_on: boolean; radar_on: boolean; radar_km: number; channels: string[]; email: string | null;
  phone: string | null; mode: Record<string, boolean>; is_demo: boolean; has_push: boolean;
};
export type UnionOut = { union_id: string; name_en: string; name_bn: string | null; upazila_en: string | null; upazila_bn?: string | null; lat: number; lon: number };
export type PointReport = {
  covered: boolean; lat: number; lon: number; message?: string; in_permanent_river?: boolean; height_above_river_m?: number | null;
  distance_to_river_m?: number | null; nearest_union?: UnionOut | null; notes?: string[];
  passes?: { key: string; track: string; date: string; baseline: boolean; dist_new_water_m?: { strict: number | null; mid: number | null; loose: number | null } }[];
};

// ------------------------------------------------------------------ guided demo
export const sandboxApi = {
  create: () => api<{ sandbox_id: string; visitor_device_id: string; snapshot: Snapshot }>('/api/v1/sandbox', { method: 'POST' }),
  get: (sid: string) => api<Snapshot>(`/api/v1/sandbox/${sid}`),
  nextEvent: (sid: string) => api<Snapshot & { label: string }>(`/api/v1/sandbox/${sid}/next-event`, { method: 'POST' }),
  tick: (sid: string) => api<Snapshot>(`/api/v1/sandbox/${sid}/tick`, { method: 'POST' }),
  approve: (sid: string, eid: string, volunteer: string) => api<Snapshot>(`/api/v1/sandbox/${sid}/events/${eid}/approve`, { method: 'POST', json: { volunteer } }),
  reject: (sid: string, eid: string, volunteer: string, reason: string) => api<Snapshot>(`/api/v1/sandbox/${sid}/events/${eid}/reject`, { method: 'POST', json: { volunteer, reason } }),
  callbackDone: (sid: string, rid: string, volunteer: string) => api<Snapshot>(`/api/v1/sandbox/${sid}/callbacks/${rid}/done`, { method: 'POST', json: { volunteer } }),
  simulateReplies: (sid: string) => api<Snapshot>(`/api/v1/sandbox/${sid}/simulate-replies`, { method: 'POST' }),
  clock: (sid: string, body: { mode: 'live' | 'replay'; as_of_utc?: string; preset?: 'start' | 'gap_rain' }) => api<Snapshot>(`/api/v1/sandbox/${sid}/clock`, { method: 'PUT', json: body }),
  join: (sid: string, device_id: string) => api<{ device_id: string; sandbox_id: string; display_name: string }>(`/api/v1/sandbox/${sid}/join`, { method: 'POST', json: { device_id } }),
};

// ------------------------------------------------------------------ phone
export const phoneApi = {
  unions: () => api<UnionOut[]>('/api/v1/unions'),
  person: (d: string) => api<PersonOut>(`/api/v1/people/${d}`),
  putPerson: (d: string, body: Record<string, unknown>) => api<PersonOut>(`/api/v1/people/${d}`, { method: 'PUT', json: body }),
  deletePerson: (d: string) => api<{ removed: boolean }>(`/api/v1/people/${d}`, { method: 'DELETE' }),
  status: (d: string) => api<StatusOut>(`/api/v1/people/${d}/status`, { timeoutMs: 30_000 }),
  alerts: (d: string) => api<AlertOut[]>(`/api/v1/people/${d}/alerts`),
  rain: (d: string) => api<{ as_of_utc: string; replay: boolean; days: { date: string; mm: number }[]; limit_mm: number; source: string | null; note: string }>(`/api/v1/people/${d}/rain`),
  alert: (rid: string) => api<AlertOut>(`/api/v1/alerts/${rid}`),
  evidence: (rid: string) => api<EvidenceOut>(`/api/v1/alerts/${rid}/evidence`),
  ack: (rid: string, device_id: string) => api<AlertOut>(`/api/v1/alerts/${rid}/ack`, { method: 'POST', json: { device_id } }),
  reply: (rid: string, device_id: string, reply: 'safe' | 'help', via = 'in_app') => api<AlertOut>(`/api/v1/alerts/${rid}/reply`, { method: 'POST', json: { device_id, reply, via } }),
  pushKey: () => api<{ public_key: string | null; enabled: boolean }>('/api/v1/push/public-key'),
  subscribe: (device_id: string, subscription: PushSubscriptionJSON) => api<{ subscribed: boolean }>('/api/v1/push/subscribe', { method: 'POST', json: { device_id, subscription, user_agent: navigator.userAgent.slice(0, 300) } }),
  point: (lat: number, lon: number) => api<PointReport>(`/api/v1/point?lat=${lat}&lon=${lon}`),
};

// ------------------------------------------------------------------ console
export const consoleApi = (token: string) => ({
  clock: () => api<any>('/api/v1/console/clock', { token }),
  setClock: (body: { mode: 'live' | 'replay'; as_of_utc?: string; new_run?: boolean }) => api<any>('/api/v1/console/clock', { method: 'PUT', json: body, token }),
  nextEvent: () => api<any>('/api/v1/console/clock/next-event', { method: 'POST', token }),
  tick: () => api<any>('/api/v1/console/tick', { method: 'POST', token }),
  drafts: () => api<EventOut[]>('/api/v1/console/drafts', { token }),
  events: () => api<EventOut[]>('/api/v1/console/events?limit=30', { token }),
  approve: (id: string, volunteer: string) => api<EventOut>(`/api/v1/console/drafts/${id}/approve`, { method: 'POST', json: { volunteer }, token }),
  reject: (id: string, volunteer: string, reason: string) => api<EventOut>(`/api/v1/console/drafts/${id}/reject`, { method: 'POST', json: { volunteer, reason }, token }),
  callbackDone: (rid: string, volunteer: string) => api<EventOut>(`/api/v1/console/callbacks/${rid}/done`, { method: 'POST', json: { volunteer }, token }),
  ledger: () => api<LedgerRow[]>('/api/v1/console/ledger?limit=80', { token }),
  impact: () => api<Impact>('/api/v1/console/impact', { token }),
  inputs: () => api<any>('/api/v1/console/inputs', { token }),
  addRiver: (body: Record<string, unknown>) => api<any>('/api/v1/console/river-readings', { method: 'POST', json: body, token }),
});
