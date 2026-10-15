import { useEffect, useState } from "react";
import { api, FileEntry } from "../api";

/** Workspace file tree with changed-file badges. */
export function FileExplorer({ sid, changed, openPath, onOpen }: {
  sid: string;
  changed: Set<string>;
  openPath: string | null;
  onOpen: (path: string) => void;
}) {
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [filter, setFilter] = useState("");
  const [tick, setTick] = useState(0);

  useEffect(() => {
    api.files(sid).then(setFiles).catch(() => setFiles([]));
  }, [sid, tick]);

  const shown = files.filter((f) =>
    f.type === "dir" || f.path.toLowerCase().includes(filter.toLowerCase()));

  return (
    <div className="flex h-full flex-col">
      <div className="mb-1 flex items-center gap-2">
        <input
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter files"
          className="w-full rounded bg-slate-900 px-2 py-1 text-xs" />
        <button onClick={() => setTick((n) => n + 1)} title="refresh"
          className="rounded bg-slate-800 px-2 py-1 text-xs hover:bg-slate-700">⟳</button>
      </div>
      <div className="flex-1 overflow-auto text-xs">
        {shown.map((f) => f.type === "dir" ? (
          <div key={f.path} className="px-1 py-0.5 text-slate-500">
            <span className="mr-1">▸</span>{f.path}
          </div>
        ) : (
          <button
            key={f.path}
            onClick={() => onOpen(f.path)}
            className={`flex w-full items-center gap-1 rounded px-1 py-0.5 text-left font-mono hover:bg-slate-800 ${
              openPath === f.path ? "bg-slate-800 text-emerald-200" : "text-slate-300"}`}>
            <span className="truncate">{f.path.split("/").pop()}</span>
            <span className="truncate text-slate-600">{dirOf(f.path)}</span>
            {changed.has(f.path) && <span className="ml-auto text-amber-300" title="modified">●</span>}
          </button>
        ))}
        {shown.length === 0 && <div className="text-slate-500">no files</div>}
      </div>
    </div>
  );
}

function dirOf(path: string) {
  const i = path.lastIndexOf("/");
  return i < 0 ? "" : path.slice(0, i);
}
