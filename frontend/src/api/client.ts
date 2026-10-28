import { clearAccessToken, readAccessToken } from "../auth/authStorage";
import type {
  AgentRunResponse,
  ApprovalDecisionRequest,
  ApprovalRecord,
  ApiProblem,
  CaseRecord,
  CaseReviewBundle,
  CaseState,
  CustomerCaseRecord,
  CustomerDocumentUploadResult,
  CustomerProcessOption,
  DocumentUploadResult,
  EventRecord,
  ProcessRecord,
  ProcessVersionRecord,
  ProvisionedUserCreate,
  TaskComment,
  TaskCommentCreate,
  TaskRecord,
  TaskResolutionRequest,
  TokenResponse,
  UserRead,
} from "./contracts";

const configuredBase = import.meta.env.VITE_API_BASE_URL || "/api/v1";
export const API_BASE_URL = configuredBase.replace(/\/$/, "");

export function isSecureApiTransport(
  apiBase: string,
  pageOrigin: string,
  production: boolean,
): boolean {
  if (!production) return true;
  try {
    const pageUrl = new URL(pageOrigin);
    const apiUrl = new URL(apiBase, pageUrl);
    const loopbackHosts = new Set(["localhost", "127.0.0.1", "[::1]"]);
    if (loopbackHosts.has(pageUrl.hostname) && loopbackHosts.has(apiUrl.hostname)) return true;
    return pageUrl.protocol === "https:" && apiUrl.protocol === "https:";
  } catch {
    return false;
  }
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly detail: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type RequestOptions = RequestInit & {
  authenticated?: boolean;
  responseKind?: "json" | "blob";
};

function problemMessage(status: number, problem: ApiProblem | null): string {
  const detail = problem?.detail;
  const detailText =
    typeof detail === "string"
      ? detail
      : detail && typeof detail === "object" && !Array.isArray(detail) && "message" in detail
        ? String((detail as { message: unknown }).message)
        : null;

  if (status === 401) return "Your session has expired. Sign in again to continue.";
  if (status === 403) return "Your account does not have access to this action.";
  if (status === 404) return "This record is not available in your organization.";
  if (status === 409) return detailText || "This record changed before the action completed. Refresh and try again.";
  if (status === 413) return detailText || "This file exceeds the server's upload size limit.";
  if (status === 415) return detailText || "The server does not accept this file type or content.";
  if (status === 503) return detailText || "A required backend service is unavailable. Try again later.";
  if (status === 422) return "Some submitted fields were not accepted. Review the form and try again.";
  if (status >= 500) return "The backend could not complete this request. Try again later.";
  if (detailText) return detailText;
  return "The request could not be completed.";
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { authenticated = true, responseKind = "json", headers: inputHeaders, ...init } = options;
  if (!isSecureApiTransport(API_BASE_URL, window.location.origin, import.meta.env.PROD)) {
    throw new ApiError("This app is configured with an insecure API connection. Contact your administrator.", 0);
  }
  const headers = new Headers(inputHeaders);
  const token = authenticated ? readAccessToken() : null;
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const isFormData = typeof FormData !== "undefined" && init.body instanceof FormData;
  if (init.body && !isFormData && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers,
      credentials: "omit",
    });
  } catch {
    throw new ApiError("The backend could not be reached. Check the connection and try again.", 0);
  }

  if (response.status === 401 && authenticated) {
    clearAccessToken();
    window.dispatchEvent(new Event("verifia:unauthorized"));
  }

  if (!response.ok) {
    let problem: ApiProblem | null;
    try {
      problem = (await response.json()) as ApiProblem;
    } catch {
      problem = null;
    }
    throw new ApiError(problemMessage(response.status, problem), response.status, problem?.detail ?? null);
  }

  if (response.status === 204) return undefined as T;
  if (responseKind === "blob") return (await response.blob()) as T;
  if (response.headers.get("content-type")?.includes("application/json")) {
    return (await response.json()) as T;
  }
  return undefined as T;
}

function queryString(values: Record<string, string | number | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const text = params.toString();
  return text ? `?${text}` : "";
}

export const api = {
  auth: {
    login: (email: string, password: string) =>
      apiRequest<TokenResponse>("/auth/login", {
        method: "POST",
        authenticated: false,
        body: JSON.stringify({ email, password }),
      }),
    logout: () => apiRequest<void>("/auth/logout", { method: "POST" }),
    me: () => apiRequest<UserRead>("/auth/me"),
    users: (skip = 0, limit = 100) =>
      apiRequest<UserRead[]>(`/auth/users${queryString({ skip, limit })}`),
    provisionUser: (input: ProvisionedUserCreate) =>
      apiRequest<UserRead>("/auth/users", { method: "POST", body: JSON.stringify(input) }),
  },
  cases: {
    list: (options: { status?: string; skip?: number; limit?: number } = {}) =>
      apiRequest<CaseRecord[]>(`/cases${queryString(options)}`),
    create: (input: { title: string; process_version_id: string; case_metadata: Record<string, unknown> }) =>
      apiRequest<CaseRecord>("/cases", { method: "POST", body: JSON.stringify(input) }),
    mine: (skip = 0, limit = 50) =>
      apiRequest<CustomerCaseRecord[]>(`/cases/mine${queryString({ skip, limit })}`),
    createMine: (input: { title: string; process_version_id: string }) =>
      apiRequest<CustomerCaseRecord>("/cases/mine", {
        method: "POST",
        body: JSON.stringify({ ...input, case_metadata: {} }),
      }),
    mineById: (caseId: string) =>
      apiRequest<CustomerCaseRecord>(`/cases/mine/${encodeURIComponent(caseId)}`),
    review: (caseId: string) => apiRequest<CaseReviewBundle>(`/cases/${encodeURIComponent(caseId)}/review`),
    state: (caseId: string) => apiRequest<CaseState>(`/cases/${encodeURIComponent(caseId)}/state`),
    events: (caseId: string, skip = 0, limit = 100) =>
      apiRequest<EventRecord[]>(`/cases/${encodeURIComponent(caseId)}/events${queryString({ skip, limit })}`),
  },
  processes: {
    list: (skip = 0, limit = 100) =>
      apiRequest<ProcessRecord[]>(`/processes${queryString({ skip, limit })}`),
    versions: (processId: string) =>
      apiRequest<ProcessVersionRecord[]>(`/processes/${encodeURIComponent(processId)}/versions`),
    customerOptions: () => apiRequest<CustomerProcessOption[]>("/processes/customer-options"),
  },
  documents: {
    upload: (caseId: string, documentType: string, file: File) => {
      const form = new FormData();
      form.set("case_id", caseId);
      form.set("document_type", documentType);
      form.set("file", file);
      return apiRequest<DocumentUploadResult>("/documents", { method: "POST", body: form });
    },
    uploadMine: (caseId: string, documentType: string, file: File) => {
      const form = new FormData();
      form.set("case_id", caseId);
      form.set("document_type", documentType);
      form.set("file", file);
      return apiRequest<CustomerDocumentUploadResult>("/documents/mine", { method: "POST", body: form });
    },
    process: (documentId: string, versionId: string) =>
      apiRequest<{ id: string; status: string; review_required: boolean; review_reasons: string[]; safe_error: string | null }>(
        `/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/process`,
        { method: "POST" },
      ),
    download: (documentId: string, versionId: string) =>
      apiRequest<Blob>(
        `/documents/${encodeURIComponent(documentId)}/versions/${encodeURIComponent(versionId)}/content`,
        { responseKind: "blob" },
      ),
  },
  tasks: {
    mine: () => apiRequest<TaskRecord[]>("/tasks/my"),
    addComment: (taskId: string, input: TaskCommentCreate) =>
      apiRequest<TaskComment>(`/tasks/${encodeURIComponent(taskId)}/comments`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
    resolve: (taskId: string, input: TaskResolutionRequest) =>
      apiRequest<TaskRecord>(`/tasks/${encodeURIComponent(taskId)}/resolve`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
  },
  approvals: {
    pending: () => apiRequest<ApprovalRecord[]>("/approvals/pending"),
    decide: (approvalId: string, input: ApprovalDecisionRequest) =>
      apiRequest<ApprovalRecord>(`/approvals/${encodeURIComponent(approvalId)}/decide`, {
        method: "POST",
        body: JSON.stringify(input),
      }),
  },
  agents: {
    runSupervisor: (caseId: string, userPrompt?: string) =>
      apiRequest<AgentRunResponse>("/agents/run", {
        method: "POST",
        body: JSON.stringify({ case_id: caseId, agent_type: "SUPERVISOR", ...(userPrompt ? { user_prompt: userPrompt } : {}) }),
      }),
  },
};
