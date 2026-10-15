import { useEffect, useState } from "react";
import { api } from "../api";

type Cfg = {
  tasks: number;
  pass_at_1: number;
  ci95: [number, number];
  mean_tokens: number;
  mean_steps: number;
  mean_wall_s: number;
  trap_rate: number | null;
  edit_failures: number;
  tool_errors: number;
  n_errors: number;
  stopped_by: Record<string, number>;
};

function Bar({ mean, lo, hi, label }: { mean: number; lo: number; hi: number; label: string }) {
  const x = (v: number) => `${(v * 100).toFixed(0)}%`;
  return (
    <div className="mb-2">
      <div className="mb-0.5 flex justify-between text-xs">
        <span className="font-mono">{label}</span>
        <span className="text-slate-400">{mean.toFixed(2)} [{lo.toFixed(2)}, {hi.toFixed(2)}]</span>
      </div>
      <svg viewBox="0 0 100 8" className="h-3 w-full rounded bg-slate-800" preserveAspectRatio="none">
        <rect x={x(lo)} y="2" width={`${Math.max(0.5, (hi - lo) * 100)}`} height="4" fill="#38bdf8" opacity="0.5" />
        <rect x="0" y="2" width={x(mean)} height="4" fill="#34d399" />
        <line x1={x(mean)} y1="0" x2={x(mean)} y2="8" stroke="#fff" strokeWidth="0.6" />
      </svg>
    </div>
  );
}

export function EvalPage() {
  const [data, setData] = useState<Record<string, Record<string, Cfg>> | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.evalSummary().then(setData).catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="text-sm text-red-300">{err}</div>;
  if (!data) return <div className="text-sm text-slate-500">loading… (run analyze.py --summary-json first)</div>;
  const names = Object.keys(data);
  if (names.length === 0)
    return <div className="text-sm text-slate-500">no summaries yet — run <span className="font-mono">analyze.py --summary-json evals/results/NAME_summary.json</span></div>;

  return (
    <div className="space-y-6">
      {names.map((file) => (
        <div key={file} className="rounded border border-slate-700 p-4">
          <h3 className="mb-3 font-mono text-sm text-slate-300">{file}</h3>
          {Object.entries(data[file]).map(([cfg, s]) => (
            <Bar key={cfg} label={cfg} mean={s.pass_at_1} lo={s.ci95[0]} hi={s.ci95[1]} />
          ))}
          <table className="mt-3 w-full text-xs">
            <thead>
              <tr className="text-left text-slate-400">
                <th>config</th><th>tasks</th><th>pass@1</th><th>tok/run</th>
                <th>steps</th><th>trap</th><th>editfail</th><th>stopped_by</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(data[file]).map(([cfg, s]) => (
                <tr key={cfg} className="border-t border-slate-800 font-mono">
                  <td>{cfg}</td><td>{s.tasks}</td><td>{s.pass_at_1.toFixed(2)}</td>
                  <td>{s.mean_tokens}</td><td>{s.mean_steps}</td>
                  <td>{s.trap_rate ?? "–"}</td><td>{s.edit_failures}</td>
                  <td>{JSON.stringify(s.stopped_by)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ))}
    </div>
  );
}
