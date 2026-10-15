import { Event } from "../api";

function short(s: string, n = 600) {
  return s.length > n ? s.slice(0, n) + "…" : s;
}

export function Transcript({ events }: { events: Event[] }) {
  return (
    <div className="space-y-2 text-sm">
      {events
        .filter((e) =>
          ["user_message", "model_response", "tool_call", "tool_result",
            "harness_nudge", "policy_block", "approval_request",
            "approval_decision", "context_compacted", "session_end",
            "error"].includes(e.type))
        .map((e) => (
          <div key={e.seq} className="rounded border border-slate-700/60 bg-slate-800/40 px-3 py-2">
            <div className="mb-1 flex items-center gap-2 text-xs text-slate-400">
              <span className="rounded bg-slate-700 px-1.5 py-0.5 font-mono">{e.type}</span>
              <span>#{e.seq}</span>
            </div>
            <Body e={e} />
          </div>
        ))}
    </div>
  );
}

function Body({ e }: { e: Event }) {
  const d = e.data as Record<string, unknown>;
  switch (e.type) {
    case "user_message":
      return <div className="whitespace-pre-wrap">{String(d.content ?? "")}</div>;
    case "model_response": {
      const calls = (d.tool_calls as Array<{ name: string }> | undefined) ?? [];
      return (
        <div>
          {d.text ? <div className="whitespace-pre-wrap">{short(String(d.text))}</div> : null}
          {calls.map((c, i) => (
            <div key={i} className="font-mono text-emerald-300">→ {c.name}()</div>
          ))}
        </div>
      );
    }
    case "tool_call":
      return (
        <div className="font-mono text-sky-300">
          {String(d.name)} <span className="text-slate-400">{short(JSON.stringify(d.args ?? {}), 300)}</span>
        </div>
      );
    case "tool_result":
      return (
        <div>
          <div className="font-mono text-slate-300">{String(d.name)}</div>
          <pre className="whitespace-pre-wrap text-xs text-slate-400">{short(String(d.result ?? ""), 800)}</pre>
        </div>
      );
    case "harness_nudge":
      return <div className="text-amber-300">[{String(d.kind)}] {short(String(d.text ?? ""))}</div>;
    case "policy_block":
      return <div className="text-red-300">blocked: {short(String(d.reason ?? ""))}</div>;
    case "approval_request":
      return <div className="text-amber-300">approval requested: {String(d.name)} — {short(String(d.reason ?? ""))}</div>;
    case "approval_decision":
      return (
        <div className={d.allow ? "text-emerald-300" : "text-red-300"}>
          {d.allow ? "approved" : "denied"} by {String(d.by ?? "?")}
        </div>
      );
    case "context_compacted":
      return (
        <div className="text-violet-300">
          compacted: {String(d.before)} → {String(d.after)} tokens ({String(d.dropped)} msgs)
        </div>
      );
    case "session_end": {
      const dd = d as Record<string, unknown>;
      return <div className="text-slate-200">ended: {String(dd.stopped_by)} — {short(String(dd.answer ?? ""), 300)}</div>;
    }
    default:
      return <pre className="text-xs text-slate-500">{short(JSON.stringify(d))}</pre>;
  }
}
