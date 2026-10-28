import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BriefcaseBusiness, ChevronRight, Plus } from "lucide-react";
import { Link } from "react-router";
import { api } from "../../api/client";
import { queryKeys } from "../../api/queryKeys";
import { useAuth } from "../../auth/AuthContext";
import { Button, EmptyState, ErrorNotice, ErrorState, Field, LoadingState, PageHeader, StatusBadge, SuccessNotice } from "../../components/Ui";

export function CustomerCasesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [title, setTitle] = useState("");
  const [processVersionId, setProcessVersionId] = useState("");
  const [formError, setFormError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const casesQuery = useQuery({
    queryKey: queryKeys.customerCases(user),
    queryFn: () => api.cases.mine(),
    enabled: Boolean(user),
  });
  const processQuery = useQuery({
    queryKey: queryKeys.customerProcesses(user),
    queryFn: () => api.processes.customerOptions(),
    enabled: createOpen,
  });
  const createMutation = useMutation({
    mutationFn: () => api.cases.createMine({ title: title.trim(), process_version_id: processVersionId }),
    onSuccess: async (created) => {
      setSuccess(`Case ${created.case_number} was created.`);
      setCreateOpen(false);
      setTitle("");
      setProcessVersionId("");
      setFormError(null);
      await queryClient.invalidateQueries({ queryKey: queryKeys.customerCases(user) });
    },
    onError: (error) => setFormError(getError(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setFormError(null);
    if (!processVersionId) {
      setFormError("Choose an available process before starting the case.");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="page-stack">
      <PageHeader
        eyebrow="CUSTOMER PORTAL"
        title="Your cases"
        description="Start a case and follow its status, documents, and requests from your workspace."
        actions={<Button icon={<Plus size={17} aria-hidden="true" />} onClick={() => { setSuccess(null); setCreateOpen((open) => !open); }}>{createOpen ? "Close form" : "Start a case"}</Button>}
      />
      {success && <SuccessNotice>{success}</SuccessNotice>}
      {createOpen && (
        <section className="panel">
          <div className="section-heading"><div><p className="eyebrow">NEW REQUEST</p><h2>Start a case</h2></div></div>
          <form className="dialog-form" onSubmit={submit}>
            <Field id="customer-case-title" label="Case title" hint="Choose a name you will recognize later.">
              <input id="customer-case-title" value={title} onChange={(event) => setTitle(event.target.value)} required maxLength={255} disabled={createMutation.isPending} />
            </Field>
            <Field id="customer-case-process" label="Process">
              <select id="customer-case-process" value={processVersionId} onChange={(event) => setProcessVersionId(event.target.value)} required disabled={processQuery.isPending || createMutation.isPending}>
                <option value="">Choose a process</option>
                {(processQuery.data ?? []).map((process) => (
                  <option key={process.process_version_id} value={process.process_version_id}>{process.name}</option>
                ))}
              </select>
            </Field>
            {processQuery.isError && <ErrorNotice>{getError(processQuery.error)}</ErrorNotice>}
            {!processQuery.isPending && !processQuery.isError && (processQuery.data?.length ?? 0) === 0 && <p className="muted">There are no customer case processes available right now.</p>}
            {formError && <ErrorNotice>{formError}</ErrorNotice>}
            <div className="upload-actions"><Button type="submit" disabled={createMutation.isPending || !processVersionId}>{createMutation.isPending ? "Starting…" : "Create case"}</Button></div>
          </form>
        </section>
      )}

      {casesQuery.isPending ? <LoadingState label="Loading your cases" /> : casesQuery.isError ? (
        <ErrorState message={getError(casesQuery.error)} onRetry={() => void casesQuery.refetch()} />
      ) : (casesQuery.data?.length ?? 0) === 0 ? (
        <section className="panel"><EmptyState title="No cases yet" description="Start a case when you are ready to send a request to your organization." icon={<BriefcaseBusiness size={22} aria-hidden="true" />} action={<Button onClick={() => setCreateOpen(true)}>Start a case</Button>} /></section>
      ) : (
        <section className="panel case-register-panel">
          <div className="table-scroll">
            <table className="data-table case-table">
              <thead><tr><th scope="col">Case</th><th scope="col">Status</th><th scope="col">Documents</th><th scope="col">Updated</th><th scope="col"><span className="sr-only">Open case</span></th></tr></thead>
              <tbody>{casesQuery.data!.map((item) => (
                <tr key={item.id}>
                  <td><Link className="case-number-link" to={`/customer/cases/${item.id}`}>{item.case_number}</Link><span className="table-secondary">{item.title}</span></td>
                  <td><StatusBadge status={item.status} /></td>
                  <td>{item.documents.length}{item.document_requests.some((request) => request.status === "REQUESTED") && <span className="table-secondary"> · More needed</span>}</td>
                  <td>{formatDate(item.updated_at)}</td>
                  <td><Link className="icon-link" aria-label={`Open ${item.case_number}`} to={`/customer/cases/${item.id}`}><ChevronRight size={17} aria-hidden="true" /></Link></td>
                </tr>
              ))}</tbody>
            </table>
          </div>
          <p className="table-footnote">This list contains only cases linked to your customer account.</p>
        </section>
      )}
    </div>
  );
}

function formatDate(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "Date unavailable" : new Intl.DateTimeFormat(undefined, { dateStyle: "medium" }).format(date);
}

function getError(error: unknown): string {
  return error instanceof Error ? error.message : "The request failed.";
}
