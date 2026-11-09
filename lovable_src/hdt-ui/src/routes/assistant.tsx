import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useRef, useState } from "react";
import { Bot, Send, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";
import { api } from "@/lib/api";
import { useApp, useHdt } from "@/lib/app-state";
import { cn } from "@/lib/utils";
import { Empty, PageHead, Panel } from "@/components/hdt/kit";

export const Route = createFileRoute("/assistant")({
  head: () => ({
    meta: [
      { title: "Assistant · Hospital Digital Twin" },
      { name: "description", content: "Ask questions about hospital operations, answered from the data pack with evidence." },
      { property: "og:title", content: "Hospital operations assistant" },
      { property: "og:description", content: "Evidence-backed answers about beds, staff, ER and OR." },
    ],
  }),
  component: Assistant,
});

type Msg = { role: string; text: string; evidence?: any[]; suggestions?: string[]; notes?: string[]; validation_failures?: any[]; fallback?: string; mode?: string };

function Assistant() {
  const { t, asOf, lang, mode } = useApp();
  const hist = useHdt<{ history: Msg[] }>("assistant", { scoped: false });
  const [chat, setChat] = useState<Msg[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (hist.data?.history) {
      const h = Array.isArray(hist.data.history) ? hist.data.history : [];
      setChat(h.map((m: any) => ({ role: String(m?.role ?? "assistant"), text: str(m?.text ?? m?.content) })));
    }
  }, [hist.data]);
  // Braces matter: newer Chrome returns a Promise from scrollIntoView, and React
  // would treat a returned value as the effect cleanup ("destroy is not a function").
  useEffect(() => {
    end.current?.scrollIntoView({ behavior: "smooth" });
  }, [chat]);
  const ask = async (q: string) => {
    if (!q.trim()) return;
    setChat((c) => [...c, { role: "user", text: q }]);
    setText("");
    setBusy(true);
    try {
      const r = await api<any>("/api/assistant", { message: q, as_of: asOf, language: lang });
      setChat((c) => [...c, { role: "assistant", text: str(r?.answer), evidence: Array.isArray(r?.evidence) ? r.evidence : [], suggestions: Array.isArray(r?.suggestions) ? r.suggestions.map(str) : [], notes: Array.isArray(r?.notes) ? r.notes.map(str) : [], validation_failures: Array.isArray(r?.validation_failures) ? r.validation_failures : [], fallback: r?.fallback, mode: r?.mode }]);
    } catch (e: any) {
      toast.error(str(e?.message));
      setChat((c) => c.slice(0, -1));
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="mx-auto max-w-4xl">
      <PageHead title={t("nav_assistant")} sub={t("assistant_sub")} />
      <Panel prov="agent" title={t("conversation")} right={
        <button onClick={async () => { try { await api("/api/assistant/reset", {}); setChat([]); } catch (e: any) { toast.error(e.message); } }} className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs hover:bg-muted">
          <Trash2 className="size-3.5" /> {t("clear_chat")}
        </button>
      }>
        <div className="flex h-[55vh] flex-col">
          <div className="flex-1 space-y-3 overflow-y-auto pe-1">
                          {chat.map((m, i) => (
                <div key={i} className={cn("flex gap-2.5 animate-in fade-in slide-in-from-bottom-2 duration-300", m.role === "user" && "flex-row-reverse")}>
                  <span className={cn("grid size-8 shrink-0 place-items-center rounded-full", m.role === "user" ? "bg-muted" : "bg-brand text-primary-foreground")}>
                    {m.role === "user" ? <UserRound className="size-4" /> : <Bot className="size-4" />}
                  </span>
                  <div className={cn("max-w-[80%] rounded-2xl px-4 py-2.5 text-sm leading-relaxed whitespace-pre-wrap", m.role === "user" ? "bg-primary text-primary-foreground" : "bg-muted")}>
                    <span dir="auto">{m.text}</span>
                    {m.evidence?.length ? (
                      <div className="mt-2 space-y-1 border-t border-border/60 pt-2 text-xs text-muted-foreground">
                        {m.evidence.map((e: any, j: number) => (
                          <div key={j} dir="auto"><b className="num text-foreground">[{str(e?.id)}]</b> {str(e?.label)}</div>
                        ))}
                      </div>
                    ) : null}
                    {m.notes?.length ? <div className="mt-1 text-xs text-muted-foreground">{m.notes.join(" · ")}</div> : null}
                    {m.fallback === "template" && m.validation_failures?.length ? (
                      <details className="mt-2 rounded-lg border border-warn/30 p-2 text-xs">
                        <summary className="cursor-pointer font-semibold text-warn">{t("llm_claims_rejected", { n: m.validation_failures.length })}</summary>
                        <ul className="mt-2 list-disc space-y-1 ps-5">
                          {m.validation_failures.map((f: any, j: number) => <li key={j} dir="auto"><b>{f.claim || t("claim_without_text")}</b>{f.reason ? ` — ${f.reason}` : ""}</li>)}
                        </ul>
                        <p className="mt-2 text-muted-foreground">{t("template_fallback_shown")}</p>
                      </details>
                    ) : null}
                    {m.suggestions?.length ? (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {m.suggestions.map((s, j) => (
                          <button key={j} onClick={() => ask(s)} className="rounded-full border bg-card px-2.5 py-0.5 text-xs text-foreground hover:bg-primary-soft">{s}</button>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </div>
              ))}
            {busy && <div className="flex gap-1 ps-11">{[0, 1, 2].map((i) => <span key={i} className="size-2 animate-bounce rounded-full bg-primary/50" style={{ animationDelay: `${i * 0.15}s` }} />)}</div>}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); ask(text); }} className="mt-3 flex gap-2">
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder={t("ask_ph")} className="flex-1 rounded-xl border bg-card px-4 py-2.5 text-sm" disabled={!mode} />
            <button disabled={busy || !mode} className="bg-brand grid size-11 place-items-center rounded-xl text-primary-foreground disabled:opacity-50" aria-label={t("send")}>
              <Send className="size-4 rtl:-scale-x-100" />
            </button>
          </form>
        </div>
      </Panel>
    </div>
  );
}

function str(v: unknown): string {
  if (v == null) return "";
  if (typeof v === "string") return v;
  if (typeof v === "number" || typeof v === "boolean") return String(v);
  try { return JSON.stringify(v); } catch { return ""; }
}
