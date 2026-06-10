import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { MessageCircle, X, Send, Sparkles, Loader2 } from "lucide-react";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

const GREETING = {
  role: "assistant",
  text: "Hi! 👋 I'm the InvoiceParsed assistant. Ask me about features, pricing, supported files, exports, or how it works.",
};

const SUGGESTIONS = ["How much does it cost?", "What files can I upload?", "Do you support receipts?", "How does it work?"];

/** Floating support assistant (bottom-right). Answers from the local KB via /api/chat. */
export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([GREETING]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, open, loading]);

  async function send(text) {
    const q = (text ?? input).trim();
    if (!q || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: q }]);
    setLoading(true);
    try {
      const { data } = await api.post("/api/chat", { message: q });
      setMessages((m) => [...m, { role: "assistant", text: data.reply, intent: data.intent }]);
    } catch {
      setMessages((m) => [...m, {
        role: "assistant",
        text: "Sorry, I couldn't reach the assistant right now.",
        intent: "fallback",
      }]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      {/* Launcher */}
      <button
        onClick={() => setOpen((o) => !o)}
        aria-label={open ? "Close chat" : "Open chat"}
        className="fixed bottom-5 right-5 z-[60] grid h-14 w-14 place-items-center rounded-full bg-brand-gradient text-white shadow-glow transition-transform hover:scale-105"
      >
        {open ? <X size={22} /> : <MessageCircle size={24} />}
      </button>

      {open && (
        <div className="fixed bottom-24 right-5 z-[60] flex h-[min(560px,calc(100vh-7rem))] w-[min(380px,calc(100vw-2.5rem))] flex-col overflow-hidden rounded-2xl border border-white/10 bg-ink-900 shadow-glow">
          {/* Header */}
          <div className="flex items-center gap-2.5 border-b border-white/[0.08] bg-white/[0.02] px-4 py-3">
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-gradient text-white">
              <Sparkles size={16} />
            </span>
            <div className="min-w-0">
              <div className="text-sm font-semibold text-white">InvoiceParsed assistant</div>
              <div className="text-[11px] text-slate-500">Ask about features, pricing & more</div>
            </div>
          </div>

          {/* Messages */}
          <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
            {messages.map((m, i) => (
              <div key={i} className={cn("flex flex-col", m.role === "user" ? "items-end" : "items-start")}>
                <div
                  className={cn(
                    "max-w-[85%] whitespace-pre-wrap rounded-2xl px-3.5 py-2.5 text-sm leading-relaxed",
                    m.role === "user"
                      ? "bg-brand-500/90 text-white"
                      : "bg-white/[0.06] text-slate-200",
                  )}
                >
                  {m.text}
                </div>
                {m.role === "assistant" && (m.intent === "fallback" || m.intent === "contact") && (
                  <Link
                    to="/contact"
                    onClick={() => setOpen(false)}
                    className="mt-1.5 inline-flex items-center gap-1 rounded-lg border border-brand-400/30 bg-brand-500/10 px-2.5 py-1 text-xs font-medium text-brand-200 transition-colors hover:bg-brand-500/20"
                  >
                    Contact us →
                  </Link>
                )}
              </div>
            ))}

            {messages.length === 1 && (
              <div className="flex flex-wrap gap-2 pt-1">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s}
                    onClick={() => send(s)}
                    className="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-white/[0.07] hover:text-white"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {loading && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-white/[0.06] px-3.5 py-2.5 text-slate-400">
                  <Loader2 size={16} className="animate-spin" />
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={(e) => { e.preventDefault(); send(); }}
            className="border-t border-white/[0.08] p-3"
          >
            <div className="flex items-center gap-2">
              <input
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Ask a question…"
                className="h-10 flex-1 rounded-xl border border-white/10 bg-ink-950/60 px-3.5 text-sm text-white placeholder:text-slate-600 outline-none focus:border-brand-400/60"
              />
              <button
                type="submit"
                disabled={loading || !input.trim()}
                className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-brand-gradient text-white disabled:opacity-40"
              >
                <Send size={16} />
              </button>
            </div>
            <p className="mt-2 text-center text-[11px] text-slate-600">
              Need a human?{" "}
              <Link to="/contact" className="text-brand-300 hover:text-brand-200" onClick={() => setOpen(false)}>
                Contact us
              </Link>
            </p>
          </form>
        </div>
      )}
    </>
  );
}
