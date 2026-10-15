import { useState } from "react";
import { api, Event } from "../api";

/** Approval modal: every request without a matching decision. */
export function Approvals({ sid, events, onDecided }: {
  sid: string;
  events: Event[];
  onDecided: () => void;
}) {
  const [busy, setBusy] = useState<string | null>(null);
  const decided = new Set(
    events.filter((e) => e.type === "approval_decision")
      .map((e) => String((e.data as Record<string, unknown>).req_id)),
  );
  const pending = events.filter((e) =>
    e.type === "approval_request" &&
    !decided.has(String((e.data as Record<string, unknown>).req_id)));

  async function decide(reqId: string, allow: boolean) {
    setBusy(reqId);
    try {
      await api.decideApproval(sid, reqId, allow);
      onDecided();
    } finally {
      setBusy(null);
    }
  }

  if (pending.length === 0) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70">
      <div className="w-full max-w-lg rounded-lg border border-amber-500/50 bg-slate-900 p-5">
        <h2 className="mb-3 text-lg font-semibold text-amber-300">
          Approval needed ({pending.length})
        </h2>
        {pending.map((e) => {
          const d = e.data as Record<string, unknown>;
          const reqId = String(d.req_id);
          return (
            <div key={e.seq} className="mb-3 rounded border border-slate-700 p-3">
              <div className="font-mono text-sm">{String(d.name)}</div>
              <pre className="my-2 max-h-32 overflow-auto text-xs text-slate-400">
                {JSON.stringify(d.args, null, 1)}
              </pre>
              <div className="mb-3 text-xs text-slate-400">{String(d.reason ?? "")}</div>
              <div className="flex gap-2">
                <button
                  disabled={busy === reqId}
                  onClick={() => decide(reqId, true)}
                  className="rounded bg-emerald-600 px-4 py-1.5 text-sm hover:bg-emerald-500 disabled:opacity-50">
                  Allow
                </button>
                <button
                  disabled={busy === reqId}
                  onClick={() => decide(reqId, false)}
                  className="rounded bg-red-600 px-4 py-1.5 text-sm hover:bg-red-500 disabled:opacity-50">
                  Deny
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
