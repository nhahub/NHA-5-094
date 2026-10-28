import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CaseReviewBundle } from "../../api/contracts";
import { DocumentsPanel } from "./DocumentsPanel";

const { downloadDocument } = vi.hoisted(() => ({ downloadDocument: vi.fn() }));
vi.mock("../../api/client", () => ({ api: { documents: { download: downloadDocument } } }));
vi.mock("../../auth/AuthContext", () => ({
  useAuth: () => ({ user: { id: "employee-1", organization_id: "org-1", role: "EMPLOYEE" } }),
}));

const bundle = {
  documents: [{
    id: "doc-1",
    name: "invoice.pdf",
    document_type: "INVOICE",
    status: "PROCESSED",
    versions: [{
      id: "version-1",
      version_number: 1,
      mime_type: "application/pdf",
      file_size: 24,
      extracted_fields: [],
      processing_runs: [],
    }],
  }],
} as unknown as CaseReviewBundle;

function renderPanel() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <DocumentsPanel caseId="case-1" bundle={bundle} />
    </QueryClientProvider>,
  );
}

describe("employee document preview", () => {
  beforeEach(() => {
    downloadDocument.mockReset().mockResolvedValue(new Blob(["%PDF-1.7"]));
    vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:case-document");
    vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => undefined);
  });

  afterEach(() => vi.restoreAllMocks());

  it("previews supported PDFs in a sandboxed frame and revokes the object URL on close", async () => {
    const user = userEvent.setup();
    renderPanel();

    await user.click(screen.getByRole("button", { name: "Preview" }));
    const frame = await screen.findByTitle("Preview invoice.pdf");

    expect(downloadDocument).toHaveBeenCalledWith("doc-1", "version-1");
    expect(frame).toHaveAttribute("sandbox", "allow-scripts");
    expect(frame).toHaveAttribute("referrerpolicy", "no-referrer");

    await user.click(screen.getByRole("button", { name: "Close preview" }));
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:case-document");
  });
});
