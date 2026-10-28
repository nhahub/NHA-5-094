import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider, useAuth } from "./AuthContext";

const { loginRequest, currentUserRequest, logoutRequest } = vi.hoisted(() => ({ loginRequest: vi.fn(), currentUserRequest: vi.fn(), logoutRequest: vi.fn() }));
vi.mock("../api/client", () => ({
  api: { auth: { login: loginRequest, me: currentUserRequest, logout: logoutRequest } },
  ApiError: class ApiError extends Error { constructor(message: string, readonly status: number) { super(message); } },
}));

function AuthHarness() {
  const { status, user, login, logout } = useAuth();
  return (
    <div>
      <p>{status}:{user?.email ?? "anonymous"}</p>
      <button type="button" onClick={() => void login("manager@example.test", "synthetic-password")}>Sign in</button>
      <button type="button" onClick={logout}>Sign out</button>
    </div>
  );
}

function renderHarness() {
  const queryClient = new QueryClient();
  render(<QueryClientProvider client={queryClient}><AuthProvider><AuthHarness /></AuthProvider></QueryClientProvider>);
  return queryClient;
}

const userRecord = {
  id: "manager-1", organization_id: "org-1", email: "manager@example.test", full_name: "Example Manager",
  role: "MANAGER" as const, is_active: true, created_at: "2026-01-01T00:00:00Z", updated_at: "2026-01-01T00:00:00Z",
};

describe("authenticated session", () => {
  beforeEach(() => {
    sessionStorage.clear();
    loginRequest.mockReset().mockResolvedValue({ access_token: "session-token", token_type: "bearer", expires_in: 3600 });
    currentUserRequest.mockReset().mockResolvedValue(userRecord);
    logoutRequest.mockReset().mockResolvedValue(undefined);
  });

  it("logs in through the API and clears identity-scoped cache on sign out", async () => {
    const queryClient = renderHarness();
    queryClient.setQueryData(["private", "org-1"], { record: true });
    const user = userEvent.setup();

    await user.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByText("authenticated:manager@example.test")).toBeInTheDocument();
    expect(loginRequest).toHaveBeenCalledWith("manager@example.test", "synthetic-password");
    expect(sessionStorage.getItem("verifiaai.accessToken")).toBe("session-token");

    await user.click(screen.getByRole("button", { name: "Sign out" }));
    expect(screen.getByText("anonymous:anonymous")).toBeInTheDocument();
    expect(sessionStorage.getItem("verifiaai.accessToken")).toBeNull();
    expect(queryClient.getQueryData(["private", "org-1"])).toBeUndefined();
    expect(logoutRequest).toHaveBeenCalledOnce();
  });

  it("restores a session by confirming the stored token with /auth/me", async () => {
    sessionStorage.setItem("verifiaai.accessToken", "existing-token");
    renderHarness();

    expect(await screen.findByText("authenticated:manager@example.test")).toBeInTheDocument();
    expect(currentUserRequest).toHaveBeenCalledOnce();
  });
});
