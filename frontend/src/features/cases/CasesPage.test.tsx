import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { CaseRecord, UserRead } from "../../api/contracts";
import { CasesPage } from "./CasesPage";

const { listCases } = vi.hoisted(() => ({ listCases: vi.fn() }));
vi.mock("../../api/client", () => ({ api: { cases: { list: listCases } } }));
vi.mock("../../auth/AuthContext", () => ({ useAuth: () => ({ user: { id: "user-1", organization_id: "org-1", role: "EMPLOYEE" } }) }));

const user: UserRead = {
  id: "user-1", organization_id: "org-1", email: "operator@example.test", full_name: "Example Operator",
  role: "EMPLOYEE", is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

function makeCase(index: number): CaseRecord {
  return {
    id: `case-${index}`, organization_id: user.organization_id, process_id: "process-1", process_version_id: "version-1",
    case_number: `VER-${String(index).padStart(4, "0")}`, title: `Business case ${index}`, case_metadata: {}, status: "IN_PROGRESS",
    current_stage_id: null, created_by: user.id, completed_at: null, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-02T00:00:00Z",
  };
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter><CasesPage /></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("case register", () => {
  beforeEach(() => listCases.mockReset());

  it("shows API records and searches within the currently returned page", async () => {
    listCases.mockResolvedValue([makeCase(1), makeCase(2)]);
    const userActions = userEvent.setup();
    renderPage();

    expect(await screen.findByText("VER-0001")).toBeInTheDocument();
    await userActions.type(screen.getByRole("searchbox", { name: "Search this page of cases" }), "0002");

    expect(screen.queryByText("VER-0001")).not.toBeInTheDocument();
    expect(screen.getByText("VER-0002")).toBeInTheDocument();
    expect(screen.getByText("Search filters the current API page")).toBeInTheDocument();
  });

  it("requests the next server page using the documented skip and limit", async () => {
    listCases.mockImplementation(({ skip = 0 }: { skip?: number } = {}) => Promise.resolve(skip === 0 ? Array.from({ length: 25 }, (_, index) => makeCase(index + 1)) : [makeCase(26)]));
    const userActions = userEvent.setup();
    renderPage();

    const nextButton = await screen.findByRole("button", { name: "Next" });
    await userActions.click(nextButton);

    expect(await screen.findByText("VER-0026")).toBeInTheDocument();
    await waitFor(() => expect(listCases).toHaveBeenLastCalledWith({ status: "", skip: 25, limit: 25 }));
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});
