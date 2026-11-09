import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { DecisionViewBody } from "@/components/hdt/decision-view";
import { AppProvider } from "@/lib/app-state";
import { noActionKind, runCreatedMessage } from "@/lib/decision-ui";
import { translate, type Lang } from "@/lib/i18n";

const t = (lang: Lang) => (k: string, v?: Record<string, string | number>) => translate(lang, k, v);

// Panel chips read the app context; the provider's mode detection just fails offline in jsdom.
function wrap(node: ReactNode) {
  return render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <AppProvider>{node}</AppProvider>
    </QueryClientProvider>,
  );
}

const base = {
  id: "d1",
  card: { critical_bottleneck: "ICU", waiting_minutes_saved: 12, confidence: "high" },
  accepted: [],
  rejected: [],
  reports: [],
};

describe("NO_ACTION decisions", () => {
  it("no_proposals: shows the no-need message, no rejection claim, no approval wording", () => {
    const d = { ...base, status: "NO_ACTION", no_action_code: "none.reason.no_proposals", no_action_reason: "لا يوجد عجز متوقع." };
    wrap(<DecisionViewBody d={d} t={t("ar")} />);

    expect(screen.getByTestId("no-action-no_proposals")).toHaveTextContent("لا يلزم إجراء — لا يوجد عجز مؤكد.");
    expect(screen.queryByTestId("no-action-all_rejected")).not.toBeInTheDocument();
    expect(screen.queryByText(/انتظار الاعتماد/)).not.toBeInTheDocument();
  });

  it("all_rejected: shows the need, the shortfall, rejection reasons and warnings — and no approval wording", () => {
    const d = {
      ...base,
      status: "NO_ACTION",
      no_action_code: "none.reason.all_rejected",
      no_action_reason: "رفض مقترحان بسبب القيود الصارمة.",
      card: { ...base.card, unmet: { ICU: 4 }, warnings: ["نسبة التمريض ستتجاوز الحد الآمن في العناية المركزة"] },
      rejected: [{ proposal: { id: "p1", title: "Add beds" }, reasons: ["nurse ratio exceeded"] }],
    };
    wrap(<DecisionViewBody d={d} t={t("ar")} />);

    const banner = screen.getByTestId("no-action-all-rejected");
    expect(banner).toHaveTextContent("عجز متوقع — لا يوجد إجراء آمن متاح");
    expect(banner).toHaveTextContent("ICU: 4");
    expect(screen.getByTestId("safety-warnings")).toHaveTextContent("نسبة التمريض ستتجاوز الحد الآمن");
    expect(screen.getByTestId("rejection-reasons")).toHaveTextContent("nurse ratio exceeded");
    expect(screen.queryByText(/انتظار الاعتماد/)).not.toBeInTheDocument();
  });

  it("advisory: is distinguished from an applicable action", () => {
    const d = { ...base, status: "NO_ACTION", no_action_code: "none.reason.advisory" };
    wrap(<DecisionViewBody d={d} t={t("ar")} />);

    expect(screen.getByTestId("no-action-advisory")).toHaveTextContent("توصية استشارية فقط");
  });

  it("a PENDING decision shows no NO_ACTION banner", () => {
    wrap(<DecisionViewBody d={{ ...base, status: "PENDING" }} t={t("ar")} />);

    expect(screen.queryByTestId(/no-action-/)).not.toBeInTheDocument();
  });
});

describe("ESCALATE decisions", () => {
  it("shows the residual and help text instead of a no-action-required message", () => {
    const d = { ...base, status: "ESCALATE", scenario_core: { bed_demand: {
      ICU: { residual_shortfall_beds: 101, residual_message: { code: "unresolved_shortfall", params: { beds: 101 } },
        what_would_help: [{ code: "manager_escalation", params: { beds: 101 } }] },
    } } };
    wrap(<DecisionViewBody d={d} t={t("ar")} />);
    const banner = screen.getByTestId("decision-escalation");
    expect(banner).toHaveTextContent("تصعيد");
    expect(banner).toHaveTextContent("101");
    expect(banner).not.toHaveTextContent("ما الذي قد يساعد");
    expect(banner).not.toHaveTextContent("لا يلزم إجراء");
  });
});

describe("runCreatedMessage", () => {
  it("PENDING run says the decision awaits approval and shows the real status", () => {
    const msg = runCreatedMessage({ status: "PENDING" }, "ar");
    expect(msg).toContain("تم إنشاء القرار وهو في انتظار الاعتماد");
    expect(msg).toContain("معلّقة");
  });

  it("NO_ACTION run shows the backend note, never the approval wording", () => {
    const msg = runCreatedMessage({ status: "NO_ACTION", note: "لا يوجد عجز متوقع." }, "ar");
    expect(msg).toBe("لا يوجد عجز متوقع.");
    expect(msg).not.toContain("انتظار الاعتماد");
  });
});

describe("Arabic labels", () => {
  it("translates the shortfall label instead of the literal 'Shortfall'", () => {
    expect(translate("ar", "shortfall_beds")).toBe("العجز في الأسرّة");
    expect(translate("ar", "shortfall_beds")).not.toContain("Shortfall");
  });

  it("labels pack_reference waits as historical reference, not simulation", () => {
    expect(translate("ar", "pack_ref_hist")).toContain("تاريخية");
    expect(translate("ar", "pack_ref_hist_sub")).toContain("ليست ناتجة عن سيناريو المحاكاة");
    expect(translate("en", "pack_ref_hist_sub")).toContain("not produced by the current simulation");
  });
});

describe("noActionKind", () => {
  it("reads only the backend code, never the status text", () => {
    expect(noActionKind({ status: "NO_ACTION", no_action_code: "none.reason.all_rejected" })).toBe("all_rejected");
    expect(noActionKind({ status: "NO_ACTION" })).toBeNull();
    expect(noActionKind({ status: "PENDING" })).toBeNull();
  });
});
