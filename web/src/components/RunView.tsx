import { useEffect, useState } from "react";
import { api, SessionSummary } from "../api";
import { useSessionEvents } from "../hooks";
import { Approvals } from "./Approvals";
import { ContextMeter } from "./ContextMeter";
import { DiffView } from "./DiffView";
import { Transcript } from "./Transcript";

export function RunView({ sid, onDone }: { sid: string | null; onDone: () => void }) {
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const live = summary === null || ["running", "waiting_approval"].includes(summary.status);
  const events = useSessionEvents(sid, live);

  useEffect(() => {
    if (!sid) return;
    const t = setInterval(async () => {
      try {
        const s = await api.getSession(sid);
        setSummary(s);
        if (s.status === "done" || s.status === "error") {
          clearInterval(t);
          onDone();
        }
      } catch { /* session gone */ }
    }, 1000);
    return () => clearInterval(t);
  }, [sid, onDone]);

  if (!sid) return <div className="text-slate-500">Create or pick a session to watch it run.</div>;
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <div>
        <div className="mb-2 flex items-center gap-2 text-sm">
          <span className="font-mono text-slate-400">{sid}</span>
          <StatusBadge status={summary?.status ?? "?"} />
          {summary?.error && <span className="text-red-300">{summary.error}</span>}
        </div>
        <div className="mb-4"><ContextMeter sid={sid} events={events} /></div>
        <Transcript events={events} />
      </div>
      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-300">Diff</h3>
        <DiffView sid={sid} refreshKey={events.length} />
      </div>
      <Approvals sid={sid} events={events} onDecided={() => undefined} />
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "done" ? "bg-emerald-700"
    : status === "error" ? "bg-red-700"
    : status === "waiting_approval" ? "bg-amber-600"
    : "bg-sky-700";
  return <span className={`rounded px-2 py-0.5 text-xs ${color}`}>{status}</span>;
}

export function NewSessionForm({ onCreated }: { onCreated: (id: string) => void }) {
  const [repo, setRepo] = useState("D:/Lever/bug-repo");
  const [task, setTask] = useState("Read add.py, find the bug, fix it.");
  const [provider, setProvider] = useState("auto");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      const s = await api.createSession({ repo, task, provider });
      onCreated(s.id);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 rounded border border-slate-700 bg-slate-800/40 p-4">
      <div className="grid grid-cols-1 gap-2 md:grid-cols-3">
        <input value={repo} onChange={(e) => setRepo(e.target.value)}
          className="rounded bg-slate-900 px-2 py-1.5 font-mono text-sm" placeholder="repo path" />
        <input value={task} onChange={(e) => setTask(e.target.value)}
          className="rounded bg-slate-900 px-2 py-1.5 text-sm md:col-span-1" placeholder="task" />
        <div className="flex gap-2">
          <select value={provider} onChange={(e) => setProvider(e.target.value)}
            className="rounded bg-slate-900 px-2 py-1.5 text-sm">
            <option value="auto">auto</option>
            <option value="fake">fake</option>
            <option value="gemini">gemini</option>
            <option value="local">local</option>
          </select>
          <button disabled={busy} onClick={submit}
            className="rounded bg-emerald-600 px-4 py-1.5 text-sm hover:bg-emerald-500 disabled:opacity-50">
            Run
          </button>
        </div>
      </div>
      {err && <div className="mt-2 text-sm text-red-300">{err}</div>}
    </div>
  );
}
