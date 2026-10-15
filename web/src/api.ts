const BASE = "/api";

export type SessionSummary = {
  id: string;
  source: string;
  task: string | null;
  status: string;
  error: string;
  pending_approvals: string[];
};

export type Event = {
  id: number | null;
  session_id: string;
  seq: number;
  ts: number;
  type: string;
  data: Record<string, unknown>;
};

async function req(path: string, init?: RequestInit) {
  const r = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}

export const api = {
  health: () => req("/health"),
  createSession: (body: object) => req("/sessions", { method: "POST", body: JSON.stringify(body) }),
  listSessions: (): Promise<SessionSummary[]> => req("/sessions"),
  getSession: (id: string): Promise<SessionSummary> => req(`/sessions/${id}`),
  postMessage: (id: string, content: string) =>
    req(`/sessions/${id}/messages`, { method: "POST", body: JSON.stringify({ content }) }),
  getEvents: (id: string, since = 0): Promise<Event[]> =>
    req(`/sessions/${id}/events?since_seq=${since}`),
  getDiff: (id: string): Promise<{ diff: string }> => req(`/sessions/${id}/diff`),
  decideApproval: (id: string, reqId: string, allow: boolean) =>
    req(`/sessions/${id}/approvals/${reqId}`, {
      method: "POST",
      body: JSON.stringify({ allow }),
    }),
  forkSession: (id: string, atSeq?: number): Promise<SessionSummary> =>
    req(`/sessions/${id}/fork${atSeq === undefined ? "" : `?at_seq=${atSeq}`}`, {
      method: "POST",
    }),
  evalSummary: (): Promise<Record<string, any>> => req("/eval-summary"),
};
