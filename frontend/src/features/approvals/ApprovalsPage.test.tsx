import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ApprovalRecord } from "../../api/contracts";
import { ApprovalsPage } from "./ApprovalsPage";

const { pendingApprovals, decideApproval } = vi.hoisted(() => ({ pendingApprovals: vi.fn(), decideApproval: vi.fn() }));
vi.mock("../../api/client", () => ({ api: { approvals: { pending: pendingApprovals, decide: decideApproval } } }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "manager-1", organization_id: "org-1", role: "MANAGER" } }) }));

const approval: ApprovalRecord = {
  id: "approval-1", case_id: "case-1", approval_type: "CASE_COMPLETION", task_id: null, decision: "PENDING",
  decided_by_user_id: null, decided_at: null, comment: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

describe("manager approval queue", () => {
  beforeEach(() => {
    pendingApprovals.mockReset().mockResolvedValue([approval]);
    decideApproval.mockReset();
  });

  it("requires a reason and reports the backend-confirmed decision", async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><MemoryRouter><ApprovalsPage /></MemoryRouter></QueryClientProvider>);

    await user.click(await screen.findByRole("button", { name: "Approve" }));
    const confirm = screen.getByRole("button", { name: "Confirm approval" });
    expect(confirm).toBeDisabled();
    await user.type(screen.getByRole("textbox", { name: "Decision comment" }), "Evidence checked against the approved process.");
    expect(confirm).toBeEnabled();
    decideApproval.mockResolvedValue({ ...approval, decision: "APPROVED", comment: "Evidence checked against the approved process." });
    await user.click(confirm);

    expect(await screen.findByText("Approved decision was recorded by the backend.")).toBeInTheDocument();
    expect(decideApproval).toHaveBeenCalledWith("approval-1", { decision: "APPROVED", comment: "Evidence checked against the approved process." });
  });
});
