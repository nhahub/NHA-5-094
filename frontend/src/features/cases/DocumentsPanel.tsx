import { useEffect, useRef, useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Download, Eye, FileCheck2, FileText, RefreshCw, Upload } from "lucide-react";
import { api } from "../../api/client";
import type { CaseReviewBundle, DocumentVersionSummary, ReviewDocument } from "../../api/contracts";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { Button, EmptyState, ErrorNotice, SectionHeading, StatusBadge, SuccessNotice } from "../../components/Ui";

const MAX_FILE_BYTES = 20 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(["pdf", "png", "jpg", "jpeg", "xls", "xlsx", "csv", "docx", "txt"]);

export function DocumentsPanel({ caseId, bundle }: { caseId: string; bundle: CaseReviewBundle }) {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const fileRef = useRef<HTMLInputElement>(null);
  const [documentType, setDocumentType] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const [previewFile, setPreviewFile] = useState<{ url: string; mimeType: string; name: string } | null>(null);

  useEffect(() => () => {
    if (previewFile?.url) URL.revokeObjectURL(previewFile.url);
  }, [previewFile?.url]);

  const uploadMutation = useMutation({
    mutationFn: () => {
      if (!file) throw new Error("Choose a file before uploading.");
      if (!documentType.trim()) throw new Error("Enter a document type.");
      return api.documents.upload(caseId, documentType.trim(), file);
    },
    onSuccess: async (result) => {
      setFormError(null);
      setSuccess(result.duplicate ? `${result.document.name} matches a document version already stored by the backend.` : `${result.document.name} was uploaded. Current status: ${result.document.status}.`);
      setDocumentType("");
      setFile(null);
      if (fileRef.current) fileRef.current.value = "";
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.caseReview(user, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.caseState(user, caseId) }),
        queryClient.invalidateQueries({ queryKey: ["cases"] }),
      ]);
    },
    onError: (error) => setFormError(error instanceof Error ? error.message : "The upload failed."),
  });

  const processMutation = useMutation({
    mutationFn: ({ documentId, versionId }: { documentId: string; versionId: string }) => api.documents.process(documentId, versionId),
    onSuccess: async (run) => {
      setSuccess(`Processing request recorded with status ${run.status}. Review reasons and completion status come from the backend.`);
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.caseReview(user, caseId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.caseState(user, caseId) }),
      ]);
    },
  });

  function selectFile(next: File | null) {
    setFormError(null);
    setSuccess(null);
    if (!next) {
      setFile(null);
      return;
    }
    const extension = next.name.split(".").pop()?.toLowerCase() ?? "";
    if (!ALLOWED_EXTENSIONS.has(extension)) {
      setFile(null);
      setFormError("Choose a PDF, PNG/JPEG, XLS/XLSX, CSV, DOCX, or TXT file.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    if (next.size === 0) {
      setFile(null);
      setFormError("Empty files cannot be uploaded.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    if (next.size > MAX_FILE_BYTES) {
      setFile(null);
      setFormError("This file is larger than 20 MiB, the default server upload limit.");
      if (fileRef.current) fileRef.current.value = "";
      return;
    }
    setFile(next);
  }

  function submitUpload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSuccess(null);
    if (!file) {
      setFormError("Choose a file before uploading.");
      return;
    }
    if (!documentType.trim()) {
      setFormError("Enter a document type.");
      return;
    }
    setFormError(null);
    uploadMutation.mutate();
  }

  const knownTypes = Array.from(new Set(bundle.documents.map((document) => document.document_type).filter(Boolean)));

  return (
    <div className="page-stack">
      <section className="panel upload-panel">
        <SectionHeading title="Add a document" detail="The backend validates the file and stores each upload as a versioned record." />
        <form className="upload-form" onSubmit={submitUpload}>
          <div className="upload-fields">
            <div className="form-field">
              <label htmlFor="document-type">Document type</label>
              <input
                id="document-type"
                list="case-document-types"
                value={documentType}
                onChange={(event) => setDocumentType(event.target.value)}
                placeholder="For example, invoice"
                required
                maxLength={100}
                disabled={uploadMutation.isPending}
              />
              <datalist id="case-document-types">{knownTypes.map((type) => <option key={type} value={type} />)}</datalist>
              <small className="field-hint">Use the process’ document label. Existing labels are suggested.</small>
            </div>
            <div className="form-field">
              <label htmlFor="document-file">File</label>
              <input
                id="document-file"
                ref={fileRef}
                type="file"
                accept=".pdf,.png,.jpg,.jpeg,.xls,.xlsx,.csv,.docx,.txt"
                onChange={(event) => selectFile(event.currentTarget.files?.[0] ?? null)}
                required
                disabled={uploadMutation.isPending}
              />
              <small className="field-hint">PDF, PNG/JPEG, XLS/XLSX, CSV, DOCX, TXT · 20 MiB default limit</small>
            </div>
          </div>
          {file && <div className="selected-file"><FileText size={16} aria-hidden="true" /><span>{file.name}</span><small>{formatBytes(file.size)}</small></div>}
          {formError && <ErrorNotice>{formError}</ErrorNotice>}
          {uploadMutation.isError && !formError && <ErrorNotice>{getError(uploadMutation.error)}</ErrorNotice>}
          {success && <SuccessNotice>{success}</SuccessNotice>}
          <div className="upload-actions"><Button type="submit" disabled={uploadMutation.isPending} icon={<Upload size={16} aria-hidden="true" />}>{uploadMutation.isPending ? "Uploading…" : "Upload document"}</Button></div>
        </form>
      </section>

      <section className="panel">
        <SectionHeading title="Case documents" detail={`${bundle.documents.length} document record${bundle.documents.length === 1 ? "" : "s"} in the current case packet`} />
        {bundle.documents.length === 0 ? (
          <EmptyState title="No documents on this case" description="Upload the first document when evidence is available for review." icon={<FileCheck2 size={22} aria-hidden="true" />} />
        ) : (
          <div className="document-list">
            {bundle.documents.map((document) => (
              <DocumentCard
                key={document.id}
                document={document}
                preview={async (version) => {
                  if (!version.mime_type || !["application/pdf", "image/png", "image/jpeg"].includes(version.mime_type)) return;
                  try {
                    const content = await api.documents.download(document.id, version.id);
                    setPreviewFile({ url: URL.createObjectURL(content), mimeType: version.mime_type, name: document.name });
                  } catch (error) {
                    setFormError(getError(error));
                  }
                }}
                onProcess={(version) => processMutation.mutate({ documentId: document.id, versionId: version.id })}
                processing={processMutation.isPending && processMutation.variables?.documentId === document.id}
                processingError={processMutation.isError && processMutation.variables?.documentId === document.id ? getError(processMutation.error) : null}
                download={async (version) => {
                  try {
                    const content = await api.documents.download(document.id, version.id);
                    const url = URL.createObjectURL(content);
                    const anchor = window.document.createElement("a");
                    anchor.href = url;
                    anchor.download = safeFilename(document.name);
                    anchor.rel = "noopener";
                    anchor.click();
                    window.setTimeout(() => URL.revokeObjectURL(url), 1000);
                  } catch (error) {
                    setFormError(getError(error));
                  }
                }}
              />
            ))}
          </div>
        )}
      </section>
      {previewFile && (
        <div className="preview-overlay" role="dialog" aria-modal="true" aria-label={`Preview ${previewFile.name}`}>
          <div className="preview-dialog">
            <div className="section-heading"><div><p className="eyebrow">CASE DOCUMENT</p><h2>{previewFile.name}</h2></div><Button variant="secondary" onClick={() => setPreviewFile(null)}>Close preview</Button></div>
            {previewFile.mimeType === "application/pdf" ? (
              <iframe title={`Preview ${previewFile.name}`} src={previewFile.url} sandbox="allow-scripts" referrerPolicy="no-referrer" />
            ) : (
              <img src={previewFile.url} alt={previewFile.name} />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function DocumentCard({
  document,
  preview,
  onProcess,
  processing,
  processingError,
  download,
}: {
  document: ReviewDocument;
  preview: (version: DocumentVersionSummary) => Promise<void>;
  onProcess: (version: DocumentVersionSummary) => void;
  processing: boolean;
  processingError: string | null;
  download: (version: DocumentVersionSummary) => Promise<void>;
}) {
  const versions = [...document.versions].sort((a, b) => b.version_number - a.version_number);
  const latest = versions[0];
  const latestRun = latest?.processing_runs?.[0];
  const canRunProcessing = Boolean(latest && ["PENDING", "FAILED"].includes(document.status.toUpperCase()));

  return (
    <article className="document-card">
      <div className="document-card-head">
        <div className="document-file-mark"><FileText size={19} aria-hidden="true" /></div>
        <div className="document-main-name"><strong>{document.name}</strong><span>{document.document_type}</span></div>
        <StatusBadge status={document.status} />
      </div>
      {versions.length === 0 ? (
        <p className="muted document-no-version">No file version details were returned.</p>
      ) : (
        <div className="document-version-list">
          {versions.map((version) => {
            const run = version.processing_runs?.[0];
            return (
              <div className="document-version" key={version.id}>
                <div className="version-heading"><strong>Version {version.version_number}</strong><span>{version.mime_type || "File type unavailable"}</span><span>{formatBytes(version.file_size)}</span></div>
                {run && <div className="processing-summary"><StatusBadge status={run.status} />{run.review_required && <span className="review-needed"><AlertTriangle size={14} aria-hidden="true" /> Human review requested</span>}{run.safe_error && <p>{run.safe_error}</p>}{run.review_reasons.length > 0 && <p>{run.review_reasons.join(" · ")}</p>}</div>}
                {version.extracted_fields.length > 0 && (
                  <details className="extracted-fields-details">
                    <summary>{version.extracted_fields.length} extracted field{version.extracted_fields.length === 1 ? "" : "s"} · review values with their source</summary>
                    <div className="extracted-field-list">
                      {version.extracted_fields.map((field) => (
                        <div className="extracted-field" key={field.id}>
                          <div><strong>{field.field_name}</strong><span>{displayValue(field.field_value)}</span></div>
                          <div className="field-provenance">
                            {field.confidence !== null && <span>Confidence {Math.round(field.confidence * 100)}%</span>}
                            {field.page_number !== null && <span>Page {field.page_number}</span>}
                          </div>
                          {field.source_text && <details className="source-text-details"><summary>Source excerpt</summary><p>{field.source_text}</p></details>}
                        </div>
                      ))}
                    </div>
                  </details>
                )}
                <div className="version-actions">
                  {version.mime_type && ["application/pdf", "image/png", "image/jpeg"].includes(version.mime_type) && (
                    <Button variant="secondary" onClick={() => void preview(version)} icon={<Eye size={15} aria-hidden="true" />}>Preview</Button>
                  )}
                  <Button variant="quiet" onClick={() => void download(version)} icon={<Download size={15} aria-hidden="true" />}>Download file</Button>
                  {canRunProcessing && version.id === latest?.id && (
                    <Button variant="secondary" onClick={() => onProcess(version)} disabled={processing} icon={<RefreshCw size={15} aria-hidden="true" />}>
                      {processing ? "Processing…" : "Run processing"}
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
      {processingError && <div className="document-process-error"><ErrorNotice>{processingError}</ErrorNotice></div>}
      {latestRun && latestRun.completed_at && <p className="document-last-processed">Latest processing run completed {formatDateTime(latestRun.completed_at)}.</p>}
    </article>
  );
}

function displayValue(value: Record<string, unknown> | null): string {
  if (!value) return "Value unavailable";
  if ("value" in value) return String(value.value ?? "Value unavailable");
  const text = JSON.stringify(value);
  return text.length > 160 ? `${text.slice(0, 157)}…` : text;
}

function formatBytes(value: number | null): string {
  if (value === null) return "Size unavailable";
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(0)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDateTime(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium", timeStyle: "short" }).format(date);
}

function safeFilename(value: string): string {
  const safe = Array.from(value, (character) => {
    const code = character.charCodeAt(0);
    return /[\\/:*?"<>|]/.test(character) || code < 0x20 || code === 0x7f ? "_" : character;
  }).join("");
  return safe.slice(0, 180) || "document";
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}
