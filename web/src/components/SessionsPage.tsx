import { useEffect, useState } from "react";
import { api, Event, SessionSummary } from "../api";
import { Transcript } from "./Transcript";

export function SessionsPage({ onOpen }: { onOpen: (id: string) => void }) {
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [active, setActive] = useState<string | null>(null);
  const [events, setEvents] = useState<Event[]>([]);
  const [cursor, setCursor] = useState<number>(-1);
  const [forked, setForked] = useState("");

  async function refresh() {
    setSessions(await api.listSessions());
  }

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  async function open(id: string) {
    setActive(id);
    const evs = await api.getEvents(id);
    setEvents(evs);
    setCursor(evs.length ? evs[evs.length - 1].seq : -1);
  }

  async function fork() {
    if (!active) return;
    const child = await api.forkSession(active, cursor < 0 ? 0 : cursor);
    setForked(child.id);
    refresh();
  }

  const maxSeq = events.length ? events[events.length - 1].seq : 0;
  const shown = cursor < 0 ? events : events.filter((e) => e.seq <= cursor);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <div>
        <h3 className="mb-2 text-sm font-semibold text-slate-300">Sessions</h3>
        <div className="space-y-1">
          {sessions.map((s) => (
            <button
              key={s.id}
              onClick={() => open(s.id)}
              className={`block w-full rounded border px-2 py-1.5 text-left text-xs ${
                active === s.id ? "border-emerald-500" : "border-slate-700"}`}>
              <span className="font-mono">{s.id}</span>{" "}
              <span className="text-slate-400">{s.status}</span>
              <span className="ml-2 text-slate-500">{(s.task ?? "").slice(0, 40)}</span>
            </button>
          ))}
          {sessions.length === 0 && <div className="text-sm text-slate-500">none yet</div>}
        </div>
      </div>
      <div className="lg:col-span-2">
        {!active ? (
          <div className="text-sm text-slate-500">pick a session to replay it</div>
        ) : (
          <div>
            <div className="mb-2 flex items-center gap-3 text-sm">
              <input
                type="range" min={0} max={maxSeq} value={cursor < 0 ? maxSeq : cursor}
                onChange={(e) => setCursor(Number(e.target.value))}
                className="w-64" />
              <span className="font-mono text-slate-400">
                @{cursor < 0 ? maxSeq : cursor}/{maxSeq}
              </span>
              <button onClick={fork} className="rounded bg-sky-700 px-2 py-1 text-xs hover:bg-sky-600">
                Fork here
              </button>
              <button onClick={() => onOpen(active)} className="rounded bg-slate-700 px-2 py-1 text-xs hover:bg-slate-600">
                Watch live
              </button>
              {forked && <span className="font-mono text-xs text-emerald-300">→ {forked}</span>}
            </div>
            <Transcript events={shown} />
          </div>
        )}
      </div>
    </div>
  );
}
