import { useEffect, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Download, Eye, FileText, Upload } from "lucide-react";
import { Link, useParams } from "react-router";
import { api } from "../../api/client";
import type { CustomerDocumentRecord, CustomerDocumentRequest } from "../../api/contracts";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { Button, EmptyState, ErrorNotice, ErrorState, LoadingState, PageHeader, SectionHeading, StatusBadge, SuccessNotice } from "../../components/Ui";

const MAX_FILE_BYTES = 20 * 1024 * 1024;

export function CustomerCaseWorkspacePage() {
  const { caseId = "" } = useParams();
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [uploadNotice, setUploadNotice] = useState<string | null>(null);
  const caseQuery = useQuery({
    queryKey: queryKeys.customerCase(user, caseId),
    queryFn: () => api.cases.mineById(caseId),
    enabled: Boolean(caseId && user),
  });
  const uploadMutation = useMutation({
    mutationFn: ({ documentType, file }: { documentType: string; file: File }) => api.documents.uploadMine(caseId, documentType, file),
    onSuccess: async (result) => {
      setUploadNotice(result.duplicate ? `${result.document.name} is already on this case.` : `${result.document.name} was uploaded.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.customerCase(user, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.customerCases(user) }),
      ]);
    },
  });

  if (!caseId) return <ErrorState message="A case identifier is required." />;
  if (caseQuery.isPending) return <LoadingState label="Loading your case" />;
  if (caseQuery.isError) return (
    <div className="page-stack">
      <Link className="back-link" to="/customer/cases"><ArrowLeft size={16} aria-hidden="true" /> Back to your cases</Link>
      <ErrorState message={getError(caseQuery.error)} onRetry={() => void caseQuery.refetch()} />
    </div>
  );

  const record = caseQuery.data;
  return (
    <div className="page-stack">
      <Link className="back-link" to="/customer/cases"><ArrowLeft size={16} aria-hidden="true" /> Back to your cases</Link>
      <PageHeader
        eyebrow={`CASE ${record.case_number}`}
        title={record.title}
        description={record.current_stage_name ? `Current step: ${record.current_stage_name}` : "Track the progress of your request."}
        actions={<StatusBadge status={record.status} />}
      />
      {uploadNotice && <SuccessNotice>{uploadNotice}</SuccessNotice>}
      {uploadMutation.isError && <ErrorNotice>{getError(uploadMutation.error)}</ErrorNotice>}

      <section className="panel">
        <SectionHeading title="Case status" detail="Status updates come from your organization’s case workflow." />
        <div className="case-metadata-strip">
          <div><span>Status</span><StatusBadge status={record.status} /></div>
          <div><span>Current step</span><strong>{record.current_stage_name || "Not assigned"}</strong></div>
          <div><span>Created</span><strong>{formatDate(record.created_at)}</strong></div>
          <div><span>Last updated</span><strong>{formatDate(record.updated_at)}</strong></div>
        </div>
      </section>

      <section className="panel">
        <SectionHeading title="Documents requested" detail="Upload the files listed here to complete your case submission." />
        {record.document_requests.length === 0 ? (
          <EmptyState title="No additional documents requested" description="Your organization has not configured document requirements for this process." icon={<FileText size={22} aria-hidden="true" />} />
        ) : (
          <div className="document-list">
            {record.document_requests.map((request) => (
              <DocumentRequestCard key={request.code} request={request} busy={uploadMutation.isPending} onUpload={(file) => uploadMutation.mutate({ documentType: request.code, file })} />
            ))}
          </div>
        )}
      </section>

      <section className="panel">
        <SectionHeading title="Your uploaded files" detail={`${record.documents.length} file${record.documents.length === 1 ? "" : "s"} recorded for this case.`} />
        {record.documents.length === 0 ? (
          <EmptyState title="No files uploaded yet" description="Upload a requested document above or attach another supporting file." icon={<FileText size={22} aria-hidden="true" />} />
        ) : (
          <div className="document-list">
            {record.documents.map((document) => <CustomerDocumentCard key={document.id} document={document} />)}
          </div>
        )}
      </section>

      <section className="panel">
        <SectionHeading title="Upload another file" detail="Add a supporting document that is not listed above." />
        <OtherDocumentUpload busy={uploadMutation.isPending} onUpload={(documentType, file) => uploadMutation.mutate({ documentType, file })} />
      </section>
    </div>
  );
}

function DocumentRequestCard({ request, busy, onUpload }: { request: CustomerDocumentRequest; busy: boolean; onUpload: (file: File) => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!file) return setError("Choose a file first.");
    const validation = validateFile(file);
    if (validation) return setError(validation);
    onUpload(file);
    setFile(null);
    event.currentTarget.reset();
  }

  return (
    <article className="document-card">
      <div className="document-card-head">
        <div className="document-file-mark"><FileText size={19} aria-hidden="true" /></div>
        <div className="document-main-name"><strong>{request.name}</strong><span>{request.description || request.code}</span></div>
        <StatusBadge status={request.status} />
      </div>
      {request.status === "REQUESTED" && (
        <form className="upload-form" onSubmit={submit}>
          <label className="sr-only" htmlFor={`file-${request.code}`}>Choose {request.name} file</label>
          <input id={`file-${request.code}`} type="file" accept=".pdf,.png,.jpg,.jpeg,.xls,.xlsx,.csv,.docx,.txt" onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} disabled={busy} />
          {error && <ErrorNotice>{error}</ErrorNotice>}
          <Button type="submit" disabled={busy || !file} icon={<Upload size={15} aria-hidden="true" />}>{busy ? "Uploading…" : `Upload ${request.name}`}</Button>
        </form>
      )}
    </article>
  );
}

function OtherDocumentUpload({ busy, onUpload }: { busy: boolean; onUpload: (documentType: string, file: File) => void }) {
  const [documentType, setDocumentType] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    if (!documentType.trim() || !file) return setError("Enter a document name and choose a file.");
    const validation = validateFile(file);
    if (validation) return setError(validation);
    onUpload(documentType.trim(), file);
    setDocumentType("");
    setFile(null);
    event.currentTarget.reset();
  }

  return (
    <form className="upload-form" onSubmit={submit}>
      <div className="upload-fields">
        <div className="form-field"><label htmlFor="other-document-type">Document name</label><input id="other-document-type" value={documentType} onChange={(event) => setDocumentType(event.target.value)} required maxLength={100} disabled={busy} /></div>
        <div className="form-field"><label htmlFor="other-document-file">File</label><input id="other-document-file" type="file" accept=".pdf,.png,.jpg,.jpeg,.xls,.xlsx,.csv,.docx,.txt" onChange={(event) => setFile(event.currentTarget.files?.[0] ?? null)} disabled={busy} /></div>
      </div>
      {error && <ErrorNotice>{error}</ErrorNotice>}
      <div className="upload-actions"><Button type="submit" disabled={busy || !file} icon={<Upload size={15} aria-hidden="true" />}>Upload file</Button></div>
    </form>
  );
}

function CustomerDocumentCard({ document }: { document: CustomerDocumentRecord }) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const previewable = document.mime_type === "application/pdf" || document.mime_type === "image/png" || document.mime_type === "image/jpeg";

  useEffect(() => () => { if (previewUrl) URL.revokeObjectURL(previewUrl); }, [previewUrl]);

  async function loadContent() {
    if (!document.version_id) return setError("The file content is not available.");
    setError(null);
    try {
      const blob = await api.documents.download(document.id, document.version_id);
      setPreviewUrl(URL.createObjectURL(blob));
    } catch (cause) {
      setError(getError(cause));
    }
  }

  async function download() {
    if (!document.version_id) return setError("The file content is not available.");
    setError(null);
    try {
      const blob = await api.documents.download(document.id, document.version_id);
      const url = URL.createObjectURL(blob);
      const anchor = window.document.createElement("a");
      anchor.href = url;
      anchor.download = safeFilename(document.name);
      anchor.rel = "noopener";
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
    } catch (cause) {
      setError(getError(cause));
    }
  }

  return (
    <article className="document-card">
      <div className="document-card-head">
        <div className="document-file-mark"><FileText size={19} aria-hidden="true" /></div>
        <div className="document-main-name"><strong>{document.name}</strong><span>{document.document_type} · {formatDate(document.created_at)}</span></div>
        <StatusBadge status={document.status} />
      </div>
      {document.version_id && (
        <div className="version-actions">
          {previewable && <Button variant="secondary" onClick={() => void loadContent()} icon={<Eye size={15} aria-hidden="true" />}>Preview file</Button>}
          <Button variant="quiet" onClick={() => void download()} icon={<Download size={15} aria-hidden="true" />}>Download file</Button>
        </div>
      )}
      {error && <ErrorNotice>{error}</ErrorNotice>}
      {previewUrl && (
        <div className="preview-overlay" role="dialog" aria-modal="true" aria-label={`Preview ${document.name}`}>
          <div className="preview-dialog">
            <div className="section-heading"><div><p className="eyebrow">CASE DOCUMENT</p><h2>{document.name}</h2></div><Button variant="secondary" onClick={() => setPreviewUrl(null)}>Close preview</Button></div>
            {document.mime_type === "application/pdf" ? (
              <iframe title={`Preview ${document.name}`} src={previewUrl} sandbox="allow-scripts" referrerPolicy="no-referrer" />
            ) : (
              <img src={previewUrl} alt={document.name} />
            )}
          </div>
        </div>
      )}
    </article>
  );
}

function validateFile(file: File): string | null {
  const allowed = new Set(["pdf", "png", "jpg", "jpeg", "xls", "xlsx", "csv", "docx", "txt"]);
  const extension = file.name.split(".").pop()?.toLowerCase() ?? "";
  if (!allowed.has(extension)) return "Choose a PDF, PNG/JPEG, XLS/XLSX, CSV, DOCX, or TXT file.";
  if (file.size === 0) return "Empty files cannot be uploaded.";
  if (file.size > MAX_FILE_BYTES) return "This file is larger than the 20 MiB server limit.";
  return null;
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}

function safeFilename(value: string): string {
  const safe = Array.from(value, (character) => {
    const code = character.charCodeAt(0);
    return /[\\/:*?"<>|]/.test(character) || code < 0x20 || code === 0x7f ? "_" : character;
  }).join("");
  return safe.slice(0, 180) || "document";
}
