import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { api, apiRequest, isSecureApiTransport } from "./client";
import { readAccessToken, writeAccessToken } from "../auth/authStorage";

describe("authenticated API client", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.stubGlobal("fetch", vi.fn());
  });

  it("requires HTTPS for production app and API transports", () => {
    expect(isSecureApiTransport("/api/v1", "https://app.example.test", true)).toBe(true);
    expect(isSecureApiTransport("http://api.example.test/v1", "https://app.example.test", true)).toBe(false);
    expect(isSecureApiTransport("/api/v1", "http://app.example.test", true)).toBe(false);
    expect(isSecureApiTransport("/api/v1", "http://127.0.0.1:3000", true)).toBe(true);
    expect(isSecureApiTransport("http://127.0.0.1:8000/api/v1", "http://localhost:5173", false)).toBe(true);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    sessionStorage.clear();
  });

  it("adds the bearer token and JSON content type to authenticated requests", async () => {
    writeAccessToken("session-token");
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ ok: true }), {
      status: 200,
      headers: { "content-type": "application/json" },
    }));

    await expect(apiRequest<{ ok: boolean }>("/example", { method: "POST", body: JSON.stringify({ value: 1 }) })).resolves.toEqual({ ok: true });

    const [, options] = vi.mocked(fetch).mock.calls[0]!;
    const headers = new Headers(options?.headers);
    expect(headers.get("Authorization")).toBe("Bearer session-token");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(options?.credentials).toBe("omit");
  });

  it("clears an expired token and notifies the session provider on 401", async () => {
    writeAccessToken("expired-token");
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ detail: "unauthorized" }), {
      status: 401,
      headers: { "content-type": "application/json" },
    }));
    const unauthorized = vi.fn();
    window.addEventListener("verifia:unauthorized", unauthorized);

    await expect(apiRequest("/private")).rejects.toMatchObject({ status: 401 });

    expect(readAccessToken()).toBeNull();
    expect(unauthorized).toHaveBeenCalledOnce();
    window.removeEventListener("verifia:unauthorized", unauthorized);
  });

  it("leaves multipart boundaries to the browser", async () => {
    const body = new FormData();
    body.set("field", "value");
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));

    await apiRequest<void>("/upload", { method: "POST", body });

    const [, options] = vi.mocked(fetch).mock.calls[0]!;
    expect(new Headers(options?.headers).has("Content-Type")).toBe(false);
  });

  it("sends document uploads with the backend's multipart field names", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(JSON.stringify({ document: { id: "doc-1" }, duplicate: false }), {
      status: 201,
      headers: { "content-type": "application/json" },
    }));
    const file = new File(["synthetic content"], "invoice.pdf", { type: "application/pdf" });

    await api.documents.upload("case-1", "INVOICE", file);

    const [url, options] = vi.mocked(fetch).mock.calls[0]!;
    expect(url).toContain("/api/v1/documents");
    expect(options?.body).toBeInstanceOf(FormData);
    expect((options?.body as FormData).get("case_id")).toBe("case-1");
    expect((options?.body as FormData).get("document_type")).toBe("INVOICE");
    expect((options?.body as FormData).get("file")).toBe(file);
    expect(new Headers(options?.headers).has("Content-Type")).toBe(false);
  });
});
