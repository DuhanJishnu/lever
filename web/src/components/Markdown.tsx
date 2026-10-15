/** Tiny markdown renderer: fences, inline code, bold, lists. No deps. */

export function Markdown({ text }: { text: string }) {
  const blocks: React.ReactNode[] = [];
  const parts = text.split(/```/);
  for (let i = 0; i < parts.length; i++) {
    if (i % 2 === 1) {
      const nl = parts[i].indexOf("\n");
      const body = nl >= 0 ? parts[i].slice(nl + 1) : parts[i];
      const lang = nl > 0 ? parts[i].slice(0, nl).trim() : "";
      blocks.push(
        <pre key={i} className="my-1 overflow-auto rounded bg-black/50 p-2 font-mono text-xs">
          {lang && <div className="mb-1 text-[10px] text-slate-500">{lang}</div>}
          {body.replace(/\n$/, "")}
        </pre>,
      );
    } else {
      blocks.push(
        <div key={i} className="whitespace-pre-wrap">
          <Inline text={parts[i]} />
        </div>,
      );
    }
  }
  return <>{blocks}</>;
}

function Inline({ text }: { text: string }) {
  // inline `code` first, then **bold** inside the rest
  const segs = text.split(/(`[^`]+`)/g);
  return (
    <>
      {segs.map((s, i) =>
        s.startsWith("`") && s.endsWith("`") && s.length > 1 ? (
          <code key={i} className="rounded bg-black/50 px-1 font-mono text-[13px] text-amber-100">
            {s.slice(1, -1)}
          </code>
        ) : (
          <Bold key={i} text={s} />
        ),
      )}
    </>
  );
}

function Bold({ text }: { text: string }) {
  const segs = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {segs.map((s, i) =>
        s.startsWith("**") && s.endsWith("**") && s.length > 4 ? (
          <strong key={i}>{s.slice(2, -2)}</strong>
        ) : (
          <span key={i}>{s}</span>
        ),
      )}
    </>
  );
}
