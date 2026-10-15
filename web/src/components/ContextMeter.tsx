import { useEffect, useState } from "react";
import { Event } from "../api";

const BUDGET = 60000;

/** Stacked context bar from model_request message sizes + compaction markers. */
export function ContextMeter({ sid, events }: { sid: string; events: Event[] }) {
  const [detail, setDetail] = useState<{ sys: number; user: number; other: number } | null>(null);
  const [markers, setMarkers] = useState<number[]>([]);

  useEffect(() => {
    const reqs = events.filter((e) => e.type === "model_request");
    const last = reqs[reqs.length - 1];
    if (!last) {
      setDetail(null);
      return;
    }
    const msgs = ((last.data as Record<string, unknown>).messages as Array<{
      role: string; content: string;
    }>) ?? [];
    let sys = 0, user = 0, other = 0;
    for (const m of msgs) {
      const t = Math.ceil(String(m.content ?? "").length / 4);
      if (m.role === "system") sys += t;
      else if (m.role === "user") user += t;
      else other += t;
    }
    setDetail({ sys, user, other });
    setMarkers(events.filter((e) => e.type === "context_compacted").map((e) => e.seq));
  }, [events, sid]);

  if (!detail) return <div className="text-sm text-slate-500">no model calls yet</div>;
  const total = detail.sys + detail.user + detail.other;
  const pct = (v: number) => `${Math.min(100, (v / BUDGET) * 100).toFixed(1)}%`;
  return (
    <div>
      <div className="flex h-5 w-full overflow-hidden rounded bg-slate-800">
        <div className="bg-violet-500" style={{ width: pct(detail.sys) }} title={`system ${detail.sys}`} />
        <div className="bg-sky-500" style={{ width: pct(detail.user) }} title={`user ${detail.user}`} />
        <div className="bg-slate-500" style={{ width: pct(detail.other) }} title={`other ${detail.other}`} />
      </div>
      <div className="mt-1 flex justify-between text-xs text-slate-400">
        <span>
          <span className="text-violet-300">■ sys {detail.sys}</span>{" "}
          <span className="text-sky-300">■ user {detail.user}</span>{" "}
          <span className="text-slate-300">■ other {detail.other}</span>
        </span>
        <span>{total} / {BUDGET} tokens {markers.length > 0 && `· compacted @${markers.join(",@")}`}</span>
      </div>
    </div>
  );
}
