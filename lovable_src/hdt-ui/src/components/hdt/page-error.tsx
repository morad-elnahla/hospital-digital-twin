import { useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { useApp } from "@/lib/app-state";

/** Error inside one page: the menu stays, the real reason is shown, and retry re-renders the page. */
export function PageError({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  const { lang } = useApp();
  console.error(error);
  const ar = lang === "ar";
  return (
    <div className="mx-auto mt-16 max-w-lg rounded-2xl border bg-card p-6 text-center shadow-sm">
      <span className="mx-auto grid size-11 place-items-center rounded-full bg-destructive/10 text-destructive">
        <AlertTriangle className="size-5" />
      </span>
      <h2 className="mt-3 text-base font-semibold">{ar ? "حصلت مشكلة في عرض الصفحة دي" : "This page hit a problem"}</h2>
      <p className="mt-1 text-sm text-muted-foreground" dir="auto">{String((error as any)?.message ?? error)}</p>
      <button
        onClick={() => { router.invalidate(); reset(); }}
        className="bg-brand mt-4 inline-flex items-center gap-1.5 rounded-xl px-4 py-2 text-sm text-primary-foreground"
      >
        <RotateCcw className="size-4" /> {ar ? "حاول تاني" : "Try again"}
      </button>
    </div>
  );
}
