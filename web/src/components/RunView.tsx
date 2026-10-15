import { useEffect, useRef, useState } from "react";
import { api, SessionSummary } from "../api";
import { useSessionEvents } from "../hooks";
import { Approvals } from "./Approvals";
import { ContextMeter } from "./ContextMeter";
import { FileExplorer } from "./FileExplorer";
import { FileView } from "./FileView";
import { NewTaskBar, PromptBox } from "./PromptBox";
import { Transcript } from "./Transcript";

/** Cursor-style IDE: chat left, files right. */
export function IDE({ sid, onSession }: {
  sid: string | null;
  onSession: (id: string) => void;
}) {
  const [summary, setSummary] = useState<SessionSummary | null>(null);
  const summaryRef = useRef<SessionSummary | null>(null);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(true);
  const [changed, setChanged] = useState<Set<string>>(new Set());
  const [tick, setTick] = useState(0);
  const live = !summary || ["running", "waiting_approval", "idle"].includes(summary.status);
  const events = useSessionEvents(sid, live);

  useEffect(() => {
    if (!sid) return;
    let stop = false;
    const poll = async () => {
      try {
        const s = await api.getSession(sid);
        if (stop) return;
        const was = summaryRef.current?.status;
        summaryRef.current = s;
        setSummary(s);
        if ((s.status === "done" || s.status === "error") && was !== s.status) {
          setTick((n) => n + 1);
        }
      } catch { /* session gone */ }
    };
    poll();
    const t = setInterval(poll, 1000);
    return () => { stop = true; clearInterval(t); };
  }, [sid]);

  useEffect(() => {
    if (!sid) return;
    api.getDiff(sid).then((d) => setChanged(parseChanged(d.diff))).catch(() => undefined);
  }, [sid, tick, events.length]);

  async function start(repo: string, task: string, provider: string, model: string) {
    const s = await api.createSession({ repo, task, provider, model: model || undefined });
    onSession(s.id);
  }

  async function followUp(content: string, files: string[]) {
    if (!sid) return;
    await api.postMessage(sid, content, files);
  }

  return (
    <div>
      <NewTaskBar onRun={start} />
      {!sid ? (
        <div className="text-sm text-slate-500">Start a task above — the agent works in a copy; your repo stays clean.</div>
      ) : (
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <div className="min-w-0">
            <div className="mb-2 flex items-center gap-2 text-sm">
              <span className="font-mono text-slate-400">{sid}</span>
              <StatusBadge status={summary?.status ?? "?"} />
              {summary?.model && (
                <span className="rounded bg-slate-700 px-2 py-0.5 font-mono text-xs">{summary.model}</span>
              )}
              {summary?.error && <span className="text-red-300">{summary.error}</span>}
            </div>
            <div className="mb-3"><ContextMeter sid={sid} events={events} /></div>
            <div className="mb-3 max-h-[46vh] overflow-auto"><Transcript events={events} live={live} /></div>
            <PromptBox sid={sid} disabled={!summary || !["done", "error", "idle"].includes(summary.status)} onSend={followUp} />
            <div className="mt-1 text-xs text-slate-500">
              {summary && !["done", "error", "idle"].includes(summary.status)
                ? "Agent running — prompt unlocks when it stops."
                : "Idle — send a follow-up (edits accumulate in the same workspace)."}
            </div>
          </div>
          <div className="grid min-w-0 grid-cols-[180px_1fr] gap-2">
            <div className="max-h-[70vh] overflow-auto rounded border border-slate-700/60 p-2">
              <FileExplorer sid={sid} changed={changed} openPath={openPath} onOpen={setOpenPath} />
            </div>
            <div className="min-w-0">
              {!openPath ? (
                <div className="text-sm text-slate-500">Pick a file. <span className="text-amber-300">●</span> = changed.</div>
              ) : (
                <div>
                  <div className="mb-1 flex items-center gap-2">
                    <span className="font-mono text-xs text-slate-300">{openPath}</span>
                    <button onClick={() => setShowDiff(!showDiff)}
                      className="rounded bg-slate-700 px-2 py-0.5 text-xs hover:bg-slate-600">
                      {showDiff ? "show file" : "show changes"}
                    </button>
                  </div>
                  <div className="max-h-[66vh] overflow-auto">
                    <FileView sid={sid} path={openPath} showDiff={showDiff} refreshKey={events.length} />
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
      {sid && <Approvals sid={sid} events={events} onDecided={() => undefined} />}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const color =
    status === "done" ? "bg-emerald-700"
    : status === "error" ? "bg-red-700"
    : status === "waiting_approval" ? "bg-amber-600"
    : "bg-sky-700";
  const pulse = ["running", "waiting_approval"].includes(status) ? " animate-pulse" : "";
  return <span className={`rounded px-2 py-0.5 text-xs ${color}${pulse}`}>{status}</span>;
}

function parseChanged(stat: string): Set<string> {
  const out = new Set<string>();
  for (const line of stat.split("\n")) {
    const m = line.match(/^\s*(\S.*?)\s+\|\s+\d+/);
    if (m) out.add(m[1].trim());
    const u = line.match(/^\?\?\s+(.+?)\s*$/);
    if (u) out.add(u[1].trim());
  }
  return out;
}
