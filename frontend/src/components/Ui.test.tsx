import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusBadge, statusTone } from "./Ui";

describe("verification status presentation", () => {
  it("keeps indeterminate results visually separate from pass and fail", () => {
    expect(statusTone("PASS")).toBe("positive");
    expect(statusTone("FAIL")).toBe("negative");
    expect(statusTone("INCONCLUSIVE")).toBe("caution");
    expect(statusTone("NOT_APPLICABLE")).toBe("neutral");
  });

  it("formats backend enum values without changing their meaning", () => {
    render(<StatusBadge status="NOT_APPLICABLE" />);
    expect(screen.getByText("Not applicable")).toHaveClass("status-neutral");
  });
});
