import { useState } from "react";
import { EvalPage } from "./components/EvalPage";
import { IDE } from "./components/RunView";
import { SessionsPage } from "./components/SessionsPage";
import "./index.css";

type Tab = "run" | "sessions" | "evals";

export default function App() {
  const [tab, setTab] = useState<Tab>("run");
  const [activeSid, setActiveSid] = useState<string | null>(null);

  return (
    <div className="mx-auto max-w-7xl p-4">
      <header className="mb-4 flex items-center gap-4">
        <h1 className="text-xl font-bold">Lever <span className="text-sm font-normal text-slate-400">harness console</span></h1>
        <nav className="flex gap-1 text-sm">
          {(["run", "sessions", "evals"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-3 py-1.5 capitalize ${tab === t ? "bg-slate-700" : "hover:bg-slate-800"}`}>
              {t}
            </button>
          ))}
        </nav>
      </header>
      {tab === "run" && <IDE sid={activeSid} onSession={setActiveSid} />}
      {tab === "sessions" && (
        <SessionsPage onOpen={(id) => { setActiveSid(id); setTab("run"); }} />
      )}
      {tab === "evals" && <EvalPage />}
    </div>
  );
}
