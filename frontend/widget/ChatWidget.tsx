import { useEffect, useState } from "react";

interface HistoryItem {
  id: string;
  sender: string;
  text: string | null;
}

interface History {
  items: HistoryItem[];
  handoff: boolean;
}

function visitorId() {
  const key = "socialpilot-visitor";
  const existing = window.localStorage.getItem(key);
  if (existing) return existing;
  const created = crypto.randomUUID();
  window.localStorage.setItem(key, created);
  return created;
}

export default function ChatWidget({ channelId, token }: { channelId: string; token: string }) {
  const [visitor] = useState(visitorId);
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [handoff, setHandoff] = useState(false);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    const response = await fetch(
      `/api/channels/webchat/${channelId}/messages?visitor_id=${encodeURIComponent(visitor)}`,
      { headers: { "X-Widget-Token": token } },
    );
    if (!response.ok) {
      setError("This chat is not available.");
      return;
    }
    const body = (await response.json()) as History;
    setItems(body.items);
    setHandoff(body.handoff);
  }

  useEffect(() => {
    void load();
    // The visitor id and channel are fixed for this page.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channelId, token, visitor]);

  async function send() {
    const message = text.trim();
    if (!message || sending) return;
    setSending(true);
    setError(null);
    try {
      const response = await fetch(`/api/channels/webchat/${channelId}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Widget-Token": token },
        body: JSON.stringify({
          visitor_id: visitor,
          message_id: crypto.randomUUID(),
          text: message,
        }),
      });
      if (!response.ok) {
        setError("The message could not be delivered to the team.");
        return;
      }
      setText("");
      await load();
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="flex h-screen flex-col bg-white text-slate-900">
      <header className="border-b border-slate-200 px-4 py-3">
        <p className="text-sm font-semibold">Chat</p>
        <p className="text-xs text-slate-500">
          {handoff ? "A teammate has this conversation." : "A person reviews replies before they are sent."}
        </p>
      </header>
      <ul className="flex-1 space-y-2 overflow-y-auto px-4 py-3">
        {items.map((item) => (
          <li
            key={item.id}
            className={`max-w-[85%] rounded-lg px-3 py-2 text-sm ${item.sender === "customer" ? "ml-auto bg-brand-600 text-white" : "bg-slate-100"}`}
          >
            {item.text}
          </li>
        ))}
        {sending && <li className="text-xs text-slate-400">Sending…</li>}
      </ul>
      {error && <p className="px-4 text-xs text-red-600">{error}</p>}
      <form
        className="flex gap-2 border-t border-slate-200 p-3"
        onSubmit={(event) => {
          event.preventDefault();
          void send();
        }}
      >
        <input
          value={text}
          onChange={(event) => setText(event.target.value)}
          placeholder="Write a message"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm"
        />
        <button
          type="submit"
          disabled={sending || text.trim().length === 0}
          className="rounded-lg bg-brand-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-60"
        >
          Send
        </button>
      </form>
    </div>
  );
}
