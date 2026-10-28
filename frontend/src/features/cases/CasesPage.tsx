import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, ChevronLeft, ChevronRight, Plus, Search, SlidersHorizontal } from "lucide-react";
import { Link } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { Button, EmptyState, ErrorNotice, ErrorState, Field, LoadingState, PageHeader, StatusBadge, SuccessNotice } from "../../components/Ui";

const PAGE_SIZE = 25;
const CASE_STATUSES = ["OPEN", "IN_PROGRESS", "PENDING_REVIEW", "COMPLETED", "REJECTED", "CANCELLED"];

export function CasesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(0);
  const [createOpen, setCreateOpen] = useState(false);
  const [success, setSuccess] = useState<string | null>(null);
  const casesQuery = useQuery({
    queryKey: queryKeys.cases(user, { status, skip: page * PAGE_SIZE, limit: PAGE_SIZE }),
    queryFn: () => api.cases.list({ status, skip: page * PAGE_SIZE, limit: PAGE_SIZE }),
    enabled: Boolean(user),
  });
  const visibleCases = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) return casesQuery.data ?? [];
    return (casesQuery.data ?? []).filter((item) =>
      `${item.case_number} ${item.title} ${item.status}`.toLowerCase().includes(needle),
    );
  }, [casesQuery.data, search]);
  const canGoNext = (casesQuery.data?.length ?? 0) === PAGE_SIZE;

  async function refreshCases() {
    await queryClient.invalidateQueries({ queryKey: ["cases"] });
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="OPERATIONS"
        title="Cases"
        description="Track process work from intake through verification and human decision."
        actions={<Button icon={<Plus size={17} aria-hidden="true" />} onClick={() => { setSuccess(null); setCreateOpen(true); }}>New case</Button>}
      />

      {success && <SuccessNotice>{success}</SuccessNotice>}
      <section className="panel case-register-panel">
        <div className="filter-toolbar">
          <div className="search-control">
            <Search size={17} aria-hidden="true" />
            <label className="sr-only" htmlFor="case-search">Search this page of cases</label>
            <input id="case-search" type="search" value={search} placeholder="Search this page" onChange={(event) => setSearch(event.target.value)} />
          </div>
          <div className="filter-select-wrap">
            <SlidersHorizontal size={16} aria-hidden="true" />
            <label className="sr-only" htmlFor="case-status-filter">Filter cases by status</label>
            <select
              id="case-status-filter"
              value={status}
              onChange={(event) => { setStatus(event.target.value); setPage(0); }}
            >
              <option value="">All statuses</option>
              {CASE_STATUSES.map((item) => <option key={item} value={item}>{item.replaceAll("_", " ")}</option>)}
            </select>
          </div>
          <span className="filter-scope-note">Search filters the current API page</span>
        </div>

        {casesQuery.isPending ? (
          <LoadingState label="Loading cases" />
        ) : casesQuery.isError ? (
          <ErrorState message={getError(casesQuery.error)} onRetry={() => void casesQuery.refetch()} />
        ) : visibleCases.length === 0 ? (
          <EmptyState
            title={search || status ? "No cases match these filters" : "No cases have been created"}
            description={search || status ? "Clear or adjust the current page filters to see more records." : "Start a case from a published process version when work arrives."}
            icon={<BriefcaseBusiness size={22} aria-hidden="true" />}
            action={search || status ? <Button variant="secondary" onClick={() => { setSearch(""); setStatus(""); setPage(0); }}>Clear filters</Button> : undefined}
          />
        ) : (
          <div className="table-scroll">
            <table className="data-table case-table">
              <thead>
                <tr><th scope="col">Case</th><th scope="col">Status</th><th scope="col">Updated</th><th scope="col"><span className="sr-only">Open case</span></th></tr>
              </thead>
              <tbody>
                {visibleCases.map((item) => (
                  <tr key={item.id}>
                    <td><Link className="case-number-link" to={`/cases/${item.id}`}>{item.case_number}</Link><span className="table-secondary">{item.title}</span></td>
                    <td><StatusBadge status={item.status} /></td>
                    <td>{formatDate(item.updated_at)}</td>
                    <td><Link className="icon-link" aria-label={`Open ${item.case_number}`} to={`/cases/${item.id}`}><ChevronRight size={17} aria-hidden="true" /></Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <div className="pagination-bar">
          <span>Page {page + 1} · {casesQuery.data?.length ?? 0} records returned</span>
          <div>
            <Button variant="secondary" onClick={() => setPage((value) => Math.max(0, value - 1))} disabled={page === 0} icon={<ChevronLeft size={15} aria-hidden="true" />}>Previous</Button>
            <Button variant="secondary" onClick={() => setPage((value) => value + 1)} disabled={!canGoNext} icon={<ChevronRight size={15} aria-hidden="true" />}>Next</Button>
          </div>
        </div>
        <p className="table-footnote">Cases are organization-scoped by the backend. The API returns at most 100 records per request and does not provide a total count or server-side text search.</p>
      </section>

      <CreateCaseDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={async (caseNumber) => {
          setCreateOpen(false);
          setSuccess(`Case ${caseNumber} was created.`);
          setPage(0);
          await refreshCases();
        }}
      />
    </div>
  );
}

function CreateCaseDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: (caseNumber: string) => Promise<void>;
}) {
  const { user } = useAuth();
  const [title, setTitle] = useState("");
  const [processId, setProcessId] = useState("");
  const [versionId, setVersionId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const processesQuery = useQuery({
    queryKey: queryKeys.processes(user),
    queryFn: () => api.processes.list(0, 100),
    enabled: open,
  });
  const versionsQuery = useQuery({
    queryKey: queryKeys.processVersions(user, processId),
    queryFn: () => api.processes.versions(processId),
    enabled: open && Boolean(processId),
  });
  const publishedVersions = (versionsQuery.data ?? []).filter((item) => item.status.toUpperCase() === "PUBLISHED");

  const createMutation = useMutation({
    mutationFn: () => api.cases.create({ title: title.trim(), process_version_id: versionId, case_metadata: {} }),
    onSuccess: async (createdCase) => {
      await onCreated(createdCase.case_number);
      setTitle("");
      setProcessId("");
      setVersionId("");
    },
    onError: (error) => setFormError(getError(error)),
  });

  function chooseProcess(value: string) {
    setProcessId(value);
    setVersionId("");
    setFormError(null);
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!versionId) {
      setFormError("Choose a published process version before creating the case.");
      return;
    }
    createMutation.mutate();
  }

  function close() {
    if (createMutation.isPending) return;
    onClose();
    setFormError(null);
  }

  return (
    <ConfirmDialog
      open={open}
      title="Create a case"
      description="Bind this case to a published process version. The backend assigns its case number and initial state."
      confirmLabel="Create case"
      onConfirm={() => (document.getElementById("create-case-form") as HTMLFormElement | null)?.requestSubmit()}
      onClose={close}
      busy={createMutation.isPending}
    >
      <form id="create-case-form" className="dialog-form" onSubmit={submit}>
        <Field id="case-title" label="Case title" hint="Use a concise name your team can recognize.">
          <input id="case-title" value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={255} disabled={createMutation.isPending} />
        </Field>
        <Field id="case-process" label="Process">
          <select id="case-process" value={processId} onChange={(event) => chooseProcess(event.target.value)} required disabled={processesQuery.isPending || createMutation.isPending}>
            <option value="">Select a process</option>
            {(processesQuery.data ?? []).filter((item) => item.status.toUpperCase() === "ACTIVE").map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
          </select>
        </Field>
        {processesQuery.isPending && <p className="field-hint">Loading available processes…</p>}
        {processesQuery.isError && <ErrorNotice>{getError(processesQuery.error)}</ErrorNotice>}
        {processId && (
          <Field id="case-process-version" label="Published version">
            <select id="case-process-version" value={versionId} onChange={(event) => setVersionId(event.target.value)} required disabled={versionsQuery.isPending || createMutation.isPending}>
              <option value="">Select a published version</option>
              {publishedVersions.map((version) => <option key={version.id} value={version.id}>Version {version.version_number}</option>)}
            </select>
          </Field>
        )}
        {versionsQuery.isPending && <p className="field-hint">Loading published versions…</p>}
        {versionsQuery.isError && <ErrorNotice>{getError(versionsQuery.error)}</ErrorNotice>}
        {processId && !versionsQuery.isPending && !versionsQuery.isError && publishedVersions.length === 0 && (
          <p className="inline-warning">This process has no published versions available for case intake.</p>
        )}
        {formError && <ErrorNotice>{formError}</ErrorNotice>}
      </form>
    </ConfirmDialog>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "—" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}
