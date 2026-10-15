const BASE = "/api";

export type SessionSummary = {
  id: string;
  source: string;
  task: string | null;
  status: string;
  error: string;
  model: string;
  provider: string;
  pending_approvals: string[];
};

export type ProviderInfo = {
  id: string;
  model: string;
  configured: boolean;
  cost: string;
};

export type FileEntry = { path: string; type: string; size?: number };

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
  postMessage: (id: string, content: string, files: string[] = []) =>
    req(`/sessions/${id}/messages`, {
      method: "POST",
      body: JSON.stringify({ content, files }),
    }),
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
  providers: (): Promise<ProviderInfo[]> => req("/providers"),
  files: (id: string): Promise<FileEntry[]> => req(`/sessions/${id}/files`),
  fileContent: (id: string, path: string): Promise<{ path: string; content: string; truncated: boolean }> =>
    req(`/sessions/${id}/file?path=${encodeURIComponent(path)}`),
  fileDiff: (id: string, path: string): Promise<{ path: string; original: string | null; modified: string }> =>
    req(`/sessions/${id}/file-diff?path=${encodeURIComponent(path)}`),
};
