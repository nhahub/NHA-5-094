import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CustomerCaseWorkspacePage } from "./CustomerCaseWorkspacePage";

const { getMine, uploadMine } = vi.hoisted(() => ({ getMine: vi.fn(), uploadMine: vi.fn() }));
vi.mock("../../api/client", () => ({ api: { cases: { mineById: getMine }, documents: { uploadMine } } }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "customer-1", organization_id: "org-1", role: "CUSTOMER" } }) }));

const customerCase = {
  id: "case-1", case_number: "CASE-1", title: "Invoice request", status: "OPEN", current_stage_name: "Intake",
  created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z", documents: [],
  document_requests: [{ code: "INVOICE", name: "Invoice", description: "Upload a signed invoice.", status: "REQUESTED" as const }],
};

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/customer/cases/case-1"]}>
        <Routes><Route path="/customer/cases/:caseId" element={<CustomerCaseWorkspacePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("customer case workspace", () => {
  beforeEach(() => {
    getMine.mockReset().mockResolvedValue(customerCase);
    uploadMine.mockReset().mockResolvedValue({ document: { name: "invoice.pdf" }, duplicate: false });
  });

  it("shows a requested document and uploads it through the customer-scoped API", async () => {
    const user = userEvent.setup();
    renderPage();

    const file = new File(["%PDF-1.7 customer test"], "invoice.pdf", { type: "application/pdf" });
    await user.upload(await screen.findByLabelText("Choose Invoice file"), file);
    await user.click(screen.getByRole("button", { name: "Upload Invoice" }));

    expect(await screen.findByText("invoice.pdf was uploaded.")).toBeInTheDocument();
    expect(uploadMine).toHaveBeenCalledWith("case-1", "INVOICE", file);
  });
});
