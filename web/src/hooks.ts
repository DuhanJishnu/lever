import { useEffect, useRef, useState } from "react";
import { api, Event } from "./api";

/** Live event feed: initial fetch, then SSE append by seq (deduped). */
export function useSessionEvents(sid: string | null, live: boolean) {
  const [events, setEvents] = useState<Event[]>([]);
  const seen = useRef(new Set<number>());

  useEffect(() => {
    if (!sid) return;
    seen.current = new Set();
    setEvents([]);
    let stop = false;
    api.getEvents(sid).then((evs) => {
      if (stop) return;
      for (const e of evs) seen.current.add(e.seq);
      setEvents(evs);
    });
    if (!live) return () => { stop = true; };
    const src = new EventSource(`/api/sessions/${sid}/stream`);
    src.onmessage = (msg) => {
      if (stop) return;
      try {
        const e = JSON.parse(msg.data) as Event;
        if (seen.current.has(e.seq)) return;
        seen.current.add(e.seq);
        setEvents((prev) => [...prev, e].sort((a, b) => a.seq - b.seq));
      } catch { /* partial chunk */ }
    };
    return () => {
      stop = true;
      src.close();
    };
  }, [sid, live]);

  return events;
}
