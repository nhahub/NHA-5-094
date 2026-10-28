export type UserRole = "CUSTOMER" | "EMPLOYEE" | "MANAGER" | "ADMIN";

export interface UserRead {
  id: string;
  organization_id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export type ProvisionableUserRole = "CUSTOMER" | "EMPLOYEE" | "MANAGER";

export interface ProvisionedUserCreate {
  email: string;
  full_name: string;
  password: string;
  role: ProvisionableUserRole;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
}

export interface CaseRecord {
  id: string;
  organization_id: string;
  process_id: string;
  process_version_id: string;
  case_number: string;
  title: string;
  case_metadata: Record<string, unknown>;
  status: string;
  current_stage_id: string | null;
  created_by: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface CustomerDocumentRecord {
  id: string;
  document_type: string;
  name: string;
  status: string;
  created_at: string;
  version_id: string | null;
  mime_type: string | null;
}

export interface CustomerDocumentRequest {
  code: string;
  name: string;
  description: string | null;
  status: "REQUESTED" | "RECEIVED";
}

export interface CustomerCaseRecord {
  id: string;
  case_number: string;
  title: string;
  status: string;
  current_stage_name: string | null;
  created_at: string;
  updated_at: string;
  documents: CustomerDocumentRecord[];
  document_requests: CustomerDocumentRequest[];
}

export interface CustomerProcessOption {
  process_id: string;
  process_version_id: string;
  name: string;
  description: string | null;
}

export interface CustomerDocumentUploadResult {
  document: CustomerDocumentRecord;
  duplicate: boolean;
}

export interface CaseState {
  case: CaseRecord;
  current_stage_name: string | null;
  current_stage_code: string | null;
  documents_count: number;
  verifications_count: number;
  open_tasks_count: number;
  evidence_count: number;
}

export interface ProcessRecord {
  id: string;
  organization_id: string;
  name: string;
  code: string;
  description: string | null;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ProcessVersionRecord {
  id: string;
  process_id: string;
  version_number: number;
  status: string;
  configuration: Record<string, unknown>;
  created_by: string | null;
  published_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExtractedField {
  id: string;
  field_name: string;
  field_value: Record<string, unknown> | null;
  confidence: number | null;
  page_number: number | null;
  source_text?: string | null;
  source_locator?: Record<string, unknown> | null;
  extraction_method?: string | null;
  processing_run_id?: string | null;
}

export interface ProcessingRun {
  id: string;
  run_number: number;
  status: string;
  predicted_document_type: string | null;
  classification_confidence: number | null;
  review_required: boolean;
  review_reasons: string[];
  safe_error: string | null;
  completed_at: string | null;
}

export interface DocumentVersionSummary {
  id: string;
  version_number: number;
  mime_type: string | null;
  file_size: number | null;
  extracted_fields: ExtractedField[];
  processing_runs: ProcessingRun[];
}

export interface ReviewDocument {
  id: string;
  name: string;
  document_type: string;
  status: string;
  versions: DocumentVersionSummary[];
}

export interface DocumentRecord extends Omit<ReviewDocument, "versions"> {
  case_id: string;
  uploaded_by: string | null;
  created_at: string;
  versions: Array<DocumentVersionSummary & { document_id: string; version_number: number }>;
}

export interface DocumentUploadResult {
  document: DocumentRecord;
  duplicate: boolean;
}

export interface EvidenceItem {
  id: string;
  source_type: string;
  source_id: string | null;
  field_reference: string | null;
  value_snapshot: Record<string, unknown> | null;
  page_number: number | null;
  location: Record<string, unknown> | null;
}

export interface EvidenceRecord {
  id: string;
  evidence_type: string;
  description: string | null;
  verification_execution_id: string | null;
  items: EvidenceItem[];
}

export interface VerificationResult {
  id: string;
  result: string;
  summary: string | null;
  confidence: number | null;
  reason: string | null;
}

export interface ReviewVerification {
  id: string;
  verification_id: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  results: VerificationResult[];
}

export interface TaskComment {
  id: string;
  author_id: string;
  comment: string;
  evidence_ids: string[];
  created_at: string;
}

export interface TaskRecord {
  id: string;
  case_id: string;
  task_type: string;
  title: string;
  description: string | null;
  priority: string;
  stage_id: string | null;
  assigned_user_id: string | null;
  assigned_role_id: string | null;
  assigned_department_id: string | null;
  due_at: string | null;
  status: string;
  created_by_type: string;
  created_by_id: string | null;
  completed_at: string | null;
  completion_metadata: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

export interface ReviewTask extends TaskRecord {
  comments: TaskComment[];
}

export interface ApprovalRecord {
  id: string;
  case_id: string;
  approval_type: string;
  task_id: string | null;
  decision: string;
  decided_by_user_id: string | null;
  decided_at: string | null;
  comment: string | null;
  created_at: string;
  updated_at: string;
}

export interface CaseDiscrepancy {
  kind: string;
  summary?: string | null;
  reason?: string | null;
  reasons?: string[];
  document_version_id?: string;
  processing_run_id?: string;
  verification_execution_id?: string;
  result_id?: string;
}

export interface CaseRecommendation {
  execution_id: string;
  agent_type: string;
  status: string;
  recommendation: Record<string, unknown>;
  completed_at: string | null;
}

export interface CaseReviewBundle {
  case: CaseRecord;
  review_tasks: ReviewTask[];
  approvals: ApprovalRecord[];
  documents: ReviewDocument[];
  verifications: ReviewVerification[];
  evidence: EvidenceRecord[];
  discrepancies: CaseDiscrepancy[];
  recommendations: CaseRecommendation[];
}

export interface EventRecord {
  id: string;
  organization_id: string;
  case_id: string | null;
  event_type: string;
  actor_type: string;
  actor_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TaskResolutionRequest {
  outcome: "COMPLETED" | "REJECTED";
  comment: string;
  evidence_ids: string[];
}

export interface TaskCommentCreate {
  comment: string;
  evidence_ids: string[];
}

export interface ApprovalDecisionRequest {
  decision: "APPROVED" | "REJECTED";
  comment: string;
}

export interface AgentProposal {
  agent_name: string;
  case_id: string;
  proposed_action: string;
  suggested_target_stage_id: string | null;
  confidence: number;
  rationale: string;
  evidence_references: string[];
}

export interface AgentRunResponse {
  case_id: string;
  agent_type: string;
  success: boolean;
  summary: string;
  proposals: AgentProposal[];
  result_data: Record<string, unknown>;
  execution_id: string | null;
}

export interface ApiProblem {
  detail?: unknown;
}
