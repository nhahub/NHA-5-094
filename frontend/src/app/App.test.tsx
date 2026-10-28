import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../auth/AuthContext";
import { App } from "./App";

const { currentUserRequest, usersRequest, customerCasesRequest, customerProcessesRequest, logoutRequest } = vi.hoisted(() => ({ currentUserRequest: vi.fn(), usersRequest: vi.fn(), customerCasesRequest: vi.fn(), customerProcessesRequest: vi.fn(), logoutRequest: vi.fn() }));
vi.mock("../api/client", () => ({
  api: {
    auth: { me: currentUserRequest, users: usersRequest, provisionUser: vi.fn(), logout: logoutRequest },
    cases: { mine: customerCasesRequest },
    processes: { customerOptions: customerProcessesRequest },
  },
  ApiError: class ApiError extends Error { constructor(message: string, readonly status: number) { super(message); } },
}));

const employee = {
  id: "employee-1", organization_id: "org-1", email: "employee@example.test", full_name: "Example Employee",
  role: "EMPLOYEE" as const, is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

function renderRoute(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}><AuthProvider><App /></AuthProvider></MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("application access boundaries", () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem("verifiaai.accessToken", "synthetic-token");
    currentUserRequest.mockReset().mockResolvedValue(employee);
    usersRequest.mockReset().mockResolvedValue([]);
    customerCasesRequest.mockReset().mockResolvedValue([]);
    customerProcessesRequest.mockReset().mockResolvedValue([]);
  });

  it("blocks employee access to the manager approval route", async () => {
    renderRoute("/approvals");

    expect(await screen.findByRole("heading", { name: "Manager access required" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Approvals" })).not.toBeInTheDocument();
  });

  it("routes customers to their participant-scoped case workspace", async () => {
    currentUserRequest.mockResolvedValue({ ...employee, role: "CUSTOMER" });
    renderRoute("/cases");

    expect(await screen.findByRole("heading", { name: "Your cases" })).toBeInTheDocument();
    expect(await screen.findByText("No cases yet")).toBeInTheDocument();
    expect(customerCasesRequest).toHaveBeenCalledOnce();
  });

  it("shows user administration only to an administrator", async () => {
    currentUserRequest.mockResolvedValue({ ...employee, role: "ADMIN" });
    renderRoute("/admin/users");

    expect(await screen.findByRole("heading", { name: "User access" })).toBeInTheDocument();
    expect(await screen.findByText("No users were returned")).toBeInTheDocument();
    expect(usersRequest).toHaveBeenCalledOnce();
  });

  it("blocks employee access to user administration", async () => {
    renderRoute("/admin/users");

    expect(await screen.findByRole("heading", { name: "Administrator access required" })).toBeInTheDocument();
    expect(usersRequest).not.toHaveBeenCalled();
  });
});
