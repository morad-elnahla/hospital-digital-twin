import { useEffect, useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";

export function clampDemandMultiplier(value: number) {
  return Number.isFinite(value) && value >= 0.1 && value <= 50;
}

export function stepDemandMultiplier(value: number, direction: -1 | 1, fine = false) {
  const delta = fine ? 0.01 : 0.1;
  return Math.min(50, Math.max(0.1, Math.round((value + direction * delta) * 100) / 100));
}

export function DemandMultiplierControl({ value, onChange, label, lang, t }: {
  value: number; onChange: (n: number) => void; label: string; lang: "en" | "ar";
  t: (key: string) => string;
}) {
  const [draft, setDraft] = useState(String(value));
  const [invalid, setInvalid] = useState(false);
  useEffect(() => { setDraft(String(value)); setInvalid(false); }, [value]);
  const commit = () => {
    const parsed = Number(draft);
    if (clampDemandMultiplier(parsed)) { onChange(parsed); setInvalid(false); }
    else { setDraft(String(value)); setInvalid(true); }
  };
  const bump = (direction: -1 | 1, fine = false) => onChange(stepDemandMultiplier(value, direction, fine));
  return <div className="min-w-56 flex-1 space-y-1 text-xs font-semibold">
    <div className="flex justify-between text-muted-foreground"><span>{label}</span><span className="num text-base text-foreground" dir="ltr">×{value}</span></div>
    <input aria-label={label} type="range" dir="ltr" min={0.1} max={50} step={0.01} value={value}
      onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[var(--primary)]" />
    <div className="flex items-center gap-1" dir={lang === "ar" ? "rtl" : "ltr"}>
      <button type="button" aria-label={t("multiplier_step_down")} title={`${t("multiplier_step_down")} · ${t("step_hint")}`}
        onClick={() => bump(-1)} className="grid size-9 place-items-center rounded-lg border bg-card"><ChevronDown className="size-4" /></button>
      <input aria-label={label} type="number" inputMode="decimal" min={0.1} max={50} step={0.01} value={draft} dir="ltr"
        aria-invalid={invalid} onChange={(e) => setDraft(e.target.value)} onBlur={commit}
        onKeyDown={(e) => { if (e.key === "ArrowUp" || e.key === "ArrowDown") { e.preventDefault(); bump(e.key === "ArrowUp" ? 1 : -1, e.shiftKey); } }}
        className="num w-28 rounded-lg border bg-card px-3 py-2 text-center text-sm" />
      <button type="button" aria-label={t("multiplier_step_up")} title={`${t("multiplier_step_up")} · ${t("step_hint_shift")}`}
        onClick={() => bump(1)} className="grid size-9 place-items-center rounded-lg border bg-card"><ChevronUp className="size-4" /></button>
      {invalid && <span className="text-bad" role="alert">{t("multiplier_invalid")}</span>}
    </div>
  </div>;
}
