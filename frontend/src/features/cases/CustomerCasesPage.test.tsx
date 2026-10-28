import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { CustomerCasesPage } from "./CustomerCasesPage";

const { listMine, createMine, customerOptions } = vi.hoisted(() => ({ listMine: vi.fn(), createMine: vi.fn(), customerOptions: vi.fn() }));
vi.mock("../../api/client", () => ({ api: { cases: { mine: listMine, createMine }, processes: { customerOptions } } }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "customer-1", organization_id: "org-1", role: "CUSTOMER" } }) }));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={queryClient}><MemoryRouter><CustomerCasesPage /></MemoryRouter></QueryClientProvider>);
}

describe("customer case register", () => {
  beforeEach(() => {
    listMine.mockReset().mockResolvedValue([]);
    createMine.mockReset();
    customerOptions.mockReset().mockResolvedValue([
      { process_id: "process-1", process_version_id: "version-1", name: "Customer intake", description: null },
    ]);
  });

  it("creates a case from an active customer process option", async () => {
    createMine.mockResolvedValue({ id: "case-1", case_number: "CASE-1" });
    const user = userEvent.setup();
    renderPage();

    await screen.findByText("No cases yet");
    await user.click(screen.getAllByRole("button", { name: "Start a case" })[0]!);
    await user.type(await screen.findByLabelText("Case title"), "Invoice review");
    await user.selectOptions(await screen.findByLabelText("Process"), "version-1");
    await user.click(screen.getByRole("button", { name: "Create case" }));

    expect(await screen.findByText("Case CASE-1 was created.")).toBeInTheDocument();
    expect(createMine).toHaveBeenCalledWith({ title: "Invoice review", process_version_id: "version-1" });
  });

  it("shows only the customer case API result", async () => {
    listMine.mockResolvedValue([{
      id: "case-2", case_number: "CASE-2", title: "My request", status: "OPEN", current_stage_name: null,
      created_at: "2026-10-10T00:00:00Z", updated_at: "2026-10-10T00:00:00Z", documents: [],
      document_requests: [{ code: "INVOICE", name: "Invoice", description: null, status: "REQUESTED" }],
    }]);
    renderPage();

    expect(await screen.findByText("CASE-2")).toBeInTheDocument();
    expect(screen.getByText(/More needed/)).toBeInTheDocument();
    expect(listMine).toHaveBeenCalledOnce();
  });
});
