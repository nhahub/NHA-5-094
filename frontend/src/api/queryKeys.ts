import type { UserRead } from "./contracts";

const identity = (user: UserRead | null) => [user?.organization_id ?? "no-org", user?.id ?? "anonymous"] as const;

export const queryKeys = {
  cases: (user: UserRead | null, options: { status?: string; skip?: number; limit?: number }) =>
    ["cases", ...identity(user), options] as const,
  customerCases: (user: UserRead | null) => ["customer-cases", ...identity(user)] as const,
  customerCase: (user: UserRead | null, caseId: string) => ["customer-case", ...identity(user), caseId] as const,
  customerProcesses: (user: UserRead | null) => ["customer-processes", ...identity(user)] as const,
  caseReview: (user: UserRead | null, caseId: string) => ["case-review", ...identity(user), caseId] as const,
  caseState: (user: UserRead | null, caseId: string) => ["case-state", ...identity(user), caseId] as const,
  caseEvents: (user: UserRead | null, caseId: string) => ["case-events", ...identity(user), caseId] as const,
  processes: (user: UserRead | null) => ["processes", ...identity(user)] as const,
  processVersions: (user: UserRead | null, processId: string) => ["process-versions", ...identity(user), processId] as const,
  myTasks: (user: UserRead | null) => ["my-tasks", ...identity(user)] as const,
  pendingApprovals: (user: UserRead | null) => ["pending-approvals", ...identity(user)] as const,
  organizationUsers: (user: UserRead | null) => ["organization-users", ...identity(user)] as const,
};
