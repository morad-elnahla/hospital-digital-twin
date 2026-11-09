import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AppProvider } from "@/lib/app-state";
const wrap = (n: ReactNode) => render(<QueryClientProvider client={new QueryClient()}><AppProvider>{n}</AppProvider></QueryClientProvider>);
import { statusLabelKey } from "@/lib/decision-ui";
import { translate } from "@/lib/i18n";
import { DecisionViewBody } from "@/components/hdt/decision-view";

const ar = (k: string, v?: Record<string, string | number>) => translate("ar", k, v);
// ICU ×12: backend closes NO_ACTION with all proposals rejected and 32 unmet.
const icu12Detail = { id: "d1", status: "NO_ACTION", no_action_code: "none.reason.all_rejected", card: { unmet: { ICU: 32 } }, accepted: [], rejected: [] };
const icu12ListItem = { id: "d1", status: "NO_ACTION", no_action_code: "none.reason.all_rejected", unmet: { ICU: 32 } };
const zeroDetail = { id: "d2", status: "NO_ACTION", no_action_code: "none.reason.no_proposals", card: { unmet: {} }, accepted: [], rejected: [] };
const zeroListItem = { id: "d2", status: "NO_ACTION", no_action_code: "none.reason.no_proposals", unmet: { ICU: 0 } };
const SHORT = "عجز متوقع — لا يوجد إجراء آمن متاح";

describe("NO_ACTION title is the same on agents card, decisions list and details", () => {
  it("ICU ×12 (unmet 32) agents card + list title is the shortfall title", () => {
    expect(ar(statusLabelKey(icu12Detail))).toBe(SHORT); // agents result card
    expect(ar(statusLabelKey(icu12ListItem))).toBe(SHORT); // decisions list
  });
  it("ICU ×12 details title is the shortfall title", () => {
    wrap(<DecisionViewBody d={icu12Detail} t={ar} />);
    expect(screen.getByTestId("no-action-title").textContent).toBe(SHORT);
  });
  it("zero shortfall shows لا يلزم إجراء everywhere", () => {
    expect(ar(statusLabelKey(zeroDetail))).toBe("لا يلزم إجراء");
    expect(ar(statusLabelKey(zeroListItem))).toBe("لا يلزم إجراء");
    wrap(<DecisionViewBody d={zeroDetail} t={ar} />);
    expect(screen.getByTestId("no-action-title").textContent).toBe("لا يلزم إجراء");
  });
});
