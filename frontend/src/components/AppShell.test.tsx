import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

const { logout } = vi.hoisted(() => ({ logout: vi.fn() }));
vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    user: { full_name: "Example Administrator", role: "ADMIN" },
    logout,
  }),
}));

describe("responsive application navigation", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("opens a mobile dialog, contains navigation, and restores focus on Escape", async () => {
    const addEventListener = vi.fn();
    const removeEventListener = vi.fn();
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: true,
      addEventListener,
      removeEventListener,
    }));
    const user = userEvent.setup();
    render(<MemoryRouter><AppShell /></MemoryRouter>);

    const toggle = screen.getByRole("button", { name: "Open navigation" });
    expect(screen.getByLabelText("Main navigation")).toHaveAttribute("aria-hidden", "true");
    await user.click(toggle);

    const dialog = screen.getByRole("dialog", { name: "Main navigation" });
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(document.activeElement).toBe(screen.getByRole("link", { name: "VerifiaAI workspace home" }));
    expect(document.querySelector(".main-column")).toHaveAttribute("inert");

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });
});
