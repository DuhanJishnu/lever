import { useEffect, useState } from "react";
import { api } from "../api";

function norm(s: string) {
  return s.replace(/\r\n/g, "\n");
}

/** File viewer: current content with line numbers, or unified per-file diff. */
export function FileView({ sid, path, showDiff, refreshKey }: {
  sid: string;
  path: string;
  showDiff: boolean;
  refreshKey: number;
}) {
  const [content, setContent] = useState<string | null>(null);
  const [original, setOriginal] = useState<string | null>(null);

  useEffect(() => {
    setContent(null);
    setOriginal(null);
    api.fileContent(sid, path).then((f) => setContent(f.content)).catch(() => setContent("(unreadable)"));
    if (showDiff) {
      api.fileDiff(sid, path).then((d) => setOriginal(d.original)).catch(() => setOriginal(null));
    }
  }, [sid, path, showDiff, refreshKey]);

  if (content === null) return <div className="text-sm text-slate-500">loading…</div>;
  if (showDiff && original !== null && norm(original) !== norm(content)) {
    return <UnifiedDiff original={norm(original)} modified={norm(content)} />;
  }
  if (showDiff) return <div className="text-sm text-slate-500">no changes in this file</div>;
  const lines = norm(content).split("\n");
  return (
    <pre className="overflow-auto rounded bg-black/40 p-2 font-mono text-xs leading-5">
      {lines.map((ln, i) => (
        <div key={i} className="flex">
          <span className="w-10 shrink-0 select-none pr-3 text-right text-slate-600">{i + 1}</span>
          <span className="whitespace-pre-wrap text-slate-200">{ln}</span>
        </div>
      ))}
    </pre>
  );
}

function UnifiedDiff({ original, modified }: { original: string; modified: string }) {
  const a = original.split("\n");
  const b = modified.split("\n");
  const ops = diffLines(a, b);
  return (
    <pre className="overflow-auto rounded bg-black/40 p-2 font-mono text-xs leading-5">
      {ops.map((op, i) => (
        <div key={i} className="flex">
          <span className="w-10 shrink-0 select-none pr-3 text-right text-slate-600">
            {op.a !== null && op.b !== null ? `${op.a + 1}` : op.a !== null ? `${op.a + 1} ` : ` ${op.b !== null ? op.b + 1 : ""}`}
          </span>
          <span className={
            op.kind === "+" ? "bg-emerald-900/40 text-emerald-200" :
            op.kind === "-" ? "bg-red-900/40 text-red-200" : "text-slate-400"}>
            <span className="mr-1 select-none">{op.kind === " " ? " " : op.kind}</span>
            <span className="whitespace-pre-wrap">{op.text}</span>
          </span>
        </div>
      ))}
    </pre>
  );
}

type Op = { kind: "+" | "-" | " "; text: string; a: number | null; b: number | null };

/** Tiny Myers-free LCS diff (fine for small files). */
function diffLines(a: string[], b: string[]): Op[] {
  const n = a.length, m = b.length;
  const dp: number[][] = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
  const ops: Op[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { ops.push({ kind: " ", text: a[i], a: i, b: j }); i++; j++; }
    else if (dp[i + 1][j] >= dp[i][j + 1]) { ops.push({ kind: "-", text: a[i], a: i, b: null }); i++; }
    else { ops.push({ kind: "+", text: b[j], a: null, b: j }); j++; }
  }
  while (i < n) { ops.push({ kind: "-", text: a[i], a: i, b: null }); i++; }
  while (j < m) { ops.push({ kind: "+", text: b[j], a: null, b: j }); j++; }
  return ops;
}
