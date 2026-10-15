import { useEffect, useState } from "react";
import { api } from "../api";

/** Unified-diff renderer (green/red), fetched from the session workspace. */
export function DiffView({ sid, refreshKey }: { sid: string; refreshKey: number }) {
  const [diff, setDiff] = useState<string | null>(null);
  useEffect(() => {
    setDiff(null);
    api.getDiff(sid).then((d) => setDiff(d.diff)).catch(() => setDiff("(no workspace yet)"));
  }, [sid, refreshKey]);

  if (diff === null) return <div className="text-sm text-slate-500">loading diff…</div>;
  if (!diff.trim()) return <div className="text-sm text-slate-500">no changes yet</div>;
  return (
    <pre className="max-h-96 overflow-auto rounded bg-black/50 p-3 font-mono text-xs leading-5">
      {diff.split("\n").map((line, i) => (
        <div
          key={i}
          className={
            line.startsWith("+") && !line.startsWith("+++")
              ? "bg-emerald-900/40 text-emerald-200"
              : line.startsWith("-") && !line.startsWith("---")
                ? "bg-red-900/40 text-red-200"
                : line.startsWith("@@")
                  ? "text-sky-300"
                  : "text-slate-400"
          }>
          {line}
        </div>
      ))}
    </pre>
  );
}
