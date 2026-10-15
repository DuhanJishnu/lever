import { useEffect, useRef, useState } from "react";
import { api, FileEntry, ProviderInfo } from "../api";

/** Follow-up prompt: @-file mentions from the workspace tree. */
export function PromptBox({ sid, disabled, onSend }: {
  sid: string | null;
  disabled: boolean;
  onSend: (content: string, files: string[]) => void;
}) {
  const [text, setText] = useState("");
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [attach, setAttach] = useState<string[]>([]);
  const [suggest, setSuggest] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const boxRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (!sid) return;
    api.files(sid).then(setFiles).catch(() => setFiles([]));
  }, [sid]);

  function onChange(v: string) {
    setText(v);
    const m = v.match(/@([\w./-]*)$/);
    if (!m) {
      setSuggest([]);
      return;
    }
    const q = m[1].toLowerCase();
    setSuggest(
      files.filter((f) => f.type === "file" && f.path.toLowerCase().includes(q))
        .slice(0, 8).map((f) => f.path));
  }

  function pick(path: string) {
    if (!attach.includes(path)) setAttach([...attach, path]);
    setText(text.replace(/@[\w./-]*$/, `@${path.split("/").pop()} `));
    setSuggest([]);
    boxRef.current?.focus();
  }

  async function send() {
    if (!text.trim() || busy) return;
    setBusy(true);
    try {
      onSend(text, attach);
      setText("");
      setAttach([]);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded border border-slate-700 bg-slate-800/40 p-3">
      {attach.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-1">
          {attach.map((a) => (
            <span key={a} className="rounded bg-sky-900 px-2 py-0.5 font-mono text-xs text-sky-200">
              @{a.split("/").pop()}
              <button onClick={() => setAttach(attach.filter((x) => x !== a))} className="ml-1 text-slate-400">×</button>
            </span>
          ))}
        </div>
      )}
      <div className="relative">
        <textarea
          ref={boxRef}
          value={text}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) send(); }}
          rows={3}
          placeholder="Follow-up… @ to attach a file, Ctrl+Enter to send"
          className="w-full rounded bg-slate-900 px-2 py-1.5 text-sm" />
        {suggest.length > 0 && (
          <div className="absolute bottom-full left-0 z-10 mb-1 w-72 rounded border border-slate-600 bg-slate-900 shadow-lg">
            {suggest.map((s) => (
              <button key={s} onClick={() => pick(s)}
                className="block w-full truncate px-2 py-1 text-left font-mono text-xs hover:bg-slate-700">
                {s}
              </button>
            ))}
          </div>
        )}
      </div>
      <div className="mt-2 flex justify-end">
        <button disabled={disabled || busy || !text.trim()} onClick={send}
          className="rounded bg-emerald-600 px-4 py-1.5 text-sm hover:bg-emerald-500 disabled:opacity-50">
          Send
        </button>
      </div>
    </div>
  );
}

/** First-run bar: repo + task + provider/model picker. */
export function NewTaskBar({ onRun }: {
  onRun: (repo: string, task: string, provider: string, model: string) => void;
}) {
  const [repo, setRepo] = useState("D:/Lever/bug-repo");
  const [task, setTask] = useState("Read add.py, find the bug, fix it.");
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [provider, setProvider] = useState("auto");
  const [model, setModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  useEffect(() => {
    api.providers().then(setProviders).catch(() => setProviders([]));
  }, []);

  async function submit() {
    setBusy(true);
    setErr("");
    try {
      await onRun(repo, task, provider, model);
    } catch (e) {
      setErr(String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-4 rounded border border-slate-700 bg-slate-800/40 p-3">
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-[1fr_2fr_auto]">
        <input value={repo} onChange={(e) => setRepo(e.target.value)}
          className="rounded bg-slate-900 px-2 py-1.5 font-mono text-sm" placeholder="repo path" />
        <input value={task} onChange={(e) => setTask(e.target.value)}
          className="rounded bg-slate-900 px-2 py-1.5 text-sm" placeholder="task" />
        <div className="flex gap-2">
          <select value={provider} onChange={(e) => setProvider(e.target.value)}
            title="provider"
            className="rounded bg-slate-900 px-2 py-1.5 text-sm">
            {providers.map((p) => (
              <option key={p.id} value={p.id} disabled={!p.configured}>
                {p.id}{p.model ? ` · ${p.model}` : ""}{p.configured ? "" : " (off)"} · {p.cost}
              </option>
            ))}
          </select>
          {provider === "gemini" && (
            <input value={model} onChange={(e) => setModel(e.target.value)}
              placeholder="model override"
              title="blank = LEVER_MODEL env"
              className="w-40 rounded bg-slate-900 px-2 py-1.5 font-mono text-sm" />
          )}
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
